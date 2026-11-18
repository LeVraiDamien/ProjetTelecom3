#!/usr/bin/env python3
"""Scenario A - Phase 10 : validation de la classification et evaluation de la politique.

Usage : python3 analyze_phase10.py ../experiments/<RUN_ID>

Reutilise les parseurs de la Phase 9 (analyze.py) : meme methodologie de mesure.
Sorties a la racine du run :
  classification_flows.csv        un flux par ligne (5-tuple, classe, observables)
  classification_validation.csv   decision vs verite terrain, par test
  policy_evaluation.csv           monitor vs enforce (debit, perte, gigue, retrans.)
  analysis_report.md
"""

import csv
import json
import re
import statistics
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze import parse_flows, parse_iperf, parse_pcap  # noqa: E402

MODES = ["monitor", "enforce"]
STEADY_FROM_S = 6          # regime etabli de l'essai de concurrence (classification faite)


def load_events(path):
    return [json.loads(l[4:]) for l in path.read_text().splitlines() if l.startswith("EVT ")]


def build_flows(events):
    flows = {}
    for e in events:
        if e["type"] == "flow_new":
            flows[e["flow"]] = dict(e, obs=[], cls=None, classify_ts=None, policy=None, history=[])
        elif e["flow"] in flows if "flow" in e else False:
            f = flows[e["flow"]]
            if e["type"] == "obs":
                f["obs"].append(e)
            elif e["type"] == "classify":
                f["history"].append(e["cls"])
                f["cls"], f["classify_ts"], f["classify_evt"] = e["cls"], e["ts"], e
            elif e["type"] == "policy":
                f["policy"] = e
    return flows


def flow_row(mode, f):
    rates = [o["rate_mbps"] for o in f["obs"]]
    total_b = f["obs"][-1]["total_bytes"] if f["obs"] else 0
    total_p = f["obs"][-1]["total_packets"] if f["obs"] else 0
    return {"mode": mode, "flow": f["flow"], "ingress_dpid": f["dpid"], "in_port": f["in_port"],
            "src": f["src"], "dst": f["dst"], "proto": f["proto"], "sport": f["sport"],
            "dport": f["dport"], "first_seen_ts": f["ts"],
            "class": f["cls"] or "UNCLASSIFIED",
            "time_to_classify_s": round(f["classify_ts"] - f["ts"], 3) if f["classify_ts"] else "",
            "n_observations": len(f["obs"]), "total_packets": total_p, "total_bytes": total_b,
            "max_rate_mbps": max(rates, default=0),
            "median_rate_mbps": round(statistics.median(rates), 3) if rates else 0,
            "mean_pkt_bytes": round(total_b / total_p, 1) if total_p else "",
            "policy_action": f["policy"]["action"] if f["policy"] else "",
            "policy_executed": f["policy"]["executed"] if f["policy"] else ""}


def interval_rates(path, key="intervals"):
    d = json.loads(path.read_text())
    return [i["sum"]["bits_per_second"] / 1e6 for i in d.get(key, [])]


def analyze(run):
    checks, md = [], []
    flow_rows, val_rows, pol_rows = [], [], []
    summary = {}

    def check(name, ok, detail):
        checks.append((name, ok, detail))

    for mode in MODES:
        d = run / mode
        params = json.loads((d / "params.json").read_text())
        events = load_events(d / "controller.log")
        flows = build_flows(events)
        flow_rows += [flow_row(mode, f) for f in flows.values()]
        start = next(e for e in events if e["type"] == "start")
        check("%s/pas_d_erreur_openflow" % mode, not any(e["type"] == "of_error" for e in events),
              "%d erreur(s)" % sum(e["type"] == "of_error" for e in events))
        check("%s/mode_controleur" % mode, start["mode"] == mode, "POLICY_MODE=%s" % start["mode"])

        # ---- validation de la classification contre la verite terrain
        for t in params["tests"]:
            window = [f for f in flows.values() if t["start"] - 0.5 <= f["ts"] <= t["end"]]
            cands = [f for f in window if (f["src"], f["dst"], f["proto"], f["dport"]) ==
                     (t["src"], t["dst"], t["proto"], t["dport"])]
            target = max(cands, key=lambda f: f["obs"][-1]["total_bytes"] if f["obs"] else 0,
                         default=None)
            got = target["cls"] if target and target["cls"] else "UNCLASSIFIED"
            ok = got == t["expected_class"]
            ev = target.get("classify_evt", {}) if target else {}
            val_rows.append({
                "mode": mode, "test": t["name"], "role": "flux de donnees genere",
                "flow": target["flow"] if target else "", "proto": t["proto"], "dport": t["dport"],
                "expected_class": t["expected_class"], "decided_class": got,
                "correct": ok, "rate_mbps_at_decision": ev.get("rate_mbps", ""),
                "mean_pkt_bytes_at_decision": ev.get("mean_pkt_bytes", ""),
                "time_to_classify_s": round(target["classify_ts"] - target["ts"], 3)
                if target and target["classify_ts"] else ""})
            check("%s/classe_%s" % (mode, t["name"]), ok,
                  "attendu %s, decide %s" % (t["expected_class"], got))
            # Flux annexes de la meme fenetre (controle iperf3, ACK, retours) : attendus LIGHT.
            others = {f["flow"]: f for f in window if f is not target}
            for f in others.values():
                if any(v["flow"] == f["flow"] and v["mode"] == mode for v in val_rows):
                    continue
                if any(f is max([c for c in flows.values()
                                 if (c["src"], c["dst"], c["proto"], c["dport"]) ==
                                 (o["src"], o["dst"], o["proto"], o["dport"])
                                 and o["start"] - 0.5 <= c["ts"] <= o["end"]],
                                key=lambda c: c["obs"][-1]["total_bytes"] if c["obs"] else 0,
                                default=None) for o in params["tests"]):
                    continue                     # c'est le flux cible d'un autre test simultane
                got_o = f["cls"] or "UNCLASSIFIED"
                val_rows.append({
                    "mode": mode, "test": t["name"], "role": "flux annexe (controle/ACK/retour)",
                    "flow": f["flow"], "proto": f["proto"], "dport": f["dport"],
                    "expected_class": f["proto"] + "_LIGHT", "decided_class": got_o,
                    "correct": got_o in (f["proto"] + "_LIGHT", "UNCLASSIFIED"),
                    "rate_mbps_at_decision": f.get("classify_evt", {}).get("rate_mbps", ""),
                    "mean_pkt_bytes_at_decision": f.get("classify_evt", {}).get("mean_pkt_bytes", ""),
                    "time_to_classify_s": round(f["classify_ts"] - f["ts"], 3) if f["classify_ts"] else ""})
        check("%s/classes_stables" % mode, all(len(f["history"]) <= 1 for f in flows.values()),
              "%d flux reclasses" % sum(len(f["history"]) > 1 for f in flows.values()))

        # ---- mesures iperf3
        res = {}
        for name in ("single_tcp", "single_udp_50M", "single_udp_1M_small", "compete_tcp", "compete_udp"):
            r = parse_iperf(d / (name + ".json"))
            res[name] = r
            pol_rows.append({"mode": mode, "test": name, **{k: (round(v, 4) if isinstance(v, float) else v)
                                                              for k, v in r.items()}})
        tcp_i = interval_rates(d / "compete_tcp.json")
        res["tcp_intervals"] = tcp_i
        res["tcp_steady"] = statistics.fmean(tcp_i[STEADY_FROM_S:]) if len(tcp_i) > STEADY_FROM_S else None
        pc = parse_pcap(d / "compete_h4_udp.pcap")
        res["pcap"] = pc
        pol_rows.append({"mode": mode, "test": "compete_tcp_steady(t>=%ds)" % STEADY_FROM_S,
                         "sender_mbps": round(res["tcp_steady"], 3) if res["tcp_steady"] else ""})
        pol_rows.append({"mode": mode, "test": "compete_udp_pcap_h4", "receiver_mbps": round(pc["rate_mbps"], 3),
                         "sent_packets": pc["packets"], "duration_s": round(pc["span_s"], 3)})

        # ---- preuve dans les tables de flux et les meters
        metered = []
        for sw in ("s1", "s2", "s3"):
            for (match, actions) in parse_flows(d / ("compete_after_flows_%s.txt" % sw)):
                if "meter:" in actions:
                    metered.append("%s : `%s` → `%s`" % (sw, match, actions))
        m = re.search(r"meter-stats s1\n.*?\nmeter:1 flow_count:(\d+) packet_in_count:(\d+) byte_in_count:(\d+)"
                      r".*?\n0: packet_count:(\d+) byte_count:(\d+)", (d / "meters_after.txt").read_text(), re.S)
        res["meter"] = dict(zip(("flow_count", "pkts_in", "bytes_in", "pkts_dropped", "bytes_dropped"),
                                map(int, m.groups()))) if m else {}
        res["metered_rules"] = metered
        res["policy_events"] = [e for e in events if e["type"] == "policy" and e["executed"]]
        res["start"] = start
        summary[mode] = res

    mon, enf = summary["monitor"], summary["enforce"]
    # ---- verifications de la politique
    check("monitor/aucune_action_executee", not mon["policy_events"] and not mon["metered_rules"]
          and mon["meter"].get("pkts_dropped", 0) == 0,
          "%d action(s), %d regle(s) avec meter, %d paquets jetes" % (
              len(mon["policy_events"]), len(mon["metered_rules"]), mon["meter"].get("pkts_dropped", 0)))
    check("enforce/meter_dans_table_de_flux", len(enf["metered_rules"]) >= 1,
          "%d regle(s) avec meter" % len(enf["metered_rules"]))
    check("enforce/meter_a_jete_des_paquets", enf["meter"].get("pkts_dropped", 0) > 0,
          "%d paquets jetes par le meter 1 sur s1" % enf["meter"].get("pkts_dropped", 0))
    limit = enf["start"]["udp_bulk_limit_kbps"] / 1000
    check("enforce/udp_limite_au_seuil", abs(enf["pcap"]["rate_mbps"] - limit) <= 0.15 * limit,
          "PCAP h4 en regime etabli : %.2f Mbit/s pour une limite de %.0f" % (enf["pcap"]["rate_mbps"], limit))
    check("enforce/tcp_ameliore", enf["tcp_steady"] > 1.5 * mon["tcp_steady"],
          "TCP en regime etabli : %.2f → %.2f Mbit/s" % (mon["tcp_steady"], enf["tcp_steady"]))

    # ---- rapport
    n_data = [v for v in val_rows if v["role"].startswith("flux de donnees")]
    n_other = [v for v in val_rows if not v["role"].startswith("flux de donnees")]
    s = mon["start"]
    md += ["# Phase 10 — classification de trafic et politique SDN (%s)" % run.name, "",
           "Regle de classification (`%s`) : BULK si debit ≥ %.0f Mbit/s **et** taille moyenne ≥ %d octets "
           "pendant %d intervalles consecutifs de %.0f s, sinon LIGHT ; classe = protocole + BULK/LIGHT."
           % (s["policy_version"], s["bulk_rate_mbps"], s["bulk_pkt_bytes"], s["bulk_streak"], s["poll_interval_s"]),
           "Politique : UDP_BULK → meter OpenFlow %d kbit/s sur le switch d'entree (mode enforce uniquement)."
           % s["udp_bulk_limit_kbps"], "",
           "## Verifications", "", "| verification | resultat | detail |", "|---|---|---|"]
    md += ["| %s | **%s** | %s |" % (n, "PASS" if ok else "FAIL", dd) for n, ok, dd in checks]

    md += ["", "## Validation de la classification (verite terrain = commande iperf3)", "",
           "| mode | test | attendu | decide | debit a la decision (Mbit/s) | taille moy. (o) | delai de decision (s) |",
           "|---|---|---|---|---|---|---|"]
    md += ["| %s | %s | %s | %s %s | %s | %s | %s |" % (
        v["mode"], v["test"], v["expected_class"], v["decided_class"], "✓" if v["correct"] else "✗",
        v["rate_mbps_at_decision"], v["mean_pkt_bytes_at_decision"], v["time_to_classify_s"]) for v in n_data]
    md += ["", "Flux de donnees generes : **%d/%d corrects**. Flux annexes (connexions de controle iperf3, ACK TCP, "
           "retours UDP) : %d observes, %d classes LIGHT, %d trop courts pour etre classes, %d classes BULK a tort."
           % (sum(v["correct"] for v in n_data), len(n_data), len(n_other),
              sum(v["decided_class"].endswith("_LIGHT") for v in n_other),
              sum(v["decided_class"] == "UNCLASSIFIED" for v in n_other),
              sum(v["decided_class"].endswith("_BULK") for v in n_other))]

    def r(mode, test, key, fmt="%.2f"):
        v = summary[mode][test].get(key)
        return fmt % v if isinstance(v, (int, float)) else "—"

    md += ["", "## Effet de la politique : TCP h2→h3 en concurrence avec UDP 80 Mbit/s h1→h4 (%d s)"
           % json.loads((run / "monitor" / "params.json").read_text())["compete_duration_s"], "",
           "| mesure | monitor (temoin) | enforce (meter) |", "|---|---|---|",
           "| TCP recu, moyenne sur l'essai (Mbit/s) | %s | %s |" % (r("monitor", "compete_tcp", "receiver_mbps"), r("enforce", "compete_tcp", "receiver_mbps")),
           "| TCP emis, regime etabli t ≥ %d s (Mbit/s) | %.2f | %.2f |" % (STEADY_FROM_S, mon["tcp_steady"], enf["tcp_steady"]),
           "| TCP retransmissions | %s | %s |" % (r("monitor", "compete_tcp", "retransmits", "%d"), r("enforce", "compete_tcp", "retransmits", "%d")),
           "| UDP recu, moyenne sur l'essai (Mbit/s) | %s | %s |" % (r("monitor", "compete_udp", "receiver_mbps"), r("enforce", "compete_udp", "receiver_mbps")),
           "| UDP recu d'apres le PCAP sur h4, regime etabli (Mbit/s) | %.2f | %.2f |" % (mon["pcap"]["rate_mbps"], enf["pcap"]["rate_mbps"]),
           "| UDP perte (%%) | %s | %s |" % (r("monitor", "compete_udp", "lost_percent", "%.2f"), r("enforce", "compete_udp", "lost_percent", "%.2f")),
           "| UDP gigue (ms) | %s | %s |" % (r("monitor", "compete_udp", "jitter_ms", "%.3f"), r("enforce", "compete_udp", "jitter_ms", "%.3f")),
           "| Paquets jetes par le meter 1 (s1) | %d | %d |" % (mon["meter"].get("pkts_dropped", 0), enf["meter"].get("pkts_dropped", 0)),
           "", "Debit TCP emis par seconde (Mbit/s) :", "",
           "- monitor : " + " ".join("%.0f" % x for x in mon["tcp_intervals"]),
           "- enforce : " + " ".join("%.0f" % x for x in enf["tcp_intervals"]),
           "", "## Flux isoles (meme commande dans les deux modes)", "",
           "| test | monitor recu (Mbit/s) | monitor perte % | enforce recu (Mbit/s) | enforce perte % |", "|---|---|---|---|---|"]
    for t in ("single_tcp", "single_udp_50M", "single_udp_1M_small"):
        md.append("| %s | %s | %s | %s | %s |" % (t, r("monitor", t, "receiver_mbps"), r("monitor", t, "lost_percent", "%.2f"),
                                                    r("enforce", t, "receiver_mbps"), r("enforce", t, "lost_percent", "%.2f")))
    md += ["", "## Changement dans les tables de flux (mode enforce, apres l'essai)", ""]
    md += ["- " + x for x in enf["metered_rules"]] or ["- aucune regle avec meter"]
    md += ["", "Actions executees par le controleur :", ""]
    md += ["- flux %d (dpid %d) : classe %s → action %s %d, limite %d kbit/s" % (
        e["flow"], e["dpid"], e["cls"], e["action"], e["meter_id"], e["limit_kbps"]) for e in enf["policy_events"]]
    md += ["", "## Limites", "",
           "- La decision arrive environ 2 a 3 s apres le debut du flux : pendant ce temps le flux UDP n'est pas limite "
           "(visible sur les premieres secondes du debit TCP en mode enforce).",
           "- Les moyennes « sur l'essai » incluent cette phase ; les valeurs « regime etabli » l'excluent.",
           "- Le meter jette l'excedent du flux classe UDP_BULK ; ses pertes sont donc voulues, pas un defaut du lien.",
           "- Classes et seuils valides uniquement sur du trafic iperf3 controle ; aucun trafic applicatif reel."]

    (run / "analysis_report.md").write_text("\n".join(md) + "\n")
    for name, rows in (("classification_flows.csv", flow_rows), ("classification_validation.csv", val_rows),
                       ("policy_evaluation.csv", pol_rows)):
        fields = list(dict.fromkeys(k for row in rows for k in row))
        with open(run / name, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
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
