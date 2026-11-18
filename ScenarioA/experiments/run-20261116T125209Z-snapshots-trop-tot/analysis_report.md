# Analyse run-20261116T125209Z-snapshots-trop-tot

Flux etudie : h1 10.0.0.1 -> h4 10.0.0.4 UDP dport 5201, debit offert 50M, duree 10 s.

iperf3 (Phase 8) : emis 49.99 Mbit/s, recu 49.95 Mbit/s, perte 0.000 % (0/43160), gigue 0.021 ms.

## Verifications

| verification | resultat | detail |
|---|---|---|
| pcap_borne | **PASS** | 25000 <= 25000 paquets |
| pcap_flux_attendu | **PASS** | 25000/25000 paquets = 10.0.0.1 -> 10.0.0.4 UDP dport 5201 |
| regle_h1_h4_presente | **PASS** | trouvee sur ['s1', 's2', 's3'] |
| chemin_conforme | **PASS** | s1 output:3, s2 output:2, s3 output:2 |
| deltas_flux_identiques | **FAIL** | s1=41843 pkts/62333480 o, s2=41839 pkts/62327520 o, s3=41835 pkts/62321560 o |
| pas_de_trafic_via_controleur | **PASS** | Δ table-miss : s1=2, s2=2, s3=3 |
| ports_s1_s2_coherents | **PASS** | tx 43175 pkts/64309896 o, rx 43175 pkts/64309896 o |
| ports_s2_s3_coherents | **FAIL** | tx 43175 pkts/64309896 o, rx 43176 pkts/64309962 o |

## Phase 7 — iperf3 h1 → h4

| test | offert (Mbit/s) | emis | recu | perte % | gigue (ms) | retrans. TCP |
|---|---|---|---|---|---|---|
| tcp | — | 100.85 | 92.14 | — | — | 30 |
| udp_50M | 50 | 50.00 | 49.94 | 0.023 | 0.008 | — |
| udp_80M | 80 | 79.99 | 79.74 | 0.211 | 0.020 | — |
| udp_100M | 100 | 99.99 | 96.77 | 1.974 | 0.190 | — |

## Phase 8 — flux OpenFlow h1 → h4 (deltas avant/apres)

| switch | regle | sortie | Δ paquets | Δ octets | intervalle (s) | debit moyen sur l'intervalle (Mbit/s) |
|---|---|---|---|---|---|---|
| s1 | `priority=1,in_port=1,dl_src=00:00:00:00:00:01,dl_dst=00:00:00:00:00:04` | `output:3` | 41843 | 62333480 | 11.589 | 43.03 |
| s2 | `priority=1,in_port=1,dl_src=00:00:00:00:00:01,dl_dst=00:00:00:00:00:04` | `output:2` | 41839 | 62327520 | 11.582 | 43.05 |
| s3 | `priority=1,in_port=3,dl_src=00:00:00:00:00:01,dl_dst=00:00:00:00:00:04` | `output:2` | 41835 | 62321560 | 11.579 | 43.06 |

## Phase 8 — compteurs de ports sur le chemin (sens h1 → h4)

| lien | Δ tx paquets | Δ rx paquets | Δ tx octets | Δ rx octets | drops tx |
|---|---|---|---|---|---|
| s1:3 → s2:1 | 43175 | 43175 | 64309896 | 64309896 | 0 |
| s2:2 → s3:3 | 43175 | 43176 | 64309896 | 64309962 | 0 |
| h1 → s1:1 (rx) / s3:2 → h4 (tx) | 43176 | 43174 | 64309962 | 64309826 | 0 |

## Agregat (regle MAC) vs flux UDP etudie

- Regle h1→h4 sur s1 : **41843 paquets, 62333480 octets** (tout le trafic h1→h4 : UDP, connexion de controle TCP d'iperf3, ping de preparation).
- iperf3 UDP emis : **43160 datagrammes**, soit 64308400 octets sur le fil (1448 + 42 octets d'en-tetes chacun).
- Ecart : -1317 paquets, -1974920 octets = trafic non-UDP compte par la regle.
- PCAP (borne a 25000 paquets, filtre UDP dport 5201) : 25000 paquets sur 5.803 s, trame 46-1490 octets, intervalle median 0.001 ms, debit sur la fenetre capturee 51.35 Mbit/s.
- Intervalle moyen entre paquets captures : 0.232 ms (iperf3 emet par rafales, d'ou une mediane tres basse) ; la plus petite trame (46 octets) est le datagramme d'ouverture d'iperf3.
- Le debit « sur l'intervalle de snapshot » inclut les temps morts avant/apres iperf3 : il sous-estime le debit pendant l'emission et ne doit pas etre compare tel quel aux 49.99 Mbit/s d'iperf3.
