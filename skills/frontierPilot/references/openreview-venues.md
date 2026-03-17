# OpenReview Venue 选择指南

## 支持的 venue-year 组合

| Venue | 可用年份 | 适用 topic |
|-------|---------|-----------|
| **ICLR** | 2023 / 2024 / 2025 / 2026 | 所有 ML/AI topic，**必选** |
| **NeurIPS** | 2023 / 2024 / 2025 | 所有 ML/AI topic，**必选** |
| **ICML** | 2023 / 2024 / 2025 | 所有 ML/AI topic，**必选** |
| **COLM** | 2024 / 2025 | Language model、LLM、NLP、对话系统 |
| **CoRL** | 2023 / 2024 | Robotics、Embodied AI、强化学习 |
| **UAI** | 2023 / 2024 | 概率图模型、贝叶斯方法、因果推断 |

## 选 venue 规则

1. **必选**：ICLR + NeurIPS + ICML 各取最近两年 → 共 6 个 venue-year
2. **按需追加**：topic 与 COLM/CoRL/UAI 高度相关时，追加 1-2 年（总数控制在 8-10 个）
   - topic = "LLM Reasoning" → 追加 COLM 2024/2025
   - topic = "Robot Manipulation" → 追加 CoRL 2023/2024
   - topic = "Bayesian Methods" → 追加 UAI 2023/2024

## 执行命令模板（并行执行，统一格式）

```bash
python3 /home/node/.openclaw/workspace/skills/openreview-explorer/scripts/search_papers.py \
  --venue "<VENUE>" --year <YEAR> --limit 50
```

**注意**：不加 `--query`，全量拉取后由 Step 2C 的 LLM 交叉匹配，避免漏论文。

## 返回格式

```json
{
  "papers": [
    {
      "forum_id": "abc123",
      "title": "...",
      "abstract": "...",
      "authors": ["Name1", "Name2"],
      "venue": "ICLR",
      "year": 2024,
      "url": "https://openreview.net/forum?id=abc123"
    }
  ],
  "total": 312
}
```

6 个必选 venue-year 汇总约 300-500 篇候选，供 Step 2C 交叉匹配。
