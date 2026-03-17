#!/usr/bin/env python3
"""
FrontierPilot Social Track — Bilibili + WeChat search.

Usage:
  python3 search_social.py --topic "AutoML" --topic-zh "AutoML 自动机器学习"

Output: JSON with bilibili and wechat sections.
GitHub is handled separately by the github-search skill.
"""

import argparse
import asyncio
import json
import subprocess
import sys


def run_mcporter(query: str, num: int = 5) -> list[dict]:
    """Call Exa via mcporter (tries local first, then docker exec)."""
    import shutil
    inner = f"mcporter call 'exa.web_search_exa(query: \"{query}\", numResults: {num})'"
    if shutil.which("mcporter"):
        cmd = inner
    else:
        cmd = f"docker exec openclaw-openclaw-gateway-1 bash -c '{inner}'"
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=30
        )
        output = result.stdout.strip()
        if not output:
            return []
        # mcporter returns plain text, parse Title/URL/Text blocks
        items = []
        current: dict = {}
        for line in output.splitlines():
            if line.startswith("Title:"):
                if current.get("url"):
                    items.append(current)
                current = {"title": line[6:].strip()}
            elif line.startswith("URL:"):
                current["url"] = line[4:].strip()
            elif line.startswith("Text:") and not current.get("text"):
                current["text"] = line[5:].strip()[:200]
        if current.get("url"):
            items.append(current)
        return items
    except Exception as e:
        return [{"error": str(e)}]


def search_github(topic: str) -> list[dict]:
    """Search GitHub via github-search skill."""
    script = "/home/node/.openclaw/workspace/skills/github-search/scripts/github-search.mjs"
    cmd = f'node "{script}" "{topic}" --min-stars 200 --limit 5'
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=20
        )
        repos = []
        for line in result.stdout.splitlines():
            # Table row format: | rank | name | stars | forks | lang | updated | [查看](url) |
            if line.startswith("| ") and "查看" in line and "github.com" in line:
                parts = [p.strip() for p in line.split("|")]
                if len(parts) >= 7:
                    name = parts[2].strip()
                    stars = parts[3].strip()
                    link_part = parts[7].strip() if len(parts) > 7 else parts[6].strip()
                    url = ""
                    if "](https://github.com/" in link_part:
                        url = link_part.split("](")[1].rstrip(")")
                    if name and url:
                        repos.append({"name": name, "stars": stars, "url": url})
        return repos
    except Exception as e:
        return [{"error": str(e)}]


async def search_wechat_async(topic_zh: str) -> list[dict]:
    """Search WeChat articles via miku_ai with generous timeout."""
    try:
        from miku_ai import get_wexin_article
        results = await asyncio.wait_for(
            get_wexin_article(topic_zh, 5), timeout=10
        )
        return [
            {"title": a.get("title", ""), "url": a.get("url", "")}
            for a in results
            if a.get("title")
        ][:3]
    except Exception:
        return []


def search_wechat(topic_zh: str) -> list[dict]:
    """Sync wrapper with fallback to Exa if miku_ai fails."""
    try:
        results = asyncio.run(search_wechat_async(topic_zh))
        if results:
            return results
    except Exception:
        pass
    # Fallback: Exa search for WeChat articles
    items = run_mcporter(f"{topic_zh} 综述 site:mp.weixin.qq.com", num=3)
    return [
        {"title": i.get("title", ""), "url": i.get("url", "")}
        for i in items
        if i.get("url") and "weixin.qq.com" in i.get("url", "")
    ]


def search_xiaohongshu(topic_zh: str, num: int = 8) -> list[dict]:
    """Search Xiaohongshu posts via Exa. Returns list of {title, author_id, url, text}."""
    items = run_mcporter(f"{topic_zh} site:xiaohongshu.com", num=num)
    results = []
    for item in items:
        if item.get("error"):
            continue
        url = item.get("url", "")
        if "xiaohongshu.com" not in url and "xhslink.com" not in url:
            continue
        author_id = ""
        if "/user/profile/" in url:
            author_id = url.split("/user/profile/")[-1].split("?")[0].split("/")[0]
        results.append({
            "title": item.get("title", ""),
            "url": url,
            "text": item.get("text", "")[:150],
            "author_id": author_id,
        })
    return results


def search_bilibili(topic: str, topic_zh: str) -> list[dict]:
    """Search Bilibili via yt-dlp bilisearch, with Exa fallback."""
    import os
    YTDLP = "/home/node/.local/bin/yt-dlp"
    query = f"{topic_zh} 教程 讲解"

    # Try yt-dlp bilisearch first (returns real video metadata)
    if os.path.exists(YTDLP):
        # Do NOT use 2>/dev/null — let capture_output=True handle stderr so errors are visible
        cmd = f'{YTDLP} --dump-json "bilisearch5:{query}" --no-warnings'
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=45)
            if result.stderr:
                print(f"[yt-dlp stderr] {result.stderr[:300]}", file=sys.stderr)
            videos = []
            seen_ids = set()
            for line in result.stdout.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    v = json.loads(line)
                    vid_id = v.get("id", "")
                    if vid_id in seen_ids:
                        continue
                    seen_ids.add(vid_id)
                    title = v.get("title", "")
                    url = v.get("webpage_url", f"https://www.bilibili.com/video/{vid_id}")
                    view_count = v.get("view_count", 0)
                    if title and url:
                        videos.append({"title": title, "url": url, "view_count": view_count})
                except json.JSONDecodeError:
                    continue
            if videos:
                videos.sort(key=lambda x: x.get("view_count", 0), reverse=True)
                return videos[:3]
            print("[yt-dlp] returned no videos, trying Exa fallback", file=sys.stderr)
        except Exception as e:
            print(f"[yt-dlp] exception: {e}", file=sys.stderr)
    else:
        print(f"[yt-dlp] not found at {YTDLP}", file=sys.stderr)

    # Exa fallback: search for actual video pages (not search result pages)
    items = run_mcporter(f"{topic_zh} 教程 site:bilibili.com/video", num=5)
    videos = [
        {"title": i.get("title", ""), "url": i.get("url", "")}
        for i in items
        if i.get("url") and "/video/" in i.get("url", "") and not i.get("error")
    ]
    if not videos:
        # Broader fallback without site: restriction
        items = run_mcporter(f"bilibili {topic_zh} 教程", num=5)
        videos = [
            {"title": i.get("title", ""), "url": i.get("url", "")}
            for i in items
            if i.get("url") and "bilibili.com/video/" in i.get("url", "") and not i.get("error")
        ]
    return videos[:3]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic", required=True, help="English topic name (short, e.g. 'AutoML')")
    parser.add_argument("--topic-zh", required=True, help="Chinese topic name")
    args = parser.parse_args()

    bilibili = search_bilibili(args.topic, args.topic_zh)
    wechat = search_wechat(args.topic_zh)

    # WeChat fallback: Exa general search for related content
    if not wechat:
        exa = run_mcporter(f"{args.topic_zh} 公众号 技术文章", num=3)
        wechat = [
            {"title": i.get("title", ""), "url": i.get("url", "")}
            for i in exa if i.get("url") and not i.get("error")
        ][:3]

    results = {
        "topic": args.topic,
        "bilibili": bilibili,
        "wechat": wechat,
    }

    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
