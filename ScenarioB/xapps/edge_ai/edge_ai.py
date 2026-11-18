#!/usr/bin/env python3
"""Scenario B - Phase 8 : xApp Edge-AI (analyse de charge du RAN).

ENTREE  : /data/kpm.csv, ecrit par l'xApp KPM (xapp_kpm_csv). Echange applicatif
          par fichier CSV partage ; une ligne par indication (~1 par seconde).
          Horodatage = obs_epoch_s (reception par l'xApp KPM, secondes Unix UTC).
SORTIE  : /data/edge_ai.csv, une ligne par indication analysee, lue ensuite par
          l'xApp de gestion des ressources.

Pretraitement : lignes en double (meme obs_epoch_s) ignorees ; lignes dont
mapping_status != ok ou dont un debit/PRB est illisible marquees invalides et
exclues des fenetres ; un delai RLC vide (aucune SDU emise) reste "absent".

Caracteristiques (fenetre glissante de WINDOW indications) :
  moyennes mobiles de debit DL/UL (Mbit/s), PRB DL/UL (%), delai RLC DL (ms),
  tendance du debit DL (pente sur TREND_N points, Mbit/s par seconde).

1) Detecteur a regles (reference, transparent). Seuils tires du balayage
   calib-dl-01 (5/12/18 Mbit/s -> 15/38/59 % de PRB, delai 1,1-1,6 ms ;
   >= 25 Mbit/s -> PRB plafonne a 84 %, delai 38 ms puis > 1 s) :
     charge = max(PRB DL, PRB UL) en moyenne mobile
       NORMAL    charge <  PRB_ELEVATED (50 %)
       ELEVATED  PRB_ELEVATED <= charge < PRB_HIGH (80 %)
       HIGH      charge >= PRB_HIGH
     congestion = HIGH ET delai RLC DL moyen >= DELAY_CONGESTED_MS (10 ms)
   Un debit eleve seul ne suffit donc jamais a declarer une congestion.
   Limite : il n'existe pas de mesure de delai montant ; une charge HIGH due au
   montant est signalee (ul_saturation_suspected) mais pas "congestion".

2) Modele optionnel : arbre de decision (model.json, entraine hors ligne par
   train_tree.py sur des runs separes) qui predit low/normal/high a partir du
   debit DL moyen. Ses seuils ne valent que pour ce jeu d'entrainement.
"""

import json
import os
import sys
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import CsvOut, Stopper, follow_csv, num  # noqa: E402

RULES_VERSION = "rules-v1"
WINDOW = 3
TREND_N = 5
PRB_ELEVATED = 50.0
PRB_HIGH = 80.0
DELAY_CONGESTED_MS = 10.0

FIELDS = ["run_id", "analysis_time_utc", "analysis_epoch_s", "kpm_obs_epoch_s", "kpm_delta_prev_ms",
          "valid", "invalid_reason", "window_n",
          "thp_dl_mbps", "thp_ul_mbps", "prb_dl_pct", "prb_ul_pct", "rlc_delay_dl_ms",
          "thp_dl_ma_mbps", "thp_ul_ma_mbps", "prb_dl_ma_pct", "prb_ul_ma_pct", "rlc_delay_dl_ma_ms",
          "thp_dl_trend_mbps_per_s",
          "rule_state", "congestion", "ul_saturation_suspected", "rule_reason", "rules_version",
          "ml_state", "ml_confidence", "ml_model_version"]


def mean(values):
    v = [x for x in values if x is not None]
    return sum(v) / len(v) if v else None


def slope(points):
    """Pente des moindres carres de (t, y)."""
    pts = [(t, y) for t, y in points if y is not None]
    if len(pts) < 3:
        return None
    mt, my = mean([p[0] for p in pts]), mean([p[1] for p in pts])
    den = sum((t - mt) ** 2 for t, _ in pts)
    return sum((t - mt) * (y - my) for t, y in pts) / den if den else None


def tree_predict(model, x):
    """Parcourt l'arbre exporte en JSON ; rend (classe, confiance = part de la classe dans la feuille)."""
    node = model["tree"]
    while "leaf" not in node:
        node = node["left"] if x <= node["threshold"] else node["right"]
    return node["leaf"], node["confidence"]


def rule_state(prb_dl, prb_ul, delay_ms):
    load = max(prb_dl, prb_ul)
    if load >= PRB_HIGH:
        state = "HIGH"
    elif load >= PRB_ELEVATED:
        state = "ELEVATED"
    else:
        state = "NORMAL"
    congested = state == "HIGH" and delay_ms is not None and delay_ms >= DELAY_CONGESTED_MS
    ul_sat = state == "HIGH" and prb_ul >= PRB_HIGH
    reason = "max(prb_dl_ma=%.1f,prb_ul_ma=%.1f)=%.1f %s ; delai_ma=%s ms %s %.0f" % (
        prb_dl, prb_ul, load,
        ">= %.0f" % PRB_HIGH if state == "HIGH" else ">= %.0f" % PRB_ELEVATED if state == "ELEVATED" else "< %.0f" % PRB_ELEVATED,
        "absent" if delay_ms is None else "%.2f" % delay_ms,
        ">=" if (delay_ms or 0) >= DELAY_CONGESTED_MS else "<", DELAY_CONGESTED_MS)
    return state, congested, ul_sat, reason


def r(x, n=3):
    return "" if x is None else round(x, n)


def main():
    data = Path(os.environ.get("DATA_DIR", "/data"))
    model_path = Path(os.environ.get("MODEL_PATH", "/model/model.json"))
    model = json.loads(model_path.read_text()) if model_path.exists() else None
    print("[edge_ai] regles %s ; modele %s" % (RULES_VERSION, model["version"] if model else "absent"), flush=True)

    stopper = Stopper()
    out = CsvOut(data / "edge_ai.csv", FIELDS)
    win, trend, seen, n_ok, n_bad = deque(maxlen=WINDOW), deque(maxlen=TREND_N), set(), 0, 0

    for row in follow_csv(data / "kpm.csv", stopper):
        epoch = num(row.get("obs_epoch_s"))
        if epoch is None or epoch in seen:
            continue                                   # doublon ou ligne sans horodatage
        seen.add(epoch)
        now = time.time()
        base = {"run_id": row.get("run_id", ""), "analysis_epoch_s": round(now, 3),
                "analysis_time_utc": datetime.fromtimestamp(now, timezone.utc).isoformat(timespec="milliseconds"),
                "kpm_obs_epoch_s": epoch, "kpm_delta_prev_ms": row.get("delta_prev_ms", ""),
                "rules_version": RULES_VERSION}

        thp_dl, thp_ul = num(row.get("DRB.UEThpDl")), num(row.get("DRB.UEThpUl"))
        prb_dl, prb_ul = num(row.get("RRU.PrbTotDl")), num(row.get("RRU.PrbTotUl"))
        delay = num(row.get("DRB.RlcSduDelayDl"))
        bad = ("mapping_status=%s" % row.get("mapping_status") if row.get("mapping_status") != "ok"
               else "valeur manquante" if None in (thp_dl, thp_ul, prb_dl, prb_ul) else "")
        if bad:
            n_bad += 1
            out.write(dict(base, valid=0, invalid_reason=bad))
            continue

        s = {"thp_dl": thp_dl / 1000, "thp_ul": thp_ul / 1000, "prb_dl": prb_dl, "prb_ul": prb_ul,
             "delay": None if delay is None else delay / 10}        # kbit/s -> Mbit/s ; 0,1 ms -> ms
        win.append(s)
        trend.append((epoch, s["thp_dl"]))
        ma = {k: mean([w[k] for w in win]) for k in s}
        state, congested, ul_sat, reason = rule_state(ma["prb_dl"], ma["prb_ul"], ma["delay"])
        ml_state, ml_conf = tree_predict(model, ma["thp_dl"]) if model else ("", "")
        n_ok += 1
        out.write(dict(
            base, valid=1, invalid_reason="", window_n=len(win),
            thp_dl_mbps=r(s["thp_dl"]), thp_ul_mbps=r(s["thp_ul"]), prb_dl_pct=r(prb_dl, 0),
            prb_ul_pct=r(prb_ul, 0), rlc_delay_dl_ms=r(s["delay"]),
            thp_dl_ma_mbps=r(ma["thp_dl"]), thp_ul_ma_mbps=r(ma["thp_ul"]), prb_dl_ma_pct=r(ma["prb_dl"], 1),
            prb_ul_ma_pct=r(ma["prb_ul"], 1), rlc_delay_dl_ma_ms=r(ma["delay"]),
            thp_dl_trend_mbps_per_s=r(slope(trend)),
            rule_state=state, congestion=int(congested), ul_saturation_suspected=int(ul_sat),
            rule_reason=reason, ml_state=ml_state, ml_confidence=ml_conf,
            ml_model_version=model["version"] if model else ""))
    out.close()
    print("[edge_ai] arret propre : %d analyses, %d lignes invalides" % (n_ok, n_bad), flush=True)


if __name__ == "__main__":
    main()
