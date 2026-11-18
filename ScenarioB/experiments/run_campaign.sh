#!/usr/bin/env bash
# Scenario B - Phase 10 : campagne complete d'experiences (environ 15 minutes).
#   1. deux runs d'entrainement (xApp KPM seule)  -> arbre de decision dt-v1
#   2. trois repetitions 5/12/18 Mbit/s avec les trois xApps (nouveaux runs = evaluation)
#   3. saturation descendante, montee/descente de charge, deux runs montants
# Prerequis : ../ran-up.sh. Usage : ./run_campaign.sh [prefixe]
set -euo pipefail
cd "$(dirname "$0")"
P="${1:-c1}"
REF="idle:10,dl:5M:25,idle:6,dl:12M:25,idle:6,dl:18M:25,idle:6"

for i in 1 2; do ./run_scenario.py --run-id "$P-train-0$i" --apps kpm --plan "$REF"; done

docker run --rm -u "$(id -u):$(id -g)" -v "$PWD/..":/work -w /work/xapps/edge_ai telecom-lab-p3-ai:1.0 \
  python train_tree.py --out model/model.json --version "dt-v1-$P" \
  "/work/experiments/$P-train-01" "/work/experiments/$P-train-02" | tee "$P-train-report.txt"

for i in 1 2 3; do ./run_scenario.py --run-id "$P-eval-0$i" --apps kpm,ai,rm --plan "$REF"; done
./run_scenario.py --run-id "$P-saturation" --apps kpm,ai,rm --plan "idle:8,dl:25M:20,idle:6,dl:32M:20,idle:6,dl:40M:20,idle:8"
./run_scenario.py --run-id "$P-ramp" --apps kpm,ai,rm \
  --plan "idle:6,dl:5M:12,dl:12M:12,dl:18M:12,dl:32M:12,dl:18M:12,dl:12M:12,dl:5M:12,idle:8"
for i in 1 2; do
  ./run_scenario.py --run-id "$P-uplink-0$i" --apps kpm,ai,rm \
    --plan "idle:6,ul:1M:15,idle:5,ul:2M:15,idle:5,ul:3M:15,idle:5,ul:5M:15,idle:6"
done
echo "CAMPAGNE TERMINEE : $P"
