#!/usr/bin/env python3
"""Scenario A - execution des phases 1 a 8 et collecte des preuves brutes.

Lance par run.sh (qui fournit --run-id et enregistre la console).
Tout est ecrit dans ScenarioA/experiments/<RUN_ID>/ ; l'analyse (Phase 9)
est faite ensuite, sans root, par analyze.py a partir de ces fichiers.

Ce script ne calcule rien : il deploie, genere le trafic et sauvegarde.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True  # pas de __pycache__ appartenant a root dans le repo
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "topology"))

from mininet.log import info, setLogLevel  # noqa: E402
from mininet.net import Mininet  # noqa: E402
from mininet.node import OVSSwitch, RemoteController  # noqa: E402
from mininet.topo import SingleSwitchTopo  # noqa: E402

from scenario_a_topo import LINK, build_net  # noqa: E402

CONTROLLER = "scenario-a-osken"
IMAGE = "telecom-lab-osken:1.0"
SWITCHES = ["s1", "s2", "s3"]
IPERF_PORT = 5201
SETTLE_S = 4  # repos avant chaque snapshot de la Phase 8 (voir phase8)
OF = ["ovs-ofctl", "-O", "OpenFlow13", "--no-names"]


def sh(cmd):
    """Commande dans le namespace de l'hote (la ou vivent les switches OVS)."""
    r = subprocess.run(cmd, shell=isinstance(cmd, str), capture_output=True, text=True)
    return r.stdout + r.stderr


def save(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def banner(msg):
    info("\n=== %s ===\n" % msg)


# ------------------------------------------------------------------ phase 1
def phase1(out):
    banner("Phase 1 : environnement")
    cmds = [
        "lsb_release -ds", "uname -r", "mn --version", "ovs-vsctl --version",
        "docker --version", "python3 --version", "iperf3 --version",
        "tcpdump --version", "systemctl is-active openvswitch-switch",
        "nproc", "free -h", "docker image inspect telecom-lab-osken:1.0 --format '{{.Id}}'",
        "docker exec %s pip show os-ken" % CONTROLLER,
        "docker exec %s python --version" % CONTROLLER,
    ]
    save(out / "phase1_environment.txt",
         "".join("$ %s\n%s\n" % (c, sh(c)) for c in cmds))


# ------------------------------------------------------------------ phase 2
def clean_state():
    return {
        "ovs_bridges": sh("ovs-vsctl list-br").split(),
        "mininet_links": re.findall(r"\b[sh]\d+-eth\d+", sh("ip -o link")),
        "mininet_processes": sh("pgrep -af '[m]ininet:'")  # [m] : pgrep ne se trouve pas lui-meme.strip().splitlines(),
    }


def phase2(out):
    banner("Phase 2 : baseline Mininet + OVS sans controleur")
    # failMode standalone : sans controleur, OVS se comporte en switch classique.
    net = Mininet(topo=SingleSwitchTopo(2), switch=OVSSwitch, controller=None)
    net.start()
    net["s1"].cmd("ovs-vsctl set-fail-mode s1 standalone")
    time.sleep(1)
    txt = "$ ovs-vsctl show\n" + sh("ovs-vsctl show")
    loss = net.pingAll()
    txt += "\npingall loss = %s %%\n" % loss
    net.stop()
    state = clean_state()
    txt += "\nEtat apres nettoyage (tout doit etre vide) :\n" + json.dumps(state, indent=2) + "\n"
    save(out / "phase2_baseline.txt", txt)
    if loss != 0 or any(state.values()):
        raise SystemExit("Phase 2 en echec, voir phase2_baseline.txt")


# ------------------------------------------------------------- snapshots
def snapshot(out, tag):
    """Tables de flux + compteurs de ports des 3 switches, horodates (Phase 8/9).

    L'horodatage est pris juste avant chaque commande pour pouvoir normaliser
    les deltas d'octets sur l'intervalle reel entre deux snapshots.
    """
    meta = {}
    for sw in SWITCHES:
        t = time.time()
        save(out / ("%s_flows_%s.txt" % (tag, sw)), sh(OF + ["dump-flows", sw]))
        save(out / ("%s_ports_%s.txt" % (tag, sw)), sh(OF + ["dump-ports", sw]))
        meta[sw] = t
    save(out / ("%s_timestamps.json" % tag), json.dumps(meta, indent=2))


# --------------------------------------------------------------- phase 3-6
def phase3_to_6(net, out):
    banner("Phase 3 : topologie et qdiscs")
    txt = "liens crees : %d (attendu 6)\n" % len(net.links)
    txt += "parametres TCLink : %s\n\n" % LINK
    for node in net.switches + net.hosts:
        for intf in node.intfList():
            if intf.name != "lo":
                txt += "$ tc qdisc show dev %s\n%s" % (intf.name, node.cmd("tc qdisc show dev %s" % intf.name))
    save(out / "phase3_topology.txt", txt + "\n$ ovs-vsctl show\n" + sh("ovs-vsctl show"))

    banner("Phase 5 : OpenFlow 1.3, fail-mode secure, sessions")
    txt = ""
    for sw in SWITCHES:
        for c in ["ovs-vsctl get bridge %s protocols fail_mode other-config:datapath-id" % sw,
                  "ovs-vsctl get-controller %s" % sw,
                  "ovs-vsctl --columns=target,is_connected,role,status list controller %s" % sw,
                  "ovs-ofctl -O OpenFlow13 show %s" % sw]:
            txt += "$ %s\n%s\n" % (c, sh(c))
    save(out / "phase5_openflow.txt", txt)

    banner("Phase 6 : learning switch")
    snapshot(out, "phase6_before_ping")          # table-miss seule
    loss = net.pingAll()
    snapshot(out, "phase6_after_ping")           # + regles apprises
    save(out / "phase6_pingall.txt", "pingall loss = %s %%\n" % loss)
    save(out / "phase6_controller.log", sh("docker logs %s" % CONTROLLER))
    if loss != 0:
        raise SystemExit("Phase 6 en echec : pingall = %s %% de perte" % loss)
    verify_path(net, out)


# Chemin de reference h1 -> h4 : port de sortie attendu sur chaque switch.
EXPECTED_PATH = {"s1": 3, "s2": 2, "s3": 2}


def verify_path(net, out):
    """Prouve le chemin h1->h4 par les tables de flux, avant toute mesure.

    Sans regle apprise vers h4, le trafic passerait par le controleur (table-miss)
    et les mesures de debit ne voudraient rien dire.
    """
    h1, h4 = net["h1"], net["h4"]
    h1.cmd("ping -c 3 %s" % h4.IP())
    txt, ok = "", True
    for sw, port in EXPECTED_PATH.items():
        flows = [l.strip() for l in sh(OF + ["dump-flows", sw]).splitlines()
                 if "dl_src=%s" % h1.MAC() in l and "dl_dst=%s" % h4.MAC() in l]
        good = len(flows) == 1 and flows[0].endswith("actions=output:%d" % port)
        ok &= good
        txt += "%s %s attendu output:%d\n    %s\n" % (
            "OK  " if good else "FAIL", sw, port, "\n    ".join(flows) or "(aucune regle h1->h4)")
    save(out / "phase6_path_h1_h4.txt", txt)
    info(txt)
    if not ok:
        raise SystemExit("Chemin h1->h4 non conforme, voir phase6_path_h1_h4.txt")


# ----------------------------------------------------------------- phase 7
def iperf(h_client, server_ip, out_file, extra, duration):
    cmd = "iperf3 -c %s -p %d -t %d -J --get-server-output %s" % (
        server_ip, IPERF_PORT, duration, extra)
    info("%s $ %s\n" % (h_client.name, cmd))
    save(out_file, h_client.cmd(cmd))
    return cmd


def phase7(net, out, duration):
    banner("Phase 7 : iperf3 TCP et UDP h1 -> h4")
    h1, h4 = net["h1"], net["h4"]
    params = {"client": "h1 10.0.0.1", "server": "h4 10.0.0.4", "port": IPERF_PORT,
              "duration_s": duration, "link": LINK, "tests": {}}
    tests = [("tcp", ""), ("udp_50M", "-u -b 50M"), ("udp_80M", "-u -b 80M"),
             ("udp_100M", "-u -b 100M")]
    for name, extra in tests:
        params["tests"][name] = iperf(h1, h4.IP(), out / ("phase7_iperf3_%s.json" % name), extra, duration)
        time.sleep(2)
    save(out / "phase7_params.json", json.dumps(params, indent=2, default=str))


# ----------------------------------------------------------------- phase 8
def phase8(net, out, duration, rate, pcap_limit):
    banner("Phase 8 : PCAP borne + snapshots OpenFlow avant/apres")
    h1, h4 = net["h1"], net["h4"]
    h1.cmd("ping -c 3 %s" % h4.IP())             # etat d'apprentissage stable
    bpf = "udp and src host %s and dst host %s and dst port %d" % (h1.IP(), h4.IP(), IPERF_PORT)
    pcap = out / "phase8_h1_udp.pcap"
    params = {"flow": "h1 10.0.0.1 -> h4 10.0.0.4 UDP dport %d" % IPERF_PORT,
              "dst_mac_h4": h4.MAC(), "src_mac_h1": h1.MAC(), "offered_rate": rate,
              "duration_s": duration, "capture_interface": "h1-eth0",
              "capture_filter": bpf, "capture_packet_limit": pcap_limit,
              "capture_snaplen": 128, "snapshot_settle_s": SETTLE_S}

    # OVS ne remonte les compteurs de flux du noyau vers OpenFlow que par
    # lots (~1 s). Un snapshot pris juste apres le trafic sous-compte donc les
    # regles (constate au run-20261116T125209Z : 41 843 paquets sur la regle
    # contre 43 175 sur le port). On attend que le reseau soit au repos.
    time.sleep(SETTLE_S)
    snapshot(out, "phase8_before")
    # -s 128 : on ne garde que les en-tetes (la taille reelle reste dans le PCAP),
    # ce qui borne le fichier a quelques Mo au lieu de ~37 Mo.
    cap = h1.popen(["tcpdump", "-i", "h1-eth0", "-s", "128", "-c", str(pcap_limit),
                    "-w", str(pcap), bpf],
                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    time.sleep(1.5)                              # laisse tcpdump s'attacher
    params["iperf3_start_epoch"] = time.time()
    params["iperf3_cmd"] = iperf(h1, h4.IP(), out / "phase8_iperf3_udp.json",
                                 "-u -b %s" % rate, duration)
    params["iperf3_end_epoch"] = time.time()
    try:
        cap_out, _ = cap.communicate(timeout=5)
    except subprocess.TimeoutExpired:            # moins de pcap_limit paquets vus
        cap.terminate()
        cap_out, _ = cap.communicate()
    time.sleep(SETTLE_S)
    snapshot(out, "phase8_after")
    save(out / "phase8_tcpdump.log", cap_out or "")
    save(out / "phase8_params.json", json.dumps(params, indent=2))


# -------------------------------------------------------------------- main
def wait_port(port, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        if (":%d " % port) in sh("ss -ltn"):
            return True
        time.sleep(0.5)
    return False


def start_controller(app=None, mode="monitor"):
    """(Re)cree le conteneur du controleur avec l'application voulue.

    app=None : learning switch des phases 1-9 (commande par defaut de l'image) ;
    app="classifier_switch.py" : Phase 10, avec POLICY_MODE=monitor|enforce.
    """
    sh("docker rm -f %s" % CONTROLLER)
    cmd = "" if app is None else "osken-manager --ofp-tcp-listen-port 6633 /app/%s" % app
    res = sh("docker run -d --name %s --network host -e POLICY_MODE=%s %s %s"
             % (CONTROLLER, mode, IMAGE, cmd))
    if not wait_port(6633):
        raise SystemExit("Le controleur n'ecoute pas sur 6633 :\n" + res
                         + sh("docker logs %s" % CONTROLLER))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--duration", type=int, default=10)
    ap.add_argument("--rate", default="50M", help="debit UDP de la Phase 8")
    ap.add_argument("--pcap-limit", type=int, default=25000)
    args = ap.parse_args()
    if os.geteuid() != 0:
        raise SystemExit("Mininet exige root : lancer via run.sh")

    out = HERE.parent / "experiments" / args.run_id
    out.mkdir(parents=True, exist_ok=True)
    setLogLevel("info")

    try:
        # Controleur redemarre : journaux et table MAC propres pour ce run (Phase 4).
        start_controller()
        save(out / "phase4_controller.txt",
             sh("docker ps --filter name=%s --format '{{.Names}} {{.Image}} {{.Status}}'" % CONTROLLER)
             + sh("ss -ltnp | grep ':6633 '") + "\n" + sh("docker logs %s" % CONTROLLER))

        phase1(out)
        phase2(out)

        net = build_net()
        net.addController("c0", controller=RemoteController, ip="127.0.0.1", port=6633)
        net.build()
        net.start()
        server = None
        try:
            if not net.waitConnected(timeout=15):
                raise SystemExit("Les switches ne se connectent pas au controleur")
            phase3_to_6(net, out)
            server = net["h4"].popen(["iperf3", "-s", "-p", str(IPERF_PORT)],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(1)
            phase7(net, out, args.duration)
            phase8(net, out, args.duration, args.rate, args.pcap_limit)
            save(out / "final_controller.log", sh("docker logs %s" % CONTROLLER))
        finally:
            if server:
                server.terminate()
            net.stop()
            # RemoteController.stop() ne fait rien dans Mininet : sans ceci le
            # shell "mininet:c0" survit jusqu'a la fin du script.
            for c in net.controllers:
                c.terminate()
        time.sleep(1)
        save(out / "final_cleanup.json", json.dumps(clean_state(), indent=2))
    finally:
        # Rend les fichiers a l'utilisateur (le script tourne en root).
        uid, gid = os.environ.get("SUDO_UID"), os.environ.get("SUDO_GID")
        if uid and gid:
            sh("chown -R %s:%s %s" % (uid, gid, out))
    info("\n*** Preuves dans %s\n" % out)


if __name__ == "__main__":
    main()
