# Phase 10 — classification de trafic et politique SDN (p10-20261116T130701Z)

Regle de classification (`p10-rules-v1`) : BULK si debit ≥ 10 Mbit/s **et** taille moyenne ≥ 1000 octets pendant 2 intervalles consecutifs de 1 s, sinon LIGHT ; classe = protocole + BULK/LIGHT.
Politique : UDP_BULK → meter OpenFlow 20000 kbit/s sur le switch d'entree (mode enforce uniquement).

## Verifications

| verification | resultat | detail |
|---|---|---|
| monitor/pas_d_erreur_openflow | **PASS** | 0 erreur(s) |
| monitor/mode_controleur | **PASS** | POLICY_MODE=monitor |
| monitor/classe_single_tcp | **PASS** | attendu TCP_BULK, decide TCP_BULK |
| monitor/classe_single_udp_50M | **PASS** | attendu UDP_BULK, decide UDP_BULK |
| monitor/classe_single_udp_1M_small | **PASS** | attendu UDP_LIGHT, decide UDP_LIGHT |
| monitor/classe_compete_tcp | **PASS** | attendu TCP_BULK, decide TCP_BULK |
| monitor/classe_compete_udp_80M | **PASS** | attendu UDP_BULK, decide UDP_BULK |
| monitor/classes_stables | **PASS** | 0 flux reclasses |
| enforce/pas_d_erreur_openflow | **PASS** | 0 erreur(s) |
| enforce/mode_controleur | **PASS** | POLICY_MODE=enforce |
| enforce/classe_single_tcp | **PASS** | attendu TCP_BULK, decide TCP_BULK |
| enforce/classe_single_udp_50M | **PASS** | attendu UDP_BULK, decide UDP_BULK |
| enforce/classe_single_udp_1M_small | **PASS** | attendu UDP_LIGHT, decide UDP_LIGHT |
| enforce/classe_compete_tcp | **PASS** | attendu TCP_BULK, decide TCP_BULK |
| enforce/classe_compete_udp_80M | **PASS** | attendu UDP_BULK, decide UDP_BULK |
| enforce/classes_stables | **PASS** | 0 flux reclasses |
| monitor/aucune_action_executee | **PASS** | 0 action(s), 0 regle(s) avec meter, 0 paquets jetes |
| enforce/meter_dans_table_de_flux | **PASS** | 1 regle(s) avec meter |
| enforce/meter_a_jete_des_paquets | **PASS** | 104471 paquets jetes par le meter 1 sur s1 |
| enforce/udp_limite_au_seuil | **PASS** | PCAP h4 en regime etabli : 19.82 Mbit/s pour une limite de 20 |
| enforce/tcp_ameliore | **PASS** | TCP en regime etabli : 16.10 → 79.00 Mbit/s |

## Validation de la classification (verite terrain = commande iperf3)

| mode | test | attendu | decide | debit a la decision (Mbit/s) | taille moy. (o) | delai de decision (s) |
|---|---|---|---|---|---|---|
| monitor | single_tcp | TCP_BULK | TCP_BULK ✓ | 99.004 | 1973.2 | 2.13 |
| monitor | single_udp_50M | UDP_BULK | UDP_BULK ✓ | 51.451 | 1490.0 | 2.733 |
| monitor | single_udp_1M_small | UDP_LIGHT | UDP_LIGHT ✓ | 1.209 | 242.0 | 2.645 |
| monitor | compete_tcp | TCP_BULK | TCP_BULK ✓ | 20.383 | 2701.5 | 2.549 |
| monitor | compete_udp_80M | UDP_BULK | UDP_BULK ✓ | 82.155 | 1490.0 | 2.547 |
| enforce | single_tcp | TCP_BULK | TCP_BULK ✓ | 99.037 | 1920.9 | 2.152 |
| enforce | single_udp_50M | UDP_BULK | UDP_BULK ✓ | 51.502 | 1490.0 | 2.774 |
| enforce | single_udp_1M_small | UDP_LIGHT | UDP_LIGHT ✓ | 1.212 | 242.0 | 2.706 |
| enforce | compete_tcp | TCP_BULK | TCP_BULK ✓ | 16.025 | 2631.4 | 2.611 |
| enforce | compete_udp_80M | UDP_BULK | UDP_BULK ✓ | 84.119 | 1490.0 | 2.611 |

Flux de donnees generes : **10/10 corrects**. Flux annexes (connexions de controle iperf3, ACK TCP, retours UDP) : 30 observes, 16 classes LIGHT, 14 trop courts pour etre classes, 0 classes BULK a tort.

## Effet de la politique : TCP h2→h3 en concurrence avec UDP 80 Mbit/s h1→h4 (20 s)

| mesure | monitor (temoin) | enforce (meter) |
|---|---|---|
| TCP recu, moyenne sur l'essai (Mbit/s) | 16.60 | 68.42 |
| TCP emis, regime etabli t ≥ 6 s (Mbit/s) | 16.10 | 79.00 |
| TCP retransmissions | 96 | 38 |
| UDP recu, moyenne sur l'essai (Mbit/s) | 79.50 | 27.16 |
| UDP recu d'apres le PCAP sur h4, regime etabli (Mbit/s) | 83.14 | 19.82 |
| UDP perte (%) | 0.12 | 65.77 |
| UDP gigue (ms) | 0.179 | 0.425 |
| Paquets jetes par le meter 1 (s1) | 0 | 104471 |

Debit TCP emis par seconde (Mbit/s) :

- monitor : 31 24 20 19 13 13 19 12 19 13 19 19 13 19 13 19 13 19 19 13
- enforce : 30 19 31 78 73 78 79 74 79 74 81 74 81 74 85 81 84 71 86 83

## Flux isoles (meme commande dans les deux modes)

| test | monitor recu (Mbit/s) | monitor perte % | enforce recu (Mbit/s) | enforce perte % |
|---|---|---|---|---|
| single_tcp | 94.05 | — | 92.32 | — |
| single_udp_50M | 49.89 | 0.00 | 30.13 | 39.62 |
| single_udp_1M_small | 1.00 | 0.00 | 1.00 | 0.00 |

## Changement dans les tables de flux (mode enforce, apres l'essai)

- s1 : `priority=10,udp,in_port=1,nw_src=10.0.0.1,nw_dst=10.0.0.4,tp_src=35512,tp_dst=5201` → `meter:1,goto_table:1`

Actions executees par le controleur :

- flux 19 (dpid 1) : classe UDP_BULK → action meter 1, limite 20000 kbit/s
- flux 49 (dpid 1) : classe UDP_BULK → action meter 1, limite 20000 kbit/s

## Limites

- La decision arrive environ 2 a 3 s apres le debut du flux : pendant ce temps le flux UDP n'est pas limite (visible sur les premieres secondes du debit TCP en mode enforce).
- Les moyennes « sur l'essai » incluent cette phase ; les valeurs « regime etabli » l'excluent.
- Le meter jette l'excedent du flux classe UDP_BULK ; ses pertes sont donc voulues, pas un defaut du lien.
- Classes et seuils valides uniquement sur du trafic iperf3 controle ; aucun trafic applicatif reel.
