# Plan d'exécution global — Validation finale R0+R1

> **Version** : 1.0 — 6 juillet 2026
> **Base** : [FEUILLE_DE_ROUTE_VALIDATION_FINALE_R0_R1_LOKO.md](FEUILLE_DE_ROUTE_VALIDATION_FINALE_R0_R1_LOKO.md)
> **État de départ** : Campagne v0.3.6 — R0+R1 NON VALIDÉS (rapport v2)
> **Objectif** : R0+R1 VALIDÉS → ouverture R2–R9

---

## Vue d'ensemble — Séquencement et dépendances

```
┌─────────────────────────────────────────────────────────────┐
│  PHASE 0 : DIAGNOSTIC (W2) — ~1h — BLOQUANT POUR LE RESTE   │
│  └─> Mesurer le vrai plateau (contamination V2-5 ?)         │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  PHASE 1 : CORRECTIONS RAPIDES (W1 + W3) — ~1 jour          │
│  ├─> W1 : R0 soldé (worktree + log CRITICAL)                │
│  └─> W3 : Protocole v2.1 (Pareto, bot jetable, hash natif)  │
│       (W1 et W3 peuvent s'exécuter EN PARALLÈLE)             │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  PHASE 2 : ENRICHISSEMENT TRAIN (W4) — 2-4 jours            │
│  ├─> W4.1 : Analyse patterns d'erreur                       │
│  ├─> W4.2 : Production exemples réalistes (AVEC MÉTIER)     │
│  └─> W4.3 : Tag par pattern + validation                    │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  PHASE 3 : CAMPAGNE v0.3.7 — ½-1 jour                       │
│  └─> Protocole v2.1 complet avec train enrichi              │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
                    ┌───────┴────────┐
                    │                │
                 PASS              FAIL
                    │                │
                    ▼                ▼
            ┌───────────┐    ┌──────────────┐
            │ R0+R1 OK  │    │ Itération 2  │
            │ R2-R9     │    │ ou W5        │
            └───────────┘    └──────────────┘
```

**Durée totale estimée** : 4-7 jours (hors décision métier W5 si nécessaire)

---

## PHASE 0 : W2 — Contre-épreuve du plateau (PRIORITAIRE)

**Durée** : ~1 heure
**Pourquoi en premier** : Toutes les décisions de W4 dépendent de savoir si le plateau est à 74/86/83 (v0.3.5) ou 72/82/72 (v0.3.6 régressé).

### Tâches

| # | Tâche | Effort | Artefact |
|---|---|---:|---|
| W2.1 | Reconstruire bot V2-1 **sans** l'ajout V2-5 (retour au train pré-contamination) | 15 min | Bot propre v0.3.5-like |
| W2.2 | Rejouer V3-1→V3-4 aux seuils par défaut de v0.3.5 (haut 0.85 / bas 0.30 / écart 0.05) | 30 min | 4 reports GNG |
| W2.3 | Comparer au triplet v0.3.5 et acter la lecture | 15 min | `W2_contre_epreuve.md` |

### Critères de décision

- **Si chiffres ≈ v0.3.5 (74/86/83)** → Régression = artefact. Plateau confirmé. W4 vise +11 pts GNG-1, +4 pts GNG-2.
- **Si chiffres ≈ v0.3.6 (72/82/72)** → Régression réelle. **SUSPENDRE W4**. Bissecter M1/M2/M3, corriger, puis revenir.

### Livrable

Document `W2_contre_epreuve.md` archivé avec :
- Triplet mesuré GNG-1 / GNG-2 / GNG-3
- Pièges
- Lecture actée : plateau ou régression
- Implications pour W4 (cible de gain)

---

## PHASE 1 : W1 + W3 — Corrections rapides (~1 jour, parallélisable)

### W1 — Solder R0 (< 1h)

**Bloque** : G-1 (éliminatoire)

| # | Tâche | Fichiers concernés | DoD |
|---|---|---|---|
| W1.1 | Committer réorganisation documentaire (5 suppressions) + améliorer preflight CE-1 | `.md`, `tools/preflight_validation.sh` | `git describe --tags --dirty` == tag exact, `git status --porcelain` vide |
| W1.2 | Ajouter log `CRITICAL` au boot serveur pour chaque bot dont le modèle ne charge pas | `loko/server/*.py` (boot) | Log visible au démarrage, sans chemin disque |
| W1.3 | Rejouer V1-4 tel quel | Test | 4/4 attendus PASS → **G-1 PASS** |

**Risques** : Aucun (corrections bornées, comportement fonctionnel déjà démontré)

---

### W3 — Protocole v2.1 (~½ jour)

**Bloque** : G-2, G-3 (mesures honnêtes)

| # | Tâche | Fichiers concernés | Effort | DoD |
|---|---|---|---:|---|
| W3.1 | Implémenter sélection Pareto contrainte dans `loko-eval` | `loko-eval/select.py` | 3-4h | Filtrage GNG-3≥80 + routes≤5, puis max lexico GNG-1/GNG-2/pièges ; frontière Pareto exportée ; garde-fou bord de grille |
| W3.2 | Configurer bot jetable pour V2-4/V2-5 (clone du bot campagne) | `eval/campagne-R0R1/setup.sh` | 30 min | V2-4/V2-5 ne contaminent plus le bot de mesure V3 |
| W3.3 | V2-5 : critère 3-seeds CV + ciblage advice | `loko-eval/v2_5.py` | 2h | Réduction sur ≥1 signal, moyenné 3 seeds, exemples depuis advice |
| W3.4 | Hash dataset + manifeste natifs dans `report.json` | `loko-eval/report.py` | 1h | Plus besoin de sidecar `V3_summary.json` |
| W3.5 | Publier protocole v2.1 avec amendements W3 | `PROTOCOLE_*.md`, annexe C | 1h | Version actée, diff W3.1→W3.4 documenté |

**Risques** :
- W3.1 demande ½ journée de dev + tests ; c'est le gros morceau de W3
- V2-5 devient plus exigeant (3 seeds) mais plus honnête

---

## PHASE 2 : W4 — L'itération V3-7 réelle (2-4 jours)

**Bloque** : G-3 (le verrou final)
**Dépend de** : W2 (lecture du plateau acté)

### W4.1 — Analyse patterns d'erreur (½ jour)

**Matière première disponible** :
- `V3-1_errors_classified.csv` (28 erreurs classées)
- Erreurs GNG-2 (rejets au lieu d'escalade conseiller)
- 9 commentaires pièges (v0.3.6)

**Synthèse à produire** (cf. roadmap §4.1) :

| Pattern | Exemples sources | Volume cible |
|---|---|---:|
| Frontière `services_en_ligne` ↔ `changement_coordonnees` | T01/T02/T15 + faux rejets | +10-15 exemples/classe |
| `demande_conseiller` indirect | GNG-2 (« parler à quelqu'un ») | +12-15 exemples |
| Bande clarification | T04/T05/T06 (cotisations/justificatifs) | +8-10 exemples |
| Faux rejets GNG-1 | Verbatims réels trop éloignés du train propre | +10-12 exemples/classe |

**Livrable** : `W4_1_patterns_erreur.md` avec répartition par classe et pattern.

---

### W4.2 — Production exemples réalistes (1-2 jours AVEC MÉTIER)

**Règle absolue** : Les held-out ne sont **JAMAIS** consultés. On travaille depuis les *patterns* de W4.1, pas les verbatims d'évaluation.

**Volume cible** : Train ~125 → ~230-270 exemples (~25-30/classe)

**Nature** : Verbatims **réalistes**
- Tournures orales (« bonjour, alors voilà, en fait… »)
- Fautes courantes (« j'ai changer », « elle à dit »)
- Formulations indirectes (« on peut me rappeler ? » pour `demande_conseiller`)
- Contexte parasite

**Processus** :
1. Réunion métier : présenter W4.1, expliquer les 4 patterns
2. Rédaction collaborative : métier dicte, ingénierie tag
3. Validation croisée : chaque exemple relu par 2 personnes
4. Tag pattern : chaque ligne du CSV porte `pattern=frontiere_services_coords` etc.

**Livrable** : `train_enrichi_v037.csv` avec colonnes `text`, `label`, `pattern`, `seed`

---

### W4.3 — Tag et validation (½ jour)

| # | Tâche | DoD |
|---|---|---|
| 1 | Vérifier distribution : ≥25 ex./classe sur classes en erreur | Table résumé par classe |
| 2 | Vérifier tag pattern : 100 % des nouveaux exemples taggés | Aucune ligne `pattern=` vide |
| 3 | Test train local : temps < 300 s sur ~250 ex. | Profil OK |
| 4 | Commit train enrichi + hash | Train figé pour v0.3.7 |

---

### W4.4 — Campagne v0.3.7 avec train enrichi

Voir PHASE 3 ci-dessous (fusion dans la campagne).

---

## PHASE 3 : Campagne v0.3.7 — Protocole v2.1 complet (½-1 jour)

### Pré-campagne (checklist)

- [ ] W2 contre-épreuve : lecture actée, archivée
- [ ] W1 mergé : G-1 validé en rejouant V1-4
- [ ] W3 mergé : protocole v2.1 publié, code sweep Pareto vert en CI
- [ ] W4.1/W4.2/W4.3 : train enrichi committé, hash figé, taggé par pattern
- [ ] Tag `v0.3.7` posé sur worktree **clean** (`git describe --tags --dirty` == `v0.3.7`)
- [ ] Triple version vérifiée (tag / pyproject.toml / pip show)

### Exécution campagne

**Protocole** : v2.1 (avec amendements W3)

| Phase | Tests | Durée | Artefacts clés |
|---|---|---:|---|
| CE | CE-1→CE-8 | 10 min | Worktree clean confirmé |
| V0 | V0-1→V0-5 | 30 min | → G-0 |
| V1 | V1-1→V1-5 | 45 min | → G-1 (avec W1.2 CRITICAL log) |
| V2 | V2-1→V2-6 (V2-4/V2-5 sur bot jetable) | 1h | Train 222 s (à surveiller si ~250 ex.), manifeste, latence |
| V3-0 | Sweep Pareto 240 points | 45 min | Sélection contrainte W3.1, seuils figés |
| V3-1→V3-6 | GNG + pièges + reproductibilité | 1h | → G-3 ? |

### Sorties possibles

```
┌─────────────────────────────────────────────────────┐
│  G-0/G-1/G-2/G-3 tous PASS ?                        │
└─────────────────────────────────────────────────────┘
           │
    ┌──────┴───────┐
    │              │
  OUI             NON
    │              │
    ▼              ▼
┌────────┐    ┌─────────────────────────────────────┐
│ R0+R1  │    │ Échec marginal (< 3 pts / < 2 pièges) │
│ VALIDÉS│    │ ou échec net ?                       │
│        │    └─────────────────────────────────────┘
│ R2-R9  │              │
│ ouverts│         ┌────┴─────┐
└────────┘         │          │
              marginal      net
                 │            │
                 ▼            ▼
         ┌────────────┐  ┌────────┐
         │ Itération 2│  │   W5   │
         │ (dérogation│  │ Postulat│
         │  tracée)   │  │ métier │
         └────────────┘  └────────┘
```

**Critère échec marginal** : < 3 points sur un GNG **ou** < 2 pièges manquants
**Critère échec net** : ≥ 3 points ou ≥ 2 pièges après itération 2

---

## W5 — Branche d'échec conditionnelle (à préparer dès maintenant)

**Déclencheur** : Échec net après 2 itérations W4

**Actions à préparer EN PARALLÈLE** (métier + pilote, ½ jour) :

1. **Hypothèses de révision candidates** (instruites par patterns W4.1) :
   - Fusion `cotisations` ← `justificatif_droits` ?
   - `changement_coordonnees` = sous-motif de `services_en_ligne` ?
   - `demande_conseiller` = détection dédiée (mots-clés + modèle) au lieu d'intention concurrente ?

2. **Critère de déclenchement** : > 3 points manquants sur un GNG **ou** > 2 pièges après itération 2

3. **Conséquence assumée** : Révision postulat = re-figeage datasets held-out = chiffres repartent de zéro

**Livrable anticipé** : `W5_hypotheses_revision_postulat.md` prêt à instruire si nécessaire

---

## Responsabilités et coordination

| Chantier | Responsable | Besoins métier | Critique |
|---|---|---|---|
| W2 | Claude Code (autonome) | Non | Bloquant pour tout |
| W1 | Claude Code (autonome) | Non | Éliminatoire G-1 |
| W3 | Claude Code (dev ~½j) | Non | Méthodologie honnête |
| W4.1 | Claude Code | Non (analyse existant) | — |
| W4.2 | **Métier + Claude Code** | **OUI** (rédaction verbatims) | **Verrou final G-3** |
| W4.3 | Claude Code | Non | — |
| W5 | Métier + pilote | OUI (décision périmètre) | (Conditionnel) |

**Point de blocage identifié** : W4.2 demande **impérativement** l'implication métier pour produire ~100-150 verbatims réalistes. Ce n'est **pas** une tâche d'ingénierie pure.

---

## Jalons et livrables

| Jalon | Date cible | Livrable | Validation |
|---|---|---|---|
| J+0 | Aujourd'hui | Plan exécution global approuvé | Pilote |
| J+0 | Aujourd'hui | W2 contre-épreuve actée | Pilote |
| J+1 | Demain | W1 + W3 mergés, protocole v2.1 publié | CI verte |
| J+2 à J+4 | Dans 2-4j | W4.1/W4.2/W4.3 : train enrichi committé | Métier + pilote |
| J+5 | Dans ~5j | Campagne v0.3.7 exécutée | Rapport v2.1 |
| J+5 | Dans ~5j | **Verdict R0+R1** ou itération 2 ou W5 | Pilote |

---

## Risques et mitigations

| Risque | Probabilité | Impact | Mitigation |
|---|---|---|---|
| W2 révèle régression réelle (pas artefact) | Moyenne | Élevé (suspendre W4) | Prévu : bissecter M1/M2/M3, corriger, revenir |
| Métier indisponible pour W4.2 (production verbatims) | Faible | **Bloquant** | Alerter **maintenant**, planifier créneaux dédiés |
| Train enrichi > 300 s (budget V2-1) | Faible | Modéré | Profil local avant commit ; marge disponible 222→300 s |
| W4 itération 1 échoue de peu | Moyenne | Modéré | Prévu : itération 2 autorisée (max 2 itérations) |
| W4 itération 2 échoue net | Faible | Élevé (W5) | W5 préparé en parallèle (hypothèses postulat déjà instruites) |
| Sweep Pareto W3.1 plus complexe que prévu | Moyenne | Modéré | Budgété ½ journée ; algorithme bien défini dans roadmap |

---

## Décisions immédiates requises

1. **Validation du plan** : Ce plan est-il aligné avec les contraintes et attentes ?
2. **Disponibilité métier pour W4.2** : Qui ? Quand ? Combien de temps (1-2 jours dédiés) ?
3. **Ordre d'exécution phase 0** : Lancer W2 **maintenant** (1h) avant toute autre action ?
4. **Parallélisation W1+W3** : Lancer en parallèle après W2, ou séquentiel ?

---

## Prochaine action recommandée

**Lancer W2 (contre-épreuve) immédiatement** — 1 heure pour savoir si on part d'un plateau 74/86/83 ou d'une régression 72/82/72. Toutes les décisions de W4 en dépendent.

Commande : `Confirmer démarrage W2 ?`
