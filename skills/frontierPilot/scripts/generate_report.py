#!/usr/bin/env python3
"""
FrontierPilot Report Generator

Generates a self-contained interactive HTML report from research data.
The HTML is a "living knowledge base" — not a one-time static report.
It supports personal notes (localStorage), latest updates tab, and
a growing knowledge graph.

Usage:
  python3 generate_report.py --data /tmp/fp_data.json --output ~/FrontierPilot/diffusion_models/report.html

Data JSON schema:
{
  "topic": "Diffusion Models",
  "topic_zh": "扩散模型",
  "generated_at": "2026-03-15T10:00:00",
  "field_overview": "300-400字专家视角综述：本领域本质问题、2024年共识与争议、新手最应关注什么",
  "foundation": [
    {
      "year": 2020, "title": "DDPM", "authors": ["Ho et al."],
      "description": "确立现代扩散模型范式", "url": "https://arxiv.org/abs/...",
      "problem_solved": "生成质量优于GAN", "problem_left": "采样速度极慢（1000步）",
      "is_key": true, "citation_count": 18000
    }
  ],
  "frontier": [
    {
      "title": "Flow Matching for Generative Modeling", "forum_id": "xxx",
      "venue": "ICLR", "year": 2024, "url": "https://openreview.net/forum?id=xxx",
      "avg_rating": 7.3,
      "reviews": [{"rating": "8", "strengths": "...", "weaknesses": "...", "related_work": ["Consistency Models"]}]
    }
  ],
  "reading_list": [
    {"title": "...", "type": "foundation", "reason": "...", "url": "..."}
  ],
  "top_authors": [
    {
      "name": "Yang Song", "institution": "OpenAI / Stanford",
      "papers_count": 45, "recent_work": "Score-based generative modeling, Consistency Models",
      "url": "https://scholar.google.com/citations?user=..."
    }
  ],
  "resources": {
    "github": [{"name": "CompVis/stable-diffusion", "stars": "52k", "description": "...", "url": "..."}],
    "bilibili": [{"title": "李沐 DDPM 论文精读", "url": "...", "view_count": 1800000}],
    "wechat": [{"title": "...", "url": "..."}]
  },
  "graph_mermaid": "flowchart LR\\n  classDef foundation fill:#dbeafe,stroke:#2563eb,color:#1e40af\\n  classDef frontier fill:#f5f3ff,stroke:#7c3aed,color:#4c1d95\\n  classDef key fill:#2563eb,stroke:#1e40af,color:white\\n  subgraph sg1[\\"🔵 Score-based SDE\\"]\\n    style sg1 fill:#eff6ff,stroke:#2563eb\\n    NCSN[\\"2019 NCSN\\\\n⭐4k\\"]:::foundation\\n    DDPM[\\"2020 DDPM\\\\n⭐18k\\"]:::key\\n  end\\n  NCSN --> DDPM",
  "paper_clusters": [
    {
      "id": "cluster_sde",
      "name": "Score-based / SDE Methods",
      "subgraph_style": "fill:#eff6ff,stroke:#2563eb",
      "paper_node_ids": ["N2019_NCSN", "N2020_DDPM"]
    }
  ],
  "latest_updates": [
    {
      "date": "2026-03-10", "title": "Consistency Flow Matching (arXiv 2026.03)",
      "url": "https://arxiv.org/abs/...",
      "summary": "将 consistency training 与 flow matching 统一，在 ImageNet 上单步 FID 2.3"
    }
  ]
}
"""

import argparse
import base64
import io
import json
import os
import re
import signal
import socket
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path


# ─────────────────────────────────────────────────────────────────────────────
# LLM helper (Gateway → OpenRouter → Anthropic → "")
# ─────────────────────────────────────────────────────────────────────────────

def _call_llm_once(prompt: str, system: str = "", max_tokens: int = 400) -> str:
    """
    generate_report.py 内部 LLM 调用：Gateway → OpenRouter → Anthropic → "".
    与 chat_server.py 的 call_llm() 策略完全一致。
    """
    messages: list = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    # 1. OpenClaw Gateway
    gw_token = os.environ.get("OPENCLAW_GATEWAY_TOKEN", "")
    gw_port = os.environ.get("OPENCLAW_GATEWAY_PORT", "18789")
    if gw_token:
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{gw_port}/v1/chat/completions",
                data=json.dumps({"model": "openclaw:main", "messages": messages,
                                 "stream": False, "max_tokens": max_tokens},
                                ensure_ascii=False).encode(),
                headers={"Authorization": f"Bearer {gw_token}", "Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())["choices"][0]["message"]["content"]
        except Exception:
            pass

    # 2. OpenRouter
    or_key = os.environ.get("OPENROUTER_API_KEY", "")
    if or_key:
        try:
            req = urllib.request.Request(
                "https://openrouter.ai/api/v1/chat/completions",
                data=json.dumps({"model": "anthropic/claude-haiku-4-5", "messages": messages,
                                 "max_tokens": max_tokens}, ensure_ascii=False).encode(),
                headers={"Authorization": f"Bearer {or_key}", "Content-Type": "application/json",
                         "HTTP-Referer": "https://frontierPilot.ai"},
            )
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())["choices"][0]["message"]["content"]
        except Exception:
            pass

    # 3. Anthropic 直连
    anth_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if anth_key:
        try:
            body: dict = {"model": "claude-haiku-4-5-20251001", "max_tokens": max_tokens,
                          "messages": [m for m in messages if m["role"] != "system"]}
            if system:
                body["system"] = system
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                data=json.dumps(body, ensure_ascii=False).encode(),
                headers={"x-api-key": anth_key, "anthropic-version": "2023-06-01",
                         "Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())["content"][0]["text"]
        except Exception:
            pass

    return ""


# ─────────────────────────────────────────────────────────────────────────────
# HTML Template
# ─────────────────────────────────────────────────────────────────────────────

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>FrontierPilot · {topic} 知识库</title>
<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
<style>
:root {{
  --primary: #2563eb;
  --primary-light: #eff6ff;
  --frontier: #7c3aed;
  --frontier-light: #f5f3ff;
  --social: #059669;
  --social-light: #ecfdf5;
  --warning: #d97706;
  --danger: #dc2626;
  --text: #1e293b;
  --text-muted: #64748b;
  --border: #e2e8f0;
  --bg: #f8fafc;
  --card: #ffffff;
  --radius: 12px;
  --shadow: 0 1px 3px rgba(0,0,0,0.08), 0 4px 16px rgba(0,0,0,0.04);
  --shadow-hover: 0 4px 12px rgba(0,0,0,0.12), 0 8px 32px rgba(0,0,0,0.06);
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', sans-serif;
  background: var(--bg); color: var(--text); line-height: 1.6;
}}

/* ── Header ── */
.header {{
  background: linear-gradient(135deg, #1e40af 0%, #4338ca 50%, #7c3aed 100%);
  color: white; padding: 40px 32px 32px; position: relative; overflow: hidden;
}}
.header::before {{
  content: ''; position: absolute; inset: 0;
  background: url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%23ffffff' fill-opacity='0.04'%3E%3Ccircle cx='30' cy='30' r='20'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E");
}}
.header-inner {{ position: relative; max-width: 1100px; margin: 0 auto; }}
.logo {{ font-size: 13px; font-weight: 600; letter-spacing: 2px; opacity: 0.7; margin-bottom: 8px; }}
.header h1 {{ font-size: 2.2rem; font-weight: 700; margin-bottom: 8px; }}
.header-sub {{ opacity: 0.85; font-size: 1rem; margin-bottom: 20px; }}
.badges {{ display: flex; gap: 8px; flex-wrap: wrap; }}
.badge {{
  background: rgba(255,255,255,0.15); border: 1px solid rgba(255,255,255,0.25);
  border-radius: 20px; padding: 4px 12px; font-size: 12px; font-weight: 500;
}}

/* ── Nav ── */
.nav {{
  background: white; border-bottom: 1px solid var(--border);
  position: sticky; top: 0; z-index: 100;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}}
.nav-inner {{
  max-width: 1100px; margin: 0 auto; padding: 0 32px;
  display: flex; gap: 4px; overflow-x: auto;
}}
.nav-item {{
  padding: 14px 16px; font-size: 13px; font-weight: 500; color: var(--text-muted);
  border-bottom: 2px solid transparent; cursor: pointer; white-space: nowrap;
  text-decoration: none; transition: all 0.2s;
}}
.nav-item:hover {{ color: var(--primary); }}
.nav-item.active {{ color: var(--primary); border-bottom-color: var(--primary); }}
.nav-item.panel-tab {{ color: var(--frontier); }}
.nav-item.panel-tab:hover {{ color: var(--frontier); opacity: 0.8; }}
.nav-item.panel-tab.active {{ color: var(--frontier); border-bottom-color: var(--frontier); }}
.nav-badge {{
  display: inline-block; background: var(--frontier); color: white;
  border-radius: 10px; padding: 1px 6px; font-size: 10px; font-weight: 700;
  margin-left: 4px; vertical-align: middle;
}}

/* ── Layout ── */
.container {{ max-width: 1100px; margin: 0 auto; padding: 32px; }}
.section {{ margin-bottom: 48px; scroll-margin-top: 60px; }}
.section-header {{
  display: flex; align-items: center; gap: 10px;
  margin-bottom: 24px; padding-bottom: 12px; border-bottom: 2px solid var(--border);
}}
.section-icon {{ font-size: 1.4rem; }}
.section-title {{ font-size: 1.25rem; font-weight: 700; }}
.section-count {{
  background: var(--primary-light); color: var(--primary);
  border-radius: 12px; padding: 2px 8px; font-size: 12px; font-weight: 600;
}}

/* ── Field Overview ── */
.overview-card {{
  background: linear-gradient(135deg, #f0f7ff 0%, #f5f3ff 100%);
  border-radius: var(--radius); padding: 28px 32px;
  border: 1px solid #c7d2fe; box-shadow: var(--shadow);
}}
.overview-text {{ font-size: 15px; line-height: 1.9; color: var(--text); }}
.overview-placeholder {{
  text-align: center; padding: 40px; color: var(--text-muted); font-size: 14px;
  border: 2px dashed var(--border); border-radius: var(--radius);
}}

/* ── Graph ── */
.graph-card {{
  background: var(--card); border-radius: var(--radius); padding: 24px;
  box-shadow: var(--shadow); overflow-x: auto;
}}
.mermaid {{ text-align: center; }}
.mermaid .node {{ cursor: pointer; }}
.mermaid .node:hover {{ filter: brightness(0.95); }}

/* ── Timeline (Foundation) ── */
.timeline {{ position: relative; padding-left: 32px; }}
.timeline::before {{
  content: ''; position: absolute; left: 10px; top: 0; bottom: 0;
  width: 2px; background: linear-gradient(to bottom, var(--primary), #c7d2fe);
}}
.timeline-item {{ position: relative; margin-bottom: 28px; }}
.timeline-item::before {{
  content: ''; position: absolute; left: -26px; top: 8px;
  width: 12px; height: 12px; border-radius: 50%;
  background: white; border: 2px solid var(--primary);
  box-shadow: 0 0 0 3px var(--primary-light);
}}
.timeline-item.key::before {{
  background: var(--primary); width: 16px; height: 16px; left: -28px; top: 6px;
}}
.timeline-card {{
  background: var(--card); border-radius: var(--radius); padding: 18px 20px;
  box-shadow: var(--shadow); border-left: 3px solid transparent;
  transition: all 0.2s;
}}
.timeline-card:hover {{ box-shadow: var(--shadow-hover); transform: translateX(2px); }}
.timeline-card.key {{ border-left-color: var(--primary); }}
.timeline-year {{
  font-size: 11px; font-weight: 700; color: var(--primary);
  letter-spacing: 1px; margin-bottom: 4px;
}}
.timeline-title {{ font-size: 1rem; font-weight: 600; margin-bottom: 6px; }}
.timeline-title a {{ color: var(--text); text-decoration: none; }}
.timeline-title a:hover {{ color: var(--primary); }}
.timeline-meta {{ font-size: 12px; color: var(--text-muted); margin-bottom: 10px; }}
.timeline-pills {{ display: flex; gap: 6px; flex-wrap: wrap; margin-top: 8px; }}
.pill {{
  font-size: 11px; padding: 3px 8px; border-radius: 8px; font-weight: 500;
}}
.pill-solved {{ background: #dcfce7; color: #166534; }}
.pill-left {{ background: #fee2e2; color: #991b1b; }}
.pill-cite {{ background: #fef3c7; color: #92400e; }}
.key-badge {{
  display: inline-block; background: var(--primary); color: white;
  font-size: 10px; padding: 2px 6px; border-radius: 4px; margin-left: 6px; vertical-align: middle;
}}

/* ── Frontier Cards ── */
.frontier-grid {{ display: grid; gap: 20px; }}
.frontier-card {{
  background: var(--card); border-radius: var(--radius); padding: 20px;
  box-shadow: var(--shadow); border-top: 3px solid var(--frontier);
}}
.frontier-card-header {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; margin-bottom: 14px; }}
.frontier-title {{ font-size: 1rem; font-weight: 600; }}
.frontier-title a {{ color: var(--text); text-decoration: none; }}
.frontier-title a:hover {{ color: var(--frontier); }}
.rating-badge {{
  flex-shrink: 0; background: var(--frontier-light); color: var(--frontier);
  border-radius: 8px; padding: 4px 10px; font-size: 13px; font-weight: 700;
  white-space: nowrap;
}}
.rating-badge.high {{ background: #dcfce7; color: #166534; }}
.rating-badge.mid {{ background: #fef9c3; color: #854d0e; }}
.rating-badge.low {{ background: #fee2e2; color: #991b1b; }}
.rating-badge.cite {{ background: #f3f4f6; color: #374151; }}
.reviews-wrap {{ display: grid; gap: 10px; margin-top: 12px; }}
.review-item {{
  background: var(--bg); border-radius: 8px; padding: 12px 14px;
  border-left: 3px solid var(--border);
}}
.review-rating {{ font-size: 11px; font-weight: 700; color: var(--text-muted); margin-bottom: 6px; }}
.review-pro {{ color: #166534; font-size: 13px; margin-bottom: 4px; }}
.review-con {{ color: #991b1b; font-size: 13px; margin-bottom: 4px; }}
.review-related {{ margin-top: 8px; }}
.review-related-label {{ font-size: 11px; color: var(--frontier); font-weight: 600; }}
.related-tags {{ display: flex; gap: 4px; flex-wrap: wrap; margin-top: 4px; }}
.related-tag {{
  background: var(--frontier-light); color: var(--frontier);
  font-size: 11px; padding: 2px 7px; border-radius: 6px;
}}

/* ── Reading List ── */
.reading-list {{ display: grid; gap: 10px; }}
.reading-item {{
  background: var(--card); border-radius: 10px; padding: 14px 16px;
  box-shadow: var(--shadow); display: flex; align-items: flex-start; gap: 12px;
}}
.reading-num {{
  flex-shrink: 0; width: 28px; height: 28px; border-radius: 50%;
  background: var(--primary-light); color: var(--primary);
  display: flex; align-items: center; justify-content: center;
  font-size: 12px; font-weight: 700;
}}
.reading-body {{ flex: 1; min-width: 0; }}
.reading-title {{ font-size: 14px; font-weight: 600; margin-bottom: 3px; }}
.reading-title a {{ color: var(--text); text-decoration: none; }}
.reading-title a:hover {{ color: var(--primary); }}
.reading-reason {{ font-size: 12px; color: var(--text-muted); }}
.reading-type {{
  flex-shrink: 0; font-size: 10px; padding: 2px 7px; border-radius: 6px; font-weight: 600;
}}
.type-foundation {{ background: #dbeafe; color: #1e40af; }}
.type-frontier {{ background: var(--frontier-light); color: var(--frontier); }}
.type-recommended {{ background: #fef3c7; color: #92400e; }}

/* ── Resources ── */
.resources-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; }}
.resource-section {{ background: var(--card); border-radius: var(--radius); padding: 20px; box-shadow: var(--shadow); }}
.resource-section-title {{
  font-size: 13px; font-weight: 700; color: var(--text-muted);
  letter-spacing: 1px; margin-bottom: 14px; display: flex; align-items: center; gap: 6px;
}}
.resource-item {{ padding: 10px 0; border-bottom: 1px solid var(--border); }}
.resource-item:last-child {{ border-bottom: none; padding-bottom: 0; }}
.resource-name {{ font-size: 13px; font-weight: 600; margin-bottom: 2px; }}
.resource-name a {{ color: var(--text); text-decoration: none; }}
.resource-name a:hover {{ color: var(--primary); }}
.resource-meta {{ font-size: 12px; color: var(--text-muted); display: flex; gap: 8px; }}
.stars {{ color: var(--warning); }}

/* ── Top Authors / Labs ── */
.authors-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; }}
.author-card {{
  background: var(--card); border-radius: var(--radius); padding: 16px 20px;
  box-shadow: var(--shadow); display: flex; align-items: flex-start; gap: 12px;
  transition: all 0.2s;
}}
.author-card:hover {{ box-shadow: var(--shadow-hover); }}
.author-rank {{
  flex-shrink: 0; width: 30px; height: 30px; border-radius: 50%;
  background: linear-gradient(135deg, var(--primary), var(--frontier));
  color: white; display: flex; align-items: center; justify-content: center;
  font-size: 12px; font-weight: 700;
}}
.author-body {{ flex: 1; min-width: 0; }}
.author-name {{ font-size: 14px; font-weight: 600; margin-bottom: 2px; }}
.author-name a {{ color: var(--text); text-decoration: none; }}
.author-name a:hover {{ color: var(--primary); }}
.author-institution {{ font-size: 12px; color: var(--text-muted); margin-bottom: 4px; }}
.author-recent {{ font-size: 12px; color: var(--text-muted); font-style: italic; line-height: 1.5; }}
.author-count {{
  flex-shrink: 0; text-align: center;
  font-size: 18px; font-weight: 700; color: var(--primary); line-height: 1.1;
}}
.author-count span {{ display: block; font-size: 10px; font-weight: 400; color: var(--text-muted); }}
.authors-placeholder {{
  text-align: center; padding: 40px; color: var(--text-muted); font-size: 14px;
  border: 2px dashed var(--border); border-radius: var(--radius);
}}

/* ── View Panels (最新动态 / 我的笔记) ── */
.view-panel {{
  display: none; max-width: 1100px; margin: 0 auto; padding: 32px;
}}
.view-panel.active {{ display: block; }}

/* Latest Updates */
.updates-placeholder {{
  text-align: center; padding: 80px 32px; color: var(--text-muted);
}}
.updates-placeholder-icon {{ font-size: 3rem; margin-bottom: 16px; }}
.updates-placeholder-text {{
  font-size: 1.1rem; font-weight: 600; margin-bottom: 12px; color: var(--text);
}}
.updates-placeholder-hint {{
  font-size: 14px; line-height: 1.7;
  background: var(--primary-light); border-radius: var(--radius);
  padding: 16px 24px; display: inline-block; text-align: left; max-width: 480px;
}}
.updates-placeholder-hint code {{
  background: white; padding: 2px 6px; border-radius: 4px;
  font-family: monospace; font-size: 13px; color: var(--primary);
}}
.update-batch {{ margin-bottom: 32px; }}
.update-batch-header {{
  font-size: 12px; font-weight: 700; color: var(--text-muted); letter-spacing: 1px;
  text-transform: uppercase; margin-bottom: 12px; padding: 8px 0;
  border-bottom: 1px solid var(--border);
}}
.update-item {{
  background: var(--card); border-radius: var(--radius); padding: 16px 20px;
  box-shadow: var(--shadow); margin-bottom: 10px; border-left: 3px solid var(--frontier);
  transition: all 0.2s;
}}
.update-item:hover {{ box-shadow: var(--shadow-hover); }}
.update-date {{ font-size: 11px; color: var(--text-muted); font-weight: 600; letter-spacing: 0.5px; margin-bottom: 4px; }}
.update-title {{ font-size: 14px; font-weight: 600; margin-bottom: 6px; }}
.update-title a {{ color: var(--text); text-decoration: none; }}
.update-title a:hover {{ color: var(--frontier); }}
.update-summary {{ font-size: 13px; color: var(--text-muted); line-height: 1.6; }}

/* ── Chat Panel (智能助手) ── */
.chat-panel {{ max-width: 860px; }}
.chat-server-hint {{
  font-size: 12px; color: var(--text-muted); margin-bottom: 16px;
  background: var(--primary-light); border-radius: 8px; padding: 10px 14px;
  display: flex; align-items: center; gap: 8px;
}}
.chat-server-dot {{
  width: 8px; height: 8px; border-radius: 50%; background: #94a3b8; flex-shrink: 0;
  transition: background 0.3s;
}}
.chat-server-dot.online {{ background: var(--social); box-shadow: 0 0 0 3px #bbf7d0; }}
.chat-messages {{
  min-height: 380px; max-height: 480px; overflow-y: auto;
  background: var(--bg); border-radius: var(--radius);
  border: 1px solid var(--border); padding: 20px; margin-bottom: 12px;
  display: flex; flex-direction: column; gap: 14px;
}}
.chat-welcome {{
  text-align: center; color: var(--text-muted); padding: 40px 20px;
  font-size: 14px; line-height: 2;
}}
.chat-welcome-icon {{ font-size: 2.5rem; margin-bottom: 10px; }}
.chat-msg {{
  display: flex; gap: 10px; max-width: 85%;
}}
.chat-msg.user {{ align-self: flex-end; flex-direction: row-reverse; }}
.chat-msg.agent {{ align-self: flex-start; }}
.chat-avatar {{
  flex-shrink: 0; width: 30px; height: 30px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 14px;
}}
.chat-msg.user .chat-avatar {{ background: var(--primary); }}
.chat-msg.agent .chat-avatar {{ background: linear-gradient(135deg, var(--frontier), var(--primary)); }}
.chat-bubble {{
  padding: 10px 14px; border-radius: 16px; font-size: 13px; line-height: 1.7;
  white-space: pre-wrap; word-break: break-word;
}}
.chat-msg.user .chat-bubble {{
  background: var(--primary); color: white; border-top-right-radius: 4px;
}}
.chat-msg.agent .chat-bubble {{
  background: var(--card); color: var(--text); border-top-left-radius: 4px;
  border: 1px solid var(--border); box-shadow: var(--shadow);
}}
.chat-bubble.thinking {{
  color: var(--text-muted); font-style: italic;
  display: flex; align-items: center; gap: 8px;
}}
.chat-bubble.action-done {{
  border-left: 3px solid var(--social);
}}
.thinking-dots {{ display: flex; gap: 4px; }}
.thinking-dots span {{
  width: 6px; height: 6px; border-radius: 50%; background: var(--text-muted);
  animation: dot-bounce 1.2s infinite;
}}
.thinking-dots span:nth-child(2) {{ animation-delay: 0.2s; }}
.thinking-dots span:nth-child(3) {{ animation-delay: 0.4s; }}
@keyframes dot-bounce {{
  0%, 80%, 100% {{ transform: scale(0.8); opacity: 0.4; }}
  40% {{ transform: scale(1); opacity: 1; }}
}}
.chat-refresh-hint {{
  margin-top: 8px; font-size: 12px; color: var(--social);
  background: #f0fdf4; border-radius: 8px; padding: 8px 12px;
  display: none;
}}
.chat-quickactions {{ display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }}
.chat-chip {{
  font-size: 12px; padding: 5px 12px; border-radius: 16px; cursor: pointer;
  background: var(--card); border: 1px solid var(--border); color: var(--text-muted);
  transition: all 0.15s; white-space: nowrap;
}}
.chat-chip:hover {{
  background: var(--primary-light); border-color: var(--primary); color: var(--primary);
}}
.chat-input-row {{
  display: flex; gap: 8px; align-items: flex-end;
}}
.chat-input {{
  flex: 1; min-height: 44px; max-height: 120px;
  border: 1px solid var(--border); border-radius: 12px;
  padding: 10px 14px; font-size: 14px; line-height: 1.5; resize: none;
  background: var(--card); color: var(--text); transition: border-color 0.2s;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', sans-serif;
}}
.chat-input:focus {{
  outline: none; border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(37,99,235,0.1);
}}
.btn {{
  padding: 9px 18px; border-radius: 8px; font-size: 13px; font-weight: 600;
  cursor: pointer; border: none; transition: all 0.2s;
}}
.btn-primary {{ background: var(--primary); color: white; }}
.btn-primary:hover {{ background: #1d4ed8; transform: translateY(-1px); }}
.btn-primary:disabled {{ background: #93c5fd; transform: none; cursor: not-allowed; }}
.chat-send-btn {{
  flex-shrink: 0; width: 44px; height: 44px; border-radius: 12px; padding: 0;
  background: var(--primary); color: white; border: none; cursor: pointer;
  font-size: 18px; display: flex; align-items: center; justify-content: center;
  transition: all 0.2s;
}}
.chat-send-btn:hover {{ background: #1d4ed8; transform: translateY(-1px); }}
.chat-send-btn:disabled {{ background: #93c5fd; transform: none; cursor: not-allowed; }}

/* ── Social Actions Timeline ── */
.social-timeline {{ display: flex; flex-direction: column; gap: 12px; }}
.social-action {{
  display: flex; align-items: flex-start; gap: 14px;
  background: var(--card); border-radius: var(--radius); padding: 14px 18px;
  box-shadow: var(--shadow); transition: all 0.2s;
}}
.social-action:hover {{ box-shadow: var(--shadow-hover); }}
.social-dot {{
  flex-shrink: 0; width: 12px; height: 12px; border-radius: 50%; margin-top: 4px;
}}
.social-dot.done, .social-dot.followed {{ background: var(--social); box-shadow: 0 0 0 3px #bbf7d0; }}
.social-dot.ready {{ background: var(--warning); box-shadow: 0 0 0 3px #fde68a; }}
.social-dot.skipped {{ background: #94a3b8; }}
.social-dot.demo {{ background: var(--primary); box-shadow: 0 0 0 3px var(--primary-light); }}
.social-body {{ flex: 1; min-width: 0; }}
.social-time {{
  font-size: 11px; color: var(--text-muted); font-weight: 600;
  letter-spacing: 0.5px; margin-bottom: 3px;
}}
.social-summary {{ font-size: 13px; font-weight: 500; color: var(--text); margin-bottom: 4px; }}
.social-reason {{ font-size: 12px; color: var(--text-muted); }}
.social-actions-row {{ display: flex; gap: 8px; margin-top: 8px; flex-wrap: wrap; }}
.social-btn {{
  font-size: 12px; padding: 4px 12px; border-radius: 8px;
  border: 1px solid var(--border); background: var(--bg);
  color: var(--social); cursor: pointer; font-weight: 500; transition: all 0.15s;
  text-decoration: none; display: inline-block;
}}
.social-btn:hover {{ background: var(--social-light); border-color: var(--social); }}
.social-btn.primary {{
  background: var(--social); color: white; border-color: var(--social);
}}
.social-btn.primary:hover {{ background: #047857; }}
.social-status-tag {{
  flex-shrink: 0; font-size: 10px; padding: 2px 8px; border-radius: 6px; font-weight: 600;
  margin-top: 2px; white-space: nowrap;
}}
.tag-done, .tag-followed {{ background: #dcfce7; color: #166534; }}
.tag-ready {{ background: #fef3c7; color: #854d0e; }}
.tag-skipped {{ background: #f1f5f9; color: #64748b; }}
.tag-demo {{ background: var(--primary-light); color: var(--primary); }}
.social-draft-box {{
  margin-top: 8px; background: var(--bg); border-radius: 8px; padding: 10px 14px;
  border-left: 3px solid var(--warning); font-size: 13px; color: var(--text);
  line-height: 1.6;
}}

/* ── Footer ── */
.footer {{
  text-align: center; padding: 32px; color: var(--text-muted); font-size: 12px;
  border-top: 1px solid var(--border); margin-top: 48px;
}}

/* ── Smooth scroll ── */
html {{ scroll-behavior: smooth; }}
</style>
</head>
<body>

<div class="header">
  <div class="header-inner">
    <div class="logo">✦ FRONTIERPILOT · 成长型知识库</div>
    <h1>📍 {topic} 知识库</h1>
    <div class="header-sub">{topic_zh} · 由 FrontierPilot Agent 持续维护</div>
    <div class="badges">
      <span class="badge">📚 {foundation_count} 篇奠基论文</span>
      <span class="badge">🔬 {frontier_count} 篇前沿论文</span>
      <span class="badge">📋 {reading_count} 篇阅读清单</span>
      <span class="badge">🌐 多平台资源</span>
      {updates_badge_header}
      <span class="badge">⏱️ {generated_at}</span>
    </div>
  </div>
</div>

<nav class="nav">
  <div class="nav-inner">
    <a class="nav-item active" href="#overview" onclick="showMain(event, 'overview')">📊 领域概况</a>
    <a class="nav-item" href="#graph" onclick="showMain(event, 'graph')">🗺️ 知识图谱</a>
    <a class="nav-item" href="#foundation" onclick="showMain(event, 'foundation')">📚 基础 Roadmap</a>
    <a class="nav-item" href="#frontier" onclick="showMain(event, 'frontier')">🔬 前沿快照</a>
    <a class="nav-item" href="#reading" onclick="showMain(event, 'reading')">📋 阅读清单</a>
    <a class="nav-item" href="#resources" onclick="showMain(event, 'resources')">🌐 资源地图</a>
    <a class="nav-item" href="#authors" onclick="showMain(event, 'authors')">🏛️ 领域强组</a>
    <a class="nav-item panel-tab" href="#" onclick="showPanel(event, 'panel-updates')">📰 最新动态{updates_badge_nav}</a>
    <a class="nav-item panel-tab" href="#" onclick="showPanel(event, 'panel-social');loadPendingActions()">🌐 社交行动{social_badge_nav}</a>
    <a class="nav-item panel-tab" href="#" onclick="showPanel(event, 'panel-heatmap')">📊 评审共识</a>
    <a class="nav-item panel-tab" href="#" onclick="showPanel(event, 'panel-chat')">🤖 智能助手</a>
  </div>
</nav>

<!-- ── 最新动态 Panel ── -->
<div id="panel-updates" class="view-panel">
  <div class="section-header">
    <span class="section-icon">📰</span>
    <span class="section-title">最新动态</span>
    <span class="section-count">{latest_updates_count} 条更新</span>
  </div>
  {latest_updates_html}
</div>

<!-- ── 社交行动 Panel ── -->
<div id="panel-social" class="view-panel">
  <div class="section-header">
    <span class="section-icon">🌐</span>
    <span class="section-title">社交行动</span>
    <span class="section-count">{social_actions_count} 次操作</span>
    <span style="font-size:12px;color:var(--text-muted);margin-left:auto">FrontierPilot 帮你进圈子</span>
  </div>

  <!-- 待审批行动队列 (P1) -->
  <div id="pendingActionsSection" style="display:none;padding:0 0 16px 0;">
    <h3 style="color:#059669;margin-bottom:12px;font-size:15px;">⏳ 待审批行动</h3>
    <div id="pendingActionsList"></div>
  </div>

  {social_actions_html}
</div>

<!-- ── 评审共识 Panel (P2) ── -->
<div id="panel-heatmap" class="view-panel">
  <div class="section-header">
    <span class="section-icon">📊</span>
    <span class="section-title">审稿人共识分析</span>
  </div>
  <p style="color:var(--text-muted);margin-bottom:24px;font-size:13px;">基于 OpenReview 真实评审数据，分析各论文的评分分布与审稿人共识度。标准差越低代表意见越统一，越高说明存在争议。</p>

  <div style="overflow-x:auto;margin-bottom:32px;">
    <table style="border-collapse:collapse;width:100%;font-size:14px;">
      <thead>
        <tr style="background:#f8fafc;">
          <th style="text-align:left;padding:10px 16px;border-bottom:2px solid #e5e7eb;">论文</th>
          <th style="padding:10px 16px;border-bottom:2px solid #e5e7eb;">均分</th>
          <th style="padding:10px 16px;border-bottom:2px solid #e5e7eb;">标准差</th>
          <th style="padding:10px 16px;border-bottom:2px solid #e5e7eb;">评分分布</th>
          <th style="padding:10px 16px;border-bottom:2px solid #e5e7eb;">共识度</th>
        </tr>
      </thead>
      <tbody id="heatmapTableBody"></tbody>
    </table>
  </div>

  <h3 style="color:#374151;margin-bottom:16px;font-size:15px;">🔍 审稿人关注的核心主题</h3>
  <div id="themeClusterGrid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px;"></div>
</div>

<!-- ── 智能助手 Panel ── -->
<div id="panel-chat" class="view-panel">
  <div class="chat-panel">
    <div class="section-header">
      <span class="section-icon">🤖</span>
      <span class="section-title">智能助手 · {topic}</span>
    </div>

    <div class="chat-server-hint">
      <div id="chat-dot" class="chat-server-dot"></div>
      <span id="chat-status-text">正在连接 OpenClaw 助手（localhost:7779）…</span>
    </div>

    <div id="chat-messages" class="chat-messages">
      <div class="chat-welcome">
        <div class="chat-welcome-icon">🤖</div>
        你好！我是 FrontierPilot 智能助手，由 OpenClaw 驱动。<br>
        你可以让我更新知识库、添加论文、分析最新进展。<br><br>
        <span style="font-size:12px;color:var(--text-muted)">试试下面的快捷指令 ↓</span>
      </div>
    </div>

    <div id="chat-refresh-hint" class="chat-refresh-hint">
      ✅ 知识库已更新！<a href="javascript:location.reload()" style="color:var(--social);font-weight:600;margin-left:4px">点击刷新页面</a>查看最新内容
    </div>

    <div class="chat-quickactions">
      <span class="chat-chip" onclick="fillInput('更新 {topic} 的最新动态')">🔄 更新最新动态</span>
      <span class="chat-chip" onclick="fillInput('把这篇论文添加到知识图谱：')">➕ 添加论文</span>
      <span class="chat-chip" onclick="fillInput('分析 arXiv 论文：')">🔍 分析 arXiv 论文</span>
      <span class="chat-chip" onclick="fillInput('推荐 {topic} 方向的入门阅读路径')">📚 入门路径推荐</span>
    </div>

    <div class="chat-input-row">
      <textarea id="chat-input" class="chat-input" rows="1"
        placeholder="输入指令，例如：把 Stable Diffusion 3 添加到知识图谱…"></textarea>
      <button id="chat-send-btn" class="chat-send-btn" onclick="sendChat()">↑</button>
    </div>
  </div>
</div>

<!-- ── Main View ── -->
<div id="view-main" class="container">

  <!-- Field Overview -->
  <section class="section" id="overview">
    <div class="section-header">
      <span class="section-icon">📊</span>
      <span class="section-title">领域全景 · 专家视角导读</span>
    </div>
    {field_overview_html}
  </section>

  <!-- Knowledge Graph -->
  <section class="section" id="graph">
    <div class="section-header">
      <span class="section-icon">🗺️</span>
      <span class="section-title">领域知识图谱</span>
    </div>
    <div class="graph-card">
      <div class="mermaid">
{graph_mermaid}
      </div>
    </div>
    <!-- Paper tooltip overlay -->
    <div id="paperTooltip" style="display:none;position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);
         z-index:1000;background:white;border:1px solid #e5e7eb;border-radius:12px;
         box-shadow:0 20px 60px rgba(0,0,0,0.15);padding:24px;max-width:480px;width:90%;">
      <button onclick="closePaperTooltip()" style="position:absolute;top:12px;right:16px;
        background:none;border:none;font-size:20px;cursor:pointer;color:#6b7280;">&times;</button>
      <div id="tooltipTitle" style="font-weight:700;font-size:18px;color:#1e1e1e;margin-bottom:8px;padding-right:24px;"></div>
      <div id="tooltipMeta" style="color:#6b7280;font-size:13px;margin-bottom:12px;"></div>
      <div id="tooltipAbstract" style="color:#374151;font-size:14px;line-height:1.6;margin-bottom:16px;max-height:120px;overflow-y:auto;"></div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;">
        <button id="tooltipExpandBtn" onclick="expandFromNode(currentTooltipNodeId)"
          style="background:#2563eb;color:white;border:none;border-radius:8px;padding:8px 16px;cursor:pointer;font-size:14px;">
          Expand
        </button>
        <a id="tooltipLink" href="#" target="_blank"
          style="background:#f3f4f6;color:#374151;border:none;border-radius:8px;padding:8px 16px;
                 text-decoration:none;font-size:14px;display:inline-flex;align-items:center;">
          Paper
        </a>
        <button onclick="chatAboutPaper(currentTooltipNodeId)"
          style="background:#059669;color:white;border:none;border-radius:8px;padding:8px 16px;cursor:pointer;font-size:14px;">
          Ask AI
        </button>
      </div>
      <div id="tooltipExpandStatus" style="margin-top:12px;font-size:13px;color:#2563eb;display:none;"></div>
    </div>
    <div id="tooltipOverlay" onclick="closePaperTooltip()"
      style="display:none;position:fixed;inset:0;background:rgba(0,0,0,0.3);z-index:999;"></div>
    <div id="graphExpansionList" style="display:none;margin-top:24px;padding:16px;background:#f0fdf4;border-radius:8px;">
      <h3 style="color:#059669;margin-bottom:12px;">Discovered Similar Papers</h3>
      <div id="expandedPapersList"></div>
    </div>
  </section>

  <!-- Foundation -->
  <section class="section" id="foundation">
    <div class="section-header">
      <span class="section-icon">📚</span>
      <span class="section-title">基础 Roadmap · 领域演进</span>
      <span class="section-count">{foundation_count} 个节点</span>
    </div>
    <div class="timeline">
{foundation_html}
    </div>
  </section>

  <!-- Frontier -->
  <section class="section" id="frontier">
    <div class="section-header">
      <span class="section-icon">🔬</span>
      <span class="section-title">前沿快照 · 同行评审视角</span>
      <span class="section-count">{frontier_count} 篇论文</span>
    </div>
    <div class="frontier-grid">
{frontier_html}
    </div>
  </section>

  <!-- Reading List -->
  <section class="section" id="reading">
    <div class="section-header">
      <span class="section-icon">📋</span>
      <span class="section-title">精选阅读清单</span>
      <span class="section-count">{reading_count} 篇</span>
    </div>
    <div class="reading-list">
{reading_html}
    </div>
  </section>

  <!-- Resources -->
  <section class="section" id="resources">
    <div class="section-header">
      <span class="section-icon">🌐</span>
      <span class="section-title">资源地图</span>
    </div>
    <div class="resources-grid">
{resources_html}
    </div>
  </section>

  <!-- Top Authors / Labs -->
  <section class="section" id="authors">
    <div class="section-header">
      <span class="section-icon">🏛️</span>
      <span class="section-title">领域强组 · 活跃研究者</span>
    </div>
    {top_authors_html}
  </section>

</div>

<div class="footer">
  <strong>FrontierPilot</strong> · "一个课题，从小白到专家" · 成长型知识库 · 生成时间：{generated_at}
</div>

<script>
mermaid.initialize({{ startOnLoad: true, theme: 'base', themeVariables: {{
  primaryColor: '#dbeafe', primaryTextColor: '#1e40af', primaryBorderColor: '#2563eb',
  lineColor: '#94a3b8', fontSize: '14px',
  nodeBorder: '#2563eb',
}}, securityLevel: 'loose' }});

// ── Interactive Knowledge Graph ──
const paperIndex = __PAPER_INDEX__;
let currentTooltipNodeId = null;

function showPaperTooltip(nodeId) {{
  const paper = paperIndex[nodeId];
  if (!paper) return;
  currentTooltipNodeId = nodeId;

  document.getElementById('tooltipTitle').textContent = paper.title;

  const authors = Array.isArray(paper.authors) ? paper.authors.slice(0,3).join(', ') : (paper.authors || '');
  const meta = [
    paper.year,
    paper.venue || '',
    paper.citation_count ? paper.citation_count.toLocaleString() + ' citations' : '',
    paper.avg_rating ? 'Rating: ' + paper.avg_rating : ''
  ].filter(Boolean).join(' · ');
  document.getElementById('tooltipMeta').textContent = [authors, meta].filter(Boolean).join(' | ');
  document.getElementById('tooltipAbstract').textContent = paper.abstract || 'No abstract available';

  const link = document.getElementById('tooltipLink');
  if (paper.url) {{
    link.href = paper.url;
    link.style.display = 'inline-flex';
  }} else {{
    link.style.display = 'none';
  }}

  const expandBtn = document.getElementById('tooltipExpandBtn');
  // Show Expand if we have any identifier; title-only fallback handled server-side
  expandBtn.style.display = (paper.ss_paper_id || paper.arxiv_id || paper.title) ? 'block' : 'none';

  document.getElementById('tooltipExpandStatus').style.display = 'none';
  document.getElementById('paperTooltip').style.display = 'block';
  document.getElementById('tooltipOverlay').style.display = 'block';
}}

function closePaperTooltip() {{
  document.getElementById('paperTooltip').style.display = 'none';
  document.getElementById('tooltipOverlay').style.display = 'none';
  currentTooltipNodeId = null;
}}

function chatAboutPaper(nodeId) {{
  const paper = paperIndex[nodeId];
  if (!paper) return;
  closePaperTooltip();
  const input = document.getElementById('chat-input');
  if (input) {{
    input.value = '\u5206\u6790\u8fd9\u7bc7\u8bba\u6587\uff1a' + paper.title;
    const chatTab = document.querySelector('.nav-item[onclick*="panel-chat"]');
    if (chatTab) chatTab.click();
    setTimeout(() => {{
      const btn = document.getElementById('chat-send-btn');
      if (btn) btn.click();
    }}, 100);
  }}
}}

function expandFromNode(nodeId) {{
  const paper = paperIndex[nodeId];
  if (!paper) return;

  const statusDiv = document.getElementById('tooltipExpandStatus');
  statusDiv.style.display = 'block';
  statusDiv.style.color = '#2563eb';
  statusDiv.textContent = '\u23f3 \u6b63\u5728\u53d1\u73b0\u76f8\u4f3c\u8bba\u6587...';

  const paperId = paper.ss_paper_id || (paper.arxiv_id ? 'arXiv:' + paper.arxiv_id : '');

  fetch('http://localhost:7779/command', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{message: 'expand_paper ' + paperId + ' ' + paper.title}})
  }})
  .then(r => r.json())
  .then(data => {{
    if (!data.id) throw new Error('no id');
    const evtSource = new EventSource('http://localhost:7779/stream?id=' + data.id);
    evtSource.onmessage = (e) => {{
      let event;
      try {{ event = JSON.parse(e.data); }} catch {{ return; }}
      if (event.type === 'step') {{
        statusDiv.textContent = event.text;
      }} else if (event.type === 'graph_update') {{
        appendNodesToGraph(event.new_papers, nodeId);
        statusDiv.style.color = '#059669';
        statusDiv.textContent = '\u2705 \u5df2\u53d1\u73b0 ' + event.new_papers.length + ' \u7bc7\u76f8\u4f3c\u8bba\u6587';
        evtSource.close();
      }} else if (event.type === 'done') {{
        if (statusDiv.textContent.indexOf('\u2705') === -1) {{
          statusDiv.style.color = '#6b7280';
          statusDiv.textContent = '\u672a\u627e\u5230\u76f8\u4f3c\u8bba\u6587\uff0c\u53ef\u80fd\u662f\u7f51\u7edc\u95ee\u9898\u6216 API \u9650\u5236';
        }}
        evtSource.close();
      }}
    }};
    evtSource.onerror = () => {{
      statusDiv.style.color = '#6b7280';
      statusDiv.textContent = '\u53d1\u73b0\u5931\u8d25\uff0c\u8bf7\u7a0d\u540e\u91cd\u8bd5';
      evtSource.close();
    }};
  }})
  .catch(() => {{
    statusDiv.style.color = '#6b7280';
    statusDiv.textContent = '\u6682\u65f6\u65e0\u6cd5\u8fde\u63a5\u52a9\u624b\u670d\u52a1\uff0c\u8bf7\u786e\u8ba4 chat_server.py \u6b63\u5728\u8fd0\u884c';
  }});
}}

function appendNodesToGraph(newPapers, sourceNodeId) {{
  newPapers.forEach(p => {{ paperIndex[p.node_id] = p; }});

  const expandList = document.getElementById('graphExpansionList');
  expandList.style.display = 'block';
  const list = document.getElementById('expandedPapersList');
  newPapers.forEach(p => {{
    list.insertAdjacentHTML('beforeend',
      '<div style="border-bottom:1px solid #d1fae5;padding:10px 0;">' +
      '<div style="font-weight:600;">' + p.title + ' (' + p.year + ')</div>' +
      '<div style="color:#6b7280;font-size:13px;">' + (p.authors||[]).slice(0,3).join(', ') + ' · ' + (p.citation_count||0) + ' citations</div>' +
      '<div style="color:#374151;font-size:13px;margin-top:4px;">' + (p.abstract_snippet||'') + '</div>' +
      (p.url ? '<a href="' + p.url + '" target="_blank" style="color:#2563eb;font-size:12px;">View paper</a>' : '') +
      '</div>'
    );
  }});
}}

// ── Tab / Panel switching ──
const viewMain = document.getElementById('view-main');
const panels = document.querySelectorAll('.view-panel');
const navItems = document.querySelectorAll('.nav-item');

function showMain(evt, anchorId) {{
  if (evt) evt.preventDefault();
  viewMain.style.display = 'block';
  panels.forEach(p => {{ p.style.display = 'none'; p.classList.remove('active'); }});
  navItems.forEach(n => n.classList.remove('active'));
  if (anchorId) {{
    const el = document.getElementById(anchorId);
    if (el) el.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
    const navLink = document.querySelector(`.nav-item[href="#${{anchorId}}"]`);
    if (navLink) navLink.classList.add('active');
  }}
}}

function showPanel(evt, panelId) {{
  if (evt) evt.preventDefault();
  viewMain.style.display = 'none';
  panels.forEach(p => {{ p.style.display = 'none'; p.classList.remove('active'); }});
  const panel = document.getElementById(panelId);
  if (panel) {{ panel.style.display = 'block'; panel.classList.add('active'); }}
  navItems.forEach(n => n.classList.remove('active'));
  const activeNav = document.querySelector(`.nav-item[onclick*="${{panelId}}"]`);
  if (activeNav) activeNav.classList.add('active');
  window.scrollTo({{ top: 0, behavior: 'smooth' }});
}}

// ── Nav active state on scroll (main view only) ──
const sections = document.querySelectorAll('#view-main .section');
const mainNavItems = Array.from(navItems).filter(n => !n.classList.contains('panel-tab'));
const observer = new IntersectionObserver((entries) => {{
  if (viewMain.style.display === 'none') return;
  entries.forEach(e => {{
    if (e.isIntersecting) {{
      mainNavItems.forEach(n => n.classList.remove('active'));
      const active = document.querySelector(`.nav-item[href="#${{e.target.id}}"]`);
      if (active) active.classList.add('active');
    }}
  }});
}}, {{ threshold: 0.2, rootMargin: '-60px 0px -60% 0px' }});
sections.forEach(s => observer.observe(s));

// ── Chat (智能助手) ──
const CHAT_SERVER = 'http://localhost:7779';
const TOPIC_NAME = '{topic_js}';
const chatMessages = document.getElementById('chat-messages');
const chatInput = document.getElementById('chat-input');
const chatSendBtn = document.getElementById('chat-send-btn');
const chatDot = document.getElementById('chat-dot');
const chatStatusText = document.getElementById('chat-status-text');
const chatRefreshHint = document.getElementById('chat-refresh-hint');

let serverOnline = false;
let currentEs = null;   // active EventSource

// ── 服务器心跳检测 ──
function checkServer() {{
  fetch(CHAT_SERVER + '/ping')
    .then(r => r.json())
    .then(() => {{
      if (!serverOnline) {{
        serverOnline = true;
        if (chatDot) chatDot.classList.add('online');
        if (chatStatusText) chatStatusText.textContent = 'FrontierPilot 助手已连接 · localhost:7779';
      }}
    }})
    .catch(() => {{
      serverOnline = false;
      if (chatDot) chatDot.classList.remove('online');
      if (chatStatusText) chatStatusText.textContent = '助手未连接 — 请先运行 chat_server.py';
    }});
}}
checkServer();
setInterval(checkServer, 8000);

// ── DOM 操作工具 ──
function removeWelcome() {{
  const w = chatMessages.querySelector('.chat-welcome');
  if (w) w.remove();
}}

function appendUserMsg(text, skipSave) {{
  removeWelcome();
  const wrap = document.createElement('div');
  wrap.className = 'chat-msg user';
  const av = document.createElement('div');
  av.className = 'chat-avatar'; av.textContent = '👤';
  const bub = document.createElement('div');
  bub.className = 'chat-bubble'; bub.textContent = text;
  wrap.appendChild(av); wrap.appendChild(bub);
  chatMessages.appendChild(wrap);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  if (!skipSave) saveChatMessage('user', text);
}}

function createAgentBubble() {{
  removeWelcome();
  const wrap = document.createElement('div');
  wrap.className = 'chat-msg agent';
  const av = document.createElement('div');
  av.className = 'chat-avatar'; av.textContent = '🤖';
  const bub = document.createElement('div');
  bub.className = 'chat-bubble';
  wrap.appendChild(av); wrap.appendChild(bub);
  chatMessages.appendChild(wrap);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  return bub;
}}

function createStepLine() {{
  const line = document.createElement('div');
  line.style.cssText = 'font-size:11px;color:var(--text-muted);margin:2px 0 2px 40px;line-height:1.6';
  chatMessages.appendChild(line);
  return line;
}}

function enableInput() {{
  if (chatSendBtn) chatSendBtn.disabled = false;
  if (chatInput) {{ chatInput.disabled = false; chatInput.focus(); }}
}}

// ── Chat history (localStorage, UI-only) ──
const CHAT_HISTORY_KEY = 'fp_chat_' + TOPIC_NAME.replace(/\s+/g, '_');
const MAX_HISTORY = 40;

function saveChatMessage(role, content) {{
  try {{
    const hist = JSON.parse(localStorage.getItem(CHAT_HISTORY_KEY) || '[]');
    hist.push({{ role, content, ts: Date.now() }});
    if (hist.length > MAX_HISTORY) hist.splice(0, hist.length - MAX_HISTORY);
    localStorage.setItem(CHAT_HISTORY_KEY, JSON.stringify(hist));
  }} catch(e) {{}}
}}

function loadChatHistory() {{
  try {{
    const hist = JSON.parse(localStorage.getItem(CHAT_HISTORY_KEY) || '[]');
    if (!hist.length) return;
    hist.forEach(m => {{
      if (m.role === 'user') appendUserMsg(m.content, true);
      else if (m.role === 'assistant') {{
        const bub = createAgentBubble();
        bub.textContent = m.content;
      }}
    }});
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }} catch(e) {{}}
}}

// ── SSE 流式接收 ──
function subscribeStream(cmdId, userMsg) {{
  if (currentEs) {{ currentEs.close(); currentEs = null; }}

  const agentBubble = createAgentBubble();
  agentBubble.innerHTML = '<div class="thinking-dots"><span></span><span></span><span></span></div>';
  let firstToken = true;
  let stepLine = null;
  let fullText = '';

  const es = new EventSource(CHAT_SERVER + '/stream?id=' + cmdId);
  currentEs = es;

  es.onmessage = (e) => {{
    let event;
    try {{ event = JSON.parse(e.data); }} catch {{ return; }}

    if (event.type === 'step') {{
      // Show progress step below previous step (small muted text)
      if (!stepLine || stepLine.textContent) stepLine = createStepLine();
      stepLine.textContent = event.text;
      chatMessages.scrollTop = chatMessages.scrollHeight;

    }} else if (event.type === 'token') {{
      if (firstToken) {{
        agentBubble.innerHTML = '';   // clear "..."
        firstToken = false;
      }}
      fullText += event.text;
      // Strip any fallback [ACTION:xxx] markers before display
      agentBubble.textContent = fullText.replace(/\[ACTION:[^\]]+\]/g, '').trimEnd();
      chatMessages.scrollTop = chatMessages.scrollHeight;

    }} else if (event.type === 'done') {{
      es.close(); currentEs = null;
      if (firstToken) agentBubble.innerHTML = '✅ 处理完成';
      // Save clean text to localStorage for UI history
      const cleanText = fullText.replace(/\[ACTION:[^\]]+\]/g, '').trim();
      if (cleanText) saveChatMessage('assistant', cleanText);
      if (event.action === 'html_updated' && chatRefreshHint) {{
        chatRefreshHint.style.display = 'block';
      }}
      enableInput();
    }}
  }};

  es.onerror = () => {{
    es.close(); currentEs = null;
    if (firstToken) agentBubble.textContent = '❌ 连接断开，请检查 chat_server.py 是否运行中。';
    enableInput();
  }};
}}

// ── 发送消息 ──
function sendChat() {{
  if (!chatInput) return;
  const msg = chatInput.value.trim();
  if (!msg) return;

  if (!serverOnline) {{
    appendUserMsg(msg);
    const bub = createAgentBubble();
    bub.textContent = '⚠️ 助手未连接，请先运行：python3 chat_server.py --data <data.json>';
    return;
  }}

  appendUserMsg(msg);
  chatInput.value = '';
  chatInput.style.height = 'auto';
  if (chatSendBtn) chatSendBtn.disabled = true;
  if (chatInput) chatInput.disabled = true;

  fetch(CHAT_SERVER + '/command', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify({{ message: msg, topic: TOPIC_NAME }}),
  }})
    .then(r => r.json())
    .then(data => {{
      if (data.id) subscribeStream(data.id, msg);
      else throw new Error('no id');
    }})
    .catch(() => {{
      const bub = createAgentBubble();
      bub.textContent = '❌ 发送失败，请检查 chat_server.py 是否在运行。';
      enableInput();
    }});
}}

function fillInput(text) {{
  if (!chatInput) return;
  chatInput.value = text;
  chatInput.focus();
  // auto-resize
  chatInput.style.height = 'auto';
  chatInput.style.height = chatInput.scrollHeight + 'px';
}}

// Auto-resize textarea
if (chatInput) {{
  chatInput.addEventListener('input', () => {{
    chatInput.style.height = 'auto';
    chatInput.style.height = Math.min(chatInput.scrollHeight, 120) + 'px';
  }});
  chatInput.addEventListener('keydown', (e) => {{
    if (e.key === 'Enter' && !e.shiftKey) {{
      e.preventDefault();
      sendChat();
    }}
  }});
}}

// Load chat history from localStorage (UI restore on page reload)
loadChatHistory();

// ── P0: Email outreach (✉️ button on author cards) ──
function sendEmailRequest(authorName) {{
  const input = document.getElementById('chat-input');
  if (input) input.value = '帮我给 ' + authorName + ' 写一封邮件';
  const chatTab = document.querySelector('.nav-item[onclick*="panel-chat"]');
  if (chatTab) chatTab.click();
  setTimeout(() => {{
    const btn = document.getElementById('chat-send-btn');
    if (btn) btn.click();
  }}, 100);
}}

// ── P1: Pending Actions Approval Queue ──
function _platformIcon(p) {{ return ({{xiaohongshu:'📕',wechat:'💬',github:'💻'}})[p] || '🌐'; }}
function _actionLabel(a) {{ return ({{follow:'关注',join_group:'加群',star_repo:'⭐ 仓库'}})[a] || a; }}

function loadPendingActions() {{
  fetch('http://localhost:7779/pending_actions/list')
    .then(r => r.json())
    .then(data => {{
      const actions = data.actions || [];
      const pending = actions.filter(a => a.status === 'pending');
      const section = document.getElementById('pendingActionsSection');
      const list = document.getElementById('pendingActionsList');
      if (!section || !list) return;
      if (pending.length === 0) {{ section.style.display = 'none'; return; }}
      section.style.display = 'block';
      list.innerHTML = pending.map(a => `
        <div style="border:1px solid #d1fae5;border-radius:8px;padding:16px;margin-bottom:12px;background:#f0fdf4;" data-id="${{a.id}}">
          <div style="display:flex;justify-content:space-between;align-items:start;">
            <div>
              <span style="font-weight:600;">${{_platformIcon(a.platform)}} ${{a.target_name}}</span>
              <span style="margin-left:8px;color:#6b7280;font-size:12px;">${{_actionLabel(a.action)}}</span>
            </div>
            <div>
              <button onclick="approveAction('${{a.id}}')" style="background:#059669;color:white;border:none;border-radius:6px;padding:6px 14px;cursor:pointer;margin-right:6px;">✅ 批准</button>
              <button onclick="rejectAction('${{a.id}}')" style="background:#ef4444;color:white;border:none;border-radius:6px;padding:6px 14px;cursor:pointer;">❌ 拒绝</button>
            </div>
          </div>
          <div style="margin-top:8px;color:#374151;font-size:14px;">理由：${{a.reason || ''}}</div>
          ${{a.draft_message ? `<div style="margin-top:8px;"><label style="font-size:12px;color:#6b7280;">申请消息：</label><textarea id="dm_${{a.id}}" style="width:100%;margin-top:4px;padding:6px;border:1px solid #d1d5db;border-radius:4px;font-size:13px;">${{a.draft_message}}</textarea><button onclick="saveMessage('${{a.id}}')" style="margin-top:4px;background:#2563eb;color:white;border:none;border-radius:4px;padding:4px 10px;cursor:pointer;font-size:12px;">保存</button></div>` : ''}}
          ${{a.target_url ? `<div style="margin-top:6px;"><a href="${{a.target_url}}" target="_blank" style="color:#2563eb;font-size:12px;">🔗 查看链接</a></div>` : ''}}
        </div>
      `).join('');
    }})
    .catch(() => {{
      const section = document.getElementById('pendingActionsSection');
      if (section) section.style.display = 'none';
    }});
}}

function approveAction(id) {{
  fetch('http://localhost:7779/pending_actions/approve', {{
    method: 'POST', headers: {{'Content-Type': 'application/json'}}, body: JSON.stringify({{id}})
  }}).then(() => loadPendingActions());
}}

function rejectAction(id) {{
  fetch('http://localhost:7779/pending_actions/reject', {{
    method: 'POST', headers: {{'Content-Type': 'application/json'}}, body: JSON.stringify({{id}})
  }}).then(() => loadPendingActions());
}}

function saveMessage(id) {{
  const el = document.getElementById('dm_' + id);
  if (!el) return;
  fetch('http://localhost:7779/pending_actions/edit', {{
    method: 'POST', headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{id, draft_message: el.value}})
  }}).then(() => alert('已保存'));
}}

// ── P2: Reviewer Consensus Heatmap ──
const reviewerConsensus = {reviewer_consensus_json};

let heatmapInited = false;
function initHeatmap() {{
  if (heatmapInited) return;
  heatmapInited = true;

  const tbody = document.getElementById('heatmapTableBody');
  if (!tbody || !reviewerConsensus || !reviewerConsensus.papers) return;

  reviewerConsensus.papers.forEach(p => {{
    const consensusLevel = p.rating_std < 1.0 ? '🟢 高度一致' : p.rating_std < 2.0 ? '🟡 基本一致' : '🔴 存在争议';
    const ratingColor = p.avg_rating >= 7 ? '#059669' : p.avg_rating >= 5 ? '#d97706' : '#dc2626';
    const dots = (p.scores || []).map(s => {{
      const h = Math.round((s / 10) * 120);
      return `<span style="display:inline-block;width:20px;height:20px;border-radius:50%;background:hsl(${{h}},70%,50%);margin:2px;vertical-align:middle;" title="${{s}}"></span>`;
    }}).join('');

    tbody.insertAdjacentHTML('beforeend', `
      <tr style="border-bottom:1px solid #f3f4f6;">
        <td style="padding:10px 16px;max-width:280px;font-weight:500;">${{p.title}}</td>
        <td style="padding:10px 16px;text-align:center;font-weight:700;color:${{ratingColor}};font-size:18px;">${{p.avg_rating || 'N/A'}}</td>
        <td style="padding:10px 16px;text-align:center;color:#6b7280;">${{p.rating_std || '—'}}</td>
        <td style="padding:10px 16px;">${{dots || '<span style="color:#9ca3af">暂无评分</span>'}}</td>
        <td style="padding:10px 16px;">${{consensusLevel}}</td>
      </tr>
    `);
  }});

  const grid = document.getElementById('themeClusterGrid');
  if (grid && reviewerConsensus.theme_clusters) {{
    const colors = {{positive:'#ecfdf5', mixed:'#fffbeb', negative:'#fef2f2'}};
    const borders = {{positive:'#059669', mixed:'#d97706', negative:'#dc2626'}};
    reviewerConsensus.theme_clusters.forEach(t => {{
      grid.insertAdjacentHTML('beforeend', `
        <div style="background:${{colors[t.sentiment]||'#f9fafb'}};border:1px solid ${{borders[t.sentiment]||'#e5e7eb'}};border-radius:8px;padding:16px;">
          <div style="font-weight:600;color:#374151;margin-bottom:4px;">${{t.theme}}</div>
          <div style="font-size:12px;color:#6b7280;">${{t.sentiment === 'positive' ? '✅ 普遍认可' : t.sentiment === 'negative' ? '⚠️ 普遍质疑' : '⚡ 存在争议'}}</div>
        </div>
      `);
    }});
  }}
}}

// Wire initHeatmap to panel click
document.addEventListener('DOMContentLoaded', () => {{
  const heatmapNav = document.querySelector('.nav-item[onclick*="panel-heatmap"]');
  if (heatmapNav) heatmapNav.addEventListener('click', initHeatmap);
}});
</script>
</body>
</html>"""


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_authors(authors) -> list:
    """Accept str or list[str] and always return list[str]."""
    if isinstance(authors, list):
        return authors
    if isinstance(authors, str) and authors:
        return [authors]
    return []


def _escape(s: str) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _js_safe(s: str) -> str:
    """Escape a string for safe use as a JS string literal (single-quoted context)."""
    return str(s).replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"').replace("\n", "").replace("\r", "")


def make_node_id(year: int, title: str, prefix: str = "N") -> str:
    """Generate a Mermaid-compatible node ID. Must be consistent wherever used."""
    slug = re.sub(r"[^a-zA-Z0-9]", "_", title.split(":")[0].strip())[:12]
    slug = re.sub(r"_+", "_", slug).strip("_")
    return f"{prefix}{year}_{slug}"


def build_paper_index(foundation: list, frontier: list) -> dict:
    """Build paper_index dict: node_id → paper metadata for JS tooltip."""
    index = {}
    for paper in foundation:
        nid = paper.get("node_id")
        if not nid:
            continue
        index[nid] = {
            "title": paper.get("title", ""),
            "authors": _normalize_authors(paper.get("authors", [])),
            "year": paper.get("year", 2000),
            "citation_count": paper.get("citation_count", 0),
            "venue": paper.get("venue", ""),
            "arxiv_id": paper.get("arxiv_id", ""),
            # paperId (SS field name) is a fallback source for ss_paper_id
            "ss_paper_id": paper.get("ss_paper_id", "") or paper.get("paperId", ""),
            "abstract": (paper.get("abstract") or paper.get("description", ""))[:300],
            "url": paper.get("url", ""),
            "type": "foundation",
        }
    for paper in frontier:
        nid = paper.get("node_id")
        if not nid:
            continue
        # Build abstract with broad fallback chain: abstract → description → review strengths
        abstract_text = paper.get("abstract") or paper.get("description") or ""
        if not abstract_text:
            reviews = paper.get("reviews") or []
            if reviews and reviews[0].get("strengths"):
                abstract_text = reviews[0]["strengths"]
        index[nid] = {
            "title": paper.get("title", ""),
            "authors": _normalize_authors(paper.get("authors", [])),
            "year": paper.get("year", 2024),
            "citation_count": paper.get("citation_count", 0),
            "venue": paper.get("venue", ""),
            "arxiv_id": paper.get("arxiv_id", ""),
            "ss_paper_id": paper.get("ss_paper_id", "") or paper.get("paperId", ""),
            "abstract": abstract_text[:300],
            "url": paper.get("url", ""),
            "type": "frontier",
            "avg_rating": paper.get("avg_rating"),
        }
    return index


def _extract_mermaid_node_ids(mermaid_str: str) -> set:
    """Return all node IDs actually defined in a mermaid flowchart string."""
    _KW = {'flowchart', 'subgraph', 'style', 'classDef', 'end',
           'LR', 'TD', 'BT', 'RL', 'TB', 'click', 'call'}
    ids = set()
    for m in re.finditer(r'\b([A-Za-z_][A-Za-z0-9_]*)\s*[\[({]', mermaid_str):
        ids.add(m.group(1))
    for m in re.finditer(r'\b([A-Za-z_][A-Za-z0-9_]*):::', mermaid_str):
        ids.add(m.group(1))
    return ids - _KW


def _reconcile_paper_index(paper_index: dict, mermaid_str: str) -> dict:
    """Re-key paper_index so keys match actual mermaid node IDs.

    When graph_mermaid is hand-written by LLM, its node IDs (e.g. N2024_Fiddler)
    may differ from auto-generated ones (e.g. N2024_CPU_GPU_Or). This function
    remaps paper_index entries to the correct mermaid node IDs using year + title
    word overlap heuristics.
    """
    graph_ids = _extract_mermaid_node_ids(mermaid_str)
    if not graph_ids:
        return paper_index

    # Entries already matching a mermaid node — keep as-is
    matched = {k: v for k, v in paper_index.items() if k in graph_ids}
    unmatched_papers = {k: v for k, v in paper_index.items() if k not in graph_ids}
    unmapped_graph_ids = graph_ids - set(matched.keys())

    for gid in sorted(unmapped_graph_ids):
        year_m = re.search(r'(\d{4})', gid)
        if not year_m:
            continue
        year = int(year_m.group(1))
        same_year = [(k, v) for k, v in unmatched_papers.items()
                     if v.get('year') == year]
        if not same_year:
            continue

        gid_lower = gid.lower()

        def _score(item):
            words = re.sub(r'[^a-z0-9]', ' ',
                           item[1].get('title', '').lower()).split()
            return sum(1 for w in words if len(w) > 3 and w[:6] in gid_lower)

        best_k, best_v = max(same_year, key=_score)
        matched[gid] = best_v
        del unmatched_papers[best_k]

    return matched


def add_click_directives(mermaid_str: str, paper_index: dict) -> str:
    """Append Mermaid click directives so clicking a node triggers showPaperTooltip()."""
    click_lines = []
    for node_id in paper_index:
        click_lines.append(f'  click {node_id} call showPaperTooltip("{node_id}")')
    return mermaid_str + "\n" + "\n".join(click_lines)


# ─────────────────────────────────────────────────────────────────────────────
# Renderers
# ─────────────────────────────────────────────────────────────────────────────

def render_field_overview(overview_text: str) -> str:
    if not overview_text:
        return """    <div class="overview-placeholder">
      📊 FrontierPilot 将在探索时自动生成该领域的专家视角综述<br>
      <span style="font-size:12px;margin-top:8px;display:block">包括：本领域核心问题、2024年共识与争议、新手最应关注的内容</span>
    </div>"""
    # Replace newlines with paragraph breaks
    paragraphs = overview_text.strip().split("\n")
    html_paras = "".join(f"<p style='margin-bottom:12px'>{_escape(p)}</p>" for p in paragraphs if p.strip())
    return f"""    <div class="overview-card">
      <div class="overview-text">{html_paras}</div>
    </div>"""


def render_foundation(items: list) -> str:
    parts = []
    for item in items:
        is_key = item.get("is_key", False)
        title = _escape(item.get("title", ""))
        url = item.get("url", "#")
        year = item.get("year", "")
        authors = _escape(", ".join(_normalize_authors(item.get("authors", []))))
        description = _escape(item.get("description", ""))
        problem_solved = _escape(item.get("problem_solved", ""))
        problem_left = _escape(item.get("problem_left", ""))
        citation_count = item.get("citation_count")
        key_class = " key" if is_key else ""
        key_badge = '<span class="key-badge">必读</span>' if is_key else ""
        pills = ""
        if problem_solved:
            pills += f'<span class="pill pill-solved">✅ {problem_solved}</span>'
        if problem_left:
            pills += f'<span class="pill pill-left">⚠️ 遗留：{problem_left}</span>'
        if citation_count:
            count_str = f"{citation_count // 1000}k" if citation_count >= 1000 else str(citation_count)
            pills += f'<span class="pill pill-cite">⭐ {count_str} 引用</span>'
        parts.append(f"""      <div class="timeline-item{key_class}">
        <div class="timeline-card{key_class}">
          <div class="timeline-year">{year}</div>
          <div class="timeline-title"><a href="{url}" target="_blank">{title}</a>{key_badge}</div>
          <div class="timeline-meta">{authors}</div>
          <div style="font-size:13px;color:var(--text-muted)">{description}</div>
          {'<div class="timeline-pills">' + pills + '</div>' if pills else ''}
        </div>
      </div>""")
    return "\n".join(parts)


def render_frontier(items: list) -> str:
    parts = []
    for item in items:
        title = _escape(item.get("title", ""))
        url = item.get("url", "#")
        venue = _escape(item.get("venue", ""))
        year = item.get("year", "")
        avg_rating = item.get("avg_rating")
        citation_count = item.get("citation_count")  # systems-topic fallback
        if avg_rating:
            rating_str = "{:.1f}/10".format(avg_rating)
            if avg_rating >= 7:
                rating_class = "high"
            elif avg_rating >= 5:
                rating_class = "mid"
            else:
                rating_class = "low"
        elif citation_count:
            cit_str = "{:.1f}k".format(citation_count / 1000) if citation_count >= 1000 else str(citation_count)
            rating_str = "{} citations".format(cit_str)
            rating_class = "cite"
        else:
            rating_str = "N/A"
            rating_class = ""
        reviews_html = ""
        for rev in item.get("reviews", []):
            rating = _escape(rev.get("rating", ""))
            strengths = _escape(rev.get("strengths", ""))
            weaknesses = _escape(rev.get("weaknesses", ""))
            related = rev.get("related_work", [])
            related_html = ""
            if related:
                tags = "".join(f'<span class="related-tag">📎 {_escape(r)}</span>' for r in related)
                related_html = f'<div class="review-related"><div class="review-related-label">🔗 Reviewer 推荐比较：</div><div class="related-tags">{tags}</div></div>'
            reviews_html += f"""          <div class="review-item">
            <div class="review-rating">Reviewer · Rating {rating}</div>
            {'<div class="review-pro">✅ ' + strengths[:200] + '</div>' if strengths else ''}
            {'<div class="review-con">⚠️ ' + weaknesses[:200] + '</div>' if weaknesses else ''}
            {related_html}
          </div>"""
        parts.append(f"""      <div class="frontier-card">
        <div class="frontier-card-header">
          <div class="frontier-title"><a href="{url}" target="_blank">{title}</a>
            <div style="font-size:12px;color:var(--text-muted);margin-top:3px">{venue} {year}</div>
          </div>
          <div class="rating-badge {rating_class}">⭐ {rating_str}</div>
        </div>
        <div class="reviews-wrap">
{reviews_html}
        </div>
      </div>""")
    return "\n".join(parts)


def render_reading_list(items: list) -> str:
    parts = []
    type_map = {
        "foundation": ("type-foundation", "基础"),
        "frontier": ("type-frontier", "前沿"),
        "recommended": ("type-recommended", "推荐"),
    }
    for i, item in enumerate(items, 1):
        title = _escape(item.get("title", ""))
        url = item.get("url", "#")
        reason = _escape(item.get("reason", ""))
        t = item.get("type", "foundation")
        cls, label = type_map.get(t, ("type-foundation", t))
        parts.append(f"""      <div class="reading-item">
        <div class="reading-num">{i}</div>
        <div class="reading-body">
          <div class="reading-title"><a href="{url}" target="_blank">{title}</a></div>
          {'<div class="reading-reason">' + reason + '</div>' if reason else ''}
        </div>
        <span class="reading-type {cls}">{label}</span>
      </div>""")
    return "\n".join(parts)


def render_resources(resources: dict) -> str:
    parts = []

    # GitHub
    github = resources.get("github", [])
    if github:
        items_html = ""
        for r in github:
            name = _escape(r.get("name", ""))
            stars = _escape(str(r.get("stars", "")))
            desc = _escape(r.get("description", ""))
            url = r.get("url", "#")
            items_html += f"""        <div class="resource-item">
          <div class="resource-name"><a href="{url}" target="_blank">🐙 {name}</a></div>
          <div class="resource-meta"><span class="stars">⭐ {stars}</span><span>{desc[:60]}</span></div>
        </div>"""
        parts.append(f"""      <div class="resource-section">
        <div class="resource-section-title">💻 GitHub 开源实现</div>
{items_html}
      </div>""")

    # Bilibili
    bilibili = resources.get("bilibili", [])
    if bilibili:
        items_html = ""
        for v in bilibili:
            title = _escape(v.get("title", ""))
            url = v.get("url", "#")
            views = v.get("view_count", 0)
            view_str = f"{views // 10000}万" if views > 10000 else str(views)
            items_html += f"""        <div class="resource-item">
          <div class="resource-name"><a href="{url}" target="_blank">📺 {title}</a></div>
          <div class="resource-meta"><span>▶ {view_str} 播放</span></div>
        </div>"""
        parts.append(f"""      <div class="resource-section">
        <div class="resource-section-title">📺 Bilibili 中文教程</div>
{items_html}
      </div>""")

    # WeChat
    wechat = resources.get("wechat", [])
    if wechat:
        items_html = ""
        for a in wechat:
            title = _escape(a.get("title", ""))
            url = a.get("url", "#")
            items_html += f"""        <div class="resource-item">
          <div class="resource-name"><a href="{url}" target="_blank">📰 {title}</a></div>
        </div>"""
        parts.append(f"""      <div class="resource-section">
        <div class="resource-section-title">📰 微信公众号文章</div>
{items_html}
      </div>""")

    return "\n".join(parts)


def render_top_authors(authors: list) -> str:
    if not authors:
        return """    <div class="authors-placeholder">
      🏛️ FrontierPilot 将在探索时自动识别该领域最活跃的研究者和课题组<br>
      <span style="font-size:12px;margin-top:8px;display:block">包括：PI 姓名、机构、代表作、近期研究方向、学术主页链接</span>
    </div>"""
    parts = []
    for i, author in enumerate(authors[:6], 1):
        name = _escape(author.get("name", ""))
        institution = _escape(author.get("institution", ""))
        papers_count = author.get("papers_count", "")
        recent_work = _escape(author.get("recent_work", ""))
        url = author.get("url", "#")
        count_html = ""
        if papers_count:
            count_html = f'<div class="author-count">{papers_count}<span>论文</span></div>'
        email_btn = f'<button data-name="{name}" onclick="sendEmailRequest(this.dataset.name)" style="float:right;background:#2563eb;color:white;border:none;border-radius:6px;padding:4px 10px;cursor:pointer;font-size:12px;margin-left:8px;">✉️ 写信联系</button>'
        parts.append(f"""    <div class="author-card">
      <div class="author-rank">#{i}</div>
      <div class="author-body">
        <div class="author-name"><a href="{url}" target="_blank">{name}</a>{email_btn}</div>
        <div class="author-institution">🏛️ {institution}</div>
        {'<div class="author-recent">近期：' + recent_work + '</div>' if recent_work else ''}
      </div>
      {count_html}
    </div>""")
    return f'    <div class="authors-grid">\n' + "\n".join(parts) + "\n    </div>"


def _make_qr_base64(link: str) -> str:
    """Generate a QR code PNG from link, return as base64 data URI. Returns '' on failure."""
    try:
        import qrcode
        qr = qrcode.QRCode(box_size=6, border=3)
        qr.add_data(link)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()
        return f"data:image/png;base64,{b64}"
    except Exception:
        return ""


def render_social_actions(actions: list) -> str:
    """Render social_actions array as a timeline for the 社交行动 panel."""
    if not actions:
        return """  <div class="updates-placeholder">
    <div class="updates-placeholder-icon">🌐</div>
    <div class="updates-placeholder-text">社交代理尚未运行</div>
    <div class="updates-placeholder-hint">
      在 OpenClaw 中输入<br>
      <code>帮我在小红书找 [topic] 领域专家并关注</code>
    </div>
  </div>"""

    status_labels = {
        "done": ("done", "已完成"),
        "followed": ("followed", "已关注"),
        "ready": ("ready", "待确认"),
        "skipped": ("skipped", "已跳过"),
        "demo": ("demo", "演示"),
        "qr_found": ("ready", "已就绪"),
    }

    parts = []
    for action in actions:
        platform = action.get("platform", "")
        act = action.get("action", "")
        status = action.get("status", "done")
        timestamp = _escape(action.get("timestamp", ""))
        dot_cls, tag_label = status_labels.get(status, ("done", status))

        # Build summary line
        if act == "search":
            query = _escape(action.get("query", ""))
            count = action.get("result_count", 0)
            summary = f"小红书搜索「{query}」→ 找到 {count} 篇相关帖子"
            reason = ""
            extra_html = ""

        elif act == "follow":
            name = _escape(action.get("target_name", ""))
            reason_raw = _escape(action.get("reason", ""))
            url = action.get("target_url", "#")
            summary = f'关注用户 <a href="{url}" target="_blank" style="color:var(--social)">{name}</a>'
            reason = reason_raw
            extra_html = ""

        elif act == "qr_found":
            group_name = _escape(action.get("group_name", ""))
            weixin_link = action.get("weixin_link", "")
            draft = _escape(action.get("draft_message", ""))
            source_url = action.get("source_url", "")
            summary = f'发现微信群「{group_name}」· QR 已解码'
            # Source: plain text only (xiaohongshu links require app, not browser)
            reason = f'来源：小红书帖子 · {_escape(source_url.split("/")[-1][:16]) if source_url else ""}' if source_url else ""
            draft_box = f'<div class="social-draft-box">💬 入群申请语（已就绪）：{draft}</div>' if draft else ""
            # Generate QR code from weixin_link for desktop scanning
            qr_html = ""
            if weixin_link:
                qr_src = _make_qr_base64(weixin_link)
                if qr_src:
                    qr_html = f'''<div style="display:flex;align-items:flex-start;gap:16px;margin-top:10px">
      <img src="{qr_src}" style="width:120px;height:120px;border:1px solid var(--border);border-radius:8px;flex-shrink:0" alt="微信群二维码">
      <div style="font-size:12px;color:var(--text-muted);line-height:1.8;padding-top:4px">
        📱 用手机微信扫码加群<br>
        <span style="font-size:11px">或点击</span>
        <a class="social-btn" href="{_escape(weixin_link)}" style="font-size:11px;padding:2px 8px">打开微信</a>
      </div>
    </div>'''
            copy_btn = f'<button class="social-btn" onclick="navigator.clipboard.writeText(\'{draft.replace(chr(39), chr(92)+chr(39))}\')" title="复制申请语">📋 复制申请语</button>' if draft else ""
            actions_row = f'<div class="social-actions-row">{copy_btn}</div>' if copy_btn else ""
            extra_html = f'{draft_box}{qr_html}{actions_row}'

        else:
            summary = _escape(str(action))
            reason = ""
            extra_html = ""

        parts.append(f"""  <div class="social-action">
    <div class="social-dot {dot_cls}"></div>
    <div class="social-body">
      <div class="social-time">{timestamp} · {_escape(platform)}</div>
      <div class="social-summary">{summary}</div>
      {'<div class="social-reason">' + reason + '</div>' if reason else ''}
      {extra_html}
    </div>
    <span class="social-status-tag tag-{dot_cls}">{tag_label}</span>
  </div>""")

    return f'  <div class="social-timeline">\n' + "\n".join(parts) + "\n  </div>"


def render_latest_updates(updates: list) -> str:
    if not updates:
        return """  <div class="updates-placeholder">
    <div class="updates-placeholder-icon">🔔</div>
    <div class="updates-placeholder-text">OpenClaw 将定期监测最新动态</div>
    <div class="updates-placeholder-hint">
      当有新论文发表时，内容将自动追加到此处。<br><br>
      触发方式：在 OpenClaw 中输入<br>
      <code>帮我更新 [topic] 的最新动态</code>
    </div>
  </div>"""

    # Group updates by their update_batch (if field exists) or date prefix
    parts = []
    for update in updates:
        date = _escape(update.get("date", ""))
        title = _escape(update.get("title", ""))
        url = update.get("url", "#")
        summary = _escape(update.get("summary", ""))
        source = _escape(update.get("source", "arXiv"))
        parts.append(f"""  <div class="update-item">
    <div class="update-date">📅 {date} · {source}</div>
    <div class="update-title"><a href="{url}" target="_blank">{title}</a></div>
    {'<div class="update-summary">' + summary + '</div>' if summary else ''}
  </div>""")
    return "\n".join(parts)


def default_graph(topic: str, foundation: list, paper_clusters: list = None) -> str:
    """Generate a Mermaid flowchart from foundation papers.

    If paper_clusters is provided (from Step 2.5 school clustering), renders
    nodes grouped into labeled subgraph blocks with distinct background colors.
    Falls back to a flat linear chain when no clusters are given.
    """
    lines = [
        "flowchart LR",
        "  classDef foundation fill:#dbeafe,stroke:#2563eb,color:#1e40af",
        "  classDef key fill:#2563eb,stroke:#1e40af,color:white",
        "  classDef frontier fill:#f5f3ff,stroke:#7c3aed,color:#4c1d95",
        "  classDef recommended fill:#dcfce7,stroke:#059669,color:#166534",
    ]
    if not foundation:
        lines.append(f'  A["{topic}"]:::key')
        return "\n".join(lines)

    # Build node definitions keyed by node_id
    node_defs = {}
    for item in foundation[:8]:
        year = item.get("year", 2000)
        title = item.get("title", "")
        is_key = item.get("is_key", False)
        citation_count = item.get("citation_count")
        node_id = item.get("node_id") or make_node_id(year, title, "N")
        item["node_id"] = node_id  # write back for downstream
        label = f"{year} {title[:22]}"
        if citation_count and citation_count >= 1000:
            label += f"\\n⭐ {citation_count // 1000}k"
        cls = "key" if is_key else "foundation"
        node_defs[node_id] = (label, cls)

    if paper_clusters:
        # Subgraph layout: each cluster becomes a named subgraph block
        cluster_icons = ["🔵", "🟣", "🟢", "🟠"]
        clustered_ids = set()
        for i, cluster in enumerate(paper_clusters):
            icon = cluster_icons[i % len(cluster_icons)]
            sg_id = cluster.get("id", f"sg{i}")
            sg_name = cluster.get("name", f"Cluster {i+1}")
            sg_style = cluster.get("subgraph_style", "fill:#f8fafc,stroke:#94a3b8")
            lines.append(f'\n  subgraph {sg_id}["{icon} {sg_name}"]')
            lines.append(f"    style {sg_id} {sg_style}")
            for nid in cluster.get("paper_node_ids", []):
                if nid in node_defs:
                    label, cls = node_defs[nid]
                    lines.append(f'    {nid}["{label}"]:::{cls}')
                    clustered_ids.add(nid)
            lines.append("  end")
        # Render any nodes not assigned to a cluster
        unclustered = [nid for nid in node_defs if nid not in clustered_ids]
        for nid in unclustered:
            label, cls = node_defs[nid]
            lines.append(f'  {nid}["{label}"]:::{cls}')
    else:
        # Fallback: flat linear chain (original behaviour)
        prev = None
        for node_id, (label, cls) in node_defs.items():
            if prev:
                lines.append(f'  {prev} --> {node_id}["{label}"]:::{cls}')
            else:
                lines.append(f'  {node_id}["{label}"]:::{cls}')
            prev = node_id

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Reviewer Consensus (P2)
# ─────────────────────────────────────────────────────────────────────────────

def build_reviewer_consensus(frontier: list) -> dict:
    """
    Build reviewer consensus data from frontier papers.
    Returns: {"papers": [...], "theme_clusters": [...]}
    """
    import statistics
    import re as _re
    from collections import Counter

    result_papers = []
    all_weaknesses = []

    for paper in frontier:
        reviews = paper.get("reviews", [])
        scores = []
        for r in reviews:
            try:
                score_str = str(r.get("rating", "0"))
                score = float(score_str.split(":")[0].split("/")[0].strip())
                if 1 <= score <= 10:
                    scores.append(score)
            except (ValueError, AttributeError):
                pass

        avg = round(statistics.mean(scores), 1) if scores else 0
        std = round(statistics.stdev(scores), 2) if len(scores) >= 2 else 0

        themes = []
        for r in reviews:
            w = r.get("weaknesses", "")
            if w:
                all_weaknesses.append(w[:200])
                for kw in ["scalability", "efficiency", "generalization", "theory", "experiments",
                           "novelty", "clarity", "baselines", "ablation", "reproducibility",
                           "可扩展性", "效率", "泛化", "理论", "实验", "新颖性"]:
                    if kw.lower() in w.lower():
                        themes.append(kw)

        result_papers.append({
            "title": paper.get("title", "Unknown")[:50],
            "avg_rating": avg,
            "rating_std": std,
            "scores": scores,
            "key_themes": list(set(themes))[:4],
        })

    # Theme clustering via LLM → fallback to keyword frequency
    theme_clusters = []
    if all_weaknesses:
        prompt = (
            "Given these reviewer weakness comments from ML papers:\n"
            + "\n".join(all_weaknesses[:5])
            + "\n\nIdentify 3-4 recurring critique themes. For each theme give: "
            "theme name (3-5 words), sentiment: positive|mixed|negative. "
            'Respond as JSON array: [{"theme": "...", "sentiment": "..."}]'
        )
        try:
            raw = _call_llm_once(prompt, max_tokens=300)
            if raw:
                m = _re.search(r"\[.*\]", raw, _re.DOTALL)
                if m:
                    theme_clusters = json.loads(m.group())
        except Exception:
            pass

    if not theme_clusters:
        all_themes = []
        for p in result_papers:
            all_themes.extend(p["key_themes"])
        for theme, _ in Counter(all_themes).most_common(4):
            theme_clusters.append({"theme": theme, "sentiment": "mixed"})

    return {"papers": result_papers, "theme_clusters": theme_clusters}


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate FrontierPilot living knowledge base HTML")
    parser.add_argument("--data", required=True, help="Path to JSON data file")
    parser.add_argument("--output", help="Output HTML path (default: /tmp/FrontierPilot_{topic}.html)")
    args = parser.parse_args()

    data = json.loads(Path(args.data).read_text(encoding="utf-8"))

    topic = data.get("topic", "Research")
    topic_zh = data.get("topic_zh", topic)
    field_overview = data.get("field_overview", "")
    foundation = data.get("foundation", [])
    frontier = data.get("frontier", [])
    reading_list = data.get("reading_list", [])
    top_authors = data.get("top_authors", [])
    resources = data.get("resources", {})
    paper_clusters = data.get("paper_clusters")
    graph_mermaid = data.get("graph_mermaid") or default_graph(topic, foundation, paper_clusters)
    latest_updates = data.get("latest_updates", [])
    social_actions = data.get("social_actions", [])
    generated_at = data.get("generated_at", datetime.now().strftime("%Y-%m-%d %H:%M"))

    output_path = args.output or f"/tmp/FrontierPilot_{topic.replace(' ', '_')}.html"

    # Ensure every paper has a node_id (for pre-baked graph_mermaid, default_graph won't run)
    for paper in foundation:
        if not paper.get("node_id"):
            paper["node_id"] = make_node_id(paper.get("year", 2000), paper.get("title", ""), "N")
    for paper in frontier:
        if not paper.get("node_id"):
            paper["node_id"] = make_node_id(paper.get("year", 2024), paper.get("title", ""), "F")

    # Build interactive paper index and add click directives to graph
    paper_index = build_paper_index(foundation, frontier)
    # When graph_mermaid is hand-written by LLM, its node IDs may differ from
    # auto-generated ones. Reconcile so click directives bind to the correct nodes.
    if data.get("graph_mermaid"):
        paper_index = _reconcile_paper_index(paper_index, graph_mermaid)
    paper_index_json = json.dumps(paper_index, ensure_ascii=False)
    if paper_index:
        graph_mermaid = add_click_directives(graph_mermaid, paper_index)

    # Build conditional elements
    updates_count = len(latest_updates)
    updates_badge_header = f'<span class="badge">📰 {updates_count} 条最新动态</span>' if updates_count else ""
    updates_badge_nav = f'<span class="nav-badge">{updates_count}</span>' if updates_count else ""
    social_done_count = len([a for a in social_actions if a.get("status") in ("done", "followed", "ready", "qr_found")])
    social_badge_nav = f'<span class="nav-badge" style="background:var(--social)">{social_done_count}</span>' if social_done_count else ""

    # Build reviewer consensus data (P2)
    consensus_data = build_reviewer_consensus(frontier)
    reviewer_consensus_json = json.dumps(consensus_data, ensure_ascii=False)

    html = HTML_TEMPLATE.format(
        topic=_escape(topic),
        topic_zh=_escape(topic_zh),
        generated_at=_escape(generated_at),
        foundation_count=len(foundation),
        frontier_count=len(frontier),
        reading_count=len(reading_list),
        latest_updates_count=updates_count,
        social_actions_count=len(social_actions),
        updates_badge_header=updates_badge_header,
        updates_badge_nav=updates_badge_nav,
        social_badge_nav=social_badge_nav,
        graph_mermaid=graph_mermaid,
        field_overview_html=render_field_overview(field_overview),
        foundation_html=render_foundation(foundation),
        frontier_html=render_frontier(frontier),
        reading_html=render_reading_list(reading_list),
        resources_html=render_resources(resources),
        top_authors_html=render_top_authors(top_authors),
        latest_updates_html=render_latest_updates(latest_updates),
        social_actions_html=render_social_actions(social_actions),
        topic_js=_js_safe(topic),
        reviewer_consensus_json=reviewer_consensus_json,
    )

    # Inject paper_index via string replacement (avoids f-string brace escaping issues)
    html = html.replace("__PAPER_INDEX__", paper_index_json)

    Path(output_path).write_text(html, encoding="utf-8")
    print(f"✅ 知识库已生成：{output_path}")
    print(f"   在浏览器中打开：file://{output_path}")
    if latest_updates:
        print(f"   📰 包含 {updates_count} 条最新动态")
    if top_authors:
        print(f"   🏛️ 包含 {len(top_authors)} 个领域强组")

    # Auto-start chat server in background, passing the exact HTML path the browser has open
    _start_chat_server(args.data, html_path=output_path)


def _is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("localhost", port)) == 0


def _start_chat_server(data_path: str, port: int = 7779, html_path: str = ""):
    chat_server = Path(__file__).parent / "chat_server.py"
    if not chat_server.exists():
        return

    if _is_port_in_use(port):
        print(f"\n🤖 智能助手已在运行（localhost:{port}）")
        return

    cmd = [sys.executable, str(chat_server), "--data", data_path, "--port", str(port)]
    if html_path:
        cmd += ["--html", html_path]

    # Launch as detached background process so it outlives this script
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,   # detach from current process group
    )
    # Give it a moment to bind the port
    import time; time.sleep(0.8)
    if _is_port_in_use(port):
        print(f"\n🤖 智能助手已自动启动（localhost:{port}，PID {proc.pid}）")
        print(f"   在「🤖 智能助手」面板中直接发送指令即可")
        print(f"   停止服务：kill {proc.pid}")
    else:
        print(f"\n⚠️  智能助手启动失败，请手动运行：")
        print(f"   python3 {chat_server} --data {data_path}")


if __name__ == "__main__":
    main()
