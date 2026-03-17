# agent-reach 命令参考

`agent-reach` 是容器内预装的 CLI 工具，提供 Bilibili、微信公众号、网页抓取和全网语义搜索能力。

---

## 常用命令

### Bilibili 视频搜索

```bash
agent-reach bilibili search "关键词"
```

示例：
```bash
agent-reach bilibili search "AutoML 自动机器学习 教程"
agent-reach bilibili search "diffusion model 扩散模型 入门"
agent-reach bilibili search "强化学习 从零开始"
```

返回：视频标题、UP主名称、播放量、发布时间、链接。

---

### 微信公众号搜索

```bash
agent-reach wechat search "关键词"
```

示例：
```bash
agent-reach wechat search "AutoML 综述"
agent-reach wechat search "大模型 RAG 技术解析"
agent-reach wechat search "神经架构搜索 NAS"
```

返回：文章标题、公众号名称、发布时间、链接。

---

### 网页内容抓取

```bash
agent-reach web fetch "https://example.com/article"
```

示例：
```bash
agent-reach web fetch "https://openreview.net/forum?id=XXXXX"
agent-reach web fetch "https://arxiv.org/abs/2301.00001"
```

返回：页面的主要文字内容（Markdown 格式）。

---

### 全网语义搜索（Exa）

```bash
agent-reach exa search "查询语句"
```

示例：
```bash
agent-reach exa search "best AutoML frameworks 2024"
agent-reach exa search "neural architecture search survey recent advances"
```

返回：相关网页链接和摘要，支持语义匹配（不依赖关键词精确匹配）。

---

## 使用建议

| 场景 | 推荐命令 |
|------|---------|
| 找中文视频教程 | `bilibili search "<方向> 教程"` 或 `bilibili search "<方向> 入门"` |
| 找领域科普文章 | `wechat search "<方向> 综述"` 或 `wechat search "<方向> 入门"` |
| 抓取论文页面正文 | `web fetch "<arxiv 或 openreview URL>"` |
| 找英文技术博客 | `exa search "<topic> tutorial 2024"` |
| 找顶尖课题组主页 | `exa search "<topic> research group lab"` |

---

## 注意事项

- 所有命令在容器环境中直接运行，无需配置额外环境变量。
- Bilibili 和微信搜索返回的结果数量由平台决定，通常 3-10 条。
- `exa search` 适合英文内容的语义检索，中文效果弱于 bilibili/wechat 专项搜索。
- `web fetch` 适合对已知 URL 做内容提取，不适合探索性搜索。
