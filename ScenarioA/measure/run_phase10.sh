#!/usr/bin/env bash
# Scenario A - Phase 10 : classification + politique (modes monitor puis enforce).
# Prerequis : image telecom-lab-osken:1.0 construite (../controller/run_controller.sh).
set -euo pipefail
cd "$(dirname "$0")"

RUN_ID="p10-$(date -u +%Y%m%dT%H%M%SZ)"
OUT="../experiments/$RUN_ID"
mkdir -p "$OUT"

sudo /usr/bin/python3 "$PWD/run_phase10.py" --run-id "$RUN_ID" "$@" 2>&1 | tee "$OUT/console.log"
echo "RUN_ID=$RUN_ID"

python3 analyze_phase10.py "$OUT" > /dev/null && echo "ANALYSE : toutes les verifications PASS" \
  || echo "ANALYSE : au moins une verification FAIL"
echo "Rapport : $OUT/analysis_report.md"
