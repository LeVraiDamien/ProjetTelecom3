"""Scenario A - Phase 10 : classification de trafic + politique SDN (OS-Ken, OF 1.3).

Pipeline a deux tables sur chaque switch :

  table 0 = CLASSIFICATION
    prio 10  une regle par flux TCP/UDP (5-tuple)  -> [meter] puis goto table 1
    prio  5  IPv4 TCP ou UDP encore inconnu        -> controleur (1er paquet du flux)
    prio  0  tout le reste (ARP, ICMP...)          -> goto table 1
  table 1 = COMMUTATION (le learning switch des phases precedentes, inchange)

La classification ne touche donc jamais a l'acheminement : elle observe (compteurs
de la regle par flux) et, si la politique le demande, ajoute un meter.

Deroule pour un flux :
  1. 1er paquet -> packet-in table 0 -> le controleur cree l'etat du flux et installe
     la regle 5-tuple (evenement flow_new). Le switch ou le flux est vu en premier
     est son switch d'entree (ingress) ; c'est la qu'on mesure et qu'on applique
     la politique.
  2. Chaque seconde le controleur lit les compteurs OpenFlow de la table 0 et calcule,
     par flux : debit sur l'intervalle et taille moyenne de paquet (evenement obs).
  3. Regle de decision transparente (evenement classify) :
       BULK  si debit >= BULK_RATE_MBPS ET taille moyenne >= BULK_PKT_BYTES
             pendant 2 intervalles consecutifs ; sinon LIGHT.
       Classe = <TCP|UDP>_<BULK|LIGHT>. Decision au 2e intervalle actif ; un flux
       LIGHT peut devenir BULK plus tard, jamais l'inverse (stabilite).
  4. Politique (evenement policy), seulement si POLICY_MODE=enforce :
       UDP_BULK -> meter 1 (drop au-dela de UDP_BULK_LIMIT_KBPS) sur le switch d'entree.
     En POLICY_MODE=monitor, on classe sans rien changer (experience temoin).

Tous les evenements sortent sur stdout sous la forme "EVT {json}" pour l'analyse.
"""

import json
import os
import time

from os_ken.base import app_manager
from os_ken.controller import ofp_event
from os_ken.controller.handler import (
    CONFIG_DISPATCHER,
    DEAD_DISPATCHER,
    MAIN_DISPATCHER,
    set_ev_cls,
)
from os_ken.lib import hub
from os_ken.lib.packet import ether_types, ethernet, ipv4, packet, tcp, udp
from os_ken.ofproto import ofproto_v1_3

POLICY_VERSION = "p10-rules-v1"
POLL_INTERVAL_S = 1.0
BULK_RATE_MBPS = 10.0       # seuil de debit (justifie par les mesures, voir rapport)
BULK_PKT_BYTES = 1000       # seuil de taille moyenne de paquet
BULK_STREAK = 2             # intervalles consecutifs requis
UDP_BULK_METER_ID = 1
UDP_BULK_LIMIT_KBPS = 20000
UDP_BULK_BURST_KB = 2000
FLOW_IDLE_TIMEOUT_S = 30

T_CLASSIFY, T_SWITCH = 0, 1
PROTO_NAME = {6: "TCP", 17: "UDP"}


def evt(kind, **fields):
    print("EVT " + json.dumps({"ts": round(time.time(), 6), "type": kind, **fields}), flush=True)


class TrafficClassifier(app_manager.OSKenApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mode = os.environ.get("POLICY_MODE", "monitor")
        self.datapaths = {}
        self.mac_to_port = {}    # {dpid: {mac: port}}
        self.flows = {}          # cookie -> etat du flux sur un switch
        self.by_key = {}         # (dpid, 5-tuple) -> cookie
        self.ingress = {}        # 5-tuple -> dpid du switch d'entree
        self.next_cookie = 1
        evt("start", mode=self.mode, policy_version=POLICY_VERSION,
            bulk_rate_mbps=BULK_RATE_MBPS, bulk_pkt_bytes=BULK_PKT_BYTES,
            bulk_streak=BULK_STREAK, udp_bulk_limit_kbps=UDP_BULK_LIMIT_KBPS,
            poll_interval_s=POLL_INTERVAL_S)
        hub.spawn(self._poll_loop)

    # ------------------------------------------------------------------ utils
    def _flow_mod(self, dp, table, priority, match, inst, cookie=0, idle=0, command=None):
        ofp, parser = dp.ofproto, dp.ofproto_parser
        dp.send_msg(parser.OFPFlowMod(
            datapath=dp, table_id=table, priority=priority, match=match,
            instructions=inst, cookie=cookie, idle_timeout=idle,
            command=ofp.OFPFC_ADD if command is None else command))

    def _install_flow_rule(self, dp, f, command=None):
        """Regle 5-tuple de la table 0 : [meter] + goto table de commutation."""
        parser = dp.ofproto_parser
        inst = []
        if f["meter"]:
            inst.append(parser.OFPInstructionMeter(f["meter"], dp.ofproto.OFPIT_METER))
        inst.append(parser.OFPInstructionGotoTable(T_SWITCH))
        self._flow_mod(dp, T_CLASSIFY, 10, parser.OFPMatch(**f["match"]), inst,
                       cookie=f["cookie"], idle=FLOW_IDLE_TIMEOUT_S, command=command)
        f["installed"] = time.time()

    # --------------------------------------------------------------- handlers
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        dp = ev.msg.datapath
        ofp, parser = dp.ofproto, dp.ofproto_parser
        self.logger.info("SWITCH_CONNECTED dpid=%016x ofp_version=0x%02x", dp.id, ev.msg.version)

        # Meter de la classe UDP_BULK (cree partout, utilise seulement en mode enforce).
        for cmd in (ofp.OFPMC_DELETE, ofp.OFPMC_ADD):
            dp.send_msg(parser.OFPMeterMod(
                datapath=dp, command=cmd, flags=ofp.OFPMF_KBPS | ofp.OFPMF_BURST,
                meter_id=UDP_BULK_METER_ID,
                bands=[parser.OFPMeterBandDrop(rate=UDP_BULK_LIMIT_KBPS,
                                               burst_size=UDP_BULK_BURST_KB)]))

        to_ctrl = [parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, [
            parser.OFPActionOutput(ofp.OFPP_CONTROLLER, ofp.OFPCML_NO_BUFFER)])]
        goto_switch = [parser.OFPInstructionGotoTable(T_SWITCH)]
        self._flow_mod(dp, T_CLASSIFY, 0, parser.OFPMatch(), goto_switch)
        for proto in (6, 17):
            self._flow_mod(dp, T_CLASSIFY, 5,
                           parser.OFPMatch(eth_type=0x0800, ip_proto=proto), to_ctrl)
        self._flow_mod(dp, T_SWITCH, 0, parser.OFPMatch(), to_ctrl)   # table-miss

    @set_ev_cls(ofp_event.EventOFPStateChange, [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def state_change_handler(self, ev):
        dp = ev.datapath
        if ev.state == MAIN_DISPATCHER:
            self.datapaths[dp.id] = dp
        elif dp.id in self.datapaths:
            self.logger.info("SWITCH_DISCONNECTED dpid=%016x", dp.id)
            del self.datapaths[dp.id]
            self.mac_to_port.pop(dp.id, None)

    @set_ev_cls(ofp_event.EventOFPErrorMsg, [CONFIG_DISPATCHER, MAIN_DISPATCHER])
    def error_handler(self, ev):
        m = ev.msg
        evt("of_error", dpid=m.datapath.id, err_type=m.type, err_code=m.code)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        if ev.msg.table_id == T_CLASSIFY:
            self._new_flow_packet(ev.msg)
        else:
            self._learning_switch(ev.msg)

    # ------------------------------------------------- table 0 : classification
    def _new_flow_packet(self, msg):
        dp = msg.datapath
        ofp, parser = dp.ofproto, dp.ofproto_parser
        in_port = msg.match["in_port"]
        pkt = packet.Packet(msg.data)
        ip = pkt.get_protocol(ipv4.ipv4)
        l4 = pkt.get_protocol(tcp.tcp) or pkt.get_protocol(udp.udp)
        if ip and l4:
            proto = PROTO_NAME[ip.proto]
            key = (ip.src, ip.dst, proto, l4.src_port, l4.dst_port)
            cookie = self.by_key.get((dp.id, key))
            if cookie is None:
                cookie = self.next_cookie
                self.next_cookie += 1
                self.by_key[(dp.id, key)] = cookie
                is_ingress = self.ingress.setdefault(key, dp.id) == dp.id
                l4name = proto.lower()
                self.flows[cookie] = {
                    "cookie": cookie, "dpid": dp.id, "key": key, "ingress": is_ingress,
                    "match": {"in_port": in_port, "eth_type": 0x0800, "ip_proto": ip.proto,
                              "ipv4_src": ip.src, "ipv4_dst": ip.dst,
                              l4name + "_src": l4.src_port, l4name + "_dst": l4.dst_port},
                    "meter": 0, "cls": None, "n_obs": 0, "streak": 0,
                    "last": None, "installed": 0.0,
                }
                if is_ingress:
                    evt("flow_new", flow=cookie, dpid=dp.id, in_port=in_port, src=ip.src,
                        dst=ip.dst, proto=proto, sport=l4.src_port, dport=l4.dst_port)
            f = self.flows[cookie]
            # (Re)installe la regle si elle est absente ou a expire ; les packet-in
            # en rafale du meme flux ne la reinstallent pas (anti-rebond 0,5 s).
            if time.time() - f["installed"] > 0.5:
                self._install_flow_rule(dp, f)
        # Le paquet repart dans le pipeline : il matche maintenant la regle du flux.
        dp.send_msg(parser.OFPPacketOut(
            datapath=dp, buffer_id=ofp.OFP_NO_BUFFER, in_port=in_port,
            actions=[parser.OFPActionOutput(ofp.OFPP_TABLE)], data=msg.data))

    # ---------------------------------------------- table 1 : learning switch
    def _learning_switch(self, msg):
        dp = msg.datapath
        ofp, parser = dp.ofproto, dp.ofproto_parser
        in_port = msg.match["in_port"]
        eth = packet.Packet(msg.data).get_protocols(ethernet.ethernet)[0]
        if eth.ethertype in (ether_types.ETH_TYPE_LLDP, ether_types.ETH_TYPE_IPV6):
            return
        table = self.mac_to_port.setdefault(dp.id, {})
        table[eth.src] = in_port
        out_port = table.get(eth.dst, ofp.OFPP_FLOOD)
        actions = [parser.OFPActionOutput(out_port)]
        if out_port != ofp.OFPP_FLOOD:
            match = parser.OFPMatch(in_port=in_port, eth_src=eth.src, eth_dst=eth.dst)
            self._flow_mod(dp, T_SWITCH, 1, match,
                           [parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions)])
        dp.send_msg(parser.OFPPacketOut(
            datapath=dp, buffer_id=ofp.OFP_NO_BUFFER, in_port=in_port,
            actions=actions, data=msg.data))

    # ------------------------------------------------ mesure et classification
    def _poll_loop(self):
        while True:
            for dp in list(self.datapaths.values()):
                parser = dp.ofproto_parser
                dp.send_msg(parser.OFPFlowStatsRequest(dp, table_id=T_CLASSIFY))
            hub.sleep(POLL_INTERVAL_S)

    @set_ev_cls(ofp_event.EventOFPFlowStatsReply, MAIN_DISPATCHER)
    def flow_stats_reply_handler(self, ev):
        dp = ev.msg.datapath
        for st in ev.msg.body:
            f = self.flows.get(st.cookie)
            if not f or f["dpid"] != dp.id or not f["ingress"]:
                continue
            dur = st.duration_sec + st.duration_nsec / 1e9   # horloge du switch
            cur = (dur, st.packet_count, st.byte_count)
            last, f["last"] = f["last"], cur
            if last is None or dur <= last[0] or st.packet_count < last[1]:
                continue                                     # 1re lecture ou regle reinstallee
            dt, dp_pkts, d_bytes = dur - last[0], st.packet_count - last[1], st.byte_count - last[2]
            if dp_pkts == 0:
                f["streak"] = 0
                continue
            rate = d_bytes * 8 / dt / 1e6
            mean = d_bytes / dp_pkts
            f["n_obs"] += 1
            bulk_now = rate >= BULK_RATE_MBPS and mean >= BULK_PKT_BYTES
            f["streak"] = f["streak"] + 1 if bulk_now else 0
            evt("obs", flow=f["cookie"], dpid=dp.id, interval_s=round(dt, 4),
                packets=dp_pkts, bytes=d_bytes, rate_mbps=round(rate, 3),
                mean_pkt_bytes=round(mean, 1), total_packets=st.packet_count,
                total_bytes=st.byte_count, flow_duration_s=round(dur, 3))
            self._classify(dp, f, rate, mean)

    def _classify(self, dp, f, rate, mean):
        proto = f["key"][2]
        new = None
        if f["cls"] is None and f["n_obs"] >= BULK_STREAK:
            new = proto + ("_BULK" if f["streak"] >= BULK_STREAK else "_LIGHT")
        elif f["cls"] and f["cls"].endswith("_LIGHT") and f["streak"] >= BULK_STREAK:
            new = proto + "_BULK"
        if not new:
            return
        previous, f["cls"] = f["cls"], new
        evt("classify", flow=f["cookie"], dpid=dp.id, cls=new, previous=previous,
            rate_mbps=round(rate, 3), mean_pkt_bytes=round(mean, 1),
            bulk_streak=f["streak"], n_obs=f["n_obs"], policy_version=POLICY_VERSION)

        if new == "UDP_BULK" and self.mode == "enforce":
            f["meter"] = UDP_BULK_METER_ID
            # MODIFY_STRICT : change les instructions sans remettre les compteurs a zero.
            self._install_flow_rule(dp, f, command=dp.ofproto.OFPFC_MODIFY_STRICT)
            evt("policy", flow=f["cookie"], dpid=dp.id, cls=new, action="meter",
                meter_id=UDP_BULK_METER_ID, limit_kbps=UDP_BULK_LIMIT_KBPS, executed=True)
        else:
            evt("policy", flow=f["cookie"], dpid=dp.id, cls=new, action="none",
                executed=False,
                reason="mode monitor" if new == "UDP_BULK" else "classe sans restriction")
