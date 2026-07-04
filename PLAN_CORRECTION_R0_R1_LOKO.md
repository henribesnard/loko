# 🩹 LOKO — Plan de correction post-campagne R0+R1 du 4 juillet (rapport codex)

> **Version** : 1.0 — 4 juillet 2026
> **Entrée** : `RAPPORT_VALIDATION_R0_R1_LOKO.md` (verdict : R0+R1 NON VALIDÉS, CE-3 bloquant)
> **Destinataire** : Claude Code. Un commit atomique + test par item. La campagne sera rejouée **depuis V0-1** après livraison complète (règle 4 du protocole).
> **Lecture du rapport** : aucun des constats ne remet en cause la conception des lots A/B/C — ce sont des défauts de **livraison** (packaging cassé, outillage promis non implémenté, protocole désynchronisé du code). Le point positif : le protocole a fait son travail en refusant de produire des chiffres sur un environnement non recevable.

---

## 0. Synthèse des corrections

| ID | Sévérité | Constat du rapport | Correction |
|---|---|---|---|
| C1 | 🔴 P0 | `build-backend = "setuptools.backends._legacy:_Backend"` → build Docker et install editable impossibles | Backend valide + test de build en CI |
| C2 | 🔴 P0 | `constraints-ml.txt` vide (gabarit) et non appliqué par le Dockerfile | Freeze réel + `-c` effectif + garde CI |
| C3 | 🔴 P0 | `pieges.csv` désaligné des T01–T15 (ex. T04 ≠ « RIB coordonnées bancaires ») + chevauchement `train.csv`/`pieges.csv` sur « noemie » | Régénérer les jeux, aligner, dédupliquer |
| C4 | 🟠 P1 | `train.csv` = 1 801 lignes, alors que le protocole le définit comme les exemples du postulat §2 (~120) | Trancher et tracer (voir C4) |
| C5 | 🟠 P1 | `tools/make_datasets.py --check` absent (CE-5 invérifiable automatiquement) | Implémenter `--check` |
| C6 | 🟠 P1 | `npm audit --audit-level=high` : 1 critical + 1 high (chaîne Vite/Vitest) — déjà prescrit en A6.3, non fait | Mise à jour + gate CI |
| C7 | 🟠 P1 | Lint anti-mock V0-3 : imports/définitions de mocks encore trouvés dans `loko/` | Isoler les mocks + affiner la règle |
| C8 | 🟠 P1 | Dérive protocole↔code : `test_no_mock_guard.py` vs `test_mock_guards.py` ; `_load_classifier` dans `loko/api/bot_public.py` et non dans un module loader | Déplacer le code (pas amender le protocole) |
| C9 | 🟡 P2 | Worktree non propre (dataset.csv, artefacts non suivis), lien CI absent (CE-1 invérifiable) | Hygiène dépôt + preflight |
| C10 | 🟡 P2 | Les conditions d'entrée ont été découvertes en échec **pendant** la campagne | Script `preflight` automatisant CE-1→CE-7 |

---

## C1 — Réparer le packaging Python (la cause racine)

**Fichier** : `pyproject.toml`.
1. Remplacer `build-backend = "setuptools.backends._legacy:_Backend"` par `build-backend = "setuptools.build_meta"` (avec `requires = ["setuptools>=68"]`). Le backend actuel n'existe dans aucune version de setuptools — c'est vraisemblablement une hallucination introduite lors d'une édition ; la variante `setuptools.build_meta:__legacy__` n'est justifiée que sans table `[build-system]`, ce qui n'est pas le cas ici.
2. **Garde CI nouvelle (leçon du rapport)** : job `build-smoke` qui exécute, sur runner propre, `docker build` **et** `pip install -e ".[server,ml]"` dans `python:3.12-slim`. C'est exactement la reproduction faite par le testeur — elle doit vivre en CI, pas dans une campagne. Ce job devient prérequis de CE-1.

**Critère** : `docker build` OK ; install editable OK dans un conteneur vierge ; job CI vert.

## C2 — Verrouiller réellement les contraintes ML

1. Construire une fois l'environnement ML validé (imports + entraînement canari OK), puis `pip freeze | grep -E 'setfit|transformers|sentence-transformers|torch|huggingface' > constraints-ml.txt` — **committé avec ses versions réelles**, plus jamais un gabarit.
2. Dockerfile : `pip install -e ".[server,ml]" -c constraints-ml.txt` (le fichier était copié mais l'option `-c` absente — corriger la ligne).
3. Garde CI : le job `build-smoke` échoue si `constraints-ml.txt` est vide ou si une ligne ne contient pas `==` épinglé.

**Critère** : suppression d'une ligne du fichier → build CI rouge ; versions in-container == constraints.

## C3 — Réaligner `pieges.csv` sur les T01–T15 du postulat

1. Régénérer `pieges.csv` **exactement** depuis le tableau §4 du postulat : T01 = « je souhaiterais débloquer mon compte Ameli » … T04 = « RIB coordonnées bancaires » (clarify_inter:changement_coordonnees|cotisations) … T14 = « Noemie » … T15 = cas IBAN/carte vitale. La colonne `expected_behavior` reprend la syntaxe normée (`route:`, `clarify_intra:`, `clarify_inter:`, `reject`, `escalate:`).
2. Résoudre le chevauchement « noemie » : T14 (« Noemie », mot unique) est un cas de **test de robustesse** — il ne doit figurer dans aucun exemple d'entraînement. Retirer de `train.csv` tout verbatim strictement égal (comparaison casse/accents pliés) à un verbatim de `pieges.csv` ou des held-out.
3. Étendre la vérification d'intersection (C5) à **tous** les couples : train×{metier, conseiller, horsscope, pieges}, et pieges×held-out.
4. Régénérer `HASHES.sha256`, committer.

**Critère** : `--check` (C5) exit 0 ; relecture manuelle des 15 lignes contre le postulat consignée en revue de PR.

## C4 — Statuer sur `train.csv` (1 801 lignes vs postulat §2)

Le protocole définit `train.csv` comme « exactement les exemples du postulat §2 » (~120 lignes) ; le fichier livré en contient 1 801. Ce n'est pas neutre : l'expérience validée ne serait plus celle du postulat, et un train massif tiré de `dataset.csv` change la nature du test (SetFit est précisément un apprentissage few-shot). Deux options, **une seule à acter** :
- **Option A (recommandée)** : régénérer `train.csv` = postulat §2 strict. C'est le scénario produit réel (un client saisit 15–20 exemples par intention dans le wizard, pas 1 800) et c'est ce que GNG-1/2/3 doivent mesurer. Le surplus de verbatims reste disponible pour la boucle V3-7 (enrichissement tracé, itération par itération).
- **Option B** : assumer un train enrichi — alors amender formellement le postulat §2 (nouvelle version du document, exemples listés ou référencés par hash), et vérifier que l'enrichissement n'a pas siphonné des verbatims conceptuellement held-out.

Dans les deux cas : le choix, sa justification et le hash final figurent dans le rapport de la prochaine campagne.

## C5 — Implémenter `tools/make_datasets.py --check`

Mode vérification sans régénération : (a) présence des 5 fichiers ; (b) comptes exacts (train = référence actée en C4, 100/126/100/15) ; (c) hashes conformes à `HASHES.sha256` ; (d) intersections vides sur tous les couples (C3.3), comparaison en casse pliée/accents normalisés/espaces réduits ; (e) syntaxe `expected_behavior` valide sur les 15 pièges ; (f) exit code 0/1. Brancher en CI et dans le preflight (C10).

## C6 — Purger l'audit npm (dette répétée deux campagnes de suite)

1. Monter la chaîne Vite/Vitest vers les versions corrigées (`npm audit fix`, puis mise à jour majeure si nécessaire — Vitest est un outil de dev, la mise à jour est à faible risque ; re-passer les 14 tests front).
2. Gate CI : `npm audit --audit-level=high` en échec bloque le build (c'était prescrit en A6.3 et absent — cette fois avec le job, pas seulement la consigne).

**Critère** : audit 0 high/critical ; job CI présent et vert.

## C7 — Isoler les mocks et affiner le lint V0-3

Le rapport note des imports/définitions de mocks encore dans `loko/`. La règle « 0 occurrence hors tests » était ambiguë : les classes doivent bien être définies quelque part. Clarification à implémenter :
1. Déplacer les 4 mocks dans un module unique `loko/testing/mocks.py` (gardes `RAGKIT_ENV` conservées — défense en profondeur).
2. Règle de lint précise : aucun module de `loko/` hors `loko/testing/` n'importe `loko.testing.mocks` ; aucune définition de classe `Mock*`/`_Mock*`/`InMemorySearchBackend` ailleurs. Le test CI implémente cette règle exacte (AST ou grep strict), et le protocole V0-3 est réputé porter sur elle.
3. Vérifier en particulier que `bot_public.py` n'importe plus aucun mock après C8 (c'est probablement là que le grep a accroché).

## C8 — Resynchroniser le code avec le protocole (et pas l'inverse)

Deux dérives relevées ; dans les deux cas on aligne le **code** sur la cible du document d'amélioration, qui était la bonne :
1. `_load_classifier` vit dans `loko/api/bot_public.py` : le déplacer dans `loko/bot/classifier/loader.py` comme prévu par l'item A3 (un module API ne doit pas porter le chargement de modèles ; c'est aussi ce qui permet à `loko-eval` et au serveur de partager le même chemin de chargement sans importer FastAPI). `bot_public.py` n'en garde que l'appel.
2. Renommer `tests/bot/test_mock_guards.py` → `test_no_mock_guard.py` (ou ajouter un alias de collection) pour que la référence du protocole soit exécutable telle quelle.
3. Ajouter au gabarit de PR une case « références du protocole de validation vérifiées » — la dérive doc↔code est la maladie chronique de ce projet (trois campagnes, trois désynchronisations).

## C9 — Hygiène du dépôt

1. `.gitignore` : `dataset.csv` (donnée client, ne doit pas vivre dans le dépôt — seuls les CSV `eval/datasets/` figés y sont), `eval/campagne-*/` (artefacts de campagne archivés hors git ou dans un stockage dédié).
2. CE-1 : renseigner dans le README de campagne l'URL du pipeline CI à joindre au rapport (le testeur n'avait aucun lien à vérifier).

## C10 — Script `tools/preflight.py` (pour que ça ne se reproduise pas)

Automatiser CE-1→CE-7 en une commande exécutée **avant** de déclarer une campagne ouverte : build de l'image (ou vérification du digest), worktree propre, `sha256sum -c`, `make_datasets.py --check`, `docker run --rm image loko-eval --version`, présence du répertoire d'artefacts + gabarit. Sortie : tableau PASS/FAIL par CE, exit code global. Le protocole de validation reste inchangé — le preflight en est l'exécution outillée. La leçon de cette campagne est là : **une condition d'entrée qui se vérifie à la main finit par être découverte en échec trop tard.**

---

## Ordre d'exécution et reprise de campagne

| Étape | Items | Vérification |
|---|---|---|
| 1 | C1 → C2 (build réparé et verrouillé) | Job `build-smoke` vert |
| 2 | C4 (décision train.csv) puis C3 → C5 (jeux réalignés + check) | `--check` exit 0 |
| 3 | C7 → C8 (mocks isolés, loader déplacé, noms alignés) | Lint V0-3 vert, suite complète verte |
| 4 | C6, C9, C10 | Audit vert, preflight exécutable |
| 5 | Nouveau tag `v0.3.1`, `preflight.py` PASS intégral | — |
| 6 | **Rejouer la campagne depuis V0-1** (protocole inchangé) | Rapport gabarit annexe A |

**Definition of done** : les 10 items verts en CI ; `tools/preflight.py` PASS sur `v0.3.1` ; campagne R0+R1 rejouée intégralement. À noter pour le suivi : c'est la deuxième fois qu'une consigne écrite (constraints appliquées, audit npm bloquant) est livrée partiellement — les gardes CI de ce plan transforment chacune de ces consignes en vérification mécanique, ce qui est la seule réponse durable.
