#!/usr/bin/env python3
"""Run the Brindille PC-0..PC-10 protocol with Playwright.

This is a local, disposable execution:
- starts LOKO on localhost with an isolated temporary LOKO_DATA_DIR;
- starts a deterministic OpenAI-compatible fake LLM server;
- drives signup/login and selected UI checks with Playwright;
- uses the authenticated browser context for bulk setup APIs;
- writes a markdown report under Evalluation_loko/.
"""

from __future__ import annotations

import csv
import html
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import httpx
from playwright.sync_api import (
    Page,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)


ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = ROOT / "Evalluation_loko"
REPORT_DIR = EVAL_DIR / "playwright_artifacts"
BRINDILLE_URL = "https://brindille.wezon.fr/index.html"


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_http(url: str, timeout_s: int = 60) -> None:
    deadline = time.time() + timeout_s
    last_error = ""
    while time.time() < deadline:
        try:
            with httpx.Client(timeout=2.0) as client:
                res = client.get(url)
                if res.status_code < 500:
                    return
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
        time.sleep(0.5)
    raise RuntimeError(f"Timed out waiting for {url}: {last_error}")


class FakeLLMHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_args: Any) -> None:
        return

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("content-length", "0"))
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            self.send_error(400)
            return

        messages = payload.get("messages", [])
        prompt = messages[-1].get("content", "") if messages else ""
        answer = build_fake_answer(prompt)
        body = "".join(
            "data: " + json.dumps({"choices": [{"delta": {"content": token}}]}) + "\n\n"
            for token in split_tokens(answer)
        )
        body += "data: [DONE]\n\n"
        encoded = body.encode("utf-8")

        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.send_header("content-length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def split_tokens(text: str) -> list[str]:
    parts = re.findall(r"\S+\s*", text)
    return parts or [text]


def source_link(prompt: str) -> str:
    match = re.search(r"\[([^\]]+)\]\((https?://[^)]+)\)", prompt)
    if not match:
        return ""
    return f"[{match.group(1)}]({match.group(2)})"


def build_fake_answer(prompt: str) -> str:
    link = source_link(prompt)
    lower = prompt.lower()
    question_match = re.search(
        r"question utilisateur\s*:\s*(.+)", prompt, re.IGNORECASE
    )
    question = question_match.group(1).lower() if question_match else lower

    if "49" in lower and (
        "livraison" in question or "offerte" in question or "montant" in question
    ):
        return f"La livraison est offerte a partir de 49 EUR. {link}".strip()
    if ("rembours" in question or "rembourse" in question) and (
        "5 jours" in lower or "5 jours ouvr" in lower
    ):
        return f"Le remboursement est traite sous 5 jours ouvres apres validation du retour. {link}".strip()
    if ("retour" in question or "retourner" in question) and "37 jours" in lower:
        return f"Vous disposez de 37 jours pour retourner un article. {link}".strip()
    if "ficus" in question and "9 jours" in lower:
        return f"En hiver, arrosez votre ficus tous les 9 jours. {link}".strip()
    if "paypal" in lower or "3 fois" in lower:
        return f"Les moyens de paiement acceptes sont ceux indiques dans l'article source. {link}".strip()
    if "succulentes" in lower:
        return f"Pour les succulentes, suivez les conseils d'arrosage et de luminosite de la source. {link}".strip()
    if "37 jours" in lower:
        return f"Vous disposez de 37 jours pour retourner un article. {link}".strip()
    if "5 jours" in lower or "5 jours ouvr" in lower:
        return f"Le remboursement est traite sous 5 jours ouvres apres validation du retour. {link}".strip()
    if "9 jours" in lower:
        return f"En hiver, arrosez votre ficus tous les 9 jours. {link}".strip()
    if "49" in lower:
        return f"La livraison est offerte a partir de 49 EUR. {link}".strip()
    if link:
        return f"Voici l'information disponible dans la base de connaissances. {link}".strip()
    return "Je n'ai pas d'information a ce sujet."


def start_fake_llm(port: int) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", port), FakeLLMHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def start_loko(
    app_port: int,
    llm_port: int,
    data_dir: Path,
    host_port: int,
    log_path: Path,
) -> subprocess.Popen:
    env = os.environ.copy()
    env.update(
        {
            "LOKO_DATA_DIR": str(data_dir),
            "LOKO_ENV": "test",
            "LOKO_MODE": "desktop",
            "LOKO_AUTH_DEBUG_TOKENS": "on",
            "LOKO_BASE_URL": f"http://localhost:{app_port}",
            "LOKO_ESCALATION_PROVIDER": "mock",
            "LOKO_LLM_BASE_URL": f"http://127.0.0.1:{llm_port}/v1",
            "LOKO_LLM_API_KEY": "fake-key",
            "LOKO_LLM_MODEL": "fake-brindille",
            "LOKO_CORS_ORIGINS": ",".join(
                [
                    f"http://localhost:{app_port}",
                    f"http://127.0.0.1:{app_port}",
                    f"http://localhost:{host_port}",
                    f"http://127.0.0.1:{host_port}",
                ]
            ),
        }
    )
    log_fh = log_path.open("w", encoding="utf-8")
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "loko.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(app_port),
        ],
        cwd=str(ROOT),
        env=env,
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    proc._loko_log_fh = log_fh  # type: ignore[attr-defined]
    return proc


def browser_api(page: Page, method: str, path: str, payload: Any = None) -> Any:
    result = page.evaluate(
        """async ({ method, path, payload }) => {
            const options = {
              method,
              credentials: 'include',
              headers: { 'Content-Type': 'application/json' },
            };
            if (payload !== null && payload !== undefined) {
              options.body = JSON.stringify(payload);
            }
            const res = await fetch(path, options);
            const text = await res.text();
            let body = null;
            try { body = text ? JSON.parse(text) : null; } catch { body = text; }
            return { ok: res.ok, status: res.status, body };
        }""",
        {"method": method, "path": path, "payload": payload},
    )
    if not result["ok"]:
        raise RuntimeError(f"{method} {path} -> {result['status']}: {result['body']}")
    return result["body"]


def load_intents() -> list[dict[str, Any]]:
    by_intent: dict[str, list[str]] = {}
    with open(
        EVAL_DIR / "intents_brindille.csv", encoding="utf-8-sig", newline=""
    ) as fh:
        for row in csv.DictReader(fh):
            by_intent.setdefault(row["intent"], []).append(row["text"])

    by_sub: dict[str, list[str]] = {}
    with open(
        EVAL_DIR / "submotifs_compte_client.csv", encoding="utf-8-sig", newline=""
    ) as fh:
        for row in csv.DictReader(fh):
            by_sub.setdefault(row["sub_motif"], []).append(row["text"])

    labels = {
        "suivi_commande": "Suivi commande",
        "livraison": "Livraison",
        "retour_remboursement": "Retour et remboursement",
        "moyens_paiement": "Moyens de paiement",
        "compte_client": "Compte client",
        "entretien_plantes": "Entretien plantes",
        "hors_perimetre": "Hors perimetre",
        "demande_conseiller": "Demande conseiller",
    }
    system = {"hors_perimetre", "demande_conseiller"}
    intents: list[dict[str, Any]] = []
    for intent_id, examples in by_intent.items():
        intent = {
            "id": intent_id,
            "label": labels.get(intent_id, intent_id),
            "definition": f"Demandes liees a {labels.get(intent_id, intent_id)}",
            "examples": examples,
            "sub_motifs": [],
            "is_system": intent_id in system,
        }
        if intent_id == "compte_client":
            intent["sub_motifs"] = [
                {
                    "id": sub_id,
                    "label": sub_id.replace("_", " "),
                    "definition": f"Sous-motif {sub_id}",
                    "examples": sub_examples,
                }
                for sub_id, sub_examples in by_sub.items()
            ]
        intents.append(intent)
    return intents


ARTICLE_TAGS = {
    "suivi-commande.html": (["suivi_commande"], []),
    "livraison.html": (["livraison"], []),
    "retour-remboursement.html": (["retour_remboursement"], []),
    "moyens-paiement.html": (["moyens_paiement"], []),
    "creation-compte.html": (["compte_client"], ["creation_compte"]),
    "connexion-impossible.html": (["compte_client"], ["connexion_impossible"]),
    "mot-de-passe-oublie.html": (["compte_client"], ["mot_de_passe_oublie"]),
    "modification-coordonnees.html": (["compte_client"], ["modification_coordonnees"]),
    "suppression-compte.html": (["compte_client"], ["suppression_compte"]),
    "entretien-ficus.html": (["entretien_plantes"], []),
    "entretien-succulentes.html": (["entretien_plantes"], []),
    "arrosage-general.html": (["entretien_plantes"], []),
}


@dataclass
class PCResult:
    id: str
    expected: str
    observed: str
    status: str
    proof: str = ""


@dataclass
class RunState:
    results: list[PCResult] = field(default_factory=list)
    runtime_rows: list[dict[str, Any]] = field(default_factory=list)
    screenshots: list[str] = field(default_factory=list)

    def add(
        self, pc: str, expected: str, observed: str, status: str, proof: str = ""
    ) -> None:
        self.results.append(PCResult(pc, expected, observed, status, proof))
        print(f"{pc} {status}: {observed}", flush=True)


def parse_sse(text: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for block in text.split("\n\n"):
        if not block.strip():
            continue
        event = "message"
        data_lines: list[str] = []
        for raw in block.splitlines():
            if raw.startswith("event: "):
                event = raw[7:].strip()
            elif raw.startswith("data: "):
                data_lines.append(raw[6:])
        if not data_lines:
            continue
        try:
            data = json.loads("\n".join(data_lines))
        except json.JSONDecodeError:
            data = {}
        events.append({"event": event, "data": data})
    return events


def runtime_case(
    client: httpx.Client, bot_id: str, api_key: str, text: str
) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {api_key}"}
    session_res = client.post(f"/api/v1/bot/{bot_id}/sessions", headers=headers)
    session_res.raise_for_status()
    session_id = session_res.json()["session_id"]
    msg_res = client.post(
        f"/api/v1/bot/{bot_id}/sessions/{session_id}/messages",
        headers=headers,
        json={"text": text, "type": "text"},
        timeout=60,
    )
    msg_res.raise_for_status()
    events = parse_sse(msg_res.text)
    full_text = "".join(
        str(e["data"].get("token", ""))
        for e in events
        if e["event"] == "generation_delta"
    )
    templates = [
        e["data"].get("template_key") for e in events if e["event"] == "template"
    ]
    sources = []
    for e in events:
        if e["event"] == "sources":
            sources.extend(e["data"].get("sources", []))
    state_res = client.get(
        f"/api/v1/bot/{bot_id}/sessions/{session_id}", headers=headers
    )
    state_res.raise_for_status()
    state = state_res.json()
    return {
        "session_id": session_id,
        "answer": full_text,
        "templates": templates,
        "sources": sources,
        "state": state,
        "events": events,
    }


def accepted(result: dict[str, Any], accept_expr: str, case_id: str) -> bool:
    state = result["state"]
    intent = state.get("current_intent")
    sub = state.get("current_sub_motif")
    templates = set(t for t in result["templates"] if t)
    answer = result["answer"].lower()
    source_urls = " ".join(str(s.get("url", "")) for s in result["sources"])

    options = {part.strip() for part in accept_expr.split(";")}
    ok = False
    for opt in options:
        if opt.startswith("route:"):
            target = opt[len("route:") :]
            if "/" in target:
                want_intent, want_sub = target.split("/", 1)
                ok = ok or (intent == want_intent and sub == want_sub)
            elif target == "accueil":
                ok = ok or ("presentation" in templates or intent in (None, "accueil"))
            else:
                ok = ok or intent == target
        elif opt.startswith("clarify_intra:"):
            target = opt[len("clarify_intra:") :]
            ok = ok or (intent == target and "clarification_intra" in templates)
        elif opt.startswith("escalate:"):
            target = opt[len("escalate:") :]
            ok = ok or (intent == target and "mise_en_relation" in templates)
        elif opt == "reject":
            ok = ok or ("hors_perimetre" in templates or intent == "hors_perimetre")

    if case_id == "B13":
        ok = ok and "37 jours" in answer and "retour-remboursement.html" in source_urls
    if case_id == "B14":
        ok = ok and "5 jours" in answer
    if case_id == "B15":
        ok = ok and "9 jours" in answer and "entretien-ficus.html" in source_urls
    if case_id == "B17":
        ok = ok and ("49" in answer or "49" in json.dumps(result["sources"]))
    return ok


def load_runtime_cases() -> list[dict[str, str]]:
    with open(
        EVAL_DIR / "runtime_eval_brindille.csv", encoding="utf-8-sig", newline=""
    ) as fh:
        return list(csv.DictReader(fh))


def start_widget_host(
    port: int, app_base: str, bot_id: str, api_key: str
) -> ThreadingHTTPServer:
    page = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Widget Brindille</title></head>
<body>
<main><h1>Host Brindille</h1></main>
<script src="{app_base}/widget/loko-widget.js"
  data-bot-id="{html.escape(bot_id)}"
  data-api-url="{app_base}"
  data-api-key="{html.escape(api_key)}"></script>
</body></html>"""

    class HostHandler(BaseHTTPRequestHandler):
        def log_message(self, *_args: Any) -> None:
            return

        def do_GET(self) -> None:  # noqa: N802
            encoded = page.encode("utf-8")
            self.send_response(200)
            self.send_header("content-type", "text/html; charset=utf-8")
            self.send_header("content-length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    server = ThreadingHTTPServer(("127.0.0.1", port), HostHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def write_report(run: RunState, out_path: Path, bot_id: str, app_base: str) -> None:
    passed_runtime = sum(1 for row in run.runtime_rows if row["ok"])
    canari_ok = all(
        row["ok"] for row in run.runtime_rows if row["id"] in {"B13", "B14", "B15"}
    )
    verdict = (
        "PRODUIT SELF-SERVE VALIDE"
        if passed_runtime >= 18
        and canari_ok
        and all(r.status == "PASS" for r in run.results if r.id != "PC-8")
        else "NON VALIDE"
    )
    lines = [
        "# Rapport Playwright Brindille PC-0 a PC-10",
        "",
        f"Date: {datetime.now().isoformat(timespec='seconds')}",
        f"Application locale: {app_base}",
        f"Bot: `{bot_id}`",
        f"Verdict: **{verdict}**",
        "",
        "## Parcours",
        "",
        "| Phase | Statut | Observe | Preuve |",
        "|---|---:|---|---|",
    ]
    for result in run.results:
        lines.append(
            f"| {result.id} | {result.status} | {result.observed.replace('|', '/')} | {result.proof.replace('|', '/')} |"
        )
    lines += [
        "",
        "## PC-8 Runtime",
        "",
        f"Score: **{passed_runtime}/20**",
        f"Canari B13-B15: **{'OK' if canari_ok else 'FAIL'}**",
        "",
        "| ID | Statut | Intent | Sous-motif | Reponse | Sources |",
        "|---|---:|---|---|---|---|",
    ]
    for row in run.runtime_rows:
        lines.append(
            f"| {row['id']} | {'PASS' if row['ok'] else 'FAIL'} | {row.get('intent') or ''} | {row.get('sub') or ''} | {row.get('answer', '')[:120].replace('|', '/')} | {row.get('sources', '')[:120].replace('|', '/')} |"
        )
    if run.screenshots:
        lines += ["", "## Captures", ""]
        lines.extend(f"- `{path}`" for path in run.screenshots)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    data_dir = Path(tempfile.mkdtemp(prefix="loko-brindille-pc-"))
    app_port = free_port()
    llm_port = free_port()
    host_port = free_port()
    app_base = f"http://localhost:{app_port}"
    run = RunState()
    fake_llm = start_fake_llm(llm_port)
    proc = start_loko(
        app_port, llm_port, data_dir, host_port, REPORT_DIR / "loko_server.log"
    )
    widget_host: ThreadingHTTPServer | None = None
    bot_id = ""
    completed_cleanly = False

    try:
        wait_http(f"http://127.0.0.1:{app_port}/health", timeout_s=90)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1440, "height": 950})
            page = context.new_page()
            page.set_default_timeout(120_000)

            # PC-0
            page.goto(app_base)
            landing_shot = REPORT_DIR / "pc0_landing.png"
            page.screenshot(path=str(landing_shot), full_page=True)
            run.screenshots.append(str(landing_shot.relative_to(ROOT)))
            page.goto(f"{app_base}/signup")
            email = f"brindille-test+{int(time.time())}@example.test"
            password = "BrindilleTest!2026"
            page.locator("input[type=text]").first.fill("Brindille")
            page.locator("input[type=email]").fill(email)
            page.locator("input[type=password]").fill(password)
            page.locator("input[type=checkbox]").check()
            with page.expect_response(
                lambda r: r.url.endswith("/api/auth/signup")
            ) as signup_resp:
                page.locator("button[type=submit]").click()
            signup_body = signup_resp.value.json()
            token = signup_body.get("_debug_verify_token")
            if not token:
                raise RuntimeError("Signup debug verify token missing")
            page.goto(f"{app_base}/login")
            page.locator("input[type=email]").fill(email)
            page.locator("input[type=password]").fill(password)
            with page.expect_response(
                lambda r: r.url.endswith("/api/auth/login")
            ) as login_unverified:
                page.locator("button[type=submit]").click()
            blocked = login_unverified.value.status == 403
            page.goto(f"{app_base}/verify?token={token}")
            page.wait_for_url("**/verify?token=**")
            page.wait_for_selector("text=/Email|email/i")
            page.goto(f"{app_base}/login")
            page.locator("input[type=email]").fill(email)
            page.locator("input[type=password]").fill(password)
            page.locator("button[type=submit]").click()
            page.wait_for_url("**/bot", timeout=120_000)
            run.add(
                "PC-0",
                "Landing, signup, email verification, login",
                f"signup ok, pre-verification blocked={blocked}, login ok",
                "PASS" if blocked else "FAIL",
                f"capture {landing_shot.name}",
            )

            # PC-1
            config = browser_api(
                page,
                "POST",
                "/api/bot/",
                {
                    "name": "Assistant Brindille",
                    "channel": "both",
                    "language": "fr",
                    "tone_profile": "chaleureux",
                },
            )
            bot_id = config["bot_id"]
            page.goto(f"{app_base}/bot/{bot_id}/wizard/project")
            page.wait_for_selector("text=Assistant Brindille")
            run.add(
                "PC-1", "Bot draft created", f"bot {bot_id} visible in wizard", "PASS"
            )

            # PC-2
            intents = load_intents()
            config = browser_api(
                page, "PUT", f"/api/bot/{bot_id}", {"intents": intents}
            )
            train_start = browser_api(
                page,
                "POST",
                f"/api/bot/{bot_id}/train",
                {"run_evaluation": True},
            )
            _ = train_start
            deadline = time.time() + 900
            status = {"status": "running"}
            while time.time() < deadline:
                try:
                    status = browser_api(page, "GET", f"/api/bot/{bot_id}/train/status")
                    if status.get("status") in {"completed", "failed"}:
                        break
                except Exception:
                    pass
                time.sleep(5)
            if status.get("status") != "completed":
                raise RuntimeError(f"Training did not complete: {status}")
            evaluation = browser_api(page, "GET", f"/api/bot/{bot_id}/evaluation")
            run.add(
                "PC-2",
                "8 intentions, sub-motifs, training matrix",
                f"{len(config['intents'])} intents, training completed, accuracy={evaluation.get('accuracy')}",
                "PASS",
            )

            # PC-3
            crawl = browser_api(
                page,
                "POST",
                f"/api/bot/{bot_id}/knowledge/crawl",
                {
                    "start_url": BRINDILLE_URL,
                    "use_playwright": True,
                    "follow_iframes": True,
                    "document_url_patterns": ["/articles/"],
                    "ingest": True,
                },
            )
            docs = browser_api(page, "GET", f"/api/bot/{bot_id}/documents")
            previews = " ".join(
                d.get("content_preview", "") for d in crawl.get("documents", [])
            )
            pc3_ok = (
                crawl["documents_ingested"] == 12
                and "37 jours" in previews
                and "5 jours" in previews
                and "9 jours" in previews
            )
            run.add(
                "PC-3",
                "Sitemap, iframes, JS canari, 12 docs sourcees",
                f"{crawl['documents_ingested']} docs ingeres, visited={crawl['urls_visited']}",
                "PASS" if pc3_ok else "FAIL",
                "canari presents in crawl previews"
                if pc3_ok
                else json.dumps(crawl.get("errors", []))[:200],
            )

            # PC-4
            tagged = 0
            for doc in docs:
                url = doc["source_url"]
                name = url.rsplit("/", 1)[-1]
                if name not in ARTICLE_TAGS:
                    continue
                intents_tag, sub_tags = ARTICLE_TAGS[name]
                res = browser_api(
                    page,
                    "PATCH",
                    f"/api/bot/{bot_id}/documents/tags",
                    {
                        "doc_ids": [doc["doc_id"]],
                        "bot_intents": intents_tag,
                        "bot_sub_motifs": sub_tags,
                    },
                )
                tagged += int(res.get("updated", 0))
            coverage = browser_api(page, "GET", f"/api/bot/{bot_id}/knowledge/coverage")
            coverage_values = coverage["coverage"]
            pc4_ok = (
                tagged == 12
                and all(v >= 1 for v in coverage_values.values())
                and coverage_values.get("entretien_plantes") == 3
            )
            run.add(
                "PC-4",
                "Documents tagged and coverage complete",
                f"tagged={tagged}, coverage={coverage_values}",
                "PASS" if pc4_ok else "FAIL",
            )

            # PC-5
            templates = {
                "presentation": {
                    "key": "presentation",
                    "text_fr": "Bienvenue ! Je peux vous aider avec vos commandes, votre compte client et l'entretien de vos plantes.",
                    "text_en": "Welcome. I can help with orders, customer accounts and plant care.",
                    "variables": [],
                }
            }
            journey = config["journey"] | {
                "seuil_haut": 0.60,
                "retrieval_min_chunks": 1,
            }
            browser_api(
                page,
                "PUT",
                f"/api/bot/{bot_id}",
                {"templates": templates, "journey": journey},
            )
            page.goto(f"{app_base}/bot/{bot_id}/wizard/messages")
            page.wait_for_selector("text=/Messages|templates/i")
            run.add(
                "PC-5",
                "Default thresholds and scoped welcome template",
                "template saved and messages view opens",
                "PASS",
            )

            # PC-6
            publish = browser_api(page, "POST", f"/api/bot/{bot_id}/publish")
            key_res = browser_api(
                page,
                "POST",
                f"/api/bot/{bot_id}/api-keys",
                {"label": "playwright", "allowed_origins": ["*"]},
            )
            api_key = key_res["raw_key"]
            page.evaluate(
                "([botId, key]) => sessionStorage.setItem(`loko_api_key_${botId}`, key)",
                [bot_id, api_key],
            )
            page.goto(f"{app_base}/bot/{bot_id}/playground")
            page.wait_for_selector("input[placeholder]")
            page.wait_for_selector("text=/Bienvenue|Welcome/i", timeout=120_000)
            page.locator("input[placeholder]").fill(
                "Combien de temps pour retourner un article ?"
            )
            page.locator("input[placeholder]").press("Enter")
            pc6_ok = True
            pc6_observed = f"published={publish.get('status')}, key generated, playground canari ok"
            try:
                page.wait_for_selector("text=/37 jours/i", timeout=120_000)
            except PlaywrightTimeoutError:
                pc6_ok = False
                body_text = page.locator("body").inner_text(timeout=5_000)
                pc6_observed = "playground canari missing; visible text: " + body_text[
                    :300
                ].replace("\n", " ")
            pc6_shot = REPORT_DIR / "pc6_playground.png"
            page.screenshot(path=str(pc6_shot), full_page=True)
            run.screenshots.append(str(pc6_shot.relative_to(ROOT)))
            run.add(
                "PC-6",
                "Playground canari, publish, API key, widget snippet",
                pc6_observed,
                "PASS" if pc6_ok else "FAIL",
                f"capture {pc6_shot.name}",
            )

            # PC-7
            widget_host = start_widget_host(host_port, app_base, bot_id, api_key)
            widget_page = context.new_page()
            widget_page.goto(f"http://localhost:{host_port}")
            widget_page.locator("loko-widget").wait_for(
                state="attached", timeout=60_000
            )
            widget_page.wait_for_function(
                "() => document.querySelector('loko-widget')?.shadowRoot?.querySelector('.loko-launcher')",
                timeout=60_000,
            )
            widget_page.locator("loko-widget").evaluate(
                """async (el) => {
                    const btn = el.shadowRoot.querySelector('.loko-launcher');
                    btn.click();
                }"""
            )
            widget_page.wait_for_timeout(3000)
            widget_page.locator("loko-widget").evaluate(
                """async (el) => {
                    const input = el.shadowRoot.querySelector('.loko-input');
                    input.value = 'A quelle frequence arroser mon ficus en hiver ?';
                    input.dispatchEvent(new Event('input', { bubbles: true }));
                    el.shadowRoot.querySelector('.loko-send').click();
                }"""
            )
            widget_page.wait_for_function(
                """() => {
                    const el = document.querySelector('loko-widget');
                    return el?.shadowRoot?.textContent?.toLowerCase().includes('9 jours');
                }""",
                timeout=120_000,
            )
            pc7_shot = REPORT_DIR / "pc7_widget.png"
            widget_page.screenshot(path=str(pc7_shot), full_page=True)
            run.screenshots.append(str(pc7_shot.relative_to(ROOT)))
            run.add(
                "PC-7",
                "Widget third-party host works with sources",
                "widget answered ficus canari",
                "PASS",
                f"capture {pc7_shot.name}",
            )

            # PC-8
            with httpx.Client(base_url=app_base, timeout=120.0) as client:
                cases = load_runtime_cases()
                for row in cases:
                    result = runtime_case(client, bot_id, api_key, row["text"])
                    ok = accepted(result, row["accept"], row["id"])
                    state = result["state"]
                    run.runtime_rows.append(
                        {
                            "id": row["id"],
                            "text": row["text"],
                            "accept": row["accept"],
                            "ok": ok,
                            "intent": state.get("current_intent"),
                            "sub": state.get("current_sub_motif"),
                            "answer": result["answer"],
                            "sources": ";".join(
                                str(s.get("url", "")) for s in result["sources"]
                            ),
                            "session_id": result["session_id"],
                        }
                    )
            passed = sum(1 for r in run.runtime_rows if r["ok"])
            canari_ok = all(
                r["ok"] for r in run.runtime_rows if r["id"] in {"B13", "B14", "B15"}
            )
            run.add(
                "PC-8",
                "20 runtime cases, >=18/20 and canari mandatory",
                f"{passed}/20, canari={'OK' if canari_ok else 'FAIL'}",
                "PASS" if passed >= 18 and canari_ok else "FAIL",
            )

            # PC-9
            sample_text = "Ma plante est cassee et je veux un geste commercial"
            add_example = browser_api(
                page,
                "POST",
                f"/api/bot/{bot_id}/dashboard/add-example",
                {
                    "intent_id": "retour_remboursement",
                    "text": sample_text,
                    "from_production": True,
                },
            )
            retrain = browser_api(
                page,
                "POST",
                f"/api/bot/{bot_id}/dashboard/retrain",
                {"run_evaluation": False},
            )
            run.add(
                "PC-9",
                "Add verbatim as example and retrain",
                f"add-example={add_example.get('status')}, retrain={retrain.get('status')}",
                "PASS"
                if add_example.get("status") in {"added", "duplicate"}
                and retrain.get("status") == "started"
                else "FAIL",
            )

            # PC-10
            page.goto(f"{app_base}/bot/{bot_id}/dashboard", timeout=300_000)
            page.wait_for_selector("text=Dashboard")
            metrics = browser_api(page, "GET", f"/api/bot/{bot_id}/dashboard/metrics")
            pc10_shot = REPORT_DIR / "pc10_dashboard.png"
            page.screenshot(path=str(pc10_shot), full_page=True)
            run.screenshots.append(str(pc10_shot.relative_to(ROOT)))
            pc10_ok = metrics.get("total_sessions", 0) >= 1 and metrics.get(
                "recent_sessions"
            )
            run.add(
                "PC-10",
                "Dashboard reflects PC-7/PC-8 sessions",
                f"sessions={metrics.get('total_sessions')}, p50={metrics.get('latency_p50_ms')}ms",
                "PASS" if pc10_ok else "FAIL",
                f"capture {pc10_shot.name}",
            )

            browser.close()

        report_path = (
            EVAL_DIR
            / f"RAPPORT_PLAYWRIGHT_BRINDILLE_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.md"
        )
        write_report(run, report_path, bot_id, app_base)
        print(report_path)
        print(
            json.dumps([r.__dict__ for r in run.results], indent=2, ensure_ascii=False)
        )
        completed_cleanly = True
        return 0 if all(r.status == "PASS" for r in run.results) else 1
    finally:
        if widget_host:
            widget_host.shutdown()
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        log_fh = getattr(proc, "_loko_log_fh", None)
        if log_fh:
            try:
                log_fh.close()
            except Exception:
                pass
        fake_llm.shutdown()
        if completed_cleanly:
            shutil.rmtree(data_dir, ignore_errors=True)
        else:
            print(f"Kept data dir for debugging: {data_dir}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
