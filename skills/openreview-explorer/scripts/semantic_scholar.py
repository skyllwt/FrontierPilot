#!/usr/bin/env python3
"""
Semantic Scholar API client for FrontierPilot.

Subcommands:
  search      - Search papers by keyword, sort by citations / year / relevance
  paper       - Get single paper details with optional references
  references  - Get a paper's reference list (papers it cites); supports --paper-ids for batched multi-ID fetch
  citations   - Get papers that cite a given paper
  author      - Find author profile and top papers
  batch       - Fetch up to 500 papers by ID in a single request (POST /paper/batch)
  recommendations - Get recommended papers from seed IDs

Rate limits (Semantic Scholar public API):
  Without API key : 100 req / 5 min  (~3 s / req)
  With API key    :  ~1 req / s
Set SS_API_KEY env var to unlock authenticated tier.
"""

import argparse
import fcntl
import hashlib
import json
import os
import random
import sys
import time

import requests

# ---------------------------------------------------------------------------
# Rate limiting & auth
# ---------------------------------------------------------------------------

API_KEY = os.environ.get("SS_API_KEY", "")
HEADERS = {"User-Agent": "FrontierPilot/1.0"}
if API_KEY:
    HEADERS["x-api-key"] = API_KEY

# Free tier: 100 req/5 min = 1 req per 3s.  Use 3.5s to stay comfortably
# under the limit.  With an API key the quota is ~1 req/s so 1.1s suffices.
REQUEST_DELAY = 1.1 if API_KEY else 3.5

BASE_URL = "https://api.semanticscholar.org/graph/v1"

# Shared lock file used across all parallel semantic_scholar.py processes.
# Ensures the global request rate stays within the SS quota even when
# OpenClaw launches multiple skills concurrently.
_RATE_LOCK_FILE = "/tmp/fp_ss_ratelimit.lock"


def _rate_limit_wait():
    """Cross-process rate limiter: file lock + shared timestamp.

    Before every HTTP request, each process:
      1. Acquires an exclusive file lock (blocks other processes).
      2. Reads the timestamp of the last request from the lock file.
      3. Sleeps for however long remains of REQUEST_DELAY.
      4. Writes the current time back to the file.
      5. Releases the lock.
    This serialises the *scheduling* step, not the HTTP call itself,
    keeping the inter-request gap >= REQUEST_DELAY regardless of how
    many parallel processes are running.
    """
    with open(_RATE_LOCK_FILE, "a+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            f.seek(0)
            content = f.read().strip()
            last_t = float(content) if content else 0.0
            now = time.time()
            gap = last_t + REQUEST_DELAY - now
            if gap > 0:
                time.sleep(gap)
            f.seek(0)
            f.truncate()
            f.write(str(time.time()))
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


# ---------------------------------------------------------------------------
# File-based response cache
# ---------------------------------------------------------------------------

# Cache lives in /tmp (survives the session, gone on reboot).
# Set SS_CACHE_DIR="" to disable.  Set SS_CACHE_TTL to override TTL (seconds).
_CACHE_DIR = os.environ.get("SS_CACHE_DIR", "/tmp/fp_ss_cache")
_CACHE_TTL = int(os.environ.get("SS_CACHE_TTL", "3600"))  # 1 hour default


def _cache_key(url, params, method, json_body):
    raw = json.dumps(
        {"url": url, "params": params or {}, "method": method, "body": json_body or {}},
        sort_keys=True,
    )
    return hashlib.md5(raw.encode()).hexdigest()


def _cache_get(key):
    if not _CACHE_DIR:
        return None
    path = os.path.join(_CACHE_DIR, key + ".json")
    if not os.path.exists(path):
        return None
    if time.time() - os.path.getmtime(path) > _CACHE_TTL:
        return None  # expired
    try:
        with open(path) as f:
            return json.load(f)
    except (ValueError, IOError):
        return None


def _cache_set(key, data):
    if not _CACHE_DIR:
        return
    try:
        os.makedirs(_CACHE_DIR, exist_ok=True)
        path = os.path.join(_CACHE_DIR, key + ".json")
        with open(path, "w") as f:
            json.dump(data, f)
    except IOError:
        pass  # cache write failure is non-fatal


# ---------------------------------------------------------------------------
# Core HTTP helper
# ---------------------------------------------------------------------------

def _request(url, params=None, method="GET", json_body=None, max_retries=3):
    """GET or POST with cross-process rate limiting, cache, and exponential-backoff retry.

    Structure: _rate_limit_wait() is called at the TOP of every attempt (including
    retries), so the global file-lock coordinator is consulted before each real
    HTTP request.  After a 429 backoff sleep the gap since the last registered
    request is already >> REQUEST_DELAY, so _rate_limit_wait() returns instantly
    on the retry — no double-penalty.
    """
    ck = _cache_key(url, params, method, json_body)
    cached = _cache_get(ck)
    if cached is not None:
        return cached

    for attempt in range(max_retries):
        _rate_limit_wait()  # cross-process quota gate for every HTTP attempt

        try:
            if method == "POST":
                resp = requests.post(
                    url, params=params, json=json_body, headers=HEADERS, timeout=20
                )
            else:
                resp = requests.get(url, params=params, headers=HEADERS, timeout=15)

        except requests.exceptions.Timeout:
            wait = min(30, 5 * (2 ** attempt)) + random.uniform(0, 2)
            print(
                "[SS] Timeout (attempt {}/{}), retrying in {:.1f}s".format(
                    attempt + 1, max_retries, wait
                ),
                file=sys.stderr,
            )
            if attempt < max_retries - 1:
                time.sleep(wait)
                continue
            return {"error": "Request timed out", "detail": url}

        except requests.exceptions.ConnectionError as exc:
            wait = min(30, 3 * (2 ** attempt)) + random.uniform(0, 1)
            if attempt < max_retries - 1:
                time.sleep(wait)
                continue
            return {"error": "Connection error", "detail": str(exc)}

        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 0))
            # Start at 5s (not 10s) so the first retry is less painful.
            # _rate_limit_wait() on the next loop iteration is free (no extra sleep)
            # because the backoff time far exceeds REQUEST_DELAY.
            backoff = min(120, 5 * (2 ** attempt)) + random.uniform(0, 5)
            wait = max(retry_after, backoff)
            print(
                "[SS] Rate limited. Waiting {:.0f}s (attempt {}/{})".format(
                    wait, attempt + 1, max_retries
                ),
                file=sys.stderr,
            )
            time.sleep(wait)
            continue

        if not resp.ok:
            return {"error": "HTTP {}".format(resp.status_code), "detail": resp.text[:300]}

        try:
            data = resp.json()
        except ValueError:
            return {"error": "Invalid JSON", "detail": resp.text[:300]}

        _cache_set(ck, data)
        return data

    return {"error": "Max retries exceeded", "detail": url}


# ---------------------------------------------------------------------------
# Subcommand: search
# ---------------------------------------------------------------------------

# abstract removed — it's large (often 1–2 KB), only 300 chars were ever kept,
# and fetching it for 30–100 papers wastes significant quota.
# authors.name requests only the name string; authors would fetch full objects
# {authorId, name} which we never use.
SEARCH_FIELDS = (
    "title,year,citationCount,influentialCitationCount,authors.name,venue,externalIds"
)

_SORT_MAP = {
    "citations": "citationCount",
    "year": "publicationDate",
    "relevance": None,
}


def cmd_search(args):
    params = {
        "query": args.query,
        "fields": SEARCH_FIELDS,
        # Over-fetch so client-side year filter doesn't leave us short.
        # Keep within 100 (public API page limit for /paper/search).
        "limit": min(args.limit * 3, 100),
    }

    # Server-side sort (citationCount / publicationDate) reduces the need to
    # over-fetch because the best results come back first.
    api_sort = _SORT_MAP.get(args.sort_by)
    if api_sort:
        params["sort"] = api_sort

    # Server-side year filter: avoids fetching papers we'll discard client-side.
    # SS accepts   year=YYYY-    (from year onwards)
    #              year=-YYYY    (up to year)
    #              year=YYYY-YYYY
    # Our semantics: year_after=2022 means year > 2022, i.e. 2023-
    #                year_before=2020 means year < 2020, i.e. -2019
    year_lo = (args.year_after + 1) if args.year_after is not None else None
    year_hi = (args.year_before - 1) if args.year_before is not None else None
    if year_lo and year_hi:
        params["year"] = "{}-{}".format(year_lo, year_hi)
    elif year_lo:
        params["year"] = "{}-".format(year_lo)
    elif year_hi:
        params["year"] = "-{}".format(year_hi)

    data = _request("{}/paper/search".format(BASE_URL), params=params)
    if "error" in data:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    papers_raw = data.get("data", [])

    # Client-side safety filter (server filter may be slightly loose)
    if args.year_after is not None:
        papers_raw = [p for p in papers_raw if p.get("year") and p["year"] > args.year_after]
    if args.year_before is not None:
        papers_raw = [p for p in papers_raw if p.get("year") and p["year"] < args.year_before]

    if args.sort_by == "citations":
        papers_raw.sort(key=lambda p: p.get("citationCount") or 0, reverse=True)
    elif args.sort_by == "year":
        papers_raw.sort(key=lambda p: p.get("year") or 0, reverse=True)

    papers_raw = papers_raw[: args.limit]

    papers = []
    for p in papers_raw:
        authors = [a.get("name", "") for a in (p.get("authors") or [])][:3]
        ext_ids = p.get("externalIds") or {}
        papers.append(
            {
                "paperId": p.get("paperId"),
                "title": p.get("title"),
                "year": p.get("year"),
                "citationCount": p.get("citationCount"),
                "influentialCitationCount": p.get("influentialCitationCount", 0),
                "venue": p.get("venue") or "",
                "authors": authors,
                "arxiv_id": ext_ids.get("ArXiv", ""),
            }
        )

    print(json.dumps({"query": args.query, "total": len(papers), "papers": papers},
                     ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# Subcommand: paper
# ---------------------------------------------------------------------------

def cmd_paper(args):
    if args.include_references:
        fields = (
            "title,year,citationCount,abstract,authors.name,venue,"
            "references.paperId,references.title,references.year"
        )
    else:
        fields = "title,year,citationCount,abstract,authors.name,venue"

    data = _request("{}/paper/{}".format(BASE_URL, args.paper_id), params={"fields": fields})
    if "error" in data:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    result = {
        "paperId": data.get("paperId"),
        "title": data.get("title"),
        "year": data.get("year"),
        "citationCount": data.get("citationCount"),
        "venue": data.get("venue") or "",
        "authors": [a.get("name", "") for a in (data.get("authors") or [])],
        "abstract": (data.get("abstract") or "")[:500],
    }

    if args.include_references:
        refs_raw = (data.get("references") or [])[:10]
        result["references"] = [
            {"paperId": r.get("paperId"), "title": r.get("title"), "year": r.get("year")}
            for r in refs_raw
        ]

    print(json.dumps(result, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# Subcommand: references
# ---------------------------------------------------------------------------

# authors.name is not supported as a nested field in the /references endpoint;
# paperId/title/year/citationCount/venue are sufficient for building citation edges.
_REF_FIELDS = "title,year,citationCount,venue"


def _fetch_references_for(paper_id, limit):
    """Return parsed references list for a single paper_id, or error dict."""
    data = _request(
        "{}/paper/{}/references".format(BASE_URL, paper_id),
        params={"fields": _REF_FIELDS, "limit": min(limit, 500)},
    )
    if "error" in data:
        return data

    refs = []
    for item in data.get("data") or []:
        cited = item.get("citedPaper") or {}
        refs.append(
            {
                "paperId": cited.get("paperId"),
                "title": cited.get("title"),
                "year": cited.get("year"),
                "citationCount": cited.get("citationCount"),
                "venue": cited.get("venue") or "",
            }
        )
    return refs


def cmd_references(args):
    # Multi-ID mode: fetch references for multiple papers in one process call.
    # This avoids repeated Python process startup overhead and keeps the rate
    # limiter active across all fetches (no re-sleeping from scratch each time).
    if hasattr(args, "paper_ids") and args.paper_ids:
        ids = args.paper_ids
        combined = {}
        for pid in ids:
            result = _fetch_references_for(pid, args.limit)
            if isinstance(result, dict) and "error" in result:
                combined[pid] = {"error": result["error"]}
            else:
                combined[pid] = {"paperId": pid, "total": len(result), "references": result}
        print(json.dumps(combined, ensure_ascii=False, indent=2))
        return

    # Single-ID mode (backward-compatible)
    result = _fetch_references_for(args.paper_id, args.limit)
    if isinstance(result, dict) and "error" in result:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    print(json.dumps(
        {"paperId": args.paper_id, "total": len(result), "references": result},
        ensure_ascii=False, indent=2,
    ))


# ---------------------------------------------------------------------------
# Subcommand: batch — POST /paper/batch (up to 500 IDs, 1 request)
# ---------------------------------------------------------------------------

_BATCH_FIELDS = "title,year,citationCount,influentialCitationCount,authors.name,venue,externalIds"


def cmd_batch(args):
    """Fetch details for multiple paper IDs in a single POST request.

    Usage:
        python3 semantic_scholar.py batch --paper-ids ID1 ID2 ID3 ...

    Returns a list of paper objects in the same order as the input IDs.
    Entries where SS returned null (ID not found) are omitted.
    """
    ids = args.paper_ids[:500]
    data = _request(
        "{}/paper/batch".format(BASE_URL),
        params={"fields": _BATCH_FIELDS},
        method="POST",
        json_body={"ids": ids},
    )

    # Batch endpoint returns a JSON array directly (not wrapped in {"data": ...})
    if isinstance(data, dict) and "error" in data:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    papers = []
    for p in (data or []):
        if p is None:
            continue
        ext_ids = p.get("externalIds") or {}
        papers.append(
            {
                "paperId": p.get("paperId"),
                "title": p.get("title"),
                "year": p.get("year"),
                "citationCount": p.get("citationCount"),
                "influentialCitationCount": p.get("influentialCitationCount", 0),
                "venue": p.get("venue") or "",
                "authors": [a.get("name", "") for a in (p.get("authors") or [])][:3],
                "arxiv_id": ext_ids.get("ArXiv", ""),
            }
        )

    print(json.dumps({"total": len(papers), "papers": papers}, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# Subcommand: author
# ---------------------------------------------------------------------------

def cmd_author(args):
    result = _request(
        "{}/author/search".format(BASE_URL),
        params={
            "query": args.name,
            "fields": "name,affiliations,homepage,paperCount,citationCount,hIndex",
            "limit": 5,
        },
    )

    if "error" in result:
        print(json.dumps(result, ensure_ascii=False))
        return

    authors = result.get("data", [])
    if not authors:
        print(json.dumps({"error": "No author found", "query": args.name}, ensure_ascii=False))
        return

    author = authors[0]
    author_id = author.get("authorId")

    papers = []
    if author_id:
        papers_result = _request(
            "{}/author/{}/papers".format(BASE_URL, author_id),
            params={
                "fields": "title,year,citationCount,venue,externalIds",
                "limit": args.limit,
                "sort": "citationCount",
            },
        )
        if "error" not in papers_result:
            papers = papers_result.get("data", [])

    output = {
        "authorId": author_id,
        "name": author.get("name", ""),
        "affiliations": author.get("affiliations", []),
        "homepage": author.get("homepage", ""),
        "paperCount": author.get("paperCount", 0),
        "citationCount": author.get("citationCount", 0),
        "hIndex": author.get("hIndex", 0),
        "top_papers": [
            {
                "title": p.get("title", ""),
                "year": p.get("year"),
                "citationCount": p.get("citationCount", 0),
                "venue": p.get("venue", ""),
                "arxiv_id": (p.get("externalIds") or {}).get("ArXiv", ""),
            }
            for p in papers
        ],
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# Subcommand: citations
# ---------------------------------------------------------------------------

def cmd_citations(args):
    result = _request(
        "{}/paper/{}/citations".format(BASE_URL, args.paper_id),
        params={
            "fields": "title,authors.name,year,citationCount,venue,externalIds",
            "limit": min(args.limit, 500),
        },
    )

    if "error" in result:
        print(json.dumps(result, ensure_ascii=False))
        return

    output = []
    for item in result.get("data", []):
        p = item.get("citingPaper") or {}
        if not p:
            continue
        output.append(
            {
                "paperId": p.get("paperId"),
                "title": p.get("title", ""),
                "authors": [a.get("name") for a in (p.get("authors") or [])[:3]],
                "year": p.get("year"),
                "citationCount": p.get("citationCount", 0),
                "venue": p.get("venue", ""),
                "arxiv_id": (p.get("externalIds") or {}).get("ArXiv", ""),
            }
        )

    output.sort(key=lambda x: x["citationCount"], reverse=True)
    print(json.dumps(output[: args.limit], ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# Subcommand: recommendations
# ---------------------------------------------------------------------------

def cmd_recommendations(args):
    url = "https://api.semanticscholar.org/recommendations/v1/papers/"
    payload = {"positivePaperIds": args.paper_ids[:5], "negativePaperIds": []}
    params = {
        # abstract excluded — large field, not needed for recommendations list
        "fields": "title,authors.name,year,citationCount,venue,externalIds",
        "limit": min(args.limit, 500),
    }

    data = _request(url, params=params, method="POST", json_body=payload)
    if isinstance(data, dict) and "error" in data:
        print(json.dumps(data, ensure_ascii=False))
        return

    papers = data.get("recommendedPapers", [])
    output = []
    for p in papers[: args.limit]:
        output.append(
            {
                "paperId": p.get("paperId"),
                "title": p.get("title", ""),
                "authors": [a.get("name") for a in (p.get("authors") or [])[:3]],
                "year": p.get("year"),
                "citationCount": p.get("citationCount", 0),
                "venue": p.get("venue", ""),
                "arxiv_id": (p.get("externalIds") or {}).get("ArXiv", ""),
            }
        )

    output.sort(key=lambda x: x["citationCount"], reverse=True)
    print(json.dumps(output, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser():
    parser = argparse.ArgumentParser(
        description="Semantic Scholar API client for FrontierPilot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # --- search ---
    p_search = sub.add_parser("search", help="Search papers by keyword")
    p_search.add_argument("--query", required=True)
    p_search.add_argument(
        "--sort-by", choices=["citations", "year", "relevance"], default="relevance"
    )
    p_search.add_argument("--year-before", type=int, default=None, metavar="YEAR")
    p_search.add_argument("--year-after", type=int, default=None, metavar="YEAR")
    p_search.add_argument("--limit", type=int, default=10)
    p_search.set_defaults(func=cmd_search)

    # --- paper ---
    p_paper = sub.add_parser("paper", help="Get details for a single paper")
    p_paper.add_argument("--paper-id", required=True, help="S2 paper ID or arXiv:XXXX.XXXXX")
    p_paper.add_argument("--include-references", action="store_true")
    p_paper.set_defaults(func=cmd_paper)

    # --- references ---
    p_refs = sub.add_parser("references", help="Get papers cited by a given paper")
    id_group = p_refs.add_mutually_exclusive_group(required=True)
    id_group.add_argument("--paper-id", help="Single S2 paper ID")
    id_group.add_argument(
        "--paper-ids",
        nargs="+",
        help="Multiple S2 paper IDs (fetched sequentially in one process, "
             "returns a dict keyed by paper ID)",
    )
    p_refs.add_argument("--limit", type=int, default=20)
    p_refs.set_defaults(func=cmd_references)

    # --- batch ---
    p_batch = sub.add_parser(
        "batch",
        help="Fetch up to 500 papers by ID in one POST request (most quota-efficient)",
    )
    p_batch.add_argument("--paper-ids", nargs="+", required=True, help="S2 paper IDs (max 500)")
    p_batch.set_defaults(func=cmd_batch)

    # --- author ---
    p_author = sub.add_parser("author", help="Find author profile and top papers")
    p_author.add_argument("--name", required=True)
    p_author.add_argument("--limit", type=int, default=5)
    p_author.set_defaults(func=cmd_author)

    # --- citations ---
    p_cit = sub.add_parser("citations", help="Get papers that cite a given paper")
    p_cit.add_argument("--paper-id", required=True)
    p_cit.add_argument("--limit", type=int, default=20)
    p_cit.set_defaults(func=cmd_citations)

    # --- recommendations ---
    p_rec = sub.add_parser("recommendations", help="Get recommended similar papers")
    p_rec.add_argument("--paper-ids", nargs="+", required=True, help="Seed SS paper IDs")
    p_rec.add_argument("--limit", type=int, default=10)
    p_rec.set_defaults(func=cmd_recommendations)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
