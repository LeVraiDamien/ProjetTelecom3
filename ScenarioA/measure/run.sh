#!/usr/bin/env bash
# Scenario A - lance un run complet (phases 1 a 8) et garde la console.
# Usage : ./run.sh [options de run_experiments.py, ex. --rate 80M]
# Prerequis : controleur demarre (../controller/run_controller.sh).
set -euo pipefail
cd "$(dirname "$0")"

RUN_ID="run-$(date -u +%Y%m%dT%H%M%SZ)"
OUT="../experiments/$RUN_ID"
mkdir -p "$OUT"

# Chemins absolus : permet une regle sudoers NOPASSWD ciblee sur ce projet.
sudo /usr/bin/python3 "$PWD/run_experiments.py" --run-id "$RUN_ID" "$@" 2>&1 | tee "$OUT/console.log"
echo "RUN_ID=$RUN_ID"

# Phase 9 : analyse automatique (sans root)
python3 analyze.py "$OUT" > /dev/null && echo "ANALYSE : toutes les verifications PASS" \
  || echo "ANALYSE : au moins une verification FAIL"
echo "Rapport : $OUT/analysis_report.md"
