---
name: frontierPilot
description: Use when the user wants to explore a research topic/field (0→entry package) or update a topic’s latest updates. Produces a growing HTML knowledge base + fp_data_{TOPIC}.json via Semantic Scholar + OpenReview + arXiv + GitHub + Bilibili/WeChat. Do NOT use for pure Q&A, coding help, or when the user doesn’t want file outputs.
---

# FrontierPilot

## Preconditions

- Recommended: `SS_API_KEY` (avoids rate limiting + exec 30s timeout failures).
- **If `SS_API_KEY` is NOT set (degraded mode):**
  - Use smaller SS queries: `search --limit 15` (not 30).
  - Fetch real citation edges for fewer papers: run `paper --include-references` only for **top 3–4** foundations (not 6).
  - If you see `[SS] Rate limited` / HTTP 429, **stop and wait ~5 minutes** before retrying (don’t loop inside a 30s exec window).
- OpenReview works anonymously; credentials improve access/throughput when needed.
- 参考文档（按需读取，勿提前加载）：`references/data-schema.md`（JSON 字段）、`references/prompts.md`（LLM 提示词）、`references/openreview-venues.md`（venue 选择规则）、`references/runbook.md`（故障排查）

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
    │       ※ 社交主动探索（小红书专家 / 微信群发现）由知识库内智能助手触发，
    │         非主流程步骤；chat_server.py 启动后自动支持，无需 agent 编排
    │
    ├── Step 2.5：LLM 识别流派 → paper_clusters（2-4个方法族）
    │
    ├── Step 4.5：合成 Field Overview（专家视角综述，300-400字）
    │       输入：foundation摘要 + reviewer strengths/weaknesses
    │       输出：field_overview 字符串
    │
    ├── Step 3C：作者提取（可与轨道三并行，依赖轨道一+二数据）
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

目标：确定奠基论文（foundation）+ 真实引用边（graph_mermaid）。

#### Step 1A：Semantic Scholar 引用量排序搜索（主力）

```bash
python3 /home/node/.openclaw/workspace/skills/semantic-scholar/scripts/semantic_scholar.py \
  search --query "<TOPIC_ENGLISH_KEYWORDS>" --sort-by citations --limit 30
```

从结果中选取 6–8 篇作为 `foundation`（优先覆盖时间跨度）。

#### Step 1B：获取真实引用边（构建 graph_mermaid 用）

对前 3 篇奠基论文，用 `paper --include-references` 获取每篇论文及其前 10 条引用：

```bash
# 对每篇奠基论文执行一次（共 3 次，逐一执行）
python3 /home/node/.openclaw/workspace/skills/semantic-scholar/scripts/semantic_scholar.py \
  paper --paper-id <SS_PAPER_ID_1> --include-references

python3 /home/node/.openclaw/workspace/skills/semantic-scholar/scripts/semantic_scholar.py \
  paper --paper-id <SS_PAPER_ID_2> --include-references

# ... 对其余 1 篇重复
```

> **注意**：不要用 `references` 子命令——其嵌套字段在 SS API 中存在兼容性问题。
> `paper --include-references` 返回的 10 条引用对于奠基论文之间的交叉引用提取已足够。

只提取 foundation 集合内部的相互引用边，写入 `graph_mermaid`（不可编造）。

#### Step 1C：arXiv 最近 90 天预印本补充（可选，次要）

```bash
bash /home/node/.openclaw/workspace/skills/arxiv-watcher/scripts/search_arxiv.sh "<TOPIC_ENGLISH_KEYWORDS>" 20
```

只保留 `<published>` 在最近 90 天内的论文（可为 0 篇）。

**轨道一输出**：写入 JSON 的 `foundation` 数组（每项含 year/title/authors/description/problem_solved/problem_left/url/is_key/citation_count），并在 chat 中简要汇报演进逻辑和真实引用边（来自 Step 1B）。

---

### 轨道二：Frontier Track — 前沿论文分析

目标：写入 `frontier`（优先带 OpenReview reviews），并扩展阅读清单（reviewer related work）。

---

#### Step 2.0：Topic 类型判断（决定后续路径）

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

从结果中选出 8–10 篇候选，记录 `title` 用于 Step 2C 交叉匹配。

#### Step 2B：OpenReview 多 venue-year 并行搜索

Venue 选择规则和完整命令见 `references/openreview-venues.md`。

必选：ICLR + NeurIPS + ICML 各取最近两年（共 6 个）。命令格式统一为：

```bash
python3 /home/node/.openclaw/workspace/skills/openreview-explorer/scripts/search_papers.py \
  --venue "<VENUE>" --year <YEAR> --limit 50
```

⚠️ **不加 `--query`**，全量拉取后由 Step 2C 的 LLM 交叉匹配，避免漏论文。6 个 venue-year 汇总约 300-500 篇候选。

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

**操作**：使用 Step 2A 结果写入 `frontier`。设 `avg_rating: null`，用 `citation_count`（从 SS `citationCount` 字段读取）替代评分，`venue` 保留完整会议名（如 `"ASPLOS 2026"`），`reviews: []`。字段格式见 `references/data-schema.md`。

---

#### Step 2F：提取 Related Work（关键亮点功能）

对每篇论文的所有 reviews，用 LLM 解析 `weaknesses` 和 `questions` 字段，提取 reviewer **明确要求作者比较或解释的 related work**。

提取逻辑：
- 找形如"为什么不与 [论文X] 比较"、"[方法Y] 似乎与你的工作很相关"、"你的方法相比 [工作Z] 有何优势"的表述
- 提取被提及的论文名称或方法名称
- 将这些自动加入阅读清单（标注来源：reviewer 推荐）

**轨道二输出**：写入 JSON 的 `frontier` 数组（每项含 title/forum_id/venue/year/url/avg_rating/reviews），`reviews` 每项含 rating/strengths/weaknesses/related_work。在 chat 中简要汇报每篇论文的评分和 reviewer 核心观点。

---

### Step 2.5：流派聚类识别（三轨完成后执行）

将 foundation + frontier 所有论文按方法族分为 2-4 个 cluster。

使用 `references/prompts.md` 中的"Step 2.5"prompt，输入 `node_id | year | title | 摘要前100字`。

**输出**：写入 JSON `paper_clusters`（`[{id, name, subgraph_style, paper_node_ids}]`）。
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

**轨道三输出**：写入 JSON 的 `resources` 对象（含 github/bilibili/wechat 三个列表）。⚠️ 三个列表必须全部存在；如果某平台结果为空，写入空数组但在 chat 中注明"搜索无结果，建议手动搜索：[关键词]"。

---

### Step 3C：作者提取（可与轨道三并行执行）

从轨道一和轨道二收集到的论文中，提取高频作者：

1. 汇总 `foundation` 论文的 `authors` 字段 + `frontier` 论文的 authors 字段
2. 统计高频作者（出现 ≥ 2 次，或为明确的一作/通讯）
3. 对 Top 5-6 位作者，用 Semantic Scholar 查询补充机构和论文数（可选）：

```bash
python3 /home/node/.openclaw/workspace/skills/semantic-scholar/scripts/semantic_scholar.py \
  author --name "<AUTHOR_NAME>"
```

若 Semantic Scholar 无法查询，直接从论文元数据提取可用信息。

**输出**（写入 JSON 的 `top_authors` 字段）：每项含 name/institution/papers_count/recent_work/url。若无法获取完整机构信息，只填 name + recent_work 也可，不要阻塞流程。

---

### Step 4.5：合成 Field Overview（三轨 + Step 2.5 完成后）

输入：foundation abstracts + reviewer strengths/weaknesses 汇总。使用 `references/prompts.md` 中的"Step 4.5"prompt。

**输出**：300-400 字中文专家综述，写入 JSON `field_overview`。

---

### Step 4.8：向用户汇报数据收集结果（生成 HTML 前）

三轨数据 + Step 4.5 完成后，在 chat 中按 checklist 简要汇报：Roadmap / Frontier / Reading list / Resources(GitHub+Bilibili+WeChat) / Top authors。

然后继续执行 Step 5。

---

### Step 5：生成成长型知识库 HTML + 启动智能助手

三轨数据 + Field Overview + Top Authors 收集完成后，将所有结果整理为 JSON，**写入** `fp_data_{TOPIC}.json`，再调用 generate_report.py。

**⚠️ 写入 JSON 的正确方式**（禁止使用 `cat > file << 'EOF'`，会因转义和 delimiter 冲突导致解析失败）：

使用 `write_fp_json.py` 从 stdin 写入并校验：
```bash
python3 /home/node/.openclaw/workspace/skills/frontierPilot/scripts/write_fp_json.py \
  /home/node/.openclaw/workspace/output/fp_data_{TOPIC}.json << 'ENDOFJSON'
（粘贴**纯 JSON**：不要手工转义引号、不要加注释；如上游输出为 ```json ... ```，脚本会自动去掉代码块包裹）
ENDOFJSON
```
delimiter 用 `ENDOFJSON`；若 JSON 内容含该字符串，改用 `__FP_JSON_END__`。

然后生成 HTML：
```bash
mkdir -p /home/node/.openclaw/workspace/output
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
OPENCLAW_GATEWAY_TOKEN="$OPENCLAW_GATEWAY_TOKEN" \
OPENCLAW_GATEWAY_PORT="${OPENCLAW_GATEWAY_PORT:-18789}" \
nohup python3 /home/node/.openclaw/workspace/skills/frontierPilot/scripts/chat_server.py \
  --data /home/node/.openclaw/workspace/output/fp_data_{TOPIC}.json \
  --html /home/node/.openclaw/workspace/output/FrontierPilot_{TOPIC}.html \
  --port 7779 > /tmp/fp_chat.log 2>&1 &
```

> **注意**：`chat_server.py` 启动后完全自主运行（SSE 流式通信 + OpenClaw Gateway function calling），用户在 HTML 页面的所有操作（添加论文、更新动态、分析论文、问答、社交探索）均由服务器自行处理，agent 无需再与其交互。

```
✅ {TOPIC} 成长型知识库已生成！

🌐 **立即打开知识库：[http://localhost:7779/](http://localhost:7779/)**

🤖 智能助手已就绪，在浏览器中直接输入指令：
  · 把 [论文名] 添加到知识图谱
  · 更新最新动态
  · 分析 arXiv 论文：[URL]
  · 帮我在小红书找这个方向的博主和微信群
  · 帮我给 [作者名] 写一封学术交流邮件
```

JSON 字段完整说明见 `references/data-schema.md`。核心顶层字段：`topic` / `topic_zh` / `field_overview` / `foundation` / `frontier` / `reading_list` / `top_authors` / `resources` / `paper_clusters` / `graph_mermaid` / `latest_updates`。

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

1. 读取已有 `fp_data_{TOPIC}.json`
2. 将 U2 筛选出的新论文 prepend 到 `latest_updates` 数组（新的排前面），更新 `last_updated_at` 为当前时间
3. 写回 JSON 文件，然后重新执行 `generate_report.py --data ... --output ...` 生成 HTML

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
| **SS 论文详情 + 引用边（Step 1B）** | `python3 /home/node/.openclaw/workspace/skills/semantic-scholar/scripts/semantic_scholar.py paper --paper-id <SS_ID> --include-references` |
| SS 作者查询（Step 3C） | `python3 /home/node/.openclaw/workspace/skills/semantic-scholar/scripts/semantic_scholar.py author --name "<NAME>"` |
| arXiv 搜索（Step 1C 仅90天内） | `bash /home/node/.openclaw/workspace/skills/arxiv-watcher/scripts/search_arxiv.sh "<query>" <count>` |
| OpenReview 论文搜索（Step 2B × 6） | `python3 /home/node/.openclaw/workspace/skills/openreview-explorer/scripts/search_papers.py --venue {ICLR\|NeurIPS\|ICML} --year {2023\|2024} --limit 50` |
| OpenReview 获取 reviews（Step 2D） | `python3 /home/node/.openclaw/workspace/skills/openreview-explorer/scripts/get_reviews.py --forum-id <id> --venue <VENUE> --year <YEAR>` |
| GitHub 搜索（Step 3A） | `node /home/node/.openclaw/workspace/skills/github-search/scripts/github-search.mjs "<query>" --min-stars 100 --limit 8` |
| Bilibili + 微信搜索（Step 3B） | `python3 /home/node/.openclaw/workspace/skills/frontierPilot/scripts/search_social.py --topic "<query>" --topic-zh "<中文>" 2>/dev/null` |

---

## 注意事项

- **执行顺序**：Track 1 + Track 3 立即并行。Step 2C 等 2A+2B；Step 2D 等 2C；Step 2.5 等三轨完成；Step 4.5 等 Step 2.5。
- **graph_mermaid 引用边**：必须来自 Step 1B 的 SS 真实数据，不可 LLM 编造。
- **get_reviews 返回空**：该论文暂无公开 reviews，跳过并注明，不阻塞流程。
- **更新分支**：只追加 `latest_updates`，保护已有 foundation/frontier/reading_list/top_authors/resources。
- **完成后**：将阅读清单追加到 `memory/RESEARCH_LOG.md`。
