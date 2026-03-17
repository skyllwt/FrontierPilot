#!/usr/bin/env python3
"""Pre-cache demo data for FrontierPilot AutoML demo."""

import json
import os
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

CACHE_DIR = Path(__file__).parent.parent / "demo_cache"
CACHE_DIR.mkdir(exist_ok=True)

def save(filename, data):
    path = CACHE_DIR / filename
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print(f"  ✅ Saved {filename} ({len(data) if isinstance(data, list) else len(data.get('papers', data.get('reviews', [])))} items)")

# ─── 1. arXiv ────────────────────────────────────────────────────────────────
print("\n[1/3] Fetching arXiv papers...")
arxiv_results = []
for query in ["automl automated machine learning", "neural architecture search NAS"]:
    url = (
        "http://export.arxiv.org/api/query"
        f"?search_query=all:{requests.utils.quote(query)}"
        "&start=0&max_results=5&sortBy=relevance"
    )
    try:
        r = requests.get(url, timeout=15)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        root = ET.fromstring(r.text)
        for entry in root.findall("atom:entry", ns):
            title = entry.find("atom:title", ns).text.strip().replace("\n", " ")
            summary = entry.find("atom:summary", ns).text.strip()[:400]
            arxiv_id = entry.find("atom:id", ns).text.split("/abs/")[-1]
            authors = [a.find("atom:name", ns).text for a in entry.findall("atom:author", ns)][:3]
            published = entry.find("atom:published", ns).text[:10]
            if not any(p["arxiv_id"] == arxiv_id for p in arxiv_results):
                arxiv_results.append({
                    "arxiv_id": arxiv_id,
                    "title": title,
                    "authors": authors,
                    "published": published,
                    "abstract": summary,
                    "url": f"https://arxiv.org/abs/{arxiv_id}",
                })
        time.sleep(1)
    except Exception as e:
        print(f"  ⚠️  arXiv query '{query}' failed: {e}")

save("arxiv_automl.json", arxiv_results)

# ─── 2. Semantic Scholar foundational papers ──────────────────────────────────
print("\n[2/3] Fetching Semantic Scholar foundational papers...")
ss_papers = []
for query in ["automated machine learning", "neural architecture search differentiable", "hyperparameter optimization bayesian"]:
    try:
        r = requests.get(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            params={
                "query": query,
                "fields": "title,year,citationCount,authors,abstract,venue,externalIds",
                "limit": 10,
            },
            headers={"User-Agent": "FrontierPilot/1.0"},
            timeout=15,
        )
        data = r.json()
        for p in data.get("data", []):
            if p.get("year") and p.get("citationCount", 0) > 100:
                paper_id = p.get("paperId", "")
                if not any(x["paperId"] == paper_id for x in ss_papers):
                    ss_papers.append({
                        "paperId": paper_id,
                        "title": p.get("title", ""),
                        "year": p.get("year"),
                        "citationCount": p.get("citationCount", 0),
                        "venue": p.get("venue", ""),
                        "authors": [a["name"] for a in p.get("authors", [])[:3]],
                        "abstract": (p.get("abstract") or "")[:300],
                    })
        time.sleep(1.5)
    except Exception as e:
        print(f"  ⚠️  SS query '{query}' failed: {e}")

# Sort by citation count descending, keep top 10
ss_papers.sort(key=lambda x: x.get("citationCount", 0), reverse=True)
ss_papers = ss_papers[:10]
save("ss_automl_foundational.json", {"papers": ss_papers})

# ─── 3. OpenReview reviews ────────────────────────────────────────────────────
print("\n[3/3] Fetching OpenReview ICLR 2024 AutoML reviews...")
try:
    import openreview
    client = openreview.api.OpenReviewClient(
        baseurl="https://api2.openreview.net",
        username="weitong.qian@stu.pku.edu.cn",
        password="PKU@lltqwt1121",
    )

    # Search for AutoML-related papers in ICLR 2024
    keywords = ["automl", "neural architecture search", "nas", "hyperparameter", "auto-sklearn", "darts"]
    automl_papers = []

    notes = client.get_notes(invitation="ICLR.cc/2024/Conference/-/Submission", limit=300)
    for note in notes:
        title = ""
        content = note.content or {}
        t = content.get("title", "")
        title = t.get("value", t) if isinstance(t, dict) else str(t)
        abstract = ""
        ab = content.get("abstract", "")
        abstract = ab.get("value", ab) if isinstance(ab, dict) else str(ab)
        text = (title + " " + abstract).lower()
        if any(kw in text for kw in keywords):
            automl_papers.append({"id": note.id, "number": getattr(note, "number", None), "title": title})

    print(f"  Found {len(automl_papers)} AutoML-related ICLR 2024 papers")

    # Fetch reviews for first 5 papers
    cached_reviews = []
    for paper in automl_papers[:5]:
        forum_id = paper["id"]
        num = paper["number"]
        if not num:
            continue
        inv = f"ICLR.cc/2024/Conference/Submission{num}/-/Official_Review"
        try:
            reviews = client.get_notes(forum=forum_id, invitation=inv)
            paper_reviews = []
            for r in reviews:
                c = r.content or {}
                def ev(f):
                    return f.get("value", "") if isinstance(f, dict) else str(f) if f else ""
                paper_reviews.append({
                    "rating": ev(c.get("rating", "")),
                    "confidence": ev(c.get("confidence", "")),
                    "summary": ev(c.get("summary", ""))[:500],
                    "strengths": ev(c.get("strengths", ""))[:400],
                    "weaknesses": ev(c.get("weaknesses", ""))[:400],
                    "soundness": ev(c.get("soundness", "")),
                })
            if paper_reviews:
                cached_reviews.append({
                    "forum_id": forum_id,
                    "paper_num": num,
                    "title": paper["title"],
                    "reviews": paper_reviews,
                })
                print(f"  ✓ {paper['title'][:60]}... ({len(paper_reviews)} reviews)")
            time.sleep(0.5)
        except Exception as e:
            print(f"  ⚠️ Reviews for {forum_id}: {e}")

    save("openreview_automl_reviews.json", cached_reviews)

except Exception as e:
    print(f"  ⚠️  OpenReview failed: {e}")
    save("openreview_automl_reviews.json", [])

print("\n✅ Demo cache complete.")
print(f"   Cache dir: {CACHE_DIR}")
for f in sorted(CACHE_DIR.glob("*.json")):
    size = f.stat().st_size
    print(f"   {f.name}: {size} bytes")
