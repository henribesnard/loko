# RAPPORT — Mission « préparation de campagne » LOKO — 2026-07-17

**Exécutant** : agent (Cowork) · **Aucune campagne lancée** (conforme au mandat).
**HEAD en fin de mission** : `d18df72` (re-figeage) + commit hygiène `.gitignore` — branche `main`.
**Bot de référence** : `fa4d8b2d-548f-457b-bf65-acbc61a39cbb` (data/bots/, non versionné).

## Synthèse P1→P6

| Étape | Verdict | Artefact |
|---|---|---|
| P1 — Enquête datasets | **FAIT** | `01_worktree_avant.txt`, `02_disparition_datasets.txt`, `03_note_enquete.md` |
| P2 — Re-figeage (CAS B, confirmé par Besnard) | **FAIT** | `04_decision_datasets.md`, commit `d18df72` |
| P3 — Assainissement worktree | **FAIT** | `05_worktree_apres.txt`, `.gitattributes` |
| P4 — Bot de référence + conformité CE-9 | **FAIT** | `CE-9_conformity.json` (18/18 PASS) |
| P4 — Ping LLM réel (CE-6/CE-8) | **BLOQUÉ** | Clé LLM + machine de référence requises (voir « Points bloqués ») |
| P5 — Image + tag | **BLOQUÉ** | Docker indisponible dans l'environnement de l'agent |
| P6 — Fiche machine de référence | **BLOQUÉ** | À produire sur la machine de référence |

## Faits saillants

**P1.** Les datasets figés et `make_datasets.py` ont été supprimés **volontairement** le 10/07/2026 (`2c8f58d`, `c95035d`) lors de la purge des références client. Récupérables depuis git ; les hash historiques correspondaient après conversion CRLF (calculés sur checkout Windows).

**P2 (CAS B, tracé comme exception légitime à l'interdit n°5 — re-figeage inter-campagnes).** Jeux régénérés dé-clientélisés : marque → « mutuelle », IDs d'intention → génériques `help_*` (cohérence avec l'outillage post-scrub), écriture LF native, datasets `-text` (byte-exact). Comptes : train 125, held-out 100/125/100, pièges 15. `--check` OK (hash, intersections vides, IDs T01–T15). **Perte de comparabilité E1 assumée** : les chiffres v0.3.x ne sont plus comparables.

**P3.** Les « 75 fichiers modifiés » étaient **tous des artefacts CRLF** — 0 diff de contenu réel (preuve par sha256 après suppression des `\r` sur les 75). Aucun commit de contenu depuis ces fichiers ; remède structurel par `.gitattributes`. Aucun secret tracké (`git ls-files data/` vide) ; `data/` désormais explicitement ignoré. **Garde H4 présente en CI** (`guard-datasets`, ci.yml:17) ainsi que `guard-client-mentions`.

**P4.** `setup_campaign_bot.py --offline` → bot 9 intentions (7 métier `help_*` + `hors_perimetre` + `demande_conseiller` 15 exemples intégrés) + L2 `help_account` 5 labels. `check_bot_conformity.py` : **CE-9 PASS 18/18**.

## Points bloqués (à exécuter sur la machine de référence, par toi ou en session pilotée)

1. **Clé LLM** (CE-6/CE-8) : configurer le provider réel (jamais dans un fichier versionné ni un artefact), puis prouver le ping 5 tokens temp 0 avec TTFB.
2. **P5 — Image + tag** :
   ```
   docker build -t loko:v1.3.0 .
   docker inspect --format='{{.Size}}' loko:v1.3.0        # ≤ 1,6 Go, par digest
   git tag v1.3.0 && (triple vérification : tag / loko --version / OpenAPI) > 06_version.txt
   ```
3. **P6 — Fiche machine** : CPU, RAM, OS, WSL2/natif, version Docker → `07_machine_reference.txt`.

## Anomalies signalées (non corrigées — hors périmètre mission)

1. `tools/audit_label_mapping.py` et `tools/preflight.py` référencent encore les labels français pré-scrub (leftovers ; non appelés par `run_campaign.py`). À migrer avant usage.
2. La garde CI `guard-datasets` surveille `data/**` mais **pas `eval/datasets/**`** : une modification des held-out committée sans mise à jour de `HASHES.sha256` ne serait pas attrapée par la CI (l'attrape : `make_datasets.py --check` et le hash CE-3 du runner). À renforcer si souhaité.
3. Défaut historique du générateur : le module `csv` de Python écrit CRLF par défaut — cause racine des hash CRLF historiques. Corrigé dans le générateur re-figé (`lineterminator="\n"`), signalé pour mémoire.
4. Incident technique en cours de mission : `index.lock` périmé puis index git corrompu (FS monté) — index reconstruit depuis HEAD, aucune perte (fsck : seuls des objets dangling anodins).
5. Dry-run antérieur : `pip-audit` absent de l'environnement d'exécution de l'agent (V0-4 non significatif hors conteneur).

## Critère de succès CE-1→CE-11 (projection si le runner tournait maintenant, sur la machine de référence)

| CE | État projeté |
|---|---|
| CE-1 worktree/CI | PASS après commit des artefacts de mission (ce dossier) — CI à revérifier sur le tag |
| CE-2 tag | **À faire** (P5, nouveau tag proposé v1.3.0) |
| CE-3 datasets/hash | PASS (`sha256sum -c` 5/5 OK, forme LF byte-exacte) |
| CE-4 intersection | PASS (`--check` : intersections vides) |
| CE-5 loko-eval | PASS (importable — version à revérifier in-container) |
| CE-6/CE-8 LLM | **BLOQUÉ** (clé + ping sur machine de référence) |
| CE-7 miroir FAQ | Hors périmètre mission (volet C) — non préparé ici |
| CE-9 bot | **PASS** (18/18, artefact joint) |
| CE-10 secrets serveur | À poser au boot sur machine de référence |
| CE-11 squelette rapport | Généré par le runner au lancement |

**Conclusion** : dépôt prêt côté datasets/outillage/bot ; la campagne (mission 2) ne peut démarrer qu'après P5/P6 + clé LLM sur la machine de référence, et revue humaine de ce rapport.

---

## Addendum — Compléments validés par Besnard (2026-07-17, après revue)

| Complément | État | Artefact |
|---|---|---|
| Diff de preuve du re-figeage | **FAIT** | `08_diff_refigeage.md` (générateur c95035d~1→d18df72 ; datasets 2c8f58d~1→d18df72 ; marque : 37→0 occurrences ; hash avant/après) |
| Garde CI `eval/datasets/**` | **FAIT** | `ci.yml` : modification d'un CSV figé sans mise à jour de `HASHES.sha256` → FAIL + vérification `sha256sum -c` systématique à chaque CI |
| Vérification `preflight.py` | **FAIT** | Migré vers les IDs `help_*` ; exécuté : CE-4/CE-5/CE-6/CE-7 PASS (échecs restants = arguments tag/image/bot non fournis, attendus) |
| Provider LLM DeepSeek | **FAIT (config) / ping délégué au poste** | Clé lue depuis `.env` (jamais copiée), chiffrée au SecretStore (Fernet, `ref_91d9…`), `LOKO_SECRET_KEY` générée et ajoutée à `.env` (compose la charge) ; bot : `provider_source=custom`, `preset=deepseek`, `model=deepseek-chat`, `base_url=https://api.deepseek.com`, `api_key_set=true`. Le proxy de l'environnement agent bloque `api.deepseek.com` (403) — le ping TTFB (CE-8) s'exécute sur le poste via le script ci-dessous, là où la mesure est recevable. |
| P5/P6 sur le poste | **PRÊT À LANCER** | `tools/prepare_campagne_poste.ps1` : ping CE-8 + build + inspect ≤ 1,6 Go + tag v1.3.0 + triple vérification (`pyproject` bumpé à 1.3.0) + fiche machine → `CE-8_ping.txt`, `06_version.txt`, `07_machine_reference.txt` |

Anomalie restante non corrigée (hors demande) : `tools/audit_label_mapping.py` toujours sur labels français pré-scrub.
