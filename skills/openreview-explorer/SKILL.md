---
name: openreview-explorer
description: Search papers on OpenReview and retrieve peer reviews and rebuttals from major ML conferences (ICLR, NeurIPS, ICML). Core skill for FrontierPilot's Knowledge Exploration engine.
version: 1.0.0
---

# OpenReview Explorer

This skill fetches papers, peer reviews, and author rebuttals from OpenReview — treating the review process as structured learning material for newcomers entering a research field.

## Why Reviews Matter

Peer reviews reveal what the field actually cares about: common weaknesses, evaluation standards, and how top authors respond to criticism. This is knowledge that takes years to accumulate informally — FrontierPilot surfaces it directly.

## Python Interpreter

Always use: `python3` (available in the OpenClaw container environment)

## Capabilities

### 1. Search papers by keyword + venue

```bash
python3 /home/node/.openclaw/workspace/skills/openreview-explorer/scripts/search_papers.py \
  --query "automl" \
  --venue "ICLR" \
  --year 2024 \
  --limit 5
```

### 2. Get reviews + rebuttal for a paper

```bash
python3 /home/node/.openclaw/workspace/skills/openreview-explorer/scripts/get_reviews.py \
  --forum-id <FORUM_ID> \
  --venue "ICLR" \
  --year 2024
```

### 3. Get conference papers (all from a venue/year)

```bash
python3 /home/node/.openclaw/workspace/skills/openreview-explorer/scripts/search_papers.py \
  --venue "ICLR" \
  --year 2024 \
  --limit 10
```

## Workflow for Knowledge Exploration

1. User provides a topic (e.g., "diffusion models for image generation")
2. Run `search_papers.py` to find top relevant papers from recent ICLR/NeurIPS/ICML
3. For each promising paper, run `get_reviews.py` to retrieve:
   - Reviewer ratings and summaries
   - Detailed strengths/weaknesses
   - Author rebuttal (how the authors defended their work)
4. Synthesize: What do reviewers consistently praise? What weaknesses appear? What does the rebuttal reveal about the authors' intent?
5. Save synthesis to `memory/RESEARCH_LOG.md`

## Output Format

Papers are returned as JSON. Present them as:
- Title, authors, venue, year
- Abstract excerpt
- Forum ID (needed for get_reviews.py)

Reviews are returned with:
- Rating (e.g., "8: accept, good paper")
- Summary, strengths, weaknesses
- Confidence score
- Rebuttal excerpt

## Environment Variables

The scripts read credentials from environment. These are pre-configured:
- `OPENREVIEW_USERNAME`: weitong.qian@stu.pku.edu.cn
- `OPENREVIEW_PASSWORD`: PKU@lltqwt1121
- `OPENREVIEW_BASE_URL`: https://api2.openreview.net

## Supported Venues

| Venue | Invitation Pattern |
|-------|-------------------|
| ICLR 2024 | ICLR.cc/2024/Conference/-/Submission |
| ICLR 2023 | ICLR.cc/2023/Conference/-/Submission |
| NeurIPS 2024 | NeurIPS.cc/2024/Conference/-/Submission |
| ICML 2024 | ICML.cc/2024/Conference/-/Submission |

## Error Handling

- If a paper has no reviews yet (e.g., under review), the script returns an empty list — note this to the user
- Rate limit: space out requests for large batches (>20 papers)
- If login fails, fall back to anonymous mode (public papers only, no reviews)
