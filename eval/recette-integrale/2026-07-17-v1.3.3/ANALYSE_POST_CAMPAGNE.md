# ANALYSE POST-CAMPAGNE v1.3.3

**Date** : 2026-07-18
**Tag** : v1.3.3 (commit 0214d59)
**Image** : loko:v1.3.3 (sha256:2fcacf6c3c299...)
**Bot** : fa4d8b2d-548f-457b-bf65-acbc61a39cbb
**Runner** : v1.1.0
**Machine** : poste-ref-ryzen7-5800HS-win11-docker28.5-wsl2
**Boucle V3-7** : iteration 1/2 (enrichissement +98 exemples applique)
**Seuils selectionnes par sweep** : haut=0.85, bas=0.50, ecart=0.00

---

## 1. Verdicts des gates

| Gate | Verdict | Detail |
|------|---------|--------|
| CE   | **FAIL** | 8/9 (CE-2 FAIL) |
| G-0  | **FAIL** | 4/5 (V0-1 FAIL) |
| G-1  | **PASS** | 4/4 |
| G-1b | **PASS** | 1/1 |
| G-2  | **FAIL** | 3/6 (V2-1, V2-5, V2-6 FAIL) |
| G-3  | **FAIL** | 4/7 (V3-1, V3-2, V3-4 FAIL) |

**Decision de campagne : NON VALIDE** (gates en echec : CE, G-0, G-2, G-3)

---

## 2. Chiffres GNG vs seuils et vs v1.3.2

| Metrique | Seuil | v1.3.2 | v1.3.3 | Delta | Verdict |
|----------|-------|--------|--------|-------|---------|
| GNG-1 (heldout_metier) | >= 85% | 78.0% | **81.0%** (81/100) | +3.0 | **FAIL** |
| GNG-2 (heldout_conseiller) | >= 90% | 85.6% | **88.8%** (111/125) | +3.2 | **FAIL** |
| GNG-3 (heldout_horsscope) | >= 80% | 84.0% | **80.0%** (80/100) | -4.0 | PASS |
| Pieges | >= 12/15 | 8/15 | **9/15** (60%) | +1 | **FAIL** |

**Observations** :
- GNG-1 et GNG-2 progressent sensiblement par rapport a v1.3.2 (+3 et +3.2 points)
  mais restent sous les seuils (85% et 90%).
- GNG-3 regresse de 4 points (84% -> 80%) et atteint le seuil tout juste.
- Les pieges progressent marginalement (8/15 -> 9/15) mais restent loin du seuil (12/15).
- Le sweep a selectionne des seuils differents de v1.3.2 (haut 0.85 vs 0.90,
  bas 0.50 vs 0.40, ecart 0.00 vs non specifie), ce qui modifie la logique de
  decision (plus de routes directes, moins de rejets).

---

## 3. Classification des FAIL par cause

### 3.1 Outillage (reparable entre campagnes)

| Ligne | Cause | Detail |
|-------|-------|--------|
| CE-2 | `pyproject.toml` version non bumpee | tag=v1.3.3, pyproject=1.3.2. La version dans `pyproject.toml` n'a pas ete mise a jour lors du bump de tag. Correction triviale. |

### 3.2 Produit (code applicatif)

| Ligne | Cause | Detail |
|-------|-------|--------|
| V0-1 | 7 tests unitaires en echec | 569 passed, 7 failed, 3 skipped. Voir detail ci-dessous. |
| V2-1 | Temps d'entrainement 463s > 300s | L'enrichissement +98 exemples augmente le volume d'entrainement. CPU-only, pas d'acceleration GPU. |
| V2-5 | Cycle d'amelioration regressif | Paire detectee (hors_perimetre x help_leave), retrain +10 ex. Accuracy avant=0.914, apres=0.894. Les cellules de la matrice ne sont pas disponibles pour evaluer la correction ciblee. |
| V2-6 | Latence P95 = 106 ms > 50 ms | Mesure in-container, CPU-only, n=200. Le seuil de 50 ms semble calibre pour GPU ou hardware plus performant. |

**Detail V0-1 — 7 tests en echec (tous produit, aucun outillage) :**

1. `test_too_few_examples_raises` (TestIntent + TestSubMotif) — 2 tests :
   Le code ne leve plus `ValueError` pour un nombre insuffisant d'exemples.
   Le produit a change la validation minimale des exemples.

2. `test_signup_no_token_in_logs` / `test_reset_no_token_in_logs` — 2 tests :
   `asyncio.get_event_loop()` leve `RuntimeError` sous Python 3.12
   (deprecation de la boucle implicite dans le thread principal).
   Test a migrer vers `asyncio.new_event_loop()` ou `asyncio.run()`.

3. `test_lazy_migration_assigns_internal_account` — 1 test :
   Attend `schema_version == 2`, obtient `4`. Le schema de migration a evolue.

4. `test_login_blocked_before_verification` — 1 test :
   Attend HTTP 403, obtient 200. Le comportement d'authentification a change.

5. `test_intent_min_examples_validation` (e2e) — 1 test :
   Attend HTTP 422/400, obtient 200. Coherent avec le changement de validation
   minimale des exemples (points 1).

### 3.3 Modele / qualite de classification

| Ligne | Cause | Detail |
|-------|-------|--------|
| V3-1 | GNG-1 = 81% < 85% | 19 erreurs / 100 sur heldout_metier |
| V3-2 | GNG-2 = 88.8% < 90% | 14 erreurs / 125 sur heldout_conseiller |
| V3-4 | Pieges = 9/15 < 12/15 | 6 pieges echoues |

---

## 4. Patterns d'erreurs GNG

### 4.1 GNG-1 — heldout_metier (19 erreurs)

**Pattern dominant : confusion help_documents (11/19 erreurs)**

| Attendu | Predit | Nb | Pattern |
|---------|--------|----|---------|
| help_documents | hors_perimetre | 7 | "carte mutuelle", "certificat", "attestation" classes hors perimetre |
| help_documents | help_account | 2 | "perdu carte adherent", "telecharger carte mutuelle" |
| help_documents | help_transfer | 1 | "renseignement carte mutuelle" |
| help_documents | help_documents (reject) | 1 | Score 0.35, sous le seuil bas (0.50) |
| help_account | reject | 2 | Scores 0.47 et 0.33, sous le seuil bas |
| help_contact | reject/erreur | 2 | Score ~0.50, zone d'ambiguite |
| help_leave | erreur diverse | 3 | "subrogation" -> help_billing (route), "cld" -> hors_perimetre, "temps partiel" -> help_transfer |
| help_transfer | reject | 1 | Score 0.41, sous le seuil bas |

**Analyse** : Le modele ne reconnait pas suffisamment le champ semantique
"documents / attestations / carte mutuelle" comme relevant de `help_documents`.
Les 7 confusions help_documents -> hors_perimetre suggerent que l'enrichissement
iteration 1 n'a pas couvert ce vecteur de confusion. La majorite des erreurs
sont des rejets (score < seuil_bas 0.50) plutot que des classifications erronees.

### 4.2 GNG-2 — heldout_conseiller (14 erreurs)

**Pattern dominant : "mutuelle" = poison semantique (14/14 erreurs = parler_conseiller)**

| Predit | Nb | Exemples |
|--------|----|----------|
| hors_perimetre | 6 | "mutuelle", "mutuelle obligatoire", "modification mutuelle sante", "souscrire mutuelle", "demandes d'informations", "renseignement dematerialisation" |
| help_transfer | 3 | "renseignement prise mutuelle", "sans mutuelle", "demi-traitement" |
| help_contact | 1 | "appel mutuelle coupe" |
| help_billing | 1 | "perte carte mutuelle" |
| help_cancellation | 1 | "resiliation mutuelle" (route, score 0.998) |
| reject divers | 2 | Scores faibles (0.20-0.28) |

**Analyse** : Toutes les 14 erreurs sont des `parler_conseiller` non reconnus.
Le mot "mutuelle" est un leurre semantique fort qui attire le modele vers
`hors_perimetre` ou d'autres intents. La confusion "resiliation de mutuelle"
-> `help_cancellation` (score 0.998, route directe) est particulierement
symptomatique : le modele comprend le verbe "resilier" mais ignore le contexte
"parler a un conseiller" present dans le dataset source.

### 4.3 GNG-3 — heldout_horsscope (20 erreurs)

Les 20 erreurs sont toutes des labels hors-scope (accident, action_sociale,
ceam, dentaire, etc.) classifies vers des intents in-scope (help_documents,
help_billing, help_contact, help_leave, help_transfer). C'est le comportement
attendu du classifieur, qui ne connait pas les labels hors-scope et doit les
rejeter. La regression de 84% a 80% est coherente avec le changement de
seuils : le seuil_haut abaisse de 0.90 a 0.85 provoque davantage de routes
directes erronees vers des intents in-scope.

### 4.4 Pieges (6 echecs / 15)

| Piege | Attendu | Obtenu | Analyse |
|-------|---------|--------|---------|
| T02 "modification mot de passe" | route:help_account | clarify_inter:help_contact\|help_account | Le bon intent est dans les candidats mais pas en route directe |
| T04 "RIB coordonnees bancaires" | clarify_inter:help_contact\|help_billing | route:help_contact (0.981) | Score trop eleve, pas de clarification |
| T05 "changement banque prelevements" | clarify_inter:help_contact\|help_billing | route:help_billing (0.982) | Idem, conviction trop forte |
| T06 "attestation de paiement" | clarify_inter 3-voies | clarify_inter 2-voies | Candidat help_billing manquant dans la clarification |
| T13 "bilan bucco-dentaire" | reject | clarify_inter:help_billing\|help_leave | Devrait etre hors perimetre, mal classe |
| T15 "IBAN + carte vitale" | route:help_account | reject:help_contact | Score 0.49, sous le seuil bas |

---

## 5. Comparaison globale v1.3.2 -> v1.3.3

| Dimension | v1.3.2 | v1.3.3 | Tendance |
|-----------|--------|--------|----------|
| Seuils sweep | haut=0.90 bas=0.40 | haut=0.85 bas=0.50 | Bande de clarification retrecit |
| GNG-1 | 78% | 81% | Amelioration (+3 pts) |
| GNG-2 | 85.6% | 88.8% | Amelioration (+3.2 pts) |
| GNG-3 | 84% | 80% | Regression (-4 pts) |
| Pieges | 8/15 | 9/15 | Leger progres (+1) |
| Tests pytest | Non documente | 7 FAIL | Regression produit |
| Train time | Non documente | 463s (> 300s) | Hors seuil |
| Latence P95 | Non documente | 106 ms (> 50 ms) | Hors seuil |
| G-1 / G-1b | PASS | PASS | Stable |

L'enrichissement iteration 1 (+98 exemples) ameliore les deux metriques GNG
principales mais pas suffisamment pour franchir les seuils. La regression
GNG-3 est un effet de bord du changement de seuils (plus de routes directes
= plus de faux positifs sur les labels hors-scope).

---

## 6. Etat de la boucle V3-7

- **Iterations consommees** : 1/2
- **Iteration 1** : +98 exemples (`eval/enrichment/enrichment_v3_7_iter1.csv`),
  held-out verifies intouches.
- **Resultat** : GNG-1 +3 pts, GNG-2 +3.2 pts, GNG-3 -4 pts, pieges +1.
  Progression insuffisante (4 pts manquants sur GNG-1, 1.2 pts sur GNG-2,
  3 pieges manquants).

---

## 7. Proposition de plan d'iteration 2/2 (soumise a decision humaine)

**La decision de lancer l'iteration 2 appartient a Besnard.**

### Cibles prioritaires identifiees :

1. **help_documents** (impact GNG-1 : 11/19 erreurs) :
   Enrichir le bot avec des exemples de type "carte mutuelle", "certificat
   d'appartenance", "attestation carte vitale", "justificatif" pour que le
   modele distingue mieux help_documents de hors_perimetre.

2. **parler_conseiller + "mutuelle"** (impact GNG-2 : 14/14 erreurs) :
   Le mot "mutuelle" est un leurre. Enrichir avec des exemples contenant
   "mutuelle" labeles parler_conseiller pour desensibiliser le modele.

3. **Pieges T04/T05** (impact pieges : 2 echecs par sur-confiance) :
   Les scores 0.98 empechent la clarification. Ce probleme est lie au
   modele et aux seuils ; un enrichissement cible est peu probable de
   resoudre une sur-confiance a 0.98.

### Methode (meme protocole que iteration 1) :

- Source : `dataset.csv` (via `tools/make_datasets.py`, scrub + INTENT_RENAME)
- Selection deterministe triee
- Exclusion stricte des held-out / pieges / exemples existants
- Intersection verifiee = 0
- Estimation : ~50-80 exemples cibles (help_documents + parler_conseiller)

### Risques :

- La regression GNG-3 pourrait s'aggraver si les seuils Pareto changent encore.
- Le temps d'entrainement (deja 463s) va augmenter avec plus d'exemples.
- Les pieges T04/T05 (sur-confiance a 0.98) ne sont probablement pas
  corrigeables par enrichissement seul.

---

## 8. Anomalies de protocole suspectees

*(Cette section n'altere JAMAIS les verdicts)*

1. **CE-2** : La version `pyproject.toml` (1.3.2) n'a pas ete bumpee pour
   le tag v1.3.3. C'est un oubli d'outillage lors de la preparation.
   Correctible entre campagnes mais ne change rien aux resultats GNG.

2. **V2-6** : Le seuil de latence P95 <= 50 ms semble calibre pour un
   environnement avec acceleration (GPU ou ARM optimise). Sur le poste
   de reference (Ryzen 7 5800HS, CPU-only, Docker/WSL2), 106 ms peut etre
   le plancher atteignable avec MiniLM-L12 in-container.

---

## 9. Artefacts

| Artefact | Chemin |
|----------|--------|
| Rapport de campagne | `eval/recette-integrale/2026-07-17-v1.3.3/RAPPORT_CAMPAGNE.md` |
| Rapport JSON | `eval/recette-integrale/2026-07-17-v1.3.3/campaign_report.json` |
| Erreurs GNG-1 | `eval/recette-integrale/2026-07-17-v1.3.3/V3_heldout_metier/errors.csv` |
| Erreurs GNG-2 | `eval/recette-integrale/2026-07-17-v1.3.3/V3_heldout_conseiller/errors.csv` |
| Erreurs GNG-3 | `eval/recette-integrale/2026-07-17-v1.3.3/V3_heldout_horsscope/errors.csv` |
| Erreurs pieges | `eval/recette-integrale/2026-07-17-v1.3.3/V3_pieges/errors.csv` |
| Pytest output | `eval/recette-integrale/2026-07-17-v1.3.3/V0-1_pytest.txt` |
| Sweep | `eval/recette-integrale/2026-07-17-v1.3.3/sweep/` |
| Manifeste gele | `eval/recette-integrale/2026-07-17-v1.3.3/V3-5_manifest.json` |
| Manifeste hash | c5ffe2ee3a9f56f7... |

---

*Analyse redigee le 2026-07-18 par Claude Code (runner de campagne). Aucune requalification.*
