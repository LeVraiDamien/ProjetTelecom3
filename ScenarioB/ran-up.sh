#!/usr/bin/env bash
# Scenario B - (re)demarre le RAN dans le bon ordre : RIC -> gNB -> UE.
# La radio ZeroMQ est un echange requete/reponse : si un seul des deux cotes
# redemarre, l'autre reste bloque. On recree donc toujours gNB ET UE ensemble,
# et l'UE seulement une fois le gNB connecte a l'AMF et au RIC.
set -euo pipefail
cd "$(dirname "$0")"
C=./p3-compose.sh

$C up -d --no-deps p3-flexric p3-dn-endpoint 2>&1 | grep -iE "error" || true
$C rm -sf p3-srsue p3-gnb >/dev/null 2>&1
$C up -d --no-deps p3-gnb 2>&1 | grep -iE "error" || true
echo -n "attente du gNB (NG setup + E2 setup) "
for i in $(seq 1 30); do
  if docker logs project3-ocudu-gnb 2>&1 | grep -q "gNB started"; then break; fi
  echo -n "."; sleep 1
done
echo; sleep 3
$C up -d --no-deps p3-srsue 2>&1 | grep -iE "error" || true
echo -n "attente de la session PDU "
for i in $(seq 1 60); do
  if docker logs project3-srsue 2>&1 | grep -q "PDU Session Establishment successful"; then echo " OK"; break; fi
  echo -n "."; sleep 1
done
docker logs project3-srsue 2>&1 | grep -E "Random Access|RRC Connected|PDU Session|Registration" || true
# srsUE ne pose pas de route par defaut : tout le trafic de ue1 passe par la session PDU.
docker exec project3-srsue ip netns exec ue1 ip route replace default via 10.45.0.1 dev tun_srsue 2>&1 || true
docker exec project3-srsue ip netns exec ue1 ip -br a show tun_srsue 2>&1 || true
docker exec project3-srsue ip netns exec ue1 ip route 2>&1 || true
