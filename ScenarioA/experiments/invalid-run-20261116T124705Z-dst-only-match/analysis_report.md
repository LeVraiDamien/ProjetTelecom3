# Analyse invalid-run-20261116T124705Z-dst-only-match

Flux etudie : h1 10.0.0.1 -> h4 10.0.0.4 UDP dport 5201, debit offert 50M, duree 10 s.

iperf3 (Phase 8) : emis 50.00 Mbit/s, recu 17.72 Mbit/s, perte 42.502 % (18344/43160), gigue 0.227 ms.

## Verifications

| verification | resultat | detail |
|---|---|---|
| pcap_borne | **PASS** | 25000 <= 25000 paquets |
| pcap_flux_attendu | **PASS** | 25000/25000 paquets = 10.0.0.1 -> 10.0.0.4 UDP dport 5201 |
| regle_h1_h4_presente | **FAIL** | trouvee sur aucun switch |
| pas_de_trafic_via_controleur | **FAIL** | Δ table-miss : s1=43176, s2=24173, s3=24073 |
| ports_s1_s2_coherents | **PASS** | tx 24533 pkts/36526210 o, rx 24533 pkts/36526210 o |
| ports_s2_s3_coherents | **PASS** | tx 24533 pkts/36526210 o, rx 24533 pkts/36526210 o |

## Phase 7 — iperf3 h1 → h4

| test | offert (Mbit/s) | emis | recu | perte % | gigue (ms) | retrans. TCP |
|---|---|---|---|---|---|---|
| tcp | — | 21.08 | 17.12 | — | — | 0 |
| udp_50M | 50 | 50.00 | 17.92 | 43.601 | 2.001 | — |
| udp_80M | 80 | 79.99 | 17.82 | 64.724 | 0.231 | — |
| udp_100M | 100 | 99.99 | 17.80 | 71.246 | 0.191 | — |

## Phase 8 — flux OpenFlow h1 → h4 (deltas avant/apres)

| switch | regle | sortie | Δ paquets | Δ octets | intervalle (s) | debit moyen sur l'intervalle (Mbit/s) |
|---|---|---|---|---|---|---|

## Phase 8 — compteurs de ports sur le chemin (sens h1 → h4)

| lien | Δ tx paquets | Δ rx paquets | Δ tx octets | Δ rx octets | drops tx |
|---|---|---|---|---|---|
| s1:3 → s2:1 | 24533 | 24533 | 36526210 | 36526210 | 0 |
| s2:2 → s3:3 | 24533 | 24533 | 36526210 | 36526210 | 0 |
| h1 → s1:1 (rx) / s3:2 → h4 (tx) | 24533 | 43181 | 36526210 | 64310307 | 0 |
