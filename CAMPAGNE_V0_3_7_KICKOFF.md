# 🚀 Campagne v0.3.7 — Guide d'exécution

> **Version** : v0.3.7 (tag posé, worktree clean)
> **Protocole** : v2.1 ([PROTOCOLE_VALIDATION_R0_R1_LOKO_V2.md](PROTOCOLE_VALIDATION_R0_R1_LOKO_V2.md))
> **Date prévue** : 2026-07-07
> **Durée estimée** : 4-6h (build + exécution complète)

---

## ✅ Prérequis validés

- [x] Tag v0.3.7 posé (commit b0c959a)
- [x] Worktree clean (CE-1 PASS)
- [x] Triple version identique : tag = pyproject = 0.3.7 (CE-2 PASS)
- [x] Datasets figés vérifiés (CE-4 PASS)
- [x] Intersection train/held-out vide (CE-5 PASS)
- [x] loko-eval installé (CE-6 PASS)

---

## 📋 Checklist d'exécution

### Étape 1 : Build Docker image (~10-15 min)

```bash
# Depuis c:/Users/henri/Projets/loko
docker build -t loko-r0r1-codex:v0.3.7 .
docker images | grep loko-r0r1-codex
```

**Vérifications CE-3** :
```bash
# Digest
docker inspect loko-r0r1-codex:v0.3.7 --format '{{.Id}}' > campaign_digest.txt

# Taille réelle (≤ 1.6 Go par inspect, pas par `docker images`)
docker inspect loko-r0r1-codex:v0.3.7 --format '{{.Size}}' | awk '{print $1/1024/1024/1024 " GB"}'
```

---

### Étape 2 : Création répertoire campagne

```bash
mkdir -p eval/campagne-R0R1/2026-07-07-v0.3.7
cd eval/campagne-R0R1/2026-07-07-v0.3.7
```

---

### Étape 3 : Exécution protocole v2.1

**Mode recommandé** : Suivre le protocole manuellement étape par étape

#### Phase CE (Conditions d'entrée)
Voir [PROTOCOLE_VALIDATION_R0_R1_LOKO_V2.md](PROTOCOLE_VALIDATION_R0_R1_LOKO_V2.md) § 1

- CE-1 : Worktree clean ✓ (déjà validé)
- CE-2 : Tag + triple version ✓ (déjà validé)
- CE-3 : Image build + digest
- CE-4 : Datasets ✓ (déjà validé)
- CE-5 : Intersection vide ✓ (déjà validé)
- CE-6 : loko-eval ✓ (déjà validé)
- CE-7 : Pas de secret LLM (mock ou vraie clé selon test)
- CE-8 : npm ci frontend + npm audit

#### Phase V0 (Build + config)
Voir protocole § 3

- V0-1 : Lint pre-commit (si configuré)
- V0-2 : Tests unitaires (pytest)
- V0-3 : License SPDX check
- V0-4 : npm audit (conteneur Node dédié)
- V0-5 : Image size ≤ 1.6 GB (par inspect)

#### Phase V1 (Runtime R0)
Voir protocole § 4

- V1-1 : Server startup
- V1-2 : Health check
- V1-3 : Session témoin (200 OK)
- V1-4 : **Fail-fast model unavailable** (W1.2 → CRITICAL log au boot attendu)
- V1-5 : Offline mode (--network none)

#### Phase V2 (Training R1.a)
Voir protocole § 5

**Important W3.2** : Cloner bot pour V2-4/V2-5

```bash
# Après V2-1 (training complet)
python tools/clone_bot.py <bot_id> v2-disposable
```

- V2-1 : Training MGEN ≤ 300s
- V2-2 : Niveau 2 services_en_ligne
- V2-3 : Atomicité (kill worker)
- V2-4 : Matrice + advice (**sur bot jetable**)
- V2-5 : Cycle amélioration (**sur bot jetable**, 3-seed CV, critère dual)
- V2-6 : Latence P95 ≤ 50ms

#### Phase V3 (Evaluation R1.b)
Voir protocole § 6

**Important W3** :
- V3-0 : Calibration avec **sélection Pareto** (W3.1)
- V3-1 à V3-6 : Mesure sur **bot campagne V2-1 figé** (PAS le bot jetable V2-5)

```bash
# V3-0 : Calibration 3-axis sweep
loko-eval --bot-dir /data/bots/{campaign_bot_id} --mode sweep \
  --sweep-datasets metier=...,conseiller=...,horsscope=...,pieges=... \
  --out eval/campagne-R0R1/2026-07-07-v0.3.7/sweep/

# La sélection Pareto se fait automatiquement (W3.1)
# Vérifier selection.json pour warnings (coin de grille, etc.)
```

- V3-0 : Calibration Pareto contrainte
- V3-1 : GNG-1 métier (seuil 85%)
- V3-2 : GNG-2 conseiller (seuil 90%)
- V3-3 : GNG-3 hors-scope (seuil 80%, routes directes ≤ 5)
- V3-4 : Pièges (12/15)
- V3-5 : Supprimé (v2.0)
- V3-6 : Reproducibilité
- V3-7 : **NON ENGAGÉ** dans cette campagne (enrichissement W4)

---

## 🎯 Verdict attendu

### R0 (G-0 + G-1) : **PASS PROBABLE**

- **G-0** (V0-1 à V0-5) : PASS attendu (build standard)
- **G-1** (V1-1 à V1-4) : PASS attendu
  - ✅ W1.2 implémenté → V1-4 devrait PASS (CRITICAL log au boot)

### R1 (G-2 + G-3) : **FAIL ATTENDU**

- **G-2** (V2-1 à V2-6) : PASS probable
  - ✅ W3.2/W3.3 implémentés → V2-5 plus robuste (3-seed CV, bot jetable)

- **G-3** (V3-0 à V3-6) : **FAIL ATTENDU** sur seuils GNG
  - **Plateau de référence** (hypothèse W2) : 74% / 86% / 83% (8/15 pièges)
  - **Cibles** : 85% / 90% / 80% (12/15 pièges)
  - **Gap** : +11 pts GNG-1, +4 pts GNG-2, +4 pièges
  - ✅ W3.1 garantit sélection Pareto propre (pas d'artefact coin de grille)
  - ✅ W3.4 embarque dataset_hash + manifest_reference (traçabilité)

### Conséquence attendue

**Verdict global** : **R0+R1 NON VALIDÉS** (échec G-3)

**Mais** : Campagne réussie si elle établit proprement le plateau actuel, sans artefacts méthodologiques.

**Déclenchement V3-7** : Le FAIL G-3 rend V3-7 **obligatoire** (boucle corrective).
→ Exécution W4 complète (enrichissement train) devient nécessaire.

---

## 📊 Après campagne : Analyse verdict

### Si R0 FAIL (G-0 ou G-1)

**Action immédiate** : Identifier et corriger anomalie produit.
- G-0 (build) : Rare, vérifier dependencies ou tests
- G-1 (runtime) : Probable cause V1-4 → vérifier log CRITICAL boot

**Plan** : Corriger → tag v0.3.8 → reprendre campagne depuis V0-1

### Si R1 FAIL sur G-2 (V2-5)

**Vérifier W3.3** : 3-seed CV + critère dual
- Si signal ne réduit toujours pas → FAIL produit réel (chaîne advice)
- Analyser V2-5_comparison.json pour diagnostic

### Si R1 FAIL sur G-3 (attendu)

**C'est normal** — le gap +11/+4 pts nécessite enrichissement train.

**Actions** :
1. Vérifier que V3-0 selection Pareto est propre (pas de warning coin de grille)
2. Confirmer plateau : GNG-1 ~74%, GNG-2 ~86%, GNG-3 ~83%
3. Si régression vs v0.3.5 (74/86/83) → déclencher Plan B W2 (bisect M1/M2/M3)
4. Si plateau confirmé → **lancer W4 complet** (production exemples métier)

---

## 🔄 Prochaines étapes après campagne

### Scénario A : Plateau confirmé (74/86/83)

1. **W4.2-W4.4** : Production ~60-80 exemples réalistes (avec expert MGEN)
   - Utiliser [eval/w4-pattern-analysis/](eval/w4-pattern-analysis/) comme guide
   - Priorités : arret_travail (12 ex), justificatif_droits (12 ex), services_en_ligne (14 ex)

2. **Campagne v0.3.8** : Avec train enrichi (V3-7 itération 1)
   - Objectif : GNG-1 ≥ 85%, GNG-2 ≥ 90%, pièges ≥ 12/15
   - Si atteint → **R0+R1 VALIDÉS** ✓

3. **Ouverture R2-R9** : Phases suivantes de validation produit

### Scénario B : Régression détectée vs v0.3.5

1. **Bisect M1/M2/M3** : Identifier commit régressif dans v0.3.6
2. **Corriger** + tag v0.3.8-fix
3. **Reprendre campagne** avec correction

---

## 📁 Artefacts attendus

À la fin de la campagne, `eval/campagne-R0R1/2026-07-07-v0.3.7/` contiendra :

```
CE_preflight.txt
CE-1_*.txt (git status, branch, describe)
CE-2_*.txt (tag, version)
CE-3_*.json (image inspect, size)
...
V0-1_*.txt
...
V2-1_train_run.txt
V2-1_manifest.json
V2-4_*.json (bot jetable)
V2-5_*.json (bot jetable, 3-seed CV)
...
V3-0_selection.json (Pareto)
sweep/sweep_3axis.csv
V3-1_metier/report.json (avec dataset_hash, manifest_reference)
V3-2_conseiller/report.json
V3-3_horsscope/report.json
V3-4_pieges/report.json
V3-6_reproducibility.json
V3_summary.json
RAPPORT_VALIDATION_R0_R1_LOKO_V3.md (final)
```

---

## 🛠️ Support et outils

- **Protocole complet** : [PROTOCOLE_VALIDATION_R0_R1_LOKO_V2.md](PROTOCOLE_VALIDATION_R0_R1_LOKO_V2.md)
- **Hypothèse plateau** : [W2_hypothese_actee.md](W2_hypothese_actee.md)
- **Clone bot** : `python tools/clone_bot.py <bot_id> <suffix>`
- **Pattern analysis** : [eval/w4-pattern-analysis/](eval/w4-pattern-analysis/)
- **Preflight** : `python tools/preflight.py --image loko-r0r1-codex:v0.3.7 --campaign-dir <dir>`

---

**Prêt à démarrer la campagne ?**

```bash
# Build image
docker build -t loko-r0r1-codex:v0.3.7 .

# Create campaign dir
mkdir -p eval/campagne-R0R1/2026-07-07-v0.3.7

# Follow protocol step by step
# PROTOCOLE_VALIDATION_R0_R1_LOKO_V2.md
```

**Bonne chance !** 🚀
