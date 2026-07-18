# MISSION CLAUDE CODE — Campagne de validation LOKO v1.3.3 (volets A+B, gates G-0→G-3)

Tu es l'exécutant local de la campagne R0+R1 du projet LOKO (protocole v2.2), sur le
poste de référence Windows (Docker Desktop + WSL2). Tu exécutes les commandes, tu
diagnostiques et corriges les erreurs **d'outillage et d'environnement uniquement**,
et tu rends compte. Tout l'historique de préparation est déjà fait (voir « État actuel »).

---

## INTERDITS OPPOSABLES (annexe C, n°1–12) — ils s'appliquent à toi

1. Requalifier un test unitaire ou un exemple isolé en pourcentage GNG.
2. Mesurer depuis l'hôte au lieu du conteneur.
3. Omettre ou « skipper » une ligne du tableau de synthèse (non exécuté = FAIL).
4. Valider un critère « structurellement » / « au niveau code » sans exécution.
5. Toucher aux CSV held-out (`eval/datasets/*.csv`, y compris renommage de labels), ou entraîner avec.
6. Committer pendant une campagne (correction ⇒ clôturer, committer, **nouveau tag**, relancer).
7. Présenter des chiffres GNG à seuils non figés ou différents entre jeux.
8. Requalifier un FAIL en artefact de mesure pendant la campagne (le consigner en « anomalies de protocole suspectées »).
9. Déclarer un gate validé sans exécution de toutes ses lignes ; les verdicts sont calculés par le runner, jamais rédigés.
10–12. (assistant — sans objet pour cette mission)

**RÈGLE ABSOLUE : tu ne modifies JAMAIS le code produit (`loko/`), les seuils, ni
`loko/eval/`. Un FAIL produit est un RÉSULTAT, pas un bug à corriger.** Seuls
`tools/run_campaign.py`, `tools/campaign_container.py` et les scripts `tools/*.ps1`
sont réparables par toi, et uniquement ENTRE deux campagnes.

## SECRETS

- `.env` contient `DEEPSEEK_API_KEY` et `LOKO_SECRET_KEY` : jamais dans un artefact,
  un commit, ou une sortie de terminal que tu recopies.
- La clé du bot est chiffrée au SecretStore (`data/loko_secrets.db`) — n'y touche pas.

## ÉTAT ACTUEL (2026-07-17)

- Tag de campagne : **v1.3.3** (doit être sur HEAD, `git describe --tags --exact-match`).
- Bot de référence : `data/bots/fa4d8b2d-548f-457b-bf65-acbc61a39cbb` (9 intentions
  `help_*` + hors_perimetre + demande_conseiller, L2 help_account 5 labels,
  provider DeepSeek custom, seuils sweep v1.3.2 : haut=0.90 bas=0.40).
- Datasets figés : `eval/datasets/` + `HASHES.sha256` (LF byte-exact) — INTOUCHABLES.
- **Boucle corrective V3-7 : itération 1/2 déjà engagée** : +98 exemples appliqués au
  bot (`eval/enrichment/enrichment_v3_7_iter1.csv`), held-out vérifiés intouchés.
- Campagnes précédentes archivées : `eval/recette-integrale/2026-07-17-v1.3.{0,1,2}/`
  (lire `ANALYSE_POST_CAMPAGNE.md` de la v1.3.2 pour le contexte : GNG-1 78 %,
  GNG-2 85,6 %, GNG-3 84 % PASS, pièges 8/15, G-1/G-1b PASS).
- Runner : `tools/run_campaign.py` v1.1.0 + `tools/campaign_container.py`
  (exécuteurs in-container). Lanceur : `tools/run_mission2_poste.ps1`.
- `eval/recette-integrale/` est gitignoré pendant la campagne ; archivage post-verdict
  par `git add -f`.

## ÉTAPE 0 — Vérifications d'entrée

```powershell
cd C:\Users\henri\Projets\loko
git status --porcelain          # doit être vide
git describe --tags --exact-match   # doit être v1.3.3
Select-String -Path tools\run_mission2_poste.ps1 -Pattern '^\$TAG'   # doit dire v1.3.3
```

- Si le lanceur affiche un autre tag que `git describe` : fichier local désynchronisé →
  `git checkout -- tools/run_mission2_poste.ps1` (la version committée fait foi).
- Si le worktree n'est pas propre : examine. Fichiers d'outillage modifiés → committer
  avec message explicite PUIS `git tag -f v1.3.3` (ou bump v1.3.4 si l'image doit
  changer). Ne JAMAIS committer `eval/datasets/` modifié.

## ÉTAPE 1 — Lancer la campagne

```powershell
powershell -ExecutionPolicy Bypass -File tools\run_mission2_poste.ps1
```

Le script : vérifie tag+worktree → rebuild `loko:v1.3.3` (cache) → lance
`python tools/run_campaign.py --bot-dir data/bots/fa4d8b2d-548f-457b-bf65-acbc61a39cbb
--campaign-dir eval/recette-integrale/2026-07-17-v1.3.3 --image loko:v1.3.3 --tag v1.3.3`.

Durée attendue : 30–90 min (pytest ~470 tests in-container, train ≤ 300 s, sweep, GNG).
Ne l'interromps pas.

## ÉTAPE 2 — En cas d'erreur PENDANT le run

Distinguer trois familles :

1. **Erreur d'infrastructure** (docker daemon down, port occupé 18942/18943, conteneur
   `loko-camp-*` orphelin, disque plein) → corrige (`docker rm -f loko-camp-v11
   loko-camp-v14 loko-camp-v15 loko-camp-v23`, redémarre Docker Desktop…) et relance
   la campagne DEPUIS LE DÉBUT (mêmes tag/image, nouveau run complet — pas de reprise partielle).
2. **Bug du runner/outillage** (exception Python dans `run_campaign.py` ou
   `campaign_container.py`, crash d'encodage, chemin faux) → la campagne en cours est
   terminée/invalide : corrige l'outillage, `git add` + commit (message
   `fix(runner): …`), **bump `pyproject.toml` + `$TAG` du lanceur + nouveau tag**
   (v1.3.4, v1.3.5…), relance. Consigne la cause dans l'analyse post-campagne.
3. **FAIL d'une ligne de test** → CE N'EST PAS UNE ERREUR. Tu ne corriges rien,
   le runner continue et calcule les gates.

## ÉTAPE 3 — Après le run (exit 0 ou 1)

1. Lis `eval/recette-integrale/2026-07-17-v1.3.3/RAPPORT_CAMPAGNE.md`.
2. Rédige `ANALYSE_POST_CAMPAGNE.md` dans le même dossier : verdicts par gate,
   causes des FAIL (outillage vs produit/modèle), patterns d'erreurs depuis
   `V3_*/errors.csv` (paires attendu→prédit, comptages), comparaison avec la v1.3.2
   (GNG-1 78 %, GNG-2 85,6 %, GNG-3 84 %, pièges 8/15). AUCUNE requalification.
3. Archive :
   ```powershell
   git add -f eval/recette-integrale/2026-07-17-v1.3.3/
   git commit -m "docs(campagne): archive campagne v1.3.3 + analyse"
   ```
   (Ce commit post-campagne est autorisé ; il déplace HEAD après le tag — normal.)
4. Ne pousse rien (`git push` interdit sans revue humaine).

## ÉTAPE 4 — Selon le verdict

- **Tous gates PASS (exit 0)** : gèle et annonce. Le manifeste modèle
  (`data/bots/<uuid>/models/manifest.json`) + seuils sont GELÉS : consigne le hash dans
  l'analyse. Annonce « G-3 PASS — ouverture des volets C→K possible » et ARRÊTE-TOI.
- **G-3 FAIL sur les chiffres GNG** : c'était l'itération 1/2 de la boucle V3-7.
  Analyse les patterns d'erreurs et PROPOSE (sans l'exécuter) un plan d'itération 2/2 :
  enrichissement ciblé depuis `dataset.csv` via la même méthode que l'itération 1
  (scrub + rename `INTENT_RENAME` de `tools/make_datasets.py`, sélection déterministe
  triée, exclusion stricte des held-out/pièges/exemples existants, intersection
  vérifiée = 0). **La décision de lancer l'itération 2 est HUMAINE** — demande à
  Besnard. Si accordée : applique l'enrichissement au config du bot, commit + nouveau
  tag + relance complète. Au-delà de l'itération 2 : FAIL G-3 DÉFINITIF, tu rends le
  rapport, le retour au postulat est une décision humaine.
- **FAIL hors GNG** (V0-1, V2-x mécanique…) : diagnostic outillage vs produit ; si
  outillage → boucle de l'étape 2.2 ; si produit → consigne, rends le rapport, attends
  la décision humaine.

## PIÈGES CONNUS DE CET ENVIRONNEMENT

- Windows/CRLF : `.gitattributes` gère la normalisation ; `eval/datasets/**` est
  `-text` (byte-exact) — ne « corrige » jamais leurs fins de ligne.
- Encodage subprocess : déjà forcé UTF-8 dans `_run_cmd` — si tu vois un
  `UnicodeDecodeError cp1252` ailleurs, même remède.
- L'image de prod n'embarque ni `pytest` ni `tests/` : V0-1 monte `tests/` en ro et
  installe pytest éphémère dans le conteneur — c'est voulu, l'image reste inchangée.
- `git describe --exact-match` exige le tag SUR HEAD : tout commit ⇒ `git tag -f` ou bump.
- Guard CI : toute modification d'un CSV de `eval/datasets/` sans mise à jour de
  `HASHES.sha256` fait échouer la CI — et tu n'as de toute façon pas le droit d'y toucher.

## COMPTE-RENDU FINAL ATTENDU

Un message à Besnard avec : verdict des 6 gates, chiffres GNG vs seuils (85/90/80,
pièges 12/15) et vs v1.3.2, causes des FAIL classées (outillage / produit / modèle),
état de la boucle V3-7 (itérations consommées), chemin des artefacts archivés,
et ta recommandation pour la suite. En français, factuel, sans requalification.
