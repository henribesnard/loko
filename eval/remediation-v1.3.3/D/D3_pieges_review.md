# D3 — Preuve re-figeage v2 + revue pièges

## Re-figeage v2 : validation

- `make_datasets.py --check eval/datasets/` : PASS
- `grep -c mutuelle eval/datasets/*.csv` : 0 occurrences
- `diff_refigeage.py --summary-only` : 0 rows with 'mutuelle'
- `test_no_client_mention.py` : 2/2 PASSED

## Revue des 15 pièges (pieges.csv)

| ID  | Texte (post-scrub) | Comportement attendu | Verdict |
|-----|----|----|---------|
| T01 | je souhaiterais débloquer mon compte Ameli | route:help_account | OK — compte_bloque direct |
| T02 | modification mot de passe | route:help_account | OK — mot_de_passe_oublie direct |
| T03 | accéder au compte Santelis | clarify_intra:help_account | OK — sous-motif incertain, clarification intra |
| T04 | RIB coordonnées bancaires | clarify_inter:help_contact\|help_billing | OK — ambigu contact/cotisations |
| T05 | changement de banque pour les prélèvements... | clarify_inter:help_contact\|help_billing | OK — zone grise RIB/prélèvement |
| T06 | attestation de paiement | clarify_inter:help_leave\|help_billing\|help_documents | OK — triple ambiguité |
| T07 | attestation de droits Santelis | route:help_documents | OK — documents direct |
| T08 | complément de salaire arrêt longue maladie | route:help_leave | OK — leave direct |
| T09 | est-ce qu'il y a une télétransmission... Santelis | route:help_transfer | OK — transfer contrôle positif |
| T10 | comment résilier mon ancien contrat Santelis | route:help_cancellation | OK — cancellation direct |
| T11 | Je préfère parler à un humain | escalate:demande_explicite | OK — transverse conseiller |
| T12 | déclarer un accident de ski | reject | OK — hors périmètre |
| T13 | bilan bucco-dentaire détartrage | reject | OK — hors périmètre |
| T14 | Noemie | route:help_transfer | OK — mot unique robustesse |
| T15 | la référence iban et le numéro de carte vitale... | route:help_account | OK — piège multi-concept |

## Conclusion

15/15 pièges validés. Le remplacement de "mutuelle" par "Santelis" n'altère pas
la sémantique des cas limites — les comportements attendus restent cohérents.
