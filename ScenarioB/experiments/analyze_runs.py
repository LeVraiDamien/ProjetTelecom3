#!/usr/bin/env python3
"""Scenario B - Phase 10 : analyse d'une campagne (alignement KPM / Edge-AI / RM).

Usage : ./analyze_runs.py <prefixe>      ex. ./analyze_runs.py c1

Aligne par horodatage (obs_epoch_s de l'indication KPM, recopie dans edge_ai.csv et
rm_decisions.csv) les enregistrements des trois xApps avec les segments de trafic
(segments.csv = verite terrain). Regime etabli d'un segment = de debut+3 s a fin-1 s.

Sorties : <prefixe>-summary.csv (une ligne par segment de trafic) et <prefixe>-report.md.
Ce script ne mesure que la justesse, la stabilite et l'explicabilite des
recommandations : aucune action de controle n'ayant ete executee (DRY_RUN), aucun
gain de performance n'est calcule ni revendique.
"""

import csv
import json
import statistics as st
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKIP_START_S, SKIP_END_S = 3.0, 1.0
ML_TRUTH = {"5M": "low", "12M": "normal", "18M": "high"}


def load(path):
    return list(csv.DictReader(open(path))) if path.exists() else []


def f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def med(rows, col):
    v = [x for x in (f(r.get(col)) for r in rows) if x is not None]
    return st.median(v) if v else None


def mode(rows, col):
    c = Counter(r[col] for r in rows if r.get(col))
    if not c:
        return "", 0.0
    k, n = c.most_common(1)[0]
    return k, n / sum(c.values())


def fmt(x, n=2):
    return "—" if x is None or x == "" else ("%.*f" % (n, x) if isinstance(x, float) else str(x))


def main():
    prefix = sys.argv[1]
    runs = sorted(d for d in HERE.glob(prefix + "-*") if (d / "segments.csv").exists())
    rows, ml_pairs, run_notes = [], [], []

    for run in runs:
        segs, kpm = load(run / "segments.csv"), load(run / "kpm.csv")
        ai = [r for r in load(run / "edge_ai.csv") if r.get("valid") == "1"]
        rm = load(run / "rm_decisions.csv")
        deltas = [f(r["delta_prev_ms"]) for r in kpm[2:-1]]
        deltas = [d for d in deltas if d and d > 0]
        gaps = sum(1 for d in deltas if d > 1500)
        changes = [r for r in rm if r["decision_outcome"] == "CHANGED"]
        held = sum(1 for r in rm if r["decision_outcome"].startswith("HELD"))
        transitions = sum(1 for a, b in zip(segs, segs[1:]) if (a["kind"], a["offered"]) != (b["kind"], b["offered"]))
        run_notes.append({
            "run": run.name, "indications": len(kpm), "invalid": sum(r["mapping_status"] != "ok" for r in kpm),
            "period_ms": st.mean(deltas) if deltas else None, "gaps": gaps, "ai_rows": len(ai), "rm_rows": len(rm),
            "rm_changes": len(changes), "rm_held": held, "load_transitions": transitions,
            "dry_run_only": all(r["execution_mode"] == "DRY_RUN" and r["control_request_sent"] == "0" for r in rm),
            "ue": all(s["ue_connected"] == "True" for s in segs)})

        for s in segs:
            if s["kind"] == "idle":
                continue
            t0, t1 = f(s["start_epoch"]) + SKIP_START_S, f(s["end_epoch"]) - SKIP_END_S
            inside = lambda r, key="kpm_obs_epoch_s": t0 <= f(r[key]) <= t1  # noqa: E731
            k = [r for r in kpm if inside(r, "obs_epoch_s")]
            a = [r for r in ai if inside(r)]
            m = [r for r in rm if inside(r)]
            state, share = mode(a, "rule_state")
            ml, ml_share = mode(a, "ml_state")
            action, act_share = mode(m, "recommended_action")
            truth = ML_TRUTH.get(s["offered"]) if s["kind"] == "dl" else None
            if truth and a and a[0].get("ml_state"):
                ml_pairs += [(run.name, truth, r["ml_state"]) for r in a]
            # Delai de reaction : premiere analyse du segment (transitoire compris) dont
            # l'etat vaut l'etat majoritaire du regime etabli.
            first = next((f(r["kpm_obs_epoch_s"]) - f(s["start_epoch"]) for r in ai
                          if f(s["start_epoch"]) <= f(r["kpm_obs_epoch_s"]) <= f(s["end_epoch"])
                          and r["rule_state"] == state), None)
            first_rm = next((f(r["kpm_obs_epoch_s"]) - f(s["start_epoch"]) for r in rm
                             if f(s["start_epoch"]) <= f(r["kpm_obs_epoch_s"]) <= f(s["end_epoch"])
                             and r["recommended_action"] == action), None)
            rows.append({
                "run": run.name, "segment": s["segment"], "direction": s["kind"], "offered": s["offered"],
                "duration_s": s["duration_s"], "ue_connected": s["ue_connected"],
                "iperf_rx_mbps": f(s.get("iperf_receiver_mbps")), "iperf_loss_pct": f(s.get("iperf_lost_percent")),
                "iperf_jitter_ms": f(s.get("iperf_jitter_ms")), "n_kpm": len(k),
                "kpm_thp_dl_mbps": (med(k, "DRB.UEThpDl") or 0) / 1000 if k else None,
                "kpm_thp_ul_mbps": (med(k, "DRB.UEThpUl") or 0) / 1000 if k else None,
                "prb_dl_pct": med(k, "RRU.PrbTotDl"), "prb_ul_pct": med(k, "RRU.PrbTotUl"),
                "rlc_delay_dl_ms": None if med(k, "DRB.RlcSduDelayDl") is None else med(k, "DRB.RlcSduDelayDl") / 10,
                "rule_state": state, "rule_state_share": round(share, 3),
                "congestion_share": round(sum(r["congestion"] == "1" for r in a) / len(a), 3) if a else None,
                "state_reaction_s": first, "ml_truth": truth or "", "ml_state": ml,
                "ml_share": round(ml_share, 3) if ml else None,
                "rm_action": action, "rm_action_share": round(act_share, 3) if action else None,
                "rm_reaction_s": first_rm})

    fields = list(rows[0]) if rows else []
    with open(HERE / (prefix + "-summary.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    md = ["# Scenario B — campagne `%s`" % prefix, "",
          "Regime etabli d'un segment = de debut+%.0f s a fin-%.0f s. Valeurs KPM = medianes sur ce regime."
          % (SKIP_START_S, SKIP_END_S), "",
          "## Runs", "",
          "| run | indications KPM | invalides | periode moyenne (ms) | trous > 1,5 s | analyses Edge-AI | decisions RM | changements RM | retenues | transitions de charge | DRY_RUN seul | UE connecte |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for n in run_notes:
        md.append("| %s | %d | %d | %s | %d | %d | %d | %d | %d | %d | %s | %s |" % (
            n["run"], n["indications"], n["invalid"], fmt(n["period_ms"], 0), n["gaps"], n["ai_rows"], n["rm_rows"],
            n["rm_changes"], n["rm_held"], n["load_transitions"],
            "oui" if n["dry_run_only"] else "NON", "oui" if n["ue"] else "NON"))

    md += ["", "## Mesures par segment de trafic", "",
           "| run | sens | offert | iperf recu (Mbit/s) | perte % | KPM debit DL | KPM debit UL | PRB DL % | PRB UL % | delai RLC DL (ms) | etat (part) | congestion | reco. RM (part) |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        md.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s (%.0f %%) | %s | %s (%s) |" % (
            r["run"].replace(prefix + "-", ""), r["direction"], r["offered"], fmt(r["iperf_rx_mbps"]),
            fmt(r["iperf_loss_pct"]), fmt(r["kpm_thp_dl_mbps"]), fmt(r["kpm_thp_ul_mbps"]),
            fmt(r["prb_dl_pct"], 0), fmt(r["prb_ul_pct"], 0), fmt(r["rlc_delay_dl_ms"]),
            r["rule_state"] or "—", 100 * r["rule_state_share"],
            fmt(r["congestion_share"]), r["rm_action"] or "—",
            "—" if r["rm_action_share"] is None else "%.0f %%" % (100 * r["rm_action_share"])))

    # ---- repetabilite sur les runs d'evaluation
    ev = [r for r in rows if "-eval-" in r["run"]]
    if ev:
        md += ["", "## Repetabilite (runs `eval`, memes conditions)", "",
               "| offert | n | KPM debit DL min–max (Mbit/s) | PRB DL min–max (%) | delai min–max (ms) | etats detectes | recommandations |",
               "|---|---|---|---|---|---|---|"]
        for off in ("5M", "12M", "18M"):
            g = [r for r in ev if r["offered"] == off]
            if g:
                rng = lambda c, n=2: "%s–%s" % (fmt(min(r[c] for r in g), n), fmt(max(r[c] for r in g), n))  # noqa: E731
                md.append("| %s | %d | %s | %s | %s | %s | %s |" % (
                    off, len(g), rng("kpm_thp_dl_mbps"), rng("prb_dl_pct", 0), rng("rlc_delay_dl_ms"),
                    ", ".join(sorted({r["rule_state"] for r in g})), ", ".join(sorted({r["rm_action"] for r in g}))))

    # ---- modele ML : entrainement vs nouveaux runs
    model_path = HERE.parent / "xapps" / "edge_ai" / "model" / "model.json"
    if model_path.exists() and ml_pairs:
        model = json.loads(model_path.read_text())
        labels = ["low", "normal", "high"]
        new = [(t, p) for run, t, p in ml_pairs if run not in model["training_runs"]]
        md += ["", "## Arbre de decision `%s`" % model["version"], "",
               "- Entrainement : runs %s, %d echantillons (%s), seuils appris %s Mbit/s, exactitude sur le jeu "
               "d'entrainement **%.1f %%**." % (", ".join(model["training_runs"]), model["n_train"],
                                                 model["n_per_class"], model["thresholds_mbps"],
                                                 100 * model["train_accuracy"]),
               "- Ces seuils ne valent que pour cette caracteristique (debit DL KPM lisse) et ce banc ; "
               "le sujet cite 12,06 et 20,72 Mbit/s pour le modele de l'enseignant, que nous n'avons pas.",
               "- Evaluation sur des runs **nouveaux** (jamais vus a l'entrainement), regime etabli, %d echantillons : "
               "exactitude **%.1f %%**." % (len(new), 100 * sum(t == p for t, p in new) / len(new) if new else 0),
               "", "| verite \\ prediction | " + " | ".join(labels) + " |", "|---|" + "---|" * len(labels)]
        for t in labels:
            md.append("| %s | %s |" % (t, " | ".join(str(sum(1 for a, b in new if a == t and b == p)) for p in labels)))
        md += ["", "- Hors de son domaine d'entrainement le modele reste limite a trois classes de DEBIT : "
               "il classe « high » un debit de 18 Mbit/s comme un debit sature, alors que seules les regles "
               "(PRB + delai) distinguent charge elevee et congestion."]

    md += ["", "## Reactivite et stabilite", "",
           "| run | sens | offert | delai avant l'etat final (s) | delai avant la recommandation finale (s) |", "|---|---|---|---|---|"]
    for r in rows:
        md.append("| %s | %s | %s | %s | %s |" % (r["run"].replace(prefix + "-", ""), r["direction"], r["offered"],
                                                    fmt(r["state_reaction_s"], 1), fmt(r["rm_reaction_s"], 1)))
    (HERE / (prefix + "-report.md")).write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
