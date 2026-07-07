#!/usr/bin/env bash
# W2 — Contre-épreuve du plateau (mesure pré-contamination V2-5, seuils v0.3.5)
#
# Objectif : Mesurer le vrai plateau avant de décider quoi que ce soit
# - Bot V2-1 SANS l'ajout V2-5 (train.csv propre, 125 exemples)
# - Seuils v0.3.5 : haut 0.85 / bas 0.30 / écart 0.05
# - Comparaison au triplet v0.3.5 : 74% / 85.6% / 83% (pièges 8/15)
#
# Durée : ~1h
# Usage : ./tools/w2_contre_epreuve.sh

set -euo pipefail

# Configuration
TAG="${TAG:-v0.3.6}"  # Utiliser l'image v0.3.6 existante
IMAGE="loko-r0r1-codex:${TAG}"
VOLUME="loko-w2-test"
CONTAINER="loko-w2"
PORT="18002"
OUT_DIR="eval/w2-contre-epreuve-$(date +%Y-%m-%d-%H%M%S)"
DATA_DIR="/tmp/loko-w2"

# Seuils v0.3.5 (référence de comparaison)
SEUIL_HAUT="0.85"
SEUIL_BAS="0.30"
SEUIL_ECART="0.05"

# Baseline v0.3.5 attendue (depuis feuille de route)
BASELINE_GNG1="74"
BASELINE_GNG2="85.6"
BASELINE_GNG3="83"
BASELINE_PIEGES="8"

echo "=== W2 Contre-épreuve du plateau ==="
echo "Image: ${IMAGE}"
echo "Seuils v0.3.5: haut=${SEUIL_HAUT} / bas=${SEUIL_BAS} / écart=${SEUIL_ECART}"
echo "Baseline attendue: GNG-1=${BASELINE_GNG1}% / GNG-2=${BASELINE_GNG2}% / GNG-3=${BASELINE_GNG3}% / Pièges=${BASELINE_PIEGES}/15"
echo ""

# Nettoyage préalable
echo "→ Nettoyage préalable..."
docker stop ${CONTAINER} 2>/dev/null || true
docker rm ${CONTAINER} 2>/dev/null || true
docker volume rm ${VOLUME} 2>/dev/null || true

# Création volume et démarrage conteneur
echo "→ Création volume ${VOLUME}..."
docker volume create ${VOLUME}

echo "→ Démarrage conteneur ${CONTAINER}..."
ADMIN_TOKEN=$(openssl rand -hex 24)

docker run -d \
  --name ${CONTAINER} \
  -e LOKO_ADMIN_TOKEN="${ADMIN_TOKEN}" \
  -e RAGKIT_MODE=server \
  -e LOKO_DATA_DIR=/data \
  -v ${VOLUME}:/data \
  -p 127.0.0.1:${PORT}:8000 \
  ${IMAGE}

echo "→ Attente démarrage serveur (health check)..."
for i in {1..30}; do
  if curl -sf http://127.0.0.1:${PORT}/health >/dev/null 2>&1; then
    echo "   Serveur prêt après ${i}s"
    break
  fi
  if [ $i -eq 30 ]; then
    echo "ERREUR: Serveur n'a pas démarré en 30s"
    docker logs ${CONTAINER}
    exit 1
  fi
  sleep 1
done

# Préparation environnement local
mkdir -p "${OUT_DIR}"
echo "→ Répertoire artefacts: ${OUT_DIR}"

# Fonction utilitaire : API call avec token
function api_call() {
  local method="$1"
  local path="$2"
  local data="${3:-}"

  if [ -z "$data" ]; then
    curl -sf -X ${method} \
      -H "Authorization: Bearer ${ADMIN_TOKEN}" \
      "http://127.0.0.1:${PORT}${path}"
  else
    curl -sf -X ${method} \
      -H "Authorization: Bearer ${ADMIN_TOKEN}" \
      -H "Content-Type: application/json" \
      -d "${data}" \
      "http://127.0.0.1:${PORT}${path}"
  fi
}

# 1. Création bot avec configuration minimale (depuis train.csv)
echo ""
echo "→ W2.1: Création bot de contre-épreuve (train.csv propre, 125 exemples)..."

# Lire train.csv et construire la configuration bot
# Note: Pour simplifier, on utilise une config minimale avec exemples de train.csv
# Le bot sera créé puis on ajoutera les exemples via l'API

BOT_CONFIG=$(cat <<'EOF'
{
  "name": "W2 Contre-épreuve",
  "channel": "both",
  "language": "fr",
  "tone_profile": "neutre",
  "intents": [
    {
      "id": "arret_travail",
      "label": "Arrêt de travail",
      "definition": "Demande liée à un arrêt de travail, congé maladie ou invalidité",
      "examples": [],
      "sub_motifs": [],
      "is_system": false
    },
    {
      "id": "changement_coordonnees",
      "label": "Changement de coordonnées",
      "definition": "Modification des coordonnées personnelles",
      "examples": [],
      "sub_motifs": [],
      "is_system": false
    },
    {
      "id": "cotisations",
      "label": "Cotisations",
      "definition": "Questions sur les cotisations mutuelle/prévoyance",
      "examples": [],
      "sub_motifs": [],
      "is_system": false
    },
    {
      "id": "justificatif_droits",
      "label": "Justificatif de droits",
      "definition": "Demande de document attestant des droits ou de la couverture",
      "examples": [],
      "sub_motifs": [],
      "is_system": false
    },
    {
      "id": "resiliation",
      "label": "Résiliation",
      "definition": "Résiliation du contrat mutuelle ou prévoyance",
      "examples": [],
      "sub_motifs": [],
      "is_system": false
    },
    {
      "id": "services_en_ligne",
      "label": "Services en ligne",
      "definition": "Besoin lié à l'espace personnel en ligne ou à l'application",
      "examples": [],
      "sub_motifs": [],
      "is_system": false
    },
    {
      "id": "teletransmission_noemie",
      "label": "Télétransmission Noemie",
      "definition": "Demande sur la télétransmission Noemie",
      "examples": [],
      "sub_motifs": [],
      "is_system": false
    },
    {
      "id": "hors_perimetre",
      "label": "Hors périmètre",
      "definition": "Demande hors du périmètre des intentions gérées",
      "examples": [],
      "sub_motifs": [],
      "is_system": true
    },
    {
      "id": "demande_conseiller",
      "label": "Demande conseiller",
      "definition": "Demande explicite de parler à un conseiller ou un humain",
      "examples": [],
      "sub_motifs": [],
      "is_system": true
    }
  ],
  "journey": {
    "seuil_haut": ${SEUIL_HAUT},
    "seuil_bas": ${SEUIL_BAS},
    "seuil_ecart_clarification": ${SEUIL_ECART},
    "seuil_sous_motif": 0.6,
    "max_clarifications": 1,
    "max_demandes": 5,
    "timeout_inactivite_s": 300,
    "retrieval_min_score": 0.35,
    "retrieval_min_chunks": 2
  },
  "training": {
    "num_iterations": 5,
    "num_epochs": 1,
    "batch_size": 16
  }
}
EOF
)

CREATE_RESPONSE=$(api_call POST /api/bot/ "${BOT_CONFIG}")
BOT_ID=$(echo "${CREATE_RESPONSE}" | jq -r '.bot_id')
echo "   Bot créé: ${BOT_ID}"
echo "${CREATE_RESPONSE}" | jq '.' > "${OUT_DIR}/bot_create_response.json"

# Charger exemples depuis train.csv dans le bot
echo "→ Chargement des exemples depuis train.csv..."

# Compte exemples par intent
echo "   Distribution train.csv:"
tail -n +2 eval/datasets/train.csv | cut -d',' -f2 | sort | uniq -c

# Copier train.csv dans le conteneur et charger via script Python interne
# (Alternative: itérer sur CSV et faire POST /api/bot/{bot_id}/examples pour chaque ligne)
# Pour simplifier, on va copier train.csv dans le conteneur et charger directement

docker cp eval/datasets/train.csv ${CONTAINER}:/tmp/train.csv

# Script Python pour charger les exemples
docker exec ${CONTAINER} python3 -c "
import csv
import json
import requests

bot_id = '${BOT_ID}'
token = '${ADMIN_TOKEN}'
headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

with open('/tmp/train.csv', 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        text = row['text']
        intent = row['intent']
        payload = {'intent_id': intent, 'text': text, 'from_production': False}
        r = requests.post(f'http://localhost:8000/api/bot/{bot_id}/examples',
                          headers=headers, json=payload)
        if r.status_code != 200:
            print(f'WARN: Failed to add example: {text[:50]}... to {intent}')

print('Exemples chargés depuis train.csv')
"

echo "   Exemples chargés"

# 2. Entraînement (V2-1 équivalent)
echo ""
echo "→ W2.2: Entraînement bot (V2-1 équivalent)..."

TRAIN_REQUEST='{"base_model": "sentence-transformers/paraphrase-MiniLM-L3-v2", "run_evaluation": true}'
TRAIN_RESPONSE=$(api_call POST "/api/bot/${BOT_ID}/train" "${TRAIN_REQUEST}")
echo "${TRAIN_RESPONSE}" | jq '.'

echo "   Polling status entraînement..."
START_TIME=$(date +%s)
while true; do
  STATUS_RESPONSE=$(api_call GET "/api/bot/${BOT_ID}/train/status")
  STATUS=$(echo "${STATUS_RESPONSE}" | jq -r '.status')
  STEP=$(echo "${STATUS_RESPONSE}" | jq -r '.step')
  ELAPSED=$(($(date +%s) - START_TIME))

  echo "   [${ELAPSED}s] Status: ${STATUS} / Step: ${STEP}"

  if [ "${STATUS}" = "completed" ]; then
    echo "   ✓ Entraînement terminé en ${ELAPSED}s"
    break
  elif [ "${STATUS}" = "failed" ]; then
    echo "   ✗ ERREUR: Entraînement échoué"
    echo "${STATUS_RESPONSE}" | jq '.'
    exit 1
  fi

  if [ $ELAPSED -gt 600 ]; then
    echo "   ✗ TIMEOUT: Entraînement > 10 minutes"
    exit 1
  fi

  sleep 5
done

# Récupérer le rapport d'entraînement
TRAIN_REPORT=$(api_call GET "/api/bot/${BOT_ID}/train/report")
echo "${TRAIN_REPORT}" | jq '.' > "${OUT_DIR}/train_report.json"

TRAIN_TIME=$(echo "${TRAIN_REPORT}" | jq -r '.profile.total_s // "N/A"')
ACCURACY=$(echo "${TRAIN_REPORT}" | jq -r '.evaluation.accuracy // "N/A"')
echo "   Durée: ${TRAIN_TIME}s / Accuracy CV: ${ACCURACY}"

# 3. Évaluation V3 avec seuils v0.3.5
echo ""
echo "→ W2.3: Évaluation V3-1 → V3-4 (seuils v0.3.5)..."

# Récupérer le bot_dir dans le conteneur
BOT_DIR="/data/bots/${BOT_ID}"

# V3-1: GNG-1 (heldout_metier.csv)
echo "   V3-1 (GNG-1)..."
docker exec ${CONTAINER} loko-eval \
  --bot-dir ${BOT_DIR} \
  --dataset /app/eval/datasets/heldout_metier.csv \
  --mode decision \
  --out /tmp/w2-v3-1 > "${OUT_DIR}/v3-1_console.txt" 2>&1 || true

docker cp ${CONTAINER}:/tmp/w2-v3-1/report.json "${OUT_DIR}/v3-1_report.json"
GNG1=$(jq -r '.decision_accuracy // "N/A"' "${OUT_DIR}/v3-1_report.json")
echo "      GNG-1: ${GNG1}"

# V3-2: GNG-2 (heldout_conseiller.csv)
echo "   V3-2 (GNG-2)..."
docker exec ${CONTAINER} loko-eval \
  --bot-dir ${BOT_DIR} \
  --dataset /app/eval/datasets/heldout_conseiller.csv \
  --mode decision \
  --out /tmp/w2-v3-2 > "${OUT_DIR}/v3-2_console.txt" 2>&1 || true

docker cp ${CONTAINER}:/tmp/w2-v3-2/report.json "${OUT_DIR}/v3-2_report.json"
GNG2=$(jq -r '.decision_accuracy // "N/A"' "${OUT_DIR}/v3-2_report.json")
echo "      GNG-2: ${GNG2}"

# V3-3: GNG-3 (heldout_horsscope.csv)
echo "   V3-3 (GNG-3)..."
docker exec ${CONTAINER} loko-eval \
  --bot-dir ${BOT_DIR} \
  --dataset /app/eval/datasets/heldout_horsscope.csv \
  --mode decision \
  --out /tmp/w2-v3-3 > "${OUT_DIR}/v3-3_console.txt" 2>&1 || true

docker cp ${CONTAINER}:/tmp/w2-v3-3/report.json "${OUT_DIR}/v3-3_report.json"
GNG3=$(jq -r '.decision_accuracy // "N/A"' "${OUT_DIR}/v3-3_report.json")
ROUTES_DIRECTES=$(jq -r '.direct_business_routes // "N/A"' "${OUT_DIR}/v3-3_report.json")
echo "      GNG-3: ${GNG3} / Routes directes: ${ROUTES_DIRECTES}"

# V3-4: Pièges
echo "   V3-4 (Pièges)..."
docker exec ${CONTAINER} loko-eval \
  --bot-dir ${BOT_DIR} \
  --dataset /app/eval/datasets/pieges.csv \
  --mode pieges \
  --out /tmp/w2-v3-4 > "${OUT_DIR}/v3-4_console.txt" 2>&1 || true

docker cp ${CONTAINER}:/tmp/w2-v3-4/report.json "${OUT_DIR}/v3-4_report.json"
PIEGES_CORRECT=$(jq -r '.pieges_correct // "N/A"' "${OUT_DIR}/v3-4_report.json")
PIEGES_TOTAL=$(jq -r '.pieges_total // "N/A"' "${OUT_DIR}/v3-4_report.json")
echo "      Pièges: ${PIEGES_CORRECT}/${PIEGES_TOTAL}"

# 4. Synthèse et analyse
echo ""
echo "=== SYNTHÈSE W2 ==="
echo ""
echo "Mesures contre-épreuve (seuils v0.3.5):"
echo "  GNG-1: ${GNG1}  (baseline v0.3.5: ${BASELINE_GNG1}%)"
echo "  GNG-2: ${GNG2}  (baseline v0.3.5: ${BASELINE_GNG2}%)"
echo "  GNG-3: ${GNG3}  (baseline v0.3.5: ${BASELINE_GNG3}%)"
echo "  Pièges: ${PIEGES_CORRECT}/${PIEGES_TOTAL}  (baseline v0.3.5: ${BASELINE_PIEGES}/15)"
echo ""
echo "Analyse:"

# Conversion pour comparaison (enlever % et convertir en float)
GNG1_NUM=$(echo "${GNG1}" | sed 's/%//' | awk '{printf "%.1f", $1}')
GNG2_NUM=$(echo "${GNG2}" | sed 's/%//' | awk '{printf "%.1f", $1}')
GNG3_NUM=$(echo "${GNG3}" | sed 's/%//' | awk '{printf "%.1f", $1}')

# Comparaison (tolérance ±2%)
GNG1_DELTA=$(awk "BEGIN {printf \"%.1f\", ${GNG1_NUM} - ${BASELINE_GNG1}}")
GNG2_DELTA=$(awk "BEGIN {printf \"%.1f\", ${GNG2_NUM} - ${BASELINE_GNG2}}")
GNG3_DELTA=$(awk "BEGIN {printf \"%.1f\", ${GNG3_NUM} - ${BASELINE_GNG3}}")
PIEGES_DELTA=$((${PIEGES_CORRECT} - ${BASELINE_PIEGES}))

echo "  Δ GNG-1: ${GNG1_DELTA} pts"
echo "  Δ GNG-2: ${GNG2_DELTA} pts"
echo "  Δ GNG-3: ${GNG3_DELTA} pts"
echo "  Δ Pièges: ${PIEGES_DELTA}"
echo ""

# Verdict
if awk "BEGIN {exit (${GNG1_DELTA} > -2 && ${GNG1_DELTA} < 2) ? 0 : 1}" && \
   awk "BEGIN {exit (${GNG2_DELTA} > -2 && ${GNG2_DELTA} < 2) ? 0 : 1}" && \
   awk "BEGIN {exit (${GNG3_DELTA} > -2 && ${GNG3_DELTA} < 2) ? 0 : 1}"; then
  echo "LECTURE: Chiffres ≈ v0.3.5 → Régression v0.3.6 = ARTEFACT confirmé"
  echo "  - Plateau confirmé ~74/86/83"
  echo "  - W4 vise +11 pts GNG-1, +4 pts GNG-2 depuis ce plateau"
  echo "  - Causes artefact: coin de sweep (W3.1) + contamination V2-5 (W3.2)"
  VERDICT="plateau"
else
  echo "LECTURE: Chiffres ≠ v0.3.5 → Régression v0.3.6 RÉELLE"
  echo "  - SUSPENDRE W4 immédiatement"
  echo "  - Bissecter changements M1/M2/M3 entre v0.3.5 et v0.3.6"
  echo "  - Corriger la régression avant de continuer"
  VERDICT="regression"
fi

# Écrire rapport final
cat > "${OUT_DIR}/W2_contre_epreuve.md" <<EOREPORT
# W2 — Contre-épreuve du plateau

**Date** : $(date +%Y-%m-%d\ %H:%M:%S)
**Bot ID** : ${BOT_ID}
**Image** : ${IMAGE}
**Seuils** : haut=${SEUIL_HAUT} / bas=${SEUIL_BAS} / écart=${SEUIL_ECART}

## Résultats mesurés

| Métrique | Mesuré | Baseline v0.3.5 | Δ |
|----------|--------|-----------------|---|
| GNG-1    | ${GNG1} | ${BASELINE_GNG1}% | ${GNG1_DELTA} pts |
| GNG-2    | ${GNG2} | ${BASELINE_GNG2}% | ${GNG2_DELTA} pts |
| GNG-3    | ${GNG3} | ${BASELINE_GNG3}% | ${GNG3_DELTA} pts |
| Pièges   | ${PIEGES_CORRECT}/${PIEGES_TOTAL} | ${BASELINE_PIEGES}/15 | ${PIEGES_DELTA} |

## Lecture

**Verdict** : ${VERDICT}

$(if [ "${VERDICT}" = "plateau" ]; then
  echo "La régression observée en v0.3.6 est un **artefact méthodologique**."
  echo ""
  echo "- Le plateau réel est ~${GNG1_NUM}/${GNG2_NUM}/${GNG3_NUM}"
  echo "- Causes de l'artefact:"
  echo "  - V3-0 seuils : coin de grille (haut 0.90 / bas 0.30 / écart 0.05)"
  echo "  - V2-5 : contamination (6 exemples touchant \`hors_perimetre\` avant V3)"
  echo "- **W4 part de ce plateau** et vise +11 pts GNG-1, +4 pts GNG-2"
else
  echo "La régression observée en v0.3.6 est **RÉELLE**."
  echo ""
  echo "**Action immédiate** : SUSPENDRE W4"
  echo ""
  echo "1. Bissecter les changements M1/M2/M3 entre v0.3.5 et v0.3.6"
  echo "2. Identifier la cause de la dégradation"
  echo "3. Corriger et revenir à W2 pour confirmer le retour au plateau"
fi)

## Artefacts

- Train report : \`train_report.json\`
- V3-1 (GNG-1) : \`v3-1_report.json\`
- V3-2 (GNG-2) : \`v3-2_report.json\`
- V3-3 (GNG-3) : \`v3-3_report.json\`
- V3-4 (Pièges) : \`v3-4_report.json\`
EOREPORT

echo ""
echo "Rapport complet: ${OUT_DIR}/W2_contre_epreuve.md"

# Nettoyage
echo ""
echo "→ Nettoyage conteneur ${CONTAINER}..."
docker stop ${CONTAINER}
docker rm ${CONTAINER}
docker volume rm ${VOLUME}

echo ""
echo "✓ W2 terminé — Voir ${OUT_DIR}/"
