# Analyse post-campagne — v1.3.2 (runner 1.1.0+fixes) — 2026-07-17

**Verdict runner (opposable) : NON VALIDE** — CE 9/9, G-1 **PASS 4/4 (éliminatoire)**, G-1b **PASS**, G-0 4/5, G-2 2/6, G-3 4/7.

## Acquis majeurs
- **G-1/G-1b : les éliminatoires runtime passent** (boot+health, garde no-mock, fail-fast loader, CRITICAL au boot prouvé au niveau runtime, service sous --network none).
- **Premier train complet réel** : manifeste gelé (`8aca9bca…`), L2 5 labels, **atomicité kill-en-vol PASS**, reproductibilité V3-6 **PASS** (2 runs identiques).
- **Premiers chiffres GNG réels** (seuils sweep haut=0,90 bas=0,40) : GNG-1 78 % (78/100), GNG-2 85,6 % (107/125), **GNG-3 84 % PASS**, pièges 8/15.

## FAIL et causes
| Ligne | Cause | Nature |
|---|---|---|
| V0-1 | `pytest` et `tests/` absents de l'image de prod | Outillage : monter tests/ + installer deps test éphémères |
| V2-1/V2-4 | Crash runner hôte : `UnicodeDecodeError cp1252` (subprocess Windows sans encoding) — le train lui-même a réussi | Bug runner, corrigé (`encoding="utf-8"`) |
| V2-6 | P95=230 ms vs contre-mesure 50,7 ms (écart 78 %) : deux boucles successives ≠ contre-mesure ; caches froids sur la 1re | Méthode de mesure corrigée (double horloge sur le même appel, warmup 50) |
| V3-1/V3-2/V3-4 | Vrais signaux modèle (voir patterns) | Produit/modèle → **V3-7** |

## Patterns d'erreurs (V3_heldout_metier/errors.csv, 22 erreurs)
- **12/22 : aspiration vers `hors_perimetre`** (help_documents ×6, help_leave ×4…) → sous-couverture lexicale des intentions métier.
- help_documents ↔ help_account ×3.
- Pièges : géométrie de seuils (routes attendues à scores 0,79–0,85 < seuil_haut 0,90 → clarification ; T13 hors-scope à 0,70 > seuil_bas 0,40 → non rejeté). Attendu : le re-train affine les scores puis re-sweep.

## Boucle corrective V3-7 — tableau des itérations
| Itération | Action | Contenu | Held-out |
|---|---|---|---|
| **1/2 (engagée)** | Enrichissement train + re-sweep + re-run complet à la campagne v1.3.3 | `eval/enrichment/enrichment_v3_7_iter1.csv` : +98 exemples — 86 issus de la source (scrub+rename, sélection déterministe triée) ciblant help_documents(15), help_leave(15), help_contact(10), help_transfer(10), help_account(10), help_billing(8), help_cancellation(8), hors_perimetre(10) + 12 variantes rédigées `demande_conseiller` (pool source épuisé par le held-out 125/125) | **Intouchés — intersection contrôlée = 0** |
| 2/2 | (réserve) | — | — |

Au-delà de 2 itérations : FAIL G-3 définitif → retour au postulat (décision humaine).

## Anomalie produit à suivre (hors campagne)
L'image de production n'embarque ni `pytest` ni `tests/` : la lettre de A-1 (« suite complète in-container ») impose des deps de test au run — choix assumé : montage `tests/` ro + install éphémère dans le conteneur éphémère, image de prod inchangée.
