"""Scenario A - learning switch OpenFlow 1.3 pour OS-Ken.

Principe (Phase 6 du sujet) :
  1. a la connexion d'un switch, on installe la regle "table-miss"
     (priorite 0, tout paquet inconnu -> envoye au controleur) ;
  2. a chaque packet-in, on apprend "MAC source -> port d'entree" ;
  3. si la MAC destination est connue, on installe une regle de priorite 1
     (match eth_dst -> output port) puis on renvoie le paquet ;
     sinon on inonde (FLOOD).

Les regles apprises matchent (in_port, eth_src, eth_dst) : un compteur de flux
agrege donc TOUT le trafic h1 -> h4 (UDP, controle TCP d'iperf3, ICMP...),
pas seulement le flux UDP etudie (distinction demandee en Phase 9).
"""

from os_ken.base import app_manager
from os_ken.controller import ofp_event
from os_ken.controller.handler import (
    CONFIG_DISPATCHER,
    DEAD_DISPATCHER,
    MAIN_DISPATCHER,
    set_ev_cls,
)
from os_ken.lib.packet import ether_types, ethernet, packet
from os_ken.ofproto import ofproto_v1_3

TABLE_MISS_PRIORITY = 0
LEARNED_PRIORITY = 1


class ScenarioALearningSwitch(app_manager.OSKenApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # {dpid: {mac: port}}
        self.mac_to_port = {}

    # ------------------------------------------------------------------ utils
    def add_flow(self, datapath, priority, match, actions):
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        mod = parser.OFPFlowMod(
            datapath=datapath, priority=priority, match=match, instructions=inst
        )
        datapath.send_msg(mod)

    # --------------------------------------------------------------- handlers
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        self.logger.info(
            "SWITCH_CONNECTED dpid=%016x ofp_version=0x%02x",
            datapath.id,
            ev.msg.version,
        )
        # Regle table-miss : tout ce qui ne matche rien part au controleur.
        match = parser.OFPMatch()
        actions = [
            parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)
        ]
        self.add_flow(datapath, TABLE_MISS_PRIORITY, match, actions)
        self.logger.info("FLOW_MOD dpid=%016x table-miss installed", datapath.id)

    @set_ev_cls(ofp_event.EventOFPStateChange, [DEAD_DISPATCHER])
    def switch_dead_handler(self, ev):
        datapath = ev.datapath
        if datapath.id is not None:
            self.logger.info("SWITCH_DISCONNECTED dpid=%016x", datapath.id)
            self.mac_to_port.pop(datapath.id, None)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match["in_port"]
        dpid = datapath.id

        eth = packet.Packet(msg.data).get_protocols(ethernet.ethernet)[0]
        if eth.ethertype in (ether_types.ETH_TYPE_LLDP, ether_types.ETH_TYPE_IPV6):
            return  # bruit (LLDP, IPv6 ND) : on ne l'apprend pas, on ne l'inonde pas
        src, dst = eth.src, eth.dst

        table = self.mac_to_port.setdefault(dpid, {})
        self.logger.info(
            "PACKET_IN dpid=%016x in_port=%s src=%s dst=%s", dpid, in_port, src, dst
        )
        if table.get(src) != in_port:
            table[src] = in_port
            self.logger.info(
                "MAC_LEARNED dpid=%016x mac=%s port=%s", dpid, src, in_port
            )

        out_port = table.get(dst, ofproto.OFPP_FLOOD)
        actions = [parser.OFPActionOutput(out_port)]

        if out_port != ofproto.OFPP_FLOOD:
            # Match sur (port d'entree, MAC source, MAC destination), et pas sur
            # la seule destination : avec eth_dst seul, des qu'une regle "vers h1"
            # existe, les trames h4 -> h1 ne remontent plus au controleur, qui
            # n'apprend donc jamais la MAC de h4 sur ce switch ; tout le trafic
            # vers h4 reste alors inonde via le controleur (constate au run
            # run-20261116T124705Z : 43 % de perte UDP a 50 Mbit/s).
            match = parser.OFPMatch(in_port=in_port, eth_src=src, eth_dst=dst)
            self.add_flow(datapath, LEARNED_PRIORITY, match, actions)
            self.logger.info(
                "FLOW_MOD dpid=%016x in_port=%s eth_src=%s eth_dst=%s -> output:%s",
                dpid, in_port, src, dst, out_port,
            )
        else:
            self.logger.info("FLOOD dpid=%016x dst=%s unknown", dpid, dst)

        data = msg.data if msg.buffer_id == ofproto.OFP_NO_BUFFER else None
        out = parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=msg.buffer_id,
            in_port=in_port,
            actions=actions,
            data=data,
        )
        datapath.send_msg(out)
