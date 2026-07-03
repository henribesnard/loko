# LOKO Bot Service Client — Spécifications de développement (pour Claude Code)

> **Objet** : implémenter de bout en bout le produit « LOKO Bot Service Client » (chatbot selfcare self-serve) en fork/extension du code existant RAGKit Desktop (LOKO).
> **Source fonctionnelle** : `specs-loko-bot-service-client.md` v1.0 (cadrage validé, 2 juillet 2026). Ce document la traduit en exigences d'implémentation. En cas de conflit, la spec de cadrage fait foi.
> **Langues** : FR/EN (i18n existante à étendre). Code, identifiants et commentaires en anglais ; UI bilingue.

---

## 0. Contexte de la base de code existante (à réutiliser, ne pas réécrire)

| Existant | Localisation | Réutilisation |
|---|---|---|
| Backend FastAPI (sidecar Tauri + mode serveur `RAGKIT_MODE=server`) | `ragkit/desktop/main.py` | Ajouter les routers bot ; conserver middlewares (ApiKeyMiddleware, SecurityHeaders, CORS serveur) |
| API publique v1 + gestion clés API | `ragkit/desktop/api/public_chat.py`, `middleware/api_key_auth.py` | Étendre pour les endpoints bot runtime |
| Pipeline ingestion + métadonnées documents (domaine, confidentialité, tags…) | `ragkit/desktop/api/ingestion.py`, `ragkit/desktop/documents.py` | Ajouter les tags intention/sous-motif comme métadonnées de premier ordre |
| Système de connecteurs (`BaseConnector`, REST API, crawl…) | `ragkit/connectors/` | Nouveau connecteur `faq_web_crawler` sur le même contrat |
| Retrieval hybride (BM25 + vectoriel), reranking optionnel | `ragkit/retrieval/`, stores | Ajouter le filtrage dur par tags |
| Orchestrateur chat + conversation DB | `ragkit/desktop/api/chat.py`, `conversation_db.py` | Le bot engine est un NOUVEL orchestrateur déterministe (ne pas dériver l'agentique existant) |
| Settings store + export `.loko-config` | `ragkit/config/config_export.py`, `settings_store.py` | Étendre l'export pour inclure la config bot (sans clés API) |
| Frontend React/Tauri + design system LOKO (tokens CSS, `.loko-card`, `btn`, Geist) | `desktop/src/` | Toutes les nouvelles pages respectent `desktop/docs/DESIGN_SYSTEM.md` |
| Monitoring latence existant | dashboard existant | Brancher les traces bot dessus |
| i18n `fr.json` / `en.json` | `desktop/src/locales/` | Ajouter les namespaces `bot.*` |

**Interdiction** : ne pas casser le parcours RAG desktop existant. Le mode « bot » est un module additif activable par projet.

---

## 1. Principe directeur non négociable : déterminisme structurel

Contrainte transverse à tout le code produit :

1. Le parcours conversationnel est une **machine à états finis explicite en Python pur** (pas d'agent LLM, pas de routing par prompt).
2. Tous les messages système (accueil, clarifications, enquête, fin, escalade, timeout, hors périmètre) sont des **templates fixes** rendus par interpolation de variables. Aucun de ces messages ne passe par un LLM.
3. La classification d'intention et de sous-motif est faite par **SetFit local (CPU)**.
4. Le **seul** appel non déterministe est la génération de la réponse finale : LLM provider API, `temperature=0`, contexte filtré, sortie streamée, `max_tokens` 500–800.
5. Deux conversations identiques (mêmes entrées, même config, même index) doivent produire le **même parcours d'états et les mêmes messages système** — exigence testée (voir §12).

Toute PR qui introduit un appel LLM pour une décision structurelle est un défaut de conformité.

---

## 2. Architecture cible

```
ragkit/
├── bot/                          # NOUVEAU package — moteur bot
│   ├── engine.py                 # Machine à états (FSM) déterministe
│   ├── states.py                 # Enum états + transitions déclaratives
│   ├── session.py                # BotSession : état courant, compteurs, transcript
│   ├── session_store.py          # Persistance sessions (SQLite ; interface pour Redis V2)
│   ├── classifier/
│   │   ├── setfit_service.py     # Entraînement + inférence SetFit (niv 1 et niv 2)
│   │   ├── training.py           # Cross-validation, matrice de confusion, conseils
│   │   └── model_store.py        # Persistance modèles par bot (.loko/bots/{bot_id}/models/)
│   ├── templates.py              # Moteur de templates + bibliothèque par profil de ton
│   ├── retrieval_filter.py       # Retrieval filtré par intention/sous-motif + fallback
│   ├── generation.py             # Appel LLM streaming temp 0, prompt de génération
│   ├── escalation.py             # Contrat d'escalade + implémentation mock V1
│   ├── tracing.py                # Trace structurée par tour (état, scores, chunks, latences)
│   └── metrics.py                # Agrégats dashboard (selfcarisation, escalade, clarification)
├── connectors/
│   └── faq_web_crawler.py        # NOUVEAU connecteur FAQ web (headless + iframes)
└── desktop/api/
    ├── bot_admin.py              # NOUVEAU router /api/bot/* (config, entraînement, playground)
    └── bot_public.py             # NOUVEAU router /api/v1/bot/* (runtime widget/API)

desktop/src/
├── pages/bot/                    # Wizard bot (6 étapes), dashboard bot, playground
└── ...

widget/                           # NOUVEAU package frontend indépendant
├── src/                          # Widget embarquable (Preact ou vanilla TS, < 50 ko gzippé)
└── dist/loko-widget.js           # Bundle unique servi par le backend
```

### Stockage

- Config bot : `~/.loko/bots/{bot_id}/config.json` (schémas Pydantic, versionnés `schema_version`).
- Modèles SetFit : `~/.loko/bots/{bot_id}/models/{level1|level2_{intent_id}}/`.
- Sessions + logs de conversation bot : SQLite `~/.loko/bots/{bot_id}/sessions.db` (tables `sessions`, `turns`, `traces`, `feedback`).
- Un projet LOKO peut héberger plusieurs bots ; chaque bot référence une base de connaissances (collection) existante.

---

## 3. Modèles de données (Pydantic, source de vérité)

```python
class SubMotif(BaseModel):
    id: str; label: str; definition: str
    examples: list[str]                      # ~5 recommandés, min 3

class Intent(BaseModel):
    id: str; label: str; definition: str
    examples: list[str]                      # min 8 (validation bloquante), UI encourage 15-20
    sub_motifs: list[SubMotif] = []          # optionnels
    is_system: bool = False                  # hors_perimetre, demande_conseiller

class JourneyParams(BaseModel):
    seuil_haut: float = 0.75
    seuil_bas: float = 0.45
    seuil_sous_motif: float = 0.60
    max_clarifications: int = 1              # par demande — règle d'or
    max_demandes: int = 5
    timeout_inactivite_s: int = 300
    retrieval_min_score: float = 0.35        # à calibrer, exposé dans l'UI
    retrieval_min_chunks: int = 2            # N du fallback

class MessageTemplate(BaseModel):
    key: TemplateKey                          # enum §6
    text_fr: str; text_en: str
    variables: list[str]                      # variables autorisées

class BotConfig(BaseModel):
    schema_version: int = 1
    bot_id: str; name: str
    channel: Literal["widget", "api", "both"] = "both"
    language: Literal["fr", "en", "auto"] = "fr"
    tone_profile: Literal["formel", "chaleureux", "neutre"] = "neutre"
    intents: list[Intent]
    journey: JourneyParams
    templates: dict[TemplateKey, MessageTemplate]
    knowledge_collection: str                 # référence base de connaissances LOKO
    confidentiality_filter: list[str] = ["public"]   # bot public → documents publics uniquement
    llm: BotLLMConfig                         # provider API, model, max_tokens 500-800, temp figée à 0
    status: Literal["draft", "published"] = "draft"

class BotSession(BaseModel):
    session_id: str; bot_id: str
    state: BotState
    created_at: datetime; last_activity_at: datetime
    demandes_count: int = 0
    clarifications_count_current_demande: int = 0
    current_intent: str | None; current_sub_motif: str | None
    pending_candidates: list[tuple[str, float]] = []   # pour clarification inter-intentions
    original_query: str | None                          # conservée pour concaténation retrieval
    transcript: list[Turn]

class TraceEvent(BaseModel):
    turn_id: str; step: str                   # classification_l1 | classification_l2 | retrieval | generation | template
    detail: dict                              # scores par classe, chunks + scores, tokens, etc.
    latency_ms: float
```

Contrat d'escalade (figé — mock V1) :

```json
// Requête
{
  "conversation_id": "...",
  "transcript": [...],
  "intention": "service_en_ligne",
  "sous_motif": "mot_de_passe_oublié",
  "motif_escalade": "insatisfaction | demande_explicite | hors_perimetre | retrieval_insuffisant",
  "horodatage": "ISO-8601"
}
// Réponse
{ "temps_attente_estime_min": 4 }
```

Implémentation : interface `EscalationProvider` (méthode `escalate(payload) -> EscalationResult`) + `MockEscalationProvider` (temps d'attente configurable, log du payload). Le mock est le provider par défaut ; le point d'extension est documenté.

---

## 4. Machine à états (exigences d'implémentation)

États : `ACCUEIL`, `ATTENTE_DEMANDE`, `CLASSIFICATION_L1`, `CLARIFICATION_INTER`, `CLASSIFICATION_L2`, `CLARIFICATION_INTRA`, `RETRIEVAL_GENERATION`, `ENQUETE_SATISFACTION`, `AUTRE_DEMANDE`, `ESCALADE`, `FIN`, `TIMEOUT`.

Transitions (reprend fidèlement §3 de la spec de cadrage) :

1. **ACCUEIL** : émission du template Présentation (avec `{nom_bot}`, `{intentions_gérées}`) → `ATTENTE_DEMANDE`.
2. **CLASSIFICATION_L1** (SetFit niv 1 sur le message utilisateur) :
   - `score ≥ seuil_haut` → `CLASSIFICATION_L2` (ou `RETRIEVAL_GENERATION` si l'intention n'a pas de sous-motifs).
   - `seuil_bas ≤ score < seuil_haut` → `CLARIFICATION_INTER` : template choix fermé entre les **2** meilleures candidates ; la réponse (clic ou texte) route directement ou re-classifie.
   - `score < seuil_bas` **ou** classe `hors_périmètre` → template hors périmètre → 1 reformulation autorisée ; deuxième échec → `ESCALADE` (motif `hors_perimetre`).
   - Classe `demande_conseiller` → `ESCALADE` (motif `demande_explicite`) — valable comme **sortie transverse depuis n'importe quel état**.
3. **CLASSIFICATION_L2** (uniquement si l'intention déclare des sous-motifs ; espace de décision restreint aux sous-motifs de cette intention) :
   - meilleur score ≥ `seuil_sous_motif` → suite directe sans question.
   - sinon → `CLARIFICATION_INTRA` : choix fermé = libellés des sous-motifs + « Autre » (boutons dans le widget).
     - clic option → routage direct ;
     - texte libre → re-classification niv 2 sur `requête_initiale + " " + réponse` ;
     - « Autre » → retrieval sur toute l'intention ; scores insuffisants → `ESCALADE` (motif `retrieval_insuffisant`).
   - **Maximum 1 clarification par demande** (inter OU intra) — compteur appliqué par le moteur, jamais contournable.
4. **RETRIEVAL_GENERATION** : voir §5. Puis → `ENQUETE_SATISFACTION`.
5. **ENQUETE_SATISFACTION** (template, boutons Oui/Non) :
   - Satisfait → `AUTRE_DEMANDE` (template) : Oui → retour `CLASSIFICATION_L1` avec incrément `demandes_count` (si `> max_demandes` → `FIN`) ; Non → template fin → `FIN`.
   - Non satisfait → template Mise en relation avec `{temps_attente}` + appel `EscalationProvider` → `FIN`. **Escalade immédiate, aucune boucle de ré-essai** (décision actée).
6. **Sorties transverses** actives à tout moment : demande explicite de conseiller → `ESCALADE` ; inactivité > `timeout_inactivite_s` → template Timeout → `FIN` (tâche de nettoyage périodique côté serveur, pas de timer par session en mémoire).

Exigences de code :
- Table de transitions **déclarative** (dict/dataclass), pas de `if` imbriqués éparpillés ; chaque transition loggée dans `traces`.
- Le moteur est **pur** : `engine.step(session, event) -> (new_session, actions)` sans I/O ; les effets (SetFit, retrieval, LLM, escalade) sont injectés via interfaces → testabilité totale.
- Réponses du moteur typées : `EmitTemplate(key, vars, buttons)`, `EmitGeneration(query, filter)`, `CallEscalation(payload)`, `CloseSession`.

---

## 5. Retrieval filtré + génération

### 5.1 Tagging (ingestion)

- Étendre les métadonnées de document existantes avec `bot_intents: list[str]` et `bot_sub_motifs: list[str]` (multi-tag). Propagation aux chunks (la propagation métadonnées existe déjà).
- UI de tagging dans l'étape 3 du wizard bot (réutiliser la table métadonnées existante, colonnes supplémentaires, édition en masse).
- **Filtre de confidentialité par canal** appliqué au runtime : le bot ne voit que les documents dont la confidentialité ∈ `confidentiality_filter`.

### 5.2 Runtime

1. Recherche restreinte (filtrage **dur** sur métadonnées — pas de pondération en V1) aux chunks du sous-motif détecté, sinon de l'intention.
2. Requête de retrieval = concaténation `"{requête_origine} — {libellé_sous_motif}"` (décision actée).
3. Fallback : si `< retrieval_min_chunks` chunks au-dessus de `retrieval_min_score` → élargir au corpus de l'intention entière → si toujours insuffisant → `ESCALADE` (motif `retrieval_insuffisant`).
4. Reranking **désactivé par défaut** pour le bot (activable en expert).

### 5.3 Génération

- Prompt système de génération : contraint aux chunks fournis, ton du profil, langue du bot, consigne de citer l'URL source (`source_url` en métadonnée, cf. connecteur FAQ) quand disponible, consigne d'admettre l'ignorance si le contexte ne couvre pas.
- `temperature=0`, `max_tokens` configurable 500–800, **streaming SSE** de bout en bout (backend → widget).
- Aucune mémoire conversationnelle envoyée au LLM au-delà de la demande courante + contexte (minimisation coût/latence ; l'historique vit dans la session, pas dans le prompt).

---

## 6. Templates

Enum `TemplateKey` : `presentation`, `clarification_inter`, `clarification_intra`, `hors_perimetre`, `enquete_satisfaction`, `autre_demande`, `fin`, `mise_en_relation`, `timeout`.

- Bibliothèque de défauts **pré-remplis par profil de ton** (formel / chaleureux / neutre), FR + EN, éditables dans l'étape 5 du wizard.
- Variables supportées : `{nom_bot}`, `{intentions_gérées}`, `{temps_attente}`, `{lien_escalade}`, `{options}` (liste de choix fermé). Validation : variable inconnue = erreur à la sauvegarde.
- Le template Présentation **annonce le périmètre** (liste des intentions gérées) — pré-rempli automatiquement depuis la config des intentions.
- Rendu : interpolation simple (`str.format`-like sécurisé), jamais de LLM.

---

## 7. Classification SetFit

- Dépendances : `setfit`, `sentence-transformers`. Modèle de base par défaut : multilingue compact adapté au FR (ex. `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`) — **configurable** dans les settings expert (point ouvert §12 de la spec : le choix final FR dédié vs multilingue doit rester interchangeable derrière `model_store`).
- **Niveau 1** : un modèle par bot, classes = intentions + `hors_périmètre` (obligatoire, exemples fournis par l'utilisateur, validation min 8) + `demande_conseiller` (pré-entraînée : jeu d'exemples FR/EN embarqué dans le package, fusionné automatiquement).
- **Niveau 2** : un modèle par intention ayant des sous-motifs ; discrimination évaluée uniquement entre sous-motifs de la même intention.
- Entraînement déclenché depuis l'UI (fin de saisie, étape 2) : job asynchrone avec progression (réutiliser le pattern de progression de l'analyse d'ingestion). CPU only, budget < 2 min pour ~10 intentions × 15 exemples.
- **Évaluation immédiate** : cross-validation (k=5 ou leave-one-out si peu d'exemples) → matrice de confusion simplifiée + conseils actionnables générés par règles (paires de classes confondues → « ajoutez des exemples discriminants entre X et Y » ; classe sous-dotée → « ajoutez des exemples à X »).
- Inférence : modèle chargé en mémoire au démarrage du bot publié ; latence cible **20–50 ms CPU** (mesurée et tracée à chaque appel).
- **Boucle d'amélioration continue** : endpoint + UI « depuis les logs, requête mal classée → 1 clic → devient exemple d'entraînement » (ajout à l'intention corrigée, flag `from_production`), avec bouton « ré-entraîner ».
- Suggestion de scission : job d'analyse qui détecte, par intention, l'accumulation de feedbacks 👎 ou la dispersion des scores de retrieval, et pousse une suggestion dans le dashboard (« envisagez de scinder cette intention en sous-motifs »).

---

## 8. Connecteur FAQ web (`faq_web_crawler`)

Feature de premier plan. Cas de référence : FAQ type mgen.fr/aide-et-contact (articles dans des iframes, accordéons JS).

- Implémente le contrat `BaseConnector` existant (`validate_config`, listing, fetch, incrémental).
- **Rendu JavaScript** via navigateur headless (Playwright ; Chromium embarqué ou téléchargé à la première utilisation — gérer l'offline gracieusement).
- Découverte : `sitemap.xml` si présent + crawl BFS de profondeur configurable (`max_depth`, `max_pages`, `include_patterns`/`exclude_patterns`, respect `robots.txt` avec option de bypass explicite et assumée par l'utilisateur).
- **Suivi des `src` d'iframes** : le contenu d'une iframe est rattaché à la page/article parent.
- Extraction : **un document par article** (heuristique : unité de contenu type accordéon/article/section titrée), nettoyage boilerplate (nav, footer), conversion en texte/markdown.
- Métadonnées : `source_url` (obligatoire — utilisée pour la citation du lien dans la réponse), titre, date de crawl, hash de contenu.
- **Re-synchronisation planifiée** (cron configurable : quotidien/hebdo) branchée sur l'ingestion incrémentale existante : diff par hash → re-ingestion des articles modifiés uniquement.
- UI : formulaire de source dans l'étape 3 du wizard (URL racine, profondeur, planification, aperçu des pages découvertes avant ingestion).

---

## 9. Mode serveur & API publiques

### 9.1 Endpoints runtime (préfixe `/api/v1/bot`, auth par clé API existante, rate-limit slowapi)

| Méthode | Route | Rôle |
|---|---|---|
| POST | `/api/v1/bot/{bot_id}/sessions` | Crée une session → `{session_id}` + message d'accueil (template) |
| POST | `/api/v1/bot/{bot_id}/sessions/{sid}/messages` | Message utilisateur (texte libre **ou** `{button_id}` de choix fermé). Réponse **SSE** : événements `state`, `template`, `buttons`, `generation_delta`, `sources`, `end_of_turn` |
| POST | `/api/v1/bot/{bot_id}/sessions/{sid}/feedback` | 👍/👎 sur une réponse générée |
| GET | `/api/v1/bot/{bot_id}/sessions/{sid}` | État + transcript (pour reprise) |
| GET | `/widget/loko-widget.js` | Bundle du widget (cache long, versionné) |

### 9.2 Endpoints admin (préfixe `/api/bot`, réservés desktop/admin)

CRUD bots, intentions, sous-motifs, templates, paramètres de parcours ; `POST /api/bot/{id}/train` (+ progression) ; `GET /api/bot/{id}/evaluation` (matrice de confusion) ; `POST /api/bot/{id}/publish` (validations bloquantes : min 8 exemples/intention, `hors_périmètre` renseignée, ≥ 1 document taggé par intention — sinon avertissement de couverture) ; `POST /api/bot/{id}/playground` (mêmes réponses que le runtime + **trace complète**) ; métriques dashboard ; export/import config bot dans `.loko-config`.

### 9.3 Exigences serveur

- Headless : `RAGKIT_MODE=server` existant ; fournir un **Dockerfile** + `docker-compose.yml` (backend + volume `.loko`), variables d'env documentées (`RAGKIT_CORS_ORIGINS`, provider LLM, clé).
- **Concurrence** : sessions persistées en SQLite (WAL) ; le moteur étant pur et les modèles SetFit thread-safe en lecture, viser ≥ 50 conversations simultanées sur un nœud ; test de charge fourni.
- Nettoyage des sessions inactives (timeout → émission différée du template Timeout à la reconnexion ou clôture silencieuse ; TTL de purge configurable).
- Sécurité : la clé API du widget est **scopée bot + origine** (claims dans la clé ou table de mapping) ; CORS restreint aux origines déclarées ; aucune clé LLM côté client.

---

## 10. Widget web embarquable

- Package `widget/` indépendant : Preact ou vanilla TS, **un seul fichier JS < 50 ko gzippé**, CSS isolé (Shadow DOM), aucun conflit avec la page hôte.
- Intégration : `<script src="https://{host}/widget/loko-widget.js" data-bot-id="…" data-api-key="…" data-lang="fr"></script>` — le snippet exact est généré à l'étape 6 du wizard.
- Fonctionnel : bulle flottante ouvrable, fil de conversation, **streaming token par token**, **boutons de choix fermé** (clarifications, enquête Oui/Non, « Autre »), liens sources cliquables (citation d'article FAQ), feedback 👍/👎, indicateur de saisie, reprise de session (sessionStorage), accessibilité (navigation clavier, ARIA, contrastes AA).
- Thème : variables CSS surchargeables (`--loko-widget-brand`, etc.), light/dark, défauts alignés sur le design system LOKO.
- Architecture compatible callbot : le widget ne parle qu'au contrat SSE §9.1 ; aucun couplage au moteur.

---

## 11. UI Desktop : wizard bot, playground, dashboard

### Wizard (6 étapes — §10 de la spec de cadrage)

1. **Projet bot** : nom, canal, langue, ton.
2. **Intentions** : formulaire définition + exemples (validation min 8, encouragement 15–20 avec jauge), section repliable « Sous-motifs (optionnel) », bouton Entraîner → progression → **matrice de confusion simplifiée + conseils**.
3. **Bases de connaissances** : sources (dossier local existant, connecteur FAQ web), table de tagging intention/sous-motif (édition en masse), **indicateur de couverture** (« l'intention X n'a que N documents associés » avec seuil d'alerte).
4. **Parcours** : sliders/inputs des `JourneyParams` avec hints (défauts §3).
5. **Messages** : éditeur de templates par état, insertion de variables, prévisualisation rendue, reset au défaut du profil de ton.
6. **Simulation & publication** : **playground** = widget réel + panneau de **trace complète** par tour (intention + scores par classe, sous-motif, chunks avec scores de pertinence, latence par étape, état FSM) ; puis publication → génération clé API + snippet widget copiables.

### Dashboard bot

- Conversations récentes avec replay + trace.
- Métriques : **taux de selfcarisation par intention** (conversations résolues sans escalade), **taux d'escalade par motif**, **taux de clarification**, latence P50/P95 décomposée par composant (SLO affiché), volume par intention/sous-motif.
- Actions correctives inline : requête mal classée → 1 clic → exemple d'entraînement ; suggestions de scission d'intention.
- Respect strict du design system (tokens CSS, composants `loko-*`, light/dark, i18n).

---

## 12. Exigences non fonctionnelles & tests

### Budget latence (instrumenté, affiché, testé)

| Étape | Cible |
|---|---|
| Classification L1 / L2 (SetFit CPU) | 20–50 ms chacune |
| Message templatisé | ~0 ms |
| Retrieval filtré | < 200 ms |
| Génération LLM | premier token < 2 s ; réponse complète < 6–8 s |

Chaque étape émet un `TraceEvent` avec `latency_ms` ; tests de non-régression sur les étapes locales.

### Tests exigés (CI bloquante)

1. **FSM** : tests unitaires exhaustifs des transitions (moteur pur, effets mockés) — chaque branche du §4 couverte, y compris sorties transverses, compteurs `max_clarifications`/`max_demandes`, timeout.
2. **Déterminisme** : test de rejeu — deux exécutions d'un même scénario scripté produisent des séquences d'états et de messages système identiques.
3. **SetFit** : test d'entraînement/inférence sur un mini-jeu de données FR embarqué ; latence d'inférence mesurée.
4. **Retrieval filtré** : le filtrage dur ne retourne jamais un chunk hors tag ; fallback et escalade `retrieval_insuffisant` testés ; filtre de confidentialité testé.
5. **Contrat d'escalade** : schéma validé, mock testé.
6. **API runtime** : tests d'intégration SSE (session, message texte, message bouton, feedback) ; auth et scoping de clé.
7. **Connecteur FAQ** : tests sur fixtures HTML locales (sitemap, iframe, accordéon JS) ; incrémental par hash.
8. **Widget** : tests E2E (Playwright) sur une page hôte factice : streaming, boutons, feedback, reprise de session.
9. **Charge** : script de charge ≥ 50 sessions simultanées, latences hors LLM stables.

### Divers

- RGPD : possibilité de purge des transcripts (rétention configurable), détection PII existante applicable aux logs bot.
- Compat callbot (V2) : aucune dépendance du moteur au canal ; interfaces d'E/S abstraites.
- Documentation livrée : README bot, doc API (OpenAPI enrichie), guide d'intégration widget, guide Docker.

---

## 13. Plan d'implémentation proposé (jalons pour Claude Code)

| Jalon | Contenu | Critère de sortie |
|---|---|---|
| M1 — Socle | Package `ragkit/bot/` : modèles Pydantic, FSM pure + tests, session store, templates + bibliothèque de tons | Tests FSM + déterminisme verts |
| M2 — Classification | Service SetFit (train/infer/éval), modèle `demande_conseiller` embarqué, endpoints admin train/éval | Matrice de confusion en API, latence < 50 ms |
| M3 — Retrieval & génération | Tags intention/sous-motif dans l'ingestion, retrieval filtré + fallback, génération streaming temp 0, escalade mock | Parcours complet en API playground avec trace |
| M4 — Runtime & widget | Endpoints `/api/v1/bot/*` SSE, clés scopées, widget embarquable, Docker | Démo widget sur page externe |
| M5 — UI Desktop | Wizard 6 étapes, playground avec trace, tagging UI | Publication bout en bout depuis l'UI |
| M6 — Connecteur FAQ & dashboard | Crawler headless + resync, dashboard métriques, boucle d'amélioration continue | Ingestion FAQ de référence + métriques visibles |

Chaque jalon : PR isolée, tests, i18n FR/EN, respect design system, pas de régression du produit RAG existant.

---

## 14. Hors périmètre V1 (ne pas implémenter)

- Canal vocal/callbot (seule la compatibilité architecturale est exigée).
- Pondération/boosting du retrieval par intention (filtrage dur uniquement).
- Escalade réelle (mock seulement, contrat figé).
- Boucle de ré-essai après « non satisfait » (escalade immédiate actée).
- LLM on-prem/GPU souverain (provider API uniquement, interface provider existante conservée).
