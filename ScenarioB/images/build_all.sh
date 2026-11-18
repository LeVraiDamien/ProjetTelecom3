#!/usr/bin/env bash
# Scenario B - construit les trois images (aucune n'est fournie par le cours).
# FlexRIC et srsUE d'abord (courts, en parallele), puis OCUDU seul (long, gourmand en RAM).
# Journaux dans build-logs/ (ignore par git).
set -uo pipefail
cd "$(dirname "$0")"
mkdir -p build-logs
JOBS="${JOBS:-4}"

build() {  # build <dossier> <tag> <jobs>
  if docker build --build-arg NUM_JOBS="$3" -t "$2" "$1" > "build-logs/$1.log" 2>&1; then
    echo "OK   $2"
  else
    echo "FAIL $2 (voir build-logs/$1.log)"
  fi
}

build flexric telecom-lab-flexric:1.0 3 &
build srsue   telecom-lab-srsue:1.0   3 &
wait
build ocudu-gnb telecom-lab-ocudu-gnb:1.0 "$JOBS"
docker images --format '{{.Repository}}:{{.Tag}}  {{.Size}}' | grep -E 'flexric|srsue|ocudu'
