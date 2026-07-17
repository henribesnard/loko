# Analyse post-campagne — v1.3.1 (runner 1.1.0) — 2026-07-17

**Verdict runner (opposable) : NON VALIDE** — G-0 4/5, G-1 3/4, G-1b PASS, G-2 0/6, G-3 0/7.

## Signaux positifs (premiers verdicts in-container du produit)
- V1-1 boot serveur + health 200 · V1-2 garde no-mock (RuntimeError hors env test)
- V1-3 fail-fast loader (exception typée, zéro fallback) · **V1-5 service complet sous `--network none` (G-1b PASS)**
- V0-2 imports ML in-container (torch 2.12.1+cpu) · V0-4 pip check OK · image 1 001 MB

## Causes racines des FAIL (outillage/environnement, aucune produit)
1. **V0-1 exit 127** : binaire `pytest` absent du PATH de l'image → correctif runner : `python -m pytest`.
2. **V2-1 train exit 1** : `Permission denied: 'checkpoints'` (cwd `/app` non inscriptible pour l'utilisateur conteneur) + cache HF non inscriptible → correctif runner : `-w /tmp`, `HF_HOME=/tmp/hf`, `TRANSFORMERS_CACHE=/tmp/hf`, chemin absolu du script. Cascade : V2-2→V2-6 et tout V3 (« classifier not trained »).
3. **V1-4** : le produit logge bien en **CRITICAL** (`boot_logger.critical`, loko/main.py) et le message « Published bot unavailable at startup … STARTUP CHECK: 1/1 » est émis au boot ; le format de log par défaut d'uvicorn n'imprime pas le levelname → correctif runner : boot avec logging configuré (`%(levelname)s`) pour prouver le niveau au runtime.

## Décision
Corrections runner (aucun code produit) → tag v1.3.2 → reprise volet A (§14).
