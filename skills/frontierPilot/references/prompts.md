# FrontierPilot LLM Prompt Templates

## Step 2.5 — 流派聚类（paper_clusters）

```
基于以下论文列表，将其分为 2-4 个方法族（methodological families）。
每篇论文只属于一个流派。流派命名要简洁（如 "Score-based SDE"、"Flow-based Samplers"、"Latent Methods"）。

规则：
- 按核心技术思路分组，不按发表时间
- 每组至少 2 篇论文
- 输出纯 JSON，不加 markdown 代码块

输出格式（JSON 数组）：
[
  {
    "id": "cluster_sde",
    "name": "Score-based / SDE Methods",
    "subgraph_style": "fill:#eff6ff,stroke:#2563eb",
    "paper_node_ids": ["N2019_NCSN", "N2020_DDPM"]
  }
]

可用 subgraph_style（按顺序分配，每个 cluster 用不同颜色）：
- "fill:#eff6ff,stroke:#2563eb"  （蓝）
- "fill:#faf5ff,stroke:#7c3aed"  （紫）
- "fill:#f0fdf4,stroke:#059669"  （绿）
- "fill:#fff7ed,stroke:#ea580c"  （橙）

paper_node_ids 中的 ID 必须与 graph_mermaid 中的 Mermaid 节点 ID 完全一致。

论文列表：
[PAPER_LIST — 格式：node_id | year | title | 摘要前 100 字]
```

---

## Step 4.5 — Field Overview（专家视角综述）

```
基于以下信息，用 300-400 字写一段专家视角综述，面向研究新手。

结构要求（每段一个主题，用空行分隔）：
1. 该领域的本质问题是什么（一句话，避免术语堆砌）
2. 2023-2024 年的主要共识（被多数 reviewer 肯定的方向）
3. 当前主要争议或开放问题（被 reviewer 反复质疑的点）
4. 新手最应该优先关注什么（Top 1-2 个建议）

写作风格：像资深博士在组会给新生做 5 分钟 briefing。
- 第一段直接给核心判断，不要铺垫
- 不要写成论文摘要或综述风格
- 不要用"本领域"、"综上所述"等套话

领域名称：[TOPIC]
奠基论文摘要（节选，各 100 字）：[FOUNDATION_ABSTRACTS]
Reviewer 评价汇总（strengths + weaknesses 各 3-5 条）：[REVIEWER_INSIGHTS]
```
