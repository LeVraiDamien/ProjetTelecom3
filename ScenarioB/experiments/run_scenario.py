#!/usr/bin/env python3
"""Scenario B - lance une experience de trafic controlee et collecte les preuves.

Usage :
  ./run_scenario.py --run-id calib-dl --plan "idle:8,dl:5M:15,idle:5,dl:12M:15"
  ./run_scenario.py --run-id r1 --apps kpm,ai,rm --plan "..."

Plan = segments separes par des virgules :
  idle:<s>            aucun trafic pendant <s> secondes
  dl:<debit>:<s>      UDP descendant : le point de donnees 10.20.6.30 EMET vers l'UE
  ul:<debit>:<s>      UDP montant   : l'UE EMET vers le point de donnees

Sens du trafic : iperf3 est toujours lance cote UE (client) vers le serveur du
point de donnees. Sans option le client emet (montant) ; avec -R c'est le serveur
qui emet (descendant). Le sens radio est donc porte par -R, pas par qui est
"client" - c'est consigne dans segments.csv (colonnes sender/receiver).

Sorties dans experiments/<run-id>/ :
  kpm.csv (xApp KPM), edge_ai.csv, rm_decisions.csv (si --apps ai,rm),
  segments.csv (verite terrain : sens, debit offert, debut/fin), iperf_<n>.json,
  connectivity.txt, logs des conteneurs.
Prerequis : RAN demarre (../ran-up.sh).
"""

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCENARIO_B = HERE.parent
DN = "10.20.6.30"
UE = ["docker", "exec", "project3-srsue", "ip", "netns", "exec", "ue1"]
SERVICES = {"kpm": "p3-kpm-csv", "ai": "p3-edge-ai", "rm": "p3-resource-mgmt"}
CONTAINERS = {"kpm": "project3-kpm-csv", "ai": "project3-edge-ai", "rm": "project3-resource-mgmt"}


def sh(cmd, env=None):
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    return r.stdout + r.stderr


def compose(args, env):
    return sh([str(SCENARIO_B / "p3-compose.sh"), "--profile", "xapp"] + args, env=env)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--plan", required=True)
    ap.add_argument("--apps", default="kpm", help="kpm[,ai,rm]")
    ap.add_argument("--warmup", type=int, default=6, help="s entre le demarrage des xApps et le 1er segment")
    args = ap.parse_args()

    out = HERE / args.run_id
    out.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, P3_RUN_ID=args.run_id, P3_RUN_DIR=str(out))
    apps = args.apps.split(",")

    # Etat de connectivite de l'UE avant l'experience (exige par la Phase 10).
    conn = sh(UE + ["ip", "-br", "a", "show", "tun_srsue"]) + sh(UE + ["ping", "-c", "3", "-W", "2", DN])
    (out / "connectivity.txt").write_text(conn)
    ue_ok = " 0% packet loss" in conn
    if not ue_ok:
        sys.exit("UE non connecte (voir %s) : lancer ../ran-up.sh" % (out / "connectivity.txt"))

    for a in apps:   # ordre : kpm puis ai puis rm
        print(compose(["up", "-d", "--no-deps", "--force-recreate", SERVICES[a]], env).strip().splitlines()[-1])
        time.sleep(2)
    time.sleep(args.warmup)

    rows = []
    try:
        for n, seg in enumerate(args.plan.split(","), 1):
            parts = seg.strip().split(":")
            kind = parts[0]
            t0 = time.time()
            if kind == "idle":
                dur = int(parts[1])
                print("[%d] idle %ds" % (n, dur), flush=True)
                time.sleep(dur)
                row = dict(direction="none", offered="0", sender="-", receiver="-", iperf_file="")
            else:
                rate, dur = parts[1], int(parts[2])
                cmd = ["iperf3", "-c", DN, "-u", "-b", rate, "-t", str(dur), "-J"] + (["-R"] if kind == "dl" else [])
                print("[%d] %s %s %ds" % (n, kind, rate, dur), flush=True)
                res = sh(UE + cmd)
                f = "iperf_%02d_%s_%s.json" % (n, kind, rate)
                (out / f).write_text(res)
                row = dict(direction=kind, offered=rate, iperf_file=f,
                           sender="dn-endpoint %s" % DN if kind == "dl" else "UE (ue1)",
                           receiver="UE (ue1)" if kind == "dl" else "dn-endpoint %s" % DN)
                try:
                    end = json.loads(res)["end"]
                    rcv = end.get("sum_received") or end["sum"]
                    row.update(iperf_receiver_mbps=round(rcv["bits_per_second"] / 1e6, 3),
                               iperf_lost_percent=round(rcv.get("lost_percent", 0), 3),
                               iperf_jitter_ms=round(rcv.get("jitter_ms", 0), 3))
                except Exception as e:                      # iperf en erreur : on le consigne
                    row.update(iperf_error=str(e)[:80])
            rows.append(dict(run_id=args.run_id, segment=n, kind=kind, duration_s=dur,
                             start_epoch=round(t0, 3), end_epoch=round(time.time(), 3),
                             ue_connected=ue_ok, **row))
        time.sleep(4)   # laisse arriver les dernieres indications
    finally:
        for a in reversed(apps):
            compose(["stop", SERVICES[a]], env)
            (out / ("%s_container.log" % a)).write_text(sh(["docker", "logs", CONTAINERS[a]]))
        fields = list(dict.fromkeys(k for r in rows for k in r))
        with open(out / "segments.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
        (out / "run_params.json").write_text(json.dumps(
            {"run_id": args.run_id, "plan": args.plan, "apps": apps, "data_endpoint": DN,
             "traffic": "iperf3 UDP, client cote UE ; -R pour le descendant"}, indent=2))
    print("Resultats :", out)


if __name__ == "__main__":
    main()
