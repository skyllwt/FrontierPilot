---
name: frontierPilot
description: FrontierPilot 学术探索主编排。当用户想探索一个研究方向、入场一个新领域、了解某个 AI/CS 方向时使用；也处理"更新 [topic] 的最新动态"请求（只执行更新分支）。执行三轨工作流：基础知识Roadmap + 前沿peer review分析 + 社交资源聚合，最终生成成长型知识库 HTML。
---

# FrontierPilot — 学术领域成长型知识库主编排

**定位**：将一个研究新手变成领域入门者，并持续陪伴其成长。
- **首次探索**：输入方向名称，输出完整领域入场包（历史脉络 + 同行评审视角 + 中文资源 + 领域强组）
- **持续更新**：定期追踪最新动态，将新论文追加到知识库的"最新动态"栏

**触发条件**：
- 首次探索：用户说"帮我探索 X 方向"、"我想入门 X"、"X 领域现在什么水平"、"带我了解 X 研究方向"
- 更新动态：用户说"帮我更新 X 的最新动态"、"X 方向有什么新进展"、"更新一下 X 知识库"

---

## 运行环境依赖

| 依赖 | 用途 | 状态检测 |
|------|------|---------|
| OpenReview API | 轨道二 peer review 抓取 | 匿名访问，无需配置 |
| Semantic Scholar API | 轨道一/二论文搜索 | 匿名访问；`SS_API_KEY` 可选提速 |
| `xiaohongshu-mcp` Docker 容器 | 智能助手"社交探索"功能 | **可选**；缺失时自动降级为 demo 模式 |

**xiaohongshu-mcp 启动方式**（一次配置，长期有效）：
```bash
docker start xiaohongshu-mcp   # 机器重启后需要执行一次
```
Cookie 有效期约 1-3 个月。过期后运行 `python3 scripts/xhs_login.py` 重新扫码登录。
社交探索功能在 xiaohongshu-mcp 不可用时自动降级为 demo 模式，不影响主流程。

---

## 工作流总览

**首次探索模式**：三轨并行执行 + 合成步骤，最终生成成长型知识库 HTML。总时间目标 < 10 分钟。

**更新模式**：仅执行 arXiv 最近 30 天搜索，将新论文追加到已有 JSON 的 `latest_updates` 字段，重新生成 HTML。

```
用户输入: "帮我探索 [方向]"
    │
    ├── 轨道一：Foundation Track（基础 Roadmap）
    │       1A: SS search --sort-by citations → 高引用奠基论文（精准，无需 LLM 猜）
    │       1B: SS paper --include-references × 前6篇 → 真实引用边（构建图谱用）
    │       1C: arXiv 最近90天 → 补充预印本（可选，通常0-2篇）
    │       Step 3C（并行）：提取高频作者 → Semantic Scholar 补充机构信息
    │
    ├── 轨道二：Frontier Track（前沿 peer review 分析）
    │       2A: SS search --sort-by year --year-after 2022 → 近年前沿候选
    │       2B: OR 6个venue-year并行搜索（ICLR/NeurIPS/ICML × 2023/2024，约300篇）
    │       2C: 交叉匹配 SS ↔ OR → 命中 forum_id → 拉取 peer review（目标5-8篇）
    │       2D: get_reviews.py × 5-8篇
    │       2E: Related work 提取（reviewer 推荐的比较对象）
    │
    ├── 轨道三：Social Track（资源地图）
    │       GitHub 开源实现 + Bilibili 中文教程 + 微信公众号文章
    │
    ├── Step 2.5：LLM 识别流派 → paper_clusters（2-4个方法族）
    │
    ├── Step 4.5：合成 Field Overview（专家视角综述，300-400字）
    │       输入：foundation摘要 + reviewer strengths/weaknesses
    │       输出：field_overview 字符串
    │
    └── Step 5：生成成长型知识库 HTML（generate_report.py）
            包含：领域概况 + 知识图谱（subgraph流派区块） + 基础Roadmap + 前沿快照
            + 阅读清单 + 资源地图 + 领域强组
            + 最新动态（初始为空占位） + 我的笔记（localStorage）

用户输入: "帮我更新 [方向] 的最新动态"
    │
    └── 更新分支（仅执行此步骤）：
            arXiv 搜索最近 30 天 → 提取 2-5 篇新论文
            → 追加到 latest_updates 字段（带日期和摘要）
            → 重新生成 HTML（保留已有数据，追加 latest_updates）
```

---

## 执行步骤

### 步骤 0：解析用户输入 + 判断模式

从用户输入中提取：
- `MODE`：`explore`（首次探索）或 `update`（更新最新动态）
  - 包含"更新"、"最新动态"、"新进展"等词 → `update` 模式
  - 否则 → `explore` 模式
- `TOPIC`：研究方向名称（中文或英文均可，后续搜索转为英文关键词）
- `VENUE`：目标会议（默认 ICLR，可由用户指定）
- `YEAR`：目标年份（默认 2024）

如果用户未指定 venue/year，默认使用 ICLR 2024。

**如果是 `update` 模式**：跳转到文末的"更新分支"步骤，不执行三轨主流程。

---

### 轨道一：Foundation Track — 基础知识 Roadmap

**目标**：找出该方向的奠基性工作，获取真实引用边，构建演进时间线。

**核心改进**：不再用 arXiv（按提交时间降序，奠基论文被埋在后几十条）。改用 Semantic Scholar 按引用量排序——高引用 = 奠基论文，精准且无需 LLM 猜测。

#### Step 1A：Semantic Scholar 引用量排序搜索（主力）

```bash
python3 /home/node/.openclaw/workspace/skills/semantic-scholar/scripts/semantic_scholar.py \
  search --query "<TOPIC_ENGLISH_KEYWORDS>" --sort-by citations --limit 30
```

返回按引用量降序排列的论文列表。每篇包含：`paperId`、`title`、`year`、`citationCount`、`venue`、`authors`、`abstract`。

**前 8-10 篇即为奠基论文**（无需 LLM 筛选引用量高低，数字直接说明）。从中选取 6-8 篇时间跨度合理的论文作为 foundation。

#### Step 1B：获取真实引用边（构建 graph_mermaid 用）

对前 6 篇奠基论文，用 `paper --include-references` 获取每篇论文及其前 10 条引用：

```bash
# 对每篇奠基论文执行一次（共 6 次，逐一执行）
python3 /home/node/.openclaw/workspace/skills/semantic-scholar/scripts/semantic_scholar.py \
  paper --paper-id <SS_PAPER_ID_1> --include-references

python3 /home/node/.openclaw/workspace/skills/semantic-scholar/scripts/semantic_scholar.py \
  paper --paper-id <SS_PAPER_ID_2> --include-references

# ... 对其余 4 篇重复
```

返回结构包含 `references[]`，每条引用有 `paperId`、`title`、`year`。

> **注意**：不要用 `references` 子命令——其嵌套字段在 SS API 中存在兼容性问题。
> `paper --include-references` 返回的 10 条引用对于奠基论文之间的交叉引用提取已足够。

**目的**：得到真实的"A引用了B"关系，用于在 graph_mermaid 中画真实引用边（`A --> B`），而非 LLM 编造的线性链。

跨越范围：只取奠基论文集合内部的相互引用关系（约 5-10 条真实边），忽略指向集合外部论文的引用。

#### Step 1C：arXiv 最近 90 天预印本补充（可选，次要）

```bash
bash /home/node/.openclaw/workspace/skills/arxiv-watcher/scripts/search_arxiv.sh "<TOPIC_ENGLISH_KEYWORDS>" 20
```

从返回结果中**只取 `<published>` 在最近 90 天内的论文**（其余全部丢弃）。通常补充 0-2 篇 Semantic Scholar 尚未收录的最新预印本。若 Step 1A 已覆盖最新工作，此步骤可跳过。

**轨道一最终输出**：

```
📚 基础 Roadmap · [TOPIC] 领域演进

[2018] 论文A — 奠定了 X 基础...（⭐ 8k citations）
[2020] 论文B — 引入了 Y 机制，解决了...（⭐ 18k citations）
[2022] 论文C — 提出 Z 方法，首次实现...（⭐ 12k citations）
[2024] 论文D — 当前 SOTA，方向是...（⭐ 2k citations）

演进逻辑：[2-3句话总结该领域如何从初始问题演进到当前前沿]
真实引用边：[从 SS references 数据得出的 A→B 关系]
```

---

### 轨道二：Frontier Track — 前沿论文分析

**目标**：覆盖 5-10 篇高质量前沿论文，尽可能附带同行评审数据。

---

#### Step 2.0：Topic 类型判断（决定后续路径）

**在执行任何搜索前**，先做显式分类，并将结果输出到后续步骤。

**分类方法**：对以下三个问题各打分（0/1），合计 ≥ 2 分判为系统类，否则为 ML/AI 类：

| 问题 | 系统类得 1 分 |
|------|-------------|
| 该 topic 的核心贡献是工程实现/性能优化而非新算法？ | 是 |
| 该 topic 的论文通常发在 ASPLOS/OSDI/SOSP/MLSys/SIGCOMM/EuroSys？ | 是 |
| 该 topic 中"引用量"比"peer review 评分"更能反映论文影响力？ | 是 |

**输出**（在继续之前请明确写出）：
```
Topic 分类：[ML/AI 类 / 系统类 / 混合类]
判断依据：[一句话说明]
执行路径：[OpenReview 路径 / Citation 路径 / 混合路径]
```

**三种路径**：
- **ML/AI 类** → Step 2A → 2B → 2C → 2D（OpenReview peer review）
- **系统类** → Step 2A → 2E（Citation 路径，跳过 2B-2D）
- **混合类** → 先走 OpenReview 路径；若 Step 2C 交叉匹配命中 < 3 篇，自动补充 Citation 路径的结果，两类论文合并进 `frontier`

---

#### Step 2A：Semantic Scholar 近年前沿候选（两条路径共用）

```bash
python3 /home/node/.openclaw/workspace/skills/semantic-scholar/scripts/semantic_scholar.py \
  search --query "<TOPIC_ENGLISH_KEYWORDS>" --sort-by year --year-after 2021 --limit 25
```

返回 2022 年至今的论文，按年份降序。LLM 从中选 8-10 篇最相关的作为前沿候选，记录其 `title`（用于下一步交叉匹配）。

#### Step 2B：OpenReview 多 venue-year 并行搜索

**第一步：根据 topic 选择要搜索的 venue-year 组合。**

所有可用 venue（均在 OpenReview 上有数据）：

| Venue | 年份范围 | 适用 topic |
|-------|---------|-----------|
| **ICLR** | 2023 / 2024 / 2025 / 2026 | 所有 ML/AI topic，必选 |
| **NeurIPS** | 2023 / 2024 / 2025 | 所有 ML/AI topic，必选 |
| **ICML** | 2023 / 2024 / 2025 | 所有 ML/AI topic，必选 |
| **COLM** | 2024 / 2025 | Language model、LLM、NLP、对话系统 |
| **CoRL** | 2023 / 2024 | Robotics、Embodied AI、强化学习 |
| **UAI** | 2023 / 2024 | 概率图模型、贝叶斯方法、因果推断 |

> **LLM 选 venue 的规则**：
> - 必选：ICLR + NeurIPS + ICML 最近两年（共 6 个）
> - 按 topic 追加：topic 与 COLM/CoRL/UAI 高度相关时各加 1-2 年（总数控制在 8-10 个以内）
> - 例：topic = "LLM Reasoning" → 追加 COLM 2024/2025
> - 例：topic = "Robot Manipulation" → 追加 CoRL 2023/2024

**第二步：执行搜索（以下命令可并行执行）。**

```bash
# ── 必选：ICLR ────────────────────────────────────────────────────────────
python3 /home/node/.openclaw/workspace/skills/openreview-explorer/scripts/search_papers.py \
  --venue "ICLR" --year 2025 --limit 50
python3 /home/node/.openclaw/workspace/skills/openreview-explorer/scripts/search_papers.py \
  --venue "ICLR" --year 2024 --limit 50
# 若需更早覆盖，可追加 --year 2023

# ── 必选：NeurIPS ─────────────────────────────────────────────────────────
python3 /home/node/.openclaw/workspace/skills/openreview-explorer/scripts/search_papers.py \
  --venue "NeurIPS" --year 2025 --limit 50
python3 /home/node/.openclaw/workspace/skills/openreview-explorer/scripts/search_papers.py \
  --venue "NeurIPS" --year 2024 --limit 50

# ── 必选：ICML ────────────────────────────────────────────────────────────
python3 /home/node/.openclaw/workspace/skills/openreview-explorer/scripts/search_papers.py \
  --venue "ICML" --year 2025 --limit 50
python3 /home/node/.openclaw/workspace/skills/openreview-explorer/scripts/search_papers.py \
  --venue "ICML" --year 2024 --limit 50

# ── 按 topic 追加（示例）────────────────────────────────────────────────────
# LLM / language model topic:
python3 /home/node/.openclaw/workspace/skills/openreview-explorer/scripts/search_papers.py \
  --venue "COLM" --year 2024 --limit 50
python3 /home/node/.openclaw/workspace/skills/openreview-explorer/scripts/search_papers.py \
  --venue "COLM" --year 2025 --limit 50

# Robotics / embodied AI topic:
python3 /home/node/.openclaw/workspace/skills/openreview-explorer/scripts/search_papers.py \
  --venue "CoRL" --year 2024 --limit 50
```

每次返回 `{"papers": [...], "total": N}`，每篇含 `forum_id`、`title`、`abstract`、`authors`、`url`。6-8 个 venue-year 汇总约 300-500 篇候选。

#### Step 2C：交叉匹配（核心新步骤）→ 获得 forum_id

LLM 将 Step 2A 的 SS 论文标题 与 Step 2B 的 ~300 篇 OR 标题进行模糊比对：
- **匹配成功**：得到 `forum_id`，进入 Step 2D 拉取 peer review
- **OR 有相关但 SS 未收录的论文**：也纳入前沿候选（同样进入 Step 2D）
- **目标**：命中 5-8 篇带 forum_id 的相关论文

若某 venue-year 搜索结果为空（网络或 API 问题），跳过该 venue，不阻塞整体流程。

#### Step 2D：获取 Peer Reviews（目标 5-8 篇）

对交叉匹配命中的**每篇**论文，均需获取 peer review：

```bash
python3 /home/node/.openclaw/workspace/skills/openreview-explorer/scripts/get_reviews.py \
  --forum-id <FORUM_ID_1> \
  --venue "ICLR" \
  --year 2024

python3 /home/node/.openclaw/workspace/skills/openreview-explorer/scripts/get_reviews.py \
  --forum-id <FORUM_ID_2> \
  --venue "NeurIPS" \
  --year 2023
# ... 对每篇论文重复（venue 和 year 需与 Step 2B 匹配的记录一致）
```

返回 JSON 列表，每个 review 包含：rating、summary、strengths、weaknesses、confidence、rebuttal。

---

#### Step 2E：系统类 Topic 的 Citation 路径（跳过 2B-2D）

> **仅当 Step 2.0 判断为系统类时执行**，ML/AI 类直接跳过此步骤。

系统类 topic 的顶会（ASPLOS、OSDI、MLSys、SIGCOMM 等）不在 OpenReview，无法获取 peer review 数据。改用 **Semantic Scholar 引用量 + 发表 venue** 作为论文质量代理指标。

**操作**：直接使用 Step 2A 已获取的前沿论文结果。对每篇论文，将其写入 `frontier` 字段时使用以下格式（注意用 `citation_count` 替代 `avg_rating`）：

```json
{
  "title": "MoE-APEX: An Efficient MoE Inference System...",
  "venue": "ASPLOS 2026",
  "year": 2026,
  "url": "https://arxiv.org/abs/2502.xxxxx",
  "avg_rating": null,
  "citation_count": 39,
  "reviews": []
}
```

**`citation_count` 填写规则**：从 Step 2A 的 SS 搜索结果中直接读取 `citationCount` 字段。若论文发表在高水平 systems 会议（ASPLOS/OSDI/SOSP/MLSys/SIGCOMM），在 `venue` 字段中**保留完整会议名和年份**（如 `"ASPLOS 2026"`），这是论文质量的核心信号。

**展示效果**：generate_report.py 检测到 `avg_rating` 为 null 且 `citation_count` 存在时，自动显示为 `⭐ 39 citations`（灰色徽章），而不是 `N/A`。

---

#### Step 3C：作者提取（与轨道三并行执行）

从轨道一和轨道二收集到的论文中，提取高频作者：

1. 汇总 `foundation` 论文的 `authors` 字段 + `frontier` 论文的 authors 字段
2. 统计高频作者（出现 ≥ 2 次，或为明确的一作/通讯）
3. 对 Top 5-6 位作者，用 Semantic Scholar 查询补充机构和论文数（可选）：

```bash
python3 /home/node/.openclaw/workspace/skills/semantic-scholar/scripts/semantic_scholar.py \
  author --name "<AUTHOR_NAME>"
```

若 Semantic Scholar 无法查询，直接从论文元数据提取可用信息（机构通常在 arXiv 摘要末尾或 OpenReview profile 中）。

**输出格式**（写入 JSON 的 `top_authors` 字段）：
```json
[
  {
    "name": "Yang Song",
    "institution": "OpenAI / Stanford University",
    "papers_count": 45,
    "recent_work": "Score-based generative modeling, Consistency Models, Flow Matching",
    "url": "https://scholar.google.com/citations?user=..."
  }
]
```

⚠️ 若无法获取完整机构信息，只填 name + recent_work 也可，不要阻塞流程。

#### Step 2E：提取 Related Work（关键亮点功能）

对每篇论文的所有 reviews，用 LLM 解析 `weaknesses` 和 `questions` 字段，提取 reviewer **明确要求作者比较或解释的 related work**。

提取逻辑：
- 找形如"为什么不与 [论文X] 比较"、"[方法Y] 似乎与你的工作很相关"、"你的方法相比 [工作Z] 有何优势"的表述
- 提取被提及的论文名称或方法名称
- 将这些自动加入阅读清单（标注来源：reviewer 推荐）

**轨道二最终输出**：

```
🔬 前沿进展 · 多 venue 同行评审视角（5-8篇）

**论文 1**：[标题]（venue year）
  作者：...  |  链接：...
  摘要：[1句话]
  📊 Reviewer 评分：[平均分] / 10
  ✅ 优点：[综合 strengths]
  ⚠️  弱点：[综合 weaknesses]
  💬 作者回应：[rebuttal 核心观点]
  🔗 Reviewer 推荐比较的工作：[论文A]、[论文B]（已加入阅读清单）

**论文 2**：...
```

---

### Step 2.5：流派聚类识别（三轨完成后执行）

**目标**：将所有收集到的论文（foundation + frontier）按方法族分组，用于 graph_mermaid 的 subgraph 布局。

**输入**：所有论文的标题 + 摘要（foundation 和 frontier 合并）

**LLM Prompt 框架**：
```
基于以下论文列表，将其分为 2-4 个方法族（methodological families）。
每篇论文只属于一个流派。流派命名要简洁（如 "Score-based SDE"、"Flow-based Samplers"、"Latent Methods"）。
输出 JSON 格式的 paper_clusters 数组。

论文列表：[PAPER_LIST with title + abstract]
```

**输出格式**（写入 JSON 的 `paper_clusters` 字段）：
```json
[
  {
    "id": "cluster_sde",
    "name": "Score-based / SDE Methods",
    "subgraph_style": "fill:#eff6ff,stroke:#2563eb",
    "paper_node_ids": ["N2019_NCSN", "N2020_DDPM", "N2021_SDE"]
  },
  {
    "id": "cluster_flow",
    "name": "Flow-based Samplers",
    "subgraph_style": "fill:#faf5ff,stroke:#7c3aed",
    "paper_node_ids": ["N2021_DDIM", "N2022_RF", "N2023_FM"]
  },
  {
    "id": "cluster_latent",
    "name": "Latent / Efficient Methods",
    "subgraph_style": "fill:#f0fdf4,stroke:#059669",
    "paper_node_ids": ["N2022_LDM", "N2023_DiT"]
  }
]
```

⚠️ `paper_node_ids` 中的 ID 必须与 `graph_mermaid` 中的 Mermaid 节点 ID 完全一致。

---

### 轨道三：Social Track — 资源地图

**目标**：找到该方向的开源实现、中文教程、和公众号文章。

⚠️ **该轨道所有步骤均为必须执行，不可省略。**

#### Step 3A：GitHub 开源实现

```bash
node /home/node/.openclaw/workspace/skills/github-search/scripts/github-search.mjs \
  "<TOPIC_ENGLISH>" --min-stars 200 --limit 6
```

若结果偏少（<3个），将 `--min-stars` 改为 100 再跑一次。

#### Step 3B：Bilibili + 微信（⚠️ 必须执行，不可跳过）

```bash
python3 /home/node/.openclaw/workspace/skills/frontierPilot/scripts/search_social.py \
  --topic "<TOPIC_ENGLISH>" \
  --topic-zh "<TOPIC_CHINESE>" \
  2>/dev/null
```

返回 JSON，格式：
```json
{
  "bilibili": [{"title": "...", "url": "..."}],
  "wechat": [{"title": "...", "url": "..."}]
}
```

⚠️ **必须将 bilibili 和 wechat 两个 section 的内容都包含在最终输出中。** 即使某平台只有搜索页链接也要列出，不可丢弃。

**轨道三最终输出**（三个 section 必须全部出现）：

```
🌐 资源地图 · [TOPIC]

💻 GitHub 开源实现
  1. [repo名] ⭐[stars] — [链接]
  2. ...（至少3个）

📺 Bilibili 中文教程（⚠️ 必须列出，来自 search_social.py 的 bilibili 字段）
  1. [标题] — [链接]
  2. ...

📰 微信公众号文章（⚠️ 必须列出，来自 search_social.py 的 wechat 字段）
  1. [标题] — [链接]
  2. ...
```

⚠️ **如果 Bilibili 或微信结果为空，必须写"搜索无结果，建议手动搜索：[关键词]"，不可整个 section 消失。**

---

### Step 4.5：合成 Field Overview（专家视角综述）

三轨数据收集完成后，在生成 HTML 之前，用 LLM 综合所有信息生成一段 300-400 字的专家视角综述。

**输入**：
- 轨道一：奠基论文的 abstract + problem_solved/problem_left
- 轨道二：frontier 论文的 reviewer strengths 和 weaknesses 汇总

**LLM Prompt 框架**：
```
基于以下信息，用 300-400 字写一段专家视角综述，面向研究新手。

需要涵盖：
1. 该领域的本质问题是什么（用一句话说清楚，避免术语堆砌）
2. 2023-2024 年的主要共识是什么（被多数 reviewer 肯定的方向）
3. 当前主要争议或开放问题（被 reviewer 反复质疑的点）
4. 新手最应该优先关注什么（Top 1-2 个建议）

写作风格：像一位资深博士在组会上给新生做 5 分钟 briefing，直接、实用、有洞察。
不要写成论文摘要或综述论文风格。第一段就给出核心判断，不要铺垫。

领域名称：[TOPIC]
奠基论文摘要（节选）：[FOUNDATION_ABSTRACTS]
Reviewer 评价汇总：[REVIEWER_INSIGHTS]
```

**输出格式**（写入 JSON 的 `field_overview` 字段）：
纯文本字符串，约 300-400 字，用换行分段（每段一个主题）。

---

### 最终整合输出

三轨完成后，整合为完整的领域入场包：

```
✅ [TOPIC] 领域入场包

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📚 基础 Roadmap：[N] 个关键节点 + 演进逻辑
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[轨道一输出]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔬 前沿快照：[VENUE] [YEAR] 顶会 + Peer Review 视角
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[轨道二输出]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 综合阅读清单（按依赖顺序）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
优先阅读（奠基）：
  1. [论文] — [一句话说明为何先读]
  2. ...

进阶阅读（前沿）：
  3. [论文] — [来源：ICLR 2024 top paper]
  4. ...

扩展阅读（Reviewer 推荐）：
  5. [论文] — [来源：reviewer 要求与之比较]
  6. ...

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🌐 资源地图（必须包含 GitHub + Bilibili + 微信三个子节）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💻 GitHub 开源实现
[来自 github-search 的结果]

📺 Bilibili 中文教程
[来自 search_social.py 的 bilibili 字段，必须输出]

📰 微信公众号
[来自 search_social.py 的 wechat 字段，必须输出]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⏱️  总用时：< 10 分钟  |  数据来源：arXiv + OpenReview + GitHub + Bilibili + 微信
```

---

## Demo 示例：输入 "帮我探索 AutoML 方向"

当用户输入 "帮我探索 AutoML 方向" 时，Agent 应按以下顺序执行：

**1. 解析参数**
- TOPIC = "AutoML"
- TOPIC_ENGLISH = "AutoML neural architecture search"
- TOPIC_CHINESE = "AutoML 自动机器学习"
- VENUE = ICLR，YEAR = 2024（默认）

**2. 执行轨道一**

```bash
bash /home/node/.openclaw/workspace/skills/arxiv-watcher/scripts/search_arxiv.sh "AutoML neural architecture search" 30
```

解析 XML，LLM 从中识别出：
- [2019] NAS with RL (Zoph & Le) — 开创神经架构搜索
- [2019] DARTS — 可微分架构搜索，大幅降低搜索成本
- [2021] EfficientNet — 自动化网络缩放
- [2023] LLM4NAS — 用 LLM 指导架构搜索

**3. 执行轨道二**

```bash
# 先尝试带 query
python3 /home/node/.openclaw/workspace/skills/openreview-explorer/scripts/search_papers.py \
  --query "automl" \
  --venue "ICLR" \
  --year 2024 \
  --limit 20
```

若有结果，LLM 筛选出最相关的 3 篇。若返回 total=0，改为：

```bash
python3 /home/node/.openclaw/workspace/skills/openreview-explorer/scripts/search_papers.py \
  --venue "ICLR" \
  --year 2024 \
  --limit 50
```

对每篇相关论文获取 reviews：

```bash
python3 /home/node/.openclaw/workspace/skills/openreview-explorer/scripts/get_reviews.py \
  --forum-id <forum_id_1> \
  --venue "ICLR" \
  --year 2024

python3 /home/node/.openclaw/workspace/skills/openreview-explorer/scripts/get_reviews.py \
  --forum-id <forum_id_2> \
  --venue "ICLR" \
  --year 2024
```

LLM 解析 weaknesses 字段，发现 reviewer 提到 "与 SMAC3 比较" 和 "为何不与 BOHB 对比"，自动将 SMAC3 和 BOHB 加入阅读清单（标注来源）。

**4. 执行轨道三**

```bash
# GitHub
node /home/node/.openclaw/workspace/skills/github-search/scripts/github-search.mjs \
  "AutoML" --min-stars 200 --limit 6

# Bilibili + 微信（⚠️ 必须执行）
python3 /home/node/.openclaw/workspace/skills/frontierPilot/scripts/search_social.py \
  --topic "AutoML" \
  --topic-zh "AutoML 自动机器学习" \
  2>/dev/null
```

**5. 生成成长型知识库 HTML（必须执行）**

三轨数据 + Field Overview + Top Authors 收集完成后，将所有结果整理为 JSON，调用 generate_report.py 生成成长型知识库 HTML：

```python
# 输出路径使用 workspace 挂载目录，主机可直接访问
# 容器内路径：/home/node/.openclaw/workspace/output/
# 主机路径：  /home/corin/projects/FrontierPilot-workspace/output/（自动同步）
import os
os.makedirs("/home/node/.openclaw/workspace/output", exist_ok=True)

python3 /home/node/.openclaw/workspace/skills/frontierPilot/scripts/generate_report.py \
  --data /home/node/.openclaw/workspace/output/fp_data_{TOPIC}.json \
  --output /home/node/.openclaw/workspace/output/FrontierPilot_{TOPIC}.html
```

生成成功后，启动聊天桥接并在 Chat 里输出：

```bash
# 先停止旧的聊天服务器（如有），再启动新的
pkill -f "chat_server.py" 2>/dev/null || true
sleep 1

# 后台启动聊天桥接服务器（监听 localhost:7779）
# --html 参数让 GET http://localhost:7779/ 直接 serve 知识库页面
OPENCLAW_GATEWAY_TOKEN=OPENCLAW_GATEWAY_TOKEN_REDACTED \
OPENCLAW_GATEWAY_PORT=18789 \
nohup python3 /home/node/.openclaw/workspace/skills/frontierPilot/scripts/chat_server.py \
  --data /home/node/.openclaw/workspace/output/fp_data_{TOPIC}.json \
  --html /home/node/.openclaw/workspace/output/FrontierPilot_{TOPIC}.html \
  --port 7779 > /tmp/fp_chat.log 2>&1 &
```

```
✅ {TOPIC} 成长型知识库已生成！

🌐 **立即打开知识库：[http://localhost:7779/](http://localhost:7779/)**

知识库包含：
  📊 领域全景·专家视角导读（Field Overview）
  🗺️ 领域知识图谱（Mermaid 可交互，含引用关系）
  📚 基础 Roadmap（可视化时间线）
  🔬 前沿论文 + 同行评审卡片
  📋 阅读清单（分级排列）
  🌐 GitHub / Bilibili / 微信资源地图
  🏛️ 领域强组（Top 活跃研究者）
  📰 最新动态（占位，更新时自动填充）
  🤖 智能助手（与 OpenClaw 实时对话，可添加论文/更新知识库）

🤖 智能助手已就绪，在浏览器中直接输入指令：
  · 把 [论文名] 添加到知识图谱
  · 更新最新动态
  · 分析 arXiv 论文：[URL]
```

**JSON 数据格式说明**（写入 `/home/node/.openclaw/workspace/output/fp_data_{TOPIC}.json`）：
- `topic`：英文方向名，如 "AutoML"
- `topic_zh`：中文方向名，如 "自动机器学习"
- `field_overview`：300-400字专家视角综述字符串（Step 4.5 生成）
- `foundation`：奠基论文列表，每项含 year/title/authors/description/problem_solved/problem_left/url/is_key/citation_count（来自 SS，精准）
- `frontier`：前沿论文列表（目标 5-8 篇），每项含 title/forum_id/venue/year/url/avg_rating/reviews
  - reviews 每项含 rating/strengths/weaknesses/related_work（reviewer 推荐的 related work 列表）
- `reading_list`：阅读清单，每项含 title/type(foundation|frontier|recommended)/reason/url
- `top_authors`：领域强组列表，每项含 name/institution/papers_count/recent_work/url（Step 3C 生成）
- `resources`：含 github/bilibili/wechat 三个列表
- `paper_clusters`：流派聚类（Step 2.5 生成），用于 subgraph 布局。每项含：
  - `id`：唯一标识符（如 `"cluster_sde"`）
  - `name`：流派名称（如 `"Score-based / SDE Methods"`）
  - `subgraph_style`：subgraph 背景色（如 `"fill:#eff6ff,stroke:#2563eb"`）
  - `paper_node_ids`：该流派的 Mermaid 节点 ID 列表（必须与 graph_mermaid 中 ID 一致）
- `graph_mermaid`：Mermaid flowchart 代码（**subgraph 格式**，引用边来自 SS 真实数据）。格式：
  ```
  flowchart LR
    classDef foundation fill:#dbeafe,stroke:#2563eb,color:#1e40af
    classDef key fill:#2563eb,stroke:#1e40af,color:white
    classDef frontier fill:#f5f3ff,stroke:#7c3aed,color:#4c1d95

    subgraph sg1["🔵 Score-based / SDE"]
      style sg1 fill:#eff6ff,stroke:#2563eb
      N2019_NCSN["2019 NCSN\n⭐4k"]:::foundation
      N2020_DDPM["2020 DDPM\n⭐18k"]:::key
    end

    subgraph sg2["🟣 Flow-based Samplers"]
      style sg2 fill:#faf5ff,stroke:#7c3aed
      N2021_DDIM["2021 DDIM\n⭐6k"]:::foundation
      N2023_FM["2023 Flow Matching"]:::frontier
    end

    N2019_NCSN --> N2020_DDPM
    N2020_DDPM --> N2021_DDIM
    N2021_DDIM --> N2023_FM
  ```
  ⚠️ 引用边（`A --> B`）必须来自 Step 1B 的 SS references 真实数据，不可 LLM 编造。跨 subgraph 的边保留。
- `latest_updates`：最新动态列表（首次生成时为空列表 `[]`），更新时追加项目
  - 每项含 date/title/url/summary/source（如 "arXiv"）

---

## 智能助手（聊天桥接）协议

HTML 知识库包含"🤖 智能助手"面板，通过本地 HTTP 服务器（`chat_server.py`，端口 7779）与 OpenClaw agent 通信。

### 启动聊天桥接（生成 HTML 后执行）

生成知识库 HTML 后，在后台启动聊天服务器：

```bash
python3 /home/node/.openclaw/workspace/skills/frontierPilot/scripts/chat_server.py &
```

然后使用 `CronCreate` 工具设置定时检查（每分钟），让 OpenClaw 自动处理用户发来的聊天请求：

```
CronCreate: cron="* * * * *", prompt="检查 FrontierPilot 聊天队列：GET http://localhost:7779/queue，如有 pending 命令则处理并 POST /respond 回复"
```

### 处理聊天命令（自动触发）

当 Cron 或用户手动触发时，执行：

#### C1：读取待处理命令

```bash
# 读取队列端点
curl -s http://localhost:7779/queue
# 返回 {"commands": [...], "total_pending": N}
```

若 `total_pending == 0`，什么都不做。

#### C2：判断命令类型并处理

根据 `message` 字段内容判断意图：

**类型 A：添加论文到知识图谱**（"添加论文"、"加入图谱"、"add paper"）
```
- 提取论文标题 / arXiv URL
- semantic_scholar.py search --query "<title>" --limit 5
- 找到 paperId，获取 citation_count / abstract / year / authors
- 将新论文追加到 data JSON 的 foundation 或 frontier 列表（由 LLM 判断归属）
- 重新运行 Step 2.5 更新 paper_clusters（如需要）
- 重新生成 HTML
- response: "✅ 已将《[title]》添加到知识图谱，请刷新页面查看"
- action: "html_updated"
```

**类型 B：更新最新动态**（"更新动态"、"最新进展"、"update"）
```
- 执行更新分支（见"更新分支"章节）
- response: "✅ 已发现 N 篇新论文并更新知识库，请刷新页面"
- action: "html_updated"
```

**类型 C：分析 arXiv 论文**（"分析"、"解读"、"arxiv.org/abs/"）
```
- 提取 arXiv ID 或搜索关键词
- 获取论文 abstract（SS search 或 arXiv XML）
- LLM 生成中文摘要 + 与当前领域的关系分析
- response: "📄 [论文名]\n\n[100字中文摘要]\n\n与 {topic} 的关系：[2-3句话]\n\n是否要将此论文加入知识图谱？"
- action: "analysis_done"
```

**类型 D：其他 / 问答**
```
- LLM 基于已有 foundation + frontier 数据回答问题
- response: "[LLM 回答，基于知识库数据]"
- action: "answer"
```

#### C3：POST 回复到桥接服务器

```bash
curl -s -X POST http://localhost:7779/respond \
  -H "Content-Type: application/json" \
  -d '{"id": "<COMMAND_ID>", "response": "<RESPONSE_TEXT>", "action": "<ACTION>"}'
```

`id` 来自 C1 读取到的命令的 `id` 字段。

### 完整示例：用户在 HTML 输入"把 Stable Diffusion 3 添加到知识图谱"

```
1. HTML → POST /command: {"message": "把 Stable Diffusion 3 添加到知识图谱", "topic": "Diffusion Models"}
2. OpenClaw (Cron触发) → GET /queue → 看到 pending 命令
3. SS search "Stable Diffusion 3 scaling rectified flow transformers" → 找到 paper
4. 追加到 frontier 列表，更新 JSON，重新生成 HTML
5. OpenClaw → POST /respond: {"id": "1", "response": "✅ 已将《Scaling Rectified Flow Transformers...》添加到前沿快照，请刷新页面", "action": "html_updated"}
6. HTML poll → 收到 done → 显示回复 + "点击刷新页面"
```

---

## 更新分支（"帮我更新 [topic] 的最新动态"）

当用户请求更新时，执行以下步骤：

### U1：搜索最近 30 天新论文

```bash
bash /home/node/.openclaw/workspace/skills/arxiv-watcher/scripts/search_arxiv.sh \
  "<TOPIC_ENGLISH_KEYWORDS>" 20
```

从结果中筛选发布时间在最近 30 天内的论文（检查 `<published>` 字段）。

### U2：LLM 筛选相关新论文

从最近 30 天内发布的论文中，LLM 筛选 2-5 篇与 TOPIC 最相关的，每篇生成：
- `date`：发布日期（YYYY-MM-DD）
- `title`：论文标题
- `url`：arXiv 链接
- `summary`：一句话中文摘要（核心贡献，50 字以内）
- `source`：固定为 "arXiv"

### U3：追加到已有 JSON 并重新生成

```python
import json
from pathlib import Path
from datetime import datetime

# 读取已有数据
data_path = "/home/node/.openclaw/workspace/output/fp_data_{TOPIC}.json"
data = json.loads(Path(data_path).read_text())

# 追加新内容（不覆盖已有数据）
new_updates = [
  {"date": "2026-03-10", "title": "...", "url": "...", "summary": "...", "source": "arXiv"},
  # ...
]
data.setdefault("latest_updates", [])
data["latest_updates"] = new_updates + data["latest_updates"]  # 新的排前面

# 记录更新时间
data["last_updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")

# 写回 JSON
Path(data_path).write_text(json.dumps(data, ensure_ascii=False, indent=2))

# 重新生成 HTML
# python3 generate_report.py --data /home/node/.openclaw/workspace/output/fp_data_{TOPIC}.json --output /home/node/.openclaw/workspace/output/FrontierPilot_{TOPIC}.html
```

### U4：向用户确认

```
✅ {TOPIC} 知识库已更新！

📰 新增 {N} 条最新动态（最近 30 天）：
  · [2026-03-10] 论文标题 — 一句话摘要
  · [2026-03-08] 论文标题 — 一句话摘要

🌐 **立即打开知识库：[http://localhost:7779/](http://localhost:7779/)**
   打开"最新动态"标签页查看新内容
```

---

## 工具路径速查

| 工具 | 容器内路径 / 命令 |
|------|-----------------|
| **SS 按引用量搜索（Step 1A）** | `python3 /home/node/.openclaw/workspace/skills/semantic-scholar/scripts/semantic_scholar.py search --query "<query>" --sort-by citations --limit 30` |
| **SS 按年份搜索（Step 2A）** | `python3 /home/node/.openclaw/workspace/skills/semantic-scholar/scripts/semantic_scholar.py search --query "<query>" --sort-by year --year-after 2022 --limit 25` |
| **SS 真实引用边（Step 1B）** | `python3 /home/node/.openclaw/workspace/skills/semantic-scholar/scripts/semantic_scholar.py references --paper-id <SS_ID> --limit 20` |
| **SS 论文详情含引用边** | `python3 /home/node/.openclaw/workspace/skills/semantic-scholar/scripts/semantic_scholar.py paper --paper-id <SS_ID> --include-references` |
| SS 作者查询（Step 3C） | `python3 /home/node/.openclaw/workspace/skills/semantic-scholar/scripts/semantic_scholar.py author --name "<NAME>"` |
| arXiv 搜索（Step 1C 仅90天内） | `bash /home/node/.openclaw/workspace/skills/arxiv-watcher/scripts/search_arxiv.sh "<query>" <count>` |
| OpenReview 论文搜索（Step 2B × 6） | `python3 /home/node/.openclaw/workspace/skills/openreview-explorer/scripts/search_papers.py --venue {ICLR\|NeurIPS\|ICML} --year {2023\|2024} --limit 50` |
| OpenReview 获取 reviews（Step 2D） | `python3 /home/node/.openclaw/workspace/skills/openreview-explorer/scripts/get_reviews.py --forum-id <id> --venue <VENUE> --year <YEAR>` |
| GitHub 搜索 | `node /home/node/.openclaw/workspace/skills/github-search/scripts/github-search.mjs "<query>" --min-stars 100 --limit 8` |
| Bilibili 搜索 | `agent-reach bilibili search "<query>"` |
| 微信公众号搜索 | `agent-reach wechat search "<query>"` |
| 网页抓取 | `agent-reach web fetch "<url>"` |
| 全网语义搜索 | `agent-reach exa search "<query>"` |

详细的 agent-reach 命令参考见：`agent-reach-guide.md`（同目录）

---

## 注意事项

1. **OpenReview query 过滤限制**：`--query` 仅在客户端对 `limit*5` 条结果做关键词匹配（标题+摘要子串匹配）。Step 2B 统一不带 `--query`，全量拉取后由 LLM / Step 2C 交叉匹配处理，避免漏掉相关论文。

2. **OpenReview 登录**：环境变量已预配置，脚本自动登录。若 get_reviews.py 返回空列表，可能该论文尚无公开 reviews，跳过并注明。

3. **arXiv 定位变更**：arXiv 现在仅作为预印本补充（Step 1C），只保留最近 90 天内的结果。奠基论文搜索已改由 Semantic Scholar `--sort-by citations` 承担（精准且无需 LLM 猜测年份/引用量）。

4. **执行顺序**：Step 1A/1B/1C + 轨道三可同步进行。Step 2B（OR 6次搜索）可并行。Step 2C 需 2A+2B 完成后执行，Step 2D 需 2C 完成后执行。Step 2.5（流派识别）需三轨完成后执行。Step 4.5（Field Overview）需三轨 + 2.5 完成后执行。

5. **资源保存**：执行完成后，将阅读清单保存到 `memory/RESEARCH_LOG.md`，格式与 arxiv-watcher 的日志格式一致。

6. **更新分支要求**：更新时只追加 `latest_updates`，不修改已有的 foundation/frontier/reading_list/top_authors/resources 字段。保护用户已有的知识库内容。
