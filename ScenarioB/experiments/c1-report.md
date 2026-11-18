# Scenario B — campagne `c1`

Regime etabli d'un segment = de debut+3 s a fin-1 s. Valeurs KPM = medianes sur ce regime.

## Runs

| run | indications KPM | invalides | periode moyenne (ms) | trous > 1,5 s | analyses Edge-AI | decisions RM | changements RM | retenues | transitions de charge | DRY_RUN seul | UE connecte |
|---|---|---|---|---|---|---|---|---|---|---|---|
| c1-eval-01 | 120 | 0 | 1120 | 4 | 118 | 114 | 2 | 4 | 6 | oui | oui |
| c1-eval-02 | 119 | 0 | 1125 | 4 | 117 | 113 | 2 | 4 | 6 | oui | oui |
| c1-eval-03 | 120 | 0 | 1114 | 4 | 118 | 114 | 2 | 4 | 6 | oui | oui |
| c1-ramp | 119 | 0 | 1103 | 3 | 117 | 113 | 4 | 8 | 8 | oui | oui |
| c1-saturation | 111 | 0 | 1104 | 3 | 109 | 105 | 6 | 16 | 6 | oui | oui |
| c1-train-01 | 107 | 0 | 1103 | 3 | 0 | 0 | 0 | 0 | 6 | oui | oui |
| c1-train-02 | 104 | 0 | 1143 | 4 | 0 | 0 | 0 | 0 | 6 | oui | oui |
| c1-uplink-01 | 106 | 0 | 1105 | 3 | 104 | 100 | 8 | 18 | 8 | oui | oui |
| c1-uplink-02 | 107 | 0 | 1101 | 3 | 105 | 101 | 8 | 18 | 8 | oui | oui |

## Mesures par segment de trafic

| run | sens | offert | iperf recu (Mbit/s) | perte % | KPM debit DL | KPM debit UL | PRB DL % | PRB UL % | delai RLC DL (ms) | etat (part) | congestion | reco. RM (part) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| eval-01 | dl | 5M | 5.00 | 0.00 | 5.55 | 0.00 | 15 | 1 | 1.06 | NORMAL (100 %) | 0.00 | MAINTAIN_CURRENT_ALLOCATION (100 %) |
| eval-01 | dl | 12M | 12.00 | 0.00 | 13.42 | 0.00 | 38 | 1 | 1.55 | NORMAL (100 %) | 0.00 | MAINTAIN_CURRENT_ALLOCATION (100 %) |
| eval-01 | dl | 18M | 18.00 | 0.00 | 20.45 | 0.00 | 59 | 1 | 1.43 | ELEVATED (100 %) | 0.00 | CONTINUE_MONITORING (90 %) |
| eval-02 | dl | 5M | 5.00 | 0.00 | 5.53 | 0.00 | 15 | 1 | 1.06 | NORMAL (100 %) | 0.00 | MAINTAIN_CURRENT_ALLOCATION (100 %) |
| eval-02 | dl | 12M | 12.00 | 0.00 | 13.30 | 0.00 | 38 | 1 | 1.53 | NORMAL (100 %) | 0.00 | MAINTAIN_CURRENT_ALLOCATION (100 %) |
| eval-02 | dl | 18M | 18.00 | 0.00 | 21.10 | 0.00 | 61 | 1 | 1.58 | ELEVATED (95 %) | 0.00 | CONTINUE_MONITORING (84 %) |
| eval-03 | dl | 5M | 5.00 | 0.00 | 5.55 | 0.00 | 15 | 1 | 1.06 | NORMAL (100 %) | 0.00 | MAINTAIN_CURRENT_ALLOCATION (100 %) |
| eval-03 | dl | 12M | 12.00 | 0.00 | 13.36 | 0.00 | 38 | 1 | 1.56 | NORMAL (100 %) | 0.00 | MAINTAIN_CURRENT_ALLOCATION (100 %) |
| eval-03 | dl | 18M | 18.00 | 0.00 | 20.05 | 0.00 | 57 | 1 | 1.38 | ELEVATED (95 %) | 0.00 | CONTINUE_MONITORING (85 %) |
| ramp | dl | 5M | 5.00 | 0.00 | 5.52 | 0.00 | 15 | 1 | 1.06 | NORMAL (100 %) | 0.00 | MAINTAIN_CURRENT_ALLOCATION (100 %) |
| ramp | dl | 12M | 12.00 | 0.00 | 13.45 | 0.00 | 38 | 1 | 1.53 | NORMAL (100 %) | 0.00 | MAINTAIN_CURRENT_ALLOCATION (100 %) |
| ramp | dl | 18M | 18.00 | 0.00 | 20.26 | 0.00 | 59 | 1 | 1.39 | ELEVATED (100 %) | 0.00 | CONTINUE_MONITORING (75 %) |
| ramp | dl | 32M | 24.54 | 6.12 | 28.85 | 0.00 | 84 | 1 | 1425.85 | HIGH (100 %) | 1.00 | REVIEW_RESOURCE_ALLOCATION (78 %) |
| ramp | dl | 18M | 18.00 | 0.00 | 20.13 | 0.00 | 58 | 1 | 1.37 | ELEVATED (100 %) | 0.00 | CONTINUE_MONITORING (100 %) |
| ramp | dl | 12M | 12.00 | 0.00 | 13.28 | 0.00 | 38 | 1 | 1.54 | NORMAL (100 %) | 0.00 | MAINTAIN_CURRENT_ALLOCATION (100 %) |
| ramp | dl | 5M | 5.00 | 0.00 | 5.53 | 0.00 | 15 | 1 | 1.05 | NORMAL (100 %) | 0.00 | MAINTAIN_CURRENT_ALLOCATION (100 %) |
| saturation | dl | 25M | 25.00 | 0.00 | 27.72 | 0.00 | 80 | 1 | 1.60 | HIGH (69 %) | 0.00 | CONTINUE_MONITORING (81 %) |
| saturation | dl | 32M | 25.55 | 11.73 | 28.85 | 0.00 | 84 | 1 | 1617.54 | HIGH (94 %) | 0.94 | REVIEW_RESOURCE_ALLOCATION (82 %) |
| saturation | dl | 40M | 24.69 | 28.60 | 28.85 | 0.00 | 84 | 1 | 1618.08 | HIGH (94 %) | 0.94 | REVIEW_RESOURCE_ALLOCATION (82 %) |
| train-01 | dl | 5M | 5.00 | 0.00 | 5.59 | 0.00 | 15 | 1 | 1.08 | — (0 %) | — | — (—) |
| train-01 | dl | 12M | 12.00 | 0.00 | 13.38 | 0.00 | 38 | 1 | 1.54 | — (0 %) | — | — (—) |
| train-01 | dl | 18M | 18.00 | 0.00 | 19.97 | 0.00 | 57 | 1 | 1.37 | — (0 %) | — | — (—) |
| train-02 | dl | 5M | 5.00 | 0.00 | 5.62 | 0.00 | 15 | 1 | 1.14 | — (0 %) | — | — (—) |
| train-02 | dl | 12M | 12.00 | 0.00 | 13.31 | 0.00 | 38 | 1 | 1.54 | — (0 %) | — | — (—) |
| train-02 | dl | 18M | 18.00 | 0.00 | 20.06 | 0.00 | 57 | 1 | 1.38 | — (0 %) | — | — (—) |
| uplink-01 | ul | 1M | 1.00 | 0.00 | 0.00 | 1.12 | 0 | 40 | — | NORMAL (100 %) | 0.00 | MAINTAIN_CURRENT_ALLOCATION (100 %) |
| uplink-01 | ul | 2M | 2.00 | 0.00 | 0.00 | 2.24 | 0 | 63 | — | ELEVATED (91 %) | 0.00 | CONTINUE_MONITORING (73 %) |
| uplink-01 | ul | 3M | 3.00 | 0.00 | 0.00 | 3.36 | 0 | 92 | — | HIGH (91 %) | 0.00 | CONTINUE_MONITORING (46 %) |
| uplink-01 | ul | 5M | 4.89 | 1.27 | 0.00 | 5.85 | 0 | 96 | — | HIGH (91 %) | 0.00 | CONTINUE_MONITORING (46 %) |
| uplink-02 | ul | 1M | 1.00 | 0.00 | 0.00 | 1.12 | 0 | 38 | — | NORMAL (100 %) | 0.00 | MAINTAIN_CURRENT_ALLOCATION (100 %) |
| uplink-02 | ul | 2M | 2.00 | 0.00 | 0.00 | 2.24 | 0 | 61 | — | ELEVATED (100 %) | 0.00 | CONTINUE_MONITORING (80 %) |
| uplink-02 | ul | 3M | 3.00 | 0.00 | 0.00 | 3.37 | 0 | 92 | — | HIGH (100 %) | 0.00 | CONTINUE_MONITORING (50 %) |
| uplink-02 | ul | 5M | 4.92 | 0.93 | 0.00 | 5.90 | 0 | 96 | — | HIGH (100 %) | 0.00 | CONTINUE_MONITORING (50 %) |

## Repetabilite (runs `eval`, memes conditions)

| offert | n | KPM debit DL min–max (Mbit/s) | PRB DL min–max (%) | delai min–max (ms) | etats detectes | recommandations |
|---|---|---|---|---|---|---|
| 5M | 3 | 5.53–5.55 | 15–15 | 1.06–1.06 | NORMAL | MAINTAIN_CURRENT_ALLOCATION |
| 12M | 3 | 13.30–13.42 | 38–38 | 1.53–1.56 | NORMAL | MAINTAIN_CURRENT_ALLOCATION |
| 18M | 3 | 20.05–21.10 | 57–61 | 1.38–1.58 | ELEVATED | CONTINUE_MONITORING |

## Arbre de decision `dt-v1-c1`

- Entrainement : runs c1-train-01, c1-train-02, 118 echantillons ({'high': 39, 'low': 39, 'normal': 40}), seuils appris [8.12, 14.787] Mbit/s, exactitude sur le jeu d'entrainement **100.0 %**.
- Ces seuils ne valent que pour cette caracteristique (debit DL KPM lisse) et ce banc ; le sujet cite 12,06 et 20,72 Mbit/s pour le modele de l'enseignant, que nous n'avons pas.
- Evaluation sur des runs **nouveaux** (jamais vus a l'entrainement), regime etabli, 227 echantillons : exactitude **99.1 %**.

| verite \ prediction | low | normal | high |
|---|---|---|---|
| low | 76 | 0 | 0 |
| normal | 1 | 76 | 0 |
| high | 0 | 1 | 73 |

- Hors de son domaine d'entrainement le modele reste limite a trois classes de DEBIT : il classe « high » un debit de 18 Mbit/s comme un debit sature, alors que seules les regles (PRB + delai) distinguent charge elevee et congestion.

## Reactivite et stabilite

| run | sens | offert | delai avant l'etat final (s) | delai avant la recommandation finale (s) |
|---|---|---|---|---|
| eval-01 | dl | 5M | 0.5 | 0.5 |
| eval-01 | dl | 12M | 0.4 | 0.4 |
| eval-01 | dl | 18M | 3.8 | 6.0 |
| eval-02 | dl | 5M | 1.0 | 1.0 |
| eval-02 | dl | 12M | 1.0 | 1.0 |
| eval-02 | dl | 18M | 4.2 | 6.4 |
| eval-03 | dl | 5M | 0.3 | 0.3 |
| eval-03 | dl | 12M | 0.3 | 0.3 |
| eval-03 | dl | 18M | 5.5 | 7.7 |
| ramp | dl | 5M | 0.7 | 0.7 |
| ramp | dl | 12M | 0.2 | 0.2 |
| ramp | dl | 18M | 3.1 | 5.3 |
| ramp | dl | 32M | 3.9 | 6.0 |
| ramp | dl | 18M | 0.5 | 2.7 |
| ramp | dl | 12M | 1.1 | 3.3 |
| ramp | dl | 5M | 0.6 | 0.6 |
| saturation | dl | 25M | 5.2 | 6.3 |
| saturation | dl | 32M | 4.6 | 6.8 |
| saturation | dl | 40M | 5.2 | 7.3 |
| train-01 | dl | 5M | — | — |
| train-01 | dl | 12M | — | — |
| train-01 | dl | 18M | — | — |
| train-02 | dl | 5M | — | — |
| train-02 | dl | 12M | — | — |
| train-02 | dl | 18M | — | — |
| uplink-01 | ul | 1M | 0.8 | 0.8 |
| uplink-01 | ul | 2M | 4.2 | 6.4 |
| uplink-01 | ul | 3M | 4.2 | 5.3 |
| uplink-01 | ul | 5M | 4.4 | 5.5 |
| uplink-02 | ul | 1M | 0.7 | 0.7 |
| uplink-02 | ul | 2M | 3.9 | 6.1 |
| uplink-02 | ul | 3M | 3.9 | 5.0 |
| uplink-02 | ul | 5M | 3.9 | 5.0 |
