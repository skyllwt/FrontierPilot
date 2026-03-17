#!/usr/bin/env python3
"""
FrontierPilot Social Agent

Backend priority for Xiaohongshu:
  1. xiaohongshu-mcp via mcporter  — real data, persistent login via QR code
  2. xhs CLI (xiaohongshu-cli)     — real data, needs browser cookie
  3. Demo fallback                  — plausible generated data for hackathon demo

Capabilities:
  1. search_xiaohongshu  — find relevant posts and authors
  2. follow_experts       — follow active authors (mcp / xhs-cli / planned)
  3. find_wechat_groups   — find WeChat group QR codes in posts, draft join message

Usage:
  python3 social_agent.py --topic-zh "扩散模型" --dry-run
  python3 social_agent.py --topic-zh "扩散模型" --follow
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Strip SOCKS proxy — xhs CLI's httpx crashes on socks://
_ENV_NO_SOCKS = dict(os.environ)
for _k in ("ALL_PROXY", "all_proxy"):
    _ENV_NO_SOCKS.pop(_k, None)


# ─────────────────────────────────────────────────────────────────────────────
# Health check — xiaohongshu-mcp via mcporter
# (pattern from Agent-Reach/agent_reach/channels/xiaohongshu.py)
# ─────────────────────────────────────────────────────────────────────────────

def _mcporter_status_ok(stdout: str) -> bool:
    """Return True if mcporter JSON output shows status == 'ok'."""
    text = stdout.strip().lstrip("\ufeff")  # strip Windows BOM
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return str(data.get("status", "")).lower() == "ok"
    except (json.JSONDecodeError, ValueError):
        pass
    normalised = text.lower().replace("\r\n", "\n").replace(" ", "")
    return '"status":"ok"' in normalised


def check_xhs_mcp() -> Tuple[str, str]:
    """Check xiaohongshu-mcp health. Returns (status, message).

    status: 'ok' | 'warn' | 'off'
    - ok   — mcporter + xiaohongshu MCP fully connected
    - warn — configured but MCP service not responding (container down / not logged in)
    - off  — mcporter not found or xiaohongshu not configured
    """
    mcporter = shutil.which("mcporter")
    if not mcporter:
        return "off", "mcporter 未安装"

    # Check if xiaohongshu is configured
    try:
        r = subprocess.run(
            [mcporter, "config", "get", "xiaohongshu", "--json"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode != 0 or "xiaohongshu" not in r.stdout.lower():
            return "off", (
                "xiaohongshu-mcp 未配置。运行：\n"
                "  docker run -d --name xiaohongshu-mcp -p 18060:18060 "
                "-v xhs-data:/app/data xpzouying/xiaohongshu-mcp\n"
                "  mcporter config add xiaohongshu http://localhost:18060/mcp\n"
                "  然后打开 http://localhost:18060 用手机扫码登录"
            )
    except Exception:
        return "off", "mcporter 连接异常"

    # Check if MCP service is alive
    try:
        r = subprocess.run(
            [mcporter, "list", "xiaohongshu", "--json"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0 and _mcporter_status_ok(r.stdout):
            return "ok", "xiaohongshu-mcp 已连接"
        return "warn", "xiaohongshu-mcp 已配置但服务未响应（容器没跑 / 未登录）"
    except subprocess.TimeoutExpired:
        return "warn", "xiaohongshu-mcp 健康检查超时"
    except Exception:
        return "warn", "xiaohongshu-mcp 连接异常"


def _xhs_cli_status() -> Tuple[str, str]:
    """Check xhs CLI status. Returns ('ok'|'warn'|'off', message)."""
    if not shutil.which("xhs"):
        return "off", "xhs CLI 未安装"
    try:
        r = subprocess.run(
            ["xhs", "status", "--json"],
            capture_output=True, text=True, timeout=10,
            env=_ENV_NO_SOCKS,
        )
        data = json.loads(r.stdout) if r.stdout.strip() else {}
        if data.get("ok") or data.get("logged_in"):
            return "ok", "xhs CLI 已登录"
        # check for not_authenticated
        if data.get("error", {}).get("code") == "not_authenticated":
            return "warn", "xhs CLI 已安装但未登录（需要浏览器 cookie）"
        return "warn", "xhs CLI 状态未知"
    except Exception:
        return "warn", "xhs CLI 已安装，登录状态未知"


# ─────────────────────────────────────────────────────────────────────────────
# mcporter xiaohongshu-mcp call wrapper
# ─────────────────────────────────────────────────────────────────────────────

def _mcporter_xhs(tool: str, params: Optional[Dict] = None, timeout: int = 30) -> Optional[dict]:
    """Call a xiaohongshu-mcp tool via mcporter. Returns parsed JSON or None.

    tool: MCP tool name, e.g. 'search_notes'
    params: dict of parameters, e.g. {"keyword": "扩散模型", "count": 10}
    """
    mcporter = shutil.which("mcporter")
    if not mcporter:
        return None

    params = params or {}
    # Build mcporter call string: mcporter call 'xiaohongshu.tool(k: v, ...)'
    param_parts = []
    for k, v in params.items():
        if isinstance(v, str):
            escaped = v.replace("'", "\\'").replace('"', '\\"')
            param_parts.append('{}: "{}"'.format(k, escaped))
        else:
            param_parts.append("{}: {}".format(k, v))
    call_expr = "xiaohongshu.{}({})".format(tool, ", ".join(param_parts))

    try:
        r = subprocess.run(
            [mcporter, "call", call_expr],
            capture_output=True, text=True, timeout=timeout,
        )
        if r.returncode != 0:
            print("[mcp] {} failed: {}".format(tool, r.stderr[:200]), file=sys.stderr)
            return None
        output = r.stdout.strip()
        if not output:
            return None
        # Try JSON parse; mcporter may wrap result in {"result": ...}
        try:
            data = json.loads(output)
            return data
        except (json.JSONDecodeError, ValueError):
            # Return raw text wrapped for callers to handle
            return {"_raw": output}
    except subprocess.TimeoutExpired:
        print("[mcp] {} timed out".format(tool), file=sys.stderr)
        return None
    except Exception as e:
        print("[mcp] {}: {}".format(tool, e), file=sys.stderr)
        return None


def _parse_mcp_search_results(data: dict, topic_zh: str, num: int) -> List[dict]:
    """Parse xiaohongshu-mcp search_feeds result into standard post dicts.

    xiaohongshu-mcp search_feeds returns items with feed_id and xsec_token.
    We preserve these for follow-up actions (like_feed, get_feed_detail).
    """
    results = []

    # Unwrap common mcporter/MCP envelope formats
    # Typical: {"result": [...]} or {"data": {"items": [...]}} or plain list
    if isinstance(data, list):
        items = data
    else:
        for key in ("result", "data", "feeds", "items", "notes"):
            candidate = data.get(key)
            if candidate is not None:
                data = candidate
                break
        items = data if isinstance(data, list) else data.get("items", data.get("feeds", []))

    for item in (items or [])[:num]:
        if not isinstance(item, dict):
            continue
        # xiaohongshu-mcp search_feeds fields:
        #   id/feed_id, xsecToken, noteCard.displayTitle, noteCard.user.{userId,nickname},
        #   noteCard.interactInfo.likedCount
        feed_id = item.get("id", item.get("feed_id", item.get("note_id", "")))
        xsec_token = item.get("xsecToken", item.get("xsec_token", ""))
        note_card = item.get("noteCard", item.get("note_card", {})) or {}
        title = (note_card.get("displayTitle") or note_card.get("title")
                 or item.get("title", item.get("desc", "")))
        author = (note_card.get("user") or item.get("author", item.get("user", {}))) or {}
        nickname = author.get("nickname", author.get("nickName", author.get("name", ""))) if isinstance(author, dict) else str(author)
        author_id = (author.get("userId", author.get("user_id", "")) if isinstance(author, dict) else "") or ""
        interact = note_card.get("interactInfo", item.get("interactInfo", {})) or {}
        likes_raw = interact.get("likedCount", item.get("liked_count", item.get("likes", "0")))
        likes = str(likes_raw) if likes_raw else "0"
        results.append({
            "title": (title or "{}的笔记".format(topic_zh))[:50],
            "url": "https://www.xiaohongshu.com/explore/{}".format(feed_id) if feed_id else "",
            "author": nickname,
            "author_id": str(author_id),
            "feed_id": feed_id,
            "xsec_token": xsec_token,
            "likes": likes,
            "source": "mcp",
        })

    return results


# ─────────────────────────────────────────────────────────────────────────────
# Demo fallback data
# ─────────────────────────────────────────────────────────────────────────────

def _demo_xhs_posts(topic_zh: str, num: int) -> List[dict]:
    """Generate plausible demo posts when no backend is available."""
    import hashlib
    templates = [
        ("整理了{}领域最全学习路线🔥附资源汇总", "AI研究小助手", "1.2k"),
        ("分享一下我们组在{}方向的最新工作", "深度学习打工人", "856"),
        ("{}入门指南：从零到论文复现", "炼丹师_Liang", "3.4k"),
        ("顶会最新{}论文速读（附代码链接）", "科研日记本", "2.1k"),
        ("{}技术交流群已开放，附加群方式", "AI技术社群", "987"),
        ("手把手复现{}经典工作，踩坑总结", "研究生在读中", "1.5k"),
    ]
    results = []
    for i, (title_tpl, author, likes) in enumerate(templates[:num]):
        title = title_tpl.format(topic_zh)
        note_id = hashlib.md5((topic_zh + str(i)).encode()).hexdigest()[:18]
        author_id = "uid_" + hashlib.md5((author + topic_zh).encode()).hexdigest()[:10]
        results.append({
            "title": title,
            "url": "https://www.xiaohongshu.com/explore/" + note_id,
            "author": author,
            "author_id": author_id,
            "likes": likes,
            "source": "demo",
        })
    return results


# ─────────────────────────────────────────────────────────────────────────────
# 功能一：小红书搜索
# Backend priority: xiaohongshu-mcp → xhs CLI → demo
# ─────────────────────────────────────────────────────────────────────────────

def search_xiaohongshu(topic_zh: str, num: int = 10) -> List[dict]:
    """搜索小红书相关帖子，返回 {title, author, author_id, url, likes, source}。"""

    # ── 1. Try xiaohongshu-mcp via mcporter ──────────────────────────────────
    mcp_status, _ = check_xhs_mcp()
    if mcp_status == "ok":
        print("[social] backend: xiaohongshu-mcp", file=sys.stderr)
        # Tool: search_feeds(keyword, filters?)
        data = _mcporter_xhs("search_feeds", {"keyword": topic_zh}, timeout=40)
        if data and not data.get("_raw"):
            results = _parse_mcp_search_results(data, topic_zh, num)
            if results:
                return results
        print("[social] mcp search_feeds returned no results, trying xhs CLI", file=sys.stderr)

    # ── 2. Try xhs CLI ────────────────────────────────────────────────────────
    if shutil.which("xhs"):
        print("[social] backend: xhs CLI", file=sys.stderr)
        try:
            r = subprocess.run(
                ["xhs", "search", topic_zh, "--sort", "popular", "--json"],
                capture_output=True, text=True, timeout=30,
                env=_ENV_NO_SOCKS,
            )
            data = json.loads(r.stdout) if r.stdout.strip() else {}
            if data.get("error", {}).get("code") == "not_authenticated":
                print("[social] xhs not authenticated", file=sys.stderr)
            else:
                items = data.get("data", {}).get("items", [])
                results = []
                for item in items[:num]:
                    card = item.get("note_card", {})
                    user = card.get("user", {})
                    interact = card.get("interact_info", {})
                    note_id = item.get("id", "")
                    author_id = user.get("user_id", "")
                    title = card.get("title", "") or card.get("desc", "")
                    nickname = user.get("nickname", "")
                    results.append({
                        "title": (title or "{}的笔记".format(topic_zh))[:50],
                        "url": "https://www.xiaohongshu.com/explore/{}".format(note_id),
                        "author": nickname,
                        "author_id": author_id,
                        "likes": interact.get("liked_count", "0"),
                        "source": "xhs-cli",
                    })
                if results:
                    return results
        except Exception as e:
            print("[social] xhs CLI error: {}".format(e), file=sys.stderr)

    # ── 3. Demo fallback ─────────────────────────────────────────────────────
    print("[social] backend: demo fallback", file=sys.stderr)
    return _demo_xhs_posts(topic_zh, num)


# ─────────────────────────────────────────────────────────────────────────────
# 功能二：关注小红书领域专家
# Backend priority: xiaohongshu-mcp → xhs CLI → planned
# ─────────────────────────────────────────────────────────────────────────────

def engage_experts(posts: List[dict], dry_run: bool = False) -> List[dict]:
    """与小红书领域专家互动（点赞）。

    xiaohongshu-mcp 不提供 follow_user 工具，改用 like_feed 实现可见的社交行动。
    posts: list of dicts with feed_id, xsec_token, author, title from search results.
    Returns list of {author, title, feed_id, status, reason}
    """
    if not posts:
        return []

    results = []

    if dry_run:
        for p in posts:
            results.append({
                "author": p.get("author", ""),
                "title": p.get("title", ""),
                "feed_id": p.get("feed_id", ""),
                "status": "planned",
                "reason": "dry-run 模式：将为此笔记点赞",
            })
        return results

    mcp_status, _ = check_xhs_mcp()

    # ── 1. like_feed via xiaohongshu-mcp ────────────────────────────────────
    if mcp_status == "ok":
        for p in posts:
            feed_id = p.get("feed_id", "")
            xsec_token = p.get("xsec_token", "")
            if not feed_id:
                continue
            params = {"feed_id": feed_id}
            if xsec_token:
                params["xsec_token"] = xsec_token
            data = _mcporter_xhs("like_feed", params, timeout=15)
            if data is not None and not data.get("error"):
                results.append({
                    "author": p.get("author", ""),
                    "title": p.get("title", ""),
                    "feed_id": feed_id,
                    "status": "liked",
                    "reason": "点赞成功（mcp）",
                })
            else:
                results.append({
                    "author": p.get("author", ""),
                    "title": p.get("title", ""),
                    "feed_id": feed_id,
                    "status": "planned",
                    "reason": "点赞待执行（登录后生效）",
                })
        return results

    # ── 2. Planned fallback ───────────────────────────────────────────────────
    return [{
        "author": p.get("author", ""),
        "title": p.get("title", ""),
        "feed_id": p.get("feed_id", ""),
        "status": "planned",
        "reason": "已加入待互动列表（配置 xiaohongshu-mcp 后执行）",
    } for p in posts]


# Keep backward-compatible alias
def follow_experts(author_ids: List[str], dry_run: bool = False) -> List[dict]:
    """Legacy wrapper: returns planned status for all IDs (no follow tool in MCP)."""
    return [{
        "author_id": aid,
        "status": "planned",
        "reason": "已加入待关注列表（xiaohongshu-mcp 暂不支持 follow，登录后用 App 关注）",
    } for aid in author_ids]


# ─────────────────────────────────────────────────────────────────────────────
# 功能三：微信群发现 + QR 解码 + 申请文案生成
# ─────────────────────────────────────────────────────────────────────────────

def _call_llm(prompt: str, max_tokens: int = 150) -> str:
    """Call LLM via priority chain: Gateway → OpenRouter → Anthropic → ''."""
    import urllib.request

    messages = [{"role": "user", "content": prompt}]

    gateway_token = os.environ.get("OPENCLAW_GATEWAY_TOKEN", "")
    gateway_port = os.environ.get("OPENCLAW_GATEWAY_PORT", "18789")
    if gateway_token:
        try:
            req = urllib.request.Request(
                "http://127.0.0.1:{}/v1/chat/completions".format(gateway_port),
                data=json.dumps({"model": "openclaw:main", "messages": messages,
                                 "stream": False, "max_tokens": max_tokens},
                                ensure_ascii=False).encode(),
                headers={"Authorization": "Bearer " + gateway_token,
                         "Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read())["choices"][0]["message"]["content"].strip()
        except Exception:
            pass

    openrouter_key = os.environ.get("OPENROUTER_API_KEY", "")
    if openrouter_key:
        try:
            req = urllib.request.Request(
                "https://openrouter.ai/api/v1/chat/completions",
                data=json.dumps({"model": "anthropic/claude-haiku-4-5", "messages": messages,
                                 "max_tokens": max_tokens}, ensure_ascii=False).encode(),
                headers={"Authorization": "Bearer " + openrouter_key,
                         "Content-Type": "application/json",
                         "HTTP-Referer": "https://frontierPilot.ai"},
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read())["choices"][0]["message"]["content"].strip()
        except Exception:
            pass

    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if anthropic_key:
        try:
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                data=json.dumps({"model": "claude-haiku-4-5-20251001", "max_tokens": max_tokens,
                                 "messages": messages}, ensure_ascii=False).encode(),
                headers={"x-api-key": anthropic_key, "anthropic-version": "2023-06-01",
                         "Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read())["content"][0]["text"].strip()
        except Exception as e:
            print("[social] LLM failed: {}".format(e), file=sys.stderr)

    return ""


def _generate_join_message(group_name: str, topic_zh: str) -> str:
    """Generate a WeChat group join request message."""
    result = _call_llm(
        "请帮我写一条加入微信群「{}」的申请语。"
        "我是一名研究{}方向的研究生。"
        "语气真诚、简洁，控制在50字以内。".format(group_name, topic_zh),
        max_tokens=150,
    )
    if result:
        return result
    return (
        "您好！我是研究{}方向的研究生，"
        "希望加入「{}」和大家交流学习，"
        "也可以分享我们组的最新进展。感谢！".format(topic_zh, group_name)
    )


def _decode_qr_from_url(image_url: str) -> str:
    """Download image and decode QR code. Returns decoded text or ''."""
    try:
        import requests
        from PIL import Image
        from pyzbar.pyzbar import decode

        resp = requests.get(image_url, timeout=10)
        resp.raise_for_status()
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(resp.content)
            tmp_path = f.name
        try:
            img = Image.open(tmp_path)
            decoded = decode(img)
            if decoded:
                return decoded[0].data.decode("utf-8")
        finally:
            Path(tmp_path).unlink(missing_ok=True)
    except ImportError:
        print("[social] pyzbar/Pillow not installed", file=sys.stderr)
    except Exception as e:
        print("[social] QR decode error: {}".format(e), file=sys.stderr)
    return ""


def _search_wechat_posts_mcp(topic_zh: str) -> List[dict]:
    """Search for WeChat group posts via xiaohongshu-mcp."""
    posts = []
    for kw in [topic_zh + " 微信群", topic_zh + " 加群"]:
        data = _mcporter_xhs("search_notes", {"keyword": kw, "count": 5})
        if not data or data.get("_raw"):
            continue
        items = _parse_mcp_search_results(data, topic_zh, 5)
        for item in items:
            posts.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "text": "",
                "image_urls": [],
            })
        if posts:
            break
    return posts


def _search_wechat_posts_xhs(topic_zh: str) -> List[dict]:
    """Search for WeChat group posts via xhs CLI."""
    posts = []
    for kw in [topic_zh + " 微信群", topic_zh + " 加群", topic_zh + " 交流群"]:
        try:
            r = subprocess.run(
                ["xhs", "search", kw, "--sort", "popular", "--json"],
                capture_output=True, text=True, timeout=30,
                env=_ENV_NO_SOCKS,
            )
            data = json.loads(r.stdout) if r.stdout.strip() else {}
            if not data.get("ok", True) or data.get("error"):
                break
            items = data.get("data", {}).get("items", [])
            for item in items[:5]:
                card = item.get("note_card", {})
                note_id = item.get("id", "")
                img_urls = []
                for img in card.get("image_list", []):
                    for info in img.get("info_list", []):
                        if info.get("image_scene") == "WB_DFT":
                            img_urls.append(info["url"])
                posts.append({
                    "title": (card.get("title", "") or card.get("desc", ""))[:50],
                    "url": "https://www.xiaohongshu.com/explore/{}".format(note_id),
                    "text": card.get("desc", ""),
                    "image_urls": img_urls,
                })
            if posts:
                break
        except Exception as e:
            print("[social] xhs search error: {}".format(e), file=sys.stderr)
    return posts


def find_wechat_groups(topic_zh: str, dry_run: bool = False) -> List[dict]:
    """搜索含微信群二维码的帖子，提取 QR 并生成入群申请。"""
    results = []

    # Collect candidate posts from whichever backend works
    posts = []
    mcp_status, _ = check_xhs_mcp()
    if not dry_run:
        if mcp_status == "ok":
            posts = _search_wechat_posts_mcp(topic_zh)
        if not posts and shutil.which("xhs"):
            posts = _search_wechat_posts_xhs(topic_zh)

    if dry_run or not posts:
        results.append({
            "group_name": "AIGC {}交流群".format(topic_zh),
            "qr_url": "",
            "weixin_link": "weixin://groupjoin/DEMO_LINK",
            "draft_message": _generate_join_message("AIGC {}交流群".format(topic_zh), topic_zh),
            "source_url": "https://www.xiaohongshu.com/explore/demo",
            "status": "demo",
        })
        return results

    # Try to extract QR codes from posts
    import re
    for post in posts[:4]:
        source_url = post.get("url", "")
        text = post.get("text", "")
        title = post.get("title", "")
        img_urls = post.get("image_urls", [])
        weixin_link = ""
        qr_url = ""

        for img_url in img_urls:
            decoded = _decode_qr_from_url(img_url)
            if decoded and "weixin" in decoded.lower():
                weixin_link = decoded
                qr_url = img_url
                break

        if not weixin_link:
            links = re.findall(r"weixin://[^\s'\"<>]+", text)
            if links:
                weixin_link = links[0]

        if not weixin_link and not qr_url:
            continue

        group_name = re.sub(r"[加二维码]", "", title).strip()[:20] or "{}交流群".format(topic_zh)
        results.append({
            "group_name": group_name,
            "qr_url": qr_url,
            "weixin_link": weixin_link,
            "draft_message": _generate_join_message(group_name, topic_zh),
            "source_url": source_url,
            "status": "ready",
        })
        break

    if not results:
        results.append({
            "group_name": "{}研究交流群".format(topic_zh),
            "qr_url": "",
            "weixin_link": "",
            "draft_message": _generate_join_message("{}研究交流群".format(topic_zh), topic_zh),
            "source_url": posts[0].get("url", "") if posts else "",
            "status": "qr_not_found",
        })

    return results


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="FrontierPilot Social Agent")
    parser.add_argument("--topic-zh", default="", help="Chinese topic name, e.g. '扩散模型'")
    parser.add_argument("--dry-run", action="store_true", help="Plan only, no real actions")
    parser.add_argument("--follow", action="store_true", help="Also follow discovered experts")
    parser.add_argument("--num", type=int, default=8, help="Number of posts to search")
    parser.add_argument("--doctor", action="store_true", help="Check backend health and exit")
    args = parser.parse_args()

    # Doctor mode
    if not args.topic_zh and not args.doctor:
        parser.error("--topic-zh is required")

    if args.doctor:
        mcp_st, mcp_msg = check_xhs_mcp()
        xhs_st, xhs_msg = _xhs_cli_status()
        icon = {"ok": "✅", "warn": "⚠️", "off": "❌"}
        print("小红书后台状态：")
        print("  {} xiaohongshu-mcp: {}".format(icon.get(mcp_st, "?"), mcp_msg))
        print("  {} xhs CLI:         {}".format(icon.get(xhs_st, "?"), xhs_msg))
        if mcp_st != "ok" and xhs_st != "ok":
            print("\n推荐方案（xiaohongshu-mcp，一次登录长期有效）：")
            print("  docker run -d --name xiaohongshu-mcp -p 18060:18060 \\")
            print("    -v xhs-data:/app/data xpzouying/xiaohongshu-mcp")
            print("  mcporter config add xiaohongshu http://localhost:18060/mcp")
            print("  # 然后打开 http://localhost:18060 用手机小红书扫码登录")
        sys.exit(0)

    print("\n" + "=" * 55)
    print("🌐 FrontierPilot Social Agent — {}".format(args.topic_zh))
    print("=" * 55)

    # Show active backend
    mcp_st, mcp_msg = check_xhs_mcp()
    if mcp_st == "ok":
        print("后台：xiaohongshu-mcp（真实数据）")
    elif shutil.which("xhs"):
        print("后台：xhs CLI")
    else:
        print("后台：demo 模式（运行 --doctor 查看如何启用真实后台）")

    if args.dry_run:
        print("⚠️  DRY RUN 模式")

    # Step 1: Search
    print("\n[1/3] 🔍 搜索小红书: {}".format(args.topic_zh))
    xhs_posts = search_xiaohongshu(args.topic_zh, num=args.num)
    print("  → 找到 {} 篇相关帖子".format(len(xhs_posts)))
    for i, p in enumerate(xhs_posts[:3], 1):
        print("  {}. {} (@{}, 👍{})".format(i, p["title"][:40], p.get("author", ""), p.get("likes", "")))
        print("     {}".format(p["url"]))

    # Step 2: Engage with experts (like posts via MCP; follow not available in MCP)
    engage_posts = [p for p in xhs_posts if p.get("feed_id") or p.get("author_id")][:3]
    engage_results = []  # type: List[dict]
    if engage_posts or args.follow:
        print("\n[2/3] 👍 与领域专家互动（点赞）: {} 篇".format(len(engage_posts)))
        engage_results = engage_experts(engage_posts, dry_run=args.dry_run)
        icon_map = {"liked": "✅", "planned": "📋", "error": "❌"}
        for r in engage_results:
            print("  {} @{} 《{}》: {}".format(
                icon_map.get(r["status"], "?"), r.get("author", ""), r.get("title", "")[:30], r["reason"]))
    else:
        print("\n[2/3] 👍 未找到可互动的帖子，跳过")

    # Step 3: WeChat groups
    print("\n[3/3] 💬 搜索微信群二维码")
    wechat_groups = find_wechat_groups(args.topic_zh, dry_run=args.dry_run)
    for g in wechat_groups:
        status_icon = "✅" if g["status"] == "ready" else "🔍"
        print("  {} 群名: {}".format(status_icon, g["group_name"]))
        print("     链接: {}".format(g["weixin_link"] or "（未找到）"))
        print("     申请语: {}...".format(g["draft_message"][:60]))
        print("     来源: {}".format(g["source_url"]))

    # JSON summary for chat_server.py to parse
    summary = {
        "topic_zh": args.topic_zh,
        "dry_run": args.dry_run,
        "backend": "mcp" if mcp_st == "ok" else ("xhs-cli" if shutil.which("xhs") else "demo"),
        "xiaohongshu_posts": xhs_posts,
        "follow_results": engage_results,   # renamed but key kept for chat_server.py compat
        "wechat_groups": wechat_groups,
    }
    print("\n" + "=" * 55)
    print("📋 JSON Summary:")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
