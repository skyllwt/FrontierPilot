#!/usr/bin/env python3
"""Fetch reviews and rebuttals for an OpenReview paper."""

import argparse
import json
import os
import re
import sys
import openreview

REVIEW_PATTERNS = {
    # ICLR — "Submission{num}" for 2024+, "Paper{num}" for 2023
    ("ICLR", 2026): "ICLR.cc/2026/Conference/Submission{num}/-/Official_Review",
    ("ICLR", 2025): "ICLR.cc/2025/Conference/Submission{num}/-/Official_Review",
    ("ICLR", 2024): "ICLR.cc/2024/Conference/Submission{num}/-/Official_Review",
    ("ICLR", 2023): "ICLR.cc/2023/Conference/Paper{num}/-/Official_Review",
    # NeurIPS
    ("NeurIPS", 2025): "NeurIPS.cc/2025/Conference/Paper{num}/-/Official_Review",
    ("NeurIPS", 2024): "NeurIPS.cc/2024/Conference/Paper{num}/-/Official_Review",
    ("NeurIPS", 2023): "NeurIPS.cc/2023/Conference/Paper{num}/-/Official_Review",
    # ICML
    ("ICML", 2025): "ICML.cc/2025/Conference/Paper{num}/-/Official_Review",
    ("ICML", 2024): "ICML.cc/2024/Conference/Paper{num}/-/Official_Review",
    ("ICML", 2023): "ICML.cc/2023/Conference/Paper{num}/-/Official_Review",
    # COLM
    ("COLM", 2025): "COLM.cc/2025/Conference/Paper{num}/-/Official_Review",
    ("COLM", 2024): "COLM.cc/2024/Conference/Paper{num}/-/Official_Review",
    # CoRL
    ("CoRL", 2024): "CoRL.cc/2024/Conference/Paper{num}/-/Official_Review",
    ("CoRL", 2023): "CoRL.cc/2023/Conference/Paper{num}/-/Official_Review",
    # UAI
    ("UAI", 2024): "auai.org/UAI/2024/Conference/Paper{num}/-/Official_Review",
    ("UAI", 2023): "auai.org/UAI/2023/Conference/Paper{num}/-/Official_Review",
}

REBUTTAL_PATTERNS = {
    ("ICLR", 2026): "ICLR.cc/2026/Conference/Submission{num}/-/Rebuttal_Revision",
    ("ICLR", 2025): "ICLR.cc/2025/Conference/Submission{num}/-/Rebuttal_Revision",
    ("ICLR", 2024): "ICLR.cc/2024/Conference/Submission{num}/-/Rebuttal_Revision",
    ("ICLR", 2023): "ICLR.cc/2023/Conference/Paper{num}/-/Rebuttal",
    ("COLM", 2025): "COLM.cc/2025/Conference/Paper{num}/-/Rebuttal",
    ("COLM", 2024): "COLM.cc/2024/Conference/Paper{num}/-/Rebuttal",
}

# ── Venue-specific review field names ──────────────────────────────────────────
REVIEW_FIELD_MAP = {
    ("ICLR", None):     {"rating": "rating",          "strengths": "strengths", "weaknesses": "weaknesses"},
    ("ICML", None):     {"rating": "rating",          "strengths": "strengths", "weaknesses": "weaknesses"},
    ("COLM", None):     {"rating": "rating",          "strengths": "strengths", "weaknesses": "weaknesses"},
    ("CoRL", None):     {"rating": "rating",          "strengths": "strengths", "weaknesses": "weaknesses"},
    ("UAI",  None):     {"rating": "rating",          "strengths": "strengths", "weaknesses": "weaknesses"},
    # NeurIPS 2025 uses the same string-based Recommendation as 2024
    ("NeurIPS", 2025):  {"rating": "Recommendation",  "strengths": "strengths", "weaknesses": "weaknesses"},
    ("NeurIPS", 2024):  {"rating": "Recommendation",  "strengths": "strengths", "weaknesses": "weaknesses"},
    ("NeurIPS", 2023):  {"rating": "rating",          "strengths": "strengths", "weaknesses": "weaknesses"},
}

# NeurIPS 2024/2025 uses non-numeric Recommendation strings
NEURIPS_STRING_SCORE_MAP = {
    "strong accept": 10,
    "accept (oral)": 9,
    "accept (spotlight)": 8,
    "accept (poster)": 7,
    "reject": 3,
    "strong reject": 1,
}


def get_field_map(venue: str, year: int) -> dict:
    """Get the review field names for a given venue/year."""
    for (v, y), fields in REVIEW_FIELD_MAP.items():
        if v.upper() in venue.upper() and y == year:
            return fields
    for (v, y), fields in REVIEW_FIELD_MAP.items():
        if v.upper() in venue.upper() and y is None:
            return fields
    return {"rating": "rating", "strengths": "strengths", "weaknesses": "weaknesses"}


def extract_rating(rating_value: str, venue: str = "", year: int = 0) -> float:
    """Extract numeric rating from various formats."""
    if not rating_value:
        return 0.0
    rating_str = str(rating_value)

    # NeurIPS 2024/2025 string-based Recommendation field
    if "NeurIPS" in venue and year in (2024, 2025):
        for key, score in NEURIPS_STRING_SCORE_MAP.items():
            if key in rating_str.lower():
                return float(score)

    # Parse "N: description" or plain number
    match = re.match(r"^(\d+(?:\.\d+)?)", rating_str.strip())
    if match:
        val = float(match.group(1))
        if 1 <= val <= 10:
            return val

    return 0.0


def get_client():
    username = os.environ.get("OPENREVIEW_USERNAME", "").strip()
    password = os.environ.get("OPENREVIEW_PASSWORD", "").strip()
    base_url = os.environ.get("OPENREVIEW_BASE_URL", "https://api2.openreview.net")
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--forum-id", required=True, help="OpenReview forum ID")
    parser.add_argument("--paper-num", type=int, help="Paper number (optional, auto-detected)")
    parser.add_argument("--venue", default="ICLR", help="Venue name")
    parser.add_argument("--year", type=int, default=2024, help="Year")
    args = parser.parse_args()

    client = get_client()

    # Auto-detect paper number if not provided
    paper_num = args.paper_num
    if not paper_num:
        try:
            note = client.get_note(args.forum_id)
            paper_num = getattr(note, "number", None)
        except Exception:
            pass

    result = {
        "forum_id": args.forum_id,
        "paper_num": paper_num,
        "venue": args.venue,
        "year": args.year,
        "reviews": [],
        "rebuttals": [],
    }

    # Get venue-specific field names
    field_map = get_field_map(args.venue, args.year)
    rating_field = field_map["rating"]
    strengths_field = field_map["strengths"]
    weaknesses_field = field_map["weaknesses"]

    # Fetch reviews
    review_inv = REVIEW_PATTERNS.get((args.venue, args.year), "")
    if review_inv and paper_num:
        review_inv = review_inv.format(num=paper_num)
        try:
            reviews = client.get_notes(forum=args.forum_id, invitation=review_inv)
            for r in reviews:
                c = r.content
                rating_raw = extract_value(c.get(rating_field, ""))
                rating_numeric = extract_rating(rating_raw, args.venue, args.year)

                result["reviews"].append({
                    "rating": rating_raw,
                    "rating_numeric": rating_numeric,
                    "confidence": extract_value(c.get("confidence", "")),
                    "summary": extract_value(c.get("summary", ""))[:600],
                    "soundness": extract_value(c.get("soundness", "")),
                    "presentation": extract_value(c.get("presentation", "")),
                    "contribution": extract_value(c.get("contribution", "")),
                    "strengths": extract_value(c.get(strengths_field, ""))[:400],
                    "weaknesses": extract_value(c.get(weaknesses_field, ""))[:400],
                })
        except Exception as e:
            result["review_error"] = str(e)

    # Compute average rating
    numeric_ratings = [r["rating_numeric"] for r in result["reviews"] if r["rating_numeric"] > 0]
    result["avg_rating"] = round(sum(numeric_ratings) / len(numeric_ratings), 1) if numeric_ratings else None

    # Fetch rebuttals
    rebuttal_inv = REBUTTAL_PATTERNS.get((args.venue, args.year), "")
    if rebuttal_inv and paper_num:
        rebuttal_inv = rebuttal_inv.format(num=paper_num)
        try:
            rebuttals = client.get_notes(forum=args.forum_id, invitation=rebuttal_inv)
            for rb in rebuttals:
                c = rb.content
                text = extract_value(c.get("rebuttal", c.get("comment", "")))
                result["rebuttals"].append({"text": text[:800]})
        except Exception as e:
            result["rebuttal_error"] = str(e)

    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
