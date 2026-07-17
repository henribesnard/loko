# P2 — Décision de re-figeage des datasets (CAS B)

**Date** : 2026-07-17 · **Décideur** : Besnard (confirmation explicite en session) · **Exécutant** : agent (Cowork)

## Décision

**CAS B — re-figeage officiel dé-clientélisé.** Le CAS A (restauration à l'identique) était techniquement possible (cf. `03_note_enquete.md`) mais aurait réintroduit dans le dépôt les données client MGEN purgées volontairement le 10/07/2026. Décision complémentaire : `HASHES.sha256` recalculé sur la forme canonique **LF** (celle des blobs git et du conteneur), les hash CRLF historiques restant en référence dans la note d'enquête.

## Motif

Purge des références client maintenue (commits `2c8f58d`, `c95035d`, `0c00423`) ; la garde CI `test_no_client_mention.py` scanne `tools/` et aurait échoué sur le générateur restauré tel quel.

## Ce qui a été fait (exception légitime à l'interdit n°5 — re-figeage inter-campagnes, hors campagne)

1. `tools/make_datasets.py` restauré depuis `c95035d~1` (version post-C1-C10, corrections M4 incluses), puis **dé-clientélisé** :
   - fonction `scrub_client()` : remplacement insensible à la casse du nom client → « mutuelle », appliqué à chaque verbatim source au chargement ; collapse des doublons « mutuelle mutuelle » ;
   - 11 littéraux du postulat §2 et des pièges T03/T07 remplacés à la main (T03 → « accès à mon compte de la mutuelle » pour éviter une collision train×pièges) ;
   - logique, seed (42), tris et comptes **inchangés**.
2. Régénération depuis `dataset.csv` (source client, non versionnée, inchangée) :
   train 125 · heldout_metier 100 · heldout_conseiller 125 · heldout_horsscope 100 · pieges 15.
3. Écriture **LF native** dans le générateur (`csv.DictWriter(..., lineterminator="\n")` — le défaut du module `csv` de Python est CRLF, cause historique des hash CRLF), datasets marqués `-text` dans `.gitattributes` (byte-exact sur toutes plateformes, vérifiable in-container). `HASHES.sha256` final (octets LF) :

```
1200de4b01be1b4debec0a7499f1e0fc15a7499dd9d4198ac01bf65eb4b89499  heldout_conseiller.csv
da82b54eff9957a534cfd9b83a842c5da0c8a5da52f0941d5de1f0465e6b8c95  heldout_horsscope.csv
f0400c407a789943718ac3651d41a9be07974b605f71488bb9372fbd317ca7a2  heldout_metier.csv
52ca4c00e3740c8ae219d3a41257025789f6603b5d5b5b41d654cfc2ec65e09f  pieges.csv
6f61cd022a075f914dc79332b16afe9dac95776becfabd93ad5d19db0115d11d  train.csv
```

4bis. **Renommage des IDs d'intention** (cohérence avec l'outillage post-scrub — `check_bot_conformity.py`, `setup_campaign_bot.py`, `run_campaign.py` attendent les IDs génériques) : `services_en_ligne→help_account`, `justificatif_droits→help_documents`, `arret_travail→help_leave`, `cotisations→help_billing`, `changement_coordonnees→help_contact`, `teletransmission_noemie→help_transfer`, `resiliation→help_cancellation`. Appliqué au chargement (`INTENT_RENAME`), aux clés du postulat §2, aux `expected_behavior` des pièges. `parler_conseiller` (held-out conseiller) et les intentions hors-scope conservés tels quels (le runner évalue GNG-2/GNG-3 par type de décision, pas par nom). Validation de chaîne : `setup_campaign_bot.py --offline` + `check_bot_conformity.py` → **CE-9 PASS 18/18**.

⚠️ Anomalie signalée (non corrigée, hors périmètre mission) : `tools/audit_label_mapping.py` et `tools/preflight.py` référencent encore les anciens labels français — leftovers du scrub, non appelés par le runner.

4. Vérifications : `make_datasets.py --check` **OK** (présence, comptes exacts, hash, **intersections train/held-out et pièges/held-out vides**, syntaxe `expected_behavior`, IDs T01–T15) ; scan client sur les 6 fichiers générés : **0 occurrence**.

## Conséquence assumée

**Perte de comparabilité avec le plateau E1.** Les textes des held-out diffèrent des jeux v0.3.x (marque remplacée, tris de sampling affectés). Les chiffres GNG des campagnes passées (v0.3.x) **ne sont plus comparables** aux futurs chiffres et ne seront pas présentés comme tels.

## Versionnement

Datasets, `HASHES.sha256` et `tools/make_datasets.py` committés (commit dédié « re-figeage » — voir `00_RAPPORT_PREPARATION.md`).
