#!/usr/bin/env python3
"""Search OpenReview papers by keyword, venue, and year.

Fetches all papers from a venue via pagination, then filters client-side
by keyword match in title/abstract.
"""

import argparse
import json
import os
import sys
import time
import openreview

# ---------------------------------------------------------------------------
# Venue → OpenReview invitation string mapping
#
# Coverage policy:
#   - Only venues whose papers live on OpenReview are listed here.
#   - High-impact venues NOT on OpenReview (CVPR, ICCV, ACL, OSDI, SIGCOMM…)
#     cannot be queried through this script.
#   - Topic-to-venue guidance is in SKILL.md Step 2B.
#
# Tier A — Core ML/AI (search for almost every topic)
#   ICLR, NeurIPS, ICML
# Tier B — Specialised (add when topic overlaps)
#   COLM  → Language models, LLMs, NLP
#   CoRL  → Robotics, embodied AI, RL
#   UAI   → Probabilistic ML, Bayesian methods, causality
# ---------------------------------------------------------------------------

VENUE_INVITATIONS = {
    # ── ICLR ────────────────────────────────────────────────────────────────
    ("ICLR", 2026): "ICLR.cc/2026/Conference/-/Submission",
    ("ICLR", 2025): "ICLR.cc/2025/Conference/-/Submission",
    ("ICLR", 2024): "ICLR.cc/2024/Conference/-/Submission",
    ("ICLR", 2023): "ICLR.cc/2023/Conference/-/Submission",
    ("ICLR", 2022): "ICLR.cc/2022/Conference/-/Blind_Submission",
    # ── NeurIPS ─────────────────────────────────────────────────────────────
    ("NeurIPS", 2025): "NeurIPS.cc/2025/Conference/-/Submission",
    ("NeurIPS", 2024): "NeurIPS.cc/2024/Conference/-/Submission",
    ("NeurIPS", 2023): "NeurIPS.cc/2023/Conference/-/Submission",
    ("NeurIPS", 2022): "NeurIPS.cc/2022/Conference/-/Submission",
    # ── ICML ────────────────────────────────────────────────────────────────
    ("ICML", 2025): "ICML.cc/2025/Conference/-/Submission",
    ("ICML", 2024): "ICML.cc/2024/Conference/-/Submission",
    ("ICML", 2023): "ICML.cc/2023/Conference/-/Submission",
    # ── COLM (Conference on Language Modeling) ──────────────────────────────
    ("COLM", 2025): "COLM.cc/2025/Conference/-/Submission",
    ("COLM", 2024): "COLM.cc/2024/Conference/-/Submission",
    # ── CoRL (Conference on Robot Learning) ─────────────────────────────────
    ("CoRL", 2024): "CoRL.cc/2024/Conference/-/Submission",
    ("CoRL", 2023): "CoRL.cc/2023/Conference/-/Submission",
    # ── UAI (Uncertainty in Artificial Intelligence) ─────────────────────────
    ("UAI", 2024): "auai.org/UAI/2024/Conference/-/Submission",
    ("UAI", 2023): "auai.org/UAI/2023/Conference/-/Submission",
}

# Fallback invitation strings (some venues use Blind_Submission)
VENUE_FALLBACK_INVITATIONS = {
    ("ICLR", 2026): "ICLR.cc/2026/Conference/-/Blind_Submission",
    ("ICLR", 2025): "ICLR.cc/2025/Conference/-/Blind_Submission",
    ("ICLR", 2024): "ICLR.cc/2024/Conference/-/Blind_Submission",
    ("ICLR", 2023): "ICLR.cc/2023/Conference/-/Blind_Submission",
    ("NeurIPS", 2025): "NeurIPS.cc/2025/Conference/-/Blind_Submission",
    ("NeurIPS", 2024): "NeurIPS.cc/2024/Conference/-/Blind_Submission",
    ("NeurIPS", 2023): "NeurIPS.cc/2023/Conference/-/Blind_Submission",
    ("ICML", 2025): "ICML.cc/2025/Conference/-/Blind_Submission",
    ("ICML", 2024): "ICML.cc/2024/Conference/-/Blind_Submission",
    ("ICML", 2023): "ICML.cc/2023/Conference/-/Blind_Submission",
    ("COLM", 2025): "COLM.cc/2025/Conference/-/Blind_Submission",
    ("COLM", 2024): "COLM.cc/2024/Conference/-/Blind_Submission",
}


def get_client():
    username = os.environ.get("OPENREVIEW_USERNAME", "").strip()
    password = os.environ.get("OPENREVIEW_PASSWORD", "").strip()
    base_url = os.environ.get("OPENREVIEW_BASE_URL", "https://api2.openreview.net")
    # Only attempt authenticated login when BOTH credentials are present.
    # Passing username=None to the library creates a broken auth state that
    # succeeds at client-creation time but returns HTTP 403 on every request.
    if username and password:
        try:
            client = openreview.api.OpenReviewClient(
                baseurl=base_url, username=username, password=password
            )
            return client
        except Exception as e:
            print(f"[OR] Auth failed ({e}), falling back to anonymous", file=sys.stderr)
    return openreview.api.OpenReviewClient(baseurl=base_url)


def extract_value(field):
    """Get value from either API v1 or v2 content format."""
    if isinstance(field, dict):
        return str(field.get("value", ""))
    return str(field) if field else ""


def get_all_notes(client, invitation: str) -> list:
    """Fetch ALL notes from a venue invitation using pagination."""
    all_notes = []
    offset = 0
    page_size = 500

    while True:
        try:
            notes = client.get_notes(
                invitation=invitation,
                offset=offset,
                limit=page_size,
                sort="cdate:desc",
            )
        except Exception as e:
            print(f"[OR] get_notes failed (offset={offset}): {e}", file=sys.stderr)
            break

        if not notes:
            break
        all_notes.extend(notes)
        offset += len(notes)
        # Rate limit politeness
        if len(notes) == page_size:
            time.sleep(0.1)
        else:
            break  # last page

    return all_notes


def filter_notes_by_topic(notes: list, query: str, max_results: int = 10) -> list:
    """Filter notes by keyword match in title/abstract (case-insensitive)."""
    if not query:
        return notes[:max_results]

    keywords = query.lower().split()
    matched = []

    for note in notes:
        title = extract_value(note.content.get("title", "")).lower()
        abstract = extract_value(note.content.get("abstract", "")).lower()

        if any(kw in title or kw in abstract for kw in keywords):
            matched.append(note)

    return matched[:max_results]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", default="", help="Keyword search query")
    parser.add_argument("--venue", default="ICLR", help="Venue name")
    parser.add_argument("--year", type=int, default=2024, help="Year")
    parser.add_argument("--limit", type=int, default=5, help="Max results")
    args = parser.parse_args()

    client = get_client()

    # Try primary invitation, fall back to alternate
    invitation = VENUE_INVITATIONS.get((args.venue, args.year))
    if not invitation:
        print(json.dumps({"error": f"Unsupported venue/year: {args.venue} {args.year}"}))
        sys.exit(1)

    notes = get_all_notes(client, invitation)

    # Fall back to Blind_Submission if no results
    if not notes:
        fallback = VENUE_FALLBACK_INVITATIONS.get((args.venue, args.year))
        if fallback:
            notes = get_all_notes(client, fallback)

    # Filter by keyword
    matched = filter_notes_by_topic(notes, args.query, max_results=args.limit * 2)

    results = []
    for note in matched[:args.limit]:
        title = extract_value(note.content.get("title", ""))
        abstract = extract_value(note.content.get("abstract", ""))
        authors = note.content.get("authors", {})
        if isinstance(authors, dict):
            authors = authors.get("value", [])

        results.append({
            "forum_id": note.id,
            "number": getattr(note, "number", None),
            "title": title,
            "authors": authors if isinstance(authors, list) else [],
            "abstract": abstract[:500] + ("..." if len(abstract) > 500 else ""),
            "venue": args.venue,
            "year": args.year,
            "url": f"https://openreview.net/forum?id={note.id}",
        })

    print(json.dumps({"papers": results, "total": len(results)}, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
