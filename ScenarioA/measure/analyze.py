#!/usr/bin/env python3
"""Scenario A - Phase 9 : analyse automatique d'un repertoire d'experience.

Usage : python3 analyze.py ../experiments/<RUN_ID>

Entrees (produites par run_experiments.py) :
  phase8_{before,after}_flows_sN.txt   tables de flux OpenFlow
  phase8_{before,after}_ports_sN.txt   compteurs de ports OpenFlow
  phase8_{before,after}_timestamps.json  instant de chaque snapshot
  phase8_iperf3_udp.json, phase8_h1_udp.pcap, phase8_params.json
  phase7_iperf3_*.json

Sorties : analysis_summary.csv (une ligne par metrique) et analysis_report.md.
Aucune dependance externe, pas besoin de root.
"""

import csv
import json
import re
import statistics
import struct
import sys
from pathlib import Path

SWITCHES = ["s1", "s2", "s3"]
# (switch, port) emetteur -> (switch, port) recepteur, sens h1 -> h4
INTER_SWITCH = [(("s1", 3), ("s2", 1)), (("s2", 2), ("s3", 3))]
EDGE_IN, EDGE_OUT = ("s1", 1), ("s3", 2)      # h1 -> s1, s3 -> h4
EXPECTED_OUT = {"s1": 3, "s2": 2, "s3": 2}

FLOW_RE = re.compile(r"n_packets=(\d+), n_bytes=(\d+), (?:\S+_timeout=\d+, )*(\S+) actions=(\S+)")
PORT_RE = re.compile(
    r"port\s+(\S+): rx pkts=(\d+), bytes=(\d+), drop=(\d+).*?\n\s+tx pkts=(\d+), bytes=(\d+), drop=(\d+)")


# ----------------------------------------------------------------- parsers
def parse_flows(path):
    """{(match, actions): (packets, bytes)}"""
    return {(m, a): (int(p), int(b)) for p, b, m, a in FLOW_RE.findall(path.read_text())}


def parse_ports(path):
    """{port: {rx_pkts, rx_bytes, rx_drop, tx_pkts, tx_bytes, tx_drop}}"""
    keys = ["rx_pkts", "rx_bytes", "rx_drop", "tx_pkts", "tx_bytes", "tx_drop"]
    out = {}
    for port, *vals in PORT_RE.findall(path.read_text()):
        if port.isdigit():
            out[int(port)] = dict(zip(keys, map(int, vals)))
    return out


def parse_iperf(path):
    d = json.loads(path.read_text())
    if "error" in d:
        return {"error": d["error"]}
    end, start = d["end"], d["start"]
    udp = start["test_start"]["protocol"] == "UDP"
    sent, recv = end["sum_sent"], end["sum_received"]
    r = {"protocol": "UDP" if udp else "TCP",
         "duration_s": start["test_start"]["duration"],
         "payload_bytes": start["test_start"]["blksize"],
         "sender_mbps": sent["bits_per_second"] / 1e6,
         "receiver_mbps": recv["bits_per_second"] / 1e6,
         "sent_bytes": sent["bytes"], "received_bytes": recv["bytes"]}
    if udp:
        r.update(offered_mbps=start.get("target_bitrate", 0) / 1e6,
                 sent_packets=sent["packets"], lost_packets=recv["lost_packets"],
                 lost_percent=recv["lost_percent"], jitter_ms=recv["jitter_ms"])
    else:
        r.update(retransmits=sent.get("retransmits"))
    return r


def parse_pcap(path):
    """Lit un PCAP classique (Ethernet/IPv4) sans bibliotheque externe."""
    data = path.read_bytes()
    magic = data[:4]
    fmt = {b"\xd4\xc3\xb2\xa1": ("<", 1e-6), b"\xa1\xb2\xc3\xd4": (">", 1e-6),
           b"\x4d\x3c\xb2\xa1": ("<", 1e-9), b"\xa1\xb2\x3c\x4d": (">", 1e-9)}.get(magic)
    if not fmt:
        raise ValueError("format PCAP non reconnu")
    endian, frac = fmt
    snaplen, linktype = struct.unpack(endian + "II", data[16:24])
    off, ts, sizes, tuples = 24, [], [], {}
    while off + 16 <= len(data):
        sec, sub, incl, orig = struct.unpack(endian + "IIII", data[off:off + 16])
        pkt = data[off + 16:off + 16 + incl]
        off += 16 + incl
        ts.append(sec + sub * frac)
        sizes.append(orig)
        if len(pkt) >= 42 and pkt[12:14] == b"\x08\x00":
            ihl = (pkt[14] & 0x0F) * 4
            proto = pkt[23]
            src = ".".join(map(str, pkt[26:30]))
            dst = ".".join(map(str, pkt[30:34]))
            sport, dport = struct.unpack("!HH", pkt[14 + ihl:18 + ihl])
            key = (src, dst, {17: "UDP", 6: "TCP"}.get(proto, str(proto)), dport)
        else:
            key = ("non-IPv4", "", "", 0)
        tuples[key] = tuples.get(key, 0) + 1
    gaps = [b - a for a, b in zip(ts, ts[1:])]
    span = ts[-1] - ts[0] if len(ts) > 1 else 0.0
    return {"packets": len(ts), "snaplen": snaplen, "linktype": linktype,
            "first_ts": ts[0] if ts else None, "last_ts": ts[-1] if ts else None,
            "span_s": span, "tuples": tuples,
            "frame_min": min(sizes, default=0), "frame_max": max(sizes, default=0),
            "frame_mean": statistics.fmean(sizes) if sizes else 0,
            "wire_bytes": sum(sizes),
            "gap_mean_ms": statistics.fmean(gaps) * 1e3 if gaps else 0,
            "gap_median_ms": statistics.median(gaps) * 1e3 if gaps else 0,
            "gap_max_ms": max(gaps, default=0) * 1e3,
            "rate_mbps": sum(sizes) * 8 / span / 1e6 if span else 0}


# ---------------------------------------------------------------- analysis
def analyze(run):
    rows, md, checks = [], [], []

    def row(scope, metric, value, unit=""):
        rows.append({"run_id": run.name, "scope": scope, "metric": metric,
                     "value": value, "unit": unit})

    def check(name, ok, detail):
        checks.append((name, ok, detail))
        row("check", name, "PASS" if ok else "FAIL", detail)

    params = json.loads((run / "phase8_params.json").read_text())
    src_mac, dst_mac = params["src_mac_h1"], params["dst_mac_h4"]
    t0 = json.loads((run / "phase8_before_timestamps.json").read_text())
    t1 = json.loads((run / "phase8_after_timestamps.json").read_text())

    # ---- Phase 7 : caracterisation iperf3
    md += ["## Phase 7 — iperf3 h1 → h4", "",
           "| test | offert (Mbit/s) | emis | recu | perte % | gigue (ms) | retrans. TCP |",
           "|---|---|---|---|---|---|---|"]
    order = ["tcp", "udp_50M", "udp_80M", "udp_100M"]
    for f in sorted(run.glob("phase7_iperf3_*.json"),
                    key=lambda p: (order + [p.stem[14:]]).index(p.stem[14:])):
        name = f.stem.replace("phase7_iperf3_", "")
        r = parse_iperf(f)
        if "error" in r:
            md.append("| %s | erreur : %s |||||" % (name, r["error"]))
            continue
        for k, v in r.items():
            row("phase7/" + name, k, round(v, 4) if isinstance(v, float) else v)
        md.append("| %s | %s | %.2f | %.2f | %s | %s | %s |" % (
            name, "%.0f" % r["offered_mbps"] if "offered_mbps" in r else "—",
            r["sender_mbps"], r["receiver_mbps"],
            "%.3f" % r["lost_percent"] if "lost_percent" in r else "—",
            "%.3f" % r["jitter_ms"] if "jitter_ms" in r else "—",
            r.get("retransmits", "—")))

    # ---- Phase 8 : iperf3 + PCAP
    ip = parse_iperf(run / "phase8_iperf3_udp.json")
    for k, v in ip.items():
        row("phase8/iperf3", k, round(v, 4) if isinstance(v, float) else v)
    pc = parse_pcap(run / "phase8_h1_udp.pcap")
    for k, v in pc.items():
        if k != "tuples":
            row("phase8/pcap", k, round(v, 6) if isinstance(v, float) else v)
    selected = ("10.0.0.1", "10.0.0.4", "UDP", 5201)
    n_sel = pc["tuples"].get(selected, 0)
    row("phase8/pcap", "packets_matching_selected_udp_flow", n_sel)
    check("pcap_borne", pc["packets"] <= params["capture_packet_limit"],
          "%d <= %d paquets" % (pc["packets"], params["capture_packet_limit"]))
    check("pcap_flux_attendu", n_sel == pc["packets"] and n_sel > 0,
          "%d/%d paquets = 10.0.0.1 -> 10.0.0.4 UDP dport 5201" % (n_sel, pc["packets"]))

    # ---- Phase 8 : deltas des regles de flux
    md += ["", "## Phase 8 — flux OpenFlow h1 → h4 (deltas avant/apres)", "",
           "| switch | regle | sortie | Δ paquets | Δ octets | intervalle (s) | debit moyen sur l'intervalle (Mbit/s) |",
           "|---|---|---|---|---|---|---|"]
    fwd, miss = {}, {}
    for sw in SWITCHES:
        before = parse_flows(run / ("phase8_before_flows_%s.txt" % sw))
        after = parse_flows(run / ("phase8_after_flows_%s.txt" % sw))
        dt = t1[sw] - t0[sw]
        row("phase8/" + sw, "snapshot_interval_s", round(dt, 6), "s")
        for (match, actions), (p1, b1) in after.items():
            p0, b0 = before.get((match, actions), (0, 0))
            dp, db = p1 - p0, b1 - b0
            row("phase8/%s/flow" % sw, match + " " + actions + " delta_packets", dp)
            row("phase8/%s/flow" % sw, match + " " + actions + " delta_bytes", db)
            if "dl_dst=" + dst_mac in match and ("dl_src=" not in match or "dl_src=" + src_mac in match):
                fwd[sw] = (dp, db, actions)
                md.append("| %s | `%s` | `%s` | %d | %d | %.3f | %.2f |" % (
                    sw, match, actions, dp, db, dt, db * 8 / dt / 1e6))
                row("phase8/" + sw, "fwd_flow_mbps_over_snapshot_interval", round(db * 8 / dt / 1e6, 4), "Mbit/s")
            if match == "priority=0":
                miss[sw] = dp
                row("phase8/" + sw, "table_miss_delta_packets", dp)

    check("regle_h1_h4_presente", len(fwd) == 3, "trouvee sur %s" % (sorted(fwd) or "aucun switch"))
    if len(fwd) == 3:
        check("chemin_conforme", all(fwd[s][2] == "output:%d" % EXPECTED_OUT[s] for s in SWITCHES),
              ", ".join("%s %s" % (s, fwd[s][2]) for s in SWITCHES))
        check("deltas_flux_identiques", len({fwd[s][:2] for s in SWITCHES}) == 1,
              ", ".join("%s=%d pkts/%d o" % (s, fwd[s][0], fwd[s][1]) for s in SWITCHES))
    check("pas_de_trafic_via_controleur", all(v < 50 for v in miss.values()),
          "Δ table-miss : " + ", ".join("%s=%d" % kv for kv in sorted(miss.items())))

    # ---- Phase 8 : compteurs de ports
    dports = {}
    for sw in SWITCHES:
        b = parse_ports(run / ("phase8_before_ports_%s.txt" % sw))
        a = parse_ports(run / ("phase8_after_ports_%s.txt" % sw))
        dports[sw] = {p: {k: a[p][k] - b.get(p, {}).get(k, 0) for k in a[p]} for p in a}
        for p, d in dports[sw].items():
            for k, v in d.items():
                row("phase8/%s/port%d" % (sw, p), "delta_" + k, v)
    md += ["", "## Phase 8 — compteurs de ports sur le chemin (sens h1 → h4)", "",
           "| lien | Δ tx paquets | Δ rx paquets | Δ tx octets | Δ rx octets | drops tx |",
           "|---|---|---|---|---|---|"]
    for (sa, pa), (sb, pb) in INTER_SWITCH:
        tx, rx = dports[sa][pa], dports[sb][pb]
        md.append("| %s:%d → %s:%d | %d | %d | %d | %d | %d |" % (
            sa, pa, sb, pb, tx["tx_pkts"], rx["rx_pkts"], tx["tx_bytes"], rx["rx_bytes"], tx["tx_drop"]))
        check("ports_%s_%s_coherents" % (sa, sb),
              tx["tx_pkts"] == rx["rx_pkts"] and tx["tx_bytes"] == rx["rx_bytes"],
              "tx %d pkts/%d o, rx %d pkts/%d o" % (tx["tx_pkts"], tx["tx_bytes"], rx["rx_pkts"], rx["rx_bytes"]))
    e_in, e_out = dports[EDGE_IN[0]][EDGE_IN[1]], dports[EDGE_OUT[0]][EDGE_OUT[1]]
    md.append("| h1 → s1:1 (rx) / s3:2 → h4 (tx) | %d | %d | %d | %d | %d |" % (
        e_out["tx_pkts"], e_in["rx_pkts"], e_out["tx_bytes"], e_in["rx_bytes"], e_out["tx_drop"]))

    # ---- agregat (regle MAC) vs flux UDP etudie
    if len(fwd) == 3 and "sent_packets" in ip:
        agg_p, agg_b = fwd["s1"][:2]
        udp_wire = ip["sent_packets"] * (ip["payload_bytes"] + 42)   # +Eth 14 +IP 20 +UDP 8
        row("phase8/compare", "flow_rule_packets_minus_iperf_udp_packets", agg_p - ip["sent_packets"])
        row("phase8/compare", "flow_rule_bytes_minus_iperf_udp_wire_bytes", agg_b - udp_wire)
        md += ["", "## Agregat (regle MAC) vs flux UDP etudie", "",
               "- Regle h1→h4 sur s1 : **%d paquets, %d octets** (tout le trafic h1→h4 : UDP, "
               "connexion de controle TCP d'iperf3, ping de preparation)." % (agg_p, agg_b),
               "- iperf3 UDP emis : **%d datagrammes**, soit %d octets sur le fil (%d + 42 octets d'en-tetes chacun)."
               % (ip["sent_packets"], udp_wire, ip["payload_bytes"]),
               "- Ecart : %d paquets, %d octets = trafic non-UDP compte par la regle."
               % (agg_p - ip["sent_packets"], agg_b - udp_wire),
               "- PCAP (borne a %d paquets, filtre UDP dport 5201) : %d paquets sur %.3f s, trame %d-%d octets, "
               "intervalle median %.3f ms, debit sur la fenetre capturee %.2f Mbit/s."
               % (params["capture_packet_limit"], pc["packets"], pc["span_s"], pc["frame_min"],
                  pc["frame_max"], pc["gap_median_ms"], pc["rate_mbps"]),
               "- Intervalle moyen entre paquets captures : %.3f ms (iperf3 emet par rafales, d'ou une mediane tres basse) ; "
               "la plus petite trame (%d octets) est le datagramme d'ouverture d'iperf3."
               % (pc["gap_mean_ms"], pc["frame_min"]),
               "- Le debit « sur l'intervalle de snapshot » inclut les temps morts avant/apres iperf3 : "
               "il sous-estime le debit pendant l'emission et ne doit pas etre compare tel quel aux %.2f Mbit/s d'iperf3."
               % ip["sender_mbps"]]

    head = ["# Analyse %s" % run.name, "",
            "Flux etudie : %s, debit offert %s, duree %s s." % (
                params["flow"], params["offered_rate"], params["duration_s"]), "",
            "iperf3 (Phase 8) : emis %.2f Mbit/s, recu %.2f Mbit/s, perte %.3f %% (%d/%d), gigue %.3f ms." % (
                ip["sender_mbps"], ip["receiver_mbps"], ip["lost_percent"],
                ip["lost_packets"], ip["sent_packets"], ip["jitter_ms"]), "",
            "## Verifications", "", "| verification | resultat | detail |", "|---|---|---|"]
    head += ["| %s | **%s** | %s |" % (n, "PASS" if ok else "FAIL", d) for n, ok, d in checks]
    (run / "analysis_report.md").write_text("\n".join(head + [""] + md) + "\n")
    with open(run / "analysis_summary.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["run_id", "scope", "metric", "value", "unit"])
        w.writeheader()
        w.writerows(rows)
    return all(ok for _, ok, _ in checks)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    run_dir = Path(sys.argv[1]).resolve()
    ok = analyze(run_dir)
    print((run_dir / "analysis_report.md").read_text())
    sys.exit(0 if ok else 1)
