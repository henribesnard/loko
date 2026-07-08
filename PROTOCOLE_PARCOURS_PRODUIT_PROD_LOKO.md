# ✅ LOKO — Protocole de vérification du parcours produit complet en production (loko.wezon.fr)

> **Version** : 1.0 — 8 juillet 2026
> **Destinataire** : Claude Code (exécution) — vérification que le produit déployé sur `https://loko.wezon.fr` offre le parcours self-serve complet spécifié par la spec de cadrage v1.0 (§10 wizard, §A.3 machine à états) et `SPECS_DEV_LOKO_BOT.md`.
> **Nature** : recette de parcours produit (piste A / dogfooding structuré). Elle vérifie **le produit** (la plateforme self-serve), pas le cas MGEN (piste B, campagnes GNG). Elle ne remplace aucune gate E2–E7.
> **Livrable attendu** : `RAPPORT_PARCOURS_PRODUIT_PROD.md` au gabarit de l'annexe A, avec un verdict par étape, les artefacts, le chrono, et le journal de friction.

---

## 0. Règles d'exécution

1. **Ne pas toucher au bot MGEN de validation** (s'il est déployé) : ni retrain, ni seuils, ni exemples. Le parcours se fait sur un **bot neuf jetable** créé pour l'occasion (préfixe `dogfood-`), supprimé en fin de protocole (P10).
2. **Version consignée avant tout test** : tag/commit de l'instance déployée (endpoint de version ou digest de l'image), archivée en tête de rapport. Si la version diffère du dernier tag validé, le signaler — la vérification reste valable mais le rapport doit le dire.
3. **Chaque étape produit un artefact** (réponse HTTP archivée, capture, transcript, mesure). Une étape non exécutable = FAIL avec le blocage décrit, jamais absente du rapport.
4. **Adaptation des endpoints** : les chemins d'API ci-dessous sont indicatifs. Source de vérité = l'OpenAPI de l'instance (`GET /openapi.json`). Si un endpoint attendu par la spec n'existe pas du tout (pas seulement sous un autre nom), c'est un FAIL de l'étape correspondante.
5. **Deux casquettes** : les étapes P1–P8 se testent par l'API admin (automatisable) **et** doivent être rejouables par l'IHM. Quand l'IHM n'est pas automatisable, vérifier au minimum que la page existe, charge sans erreur console, et expose les actions décrites. Toute friction UX (action introuvable, libellé ambigu, erreur silencieuse) va au **journal de friction** (annexe B) sans altérer le verdict fonctionnel.
6. **Aucun secret dans le rapport** : token admin et clés API référencés par empreinte tronquée uniquement.
7. **Chrono** : horodater le début et la fin de chaque étape. Budget de référence du parcours complet (hors rédaction créative des exemples) : **une demi-journée pour un utilisateur autonome** ; l'exécution automatisée doit tenir en < 1 h hors entraînements.

---

## P0 — Préconditions & état de l'instance

**Vérifications** :
1. `https://loko.wezon.fr` répond en HTTPS ; certificat valide ; redirection HTTP→HTTPS effective.
2. Headers de sécurité présents (nosniff, X-Frame-Options DENY hors `/widget/*`, Referrer-Policy, CSP).
3. `GET /health` → 200.
4. **Fail-closed admin** : un appel admin **sans** token → 401/403 (ou routes non montées). Un appel avec le token → 200.
5. Rate limiting vivant : rafale > limite sur un endpoint public → au moins un 429 avec `Retry-After`.
6. Version/commit de l'instance consignés.

**Critères** :
| # | Critère | Attendu |
|---|---|---|
| P0-1 | HTTPS + headers sécurité | Tous présents |
| P0-2 | Admin fail-closed | 401/403 sans token |
| P0-3 | Health | 200 |
| P0-4 | Rate limiting | 429 + Retry-After observé |
| P0-5 | Version consignée | tag/commit archivé |

---

## P1 — Étape wizard 1 : Projet bot

**Actions** : créer un bot `dogfood-faq-wezon` : nom, canal widget+API, langue FR, ton (choisir dans la bibliothèque de tons).

**Critères** :
| # | Critère | Attendu |
|---|---|---|
| P1-1 | Création via API admin | 201, `bot_id` retourné, statut `draft` |
| P1-2 | Le bot apparaît dans l'IHM (liste des projets) | Visible, éditable |
| P1-3 | Champs conformes spec | nom, canal, langue, ton persistés (GET de relecture) |

---

## P2 — Étape wizard 2 : Intentions & entraînement immédiat

**Actions** :
1. Vérifier la présence d'office des **deux intentions système** : `hors_perimetre` (obligatoire) et `demande_conseiller` (pré-entraînée, transverse). Leçon v0.3.7 : c'est le point qui avait cassé — vérifier explicitement que le bot neuf les porte.
2. Créer **3 intentions métier** de test (ex. cas FAQ Wezon : `horaires_contact`, `tarifs_offres`, `probleme_technique`) : définition + **10–15 exemples chacune** (l'UI doit imposer le minimum de 8 — tester le refus à 7).
3. Sur une intention, déclarer **2 sous-motifs** (~5 exemples chacun) pour vérifier le niveau 2.
4. Lancer l'**entraînement** ; suivre la progression (statut visible, monotone).
5. À la fin : **matrice de confusion simplifiée + conseils** exposés (API `train/report` et IHM).

**Critères** :
| # | Critère | Attendu |
|---|---|---|
| P2-1 | Intentions système présentes sur bot neuf | `hors_perimetre` + `demande_conseiller` |
| P2-2 | Minimum 8 exemples imposé | Refus (422/erreur UI) à 7 exemples |
| P2-3 | Entraînement à la demande | Statut progressif → `completed` ; durée consignée (référence : ≤ 300 s pour ~50 exemples, largement moins ici) |
| P2-4 | Manifeste écrit | Labels exacts (5 intentions dont 2 système), niveau 2 déclaré avec ses sous-motifs |
| P2-5 | Matrice + advice | Matrice N×N exposée ; si paire faible détectée, `advice` non vide et actionnable |
| P2-6 | Boucle d'itération | Ajouter 3 exemples → retrain → matrice mise à jour, `dataset_hash` changé |

---

## P3 — Étape wizard 3 : Connaissances, tagging, couverture

**Actions** :
1. Ingérer **3–5 documents** (dossier local / upload) couvrant les 3 intentions métier.
2. **Tagger** chaque document vers une ou plusieurs intentions/sous-motifs ; marquer 1 document `confidentiel` (non-« publique »).
3. Lire l'**indicateur de couverture** : il doit signaler l'intention la moins documentée.
4. Si le **connecteur FAQ web** est activable sur cette instance : crawl d'une petite page réelle (une page du site Wezon) et vérification de l'indexation. Sinon : consigner « non testé ici, couvert par la recette E5 » (pas un FAIL de ce protocole).

**Critères** :
| # | Critère | Attendu |
|---|---|---|
| P3-1 | Ingestion + tagging | Documents indexés, tags persistés (relecture) |
| P3-2 | Confidentialité | Le document `confidentiel` est marqué comme tel |
| P3-3 | Couverture | Indicateur exact vs comptage manuel ; signal sur intention pauvre |

---

## P4 — Étape wizard 4 : Paramètres du parcours

**Actions** : lire les défauts (`seuil_haut` 0.75, `seuil_bas` 0.45, `seuil_sous_motif` 0.60, `max_clarifications` 1, `max_demandes` 5, `timeout` 300 s) ; en modifier un (ex. timeout 120 s) ; vérifier la persistance et l'effet.

**Critères** :
| # | Critère | Attendu |
|---|---|---|
| P4-1 | Défauts conformes spec | Valeurs exactes ci-dessus |
| P4-2 | Modification persistée | Relecture OK, appliquée au runtime après publication |

---

## P5 — Étape wizard 5 : Messages (templates)

**Actions** : lister les templates par état (accueil, clarification inter, clarification intra, hors-périmètre, escalade avec `{temps_attente}`, enquête, fin, timeout) ; éditer l'accueil avec un marqueur unique (ex. `[DOGFOOD-42]`) ; vérifier la variable `{intentions_gerees}` dans l'accueil.

**Critères** :
| # | Critère | Attendu |
|---|---|---|
| P5-1 | Tous les états ont un template éditable | Liste complète |
| P5-2 | Édition persistée | Le marqueur apparaît dans les sessions runtime (vérifié en P7) |
| P5-3 | Interpolation | `{intentions_gerees}` rendue avec les intentions réelles du bot |

---

## P6 — Étape wizard 6 : Playground avec trace, puis publication

**Actions** :
1. **Playground** : soumettre 5 requêtes (une claire par intention, une ambiguë, une hors périmètre) et vérifier la **trace complète** pour chacune : intention + score, chunks + pertinence, latence par étape. C'est le différenciateur diagnostic — si la trace ne dit pas *pourquoi*, c'est un FAIL produit.
2. **Publication** : publier le bot → génération d'une **clé API scopée** au bot + **snippet widget** prêt à coller.
3. **Intégrité** : vérifier qu'une publication sans retrain après modification d'exemples est refusée (`422 retrain_required`) — la garde R0 vue côté produit.

**Critères** :
| # | Critère | Attendu |
|---|---|---|
| P6-1 | Trace playground complète | Intention+score, chunks+pertinence, latence/étape sur les 5 requêtes |
| P6-2 | Publication | Statut `published`, clé API générée (empreinte consignée), snippet fourni |
| P6-3 | Garde d'intégrité | 422 codé sur publication incohérente |

---

## P7 — Runtime : le bot en service réel (API + widget)

**Actions** :
1. **API runtime** (avec la clé scopée) : session complète — accueil (marqueur `[DOGFOOD-42]` présent), question claire → réponse streamée citant un document ingéré, question ambiguë → **clarification à choix fermé** (boutons, max 1), clic → routage, question hors périmètre → template hors-périmètre puis reformulation/escalade, « je veux parler à quelqu'un » → **escalade transverse immédiate**, enquête « Ai-je répondu ? » → satisfait → « Autre demande ? » → non → fin.
2. **Étanchéité** : une question dont la réponse n'est que dans le document `confidentiel` → le bot ne le cite jamais.
3. **Clé scopée** : la clé du bot dogfood sur un autre `bot_id` → 401/403 ; sans clé → 401/403.
4. **Widget** : page HTML hôte minimale avec le snippet → bulle, ouverture, streaming visible, boutons de clarification cliquables, feedback 👍/👎, reprise de session après rechargement ; payload XSS (`<script>alert(1)</script>` dans un message) → rendu inerte.
5. **Latence** : P50/P95 de la classification et TTFB de génération mesurés sur 20 requêtes (réseau public inclus — consigner, sans seuil de gate ici : la mesure opposable reste in-container).

**Critères** :
| # | Critère | Attendu |
|---|---|---|
| P7-1 | Parcours FSM complet en conditions réelles | Tous les états traversés, transcripts archivés |
| P7-2 | Max 1 clarification | 0 violation |
| P7-3 | Messages système = templates | Marqueur présent ; aucun message système généré |
| P7-4 | Réponses citent les sources | `source_url`/référence sur les réponses documentées |
| P7-5 | Confidentialité | 0 fuite du document confidentiel |
| P7-6 | Clés scopées | 401/403 hors scope |
| P7-7 | Widget fonctionnel + XSS inerte | Captures/vidéo archivées |
| P7-8 | Reprise de session | Historique restauré |

---

## P8 — Dashboard & boucle d'amélioration continue

**Actions** :
1. Après les sessions P7 : le **dashboard** affiche sessions, taux selfcare, escalades, latence P50, selfcare par intention — comparer aux compteurs manuels des transcripts P7 (écart attendu : 0).
2. **Boucle 1-clic** : marquer une requête mal classée → « Ajouter » comme exemple d'entraînement → vérifier que c'est bien le **message utilisateur** (pas celui du bot — régression D corrigée) qui est proposé, que le garde-fou anti-pollution refuse un texte identique à un template, puis « Ré-entraîner » → nouveau manifeste.

**Critères** :
| # | Critère | Attendu |
|---|---|---|
| P8-1 | Métriques exactes | Écart 0 vs comptage manuel des sessions P7 |
| P8-2 | Boucle 1-clic saine | Verbatim utilisateur proposé, garde-fou actif, retrain OK |

---

## P9 — Robustesse d'exploitation (smoke production)

**Actions** :
1. **Fail-fast constaté en prod** : sur le bot dogfood uniquement, simuler l'indisponibilité du modèle (ou utiliser un bot jetable dédié) → `503 bot_unavailable`, aucune session fantôme, log CRITICAL côté serveur ; restauration ensuite.
2. **Redémarrage** : restart du conteneur → le bot publié re-sert sans intervention ; les sessions actives se clôturent proprement (timeout), pas de corruption.
3. **Isolation** : 5 sessions simultanées entrelacées → aucun mélange de contexte entre sessions.

**Critères** :
| # | Critère | Attendu |
|---|---|---|
| P9-1 | Fail-fast + alerte/log | 503 codé, log CRITICAL, 0 réponse dégradée silencieuse |
| P9-2 | Restart propre | Service restauré, données intactes |
| P9-3 | Isolation sessions | 0 croisement sur 5 sessions entrelacées |

---

## P10 — Nettoyage & synthèse

**Actions** : supprimer le bot `dogfood-*` et ses clés ; vérifier la suppression effective (404 ensuite) ; purge des transcripts de test (vérification RGPD au passage : les transcripts purgés sont réellement absents) ; assembler le rapport.

**Critères** :
| # | Critère | Attendu |
|---|---|---|
| P10-1 | Suppression complète | 404 sur bot/clés ; artefacts disque nettoyés |
| P10-2 | Purge transcripts | Prouvée (requête de relecture vide) |

---

## Verdict global

| Verdict | Condition | Conséquence |
|---|---|---|
| **PRODUIT OK EN PROD** | P0–P10 tous PASS | Le parcours self-serve spécifié est opérationnel sur loko.wezon.fr ; le journal de friction alimente le backlog produit ; la piste B (E2b → E7) continue inchangée. |
| **OK AVEC RÉSERVES** | FAIL uniquement sur des critères non-cœur (P3-4 connecteur, latences réseau, frictions UX) | Réserves listées, correctifs planifiés, pas de blocage. |
| **KO** | FAIL sur un critère cœur : P0-2 (fail-closed), P2 (entraînement), P6 (publication/garde), P7-1/P7-5/P7-6 (parcours, confidentialité, clés), P9-1 (fail-fast) | Correction avant toute démo externe ; l'instance repasse en accès restreint. |

**Rappel de périmètre** : un PASS ici signifie « le produit est prêt à être pris en main et démontré ». Il ne signifie pas « validé pour de vrais adhérents » — cela reste la sortie de E7 (recette humaine) sur la piste B.

---

## Annexe A — Gabarit du rapport

```
# RAPPORT PARCOURS PRODUIT PROD — {date} — loko.wezon.fr
Instance : version/commit {…}, digest {…} — testé de {heure} à {heure}
Exécutant : {…} — Bot de test : dogfood-{…} (supprimé : OUI/NON)

## Tableau des étapes
| Étape | Verdict | Durée | Artefacts |
| P0 … P10 (aucune omission)

## Détail des FAIL (le cas échéant) : critère, observé, reproduction

## Journal de friction UX (annexe B remplie)

## Verdict global : PRODUIT OK / OK AVEC RÉSERVES / KO
## Suites données : backlog produit alimenté (liens), correctifs planifiés
```

## Annexe B — Journal de friction UX (à remplir au fil de l'eau)

| # | Étape | Friction observée | Gravité (bloquant / gênant / cosmétique) | Suggestion |
|---|---|---|---|---|

Consignes : noter chaque hésitation (« où est le bouton ? »), chaque libellé ambigu, chaque erreur silencieuse, chaque écart entre le vocabulaire de l'IHM et celui de la spec (intentions, sous-motifs, seuils). Cible produit rappelée : un non-technicien passe de zéro à bot publié en **une demi-journée** — toute friction qui menace ce budget est au minimum « gênant ».
