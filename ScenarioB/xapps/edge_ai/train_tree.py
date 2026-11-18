#!/usr/bin/env python3
"""Scenario B - Phase 8 (extension ML) : entraine l'arbre de decision de l'Edge-AI.

Usage (dans l'image telecom-lab-p3-ai:1.0, voir train.sh) :
  train_tree.py --out model/model.json --version dt-v1 <run_dir> [<run_dir> ...]

Donnees : runs ENTIERS dedies a l'entrainement (jamais un tirage aleatoire
d'echantillons voisins d'une meme serie temporelle : l'evaluation se fait sur
d'autres runs, par analyze_runs.py).
Etiquette = debit descendant OFFERT du segment (verite terrain de segments.csv) :
  5M -> low, 12M -> normal, 18M -> high.
Caracteristique = moyenne mobile sur 3 indications du debit DL mesure par KPM
(Mbit/s), exactement celle calculee en ligne par edge_ai.py.
Les echantillons des transitions (3 premieres secondes et derniere seconde d'un
segment) sont exclus de l'entrainement.

Le modele est exporte en JSON lisible (seuils, classe et confiance par feuille)
pour que edge_ai.py n'ait besoin d'aucune bibliotheque a l'execution.
"""

import argparse
import csv
import json
from collections import deque
from pathlib import Path

LABELS = {"5M": "low", "12M": "normal", "18M": "high"}
WINDOW = 3
SKIP_START_S, SKIP_END_S = 3.0, 1.0


def labelled_samples(run_dir):
    """[(thp_dl_ma_mbps, label, obs_epoch)] pour les segments descendants etiquetables."""
    run_dir = Path(run_dir)
    segs = [s for s in csv.DictReader(open(run_dir / "segments.csv"))
            if s["kind"] == "dl" and s["offered"] in LABELS]
    win, out = deque(maxlen=WINDOW), []
    for r in csv.DictReader(open(run_dir / "kpm.csv")):
        if r["mapping_status"] != "ok" or r["DRB.UEThpDl"] == "":
            continue
        win.append(float(r["DRB.UEThpDl"]) / 1000)
        t = float(r["obs_epoch_s"])
        for s in segs:
            if float(s["start_epoch"]) + SKIP_START_S <= t <= float(s["end_epoch"]) - SKIP_END_S:
                out.append((sum(win) / len(win), LABELS[s["offered"]], t))
    return out


def export(tree, classes, node=0):
    t = tree.tree_
    if t.children_left[node] == -1:
        counts = t.value[node][0]
        k = int(counts.argmax())
        return {"leaf": classes[k], "confidence": round(float(counts[k] / counts.sum()), 4),
                "n_train": int(t.n_node_samples[node])}
    return {"feature": "thp_dl_ma_mbps", "threshold": round(float(t.threshold[node]), 4),
            "left": export(tree, classes, t.children_left[node]),
            "right": export(tree, classes, t.children_right[node])}


def main():
    from sklearn.tree import DecisionTreeClassifier, export_text

    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--version", default="dt-v1")
    ap.add_argument("runs", nargs="+")
    a = ap.parse_args()

    data = [s for run in a.runs for s in labelled_samples(run)]
    X, y = [[s[0]] for s in data], [s[1] for s in data]
    clf = DecisionTreeClassifier(max_depth=2, random_state=0).fit(X, y)
    classes = list(clf.classes_)
    thresholds = sorted(float(t) for t in clf.tree_.threshold if t != -2)
    model = {
        "version": a.version, "type": "DecisionTreeClassifier(max_depth=2)",
        "feature": "thp_dl_ma_mbps (moyenne mobile 3 indications de DRB.UEThpDl, Mbit/s)",
        "labels": LABELS, "training_runs": [Path(r).name for r in a.runs],
        "n_train": len(data), "n_per_class": {c: y.count(c) for c in classes},
        "train_accuracy": round(float(clf.score(X, y)), 4),
        "thresholds_mbps": [round(t, 3) for t in thresholds],
        "preprocessing": "lignes mapping_status=ok ; transitions exclues (%.0f s debut, %.0f s fin)" % (
            SKIP_START_S, SKIP_END_S),
        "tree": export(clf, classes),
    }
    Path(a.out).write_text(json.dumps(model, indent=2) + "\n")
    print(export_text(clf, feature_names=["thp_dl_ma_mbps"]))
    print(json.dumps({k: model[k] for k in ("version", "n_train", "n_per_class", "train_accuracy",
                                            "thresholds_mbps")}, indent=2))


if __name__ == "__main__":
    main()
