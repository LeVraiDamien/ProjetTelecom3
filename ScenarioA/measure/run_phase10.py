#!/usr/bin/env python3
"""Scenario A - Phase 10 : experiences de classification et de politique SDN.

Le meme protocole est joue deux fois, avec le controleur classifier_switch.py :
  monitor : le controleur classe les flux mais ne change rien (temoin) ;
  enforce : les flux classes UDP_BULK sont limites par un meter OpenFlow.

Par mode :
  1. trois flux isoles a verite terrain connue (validation de la classification) :
       TCP iperf3            h1 -> h4   attendu TCP_BULK
       UDP 50 Mbit/s         h1 -> h4   attendu UDP_BULK
       UDP 1 Mbit/s, 200 o   h1 -> h4   attendu UDP_LIGHT
  2. concurrence sur les liens s1-s2-s3 (evaluation de la politique) :
       TCP h2 -> h3 (port 5202) en meme temps que UDP 80 Mbit/s h1 -> h4 (port 5201)

Sorties dans experiments/<RUN_ID>/<mode>/ ; analyse par analyze_phase10.py.
Lancement : sudo /usr/bin/python3 <ce fichier> --run-id <ID>   (voir run_phase10.sh)
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "topology"))

from mininet.log import info, setLogLevel  # noqa: E402
from mininet.node import RemoteController  # noqa: E402

from run_experiments import (  # noqa: E402
    CONTROLLER, OF, SETTLE_S, banner, clean_state, save, sh, snapshot, start_controller,
)
from scenario_a_topo import LINK, build_net  # noqa: E402

SINGLE_S, COMPETE_S, PCAP_DELAY_S, PCAP_LIMIT = 8, 20, 8, 25000


def iperf_cmd(server_ip, port, duration, extra=""):
    return "iperf3 -c %s -p %d -t %d -J --get-server-output %s" % (server_ip, port, duration, extra)


def run_mode(mode, out):
    banner("Phase 10 - mode %s" % mode)
    out.mkdir(parents=True, exist_ok=True)
    start_controller("classifier_switch.py", mode)
    net = build_net()
    net.addController("c0", controller=RemoteController, ip="127.0.0.1", port=6633)
    net.build()
    net.start()
    servers, tests = [], []
    try:
        if not net.waitConnected(timeout=15):
            raise SystemExit("Les switches ne se connectent pas au controleur")
        loss = net.pingAll()
        if loss != 0:
            raise SystemExit("pingall = %s %% de perte" % loss)
        h1, h2, h3, h4 = (net[h] for h in ("h1", "h2", "h3", "h4"))
        save(out / "meters_initial.txt", "".join(
            "$ dump-meters %s\n%s" % (sw, sh(OF + ["dump-meters", sw])) for sw in ("s1", "s2", "s3")))
        for host, port in ((h4, 5201), (h3, 5202)):
            servers.append(host.popen(["iperf3", "-s", "-J", "-p", str(port)],
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        time.sleep(1)

        # ---- 1. flux isoles a verite terrain connue
        for name, extra, proto, expected in (
                ("single_tcp", "", "TCP", "TCP_BULK"),
                ("single_udp_50M", "-u -b 50M", "UDP", "UDP_BULK"),
                ("single_udp_1M_small", "-u -b 1M -l 200", "UDP", "UDP_LIGHT")):
            cmd = iperf_cmd(h4.IP(), 5201, SINGLE_S, extra)
            info("h1 $ %s\n" % cmd)
            t0 = time.time()
            save(out / (name + ".json"), h1.cmd(cmd))
            tests.append({"name": name, "cmd": cmd, "start": t0, "end": time.time(),
                          "src": h1.IP(), "dst": h4.IP(), "proto": proto, "dport": 5201,
                          "expected_class": expected})
            time.sleep(3)

        # ---- 2. concurrence TCP (h2->h3) / UDP 80M (h1->h4)
        time.sleep(SETTLE_S)
        snapshot(out, "compete_before")
        pcap = out / "compete_h4_udp.pcap"
        bpf = "udp and dst host %s and dst port 5201" % h4.IP()
        # Capture cote recepteur, en regime etabli (apres PCAP_DELAY_S), bornee.
        cap = h4.popen(["sh", "-c", "sleep %d; exec tcpdump -i h4-eth0 -s 128 -c %d -w %s '%s'"
                        % (PCAP_DELAY_S, PCAP_LIMIT, pcap, bpf)],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        tcp_cmd = iperf_cmd(h3.IP(), 5202, COMPETE_S)
        udp_cmd = iperf_cmd(h4.IP(), 5201, COMPETE_S, "-u -b 80M")
        info("h2 $ %s\nh1 $ %s\n" % (tcp_cmd, udp_cmd))
        t0 = time.time()
        tcp = h2.popen(tcp_cmd.split(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        save(out / "compete_udp.json", h1.cmd(udp_cmd))
        tcp_out, _ = tcp.communicate(timeout=30)
        t1 = time.time()
        save(out / "compete_tcp.json", tcp_out)
        try:
            cap_out, _ = cap.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            cap.terminate()
            cap_out, _ = cap.communicate()
        save(out / "compete_tcpdump.log", cap_out or "")
        tests.append({"name": "compete_tcp", "cmd": tcp_cmd, "start": t0, "end": t1,
                      "src": h2.IP(), "dst": h3.IP(), "proto": "TCP", "dport": 5202,
                      "expected_class": "TCP_BULK"})
        tests.append({"name": "compete_udp_80M", "cmd": udp_cmd, "start": t0, "end": t1,
                      "src": h1.IP(), "dst": h4.IP(), "proto": "UDP", "dport": 5201,
                      "expected_class": "UDP_BULK"})
        time.sleep(SETTLE_S)
        snapshot(out, "compete_after")
        save(out / "meters_after.txt", "".join(
            "$ %s %s\n%s" % (c, sw, sh(OF + [c, sw]))
            for sw in ("s1", "s2", "s3") for c in ("dump-meters", "meter-stats")))
        save(out / "controller.log", sh("docker logs %s" % CONTROLLER))
        save(out / "params.json", json.dumps({
            "mode": mode, "link": LINK, "single_duration_s": SINGLE_S,
            "compete_duration_s": COMPETE_S, "pcap_delay_s": PCAP_DELAY_S,
            "pcap_filter": bpf, "pcap_limit": PCAP_LIMIT, "snapshot_settle_s": SETTLE_S,
            "tests": tests}, indent=2, default=str))
    finally:
        for s in servers:
            s.terminate()
        net.stop()
        for c in net.controllers:
            c.terminate()
    time.sleep(1)
    save(out / "final_cleanup.json", json.dumps(clean_state(), indent=2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--modes", default="monitor,enforce")
    args = ap.parse_args()
    if os.geteuid() != 0:
        raise SystemExit("Mininet exige root : lancer via run_phase10.sh")
    out = HERE.parent / "experiments" / args.run_id
    out.mkdir(parents=True, exist_ok=True)
    setLogLevel("info")
    try:
        for mode in args.modes.split(","):
            run_mode(mode, out / mode)
    finally:
        start_controller()        # remet le learning switch des phases 1-9
        uid, gid = os.environ.get("SUDO_UID"), os.environ.get("SUDO_GID")
        if uid and gid:
            sh("chown -R %s:%s %s" % (uid, gid, out))
    info("\n*** Preuves dans %s\n" % out)


if __name__ == "__main__":
    main()
