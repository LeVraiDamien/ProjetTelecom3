# Project 3 — Software-Defined Telecommunication Networks

Damien Guffon — Esisar (exchange at RTU Riga)

Two programmable-network scenarios built on the same reproducible, Docker-based approach:

- **Scenario A (basic)** — an SDN network with Mininet, Open vSwitch and an external OS-Ken controller.
- **Scenario B (advanced)** — an O-RAN set-up (OCUDU gNB, srsUE, FlexRIC) on the Project 2 Open5GS core, with three
  xApps: KPM monitoring, Edge-AI and dry-run Resource Management.

Full details, evidence and known limitations: **[REPORT.md](REPORT.md)**.

## How the system is deployed → controlled → measured → observed → analyzed → inferred → managed

| Stage | Scenario A | Scenario B |
|---|---|---|
| **Deployed** | 3 OVS switches, 4 hosts, 100 Mbit/s TBF + 1 ms links — [`scenario_a_topo.py`](ScenarioA/topology/scenario_a_topo.py) | gNB, UE and RIC compiled from source; N2/N3/N4/RAN networks — [`images/`](ScenarioB/images/), [`p3-core.yaml`](ScenarioB/compose/p3-core.yaml) |
| **Controlled** | OS-Ken 3.1.1 over OpenFlow 1.3, learning switch — [`learning_switch.py`](ScenarioA/controller/learning_switch.py) | E2 Setup with KPM (function 2) and RC (function 3); KPM subscription over E42 |
| **Measured** | iperf3 TCP/UDP, flow and port counters — [`run_experiments.py`](ScenarioA/measure/run_experiments.py) | 5 KPM measurements per second to CSV — [`xapp_kpm_csv.c`](ScenarioB/xapps/kpm/xapp_kpm_csv.c) |
| **Observed** | bounded PCAP on h1, snapshots before/after | iperf3 results and KPM records aligned by timestamp — [`run_scenario.py`](ScenarioB/experiments/run_scenario.py) |
| **Analyzed** | counter deltas, path and port consistency, 8 checks — [`analyze.py`](ScenarioA/measure/analyze.py) | per-segment medians, repeatability, responsiveness — [`analyze_runs.py`](ScenarioB/experiments/analyze_runs.py) |
| **Inferred** | per-flow traffic class from OpenFlow counters — [`classifier_switch.py`](ScenarioA/controller/classifier_switch.py) | load state and congestion from PRB + RLC delay, optional decision tree — [`edge_ai.py`](ScenarioB/xapps/edge_ai/edge_ai.py) |
| **Managed** | OpenFlow meter on bulk UDP, **executed and measured** | recommendations in **DRY_RUN**, no control request sent — [`resource_mgmt.py`](ScenarioB/xapps/resource_mgmt/resource_mgmt.py) |

## Main results

| | Result | Evidence |
|---|---|---|
| A | UDP 50 / 80 / 100 Mbit/s → 49.95 / 79.71 / 96.82 Mbit/s received, 0 / 0.23 / 1.93 % loss | [`run-20261116T125729Z`](ScenarioA/experiments/run-20261116T125729Z/analysis_report.md) |
| A | h1→h4 flow rule: 43,175 packets and 64,309,891 bytes, identical on s1, s2, s3 and on the inter-switch ports | same run |
| A | 10/10 generated flows classified correctly; policy raises competing TCP from 16.1 to 79.0 Mbit/s | [`p10-20261116T130701Z`](ScenarioA/experiments/p10-20261116T130701Z/analysis_report.md) |
| B | UE registered, 10.45.0.2, traffic in both directions; E2 Setup with KPM and RC | [`experiments/setup/`](ScenarioB/experiments/setup/) |
| B | 5 / 12 / 18 Mbit/s downlink → 15 / 38 / 57–61 % PRB, ≈ 1.5 ms delay, no loss; congestion only above 25 Mbit/s | [`c1-report.md`](ScenarioB/experiments/c1-report.md) |
| B | decision tree: 99.1 % on three runs not used for training | same report |

**Not implemented:** the two optional extensions (multi-path traffic engineering in A, E2SM-RC control in B).
**Deviations:** no course image was provided, so the Scenario B components were built from source; software versions
and a few addresses differ from the reference (REPORT §A.1, §B.1, §B.2).

## Layout

```
ScenarioA/
  controller/     Dockerfile, learning_switch.py (Phases 4-6), classifier_switch.py (Phase 10), run_controller.sh
  topology/       scenario_a_topo.py
  measure/        run.sh, run_experiments.py, analyze.py        Phases 1-9
                  run_phase10.sh, run_phase10.py, analyze_phase10.py
  experiments/    one directory per run: raw evidence, PCAP, analysis_summary.csv, analysis_report.md
ScenarioB/
  images/         Dockerfiles: flexric, ocudu-gnb, srsue, flexric-xapps; build_all.sh
  compose/        p3-core.yaml (networks, core overrides, RAN, xApps)
  config/         gnb_zmq.yaml, ue_zmq.conf, ric.conf, xApp configs, core/ (AMF, NRF, SMF, UPF variants)
  xapps/          kpm/ (C, FlexRIC SDK), edge_ai/ (+ model/), resource_mgmt/, common.py, Dockerfile
  experiments/    run_scenario.py, run_campaign.sh, analyze_runs.py, setup/, calib-dl-01/, c1-*/
  p3-compose.sh   docker compose wrapper: Project 1-2 core + Project 3 additions
  ran-up.sh       start RIC -> gNB -> UE in the right order
REPORT.md         technical report
```

## Reproducing

Requirements: Linux with Docker, Mininet 2.3.0, Open vSwitch, iperf3, tcpdump, Python 3. Mininet needs root.

**Scenario A**

```bash
ScenarioA/controller/run_controller.sh     # build and start the OS-Ken controller (port 6633)
ScenarioA/measure/run.sh                   # Phases 1-9, about 2 minutes, ends with PASS/FAIL
ScenarioA/measure/run_phase10.sh           # Phase 10 (monitor then enforce), about 3 minutes
```

Each script creates `ScenarioA/experiments/<RUN_ID>/` and writes `analysis_report.md` there.

**Scenario B** needs the Project 1–2 core (Open5GS from Gradiant/openverso-images, in
`~/openverso-images/docs/open5gs-and-ueransim`) and the Project 2 repository in `~/ProjetTelecom2`.

```bash
ScenarioB/images/build_all.sh                        # compile FlexRIC, srsUE, OCUDU (about 25 minutes)
ScenarioB/p3-compose.sh build p3-kpm-csv p3-edge-ai  # xApp images
ScenarioB/p3-compose.sh up -d nrf amf smf upf        # core in Project 3 configuration, then restart the other NFs
# add the srsUE subscriber: IMSI 001010123456780 (key and OPc in ScenarioB/config/ue_zmq.conf), with open5gs-dbctl
ScenarioB/ran-up.sh                                  # RIC -> gNB -> UE, PDU session, default route
ScenarioB/experiments/run_campaign.sh c1             # nine runs, about 15 minutes
ScenarioB/experiments/analyze_runs.py c1             # c1-summary.csv and c1-report.md
```

To return the core to its Project 2 state: `~/ProjetTelecom2/p2-compose.sh up -d nrf amf smf upf`.

## Known limitations (short list)

- Scenario A: the policy acts 2–3 s after a flow starts; classes are validated on iperf3 traffic only.
- Scenario B: one UE and one cell; Resource Management is dry-run, so no performance gain is claimed; the Edge-AI and
  Resource-Management applications exchange CSV files and do not connect to the RIC; about one KPM indication in thirty
  is missing; the ZeroMQ radio runs slower than real time.

The full list is in REPORT §A.8 and §B.10.
