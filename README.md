# FrontierPilot 🧭

> **从科研小白到领域专家，知识库陪你一起成长。**

FrontierPilot is an AI-powered research onboarding tool that turns a newcomer into a domain expert in minutes — and keeps growing with them over time.

Built for the **Zhongguancun North Latitude "Lobster" Hackathon**, Academic Lobster track, running on the [OpenClaw](https://github.com/openclaw-ai/openclaw) platform.

---

## What It Does

Given a research topic (e.g., "Diffusion Models"), FrontierPilot:

1. **Builds a growing knowledge base** — field overview, foundational papers, frontier papers with peer reviews, knowledge graph, top labs, resource map
2. **Embeds an AI assistant** — the user chats directly inside the HTML page to update it, add papers, analyze arXiv preprints, or ask questions
3. **Explores social communities** — finds experts on Xiaohongshu, discovers WeChat groups, drafts outreach messages

The output is a **single self-contained HTML file** that accumulates knowledge across sessions, unlike a one-time ChatGPT answer.

---

## Core Capabilities

### Knowledge Exploration
- **Foundation Roadmap** — top-cited papers from Semantic Scholar, real citation edges, school-clustered knowledge graph (Mermaid.js)
- **Frontier Snapshot** — recent papers from ICLR / NeurIPS / ICML with OpenReview peer reviews and rebuttals
- **Reading List** — automatically expanded from reviewer-recommended related work
- **Top Labs** — active researchers and institutions identified from author lists
- **Latest Updates tab** — filled via "帮我更新最新动态" command; searches arXiv last 30 days

### In-Page AI Assistant
- Runs as a local HTTP server (`chat_server.py`, port 7779)
- SSE streaming — responses appear in real time inside the browser
- Supported commands:
  - `更新最新动态` — search arXiv, append to knowledge base, regenerate HTML
  - `添加这篇论文 [title/arXiv ID]` — add paper via Semantic Scholar
  - `分析 arXiv:xxx` — fetch and analyze a paper
  - `帮我给 [作者] 写一封邮件` — draft academic outreach email
  - `帮我在小红书找领域博主` — social exploration

### Social Exploration
- Xiaohongshu expert discovery (via xiaohongshu-mcp → xhs-cli → demo fallback)
- WeChat group QR code finding + join message generation
- Bilibili + WeChat public account search for Chinese tutorials

---

## Repository Structure

```
skills/
├── frontierPilot/              ← Main skill
│   ├── SKILL.md                ← OpenClaw skill definition + full workflow
│   ├── references/             ← Data schema, venue rules, LLM prompts, runbook
│   └── scripts/
│       ├── chat_server.py      ← Local HTTP server (SSE streaming, port 7779)
│       ├── generate_report.py  ← Self-contained HTML knowledge base generator
│       ├── social_agent.py     ← Xiaohongshu + WeChat group exploration
│       ├── search_social.py    ← Bilibili + WeChat public account search
│       ├── preload_demo.py     ← Demo data generator (for offline demo)
│       └── write_fp_json.py    ← Safe JSON write + validation utility
│
├── arxiv-watcher/              ← arXiv search (bash script)
├── github-search/              ← GitHub repository search (Node.js)
├── openreview-explorer/        ← OpenReview paper + peer review fetcher
└── semantic-scholar/           ← Semantic Scholar API wrapper
```

---

## Data Flow

```
User input: "帮我探索 Diffusion Models"
     │
     ├── Track 1: Semantic Scholar (citation-sorted) → foundational papers + citation graph
     ├── Track 2: OpenReview (ICLR/NeurIPS/ICML × 2023/2024) → frontier papers + reviews
     └── Track 3: GitHub + Bilibili + WeChat → resource map
     │
     ├── LLM: cluster papers into schools of thought → paper_clusters
     ├── LLM: synthesize field overview (300–400 words) → field_overview
     │
     └── generate_report.py → FrontierPilot_{TOPIC}.html  (self-contained)
                            → chat_server.py starts on port 7779
```

---

## Technical Facts

| Item | Detail |
|------|--------|
| **Runtime** | Python 3.9, Node.js (OpenClaw Docker container) |
| **Main output** | Self-contained HTML (all CSS/JS inline; Mermaid.js from CDN) |
| **Chat transport** | Server-Sent Events (SSE), `ThreadingMixIn` HTTP server |
| **LLM fallback chain** | OpenClaw Gateway → OpenRouter → Anthropic API → template |
| **Data layer** | `fp_data_{TOPIC}.json` separates collection from rendering |
| **File safety** | Atomic writes (`.tmp` → rename) to prevent partial JSON reads |
| **Social backends** | xiaohongshu-mcp (MCP) → xhs-cli → demo fallback |
| **External APIs** | Semantic Scholar, OpenReview, arXiv (no key required), GitHub |

---

## Running on OpenClaw

```bash
# In OpenClaw chat:
FrontierPilot，我刚进组，方向是 Diffusion Models，帮我系统入门这个领域
```

The skill runs automatically. After ~5–10 minutes, open `http://localhost:7779/` in your browser.

To update latest papers later:
```
帮我更新 Diffusion Models 的最新动态
```

---

## Competition

**Zhongguancun North Latitude "Lobster" Hackathon** — Academic Lobster track
Platform: OpenClaw (open-source personal AI agent platform)
Team: FrontierPilot
