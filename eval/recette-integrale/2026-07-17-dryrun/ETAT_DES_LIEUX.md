# État des lieux — Recette intégrale LOKO (dry-run diagnostic)

**Date** : 2026-07-17 · **Tag** : v1.2.2 · **Runner** : run_campaign.py v1.0.0 (protocole v2.2)
**Statut** : diagnostic **non opposable** (exécuté hors conteneur, hors machine de référence — interdit n°2).

## Résultat du dry-run (CE + V0)

| Gate | Verdict | Détail |
|---|---|---|
| CE | FAIL (3/9) | CE-2, CE-6, CE-7 PASS |
| G-0 | FAIL (1/5) | seul V0-3 (anti-mock) PASS |
| G-1 / G-1b / G-2 / G-3 | NON EXÉCUTÉ = FAIL | dry-run : V1+ non lancés |

## Blocages réels (à corriger dans le repo)

| # | Blocage | Ligne | Action |
|---|---|---|---|
| 1 | Worktree sale : **75 fichiers modifiés** non commités sur v1.2.2 | CE-1 | Committer, poser un nouveau tag, redémarrer la campagne dessus |
| 2 | `eval/datasets/` absent : pas de `HASHES.sha256`, ni held-out (métier 100, conseiller 125, hors-scope 100, pièges 15) | CE-4 | Restaurer les datasets figés + vérifier les hash |
| 3 | `make_datasets.py` introuvable → contrôle d'intersection train/held-out impossible | CE-5 | Restaurer le script |
| 4 | Aucun bot de référence (`data/bots/<uuid>/config.json`) : conformité 9 intentions L1 + 5 labels L2 invérifiable, ping LLM impossible | CE-8, CE-9 | Recréer le bot de référence (`tools/setup_campaign_bot.py`) + configurer le provider LLM réel |
| 5 | Pas d'image Docker taguée fournie | CE-3, V0-5 | Builder l'image `[server,ml]`, la taguer, passer `--image` au runner |

## FAILs artefacts d'environnement (sandbox sans Docker/ML — non significatifs)

- V0-1 : pytest absent du sandbox
- V0-2 : torch/SetFit absents
- V0-4 : pip-audit absent (npm audit : **0 vulnérabilité**)

Ces lignes doivent être rejouées **in-container sur la machine de référence** pour valoir.

## Prochaine étape recommandée

1. Committer/nettoyer le worktree → nouveau tag.
2. Restaurer `eval/datasets/` + `make_datasets.py`, vérifier `HASHES.sha256`.
3. Recréer le bot de référence et poser la clé LLM (CE-6/CE-8).
4. Builder l'image et relancer sur la machine de référence :
   `python tools/run_campaign.py --bot-dir data/bots/<uuid> --campaign-dir eval/recette-integrale/<date> --image loko:<tag> --tag <tag>`
5. Volets C→K : suivre le protocole après G-3 PASS (gel du modèle).

## Artefacts

`RAPPORT_CAMPAGNE.md`, `campaign_report.json`, `CE-*.txt`, `V0-*.txt` dans ce dossier.
