# LOT 0.2 -- Inventaire des donnees reelles (loko.wezon.fr)

**Date** : 2026-08-01
**Operateur** : Claude Code (Opus 4.6)
**Version deployee** : v1.2.2 (image `loko-loko`, tag absent du conteneur)
**Methode** : requetes sqlite3 depuis l'hote VPS via le volume Docker `loko_loko-data`

---

## Comptes et utilisateurs

| Element | Valeur |
|---------|--------|
| Comptes (`accounts`) | **1** |
| Org name | `dogfood-mutuelle-v1` |
| Plan | `trial` |
| Date creation | 2026-07-12 13:10 UTC |
| Utilisateurs (`users`) | **1** |
| Email | `besnard.hounwanou@gmail.com` |
| Role | `owner` |
| Email verifie | **Oui** (2026-07-19 10:46 UTC) |

## Sessions

| Element | Valeur |
|---------|--------|
| Sessions totales | 2 |
| Sessions < 30 jours | 2 |
| Derniere session | 2026-07-13 05:55 UTC |
| Tokens email emis | 1 |

## Bots

| Bot ID | Sessions chat | Documents (knowledge) |
|--------|--------------|----------------------|
| `53a0e5d9-1ba2-4aab-8ed1-6896f08ddb56` | 5 | 10 |
| `438d3466-f4c3-40d6-9290-8102b27bcf2d` | 0 | 0 |

## Bases de donnees

| Fichier | Taille | Contenu |
|---------|--------|---------|
| `loko_accounts.db` | 48 Ko | comptes, users, sessions, email_tokens |
| `analytics.db` | 40 Ko | events (1 evenement), daily_rollups |
| `loko_releases.db` | 20 Ko | (non inspecte) |
| `loko_quota_usage.db` | 12 Ko | (non inspecte) |
| `loko_secrets.db` | 12 Ko | table `secrets` : **0 entree** |

## Verdict

| Critere | Evaluation |
|---------|------------|
| Donnees reelles (clients tiers) | **NON** |
| Comptes non maitrises | **NON** -- seul compte = Besnard (proprietaire) |
| Donnees sensibles exposees | **NON** -- 10 documents de knowledge, 5 sessions de test |
| Comptes fantomes (exploit P4) | **AUCUN** -- 0 compte non verifie |

**Verdict : donnees reelles = NON.** Le VPS ne contient qu'un compte de dogfooding
proprietaire, verifie par email. Aucune trace d'exploitation du bug P4.

---

## Consequence sur LOT 0.3 (rotation des secrets)

La rotation des secrets n'est **pas urgente** (pas de comptes parasites, pas de donnees
tierces). Elle reste recommandee avant tout deploiement public futur, mais ne bloque
plus le chemin critique.

Le lot 0.3 est reclasse en **optionnel** pour cette iteration.
