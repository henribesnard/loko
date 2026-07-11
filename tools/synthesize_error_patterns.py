#!/usr/bin/env python3
"""W4.1 — Synthesize error patterns from classified V3-1 errors.

Reads V3-1_errors_classified.csv and produces:
  1. Pattern analysis grouped by expected intent
  2. Lexical features (keywords, abbreviations, synonyms)
  3. Discriminant examples needed for each class
  4. Recommended training enrichment priorities

Usage:
    python tools/synthesize_error_patterns.py <errors_csv> <output_dir>
"""

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path


def extract_keywords(text: str) -> list[str]:
    """Extract significant keywords from verbatim (nouns, verbs, domain terms)."""
    # Lowercase and split
    words = re.findall(r"\b\w+\b", text.lower())

    # Filter stop words (French common words)
    stop_words = {
        "le",
        "la",
        "les",
        "un",
        "une",
        "de",
        "du",
        "des",
        "mon",
        "ma",
        "mes",
        "pour",
        "sur",
        "dans",
        "à",
        "a",
        "et",
        "ou",
        "je",
        "tu",
        "il",
        "elle",
        "nous",
        "vous",
        "ils",
        "elles",
        "ce",
        "ça",
        "mon",
        "ton",
        "son",
        "que",
        "qui",
        "quoi",
        "comment",
        "où",
        "est",
        "sont",
        "ai",
        "as",
        "ont",
    }

    keywords = [w for w in words if len(w) > 2 and w not in stop_words]
    return keywords


def identify_abbreviations(text: str) -> list[str]:
    """Identify domain abbreviations (AJ, RIB, CLD, etc.)."""
    # Match uppercase sequences (2-5 chars) or mixed-case acronyms
    abbrevs = re.findall(r"\b[A-Z]{2,5}\b", text)
    return abbrevs


def synthesize_patterns(errors_csv: Path, output_dir: Path) -> None:
    """Synthesize error patterns from classified errors."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load errors
    errors: list[dict] = []
    with open(errors_csv, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            errors.append(row)

    print(f"Loaded {len(errors)} errors from {errors_csv.name}")

    # Group by category and expected intent
    by_category = defaultdict(list)
    by_intent = defaultdict(list)

    for err in errors:
        cat = err.get("category", "").strip()
        expected = err.get("expected", "").strip()
        by_category[cat].append(err)
        by_intent[expected].append(err)

    # Summary
    print("\nError categories:")
    for cat, items in sorted(by_category.items(), key=lambda x: -len(x[1])):
        print(f"  {cat:20s} : {len(items):2d} errors")

    print("\nIntents affected:")
    for intent, items in sorted(by_intent.items(), key=lambda x: -len(x[1])):
        print(f"  {intent:30s} : {len(items):2d} errors")

    # Pattern synthesis per intent
    patterns_by_intent = {}

    for intent, intent_errors in by_intent.items():
        # Extract keywords and abbreviations
        all_keywords = []
        all_abbrevs = []

        for err in intent_errors:
            text = err["text"]
            all_keywords.extend(extract_keywords(text))
            all_abbrevs.extend(identify_abbreviations(text))

        keyword_freq = Counter(all_keywords).most_common(10)
        abbrev_freq = Counter(all_abbrevs).most_common(5)

        # Categorize errors
        threshold_errors = [e for e in intent_errors if e.get("category") == "seuil"]
        ambiguous_errors = [
            e for e in intent_errors if e.get("category") == "verbatim_ambigu"
        ]
        missing_examples = [
            e for e in intent_errors if e.get("category") == "manque_exemples"
        ]

        patterns_by_intent[intent] = {
            "intent": intent,
            "total_errors": len(intent_errors),
            "threshold_errors": len(threshold_errors),
            "ambiguous_errors": len(ambiguous_errors),
            "missing_examples_errors": len(missing_examples),
            "top_keywords": [{"word": kw, "count": cnt} for kw, cnt in keyword_freq],
            "abbreviations": [{"abbrev": ab, "count": cnt} for ab, cnt in abbrev_freq],
            "example_verbatims": [
                {
                    "text": e["text"],
                    "category": e.get("category", ""),
                    "predicted": e.get("predicted", ""),
                    "score": e.get("score", ""),
                }
                for e in intent_errors[:5]  # First 5 examples
            ],
            "recommendations": _generate_recommendations(
                intent, threshold_errors, ambiguous_errors, missing_examples
            ),
        }

    # Write pattern analysis
    patterns_json = output_dir / "error_patterns.json"
    patterns_json.write_text(
        json.dumps(patterns_by_intent, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nPattern analysis written to {patterns_json}")

    # Write enrichment priorities
    priorities = _compute_enrichment_priorities(patterns_by_intent)
    priorities_json = output_dir / "enrichment_priorities.json"
    priorities_json.write_text(
        json.dumps(priorities, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Enrichment priorities written to {priorities_json}")

    # Write markdown summary
    summary_md = output_dir / "pattern_analysis_summary.md"
    with open(summary_md, "w", encoding="utf-8") as f:
        f.write("# W4.1 — Analyse des patterns d'erreur V3-1\n\n")
        f.write(f"**Source** : {errors_csv.name}\n")
        f.write(f"**Total erreurs** : {len(errors)}\n\n")

        f.write("## Distribution par catégorie\n\n")
        for cat, items in sorted(by_category.items(), key=lambda x: -len(x[1])):
            f.write(f"- **{cat}** : {len(items)} erreurs\n")

        f.write("\n## Intentions affectées\n\n")
        for intent, items in sorted(by_intent.items(), key=lambda x: -len(x[1])):
            f.write(f"### {intent} ({len(items)} erreurs)\n\n")

            pattern = patterns_by_intent[intent]

            # Keywords
            if pattern["top_keywords"]:
                f.write("**Mots-clés fréquents** :\n")
                for kw_data in pattern["top_keywords"][:5]:
                    f.write(f"- `{kw_data['word']}` ({kw_data['count']}×)\n")
                f.write("\n")

            # Abbreviations
            if pattern["abbreviations"]:
                f.write("**Abréviations détectées** :\n")
                for ab_data in pattern["abbreviations"]:
                    f.write(f"- `{ab_data['abbrev']}` ({ab_data['count']}×)\n")
                f.write("\n")

            # Example errors
            f.write("**Exemples d'erreurs** :\n")
            for ex in pattern["example_verbatims"][:3]:
                f.write(
                    f'- "{ex["text"]}" → prédit `{ex["predicted"]}` (cat: {ex["category"]})\n'
                )
            f.write("\n")

            # Recommendations
            f.write("**Recommandations** :\n")
            for rec in pattern["recommendations"]:
                f.write(f"- {rec}\n")
            f.write("\n")

        f.write("\n## Priorités d'enrichissement\n\n")
        for p in priorities["priorities"]:
            f.write(
                f"{p['rank']}. **{p['intent']}** (score {p['priority_score']:.1f})\n"
            )
            f.write(f"   - {p['total_errors']} erreurs totales\n")
            f.write(
                f"   - Objectif : ajouter ~{p['recommended_examples']} exemples ciblés\n\n"
            )

    print(f"Markdown summary written to {summary_md}")


def _generate_recommendations(
    intent: str,
    threshold_errors: list[dict],
    ambiguous_errors: list[dict],
    missing_examples: list[dict],
) -> list[str]:
    """Generate enrichment recommendations for an intent."""
    recs = []

    if threshold_errors:
        recs.append(
            f"Ajouter {min(len(threshold_errors), 5)} exemples discriminants pour "
            f"renforcer le signal (actuellement {len(threshold_errors)} faux rejets)"
        )

    if ambiguous_errors:
        recs.append(
            f"Clarifier avec métier : {len(ambiguous_errors)} verbatims ambigus "
            f"déclenchent clarify_inter (besoin reformulation ?)"
        )

    if missing_examples:
        recs.append(
            f"Enrichir frontière avec intent confondu : {len(missing_examples)} routage(s) "
            f"incorrect(s) suggèrent manque d'exemples discriminants"
        )

    if not recs:
        recs.append("Classe stable — maintenir couverture actuelle")

    return recs


def _compute_enrichment_priorities(patterns_by_intent: dict) -> dict:
    """Compute enrichment priorities based on error patterns."""
    # Score = total_errors + 2*ambiguous + 3*missing_examples
    priorities = []

    for intent, pattern in patterns_by_intent.items():
        score = (
            pattern["total_errors"]
            + 2 * pattern["ambiguous_errors"]
            + 3 * pattern["missing_examples_errors"]
        )

        # Recommended examples: proportional to errors (capped at 30)
        recommended = min(30, max(5, pattern["total_errors"] * 2))

        priorities.append(
            {
                "intent": intent,
                "priority_score": score,
                "total_errors": pattern["total_errors"],
                "recommended_examples": recommended,
            }
        )

    # Sort by score descending
    priorities.sort(key=lambda x: -x["priority_score"])

    # Add rank
    for i, p in enumerate(priorities, 1):
        p["rank"] = i

    return {
        "strategy": "Enrichment prioritized by error frequency + ambiguity + missing examples",
        "priorities": priorities,
    }


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        print("\nError: Expected 2 arguments", file=sys.stderr)
        sys.exit(1)

    errors_csv = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])

    if not errors_csv.is_file():
        print(f"Error: {errors_csv} not found", file=sys.stderr)
        sys.exit(1)

    synthesize_patterns(errors_csv, output_dir)
    print("\nPattern synthesis complete!")


if __name__ == "__main__":
    main()
