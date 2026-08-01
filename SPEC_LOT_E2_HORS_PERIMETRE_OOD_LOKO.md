# 🔬 SPEC — Lot E2 : `hors_perimetre` en rejet OOD

> **Version** : 1.0 — 1er août 2026
> **Destinataire** : Claude Code (exécution), après validation humaine 🛑 B-E2.
> **Entrées** : `ANALYSE_POST_CAMPAGNE_v1.3.4.md`, `ETAT_ACTUEL_PROJET_LOKO_2026-08-01.md`, spec de dev §4–§5.
> **Objet** : remplacer `hors_perimetre` comme classe apprise par un **rejet fondé sur un score de nouveauté (OOD)**, pour sortir du plateau de G-3.
> **Nature** : chantier de fond, sur branche dédiée, **jamais pendant une campagne**.

---

## 1. Constat — trois signaux convergents

L'axe `hors_perimetre` est le vecteur d'erreur dominant du projet, établi par trois voies **indépendantes** :

| Source | Signal |
|---|---|
| Erreurs GNG-1 | Aspiration vers `hors_perimetre` : 12/22 (v1.3.2), 11/19 (v1.3.3) — dont 7 sur `help_documents` |
| Erreurs GNG-2 | 6/14 des `parler_conseiller` manqués atterrissent en `hors_perimetre` |
| Outil `advice` (V2-4, autonome) | Désigne `hors_perimetre` × `help_leave` comme paire de plus faible F1 — et le correctif de +10 exemples **dégrade** la précision (0,911 → 0,900, V2-5 FAIL) |

**Diagnostic** : on demande à SetFit d'apprendre une classe qui doit modéliser *tout le reste du langage naturel*, à partir d'environ 16 exemples, en concurrence directe avec 8 classes métier denses et bien définies. Aucun volume d'exemples ne referme un espace non borné. Chaque exemple ajouté d'un côté de la frontière se paie de l'autre : c'est ce que montre la campagne v1.3.4 (GNG-1 stable, GNG-3 −8 pts).

**Ce lot ne cherche pas à mieux entraîner `hors_perimetre`. Il cherche à ne plus l'entraîner du tout.**

---

## 2. Principe

Le classifieur L1 n'apprend plus que les **8 classes réellement définies** (7 intentions métier + `demande_conseiller`). Le hors-périmètre devient un **verdict de rejet**, prononcé par un score de nouveauté calculé dans l'espace d'embedding, en amont de la décision.

```
                      ┌─ score OOD ≥ seuil_ood ──────────► REJET (hors_perimetre)
texte ──► embedding ──┤
                      └─ score OOD < seuil_ood ──► softmax 8 classes ──► decide_l1()
```

**Invariants préservés** — non négociables :
- Décision **100 % déterministe**, aucun LLM sur le chemin.
- Le contrat de sortie de `decide_l1()` est **inchangé** : `route` / `clarify_inter` / `reject` / `escalate`. La FSM, les templates et le widget ne bougent pas.
- Le motif d'escalade `hors_perimetre` et la règle « 1 reformulation puis escalade » sont inchangés.
- Tout artefact ajouté (centroïdes, seuil OOD) est **figé et hashé au manifeste** — le rejeu déterministe GNG-4 doit rester vert.

---

## 3. Conception

### 3.1 Score de nouveauté

**Méthode retenue en V1 — distance au centroïde le plus proche** (simple, déterministe, sans dépendance nouvelle, coût négligeable) :

1. À l'entraînement, pour chacune des 8 classes, calculer le centroïde des embeddings normalisés de ses exemples.
2. À l'inférence, `d(x) = 1 − max_c cos(embed(x), centroïde_c)`.
3. `d(x) ≥ seuil_ood` → rejet, sans passer par la tête de classification.

**Méthodes à évaluer en second rideau, si la V1 sous-performe** : distance au k-ème plus proche voisin (k=5) dans l'ensemble d'entraînement ; score d'énergie sur les logits. Ne pas les implémenter d'emblée — mesurer d'abord.

### 3.2 Calibration du seuil OOD — ⚠️ point le plus sensible

**Interdit absolu : calibrer `seuil_ood` sur un held-out.** Ce serait une fuite d'évaluation, donc l'interdit n°5 dans son esprit. Les held-out mesurent, ils ne règlent rien.

**Procédure autorisée** : validation croisée sur `train.csv` uniquement. Pour chaque pli, les exemples des classes retenues sont « in », et l'on utilise comme « out » les exemples que l'utilisateur a déclarés hors-périmètre dans la configuration du bot (aujourd'hui exemples de la classe `hors_perimetre`) — **réaffectés en jeu de validation négatif, jamais en classe d'entraînement**. Le seuil retenu maximise le F1 macro de la décision binaire in/out sur les plis.

Le seuil et sa méthode sont écrits au manifeste. Le sweep Pareto existant gagne `seuil_ood` comme 4ᵉ axe, avec les mêmes règles de gel.

### 3.3 Contrainte de compatibilité — à traiter, sinon le lot casse la publication

`tests/bot/test_models.py::test_published_requires_hors_perimetre` impose la présence d'une intention `hors_perimetre` pour tout bot publié. Le validateur `BotConfig` l'exige.

**Ne pas supprimer cette contrainte.** L'intention `hors_perimetre` reste dans la configuration — elle porte son libellé, son template et sa sémantique d'escalade. Ce qui change est unique et local : elle est **exclue de l'ensemble d'entraînement L1** et ses exemples deviennent le **jeu de validation négatif** de §3.2.

Point d'attention : `prepare_l1_training_data()` alimente `compute_dataset_hash()`. Retirer une classe modifie le hash → tous les bots existants passeront en `retrain_required` à la publication. C'est **correct et voulu** (le modèle a effectivement changé de nature), mais doit être annoncé dans les notes de version et couvert par un test de migration.

### 3.4 Impacts fichiers

| Fichier | Modification |
|---|---|
| `loko/bot/classifier/ood.py` | **Nouveau** : `compute_centroids()`, `ood_score()`, `calibrate_ood_threshold()` |
| `setfit_service.py` / chaîne d'entraînement | Exclusion de `hors_perimetre` du train ; calcul et persistance des centroïdes |
| `manifest.py` | Bloc `ood` : `{ threshold, method, centroids_hash, n_classes, calibration }` |
| `loader.py` | `SetFitClassifierAdapter` charge centroïdes + seuil ; `classify_l1()` renvoie le score OOD |
| `decision.py` (`decide_l1`) | Rejet OOD **avant** l'examen des scores de classes |
| `models.py` (`TraceEvent`) | Champ `ood_score: float` dans la trace de décision |
| `loko/eval/cli.py` | Chemin unifié avec le runtime (**prérequis lot A3** — ne pas démarrer E2 sans) |
| `sweep` | `seuil_ood` en 4ᵉ axe |

---

## 4. Prérequis bloquants

E2 **ne démarre pas** tant que ces trois points ne sont pas acquis :

1. **Lot A3 livré** — `loko-eval` passe par le même adaptateur que le runtime. Sinon on mesurerait un pipeline différent de celui exécuté, et toute conclusion serait nulle.
2. **Seuils de v1.3.4 élucidés** (§4.1 de l'analyse post-campagne) — sans baseline interprétable, aucune comparaison n'a de sens.
3. **Statut de la calibration M1 tranché** — deux modifications simultanées sur la couche de scoring rendraient l'attribution des effets impossible.

---

## 5. Protocole de mesure

Sur branche `feat/ood-rejection`, **hors campagne**, avec les datasets figés strictement intouchés.

| Étape | Action | Sortie |
|---|---|---|
| M0 | Baseline : re-mesure du modèle actuel aux mêmes seuils, sur la même machine, in-container | `eval/lot-e2/baseline.json` |
| M1 | Entraînement 8 classes + centroïdes + calibration seuil (train uniquement) | manifeste avec bloc `ood` |
| M2 | Mesure GNG-1/2/3 + pièges, seuils gelés | `eval/lot-e2/ood_v1.json` |
| M3 | Sweep 4 axes, re-mesure au meilleur point | `eval/lot-e2/ood_sweep.json` |
| M4 | Rejeu déterministe ×2, diff structurel | doit être **vide** |
| M5 | Comparatif et recommandation | `eval/lot-e2/RAPPORT_E2.md` |

**Aucun tag, aucune campagne officielle avant décision humaine sur le comparatif.**

---

## 6. Critères d'acceptation

| # | Critère | Seuil |
|---|---|---|
| E2-A1 | GNG-3 (rejet hors-scope) | **≥ 84 %** — au moins le meilleur historique (v1.3.2) |
| E2-A2 | GNG-1 | **≥ 81 %** — aucune régression sur la baseline v1.3.3/v1.3.4 |
| E2-A3 | GNG-2 | **≥ 88,8 %** — aucune régression |
| E2-A4 | Pièges | ≥ 9/15, **et progression sur T13** (hors-scope mal classé — cible naturelle de l'OOD) |
| E2-A5 | Déterminisme | Rejeu ×2, diff structurel **vide** ; centroïdes hashés au manifeste |
| E2-A6 | Latence | Surcoût OOD **< 2 ms** P95 (produit scalaire sur 8 vecteurs — doit être négligeable) |
| E2-A7 | Étanchéité held-out | Hashes de `eval/datasets/**` **identiques** avant/après l'ensemble du lot |
| E2-A8 | Absence de fuite de calibration | Test statique : aucun chemin de code de calibration ne lit un fichier `heldout_*` |
| E2-A9 | Compatibilité | Un bot existant se publie encore ; `retrain_required` levé proprement ; test de migration vert |
| E2-A10 | Traçabilité | `ood_score` présent dans chaque trace de décision, visible au playground |

**Règle de décision** : E2 est retenu si **E2-A1 est atteint sans violer A2 ni A3**. Un gain sur GNG-3 payé par une chute de GNG-1 est le même échange à somme nulle que celui constaté en v1.3.4 — donc un échec, pas un progrès.

---

## 7. Risques

| Risque | Traitement |
|---|---|
| **Sur-rejet** : l'OOD rejette des requêtes métier légitimes → GNG-1 chute | E2-A2 en garde-fou dur ; le sweep arbitre explicitement l'échange |
| **Fuite de calibration** par facilité (« calibrons sur le held-out hors-scope, c'est plus propre ») | E2-A8 en test statique bloquant. **C'est le risque n°1 de ce lot** |
| Centroïdes instables sur classes à faible effectif | Consigner l'effectif par classe au manifeste ; alerter sous 10 exemples |
| Effet croisé avec la calibration M1 (deux modifications sur la même couche) | Prérequis §4.3 : M1 tranché avant de commencer |
| Le sweep 4 axes explose combinatoirement | Grille grossière d'abord, raffinement local ensuite ; budget de temps consigné |
| Échec du lot après 2–3 j | Acceptable : la branche est jetable, la baseline est intacte, et l'information « l'OOD ne suffit pas » a de la valeur |

---

## 8. Effort et séquencement

| Phase | Effort |
|---|---|
| Implémentation `ood.py` + intégration entraînement/loader/décision | 1 j |
| Calibration + sweep 4 axes | ½ j |
| Tests (A5, A7, A8, A9) | ½ j |
| Mesures M0–M5 + rapport | ½ j |
| **Total** | **~2,5 j** |

Chemin critique inchangé : **lot 0 (sécurité prod) → lot A (calibration) → élucidation des seuils**. E2 s'ouvre après, sur branche parallèle.

---

## 9. Ce que ce lot ne fait pas

Il ne touche ni la FSM, ni les templates, ni le retrieval, ni le widget, ni le contrat SSE, ni les datasets figés. Il ne modifie pas la règle « max 1 clarification par demande ». Il ne remplace pas l'itération V3-7 2/2 : il propose une alternative **à la place** de la consommer.

🛑 **Point d'arrêt B-E2** : ouvrir ce lot, ou engager l'itération V3-7 2/2 ?

*Élément pour la décision* : l'enrichissement a produit +3 pts (itération 1), puis 0 pt et −8 pts sur GNG-3 (v1.3.4), et le cycle d'amélioration autonome a lui-même dégradé la précision en tentant de renforcer `hors_perimetre`. Trois mesures indépendantes indiquent que la voie de l'enrichissement est saturée. E2 attaque la cause plutôt que le symptôme — mais reste un pari, à mesurer avant d'être cru.
