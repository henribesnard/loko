# LOKO Bot — Audit de conformité & sécurité → Plan de remédiation pour Claude Code

> **Objet** : ce document liste les écarts constatés entre le code actuel et les spécifications (`SPECS_DEV_LOKO_BOT.md` + `specs-loko-bot-service-client.md` v1.0), ainsi que les vulnérabilités de sécurité identifiées. Il est destiné à être exécuté par Claude Code.
> **Règle d'exécution** : traiter les findings dans l'ordre de priorité (P0 → P1 → P2). Chaque finding = un commit atomique avec ses tests. Ne pas régresser les tests existants (`tests/bot/`). Respecter le principe de déterminisme structurel (§1 de la spec dev) dans toute modification.
> **Date d'audit** : 3 juillet 2026.

---

## 0. Synthèse

| Verdict | Détail |
|---|---|
| Architecture / déterminisme | ✅ Conforme — FSM pure, templates fixes, temp 0, protocoles d'injection propres |
| Auth des endpoints | 🔴 **Non conforme** — module de clés existant mais jamais branché ; admin API ouverte |
| Rate limiting | 🔴 Absent (slowapi exigé par spec §9.1) |
| CORS / headers sécurité | 🔴 `allow_origins=["*"]` + credentials ; pas de SecurityHeaders |
| Runtime réel (LLM + retrieval) | 🔴 Mocks jamais remplacés en production |
| Widget | 🟠 XSS via `javascript:` dans les liens ; i18n incomplète |
| Crawler | 🟠 SSRF possible ; pas de Playwright ; robots.txt à vérifier |
| Path traversal | 🟠 `bot_id` non validé, utilisé dans des chemins fichiers |
| Points forts | Clés hachées SHA-256, SQL paramétré, WAL, échappement HTML widget, tests FSM exhaustifs |

---

## P0 — Bloquant avant toute exposition réseau

### P0-1. Brancher l'authentification par clé API sur les endpoints runtime

**Fichiers** : `loko/api/bot_public.py`, `loko/api/api_keys.py`
**Constat** : `validate_api_key_for_bot()` et `check_origin()` existent mais ne sont appelés nulle part. Tous les endpoints `/api/v1/bot/*` (création de session, messages → génération LLM, lecture de transcript, feedback) sont accessibles sans clé. Conséquences : consommation illimitée de tokens LLM par un tiers (déni de service financier), lecture de n'importe quelle session par son ID.
**Spec violée** : §9.1 (« auth par clé API existante ») et §9.3 (« clé scopée bot + origine »).

**Actions** :
1. Créer une dépendance FastAPI `require_bot_api_key(bot_id)` :
   - Lire la clé dans le header `Authorization: Bearer <key>` (fallback `X-API-Key`).
   - Valider via `validate_api_key_for_bot(raw_key, bot_id)` → 401 si invalide, 403 si le scope bot ne correspond pas.
   - Valider l'origine via `check_origin(record, request.headers.get("origin"))` → 403 si refusée.
2. Appliquer `Depends(require_bot_api_key)` à **tous** les endpoints de `bot_public.py`.
3. Comparaison en temps constant : remplacer `record.key_hash == key_hash` par `hmac.compare_digest(...)` dans `api_keys.py`.
4. Adapter le widget (`widget/loko-widget.js`) : la fonction `_fetch` doit envoyer `Authorization: Bearer ${AUTH_TOKEN}` sur toutes les requêtes (vérifier que c'est déjà le cas, sinon l'ajouter).
5. Vérifier que le message d'erreur 401/403 ne révèle pas si le bot existe (réponse identique bot inconnu / clé invalide).

**Critères d'acceptation** :
- Test : requête sans clé → 401 ; clé d'un autre bot → 403 ; clé valide → 200/201.
- Test : clé avec `allowed_origins=["https://a.com"]` + header `Origin: https://b.com` → 403.
- Les tests SSE existants (`test_bot_api.py::TestPublicAPI`) sont mis à jour pour passer une clé de test.

### P0-2. Protéger les endpoints admin

**Fichiers** : `loko/api/bot_admin.py`, `loko/api/bot_dashboard.py`, `loko/main.py`
**Constat** : `/api/bot/*` (CRUD bots, entraînement, publication, **génération de clés API**, replay de sessions avec transcripts complets, ajout d'exemples d'entraînement) est monté sur la même app sans aucune authentification. En mode serveur, c'est une prise de contrôle totale.
**Spec violée** : §9.2 (« réservés desktop/admin »).

**Actions** :
1. Introduire un token admin : variable d'env `LOKO_ADMIN_TOKEN` (obligatoire en mode serveur ; en mode desktop/sidecar Tauri, générer un token éphémère au démarrage passé au frontend, comme le pattern ApiKeyMiddleware existant de RAGKit).
2. Middleware ou dépendance `require_admin` appliqué aux routers `bot_admin` et `bot_dashboard`.
3. Si `RAGKIT_MODE=server` et `LOKO_ADMIN_TOKEN` absent : refuser de monter les routers admin (fail-closed) et logger un avertissement explicite.
4. Le frontend desktop (`desktop/src/lib/api.ts`) envoie ce token.

**Critères d'acceptation** :
- Test : `/api/bot/{id}` sans token → 401 ; avec token → 200.
- Test : en mode serveur sans `LOKO_ADMIN_TOKEN`, `/api/bot/*` → 404 ou 401 systématique.

### P0-3. Corriger le CORS et ajouter les headers de sécurité

**Fichier** : `loko/main.py`
**Constat** : `allow_origins=["*"]` avec `allow_credentials=True` — combinaison invalide selon la spec CORS et dangereuse. Le commentaire « Tightened per-bot via API key origins » est faux tant que P0-1 n'est pas fait, et même après, le CORS global doit être restreint. Aucun middleware SecurityHeaders (exigé : conserver les middlewares existants de RAGKit).
**Spec violée** : §9.3 (« CORS restreint aux origines déclarées »).

**Actions** :
1. Lire `RAGKIT_CORS_ORIGINS` (liste séparée par virgules) ; défaut : origines localhost du desktop uniquement.
2. `allow_credentials=False` (l'auth passe par header Bearer, pas par cookies).
3. Alternative robuste : construire dynamiquement la liste des origines autorisées à partir de l'union des `allowed_origins` de toutes les clés API actives (rechargée à la génération/révocation de clé), ou utiliser `allow_origin_regex` documenté.
4. Ajouter un middleware SecurityHeaders : `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` (sauf `/widget/*`), `Referrer-Policy: strict-origin-when-cross-origin`, `Content-Security-Policy` minimale sur les réponses HTML.
5. Documenter `RAGKIT_CORS_ORIGINS` dans le README / guide Docker.

**Critères d'acceptation** :
- Test : preflight OPTIONS depuis une origine non déclarée → pas de header `Access-Control-Allow-Origin`.
- Test : les headers de sécurité sont présents sur `/health`.

### P0-4. Valider `bot_id` (et tout identifiant utilisé dans un chemin fichier)

**Fichiers** : `loko/bot/session_store.py` (`get_bot_dir`), `loko/bot/config_store.py`, `loko/api/api_keys.py`, `loko/bot/classifier/model_store.py`, tous les routers
**Constat** : `bot_id` vient de l'URL et est concaténé tel quel dans des chemins (`get_bots_dir() / bot_id`). Un `bot_id` comme `..` fait pointer `get_bot_dir` vers `~/.loko` ; combiné aux endpoints admin non protégés (écriture de `config.json`, `delete_bot` avec `shutil.rmtree`), c'est une écriture/suppression arbitraire hors du répertoire bots. `intent_id` (utilisé dans `level2_{intent_id}`) a le même problème.
**Sévérité** : haute (path traversal).

**Actions** :
1. Définir dans `loko/bot/models.py` un validateur commun : `SLUG_RE = ^[a-z0-9][a-z0-9_-]{0,63}$` appliqué à `bot_id` et `intent_id` (Pydantic `field_validator` + validation au niveau des path params FastAPI via `Path(pattern=...)`).
2. Dans `get_bot_dir()` : garde défensive — résoudre le chemin (`.resolve()`) et vérifier `bots_dir in path.parents`, sinon lever `ValueError`.
3. `get_bot_dir` ne doit **pas** créer le répertoire en lecture (`mkdir` actuel crée un dossier pour tout bot_id demandé → pollution disque par énumération). Séparer `get_bot_dir(bot_id, create=False)`.
4. Même garde dans `get_model_dir` et `delete_bot`.

**Critères d'acceptation** :
- Test : `get_bot_dir("..")`, `get_bot_dir("../../etc")` → exception.
- Test : `GET /api/v1/bot/../sessions/x` → 404/422, aucun dossier créé.
- Test : après un GET sur un bot inexistant, aucun répertoire n'a été créé sur disque.

### P0-5. Rate limiting (slowapi)

**Fichiers** : `loko/main.py`, `loko/api/bot_public.py`
**Constat** : aucun rate limiting alors que la spec §9.1 l'exige explicitement. Endpoints coûteux : création de session (écriture DB), messages (appel LLM payant).

**Actions** :
1. Ajouter `slowapi` : limiter par IP + par clé API (clé de limite = `key_id` si authentifié, sinon IP).
2. Limites proposées (configurables par env) : `POST /sessions` → 10/min ; `POST /messages` → 30/min ; `POST /feedback` → 30/min ; endpoints GET → 60/min.
3. Réponse 429 avec `Retry-After`.
4. Limites de taille d'entrée (défense DoS/coût LLM) : `MessageRequest.text` → `max_length=2000` ; `FeedbackRequest.comment` → `max_length=1000` ; `rating` → `Literal["positive","negative"]` ; paramètre `limit` de `list_recent_sessions` → `le=100`.

**Critères d'acceptation** :
- Test : 11e création de session dans la minute → 429.
- Test : message de 10 000 caractères → 422.

### P0-6. Remplacer les mocks du runtime par les services réels (ou fail-closed)

**Fichier** : `loko/api/bot_public.py` (`_get_orchestrator`)
**Constat** : l'orchestrateur runtime est construit avec `InMemorySearchBackend()` vide, `MockLLMProvider(...)` et `MockEscalationProvider`. Un bot « publié » répond donc en production « Je n'ai pas encore de base de connaissances configurée ». C'est le cœur du produit (M3/M4) laissé en placeholder.
**Spec violée** : §5 (retrieval filtré réel), §6 (génération LLM provider API), M4.

**Actions** :
1. Créer une factory `build_runtime_services(config: BotConfig)` qui instancie :
   - le classifieur SetFit réel si un modèle entraîné existe (`model_exists`), sinon refuser la publication (le check de publication doit déjà l'exiger — le vérifier) ;
   - le retriever branché sur la collection de connaissances du bot (`config.knowledge_collection`) via le backend de retrieval existant de RAGKit ;
   - le générateur avec le provider LLM configuré (`config.llm`) — clé lue depuis le settings store / variable d'env, **jamais** depuis `config.json`.
2. Fail-closed : si un bot `status != "published"` reçoit un appel runtime → 409 ; si le provider LLM n'est pas configuré → 503 explicite (pas de mock silencieux).
3. **Invalidation du cache** `_ORCHESTRATORS` : purge de l'entrée à chaque `publish`, mise à jour de config, ré-entraînement, révocation. Exposer `invalidate_orchestrator(bot_id)` et l'appeler depuis `bot_admin.py`.
4. Les mocks restent injectables pour les tests (paramètre ou setter existant).

**Critères d'acceptation** :
- Test d'intégration : bot publié avec collection factice → la réponse générée cite un chunk réel de la collection.
- Test : modification de config puis nouveau message → l'orchestrateur reflète la nouvelle config (pas de cache périmé).
- Test : bot en draft → runtime 409.

---

## P1 — À corriger avant démo externe / mise en prod

### P1-1. XSS dans le widget via les URLs de liens

**Fichier** : `widget/loko-widget.js` (`_formatText`, rendu des sources)
**Constat** : `_formatText` échappe le HTML puis transforme `[texte](url)` en `<a href="$2">`. Le schéma de l'URL n'est pas validé : `[clic](javascript:alert(document.cookie))` provenant de la génération LLM ou d'un document de la base de connaissances (contenu crawlé = non fiable) exécute du JS sur le site hôte du client. Idem pour `s.url` dans le bloc sources (échappé mais schéma non contrôlé).

**Actions** :
1. Fonction `safeUrl(u)` : n'autoriser que `https:`, `http:` (et chemins relatifs si nécessaire) via `new URL(u, location.origin)` dans un try/catch ; sinon retourner `"#"`.
2. Appliquer `safeUrl` dans `_formatText` et dans le rendu des sources.
3. Ajouter `rel="noopener noreferrer"` (noreferrer manquant).
4. Côté backend, défense en profondeur : dans `generation.py`/orchestrateur, ne transmettre au client dans l'événement `sources` que des URLs validées `http(s)`.

**Critères d'acceptation** :
- Test (unitaire JS ou E2E Playwright) : un message contenant `[x](javascript:alert(1))` rend un lien vers `#`, pas de dialog.

### P1-2. Retirer l'endpoint public `/traces` et sécuriser la lecture de session

**Fichier** : `loko/api/bot_public.py`
**Constat** : `GET /{bot_id}/sessions/{sid}/traces` expose scores de classification, chunks, latences — la spec ne le prévoit que dans le playground **admin** (§9.2, §11). Fuite d'informations internes (structure de la base de connaissances, seuils) exploitable pour contourner le bot.

**Actions** :
1. Déplacer l'endpoint traces sous `/api/bot/{bot_id}/...` (protégé par P0-2), ou le garder public uniquement derrière un flag `LOKO_DEBUG_TRACES=1` jamais actif par défaut.
2. `GET /sessions/{sid}` : vérifier `session.bot_id == bot_id` du path (cohérence), et le protéger par la clé API (couvert par P0-1) — le transcript est une donnée personnelle potentielle (RGPD).

**Critère d'acceptation** : test — `/api/v1/bot/{id}/sessions/{sid}/traces` → 404 ; traces accessibles via l'API admin avec token.

### P1-3. Durcir le crawler (SSRF + robots.txt + parsing)

**Fichier** : `loko/connectors/faq_web_crawler.py`
**Constat** :
- `SimplePageFetcher` suit n'importe quelle URL, y compris `http://127.0.0.1`, `http://169.254.169.254/` (métadonnées cloud), hôtes internes — SSRF déclenchable par l'admin, mais en SaaS/serveur mutualisé c'est un vrai vecteur. Les redirections ne sont pas contrôlées.
- `respect_robots: bool = True` existe en config mais l'implémentation du respect de robots.txt n'apparaît pas dans le crawl — **vérifier**, et l'implémenter si absente (spec §8 l'exige, avec bypass explicite).
- Parsing HTML/sitemap par regex : fragile (le test `<loc>` regex casse sur CDATA, le strip de tags casse sur du HTML imbriqué). La spec exige en outre le rendu JS **Playwright** (voir P1-6).

**Actions** :
1. Garde SSRF dans `fetch()` : résoudre l'hôte (`socket.getaddrinfo`) et rejeter IP privées/loopback/link-local/réservées (`ipaddress.ip_address(...).is_private / is_loopback / is_link_local / is_reserved`), schémas autres que http(s), et re-valider à **chaque redirection** (opener custom ou boucle manuelle avec `allow_redirects` contrôlé). Prévoir un flag de config `allow_private_networks: bool = False` pour les intranets assumés.
2. Implémenter robots.txt via `urllib.robotparser`, cache par domaine, honoré quand `respect_robots=True` ; logger explicitement le bypass quand False.
3. Remplacer le parsing regex par `selectolax` ou `BeautifulSoup` (extraction de contenu, liens, iframes) et `xml.etree` (défusé, ou `defusedxml`) pour le sitemap.
4. Limites de sécurité : taille max de réponse (ex. 5 Mo), délai entre requêtes configurable (politesse), timeout déjà présent à conserver.

**Critères d'acceptation** :
- Test : `fetch("http://127.0.0.1/x")` et `fetch("http://169.254.169.254/")` → rejetés.
- Test : page disallow dans robots.txt → non crawlée quand `respect_robots=True`.

### P1-4. Défauts dangereux des origines de clés

**Fichiers** : `loko/api/api_keys.py`, `desktop/src/pages/bot/wizard/BotPublish.tsx`
**Constat** :
- `check_origin` : `allowed_origins=[]` ⇒ tout autorisé (défaut permissif).
- Le wizard génère la clé avec `allowed_origins: ["*"]` — littéral `"*"` qui ne matchera jamais une vraie origine avec la logique actuelle (bug), et intention permissive de toute façon.
- Fallback frontend `setApiKey("loko_..._demo")` : affiche une fausse clé si l'endpoint échoue — trompeur, à supprimer.

**Actions** :
1. Décision produit à encoder : `allowed_origins=[]` ⇒ **refuser** les requêtes cross-origin (fail-closed) ; n'autoriser « toutes origines » que via valeur explicite `"*"` gérée dans `check_origin`.
2. Wizard : champ de saisie des origines autorisées (pré-rempli avec l'origine du serveur), plus de `["*"]` par défaut silencieux.
3. Supprimer le fallback de fausse clé ; afficher l'erreur réelle.
4. Ajouter la rotation : la génération d'une nouvelle clé « default » propose de révoquer l'ancienne.

### P1-5. Persistance de session pendant le streaming + concurrence

**Fichier** : `loko/api/bot_public.py` (`send_message`)
**Constat** : la session n'est persistée qu'à la **fin** du flux SSE. Si le client coupe la connexion en cours de génération, l'état est perdu (le générateur peut être annulé avant `store.update_session`). Deux messages simultanés sur la même session écrasent mutuellement leur état (last-write-wins) et le diff de transcript par `len()` peut dupliquer/perdre des tours.

**Actions** :
1. Envelopper le flux dans `try/finally` : persister session + tours dans le `finally` (état au moment de l'interruption).
2. Verrou par session (`asyncio.Lock` dans un registre `{session_id: Lock}` avec purge) ou rejet 409 « message en cours » si un stream est actif — la FSM est séquentielle par conception, l'API doit l'imposer.
3. Persister les tours par `turn_id` (INSERT OR IGNORE) plutôt que par diff d'index.

**Critère d'acceptation** : test — deux POST messages simultanés sur la même session → un seul traité (409 pour l'autre) ; déconnexion en cours de stream → l'état de session relu est cohérent.

### P1-6. Fetcher Playwright (exigence spec §8)

**Fichier** : `loko/connectors/faq_web_crawler.py`
**Constat** : seul `SimplePageFetcher` (urllib, pas de rendu JS) existe. Le cas de référence (FAQ avec iframes + accordéons JS) ne fonctionnera pas. Le protocole `PageFetcher` est prêt — il manque l'implémentation.

**Actions** :
1. `PlaywrightPageFetcher` implémentant `PageFetcher` : Chromium headless, `wait_until="networkidle"` avec timeout, extraction du DOM rendu, récupération des `src` d'iframes.
2. Gestion offline gracieuse : si Chromium non installé/téléchargeable → fallback documenté sur `SimplePageFetcher` avec avertissement dans le résultat du crawl (`errors`).
3. Appliquer les mêmes gardes SSRF (P1-3) : route les requêtes du navigateur via interception (`page.route`) pour bloquer IP privées et domaines hors `allowed_domains`.
4. Tests sur fixtures HTML locales avec contenu injecté en JS (spec §12.7).

### P1-7. Purge des sessions / TTL / timeout (RGPD + spec §9.3)

**Fichiers** : `loko/bot/session_store.py`, `loko/main.py`
**Constat** : `purge_expired()` existe mais aucun job planifié ne l'appelle ; pas de rétention configurable ; l'événement `TIMEOUT_EXPIRED` de la FSM existe mais rien ne le déclenche côté serveur.

**Actions** :
1. Tâche de fond (asyncio task au startup de l'app) : toutes les N minutes, pour chaque bot, marquer TIMEOUT les sessions inactives > `timeout_inactivite_s` (émission différée du template à la reconnexion, conformément à la spec) et purger celles dépassant `LOKO_SESSION_RETENTION_DAYS` (défaut 30, configurable).
2. À la reconnexion (`GET /sessions/{sid}` ou nouveau message) sur une session dépassant le timeout : jouer l'événement `TIMEOUT_EXPIRED` dans la FSM avant de traiter.
3. Documenter la rétention dans le README (RGPD).

---

## P2 — Qualité / conformité non bloquante

### P2-1. i18n du widget
`loko-widget.js` contient des messages d'erreur en dur en français (« Une erreur est survenue. », « Impossible de démarrer la conversation. ») et n'exploite pas `data-lang` prévu par la spec §10. Ajouter un mini-dictionnaire FR/EN sélectionné par `data-lang`.

### P2-2. Livrables serveur manquants (à vérifier puis compléter)
Vérifier la présence, sinon créer : `Dockerfile` + `docker-compose.yml` (backend + volume `.loko`, variables d'env documentées dont `RAGKIT_CORS_ORIGINS`, `LOKO_ADMIN_TOKEN`, provider LLM), script de charge ≥ 50 sessions simultanées (spec §12.9), guide d'intégration widget et guide Docker (spec §12 Divers).

### P2-3. `validate_api_key` global O(n × bots)
La validation qui balaie tous les dossiers bots à chaque requête ne tiendra pas la charge. Préférer systématiquement `validate_api_key_for_bot` (le `bot_id` est toujours dans l'URL) et supprimer ou indexer la variante globale.

### P2-4. Clés LLM hors config exportée
Vérifier que `config.json` et l'export `.loko-config` ne contiennent jamais la clé du provider LLM (le modèle a `api_key_set: bool`, c'est bon signe — ajouter un test qui sérialise la config et vérifie l'absence de tout champ secret). Spec §0 : export « sans clés API ».

### P2-5. Journalisation sécurité
Ajouter des logs structurés (sans PII, sans clés) : échecs d'auth (key_id si connu, IP), 429, publications, générations/révocations de clés. Brancher sur le monitoring existant.

### P2-6. En-têtes SSE et keep-alive
Ajouter un ping SSE (`: keep-alive\n\n`) périodique pendant les phases longues (génération) pour éviter les coupures de proxy, et gérer proprement `asyncio.CancelledError` (lié à P1-5).

### P2-7. Durcissement Pydantic
Sur les modèles exposés aux requêtes (`MessageRequest`, `FeedbackRequest`, requêtes admin) : `model_config = ConfigDict(extra="forbid")`, `type: Literal["text","button_click"]` au lieu de `str` libre.

---

## Ordre d'exécution recommandé pour Claude Code

1. **Branche `security/p0`** : P0-4 (validation bot_id — fondation), P0-1, P0-2, P0-3, P0-5, puis P0-6. Un commit + tests par item. CI verte, aucun test existant cassé (adapter les fixtures pour injecter clé de test / token admin).
2. **Branche `security/p1`** : P1-1 → P1-7.
3. **Branche `hardening/p2`** : P2-1 → P2-7.
4. À chaque branche : mettre à jour le README (nouvelles variables d'env : `LOKO_ADMIN_TOKEN`, `RAGKIT_CORS_ORIGINS`, `LOKO_SESSION_RETENTION_DAYS`, limites de rate) et l'OpenAPI (schémas d'auth `bearerAuth`).

## Garde-fous transverses (à respecter dans chaque modification)

- Tout ce qui est structurel reste déterministe : aucune des corrections ne doit introduire d'appel LLM décisionnel.
- Fail-closed par défaut : en cas de configuration manquante (token admin, provider LLM, origines), refuser plutôt que dégrader silencieusement.
- Aucune donnée sensible (clés brutes, transcripts) dans les logs.
- Chaque finding corrigé = au moins un test de non-régression qui échouerait sur le code actuel.
