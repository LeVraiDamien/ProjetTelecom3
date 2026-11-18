#!/usr/bin/env bash
# Construit (si besoin) et lance le controleur OS-Ken du Scenario A.
# A lancer AVANT Mininet (Phase 4) pour que les switches se connectent tout de suite.
set -euo pipefail
cd "$(dirname "$0")"

IMAGE=telecom-lab-osken:1.0
NAME=scenario-a-osken

docker build -t "$IMAGE" .
docker rm -f "$NAME" >/dev/null 2>&1 || true
# --network host : le controleur ecoute sur 127.0.0.1:6633 de l'hote,
# la ou les switches OVS (qui vivent dans le namespace reseau de l'hote) le cherchent.
docker run -d --name "$NAME" --network host "$IMAGE"

sleep 3
docker ps --filter "name=$NAME" --format '{{.Names}}  {{.Image}}  {{.Status}}'
ss -ltnp 2>/dev/null | grep ':6633 ' || echo "ATTENTION: rien n'ecoute sur 6633"
docker logs "$NAME" 2>&1 | tail -n 15
