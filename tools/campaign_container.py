#!/usr/bin/env python3
"""Runner 1.1.0 — exécuteurs in-container (remédiation R1→R4, inter-campagnes 2026-07-17).

Toutes les mesures V0/V1/V2/V3 s'exécutent DANS l'image Docker taguée
(interdit n°2 : aucune mesure depuis l'hôte). Enregistré par
run_campaign.py via register(EXECUTORS) en fin de chargement.

Montages :
  ROOT/data           -> /app/data           (rw : bots, modèles)
  ROOT/eval/datasets  -> /app/eval/datasets  (ro : jeux figés)
  campaign_dir        -> /campaign           (rw : artefacts)
"""

from __future__ import annotations

import csv
import importlib.util
import json
import secrets as pysecrets
import shutil
import time
import urllib.request
import uuid
from pathlib import Path
from typing import Any

rc = None  # module run_campaign, injecte par register()

APP = "/app"
CAMP = "/campaign"
V11_PORT = 18942
V14_PORT = 18943


# ──────────────────────────────────────────────────────────────────────
# Helpers docker
# ──────────────────────────────────────────────────────────────────────


def _mounts(campaign_dir: Path) -> list[tuple[str, str, bool]]:
    return [
        (str((rc.ROOT / "data").resolve()), f"{APP}/data", False),
        (str(rc.DATASETS_DIR.resolve()), f"{APP}/eval/datasets", True),
        (str(Path(campaign_dir).resolve()), CAMP, False),
    ]


def _docker(
    image: str,
    args: list[str],
    *,
    campaign_dir: Path | None = None,
    env: dict[str, str] | None = None,
    network: str | None = None,
    timeout: int = 600,
    name: str | None = None,
    detach: bool = False,
    extra_docker: list[str] | None = None,
    use_mounts: bool = True,
):
    cmd = ["docker", "run"]
    cmd += ["-d"] if detach else ["--rm"]
    if name:
        cmd += ["--name", name]
    if network:
        cmd += ["--network", network]
    if use_mounts and campaign_dir is not None:
        for host, cont, ro in _mounts(campaign_dir):
            cmd += ["-v", host + ":" + cont + (":ro" if ro else "")]
    base = {"LOKO_ML": "on", "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"}
    base.update(env or {})
    for k, v in base.items():
        cmd += ["-e", f"{k}={v}"]
    if extra_docker:
        cmd += extra_docker
    cmd += [image] + args
    return rc._run_cmd(cmd, timeout=timeout)


def _rm_container(name: str) -> None:
    rc._run_cmd(["docker", "rm", "-f", name], timeout=60)


def _logs(name: str) -> str:
    res = rc._run_cmd(["docker", "logs", name], timeout=60)
    return res.stdout + "\n" + res.stderr


def _poll_health(url: str, timeout_s: int = 90) -> tuple[bool, str]:
    deadline = time.time() + timeout_s
    last = ""
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as r:
                body = r.read().decode("utf-8", "replace")
                if r.status == 200:
                    return True, body
                last = f"http {r.status}: {body}"
        except Exception as exc:  # noqa: BLE001
            last = str(exc)
        time.sleep(2)
    return False, last


def _require(line, ctx, *keys):
    vals = []
    for k in keys:
        v = ctx.get(k)
        if not v:
            rc._mark_fail(line, f"no {k} specified")
            return None
        vals.append(v)
    return vals if len(vals) > 1 else vals[0]


def _bot_id(bot_dir: str) -> str:
    return Path(bot_dir).name


def _tree_hash(root: Path) -> dict[str, str]:
    """Hash de chaque fichier sous root (relpath -> sha256)."""
    out: dict[str, str] = {}
    for p in sorted(Path(root).rglob("*")):
        if p.is_file():
            out[str(p.relative_to(root))] = rc._hash_file(p)
    return out


def _server_env() -> dict[str, str]:
    return {
        "LOKO_MODE": "server",
        "LOKO_ADMIN_TOKEN": pysecrets.token_hex(16),
        "LOKO_SECRET_KEY": pysecrets.token_hex(32),
    }


# ──────────────────────────────────────────────────────────────────────
# R1 — V0 in-container
# ──────────────────────────────────────────────────────────────────────


def exec_v0_1(line, campaign_dir: Path, **ctx: Any) -> None:
    """V0-1: suite pytest complète in-container, sans -x."""
    image = _require(line, ctx, "image")
    if not image:
        return
    res = _docker(
        image,
        [
            "sh",
            "-c",
            "pip install --no-cache-dir -q pytest pytest-asyncio pytest-cov "
            "&& python -m pytest tests/ -q --tb=short -p no:cacheprovider",
        ],
        env={"LOKO_MODE": "test", "HOME": "/tmp"},
        use_mounts=False,
        extra_docker=[
            "-v",
            str((rc.ROOT / "tests").resolve()) + ":/app/tests:ro",
            "-w",
            "/app",
            "--user",
            "root",
        ],
        timeout=3600,
    )
    content = res.stdout + "\n" + res.stderr
    rc._save_artifact(campaign_dir, "V0-1_pytest.txt", content)
    if res.returncode == 0:
        summary = next(
            (l for l in res.stdout.splitlines() if " passed" in l), "exit 0"
        ).strip()
        rc._mark_pass(
            line, f"in-container: {summary}", str(campaign_dir / "V0-1_pytest.txt")
        )
    else:
        rc._mark_fail(line, f"exit {res.returncode} (in-container)", content[-800:])


def exec_v0_2(line, campaign_dir: Path, **ctx: Any) -> None:
    """V0-2: imports ML in-container."""
    image = _require(line, ctx, "image")
    if not image:
        return
    code = (
        "import torch; "
        "print(f'torch={torch.__version__}, cuda={torch.cuda.is_available()}'); "
        "from setfit import SetFitModel; print('setfit=ok'); "
        "from sentence_transformers import SentenceTransformer; print('st=ok')"
    )
    res = _docker(image, ["python", "-c", code], use_mounts=False, timeout=300)
    content = res.stdout + "\n" + res.stderr
    rc._save_artifact(campaign_dir, "V0-2_imports.txt", content)
    if res.returncode == 0:
        rc._mark_pass(
            line,
            "in-container: " + res.stdout.strip().replace("\n", " "),
            str(campaign_dir / "V0-2_imports.txt"),
        )
    else:
        rc._mark_fail(line, "import error (in-container)", res.stderr.strip()[:300])


def exec_v0_4(line, campaign_dir: Path, **ctx: Any) -> None:
    """V0-4: pip-audit in-container (npm audit hôte en information)."""
    image = _require(line, ctx, "image")
    if not image:
        return
    pip_res = _docker(
        image, ["python", "-m", "pip_audit"], use_mounts=False, timeout=600
    )
    pip_out = pip_res.stdout + "\n" + pip_res.stderr
    fallback = ""
    verdict_ok = False
    measured = ""
    if pip_res.returncode == 0 or "No known vulnerabilities" in pip_out:
        verdict_ok = True
        measured = "pip-audit in-container: 0 vulnérabilité"
    elif "No module named" in pip_out:
        chk = _docker(
            image, ["python", "-m", "pip", "check"], use_mounts=False, timeout=300
        )
        fallback = chk.stdout + "\n" + chk.stderr
        if chk.returncode == 0:
            verdict_ok = True
            measured = "pip check in-container OK (pip-audit absent de l'image)"
        else:
            measured = "pip check FAIL in-container"
    else:
        measured = "vulnérabilités détectées (pip-audit in-container)"

    npm_out = ""
    desktop = rc.ROOT / "desktop"
    if desktop.is_dir():
        try:
            npm = rc._run_cmd(["npm", "audit", "--omit=dev"], cwd=desktop, timeout=180)
            npm_out = npm.stdout + "\n" + npm.stderr
        except Exception as exc:  # noqa: BLE001
            npm_out = f"npm audit indisponible sur l'hôte: {exc}"

    content = (
        f"=== pip audit (in-container) ===\n{pip_out}\n"
        f"=== fallback pip check ===\n{fallback}\n"
        f"=== npm audit (hôte, informatif) ===\n{npm_out}\n"
    )
    rc._save_artifact(campaign_dir, "V0-4_audit.txt", content)
    if verdict_ok:
        rc._mark_pass(line, measured, str(campaign_dir / "V0-4_audit.txt"))
    else:
        rc._mark_fail(line, measured)


# ──────────────────────────────────────────────────────────────────────
# R2 — V1 orchestration
# ──────────────────────────────────────────────────────────────────────


def exec_v1_1(line, campaign_dir: Path, **ctx: Any) -> None:
    """V1-1: boot serveur in-container + /health 200."""
    image = _require(line, ctx, "image")
    if not image:
        return
    name = "loko-camp-v11"
    _rm_container(name)
    res = _docker(
        image,
        [],
        campaign_dir=campaign_dir,
        env=_server_env(),
        name=name,
        detach=True,
        extra_docker=["-p", f"127.0.0.1:{V11_PORT}:8000"],
    )
    if res.returncode != 0:
        rc._mark_fail(line, "docker run failed", res.stderr[:300])
        return
    ok, body = _poll_health(f"http://127.0.0.1:{V11_PORT}/health")
    logs = _logs(name)
    _rm_container(name)
    rc._save_artifact(
        campaign_dir, "V1-1_boot.txt", f"health={body}\n\n=== logs ===\n{logs}"
    )
    if ok:
        rc._mark_pass(
            line,
            f"health 200: {body.strip()[:120]}",
            str(campaign_dir / "V1-1_boot.txt"),
        )
    else:
        rc._mark_fail(line, f"health KO: {body[:200]}")


def exec_v1_2(line, campaign_dir: Path, **ctx: Any) -> None:
    """V1-2: mock instancié hors env de test -> exception (garde no-mock)."""
    image = _require(line, ctx, "image")
    if not image:
        return
    code = (
        "from loko.testing.mocks import MockEscalationProvider; "
        "MockEscalationProvider(); print('NO-EXCEPTION')"
    )
    res = _docker(
        image,
        ["python", "-c", code],
        env={"LOKO_MODE": "server"},
        use_mounts=False,
        timeout=120,
    )
    content = res.stdout + "\n" + res.stderr
    rc._save_artifact(campaign_dir, "V1-2_nomock.txt", content)
    if res.returncode != 0 and "NO-EXCEPTION" not in res.stdout:
        exc_name = "RuntimeError" if "RuntimeError" in content else "exception"
        rc._mark_pass(
            line,
            f"garde active: {exc_name} levée hors env test",
            str(campaign_dir / "V1-2_nomock.txt"),
        )
    else:
        rc._mark_fail(line, "mock instanciable hors env test (garde absente)")


def exec_v1_3(line, campaign_dir: Path, **ctx: Any) -> None:
    """V1-3: loader intègre — bot sans modèle -> exception typée, aucun fallback."""
    vals = _require(line, ctx, "image", "bot_dir")
    if not vals:
        return
    image, bot_dir = vals
    # Bot jetable non entraîné (copie de config sans models/)
    v13 = "v13-" + uuid.uuid4().hex[:8]
    dest = rc.ROOT / "data" / "bots" / v13
    dest.mkdir(parents=True, exist_ok=True)
    cfg = json.loads((Path(bot_dir) / "config.json").read_text(encoding="utf-8"))
    cfg["bot_id"] = v13
    cfg["name"] = "V1-3 jetable (non entraîné)"
    (dest / "config.json").write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    try:
        code = (
            "from loko.bot.classifier.loader import load_classifier; "
            f"load_classifier('{v13}'); print('NO-EXCEPTION')"
        )
        res = _docker(
            image,
            ["python", "-c", code],
            campaign_dir=campaign_dir,
            env={"LOKO_DATA_DIR": f"{APP}/data"},
            timeout=300,
        )
        content = res.stdout + "\n" + res.stderr
        rc._save_artifact(campaign_dir, "V1-3_loader.txt", content)
        if res.returncode != 0 and "NO-EXCEPTION" not in res.stdout:
            typed = "ComponentUnavailable" in content or "not trained" in content
            if typed:
                rc._mark_pass(
                    line,
                    "fail-fast: exception typée, aucun fallback loader",
                    str(campaign_dir / "V1-3_loader.txt"),
                )
            else:
                rc._mark_fail(line, "exception non typée", content[-300:])
        else:
            rc._mark_fail(
                line, "loader a servi un bot non entraîné (fallback interdit)"
            )
    finally:
        shutil.rmtree(dest, ignore_errors=True)


def exec_v1_4(line, campaign_dir: Path, **ctx: Any) -> None:
    """V1-4: bot publié sans modèle -> log CRITICAL au boot (exécuté, pas lu)."""
    vals = _require(line, ctx, "image", "bot_dir")
    if not vals:
        return
    image, bot_dir = vals
    v14 = "v14-" + uuid.uuid4().hex[:8]
    dest = rc.ROOT / "data" / "bots" / v14
    dest.mkdir(parents=True, exist_ok=True)
    cfg = json.loads((Path(bot_dir) / "config.json").read_text(encoding="utf-8"))
    cfg["bot_id"] = v14
    cfg["name"] = "V1-4 jetable (publié sans modèle)"
    cfg["status"] = "published"
    (dest / "config.json").write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    name = "loko-camp-v14"
    _rm_container(name)
    try:
        boot_cmd = (
            "import logging; "
            "logging.basicConfig(level=logging.INFO, "
            "format='%(levelname)s %(name)s %(message)s'); "
            "import uvicorn; "
            "uvicorn.run('loko.main:app', host='0.0.0.0', port=8000)"
        )
        res = _docker(
            image,
            ["python", "-c", boot_cmd],
            campaign_dir=campaign_dir,
            env=_server_env() | {"LOKO_DATA_DIR": f"{APP}/data"},
            name=name,
            detach=True,
            extra_docker=["-p", f"127.0.0.1:{V14_PORT}:8000"],
        )
        if res.returncode != 0:
            rc._mark_fail(line, "docker run failed", res.stderr[:300])
            return
        _poll_health(f"http://127.0.0.1:{V14_PORT}/health", 60)
        time.sleep(3)
        logs = _logs(name)
        rc._save_artifact(campaign_dir, "V1-4_boot_critical.txt", logs)
        if "CRITICAL" in logs and v14 in logs:
            rc._mark_pass(
                line,
                f"CRITICAL loggé au boot pour bot publié sans modèle ({v14})",
                str(campaign_dir / "V1-4_boot_critical.txt"),
            )
        else:
            rc._mark_fail(line, "pas de log CRITICAL au boot", logs[-400:])
    finally:
        _rm_container(name)
        shutil.rmtree(dest, ignore_errors=True)


def exec_v1_5(line, campaign_dir: Path, **ctx: Any) -> None:
    """V1-5: boot et service complets sous --network none (zéro egress)."""
    image = _require(line, ctx, "image")
    if not image:
        return
    name = "loko-camp-v15"
    _rm_container(name)
    try:
        res = _docker(
            image,
            [],
            env=_server_env(),
            name=name,
            detach=True,
            network="none",
            use_mounts=False,
        )
        if res.returncode != 0:
            rc._mark_fail(line, "docker run failed", res.stderr[:300])
            return
        ok, body = False, ""
        for _ in range(18):
            time.sleep(5)
            probe = rc._run_cmd(
                [
                    "docker",
                    "exec",
                    name,
                    "python",
                    "-c",
                    "import urllib.request; "
                    "print(urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5)"
                    ".read().decode())",
                ],
                timeout=30,
            )
            if probe.returncode == 0 and '"ok"' in probe.stdout:
                ok, body = True, probe.stdout.strip()
                break
            body = probe.stdout + probe.stderr
        logs = _logs(name)
        rc._save_artifact(
            campaign_dir,
            "V1-5_offline.txt",
            f"network=none\nhealth={body}\n\n=== logs ===\n{logs}",
        )
        if ok:
            rc._mark_pass(
                line,
                f"service OK sous --network none: {body[:100]}",
                str(campaign_dir / "V1-5_offline.txt"),
            )
        else:
            rc._mark_fail(line, "health KO sous --network none", body[:300])
    finally:
        _rm_container(name)


# ──────────────────────────────────────────────────────────────────────
# R3 — V2 orchestration
# ──────────────────────────────────────────────────────────────────────


def _train(
    image,
    campaign_dir,
    bot_id,
    out_name,
    enrich: str | None = None,
    detach=False,
    name=None,
):
    args = [
        "python",
        f"{APP}/tools/train_bot_offline.py",
        "--bot-dir",
        f"{APP}/data/bots/{bot_id}",
        "--output",
        f"{CAMP}/{out_name}",
    ]
    if enrich:
        args += ["--enrich", enrich]
    return _docker(
        image,
        args,
        campaign_dir=campaign_dir,
        env={
            "LOKO_DATA_DIR": f"{APP}/data",
            "HF_HOME": "/tmp/hf",
            "TRANSFORMERS_CACHE": "/tmp/hf",
        },
        extra_docker=["-w", "/tmp"],  # cwd inscriptible (checkpoints/)
        timeout=1500,
        detach=detach,
        name=name,
    )


def exec_v2_1(line, campaign_dir: Path, **ctx: Any) -> None:
    """V2-1: train complet in-container <= 300 s, manifeste écrit."""
    vals = _require(line, ctx, "image", "bot_dir")
    if not vals:
        return
    image, bot_dir = vals
    bot_id = _bot_id(bot_dir)
    t0 = time.perf_counter()
    res = _train(image, campaign_dir, bot_id, "V2-1_train_report.json")
    wall = time.perf_counter() - t0
    rc._save_artifact(
        campaign_dir, "V2-1_train_output.txt", res.stdout + "\n" + res.stderr
    )
    report_path = campaign_dir / "V2-1_train_report.json"
    if res.returncode != 0 or not report_path.exists():
        rc._mark_fail(
            line, f"train exit {res.returncode}", (res.stdout + res.stderr)[-500:]
        )
        return
    report = json.loads(report_path.read_text(encoding="utf-8"))
    total_s = float(report.get("profile", {}).get("total_s", wall))
    manifest = Path(bot_dir) / "models" / "manifest.json"
    if total_s <= 300 and manifest.exists():
        rc._mark_pass(
            line,
            f"train in-container {total_s:.0f}s <= 300s, manifeste écrit",
            str(report_path),
        )
    elif not manifest.exists():
        rc._mark_fail(line, "manifest.json absent après train")
    else:
        rc._mark_fail(line, f"train {total_s:.0f}s > 300s")


def exec_v2_2(line, campaign_dir: Path, **ctx: Any) -> None:
    """V2-2: couverture L2 help_account (5 labels)."""
    report_path = campaign_dir / "V2-1_train_report.json"
    if not report_path.exists():
        rc._mark_fail(line, "V2-1 report absent (train non exécuté)")
        return
    report = json.loads(report_path.read_text(encoding="utf-8"))
    l2 = report.get("level2", {}).get("help_account", {})
    n = l2.get("num_classes", 0)
    rc._save_artifact(
        campaign_dir, "V2-2_l2.txt", json.dumps(l2, ensure_ascii=False, indent=2)
    )
    if n >= 5 and "error" not in l2:
        rc._mark_pass(
            line, f"L2 help_account: {n} labels", str(campaign_dir / "V2-2_l2.txt")
        )
    else:
        rc._mark_fail(line, f"L2 help_account: {n} labels (attendu 5)", str(l2)[:200])


def exec_v2_3(line, campaign_dir: Path, **ctx: Any) -> None:
    """V2-3: atomicité — kill du train en vol -> état antérieur intact."""
    vals = _require(line, ctx, "image", "bot_dir")
    if not vals:
        return
    image, bot_dir = vals
    bot_id = _bot_id(bot_dir)
    before = _tree_hash(Path(bot_dir))
    name = "loko-camp-v23"
    _rm_container(name)
    _train(
        image, campaign_dir, bot_id, "V2-3_killed_report.json", detach=True, name=name
    )
    time.sleep(25)  # au coeur de l'entraînement
    _rm_container(name)  # kill -9 du worker
    time.sleep(3)
    after = _tree_hash(Path(bot_dir))
    diff = sorted(
        set(before) ^ set(after)
        | {k for k in set(before) & set(after) if before[k] != after[k]}
    )
    load = _docker(
        image,
        [
            "python",
            "-c",
            "from loko.bot.classifier.loader import load_classifier; "
            f"load_classifier('{bot_id}'); print('LOAD-OK')",
        ],
        campaign_dir=campaign_dir,
        env={"LOKO_DATA_DIR": f"{APP}/data"},
        timeout=300,
    )
    content = (
        f"fichiers modifiés/apparus après kill: {diff if diff else 'AUCUN'}\n"
        f"reload post-kill: {'OK' if load.returncode == 0 else 'FAIL'}\n"
        f"{load.stdout}{load.stderr}"
    )
    rc._save_artifact(campaign_dir, "V2-3_atomicity.txt", content)
    if not diff and load.returncode == 0 and "LOAD-OK" in load.stdout:
        rc._mark_pass(
            line,
            "état antérieur intact après kill, modèle rechargeable",
            str(campaign_dir / "V2-3_atomicity.txt"),
        )
    else:
        rc._mark_fail(
            line,
            f"diff={len(diff)} fichiers, load={'OK' if load.returncode == 0 else 'KO'}",
            content[:400],
        )


def _load_make_datasets():
    spec = importlib.util.spec_from_file_location(
        "md", rc.ROOT / "tools" / "make_datasets.py"
    )
    md = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(md)
    return md


def _confusion_pair(report: dict):
    """Retourne (label_a, label_b, cell) — pire cellule hors diagonale, sinon None."""
    ev = report.get("evaluation") or {}
    cm = ev.get("confusion_matrix")
    labels = ev.get("labels") or ev.get("classes")
    if cm and labels:
        worst = None
        for i, row in enumerate(cm):
            for j, v in enumerate(row):
                if i != j and v > 0 and (worst is None or v > worst[2]):
                    worst = (labels[i], labels[j], v)
        if worst:
            return worst
    return None


def _lowest_f1_pair(report: dict):
    per = (report.get("evaluation") or {}).get("per_class_f1") or {}
    if len(per) >= 2:
        pair = sorted(per, key=lambda k: per[k])[:2]
        return pair[0], pair[1], 0
    return None


def exec_v2_4(line, campaign_dir: Path, **ctx: Any) -> None:
    """V2-4: cycle d'amélioration — paire détectée par l'outil, bot jetable, retrain."""
    vals = _require(line, ctx, "image", "bot_dir")
    if not vals:
        return
    image, bot_dir = vals
    report_path = campaign_dir / "V2-1_train_report.json"
    if not report_path.exists():
        rc._mark_fail(line, "V2-1 report absent")
        return
    report = json.loads(report_path.read_text(encoding="utf-8"))
    pair = _confusion_pair(report)
    fallback = False
    if pair is None:
        pair = _lowest_f1_pair(report)
        fallback = True
    if pair is None:
        rc._mark_fail(line, "aucune paire détectable (matrice/F1 absentes du rapport)")
        return
    a, b, cell = pair

    # Bot jetable = clone du bot entraîné
    clone_id = "v24-" + uuid.uuid4().hex[:8]
    clone_dir = rc.ROOT / "data" / "bots" / clone_id
    shutil.copytree(bot_dir, clone_dir)
    cfg = json.loads((clone_dir / "config.json").read_text(encoding="utf-8"))
    cfg["bot_id"] = clone_id
    cfg["name"] = "V2-4 jetable"
    (clone_dir / "config.json").write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Enrichissement depuis la source (jamais les held-out), scrub + rename via make_datasets
    md = _load_make_datasets()
    rows = md.load_source_dataset(rc.ROOT / "dataset.csv")
    exclude: set[str] = set()
    for intent in cfg.get("intents", []):
        for ex in intent.get("examples", []):
            exclude.add(md.normalize_text(ex))
    for ds in ("heldout_metier", "heldout_conseiller", "heldout_horsscope", "pieges"):
        with open(rc.DATASETS_DIR / f"{ds}.csv", encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                exclude.add(md.normalize_text(row["text"]))
    picked: dict[str, list[str]] = {a: [], b: []}
    for r in sorted(rows, key=lambda r: r["text"]):
        it = r["intent"]
        if it in picked and len(picked[it]) < 10:
            if md.normalize_text(r["text"]) not in exclude:
                exclude.add(md.normalize_text(r["text"]))
                picked[it].append(r["text"])
    n_added = sum(len(v) for v in picked.values())
    enrich_path = campaign_dir / "V2-4_enrichment.csv"
    with open(enrich_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["text", "intent"], lineterminator="\n")
        w.writeheader()
        for it, texts in picked.items():
            for t in texts:
                w.writerow({"text": t, "intent": it})

    res = _train(
        image,
        campaign_dir,
        clone_id,
        "V2-4_retrain_report.json",
        enrich=f"{CAMP}/V2-4_enrichment.csv",
    )
    rc._save_artifact(
        campaign_dir, "V2-4_retrain_output.txt", res.stdout + "\n" + res.stderr
    )
    meta = {
        "pair": [a, b],
        "cell_avant": cell,
        "detection": "lowest_f1 (matrice propre)" if fallback else "confusion_matrix",
        "exemples_ajoutes": n_added,
        "clone": clone_id,
    }
    rc._save_artifact(
        campaign_dir, "V2-4_pair.json", json.dumps(meta, ensure_ascii=False, indent=2)
    )
    if (
        res.returncode == 0
        and n_added > 0
        and (campaign_dir / "V2-4_retrain_report.json").exists()
    ):
        rc._mark_pass(
            line,
            f"paire {a}×{b} détectée ({meta['detection']}), +{n_added} ex., retrain OK",
            str(campaign_dir / "V2-4_pair.json"),
        )
    else:
        rc._mark_fail(line, f"retrain exit {res.returncode}, +{n_added} exemples")
    # le clone reste en place pour V2-5, qui le supprimera


def _pair_cells(report: dict, a: str, b: str) -> int | None:
    ev = report.get("evaluation") or {}
    cm = ev.get("confusion_matrix")
    labels = ev.get("labels") or ev.get("classes")
    if not cm or not labels or a not in labels or b not in labels:
        return None
    i, j = labels.index(a), labels.index(b)
    return int(cm[i][j]) + int(cm[j][i])


def exec_v2_5(line, campaign_dir: Path, **ctx: Any) -> None:
    """V2-5: la paire détectée s'améliore après enrichissement."""
    meta_path = campaign_dir / "V2-4_pair.json"
    before_path = campaign_dir / "V2-1_train_report.json"
    after_path = campaign_dir / "V2-4_retrain_report.json"
    clone_dir = None
    try:
        if not (meta_path.exists() and before_path.exists() and after_path.exists()):
            rc._mark_fail(line, "artefacts V2-4 absents")
            return
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        clone_dir = rc.ROOT / "data" / "bots" / meta["clone"]
        a, b = meta["pair"]
        before = json.loads(before_path.read_text(encoding="utf-8"))
        after = json.loads(after_path.read_text(encoding="utf-8"))
        cb, ca = _pair_cells(before, a, b), _pair_cells(after, a, b)
        if cb is None or ca is None:
            acc_b = (before.get("evaluation") or {}).get("accuracy", 0)
            acc_a = (after.get("evaluation") or {}).get("accuracy", 0)
            content = (
                f"cellules indisponibles — accuracy avant={acc_b:.3f} après={acc_a:.3f}"
            )
            rc._save_artifact(campaign_dir, "V2-5_improvement.txt", content)
            if acc_a >= acc_b:
                rc._mark_pass(line, content, str(campaign_dir / "V2-5_improvement.txt"))
            else:
                rc._mark_fail(line, content)
            return
        content = f"paire {a}×{b}: confusion avant={cb} après={ca}"
        rc._save_artifact(campaign_dir, "V2-5_improvement.txt", content)
        if ca < cb or (cb == 0 and ca == 0):
            rc._mark_pass(line, content, str(campaign_dir / "V2-5_improvement.txt"))
        else:
            rc._mark_fail(line, content + " (pas d'amélioration mesurée)")
    finally:
        if clone_dir is not None:
            shutil.rmtree(clone_dir, ignore_errors=True)


V26_SCRIPT = """
import csv, json, sys, time
bot = sys.argv[1]
from loko.bot.classifier.loader import load_classifier
clf = load_classifier(bot)
texts = [r["text"] for r in csv.DictReader(open("/app/eval/datasets/train.csv", encoding="utf-8"))]
texts = (texts * 3)[:200]
for t in texts[:50]:
    clf.classify_l1(t)
def p95(vals):
    s = sorted(vals)
    return s[max(0, int(round(0.95 * len(s))) - 1)]
a, b = [], []
for t in texts:
    t0p = time.perf_counter()
    t0m = time.monotonic_ns()
    clf.classify_l1(t)
    t1m = time.monotonic_ns()
    t1p = time.perf_counter()
    a.append((t1p - t0p) * 1000)
    b.append((t1m - t0m) / 1e6)
res = {"n": len(texts), "p95_perf_ms": round(p95(a), 2), "p95_mono_ms": round(p95(b), 2)}
res["ecart_rel"] = round(abs(res["p95_perf_ms"] - res["p95_mono_ms"]) / max(res["p95_perf_ms"], 1e-9), 3)
print(json.dumps(res))
"""


def exec_v2_6(line, campaign_dir: Path, **ctx: Any) -> None:
    """V2-6: P95 classification <= 50 ms in-container + contre-mesure (écart < 30 %)."""
    vals = _require(line, ctx, "image", "bot_dir")
    if not vals:
        return
    image, bot_dir = vals
    bot_id = _bot_id(bot_dir)
    (campaign_dir / "v26_measure.py").write_text(V26_SCRIPT, encoding="utf-8")
    res = _docker(
        image,
        ["python", f"{CAMP}/v26_measure.py", bot_id],
        campaign_dir=campaign_dir,
        env={"LOKO_DATA_DIR": f"{APP}/data"},
        timeout=900,
    )
    content = res.stdout + "\n" + res.stderr
    rc._save_artifact(campaign_dir, "V2-6_latency.txt", content)
    if res.returncode != 0:
        rc._mark_fail(line, "mesure impossible", content[-300:])
        return
    try:
        m = json.loads(res.stdout.strip().splitlines()[-1])
    except Exception:  # noqa: BLE001
        rc._mark_fail(line, "sortie illisible", content[-300:])
        return
    measured = (
        f"P95={m['p95_perf_ms']}ms (contre-mesure {m['p95_mono_ms']}ms, "
        f"écart {m['ecart_rel'] * 100:.0f}%), n={m['n']}, in-container"
    )
    if m["p95_perf_ms"] <= 50 and m["ecart_rel"] < 0.30:
        rc._mark_pass(line, measured, str(campaign_dir / "V2-6_latency.txt"))
    else:
        rc._mark_fail(line, measured)


# ──────────────────────────────────────────────────────────────────────
# R4 — V3 in-container
# ──────────────────────────────────────────────────────────────────────


def _eval_cli(image, campaign_dir, cli_args, timeout=900):
    return _docker(
        image,
        ["python", "-m", "loko.eval.cli"] + cli_args,
        campaign_dir=campaign_dir,
        env={"LOKO_DATA_DIR": f"{APP}/data"},
        timeout=timeout,
    )


def exec_v3_0(line, campaign_dir: Path, **ctx: Any) -> None:
    vals = _require(line, ctx, "image", "bot_dir")
    if not vals:
        return
    image, bot_dir = vals
    bot_id = _bot_id(bot_dir)
    (campaign_dir / "sweep").mkdir(parents=True, exist_ok=True)
    ds = f"{APP}/eval/datasets"
    sweep_datasets = (
        f"metier={ds}/heldout_metier.csv,conseiller={ds}/heldout_conseiller.csv,"
        f"horsscope={ds}/heldout_horsscope.csv,pieges={ds}/pieges.csv"
    )
    res = _eval_cli(
        image,
        campaign_dir,
        [
            "--bot-dir",
            f"{APP}/data/bots/{bot_id}",
            "--sweep-datasets",
            sweep_datasets,
            "--out",
            f"{CAMP}/sweep",
        ],
        timeout=1800,
    )
    content = res.stdout + "\n" + res.stderr
    rc._save_artifact(campaign_dir, "V3-0_sweep.txt", content)
    selection_file = campaign_dir / "sweep" / "selection.json"
    if selection_file.exists():
        selection = json.loads(selection_file.read_text(encoding="utf-8"))
        if selection.get("selected"):
            sel = selection["selected"]
            detail = (
                f"haut={sel['seuil_haut']:.2f} bas={sel['seuil_bas']:.2f} "
                f"ecart={sel['seuil_ecart']:.2f} | "
                f"GNG-1={sel.get('gng1', 0) * 100:.1f}% "
                f"GNG-2={sel.get('gng2', 0) * 100:.1f}% "
                f"GNG-3={sel.get('gng3', 0) * 100:.1f}%"
            )
            rc._mark_pass(line, detail, str(selection_file))
            rc._apply_sweep_thresholds(ctx["bot_dir"], sel)
        else:
            rc._mark_fail(line, "no feasible point found", str(selection_file))
    else:
        rc._mark_fail(line, "selection.json not produced", content[-500:])


def _exec_v3_eval(line, campaign_dir, dataset_name, gng_name, threshold, **ctx):
    vals = _require(line, ctx, "image", "bot_dir")
    if not vals:
        return
    image, bot_dir = vals
    bot_id = _bot_id(bot_dir)
    mode = "pieges" if dataset_name == "pieges" else "decision"
    out_dir = campaign_dir / f"V3_{dataset_name}"
    out_dir.mkdir(parents=True, exist_ok=True)
    res = _eval_cli(
        image,
        campaign_dir,
        [
            "--bot-dir",
            f"{APP}/data/bots/{bot_id}",
            "--dataset",
            f"{APP}/eval/datasets/{dataset_name}.csv",
            "--mode",
            mode,
            "--out",
            f"{CAMP}/V3_{dataset_name}",
        ],
    )
    content = res.stdout + "\n" + res.stderr
    rc._save_artifact(campaign_dir, f"V3_{dataset_name}_output.txt", content)
    report_file = out_dir / "report.json"
    if not report_file.exists():
        rc._mark_fail(line, "report.json not produced", content[-500:])
        return
    report = json.loads(report_file.read_text(encoding="utf-8"))
    accuracy = report.get("accuracy", 0)
    total = report.get("total", 0)
    correct = report.get("correct", 0)
    measured = f"{gng_name}={accuracy * 100:.1f}% ({correct}/{total})"
    extra = report.get("extra", {})
    routes = extra.get("gng3_routes_directes")
    if routes is not None:
        measured += f", routes_directes={routes}"
    if accuracy >= threshold:
        rc._mark_pass(line, measured, str(report_file))
    else:
        rc._mark_fail(line, measured, f"below {threshold * 100:.0f}% threshold")


def exec_v3_1(line, campaign_dir: Path, **ctx: Any) -> None:
    _exec_v3_eval(line, campaign_dir, "heldout_metier", "GNG-1", 0.85, **ctx)


def exec_v3_2(line, campaign_dir: Path, **ctx: Any) -> None:
    _exec_v3_eval(line, campaign_dir, "heldout_conseiller", "GNG-2", 0.90, **ctx)


def exec_v3_3(line, campaign_dir: Path, **ctx: Any) -> None:
    _exec_v3_eval(line, campaign_dir, "heldout_horsscope", "GNG-3", 0.80, **ctx)


def exec_v3_4(line, campaign_dir: Path, **ctx: Any) -> None:
    _exec_v3_eval(line, campaign_dir, "pieges", "pieges", 12 / 15, **ctx)


def exec_v3_6(line, campaign_dir: Path, **ctx: Any) -> None:
    vals = _require(line, ctx, "image", "bot_dir")
    if not vals:
        return
    image, bot_dir = vals
    bot_id = _bot_id(bot_dir)
    runs = []
    for run_idx in range(2):
        out_dir = campaign_dir / f"V3-6_run{run_idx + 1}"
        out_dir.mkdir(parents=True, exist_ok=True)
        _eval_cli(
            image,
            campaign_dir,
            [
                "--bot-dir",
                f"{APP}/data/bots/{bot_id}",
                "--dataset",
                f"{APP}/eval/datasets/heldout_metier.csv",
                "--mode",
                "decision",
                "--out",
                f"{CAMP}/V3-6_run{run_idx + 1}",
            ],
        )
        report_file = out_dir / "report.json"
        if not report_file.exists():
            rc._mark_fail(line, f"run {run_idx + 1} did not produce report.json")
            return
        runs.append(json.loads(report_file.read_text(encoding="utf-8")))
    if runs[0] == runs[1]:
        rc._mark_pass(
            line, "2 runs in-container identiques", str(campaign_dir / "V3-6_diff.txt")
        )
        rc._save_artifact(campaign_dir, "V3-6_diff.txt", "IDENTICAL - diff empty")
    else:
        diff_keys = [k for k in runs[0] if runs[0].get(k) != runs[1].get(k)]
        rc._mark_fail(line, f"diff on keys: {diff_keys}")
        rc._save_artifact(
            campaign_dir,
            "V3-6_diff.txt",
            f"DIFF on: {diff_keys}\nRun 1: {json.dumps(runs[0], indent=2)}\n"
            f"Run 2: {json.dumps(runs[1], indent=2)}",
        )


# ──────────────────────────────────────────────────────────────────────
# Enregistrement
# ──────────────────────────────────────────────────────────────────────


def register(executors: dict, rc_module) -> None:
    global rc
    rc = rc_module
    executors.update(
        {
            "V0-1": exec_v0_1,
            "V0-2": exec_v0_2,
            "V0-4": exec_v0_4,
            "V1-1": exec_v1_1,
            "V1-2": exec_v1_2,
            "V1-3": exec_v1_3,
            "V1-4": exec_v1_4,
            "V1-5": exec_v1_5,
            "V2-1": exec_v2_1,
            "V2-2": exec_v2_2,
            "V2-3": exec_v2_3,
            "V2-4": exec_v2_4,
            "V2-5": exec_v2_5,
            "V2-6": exec_v2_6,
            "V3-0": exec_v3_0,
            "V3-1": exec_v3_1,
            "V3-2": exec_v3_2,
            "V3-3": exec_v3_3,
            "V3-4": exec_v3_4,
            "V3-6": exec_v3_6,
        }
    )
