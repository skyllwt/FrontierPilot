# FrontierPilot data schema (fp_data_{TOPIC}.json)

`generate_report.py` reads a single JSON file and produces a self-contained HTML knowledge base.

## Top-level fields

- `topic` (string): topic name (English recommended)
- `topic_zh` (string, optional): Chinese name for display
- `field_overview` (string): 300–400 Chinese briefing for beginners
- `foundation` (array): foundational papers (see below)
- `frontier` (array): frontier papers (see below)
- `reading_list` (array): ordered reading list items
- `top_authors` (array): active researchers / labs
- `resources` (object): `{ github: [], bilibili: [], wechat: [] }`
- `paper_clusters` (array): clustering for graph subgraphs
- `graph_mermaid` (string): Mermaid `flowchart LR` text (subgraph per cluster)
- `latest_updates` (array): latest arXiv updates (append-only in update mode)
- `last_updated_at` (string, optional): `YYYY-MM-DD HH:MM`

## foundation item

Required (minimum):
- `year` (number)
- `title` (string)
- `authors` (array of string)
- `url` (string)
- `citation_count` (number, optional)
- `is_key` (bool, optional)

Recommended:
- `description` (string)
- `problem_solved` (string)
- `problem_left` (string)
- `node_id` (string): stable node id used by `graph_mermaid`

## frontier item

Required (minimum):
- `title` (string)
- `venue` (string)
- `year` (number)
- `url` (string)
- `reviews` (array, can be empty)

Optional:
- `forum_id` (string): OpenReview forum id (if available)
- `avg_rating` (number|null)
- `citation_count` (number)
- `node_id` (string)

## review item

- `rating` (string or number)
- `strengths` (string)
- `weaknesses` (string)
- `related_work` (array of string, optional)

## reading_list item

- `title` (string)
- `type` (string enum): `foundation` | `frontier` | `recommended`
- `reason` (string)
- `url` (string)

## resources

Always include all three keys:
- `github`: array of repos `{name, url, stars?, description?}`
- `bilibili`: array of videos `{title, url, view_count?}`
- `wechat`: array of articles `{title, url}`

## paper_clusters

- `id` (string)
- `name` (string)
- `paper_node_ids` (array of string): must match node ids used in `graph_mermaid`

