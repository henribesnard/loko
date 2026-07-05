"""C2 — Evaluation runner: run datasets through classifier + decision logic.

Modes:
  - raw: argmax accuracy (classifier only, no thresholds)
  - decision: uses decide() with real thresholds from bot config
  - pieges: reads expected_behavior, produces per-case verdict

Metrics:
  - GNG-1: route correct OR clarification pertinent (heldout_metier)
  - GNG-2: transverse demande_conseiller detected (heldout_conseiller)
  - GNG-3: reject/escalate for out-of-scope (heldout_horsscope)
"""

from __future__ import annotations

import csv
import json
import logging
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from loko.eval.decision import Decision, decide

logger = logging.getLogger(__name__)


@dataclass
class EvalRow:
    """One row from the evaluation."""
    text: str
    expected: str
    predicted: str | None = None
    score: float = 0.0
    decision_type: str = ""
    correct: bool = False
    detail: str = ""


@dataclass
class EvalReport:
    """Full evaluation report."""
    mode: str
    dataset: str
    total: int = 0
    correct: int = 0
    accuracy: float = 0.0
    per_class: dict[str, dict[str, Any]] = field(default_factory=dict)
    confusion: dict[str, dict[str, int]] = field(default_factory=dict)
    errors: list[EvalRow] = field(default_factory=list)
    all_rows: list[EvalRow] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)
    duration_s: float = 0.0

    def to_report_dict(self) -> dict[str, Any]:
        """Deterministic report data (no timing — goes into report.json)."""
        d = {
            "mode": self.mode,
            "dataset": self.dataset,
            "total": self.total,
            "correct": self.correct,
            "accuracy": round(self.accuracy, 4),
            "per_class": self.per_class,
            "confusion": self.confusion,
            "n_errors": len(self.errors),
            "errors": [asdict(e) for e in self.errors[:50]],
        }
        if self.extra:
            d["extra"] = self.extra
        return d

    def to_meta_dict(self) -> dict[str, Any]:
        """Non-deterministic metadata (timing — goes into meta.json)."""
        return {
            "duration_s": round(self.duration_s, 2),
        }

    def to_dict(self) -> dict[str, Any]:
        """Full report including timing (for backward compat / in-memory use)."""
        d = self.to_report_dict()
        d.update(self.to_meta_dict())
        return d


def load_dataset(path: Path) -> list[dict[str, str]]:
    """Load a CSV dataset with 'text' and 'intent' columns."""
    rows: list[dict[str, str]] = []
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            rows.append(row)
    return rows


def evaluate_raw(
    classifier: Any,
    dataset_path: Path,
) -> EvalReport:
    """Mode 'raw': argmax accuracy of classifier alone (no thresholds).

    Parameters
    ----------
    classifier : ClassifierProtocol
        Object with classify_l1(text) -> [(id, score), ...]
    dataset_path : Path
        CSV with text, intent columns.
    """
    start = time.perf_counter()
    rows = load_dataset(dataset_path)
    report = EvalReport(mode="raw", dataset=dataset_path.name, total=len(rows))

    confusion: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    class_correct: dict[str, int] = defaultdict(int)
    class_total: dict[str, int] = defaultdict(int)

    for row in rows:
        text = row["text"]
        expected = row["intent"]
        class_total[expected] += 1

        scores = classifier.classify_l1(text)
        predicted = scores[0][0] if scores else "unknown"
        pred_score = scores[0][1] if scores else 0.0

        correct = predicted == expected
        if correct:
            report.correct += 1
            class_correct[expected] += 1

        confusion[expected][predicted] += 1

        eval_row = EvalRow(
            text=text, expected=expected, predicted=predicted,
            score=pred_score, correct=correct,
        )
        report.all_rows.append(eval_row)
        if not correct:
            report.errors.append(eval_row)

    report.accuracy = report.correct / report.total if report.total > 0 else 0.0
    report.confusion = {k: dict(v) for k, v in confusion.items()}

    for cls in sorted(class_total.keys()):
        report.per_class[cls] = {
            "total": class_total[cls],
            "correct": class_correct[cls],
            "accuracy": round(class_correct[cls] / class_total[cls], 4) if class_total[cls] > 0 else 0.0,
        }

    report.duration_s = time.perf_counter() - start
    return report


def evaluate_decision(
    classifier: Any,
    dataset_path: Path,
    config: Any,
) -> EvalReport:
    """Mode 'decision': uses decide() with real thresholds.

    Correctness criteria (GNG-1):
      - route correct: decision.type == 'route' AND intent matches expected
      - clarification pertinent: decision.type == 'clarify_inter' AND
        expected intent is in the candidates

    For heldout_conseiller (GNG-2):
      - correct if decision.type == 'escalate'

    For heldout_horsscope (GNG-3):
      - correct if decision.type in ('reject', 'escalate')
    """
    start = time.perf_counter()
    rows = load_dataset(dataset_path)
    report = EvalReport(mode="decision", dataset=dataset_path.name, total=len(rows))

    ds_name = dataset_path.stem.lower()

    for row in rows:
        text = row["text"]
        expected = row["intent"]

        scores = classifier.classify_l1(text)
        decision = decide(scores, config)

        # Determine correctness based on dataset type
        if "conseiller" in ds_name:
            # GNG-2: must escalate
            correct = decision.type == "escalate"
        elif "horsscope" in ds_name or "hors" in ds_name:
            # GNG-3: must reject or escalate
            correct = decision.type in ("reject", "escalate")
        else:
            # GNG-1: route correct OR clarification pertinent
            if decision.type == "route":
                correct = decision.intent == expected
            elif decision.type == "clarify_inter":
                candidate_ids = [c[0] for c in decision.candidates]
                correct = expected in candidate_ids
            elif decision.type == "escalate" and expected == "demande_conseiller":
                correct = True
            elif decision.type == "reject" and expected == "hors_perimetre":
                correct = True
            else:
                correct = False

        if correct:
            report.correct += 1

        eval_row = EvalRow(
            text=text, expected=expected,
            predicted=decision.intent,
            score=decision.score,
            decision_type=decision.type,
            correct=correct,
            detail=f"candidates={decision.candidates}" if decision.candidates else "",
        )
        report.all_rows.append(eval_row)
        if not correct:
            report.errors.append(eval_row)

    report.accuracy = report.correct / report.total if report.total > 0 else 0.0
    report.duration_s = time.perf_counter() - start
    return report


def check_expected_behavior(expected: str, decision: Decision) -> bool:
    """Check if a decision matches the expected_behavior specification.

    Grammar (from pieges.csv):
      route:{intent}                         → type == "route" AND intent matches
      clarify_intra:{intent}                 → route to correct intent OR
                                               clarify_inter with intent in candidates
      clarify_inter:{a}|{b}[|{c}]           → type == "clarify_inter" AND all
                                               expected intents in candidates
      escalate[:{detail}]                    → type == "escalate"
      reject                                 → type == "reject"
    """
    if ":" in expected:
        behavior_type, detail = expected.split(":", 1)
    else:
        behavior_type = expected
        detail = ""

    if behavior_type == "route":
        return decision.type == "route" and decision.intent == detail

    if behavior_type == "clarify_intra":
        # Direct route to the correct intent is acceptable (even better)
        if decision.type == "route" and decision.intent == detail:
            return True
        # Clarification with the intent in candidates is also acceptable
        if decision.type == "clarify_inter":
            candidate_ids = [c[0] for c in decision.candidates]
            return detail in candidate_ids
        return False

    if behavior_type == "clarify_inter":
        if decision.type != "clarify_inter":
            return False
        expected_intents = detail.split("|")
        candidate_ids = [c[0] for c in decision.candidates]
        return all(intent_id in candidate_ids for intent_id in expected_intents)

    if behavior_type == "escalate":
        return decision.type == "escalate"

    if behavior_type == "reject":
        return decision.type == "reject"

    return False


def evaluate_pieges(
    classifier: Any,
    pieges_path: Path,
    config: Any,
) -> EvalReport:
    """Mode 'pieges': evaluate edge cases with expected_behavior.

    Each row has: id, text, expected_behavior, note.
    expected_behavior grammar: route:{intent}, clarify_intra:{intent},
    clarify_inter:{a}|{b}[|{c}], escalate[:{detail}], reject.
    """
    start = time.perf_counter()
    rows = load_dataset(pieges_path)
    report = EvalReport(mode="pieges", dataset=pieges_path.name, total=len(rows))

    for row in rows:
        text = row["text"]
        expected = row["expected_behavior"]
        case_id = row.get("id", "?")
        note = row.get("note", "")

        scores = classifier.classify_l1(text)
        decision = decide(scores, config)

        correct = check_expected_behavior(expected, decision)

        # Build a descriptive predicted string for errors.csv
        predicted_str = decision.type
        if decision.intent:
            predicted_str += f":{decision.intent}"
        if decision.candidates:
            cand_str = "|".join(c[0] for c in decision.candidates)
            predicted_str = f"{decision.type}:{cand_str}"

        eval_row = EvalRow(
            text=text, expected=expected,
            predicted=predicted_str,
            score=decision.score,
            decision_type=decision.type,
            correct=correct,
            detail=f"{case_id}: {note} | intent={decision.intent}",
        )
        report.all_rows.append(eval_row)
        if not correct:
            report.errors.append(eval_row)
        if correct:
            report.correct += 1

    report.accuracy = report.correct / report.total if report.total > 0 else 0.0
    report.duration_s = time.perf_counter() - start
    return report


def threshold_sweep(
    classifier: Any,
    dataset_path: Path,
    config: Any,
    seuil_haut_range: tuple[float, float, float] = (0.6, 0.9, 0.05),
    seuil_bas_range: tuple[float, float, float] = (0.3, 0.6, 0.05),
) -> list[dict[str, Any]]:
    """C3 — Sweep thresholds and compute accuracy for each pair.

    Returns a list of dicts with: seuil_haut, seuil_bas, accuracy,
    n_route, n_clarify, n_reject, n_escalate.
    """
    rows = load_dataset(dataset_path)
    results: list[dict[str, Any]] = []

    # Pre-compute classifications once
    all_scores: list[tuple[str, list[tuple[str, float]]]] = []
    for row in rows:
        scores = classifier.classify_l1(row["text"])
        all_scores.append((row["intent"], scores))

    # Sweep
    sh = seuil_haut_range[0]
    while sh <= seuil_haut_range[1] + 1e-9:
        sb = seuil_bas_range[0]
        while sb <= seuil_bas_range[1] + 1e-9:
            if sb >= sh:
                sb += seuil_bas_range[2]
                continue

            # Create config copy with new thresholds
            modified_journey = config.journey.model_copy(
                update={"seuil_haut": sh, "seuil_bas": sb},
            )
            modified_config = config.model_copy(update={"journey": modified_journey})

            n_correct = 0
            counts = {"route": 0, "clarify_inter": 0, "reject": 0, "escalate": 0}

            for expected, scores in all_scores:
                decision = decide(scores, modified_config)
                counts[decision.type] = counts.get(decision.type, 0) + 1

                if decision.type == "route" and decision.intent == expected:
                    n_correct += 1
                elif decision.type == "clarify_inter":
                    candidate_ids = [c[0] for c in decision.candidates]
                    if expected in candidate_ids:
                        n_correct += 1

            results.append({
                "seuil_haut": round(sh, 3),
                "seuil_bas": round(sb, 3),
                "accuracy": round(n_correct / len(all_scores), 4) if all_scores else 0,
                **counts,
            })

            sb += seuil_bas_range[2]
        sh += seuil_haut_range[2]

    return results


_ERRORS_CSV_FIELDNAMES = [
    "text", "expected", "predicted", "score", "decision_type", "correct", "detail",
]


def write_report(report: EvalReport, out_dir: Path) -> None:
    """Write evaluation results to files.

    Produces:
      - report.json  — deterministic data (metrics, verdicts, hashes)
      - meta.json    — non-deterministic data (duration_s)
      - errors.csv   — all errors (if any)
      - confusion.csv — confusion matrix (raw mode only)
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    # report.json — deterministic only (L1.3: no duration_s)
    report_path = out_dir / "report.json"
    report_path.write_text(
        json.dumps(report.to_report_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # meta.json — non-deterministic (timing)
    meta_path = out_dir / "meta.json"
    meta_path.write_text(
        json.dumps(report.to_meta_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # errors.csv — L1.1: fieldnames include 'correct'
    if report.errors:
        errors_path = out_dir / "errors.csv"
        with open(errors_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=_ERRORS_CSV_FIELDNAMES)
            writer.writeheader()
            for e in report.errors:
                writer.writerow(asdict(e))

    # confusion.csv (for raw mode)
    if report.confusion:
        confusion_path = out_dir / "confusion.csv"
        all_labels = sorted(set(
            list(report.confusion.keys()) +
            [l for v in report.confusion.values() for l in v.keys()]
        ))
        with open(confusion_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["true\\predicted"] + all_labels)
            for true_label in all_labels:
                row_data = [report.confusion.get(true_label, {}).get(pred, 0) for pred in all_labels]
                writer.writerow([true_label] + row_data)
