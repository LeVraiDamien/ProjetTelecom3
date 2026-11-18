#!/usr/bin/env python3
"""Scenario A - topologie de reference (Phase 3 et 5).

    h1 (10.0.0.1) --1\\                              /1-- h3 (10.0.0.3)
                     s1 --3 ---- 1-- s2 --2 ---- 3-- s3
    h2 (10.0.0.2) --2/                              \\2-- h4 (10.0.0.4)

- 3 switches OVS, DPID fixes 1, 2, 3, OpenFlow 1.3, fail-mode secure
- controleur externe OS-Ken sur 127.0.0.1:6633 (conteneur scenario-a-osken)
- 6 liens TCLink : 100 Mbit/s en TBF (pas HTB), 1 ms, 0 % de perte, file 1000 paquets

Les numeros de port sont fixes explicitement pour que le chemin
h1 -> s1(1->3) -> s2(1->2) -> s3(3->2) -> h4 corresponde au sujet.

Usage :  sudo python3 scenario_a_topo.py            (ouvre le CLI Mininet)
         sudo python3 scenario_a_topo.py --check    (verifie puis quitte)
"""

import argparse
import sys

from mininet.cli import CLI
from mininet.link import TCLink
from mininet.log import info, setLogLevel
from mininet.net import Mininet
from mininet.node import OVSSwitch, RemoteController
from mininet.topo import Topo

LINK = dict(bw=100, delay="1ms", loss=0, max_queue_size=1000, use_tbf=True)


class ScenarioATopo(Topo):
    def build(self):
        sw = dict(protocols="OpenFlow13", failMode="secure")
        s1 = self.addSwitch("s1", dpid="0000000000000001", **sw)
        s2 = self.addSwitch("s2", dpid="0000000000000002", **sw)
        s3 = self.addSwitch("s3", dpid="0000000000000003", **sw)

        h1 = self.addHost("h1", ip="10.0.0.1/24", mac="00:00:00:00:00:01")
        h2 = self.addHost("h2", ip="10.0.0.2/24", mac="00:00:00:00:00:02")
        h3 = self.addHost("h3", ip="10.0.0.3/24", mac="00:00:00:00:00:03")
        h4 = self.addHost("h4", ip="10.0.0.4/24", mac="00:00:00:00:00:04")

        # hotes <-> switches
        self.addLink(h1, s1, port1=0, port2=1, **LINK)
        self.addLink(h2, s1, port1=0, port2=2, **LINK)
        self.addLink(h3, s3, port1=0, port2=1, **LINK)
        self.addLink(h4, s3, port1=0, port2=2, **LINK)
        # liens inter-switches
        self.addLink(s1, s2, port1=3, port2=1, **LINK)
        self.addLink(s2, s3, port1=2, port2=3, **LINK)


def build_net():
    return Mininet(
        topo=ScenarioATopo(),
        switch=OVSSwitch,
        link=TCLink,
        controller=None,
        autoSetMacs=False,
        build=False,
    )


def check(net):
    """Verifications des Phases 3 et 5 : liens, qdiscs, session OpenFlow."""
    ok = True
    info("*** %d liens crees (attendu : 6)\n" % len(net.links))
    ok &= len(net.links) == 6
    for sw in net.switches:
        for intf in sw.intfList():
            if intf.name == "lo":
                continue
            out = sw.cmd("tc qdisc show dev %s" % intf.name)
            good = "tbf" in out and "netem" in out
            ok &= good
            info("%s %s\n%s" % ("OK  " if good else "FAIL", intf.name, out))
        info(sw.cmd("ovs-vsctl get bridge %s protocols fail_mode" % sw.name))
        info(sw.cmd("ovs-vsctl get controller %s is_connected" % sw.name))
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--controller-ip", default="127.0.0.1")
    ap.add_argument("--controller-port", type=int, default=6633)
    ap.add_argument("--check", action="store_true", help="verifie puis quitte")
    args = ap.parse_args()

    setLogLevel("info")
    net = build_net()
    net.addController(
        "c0",
        controller=RemoteController,
        ip=args.controller_ip,
        port=args.controller_port,
    )
    net.build()
    net.start()
    try:
        net.waitConnected(timeout=15)
        ok = check(net)
        if args.check:
            net.pingAll()
            sys.exit(0 if ok else 1)
        CLI(net)
    finally:
        net.stop()


if __name__ == "__main__":
    main()
