#!/usr/bin/env bash
# docker compose sur le coeur 5G existant + les ajouts du Projet 2 (dn-net) + ceux du Projet 3.
# Se place dans le dossier du coeur (le nom de projet Compose et ./config en dependent).
# Exemples : ./p3-compose.sh config -q      ./p3-compose.sh up -d amf smf upf
set -euo pipefail

P3_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
P2_DIR="${P2_DIR:-$HOME/ProjetTelecom2}"
CORE_DIR="${CORE_DIR:-$HOME/openverso-images/docs/open5gs-and-ueransim}"
P3_UID="$(id -u)"; P3_GID="$(id -g)"
export P3_DIR P2_DIR P3_UID P3_GID

cd "$CORE_DIR"
exec docker compose -p open5gs-and-ueransim \
  -f ngc.yaml -f gnb1.yaml \
  -f "$P2_DIR/compose/p2-core.yaml" \
  -f "$P3_DIR/compose/p3-core.yaml" \
  "$@"
