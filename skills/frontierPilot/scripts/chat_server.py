#!/usr/bin/env python3
"""
FrontierPilot Chat Server v2 — 即时 SSE 响应

架构：
- POST /command  → 立即在后台线程开始处理，返回 {id}
- GET  /stream?id=N → SSE 流，实时推送处理进度和回复文本
- ThreadingMixIn  → 并发处理 SSE 连接和 POST 请求

SSE 事件类型：
  {"type": "step",  "text": "🔍 搜索中..."}  — 进度步骤
  {"type": "token", "text": "..."}            — 回复文字块（流式）
  {"type": "done",  "action": "html_updated|none"} — 完成信号

内置 action（无需外部 API key）：
  update_latest  — 调 arXiv API → 更新 JSON → 重新生成 HTML
  add_paper      — 搜索 Semantic Scholar → 加入 JSON → 重新生成 HTML
  analyze_paper  — 获取摘要 → LLM 深度分析
  answer         — 通用问答（LLM 加持）

LLM 调用优先级（自动选择，无需手动配置）：
  1. OpenClaw Gateway  — OPENCLAW_GATEWAY_TOKEN（容器内已有，推荐）
  2. OpenRouter 直连   — OPENROUTER_API_KEY
  3. Anthropic 直连    — ANTHROPIC_API_KEY（兜底）

用法：
  python3 chat_server.py --data /tmp/fp_data_Diffusion_Models.json [--port 7779]
"""

import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
import traceback
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from socketserver import ThreadingMixIn
from typing import Optional

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

PORT = 7779
DATA_PATH = None               # type: Optional[Path]  # set via --data
HTML_PATH = None               # type: Optional[Path]  # set via --html (the file the browser has open)
PENDING_ACTIONS_PATH = None    # type: Optional[Path]  # set when DATA_PATH is set
SCRIPTS_DIR = Path(__file__).parent
GENERATE_REPORT = SCRIPTS_DIR / "generate_report.py"
QUEUE_FILE = Path("/tmp/fp_chat_queue.json")

# ─────────────────────────────────────────────────────────────────────────────
# State
# ─────────────────────────────────────────────────────────────────────────────

_id_counter = 0
_id_lock = threading.Lock()
_stream_queues: dict[str, queue.Queue] = {}   # cmd_id → Queue of SSE strings
_sq_lock = threading.Lock()


def _new_id() -> str:
    global _id_counter
    with _id_lock:
        _id_counter += 1
        return str(_id_counter)


def _push(cmd_id: str, event_type: str, text: str = "", action: str = ""):
    """Push an SSE event string into the stream queue for cmd_id."""
    payload: dict = {"type": event_type}
    if text:
        payload["text"] = text
    if action:
        payload["action"] = action
    line = "data: " + json.dumps(payload, ensure_ascii=False) + "\n\n"
    with _sq_lock:
        if cmd_id in _stream_queues:
            _stream_queues[cmd_id].put(line)


def _push_done(cmd_id: str, action: str = "none"):
    _push(cmd_id, "done", action=action)
    with _sq_lock:
        if cmd_id in _stream_queues:
            _stream_queues[cmd_id].put(None)  # sentinel — close SSE


# ─────────────────────────────────────────────────────────────────────────────
# Unified LLM helper — Gateway → OpenRouter → Anthropic → ""
# ─────────────────────────────────────────────────────────────────────────────

def call_llm(prompt: str, system: str = "", max_tokens: int = 600) -> str:
    """
    Call LLM via priority chain (no external key required by default):
      1. OpenClaw Gateway /v1/chat/completions  (OPENCLAW_GATEWAY_TOKEN — already in env)
      2. OpenRouter直连                          (OPENROUTER_API_KEY)
      3. Anthropic直连                           (ANTHROPIC_API_KEY — legacy fallback)
      4. "" — caller uses template fallback

    chat_server.py 在本地运行，Gateway 也在本地（端口 18789 转发到宿主机）。
    OPENCLAW_GATEWAY_TOKEN 由 docker-compose 注入，无需用户额外配置。
    """
    messages: list = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    # ── 1. OpenClaw Gateway (OpenAI-compatible, 需先在 openclaw.json 开启 chatCompletions)
    gateway_token = os.environ.get("OPENCLAW_GATEWAY_TOKEN", "")
    gateway_port  = os.environ.get("OPENCLAW_GATEWAY_PORT", "18789")
    if gateway_token:
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{gateway_port}/v1/chat/completions",
                data=json.dumps({
                    "model": "openclaw:main",
                    "messages": messages,
                    "stream": False,
                    "max_tokens": max_tokens,
                }, ensure_ascii=False).encode(),
                headers={
                    "Authorization": f"Bearer {gateway_token}",
                    "Content-Type": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())["choices"][0]["message"]["content"]
        except Exception:
            pass  # fall through to next option

    # ── 2. OpenRouter 直连
    openrouter_key = os.environ.get("OPENROUTER_API_KEY", "")
    if openrouter_key:
        try:
            req = urllib.request.Request(
                "https://openrouter.ai/api/v1/chat/completions",
                data=json.dumps({
                    "model": "anthropic/claude-haiku-4-5",
                    "messages": messages,
                    "max_tokens": max_tokens,
                }, ensure_ascii=False).encode(),
                headers={
                    "Authorization": f"Bearer {openrouter_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://frontierPilot.ai",
                    "X-Title": "FrontierPilot",
                },
            )
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())["choices"][0]["message"]["content"]
        except Exception:
            pass

    # ── 3. Anthropic 直连（兜底）
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if anthropic_key:
        try:
            # Anthropic API: system 是顶层字段，不在 messages 里
            anth_messages = [m for m in messages if m["role"] != "system"]
            body: dict = {
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": max_tokens,
                "messages": anth_messages,
            }
            if system:
                body["system"] = system
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                data=json.dumps(body, ensure_ascii=False).encode(),
                headers={
                    "x-api-key": anthropic_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())["content"][0]["text"]
        except Exception:
            pass

    return ""  # 所有方式均失败，由调用方使用模板兜底


def _llm_available() -> bool:
    """快速检查是否有任意 LLM 渠道可用。"""
    return bool(
        os.environ.get("OPENCLAW_GATEWAY_TOKEN")
        or os.environ.get("OPENROUTER_API_KEY")
        or os.environ.get("ANTHROPIC_API_KEY")
    )


# ─────────────────────────────────────────────────────────────────────────────
# OpenClaw Function Tools — used with /v1/responses endpoint
# ─────────────────────────────────────────────────────────────────────────────

FRONTIER_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "update_latest_papers",
            "description": (
                "搜索并更新领域最新论文动态（arXiv 近30天）。"
                "当用户询问最新进展、新论文、有什么更新时调用。"
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_paper",
            "description": (
                "添加一篇论文到知识库。用户提到论文标题、arXiv ID 或链接，"
                "想把它加入/收录/纳入知识库时调用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "论文标题、arXiv ID（如 2301.12345）或 arXiv 链接",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_paper",
            "description": (
                "深入分析一篇 arXiv 论文，对比其与知识库已有研究的关系。"
                "用户要求分析、解读某篇论文时调用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "arxiv_id": {
                        "type": "string",
                        "description": "arXiv ID，如 2301.12345，或完整链接",
                    }
                },
                "required": ["arxiv_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reach_out_email",
            "description": (
                "给论文作者起草一封学术交流邮件。"
                "用户想联系/写信给某位研究者时调用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "author_name": {
                        "type": "string",
                        "description": "作者姓名",
                    },
                    "paper_topic": {
                        "type": "string",
                        "description": "想交流的论文名称或具体问题",
                    },
                },
                "required": ["author_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "social_explore",
            "description": (
                "在小红书搜索领域专家并关注、发现微信群二维码并生成入群申请。"
                "用户说帮我在小红书找专家、帮我进圈子、找微信群、关注领域博主等时调用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "platform": {
                        "type": "string",
                        "description": "目标平台，如 xiaohongshu 或 wechat，默认 xiaohongshu",
                    },
                },
                "required": [],
            },
        },
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# Knowledge base system prompt builder
# ─────────────────────────────────────────────────────────────────────────────

def _build_system_prompt(data: dict, topic: str) -> str:
    """Build a structured knowledge-base-aware system prompt (~2000 tokens)."""
    lines = [
        f"你是 FrontierPilot 智能助手，{topic} 领域的研究专家。",
        "用中文回答，简洁、专业、有洞察力。回答可引用知识库中的具体论文、年份、评分。",
        "",
    ]

    overview = data.get("field_overview", "")
    if overview:
        lines += ["## 领域全景", overview[:600], ""]

    foundation = data.get("foundation", [])
    if foundation:
        lines.append(f"## 奠基论文（{len(foundation)} 篇）")
        for p in foundation[:8]:
            title = p.get("title", "")
            year = p.get("year", "")
            cites = p.get("citation_count", p.get("citationCount", ""))
            venue = p.get("venue", "")
            info = f"- {title} ({year})"
            if cites:
                info += f" [{cites} citations]"
            if venue:
                info += f" · {venue}"
            lines.append(info)
        lines.append("")

    frontier = data.get("frontier", [])
    if frontier:
        lines.append(f"## 前沿论文（{len(frontier)} 篇）")
        for p in frontier[:8]:
            title = p.get("title", "")
            year = p.get("year", "")
            venue = p.get("venue", "")
            avg_rating = p.get("avg_rating")
            info = f"- {title} ({year})"
            if venue:
                info += f" · {venue}"
            if avg_rating:
                info += f" · 评分 {avg_rating}"
            reviews = p.get("reviews", [])
            if reviews:
                strengths = (reviews[0].get("strengths") or "")[:80]
                weaknesses = (reviews[0].get("weaknesses") or "")[:80]
                if strengths:
                    info += f"\n  优点: {strengths}"
                if weaknesses:
                    info += f"\n  不足: {weaknesses}"
            lines.append(info)
        lines.append("")

    top_authors = data.get("top_authors", [])
    if top_authors:
        lines.append("## 领域强组")
        for a in top_authors[:5]:
            name = a.get("name", "")
            inst = a.get("institution", "")
            recent = a.get("recent_work", "")
            info = f"- {name}"
            if inst:
                info += f" ({inst})"
            if recent:
                info += f" — 代表作: {recent[:50]}"
            lines.append(info)
        lines.append("")

    clusters = data.get("paper_clusters", [])
    if clusters:
        lines.append("## 方法流派")
        for cluster in clusters[:4]:
            name = cluster.get("name", cluster.get("label", ""))
            papers_in = cluster.get("papers", [])
            if name and papers_in:
                names = ", ".join(p.get("title", "")[:20] for p in papers_in[:3])
                lines.append(f"- {name}: {names}")
        lines.append("")

    latest = data.get("latest_updates", [])
    if latest:
        lines.append(f"## 最新动态（{len(latest)} 篇）")
        for p in latest[:5]:
            date = p.get("date", "")
            title = p.get("title", "")
            lines.append(f"- [{date}] {title[:60]}")
        lines.append("")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Gateway /v1/responses streaming call (function calling)
# ─────────────────────────────────────────────────────────────────────────────

def _call_responses_streaming(cmd_id: str, message: str, instructions: str, topic: str) -> Optional[dict]:
    """
    POST to Gateway /v1/responses with FRONTIER_TOOLS and stream=true.
    - Text tokens are piped to browser via _push(cmd_id, "token", delta).
    - Returns tool_call dict {name, arguments} if LLM chose to call a tool.
    - Returns None if it was a pure text response.
    - Raises Exception if Gateway is unreachable (caller handles fallback).
    """
    gateway_token = os.environ.get("OPENCLAW_GATEWAY_TOKEN", "")
    gateway_port = os.environ.get("OPENCLAW_GATEWAY_PORT", "18789")
    session_id = "fp-" + topic.lower().replace(" ", "-")[:20]

    payload = {
        "model": "openclaw:main",
        "input": [{"type": "message", "role": "user", "content": message}],
        "instructions": instructions,
        "tools": FRONTIER_TOOLS,
        "tool_choice": "auto",
        "stream": True,
        "max_output_tokens": 1200,
        "user": session_id,
    }

    req = urllib.request.Request(
        f"http://127.0.0.1:{gateway_port}/v1/responses",
        data=json.dumps(payload, ensure_ascii=False).encode(),
        headers={
            "Authorization": f"Bearer {gateway_token}",
            "Content-Type": "application/json",
        },
    )

    tool_call = None

    with urllib.request.urlopen(req, timeout=25) as resp:
        for raw_line in resp:
            line = raw_line.decode("utf-8").rstrip("\n").rstrip("\r")
            if not line or line.startswith(":"):
                continue
            if not line.startswith("data: "):
                continue
            data_str = line[6:]
            if data_str == "[DONE]":
                break
            try:
                event = json.loads(data_str)
            except json.JSONDecodeError:
                continue

            etype = event.get("type", "")

            if etype == "response.output_text.delta":
                delta = event.get("delta", "")
                if delta:
                    _push(cmd_id, "token", delta)

            elif etype == "response.output_item.added":
                item = event.get("item", {})
                if item.get("type") == "function_call":
                    tool_call = {
                        "name": item.get("name", ""),
                        "arguments": item.get("arguments", "{}"),
                    }

    return tool_call


# ─────────────────────────────────────────────────────────────────────────────
# Pending Actions helpers (P1)
# ─────────────────────────────────────────────────────────────────────────────

def _load_pending_actions() -> list:
    if PENDING_ACTIONS_PATH and PENDING_ACTIONS_PATH.exists():
        try:
            return json.loads(PENDING_ACTIONS_PATH.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save_pending_actions(actions: list) -> None:
    if PENDING_ACTIONS_PATH:
        PENDING_ACTIONS_PATH.write_text(json.dumps(actions, ensure_ascii=False, indent=2), encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# Intent detection (rule-based, no LLM needed)
# ─────────────────────────────────────────────────────────────────────────────

def detect_intent(message: str) -> str:
    if message.startswith("expand_paper "):
        return "expand_paper"
    msg = message.lower()
    if any(w in msg for w in ["更新", "update", "最新动态", "最新进展", "new paper", "recent"]):
        return "update_latest"
    if any(w in msg for w in ["添加", "add", "加入", "加到", "把", "纳入", "收录"]):
        return "add_paper"
    if any(w in msg for w in ["分析", "analyze", "解读", "arxiv.org", "abs/"]):
        return "analyze_paper"
    if any(w in msg for w in ["邮件", "email", "mail", "联系", "reach out", "写信"]):
        return "reach_out_email"
    if any(w in msg for w in ["小红书", "微信群", "社交", "专家", "关注", "进圈", "xiaohongshu", "社群", "follow"]):
        return "social_explore"
    return "answer"


# ─────────────────────────────────────────────────────────────────────────────
# arXiv search helper
# ─────────────────────────────────────────────────────────────────────────────

import re as _re  # for venue detection in arxiv comments

# CS/ML arXiv categories for filtering
_ARXIV_CS_CATS = "cat:cs.LG+OR+cat:cs.AI+OR+cat:cs.CV+OR+cat:cs.CL+OR+cat:cs.NE+OR+cat:stat.ML"

# Top venues to detect from arxiv:comment field
_VENUE_KEYWORDS = ["ICLR", "NeurIPS", "ICML", "CVPR", "ECCV", "ICCV", "ACL", "EMNLP", "NAACL"]


def _build_arxiv_query(topic: str, days_back: int = 0) -> str:
    """Build arXiv search_query with CS/ML category filter and optional date range."""
    topic_encoded = topic.replace(" ", "+").replace(":", "")
    query = f"(ti:{topic_encoded}+OR+abs:{topic_encoded})+AND+({_ARXIV_CS_CATS})"
    if days_back > 0:
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days_back)
        date_range = f"[{start_date.strftime('%Y%m%d')}0000+TO+{end_date.strftime('%Y%m%d')}2359]"
        query += f"+AND+submittedDate:{date_range}"
    return query


def _detect_venue_from_comment(comment: str) -> Optional[str]:
    """Detect accepted venue from arxiv:comment field (e.g. 'Accepted at ICLR 2024')."""
    if not comment:
        return None
    for venue in _VENUE_KEYWORDS:
        if venue in comment:
            year_match = _re.search(r"20\d{2}", comment)
            if year_match:
                return f"{venue} {year_match.group()}"
            return venue
    return None


def search_arxiv_recent(topic: str, days: int = 30, max_results: int = 30) -> list[dict]:
    """Call arXiv public API, return CS/ML papers published in the last `days` days."""
    query = _build_arxiv_query(topic, days_back=days)
    url = (
        f"http://export.arxiv.org/api/query"
        f"?search_query={query}&start=0&max_results={max_results}"
        f"&sortBy=lastUpdatedDate&sortOrder=descending"
    )
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:
            xml_data = resp.read().decode("utf-8")
    except Exception as e:
        raise RuntimeError(f"arXiv API error: {e}")

    root = ET.fromstring(xml_data)
    ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
    cutoff = datetime.utcnow() - timedelta(days=days)
    papers = []

    for entry in root.findall("atom:entry", ns):
        pub_el = entry.find("atom:published", ns)
        if pub_el is None:
            continue
        pub_dt = datetime.fromisoformat(pub_el.text.replace("Z", "+00:00")).replace(tzinfo=None)
        if pub_dt < cutoff:
            continue

        title_el = entry.find("atom:title", ns)
        summary_el = entry.find("atom:summary", ns)
        id_el = entry.find("atom:id", ns)

        title = (title_el.text or "").strip().replace("\n", " ")
        abstract = (summary_el.text or "").strip()[:300]
        link = (id_el.text or "").strip()
        # prefer abs page URL
        for lnk in entry.findall("atom:link", ns):
            if lnk.get("type") == "text/html":
                link = lnk.get("href", link)
                break

        # Extract arxiv:comment for venue detection (A2)
        comment = (entry.findtext("arxiv:comment", "", ns) or "").strip()
        accepted_venue = _detect_venue_from_comment(comment)

        # Extract arxiv ID and primary category
        raw_id = (id_el.text or "").strip()
        arxiv_id = raw_id.split("/abs/")[-1].split("v")[0] if "/abs/" in raw_id else ""
        primary_cat_el = entry.find("arxiv:primary_category", ns)
        primary_category = primary_cat_el.get("term", "") if primary_cat_el is not None else ""

        papers.append({
            "date": pub_dt.strftime("%Y-%m-%d"),
            "title": title,
            "url": link,
            "summary": abstract,
            "source": "arXiv",
            "accepted_venue": accepted_venue,
            "arxiv_id": arxiv_id,
            "primary_category": primary_category,
        })

    return papers


# ─────────────────────────────────────────────────────────────────────────────
# Action handlers
# ─────────────────────────────────────────────────────────────────────────────

def _load_data() -> dict:
    if DATA_PATH and DATA_PATH.exists():
        try:
            return json.loads(DATA_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # File may be partially written by a concurrent save; retry once
            import time as _time
            _time.sleep(0.3)
            try:
                return json.loads(DATA_PATH.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return {}
    return {}


def _save_data(data: dict):
    """Atomic write: write to a temp file then rename to avoid partial reads."""
    if not DATA_PATH:
        return
    tmp = DATA_PATH.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(DATA_PATH)
    except Exception:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise


def _regenerate_html(cmd_id: str) -> bool:
    if not DATA_PATH:
        return False
    topic = json.loads(DATA_PATH.read_text(encoding="utf-8")).get("topic", "Topic")
    # Use the exact HTML file the browser has open (passed via --html), or derive from data path
    if HTML_PATH:
        out_path = HTML_PATH
    else:
        out_path = DATA_PATH.parent / f"FrontierPilot_{topic.replace(' ', '_')}.html"
    _push(cmd_id, "step", f"🔄 重新生成知识库 HTML…")
    result = subprocess.run(
        [sys.executable, str(GENERATE_REPORT), "--data", str(DATA_PATH), "--output", str(out_path)],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        _push(cmd_id, "step", f"✅ HTML 已写入：{out_path}")
        return True
    else:
        _push(cmd_id, "step", f"❌ HTML 生成失败：{result.stderr[:200]}")
        return False


def fetch_ss_recommendations(paper_ids: list[str], limit: int = 8) -> list[dict]:
    """Fetch recommended papers from Semantic Scholar Recommendations API."""
    ss_ids: list[str] = []
    for pid in paper_ids:
        pid = pid.strip()
        if pid.startswith("arXiv:"):
            # Resolve arXiv ID to Semantic Scholar paper ID
            arxiv_num = pid[len("arXiv:"):]
            try:
                req = urllib.request.Request(
                    f"https://api.semanticscholar.org/graph/v1/paper/arXiv:{urllib.parse.quote(arxiv_num)}?fields=paperId",
                    headers={"User-Agent": "FrontierPilot/1.0"},
                )
                with urllib.request.urlopen(req, timeout=10) as r:
                    data = json.loads(r.read())
                if data.get("paperId"):
                    ss_ids.append(data["paperId"])
            except Exception as e:
                print(f"[fetch_ss_recommendations] Failed to resolve arXiv:{arxiv_num} → SS paperId: {e}", file=sys.stderr)
        else:
            ss_ids.append(pid)

    if not ss_ids:
        print(f"[fetch_ss_recommendations] No valid SS paper IDs resolved from input: {paper_ids}", file=sys.stderr)
        return []

    # POST to recommendations endpoint
    body = json.dumps({
        "positivePaperIds": ss_ids[:5],
        "negativePaperIds": [],
    }).encode()
    fields = "title,authors,year,citationCount,venue,externalIds,abstract"
    url = f"https://api.semanticscholar.org/recommendations/v1/papers/?fields={fields}&limit={limit}"
    try:
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "User-Agent": "FrontierPilot/1.0",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            resp_data = json.loads(r.read())
    except Exception as e:
        print(f"[fetch_ss_recommendations] Recommendations API failed for IDs {ss_ids[:5]}: {e}", file=sys.stderr)
        return []

    raw_papers = resp_data.get("recommendedPapers", [])
    # Sort by citation count descending
    raw_papers.sort(key=lambda p: (p.get("citationCount") or 0), reverse=True)

    results: list[dict] = []
    for p in raw_papers:
        title = p.get("title") or "Untitled"
        year = p.get("year") or 0
        slug = re.sub(r"[^a-zA-Z0-9]", "_", title.split(":")[0])[:15]
        node_id = f"R{year}_{slug}"
        authors_raw = p.get("authors") or []
        authors = [a.get("name", "") for a in authors_raw[:3]]
        ext_ids = p.get("externalIds") or {}
        arxiv_id = ext_ids.get("ArXiv", "")
        ss_paper_id = p.get("paperId", "")
        abstract = (p.get("abstract") or "")[:200]
        url_paper = f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else f"https://www.semanticscholar.org/paper/{ss_paper_id}"
        results.append({
            "node_id": node_id,
            "title": title,
            "authors": authors,
            "year": year,
            "citation_count": p.get("citationCount") or 0,
            "venue": p.get("venue") or "",
            "arxiv_id": arxiv_id,
            "ss_paper_id": ss_paper_id,
            "abstract_snippet": abstract,
            "url": url_paper,
            "type": "recommended",
        })

    return results


def _push_graph_update(cmd_id: str, new_papers: list) -> None:
    payload = {"type": "graph_update", "new_papers": new_papers}
    line = "data: " + json.dumps(payload, ensure_ascii=False) + "\n\n"
    with _sq_lock:
        if cmd_id in _stream_queues:
            _stream_queues[cmd_id].put(line)


def _resolve_paper_id_by_title(title: str) -> str:
    """Search Semantic Scholar by title and return the first matching paperId."""
    try:
        params = urllib.parse.urlencode({"query": title, "fields": "paperId,title", "limit": "1"})
        req = urllib.request.Request(
            f"https://api.semanticscholar.org/graph/v1/paper/search?{params}",
            headers={"User-Agent": "FrontierPilot/1.0"},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        papers = data.get("data", [])
        if papers:
            return papers[0].get("paperId", "")
    except Exception as e:
        print(f"[_resolve_paper_id_by_title] Failed for title={title!r}: {e}", file=sys.stderr)
    return ""


def handle_expand_paper(cmd_id: str, message: str) -> None:
    parts = message.split(" ", 2)
    paper_id = parts[1] if len(parts) > 1 else ""
    paper_title = parts[2] if len(parts) > 2 else ""

    _push(cmd_id, "step", f"🔍 正在为「{paper_title[:30]}」发现相似论文...")

    # If no paper_id provided, try to resolve one via title search
    if not paper_id and paper_title:
        _push(cmd_id, "step", "📡 正在通过标题查找论文 ID...")
        paper_id = _resolve_paper_id_by_title(paper_title)

    try:
        new_papers = fetch_ss_recommendations([paper_id], limit=8) if paper_id else []
    except Exception as e:
        print(f"[handle_expand_paper] Exception for paper_id={paper_id}: {e}", file=sys.stderr)
        new_papers = []

    if not new_papers:
        _push(cmd_id, "token", f"未找到相似论文（paper_id: {paper_id}）。\n可能原因：网络无法连接 Semantic Scholar API，或该论文 ID 无效。请检查网络后重试。")
        _push_done(cmd_id)
        return

    _push(cmd_id, "step", f"✅ 发现 {len(new_papers)} 篇相似论文")
    _push_graph_update(cmd_id, new_papers)
    _push_done(cmd_id, "none")


def _check_xhs_backend() -> tuple:
    """Quick check of xiaohongshu backend: returns (status, label).

    Mirrors social_agent.check_xhs_mcp() but inline to avoid import overhead.
    status: 'mcp' | 'xhs-cli' | 'demo'
    """
    import shutil as _shutil
    mcporter = _shutil.which("mcporter")
    if mcporter:
        try:
            r = subprocess.run(
                [mcporter, "config", "get", "xiaohongshu", "--json"],
                capture_output=True, text=True, timeout=5,
            )
            if r.returncode == 0 and "xiaohongshu" in r.stdout.lower():
                r2 = subprocess.run(
                    [mcporter, "list", "xiaohongshu", "--json"],
                    capture_output=True, text=True, timeout=10,
                )
                raw = r2.stdout.strip().lstrip("\ufeff")
                try:
                    parsed = json.loads(raw)
                    if str(parsed.get("status", "")).lower() == "ok":
                        return "mcp", "xiaohongshu-mcp（真实数据）"
                except Exception:
                    pass
                return "warn", "xiaohongshu-mcp 已配置但服务未响应"
        except Exception:
            pass
    if _shutil.which("xhs"):
        return "xhs-cli", "xhs CLI"
    return "demo", "demo 模式"


def handle_social_explore(cmd_id: str, topic: str) -> None:
    """Search Xiaohongshu for domain experts, follow them, and discover WeChat groups."""
    data = _load_data()
    topic_zh = data.get("topic_zh") or topic

    # Health check — show which backend will be used
    backend_status, backend_label = _check_xhs_backend()
    if backend_status == "warn":
        _push(cmd_id, "step",
              "⚠️ xiaohongshu-mcp 已配置但容器未运行，将降级到 demo 模式。\n"
              "如需真实数据：docker start xiaohongshu-mcp")
    elif backend_status == "demo":
        _push(cmd_id, "step",
              "ℹ️ 未检测到小红书后台，以 demo 模式运行。\n"
              "真实数据需要：docker run -d -p 18060:18060 -v xhs-data:/app/data "
              "xpzouying/xiaohongshu-mcp  →  mcporter config add xiaohongshu "
              "http://localhost:18060/mcp  →  手机扫码登录")
    _push(cmd_id, "step", "🌐 后台：{} — 正在搜索「{}」领域专家…".format(backend_label, topic_zh))

    social_agent_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "social_agent.py"
    )
    cmd = [sys.executable, social_agent_path, "--topic-zh", topic_zh, "--follow", "--num", "8"]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120
        )
        stdout = result.stdout
    except subprocess.TimeoutExpired:
        _push(cmd_id, "token", "⚠️ 社交代理超时（120s），请稍后重试。")
        _push_done(cmd_id, "none")
        return
    except Exception as e:
        _push(cmd_id, "token", "⚠️ 社交代理启动失败：{}".format(e))
        _push_done(cmd_id, "none")
        return

    # social_agent.py prints a JSON block after "📋 JSON Summary:" marker — extract it
    summary = {}
    try:
        marker = "JSON Summary:"
        marker_pos = stdout.find(marker)
        if marker_pos != -1:
            json_str = stdout[marker_pos + len(marker):].strip()
        else:
            json_str = stdout.strip()
        # Find the first top-level { ... } block
        brace_start = json_str.find("{")
        if brace_start != -1:
            depth = 0
            for i, ch in enumerate(json_str[brace_start:], brace_start):
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        summary = json.loads(json_str[brace_start:i + 1])
                        break
    except (ValueError, Exception):
        pass

    if not summary:
        _push(cmd_id, "token", "⚠️ 社交代理未返回有效数据。\n```\n{}\n```".format(
            (result.stderr or stdout)[:400]
        ))
        _push_done(cmd_id, "none")
        return

    # Convert summary → social_actions entries
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    new_actions = []

    xhs_posts = summary.get("xiaohongshu_posts", [])
    if xhs_posts:
        new_actions.append({
            "platform": "xiaohongshu",
            "action": "search",
            "status": "done",
            "timestamp": now_str,
            "query": topic_zh,
            "result_count": len(xhs_posts),
        })

    for r in summary.get("follow_results", []):
        # follow_results now holds engage_results (like_feed actions)
        action_type = "like" if r.get("status") == "liked" else "follow"
        new_actions.append({
            "platform": "xiaohongshu",
            "action": action_type,
            "status": r.get("status", "planned"),
            "timestamp": now_str,
            "target_name": r.get("author") or r.get("author_id", ""),
            "target_url": "https://www.xiaohongshu.com/explore/{}".format(r.get("feed_id", "")) if r.get("feed_id") else "",
            "reason": r.get("reason", ""),
        })

    for g in summary.get("wechat_groups", []):
        new_actions.append({
            "platform": "wechat",
            "action": "qr_found",
            "status": g.get("status", "ready"),
            "timestamp": now_str,
            "group_name": g.get("group_name", ""),
            "weixin_link": g.get("weixin_link", ""),
            "qr_url": g.get("qr_url", ""),
            "draft_message": g.get("draft_message", ""),
            "source_url": g.get("source_url", ""),
        })

    data.setdefault("social_actions", [])
    data["social_actions"] = new_actions + data["social_actions"]
    data["last_updated_at"] = now_str
    _save_data(data)

    _push(cmd_id, "step", "✏️ 社交行动记录已写入知识库（{} 条）".format(len(new_actions)))
    ok = _regenerate_html(cmd_id)

    # Human-readable reply
    backend_used = summary.get("backend", "demo")
    backend_note = {"mcp": "（真实数据）", "xhs-cli": "（xhs CLI）", "demo": "（demo 模式）"}.get(backend_used, "")
    lines = ["✅ 社交探索完成！{}\n".format(backend_note)]
    if xhs_posts:
        lines.append("**小红书** 找到 {} 篇相关帖子".format(len(xhs_posts)))
        for p in xhs_posts[:3]:
            lines.append("• {} — {}".format(p.get("author", ""), p.get("title", "")[:40]))
    liked = [r for r in summary.get("follow_results", []) if r.get("status") == "liked"]
    planned = [r for r in summary.get("follow_results", []) if r.get("status") == "planned"]
    if liked:
        lines.append("\n👍 已为 {} 篇领域帖子点赞".format(len(liked)))
    if planned:
        lines.append("\n📋 {} 篇帖子已加入待互动列表".format(len(planned)))
    for g in summary.get("wechat_groups", []):
        if g.get("status") in ("ready", "demo"):
            lines.append("\n💬 发现微信群「{}」，入群申请语已就绪".format(g.get("group_name", "")))
    if backend_used == "demo":
        lines.append("\n\n💡 启用真实小红书数据：运行 `social_agent.py --doctor` 查看配置步骤。")
    lines.append("\n点击**刷新页面**后在「🌐 社交行动」Tab 查看完整记录。")
    _push(cmd_id, "token", "\n".join(lines))
    _push_done(cmd_id, "html_updated" if ok else "none")


def handle_update_latest(cmd_id: str, topic: str):
    _push(cmd_id, "step", f"🔍 正在搜索 arXiv 最近 30 天 · {topic}…")
    try:
        papers = search_arxiv_recent(topic, days=30, max_results=8)
    except Exception as e:
        _push(cmd_id, "token", f"⚠️ arXiv 搜索失败：{e}\n请检查网络连接后重试。")
        _push_done(cmd_id, "none")
        return

    if not papers:
        _push(cmd_id, "step", "📭 最近 30 天暂无新论文")
        _push(cmd_id, "token", "最近 30 天内未在 arXiv 找到相关新论文，知识库保持不变。")
        _push_done(cmd_id, "none")
        return

    _push(cmd_id, "step", f"📄 发现 {len(papers)} 篇相关论文，正在更新知识库…")

    data = _load_data()
    existing_titles = {u.get("title", "") for u in data.get("latest_updates", [])}
    new_papers = [p for p in papers if p["title"] not in existing_titles]

    data.setdefault("latest_updates", [])
    data["latest_updates"] = new_papers + data["latest_updates"]
    data["last_updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    _save_data(data)

    _push(cmd_id, "step", f"✏️  知识库 JSON 已更新（新增 {len(new_papers)} 篇）")

    ok = _regenerate_html(cmd_id)

    # Build human-readable reply
    lines = [f"✅ 已更新！最近 30 天发现 **{len(new_papers)} 篇**新论文：\n"]
    for p in new_papers[:5]:
        lines.append(f"• [{p['date']}] {p['title'][:60]}\n  {p['summary'][:80]}…")
    if len(new_papers) > 5:
        lines.append(f"… 及另外 {len(new_papers)-5} 篇")
    lines.append("\n点击**刷新页面**后在「📰 最新动态」Tab 查看完整内容。")
    _push(cmd_id, "token", "\n".join(lines))
    _push_done(cmd_id, "html_updated" if ok else "none")


def handle_add_paper(cmd_id: str, message: str, topic: str):
    _push(cmd_id, "step", "🔍 正在解析论文信息…")

    # Try to extract arXiv ID or paper title from the message
    arxiv_id = None
    for part in message.split():
        if "arxiv.org/abs/" in part:
            arxiv_id = part.split("/abs/")[-1].strip(".")
            break
        if part.startswith("abs/"):
            arxiv_id = part[4:].strip(".")
            break

    if arxiv_id:
        url = f"http://export.arxiv.org/api/query?id_list={urllib.parse.quote(arxiv_id)}"
        _push(cmd_id, "step", f"📡 获取 arXiv:{arxiv_id} 详细信息…")
    else:
        # Strip Chinese UI phrases and action words; keep the paper title/keywords
        keywords = message
        for w in [
            "到知识库", "到知识图谱", "到前沿快照", "到知识地图",
            "知识库", "知识图谱", "前沿快照",
            "的相关论文", "相关论文", "这篇论文", "该论文", "以下论文", "这篇",
            "添加", "加入", "加到", "纳入", "收录", "把", "将",
            "add", "please", "help",
            "：", ":", "，", ",", "。", "!",
        ]:
            keywords = keywords.replace(w, " ")
        keywords = " ".join(keywords.split())  # collapse whitespace
        keywords = keywords.strip()
        # Use title search (ti:) — far more precise than full-text (all:)
        url = (
            f"http://export.arxiv.org/api/query"
            f"?search_query=ti:{urllib.parse.quote(keywords)}&max_results=3&sortBy=relevance"
        )
        _push(cmd_id, "step", f"🔍 在 arXiv 标题搜索：「{keywords[:40]}」…")

    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            xml_data = resp.read().decode("utf-8")
    except Exception as e:
        _push(cmd_id, "token", f"⚠️ 搜索失败：{e}")
        _push_done(cmd_id, "none")
        return

    root = ET.fromstring(xml_data)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    entries = root.findall("atom:entry", ns)
    if not entries:
        _push(cmd_id, "token", "❌ 未找到匹配论文，请提供更准确的标题或 arXiv 链接。")
        _push_done(cmd_id, "none")
        return

    entry = entries[0]
    title_el = entry.find("atom:title", ns)
    summary_el = entry.find("atom:summary", ns)
    pub_el = entry.find("atom:published", ns)
    id_el = entry.find("atom:id", ns)
    authors_els = entry.findall("atom:author/atom:name", ns)

    title = (title_el.text or "").strip().replace("\n", " ")
    abstract = (summary_el.text or "").strip()
    pub_year = int((pub_el.text or "2024")[:4])
    paper_url = (id_el.text or "").strip()
    authors = [a.text for a in authors_els[:3]]

    _push(cmd_id, "step", f"📄 找到：《{title[:50]}》（{pub_year}）…")

    data = _load_data()
    existing_titles = {p.get("title", "") for p in data.get("foundation", []) + data.get("frontier", [])}
    if title in existing_titles:
        _push(cmd_id, "token", f"ℹ️ 《{title}》已在知识库中，无需重复添加。")
        _push_done(cmd_id, "none")
        return

    new_paper = {
        "title": title,
        "forum_id": arxiv_id or title[:20].replace(" ", "_"),
        "venue": "arXiv",
        "year": pub_year,
        "url": paper_url,
        "avg_rating": None,
        "reviews": [{"rating": "N/A", "strengths": abstract[:150], "weaknesses": "", "related_work": []}],
    }

    _push(cmd_id, "step", "✏️  将论文追加到「前沿快照」并更新知识库…")
    data.setdefault("frontier", []).append(new_paper)
    _save_data(data)

    ok = _regenerate_html(cmd_id)
    _push(cmd_id, "token",
          f"✅ 已将《{title}》添加到前沿快照！\n\n"
          f"作者：{', '.join(authors)}\n年份：{pub_year}\n\n"
          f"{'点击**刷新页面**查看更新后的知识图谱。' if ok else ''}")
    _push_done(cmd_id, "html_updated" if ok else "none")


def handle_answer(cmd_id: str, message: str, topic: str):
    """General Q&A via call_llm() — Gateway → OpenRouter → Anthropic → template fallback."""
    data = _load_data()
    n_f  = len(data.get("foundation", []))
    n_fr = len(data.get("frontier", []))

    if _llm_available():
        _push(cmd_id, "step", "🤖 正在生成回复…")
        context = (
            f"主题：{topic}\n"
            f"奠基论文：{n_f} 篇，前沿论文：{n_fr} 篇\n"
            f"部分论文标题：{', '.join(p.get('title','') for p in data.get('foundation',[])[:3])}"
        )
        reply = call_llm(
            prompt=message,
            system=(
                f"你是 FrontierPilot 智能助手，当前知识库主题：{topic}。\n"
                f"知识库状态：{context}\n"
                "用中文、简洁、专业地回答用户关于该研究领域的问题。回答不超过 200 字。"
            ),
            max_tokens=600,
        )
        if reply:
            _push(cmd_id, "token", reply)
        else:
            _push(cmd_id, "token", "⚠️ LLM 暂时不可用，请稍后重试。")
    else:
        _push(cmd_id, "step", "📚 基于知识库数据生成回复…")
        _push(cmd_id, "token",
              f"我是 FrontierPilot 智能助手（{topic} 知识库）。\n\n"
              f"当前知识库包含：{n_f} 篇奠基论文、{n_fr} 篇前沿论文。\n\n"
              "你可以让我：\n"
              "• 更新最新动态（搜索 arXiv）\n"
              "• 添加指定论文\n"
              "• 分析某篇 arXiv 论文")
    _push_done(cmd_id, "none")


def handle_analyze(cmd_id: str, message: str, topic: str):
    """Fetch paper abstract and provide brief analysis."""
    _push(cmd_id, "step", "🔍 解析论文链接或关键词…")

    arxiv_id = None
    for part in message.split():
        if "arxiv.org/abs/" in part:
            arxiv_id = part.split("/abs/")[-1].strip(".").strip()
        elif part.startswith("2") and "." in part and len(part) < 12:
            arxiv_id = part.strip(".")

    if not arxiv_id:
        handle_answer(cmd_id, message, topic)
        return

    url = f"http://export.arxiv.org/api/query?id_list={urllib.parse.quote(arxiv_id)}"
    _push(cmd_id, "step", f"📡 获取 arXiv:{arxiv_id}…")
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            xml_data = resp.read().decode("utf-8")
    except Exception as e:
        _push(cmd_id, "token", f"⚠️ 获取失败：{e}")
        _push_done(cmd_id, "none")
        return

    root = ET.fromstring(xml_data)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    entries = root.findall("atom:entry", ns)
    if not entries:
        _push(cmd_id, "token", "❌ 未找到该论文，请确认 arXiv ID 是否正确。")
        _push_done(cmd_id, "none")
        return

    entry = entries[0]
    title = (entry.find("atom:title", ns).text or "").strip().replace("\n", " ")
    abstract = (entry.find("atom:summary", ns).text or "").strip()
    authors_els = entry.findall("atom:author/atom:name", ns)
    authors = ", ".join(a.text for a in authors_els[:3])

    _push(cmd_id, "step", f"📄 《{title[:50]}》— 生成分析…")

    base_reply = (
        f"**{title}**\n"
        f"作者：{authors}\n\n"
        f"**摘要（原文）：**\n{abstract[:400]}…\n\n"
    )
    _push(cmd_id, "token", base_reply)

    # LLM 深度分析
    if _llm_available():
        _push(cmd_id, "step", "🧠 正在分析与知识库的关联…")
        analysis = call_llm(
            prompt=(
                f"请用中文简要分析这篇论文与「{topic}」方向的关系（100字以内）：\n"
                f"标题：{title}\n摘要：{abstract[:500]}"
            ),
            max_tokens=200,
        )
        if analysis:
            _push(cmd_id, "token", f"**与 {topic} 的关系：**\n{analysis}\n\n")

    _push(cmd_id, "token", "是否要将此论文添加到知识图谱？发送「添加这篇论文」即可。")
    _push_done(cmd_id, "none")


# ─────────────────────────────────────────────────────────────────────────────
# Tool execution router + main conversation handler
# ─────────────────────────────────────────────────────────────────────────────

def _execute_tool(cmd_id: str, tool_name: str, arguments_json: str, topic: str) -> None:
    """Route a function_call from the LLM to the appropriate local action handler."""
    try:
        args = json.loads(arguments_json) if arguments_json else {}
    except json.JSONDecodeError:
        args = {}

    if tool_name == "update_latest_papers":
        handle_update_latest(cmd_id, topic)
    elif tool_name == "add_paper":
        handle_add_paper(cmd_id, args.get("query", ""), topic)
    elif tool_name == "analyze_paper":
        handle_analyze(cmd_id, args.get("arxiv_id", ""), topic)
    elif tool_name == "reach_out_email":
        combined = args.get("author_name", "") + " " + args.get("paper_topic", "")
        handle_reach_out_email(cmd_id, combined.strip(), topic)
    elif tool_name == "social_explore":
        handle_social_explore(cmd_id, topic)
    else:
        _push_done(cmd_id, "none")


def handle_conversation(cmd_id: str, message: str, topic: str) -> None:
    """
    Main conversation path: knowledge-aware, multi-turn, function-calling.
    Primary: Gateway /v1/responses (function calling + streaming).
    Fallback: call_llm() + [ACTION:xxx] text markers.
    """
    data = _load_data()
    instructions = _build_system_prompt(data, topic)

    gateway_token = os.environ.get("OPENCLAW_GATEWAY_TOKEN", "")
    if gateway_token:
        _push(cmd_id, "step", "🤖 正在思考…")
        try:
            tool_call = _call_responses_streaming(cmd_id, message, instructions, topic)
            if tool_call:
                _execute_tool(cmd_id, tool_call["name"], tool_call["arguments"], topic)
            else:
                _push_done(cmd_id, "none")
            return
        except Exception as e:
            print(f"[handle_conversation] Gateway /v1/responses failed: {e}", file=sys.stderr)
            _push(cmd_id, "step", "⚠️ Gateway 连接失败，切换降级模式…")

    # ── Fallback: call_llm() with knowledge base context + [ACTION:xxx] markers ──
    fallback_instructions = instructions + (
        "\n## 可用操作\n"
        "当用户要求执行操作时，在回复末尾单独一行输出标记（不要加其他文字）：\n"
        "- 更新最新论文 → [ACTION:update_latest]\n"
        "- 添加论文 → [ACTION:add_paper:论文标题或arXiv链接]\n"
        "- 分析论文 → [ACTION:analyze_paper:arXiv ID]\n"
        "- 联系作者 → [ACTION:reach_out_email:作者姓名]\n"
        "- 小红书找专家/进微信群/社交探索 → [ACTION:social_explore]\n"
        "仅在用户明确要求执行操作时输出标记。正常问答不输出。"
    )
    _push(cmd_id, "step", "🤖 正在生成回复…")
    reply = call_llm(prompt=message, system=fallback_instructions, max_tokens=800)
    if not reply:
        _push(cmd_id, "token", "⚠️ LLM 暂时不可用，请检查 Gateway 或 API Key 配置。")
        _push_done(cmd_id, "none")
        return

    # Parse [ACTION:xxx] from reply
    action_match = re.search(r'\[ACTION:(\w+)(?::(.+?))?\]', reply)
    clean_reply = re.sub(r'\[ACTION:[^\]]+\]', '', reply).strip()
    if clean_reply:
        _push(cmd_id, "token", clean_reply)

    if action_match:
        action_type = action_match.group(1)
        action_arg = (action_match.group(2) or "").strip()
        _execute_tool(cmd_id, _normalize_action(action_type), action_arg or message, topic)
    else:
        _push_done(cmd_id, "none")


def _normalize_action(action_type: str) -> str:
    """Map [ACTION:xxx] marker names to FRONTIER_TOOLS function names."""
    mapping = {
        "update_latest": "update_latest_papers",
        "add_paper": "add_paper",
        "analyze_paper": "analyze_paper",
        "reach_out_email": "reach_out_email",
        "social_explore": "social_explore",
    }
    return mapping.get(action_type, action_type)


# ─────────────────────────────────────────────────────────────────────────────
# Email outreach handlers (P0)
# ─────────────────────────────────────────────────────────────────────────────

def find_author_email(author_name: str, institution: str = "", homepage_url: str = "") -> str:
    """Try to find author email: scrape homepage → Semantic Scholar → institution pattern."""
    import re

    # Strategy 1: scrape homepage for mailto: links
    if homepage_url and homepage_url.startswith("http"):
        try:
            req = urllib.request.Request(homepage_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=5) as r:
                html = r.read().decode("utf-8", errors="ignore")
            emails = re.findall(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", html)
            if emails:
                return emails[0]
        except Exception:
            pass

    # Strategy 2: Semantic Scholar author search for homepage
    try:
        params = urllib.parse.urlencode({"query": author_name, "fields": "name,affiliations,homepage"})
        req = urllib.request.Request(
            f"https://api.semanticscholar.org/graph/v1/author/search?{params}",
            headers={"User-Agent": "FrontierPilot/1.0"},
        )
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read())
        authors = data.get("data", [])
        if authors and authors[0].get("homepage"):
            return find_author_email(author_name, institution, authors[0]["homepage"])
    except Exception:
        pass

    # Strategy 3: institution domain pattern
    if institution:
        inst_lower = institution.lower()
        parts = author_name.lower().split()
        if len(parts) >= 2:
            first, last = parts[0], parts[-1]
            domain_map = {
                "stanford": "cs.stanford.edu",
                "mit": "mit.edu",
                "berkeley": "berkeley.edu",
                "cmu": "cs.cmu.edu",
                "pku": "pku.edu.cn",
                "peking": "pku.edu.cn",
                "tsinghua": "tsinghua.edu.cn",
                "openai": "openai.com",
                "google": "google.com",
                "microsoft": "microsoft.com",
                "meta": "meta.com",
                "purdue": "purdue.edu",
            }
            for key, domain in domain_map.items():
                if key in inst_lower:
                    return f"{first[0]}{last}@{domain}"
    return ""


def generate_email_draft(author_name: str, recent_work: str, topic: str) -> str:
    """Generate a personalized cold email draft via call_llm(), with template fallback."""
    prompt = (
        f"请用中文帮我写一封给 {author_name} 的学术联系邮件。"
        f"该作者近期工作：{recent_work}。"
        f"我是 {topic} 方向的研究新手，想请教入门建议和研究方向。"
        "要求：有具体提问，不要泛泛而谈，100-150字，包含主题行。"
    )
    draft = call_llm(prompt, max_tokens=400)
    if draft:
        return draft

    # Template fallback
    return (
        f"主题：关于{topic}方向的请教\n\n"
        f"尊敬的{author_name}老师，\n\n"
        f"您好！我是一名{topic}方向的研究新手，拜读了您在{recent_work}方面的工作，受益匪浅。\n\n"
        f"冒昧打扰，想请教关于{topic}领域的入门建议：\n"
        "1. 您认为目前该领域最值得关注的研究方向是什么？\n"
        "2. 对于刚入门的研究者，有什么重要的论文或资源推荐？\n\n"
        "非常感谢您的时间！期待您的回复。\n\n"
        "此致\n敬礼"
    )


def handle_reach_out_email(cmd_id: str, message: str, topic: str) -> None:
    """Handle 'reach_out_email' intent — find author info and generate email draft."""
    _push(cmd_id, "step", "🔍 正在查找作者信息…")

    data = _load_data()
    top_authors = data.get("top_authors", [])

    # Try to match author name from message
    author_name = ""
    for word in message.split():
        for a in top_authors:
            if word in a.get("name", ""):
                author_name = a["name"]
                break
        if author_name:
            break

    if not author_name and top_authors:
        author_name = top_authors[0]["name"]

    if not author_name:
        _push(cmd_id, "token", "未找到作者信息，请在消息中指定作者姓名。")
        _push_done(cmd_id)
        return

    author_info = next((a for a in top_authors if a["name"] == author_name), {})
    institution = author_info.get("institution", "")
    recent_work = author_info.get("recent_work", "")
    homepage_url = author_info.get("url", "")

    _push(cmd_id, "step", f"📧 正在为 {author_name} 生成邮件草稿…")
    email_text = generate_email_draft(author_name, recent_work, topic)

    _push(cmd_id, "step", "🔗 查找联系方式…")
    email_addr = find_author_email(author_name, institution, homepage_url)

    result = f"**收件人：** {author_name}"
    if email_addr:
        result += f"（{email_addr}）"
    result += f"\n\n---\n\n{email_text}"

    for chunk in result.split("\n"):
        _push(cmd_id, "token", chunk + "\n")

    _push_done(cmd_id, "none")


# ─────────────────────────────────────────────────────────────────────────────
# Processing dispatcher (runs in background thread)
# ─────────────────────────────────────────────────────────────────────────────

def process_command(cmd_id: str, message: str, topic: str):
    try:
        # Fast-path: expand_paper uses a special graph_update SSE protocol
        if message.startswith("expand_paper "):
            handle_expand_paper(cmd_id, message)
            return

        # Fast-path: use rule-based intent detection to directly dispatch action commands.
        # This bypasses the LLM entirely for known action intents, which is more reliable
        # because the Gateway model often streams text instead of calling tools.
        intent = detect_intent(message)
        if intent == "update_latest":
            handle_update_latest(cmd_id, topic or "AI")
            return
        if intent == "add_paper":
            handle_add_paper(cmd_id, message, topic or "AI")
            return
        if intent == "analyze_paper":
            handle_analyze(cmd_id, message, topic or "AI")
            return
        if intent == "reach_out_email":
            handle_reach_out_email(cmd_id, message, topic or "AI")
            return

        # General Q&A → LLM conversation path
        handle_conversation(cmd_id, message, topic or "AI")
    except Exception:
        tb = traceback.format_exc()
        _push(cmd_id, "token", f"❌ 处理出错：\n{tb[:300]}")
        _push_done(cmd_id, "none")


# ─────────────────────────────────────────────────────────────────────────────
# HTTP Handler
# ─────────────────────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # suppress default log; errors printed in process_command

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def _read_body(self) -> str:
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length).decode("utf-8") if length else ""

    def _json(self, data: dict, code: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # ── POST ──────────────────────────────────────────────────────────────────

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path

        if path == "/command":
            body = self._read_body()
            try:
                data = json.loads(body) if body else {}
            except json.JSONDecodeError:
                self._json({"error": "invalid JSON"}, 400)
                return

            message = data.get("message", "").strip()
            if not message:
                self._json({"error": "message is empty"}, 400)
                return

            cmd_id = _new_id()
            topic = data.get("topic", "AI")

            # Create SSE queue before spawning thread (avoid race)
            with _sq_lock:
                _stream_queues[cmd_id] = queue.Queue()

            # Log to queue file (for compatibility with old cron approach)
            try:
                q_data = json.loads(QUEUE_FILE.read_text()) if QUEUE_FILE.exists() else []
            except Exception:
                q_data = []
            q_data.append({"id": cmd_id, "message": message, "topic": topic,
                            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"), "status": "processing"})
            QUEUE_FILE.write_text(json.dumps(q_data, ensure_ascii=False, indent=2))

            # Start background processing thread immediately
            t = threading.Thread(target=process_command, args=(cmd_id, message, topic), daemon=True)
            t.start()

            print(f"[chat] #{cmd_id} started: {message[:60]}")
            self._json({"id": cmd_id, "status": "streaming"})

        elif path == "/ping":
            self._json({"ok": True})

        elif path == "/pending_actions/approve":
            body = json.loads(self._read_body() or "{}")
            action_id = body.get("id")
            actions = _load_pending_actions()
            for a in actions:
                if a["id"] == action_id:
                    a["status"] = "approved"
                    a["approved_at"] = datetime.utcnow().isoformat()
                    break
            _save_pending_actions(actions)
            self._json({"ok": True})

        elif path == "/pending_actions/reject":
            body = json.loads(self._read_body() or "{}")
            action_id = body.get("id")
            actions = _load_pending_actions()
            for a in actions:
                if a["id"] == action_id:
                    a["status"] = "rejected"
                    break
            _save_pending_actions(actions)
            self._json({"ok": True})

        elif path == "/pending_actions/edit":
            body = json.loads(self._read_body() or "{}")
            action_id = body.get("id")
            draft_message = body.get("draft_message", "")
            actions = _load_pending_actions()
            for a in actions:
                if a["id"] == action_id:
                    a["draft_message"] = draft_message
                    break
            _save_pending_actions(actions)
            self._json({"ok": True})

        else:
            self._json({"error": "not found"}, 404)

    # ── GET ───────────────────────────────────────────────────────────────────

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        params = urllib.parse.parse_qs(parsed.query)

        if path == "/stream":
            cmd_id = (params.get("id") or [""])[0]
            with _sq_lock:
                q = _stream_queues.get(cmd_id)
            if q is None:
                self.send_response(404)
                self.end_headers()
                return

            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()

            # Stream events until sentinel (None)
            try:
                while True:
                    try:
                        item = q.get(timeout=30)
                    except queue.Empty:
                        # Send heartbeat to keep connection alive
                        self.wfile.write(b": heartbeat\n\n")
                        self.wfile.flush()
                        continue

                    if item is None:
                        # Sentinel: processing done
                        break

                    self.wfile.write(item.encode("utf-8"))
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass  # Client disconnected — OK
            finally:
                # Clean up the queue after a short delay (allow SSE reconnects)
                def _cleanup():
                    time.sleep(10)
                    with _sq_lock:
                        _stream_queues.pop(cmd_id, None)
                threading.Thread(target=_cleanup, daemon=True).start()

        elif path in ("/", "/view"):
            # Serve the knowledge base HTML directly — browser-accessible at http://localhost:7779/
            if HTML_PATH and HTML_PATH.exists():
                body = HTML_PATH.read_bytes()
                self.send_response(200)
                self._cors()
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                msg = b"<h2>Knowledge base not ready. Run generate_report.py first.</h2>"
                self.send_response(503)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(msg)))
                self.end_headers()
                self.wfile.write(msg)

        elif path == "/ping":
            self._json({"ok": True, "server": "FrontierPilot Chat v2", "port": PORT})

        elif path == "/pending_actions/list":
            self._json({"actions": _load_pending_actions()})

        else:
            self._json({"error": "not found"}, 404)


# ─────────────────────────────────────────────────────────────────────────────
# Threaded server
# ─────────────────────────────────────────────────────────────────────────────

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    global PORT, DATA_PATH, HTML_PATH, PENDING_ACTIONS_PATH

    args = sys.argv[1:]
    if "--port" in args:
        PORT = int(args[args.index("--port") + 1])
    if "--data" in args:
        DATA_PATH = Path(args[args.index("--data") + 1])
        PENDING_ACTIONS_PATH = DATA_PATH.parent / "pending_actions.json"
    if "--html" in args:
        HTML_PATH = Path(args[args.index("--html") + 1])

    if DATA_PATH and not DATA_PATH.exists():
        # Try case-insensitive match in the same directory
        parent = DATA_PATH.parent
        name_lower = DATA_PATH.name.lower()
        matches = [f for f in parent.glob("*.json") if f.name.lower() == name_lower] if parent.exists() else []
        if matches:
            DATA_PATH = matches[0]
            print(f"ℹ️  Data file found (case fix): {DATA_PATH}")
        else:
            print(f"⚠️  Data file not found: {DATA_PATH}")
            DATA_PATH = None

    print(f"✅ FrontierPilot Chat Server v2  →  http://localhost:{PORT}")
    print(f"   即时处理：POST /command  →  GET /stream?id=N (SSE)")
    if DATA_PATH:
        print(f"   知识库数据：{DATA_PATH}")
    else:
        print(f"   ⚠️  未指定数据文件，HTML 更新功能不可用")
        print(f"      用法：python3 chat_server.py --data /tmp/fp_demo_test/diffusion_v1.json")
    if os.environ.get("OPENCLAW_GATEWAY_TOKEN"):
        print(f"   🤖 LLM via OpenClaw Gateway（端口 {os.environ.get('OPENCLAW_GATEWAY_PORT','18789')}）")
    elif os.environ.get("OPENROUTER_API_KEY"):
        print(f"   🤖 LLM via OpenRouter")
    elif os.environ.get("ANTHROPIC_API_KEY"):
        print(f"   🤖 LLM via Anthropic API")
    else:
        print(f"   ℹ️  未检测到 LLM 渠道，问答将使用模板回复")
    print()

    server = ThreadedHTTPServer(("localhost", PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[chat_server] Stopped.")
        server.server_close()


if __name__ == "__main__":
    main()
