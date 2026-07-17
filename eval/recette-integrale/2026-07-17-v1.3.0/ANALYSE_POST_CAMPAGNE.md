# Analyse post-campagne — 2026-07-17 — tag v1.3.0 (commit a89cac3)

**Verdict runner (inchangé, opposable) : NON VALIDE** — G-0/G-1/G-1b/G-2/G-3 FAIL.
Analyse rédigée APRÈS clôture de campagne ; aucun verdict requalifié (interdit n°8).

## Anomalies de protocole suspectées (complément à la section du rapport)

1. **V0-1 mesuré depuis l'hôte** (violation interdit n°2 par le runner v1.0.0) : la trace pytest
   montre des chemins Windows (`C:\Users\henri\AppData\...`, `tests\bot\...`). De plus l'exécution
   s'est arrêtée au 1er échec (67 tests sur ≥ 470). L'unique échec (`TestSetFitIntegration::
   test_train_and_classify`) est un `SetFitModel.from_pretrained` qui tente un téléchargement HF
   sur l'hôte — in-container le modèle est embarqué (V1-5 le vérifie).
2. **V0-4** : `pip-audit`/`npm` introuvables sur l'hôte (WinError 2) — même cause racine.
3. **V1-1→V2-6** : runner v1.0.0 marque « requires running container or manual execution » —
   ces lignes ne sont pas orchestrées par le runner : NON EXÉCUTÉ = FAIL, conforme mais
   mécanique.
4. **V3-0→V3-6** : « Level 1 classifier not trained » — conséquence directe de l'absence de V2
   (aucun entraînement effectué dans cette campagne).

## Conclusion d'analyse

Le NO-GO de cette campagne reflète l'**incomplétude du runner v1.0.0** (mesures V0 côté hôte,
V1/V2 non automatisés), pas un défaut produit démontré. Aucun signal produit négatif :
CE 9/9 PASS, 66/67 tests hôte verts, imports ML in-container OK (torch 2.10.0+cpu), image
1 001 MB ≤ 1,6 Go, anti-mock 0 occurrence.

## Proposition pour décision humaine (correction inter-campagnes, §14 : nouveau tag puis reprise volet A)

Remédiation outillage (aucun code produit) :
- R1 : V0-1/V0-4 exécutés **in-container** (`docker run --rm loko:<tag> pytest tests/ …`, `pip-audit` in-container), sans `-x` (suite complète).
- R2 : orchestration V1-1→V1-5 (boot serveur in-container, garde no-mock, intégrité loader, log CRITICAL, `--network none`).
- R3 : orchestration V2-1→V2-6 (train in-container ≤ 300 s via l'API/`train_bot_offline.py`, atomicité, cycle d'amélioration, latence P95).
- R4 : V3 enchaîné après V2 (modèle présent), sweep V3-0 → seuils figés → GNG.
Puis : nouveau tag (v1.3.1), relance campagne complète depuis le volet A.
