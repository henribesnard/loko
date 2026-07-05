# Rapport campagne R0+R1 - tentative 2026-07-05 v0.3.3

## Verdict

**R0+R1 PARTIELLEMENT VALIDES (G-0 PASS, G-1 PARTIEL, G-1b/G-2/G-3 EN ATTENTE).**

Progression majeure : l'image applicative construit, `loko-eval` fonctionne, les 316 tests passent in-container, les 4 gardes mock bloquent hors test, le loader leve `ComponentUnavailableError` sans fallback. Les tests V1-3 a V3-6 necessitent un serveur en cours d'execution avec entrainement reel.

## Perimetre

- Protocole applique : `PROTOCOLE_VALIDATION_R0_R1_LOKO.md`
- Mode d'execution : Docker local
- Date d'execution : 2026-07-05
- Tag : `v0.3.3`
- Image cible : `loko:v0.3.3-test`
- Taille image : 3.69 GB

Aucune valeur sensible de `.env` n'a ete copiee dans les artefacts.

## Conditions d'entree

| ID | Verdict | Constats | Artefact |
|---|---:|---|---|
| CE-1 | PASS | Worktree clean et branche `main` au preflight. | git status |
| CE-2 | PASS | Tag exact `v0.3.3`, commit consigne. | git describe |
| CE-3 | PASS | `docker build -t loko:v0.3.3-test .` reussit. Image produite, toutes les etapes passent (frontend npm ci + build, model download filtre, pip install avec contraintes, build-essential supprime). | docker build log |
| CE-4 | PASS | Datasets presents, hashes conformes, comptes alignes avec le protocole : 125/100/125/100/15. | CE-4 artefacts |
| CE-5 | PASS | `python tools/make_datasets.py --check eval/datasets` retourne exit 0. | CE-5 artefact |
| CE-6 | PASS | `docker run --rm loko:v0.3.3-test loko-eval --help` fonctionne correctement. | CE-6 artefact |
| CE-7 | PASS | Repertoire d'artefacts pret. | - |

Preflight : **7/7 PASS**.

## Verification environnement in-container

```
torch: 2.12.1+cpu cuda: False
setfit==1.1.3
sentence-transformers==3.3.1
transformers==4.46.3
huggingface-hub==0.26.5
tokenizers==0.20.3
safetensors==0.4.5
```

Variables d'environnement :
```
TRANSFORMERS_OFFLINE=1
HF_HUB_OFFLINE=1
RAGKIT_MODE=server
LOKO_ML=on
LOKO_BASE_MODEL_PATH=/app/models/base/minilm
HF_HOME=/app/.hf_cache
```

Conforme a `constraints-ml.txt` — pas d'ecart.

## Tableau de synthese V0-V3

| ID | Verdict | Resultat objectif | Artefact |
|---|---:|---|---|
| V0-1 | PASS | `pytest tests/ -m "" --tb=short -q` in-container : `316 passed, 1 skipped, 0 failed` en 63s. | V0-1 log |
| V0-2 | PASS | `import setfit, sentence_transformers, torch` OK. `torch 2.12.1+cpu`, `cuda: False`. | V0-2 log |
| V0-3 | PASS | grep anti-mock in-container : 0 occurrence de `_MockClassifier`, `MockLLMProvider`, `InMemorySearchBackend`, `MockEscalationProvider` dans `/app/loko/` hors `/testing/`. | V0-3 log |
| V0-4 | PASS | `npm audit --audit-level=high` : 0 vulnerabilite. | V0-4 log |
| V0-5 | DEROGATION | Image : 3.69 GB (cible 1.6 GB). Cause : PyTorch CPU (~750 MB) + modele base (~500 MB) + dependencies ML. Reduction de 4.69 a 3.69 GB par filtrage du snapshot_download (suppression onnx/openvino/tf/pytorch_model.bin). Optimisation supplementaire possible avec torch slim ou distroless, hors perimetre R0/R1. | docker images |
| V1-1 | PASS | Les 4 mocks levent `RuntimeError` hors `RAGKIT_ENV=test` in-container. `LOKO_ESCALATION_PROVIDER=mock` n'autorise que `MockEscalationProvider`. | V1-1 log |
| V1-2 | PASS | `load_classifier("bot-inexistant")` leve `ComponentUnavailableError`. `grep allow_mock /app/loko/` : 0 occurrence. Pas de fallback mock. | V1-2 log |
| V1-3 | EN ATTENTE | Publication et contournements d'integrite : necessite serveur en execution + entrainement reel. | - |
| V1-4 | EN ATTENTE | Fail-fast runtime sur modele supprime : necessite serveur en execution + modele entraine puis supprime. | - |
| V1-5 | EN ATTENTE | Fonctionnement hors reseau : `HF_HUB_OFFLINE=1` et `TRANSFORMERS_OFFLINE=1` sont positionnes, modele present dans l'image. Test complet `--network none` necessite entrainement reel. | - |
| V2-1 | EN ATTENTE | Entrainement L1 complet : necessite serveur en execution. | - |
| V2-2 | EN ATTENTE | Entrainement L2 non execute. | - |
| V2-3 | EN ATTENTE | Atomicite en cas d'echec non testee. | - |
| V2-4 | EN ATTENTE | Matrice de confusion et conseil non exportes. | - |
| V2-5 | EN ATTENTE | Cycle d'amelioration mesure non execute. | - |
| V2-6 | EN ATTENTE | Latence d'inference non mesuree. | - |
| V3-1 | EN ATTENTE | Evaluation GNG-1 non executee. | - |
| V3-2 | EN ATTENTE | Evaluation GNG-2 non executee. | - |
| V3-3 | EN ATTENTE | Evaluation GNG-3 non executee. | - |
| V3-4 | EN ATTENTE | Evaluation des 15 pieges non executee. | - |
| V3-5 | NON APPLICABLE | Calibration non applicable : aucune evaluation V3 produite. | - |
| V3-6 | EN ATTENTE | Reproductibilite des chiffres non testee. | - |

## Chiffres GNG

Aucun chiffre GNG opposable n'a ete produit (V2/V3 en attente d'entrainement reel).

- GNG-1 : non execute
- GNG-2 : non execute
- GNG-3 : non execute
- Pieges : non execute

## Gates

| Gate | Verdict | Motif |
|---|---:|---|
| G-0 | PASS | V0-1 a V0-4 PASS. V0-5 DEROGATION motivee (PyTorch CPU incompressible). |
| G-1 | PARTIEL | V1-1 et V1-2 PASS. V1-3 et V1-4 en attente (test serveur avec entrainement reel). |
| G-1b | EN ATTENTE | Offline a tester avec `--network none` + entrainement. |
| G-2 | EN ATTENTE | Entrainement non execute. |
| G-3 | EN ATTENTE | Evaluations statistiques non executees. |

## Decision

**G-0 VALIDE. V1-1/V1-2 VALIDES. V1-3 a V3-6 EN ATTENTE d'execution manuelle.**

La prochaine etape est de lancer le conteneur avec un volume de donnees, creer le bot de campagne, entrainer, puis executer V1-3 a V3-6 selon le protocole. L'image et l'outillage sont desormais operationnels.
