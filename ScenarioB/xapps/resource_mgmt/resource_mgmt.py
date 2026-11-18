#!/usr/bin/env python3
"""Scenario B - Phase 9 : xApp de gestion des ressources, mode DRY_RUN (observation seule).

ENTREE : /data/edge_ai.csv (xApp Edge-AI), qui contient deja les mesures KPM
         utiles et l'etat detecte. SORTIE : /data/rm_decisions.csv.

Cette application NE CONTACTE NI LE RIC NI LE gNB : aucune requete E2SM-RC
n'est envoyee, la configuration du gNB n'est jamais modifiee. Chaque ligne porte
execution_mode=DRY_RUN et control_request_sent=0. Une "recommandation" est ce
qu'un operateur (ou une future action de controle validee) devrait faire ; ce
n'est pas une action executee, et aucun gain de performance ne peut en etre deduit.

Politique (policy-v1), fondee sur l'etat a regles de l'Edge-AI, donc sur la
charge PRB ET le delai RLC, pas sur le debit seul :
  NORMAL                      -> MAINTAIN_CURRENT_ALLOCATION
  ELEVATED                    -> CONTINUE_MONITORING
  HIGH sans congestion        -> CONTINUE_MONITORING   (PRB hauts mais delai bas :
                                 la cellule ecoule encore le trafic)
  HIGH avec congestion        -> REVIEW_RESOURCE_ALLOCATION
  HIGH, montant sature        -> REVIEW_RESOURCE_ALLOCATION apres UL_PERSIST
                                 evaluations (pas de mesure de delai montant)

Stabilite : la recommandation ne change que si la meme recommandation candidate
est observee CONSECUTIVE fois de suite, et jamais moins de COOLDOWN_S secondes
apres le changement precedent. Une mesure isolee ne provoque donc aucun changement.
"""

import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import CsvOut, Stopper, follow_csv, num  # noqa: E402

POLICY_VERSION = "policy-v1"
CONSECUTIVE = 3
COOLDOWN_S = 5.0
UL_PERSIST = 5
EXECUTION_MODE = "DRY_RUN"

FIELDS = ["run_id", "decision_time_utc", "decision_epoch_s", "edge_ai_analysis_epoch_s", "kpm_obs_epoch_s",
          "thp_dl_ma_mbps", "thp_ul_ma_mbps", "prb_dl_ma_pct", "prb_ul_ma_pct", "rlc_delay_dl_ma_ms",
          "rule_state", "congestion", "ul_saturation_suspected", "ml_state",
          "policy_condition", "candidate_action", "candidate_streak", "seconds_since_last_change",
          "decision_outcome", "recommended_action", "policy_version", "ml_model_version",
          "execution_mode", "control_request_sent"]


def candidate(row, ul_streak):
    state = row["rule_state"]
    if state == "NORMAL":
        return "MAINTAIN_CURRENT_ALLOCATION", "etat NORMAL (charge PRB < 50 %)"
    if state == "ELEVATED":
        return "CONTINUE_MONITORING", "etat ELEVATED (50 % <= charge PRB < 80 %)"
    if row["congestion"] == "1":
        return "REVIEW_RESOURCE_ALLOCATION", "etat HIGH + delai RLC DL >= 10 ms (congestion)"
    if row["ul_saturation_suspected"] == "1" and ul_streak >= UL_PERSIST:
        return "REVIEW_RESOURCE_ALLOCATION", "etat HIGH, PRB UL >= 80 %% depuis %d evaluations" % ul_streak
    return "CONTINUE_MONITORING", "etat HIGH sans congestion confirmee"


def main():
    data = Path(os.environ.get("DATA_DIR", "/data"))
    stopper = Stopper()
    out = CsvOut(data / "rm_decisions.csv", FIELDS)
    print("[rm] %s, mode %s : aucune requete de controle ne sera envoyee" % (POLICY_VERSION, EXECUTION_MODE), flush=True)

    current, last_cand, streak, last_change, ul_streak, n, changes = None, None, 0, None, 0, 0, 0
    for row in follow_csv(data / "edge_ai.csv", stopper):
        if row.get("valid") != "1":
            continue                                    # mesure invalide : pas de decision
        obs = num(row["kpm_obs_epoch_s"])
        ul_streak = ul_streak + 1 if row["ul_saturation_suspected"] == "1" else 0
        cand, cond = candidate(row, ul_streak)
        streak = streak + 1 if cand == last_cand else 1
        last_cand = cand
        since = None if last_change is None else obs - last_change

        if current is None:
            current, last_change, outcome = cand, obs, "INITIAL"
        elif cand == current:
            outcome = "UNCHANGED"
        elif streak < CONSECUTIVE:
            outcome = "HELD_WAITING_CONSECUTIVE(%d/%d)" % (streak, CONSECUTIVE)
        elif since is not None and since < COOLDOWN_S:
            outcome = "HELD_COOLDOWN(%.1f/%.0fs)" % (since, COOLDOWN_S)
        else:
            current, last_change, outcome = cand, obs, "CHANGED"
            changes += 1
        n += 1
        now = time.time()
        out.write({
            "run_id": row["run_id"], "decision_epoch_s": round(now, 3),
            "decision_time_utc": datetime.fromtimestamp(now, timezone.utc).isoformat(timespec="milliseconds"),
            "edge_ai_analysis_epoch_s": row["analysis_epoch_s"], "kpm_obs_epoch_s": row["kpm_obs_epoch_s"],
            **{k: row[k] for k in ("thp_dl_ma_mbps", "thp_ul_ma_mbps", "prb_dl_ma_pct", "prb_ul_ma_pct",
                                   "rlc_delay_dl_ma_ms", "rule_state", "congestion",
                                   "ul_saturation_suspected", "ml_state", "ml_model_version")},
            "policy_condition": cond, "candidate_action": cand, "candidate_streak": streak,
            "seconds_since_last_change": "" if since is None else round(since, 1),
            "decision_outcome": outcome, "recommended_action": current,
            "policy_version": POLICY_VERSION, "execution_mode": EXECUTION_MODE, "control_request_sent": 0})
    out.close()
    print("[rm] arret propre : %d decisions, %d changements de recommandation, 0 requete de controle" % (n, changes),
          flush=True)


if __name__ == "__main__":
    main()
