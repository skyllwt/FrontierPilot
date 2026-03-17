# AutoML 研究日志
日期: 2026-03-15

## 用户背景
刚进组，从事 AutoML 方向科研，需要入门引导

## 阅读清单

### 优先阅读（奠基）
1. Neural Architecture Search with Reinforcement Learning (Zoph & Le, 2016) - arXiv:1611.01578
2. Efficient Neural Architecture Search via Parameter Sharing (ENAS, 2018) - arXiv:1802.03268
3. DARTS: Differentiable Architecture Search (Liu et al., 2018)
4. Auto-WEKA: Combined Selection and Hyperparameter Optimization (2012) - arXiv:1208.3719
5. BOHB: Robust and Efficient Hyperparameter Optimization at Scale (2018) - arXiv:1807.01774
6. Auto-Sklearn 2.0: Hands-free AutoML via Meta-Learning (2020) - arXiv:2007.04074

### 进阶阅读（前沿 NAS 方向）
7. FR-NAS: Forward-and-Reverse Graph Predictor for NAS (ICLR 2024, rejected) - openreview.net/forum?id=fMX07g3prp
8. Lightweight GNAS with Graph Sparsification (ICLR 2024) - openreview.net/forum?id=IefMMX12yk

### 扩展阅读（Reviewer 推荐）
9. NPNAS / NPENAS (reviewer 要求与 FR-NAS 比较)
10. NAO: Neural Architecture Optimization (reviewer 推荐)
11. BANANAS: Bayesian Optimization with Neural Architectures (reviewer 推荐)
12. GUASS: Large-scale Graph Neural Architecture Search, ICML 2022 (reviewer 推荐)


---

# Diffusion Models 最新动态更新
更新日期: 2026-03-16

## 📊 总体趋势（2025-2026 Q1）

### 1. Flow Matching 势头强劲
- Flow Matching 已从 ICLR 2023 的"新范式"发展为多个实际系统的默认选择
- **Riemannian MeanFlow** (arXiv, Mar 2026)：将 Flow Matching 推广到黎曼流形上的单步生成
- **AlphaFlowTSE** (arXiv, Mar 2026)：用 Conditional AlphaFlow 做单步语音提取，flow matching 跨领域应用加速
- **The Quadratic Geometry of Flow Matching** (arXiv, Mar 2026)：分析 fine-tuning 优化动态，揭示语义粒度对齐问题

### 2. DiT (Diffusion Transformer) 已成主流架构
- **DiT-IC** (arXiv, Mar 2026)：用对齐的 Diffusion Transformer 做高效图像压缩，解决采样开销问题
- **DiT4DiT** (arXiv, Mar 2026)：联合建模视频动态和动作，用于机器人控制
- **Contact-Guided DiT** (arXiv, Mar 2026)：用条件扩散 Transformer 生成 E. coli 基因组 3D 结构

### 3. 视频生成仍是核心战场
- **SAW** (arXiv, Mar 2026)：手术动作世界模型，可控可扩展的手术视频生成
- **FC-VFI** (arXiv, Mar 2026)：高保真慢动作视频生成
- **CompoSIA** (arXiv, Mar 2026)：自动驾驶场景合成，解耦交通因子

### 4. 可控生成 & 安全
- **Mitigating Memorization** (arXiv, Mar 2026)：通过区域感知 prompt 增强和多模态复制检测缓解 T2I 模型记忆问题
- **Purify Once, Edit Freely** (arXiv, Mar 2026)：在模型不匹配条件下破解图像保护
- **PhysMoDPO** (arXiv, Mar 2026)：用偏好优化生成物理合理的人形运动

### 5. 统一多模态理解与生成
- **Cheers** (arXiv, Mar 2026)：解耦 patch 细节与语义表示，统一多模态理解和生成

## 🔥 值得关注的论文

| 论文 | 方向 | 亮点 |
|------|------|------|
| Riemannian MeanFlow | Flow Matching | 流形上的单步生成，理论扩展 |
| DiT-IC | 图像压缩 | Diffusion + 压缩，实用方向 |
| SAW | 视频生成 | 手术 AI 世界模型，应用驱动 |
| AlphaFlowTSE | 语音处理 | Flow matching 跨模态，单步推理 |
| Mitigating Memorization | 安全 | T2I 版权问题的实用解法 |
| Cheers | 统一多模态 | 理解+生成一体化趋势 |

## 📌 趋势判断

1. **Flow Matching vs Score-based 的争论基本结束**：Flow Matching 已证明其训练简洁性和跨领域适用性，正在成为默认选择
2. **单步生成继续推进**：从 Consistency Models 到 MeanFlow，单步采样从理论走向实际系统
3. **扩散模型已不仅限于图像**：语音（AlphaFlowTSE）、3D 结构（Contact-Guided DiT）、视频（SAW）全面铺开
4. **安全与可控性成为刚需**：记忆化缓解、版权保护等论文数量激增
5. **DiT 正在替换 U-Net**：几乎所有新工作都采用 Transformer 架构


---

# Diffusion Models 动态更新 #2
更新日期: 2026-03-16 | 覆盖: 2025 Q4 - 2026 Q1

## 🔥 最新重要论文（2026年2-3月）

### MeanFlow / AlphaFlow 家族持续扩张

| 论文 | 日期 | 核心贡献 |
|------|------|---------|
| **Riemannian MeanFlow** | Mar 2026 | Flow Matching 推广到黎曼流形，支持非欧空间单步生成 |
| **Dual-End Consistency Model** | Feb 2026 | 双端一致性训练，改进单步生成质量 |
| **AlphaFlowTSE** | Mar 2026 | Conditional AlphaFlow 做单步语音提取，flow matching 跨模态 |
| **SoFlow** | Dec 2025→Mar 2026 | Solution Flow Models，另一种单步生成框架 |
| **TwinFlow** | Dec 2025→Jan 2026 | 自对抗流，大模型上实现单步生成 |
| **DSFlow** | Feb 2026 | 双监督 + step-aware 架构，单步语音合成 |
| **MeanFlow Transformers** | Nov 2025 | MeanFlow + Representation Autoencoders |
| **AlphaFlow** | Oct 2025 | 理解和改进 MeanFlow 框架 |

### 视频生成新进展

| 论文 | 日期 | 核心贡献 |
|------|------|---------|
| **FrameDiT** | Mar 2026 | 帧级矩阵注意力的 DiT，高效视频生成 |
| **InSpatio-WorldFM** | Mar 2026 | 开源实时帧模型，世界模型 |
| **DiT4DiT** | Mar 2026 | 联合建模视频动态+动作，机器人控制 |
| **SVG-EAR** | Mar 2026 | 稀疏视频生成的误差感知路由 |
| **Chain of Event-Centric Causal Thought** | Mar 2026 | 因果思维链提升物理合理视频生成 |
| **Accelerating T2V with Sparse Attention** | Mar 2026 | 校准稀疏注意力加速视频生成 |
| **Dynamic Chunking DiT** | Mar 2026 | 动态分块，按信息密度分配计算 |
| **MambaDance** | Mar 2026 | 用 Mamba 替代 Transformer 做舞蹈生成 |

### 新兴方向

| 论文 | 日期 | 方向 |
|------|------|------|
| **Dependency-Aware Parallel Decoding (DAPD)** | Mar 2026 | **扩散 LLM**：训练免费的并行解码方法 |
| **Finite Difference Flow Optimization** | Mar 2026 | **RL 后训练**：用于 T2I 模型的强化学习微调 |
| **Fractals made Practical** | Mar 2026 | 将去噪扩散重新诠释为分形迭代函数系统 |
| **Theory of Learning Data Statistics** | Mar 2026 | 扩散模型学习数据统计的理论（从易到难） |
| **Image Generation Models: A Technical History** | Mar 2026 | 全面综述：图像生成技术十年史 |

### 安全与版权（持续热点）

| 论文 | 日期 | 问题 |
|------|------|------|
| **Editing Away the Evidence** | Mar 2026 | 扩散编辑破坏水印，鲁棒水印失效模式 |
| **Purify Once, Edit Freely** | Mar 2026 | 模型不匹配下破解图像保护 |
| **Mitigating Memorization** | Mar 2026 | 区域感知 prompt 增强 + 多模态复制检测 |

### Flow Matching 理论深化

| 论文 | 日期 | 贡献 |
|------|------|------|
| **The Quadratic Geometry of FM** | Mar 2026 | 分析 FM fine-tuning 的优化动态 |
| **Momentum Guidance** | Feb 2026 | 即插即用的 Flow Model 引导方法 |
| **FlowCast** | Feb 2026 | 轨迹预测 + 零成本投机采样 |
| **VeCoR** | Nov 2025→Mar 2026 | 速度对比正则化改进 FM |
| **Learning Straight Flows** | Nov 2025 | 变分流匹配，学习更直的流线 |

## 📊 趋势判断更新

### 已确认的趋势 ✅
1. **Flow Matching 已是主流** — 几乎所有新工作都基于 FM 或兼容 FM
2. **单步生成进入实际部署期** — TwinFlow、AlphaFlow 开始在大模型上验证
3. **DiT 是唯一选择** — U-Net 已完全退出新论文
4. **安全/版权问题爆发** — 水印失效、记忆化、版权论文数量激增

### 新兴信号 📡
1. **扩散 LLM 崛起** — DAPD 表明扩散范式开始进入语言模型领域
2. **RL 后训练扩散模型** — Finite Difference Flow Optimization，类 DPO 的思路
3. **Mamba 进入扩散领域** — MambaDance 表明非 Transformer 架构也在尝试
4. **世界模型热潮** — InSpatio-WorldFM、SAW 等，扩散模型作为世界模拟器
5. **变分/分形新视角** — 理论层面的重新诠释在增加

### 潜在关注点 ⚠️
- MeanFlow 家族论文爆发（AlphaFlow→SoFlow→TwinFlow→Riemannian MeanFlow），可能有同质化风险
- 视频生成效率仍是最大瓶颈（稀疏注意力、动态分块都在解决这个问题）
- 扩散 LLM vs 自回归 LLM 的路线之争可能开始


---

# Diffusion Models 动态更新 #3（今日增量）
更新日期: 2026-03-16 晚间 | 覆盖: 当日新发表

## 🆕 今日新增论文

### 视频生成

| 论文 | arXiv ID | 核心贡献 |
|------|----------|---------|
| **Helios** | 2603.04379 | **14B 自回归扩散模型，单卡 H100 实时 19.5 FPS**。突破：无需 KV-cache/稀疏注意力/量化即可实时；长视频无漂移；训练无需分布式框架。支持 T2V/I2V/V2V |
| **DVD** | 2603.12250 | 确定性视频深度估计，将视频扩散模型转为单次深度回归器，用 163x 更少数据达到 SOTA |

### 应用方向

| 论文 | arXiv ID | 方向 |
|------|----------|------|
| **DiT-IC** | 2603.13* | 对齐的 Diffusion Transformer 用于高效图像压缩 |
| **Diffusion-Based Feature Denoising** | 2603.13* | 扩散模型特征去噪用于脑肿瘤分类（医疗） |
| **Accelerating Stroke MRI** | 2603.13* | 大规模预训练+微调的扩散概率模型加速中风 MRI |
| **SAW** | 2603.13* | 手术动作世界模型，条件视频扩散 |

### 理论与安全

| 论文 | arXiv ID | 方向 |
|------|----------|------|
| **Fractals made Practical** | 2603.13* | 去噪扩散 = 分形迭代函数系统（理论新视角） |
| **Theory of Learning Data Statistics** | 2603.13* | 扩散模型如何从"易到难"学习数据统计 |
| **Editing Away the Evidence** | 2603.13* | 扩散编辑如何破坏鲁棒水印 |
| **Purify Once, Edit Freely** | 2603.13* | 图像保护在模型不匹配条件下的脆弱性 |

### Flow Matching 新应用

| 论文 | arXiv ID | 方向 |
|------|----------|------|
| **3DTCR** | 2603.13* | 条件 Flow Matching 用于热带气旋 3D 重建 |
| **SGMatch** | 2603.13* | Flow Matching 正则化用于非刚性形状匹配 |
| **Mask2Flow-TSE** | 2603.13* | Flow Matching 用于目标说话人提取 |
| **Physics-Constrained DM** | 2603.13* | 物理约束扩散模型合成 3D 湍流数据 |

### 扩散 LLM

| 论文 | arXiv ID | 方向 |
|------|----------|------|
| **DAPD** | 2603.13* | 训练免费的依赖感知并行解码，用自注意力推断 token 间依赖 |

### RL 微调

| 论文 | arXiv ID | 方向 |
|------|----------|------|
| **Finite Difference Flow Optimization** | 2603.13* | RL 后训练 T2I 模型 |
| **Beyond Imitation** | 2603.13* | GRPO 微调扩散导航策略 |
| **PhysMoDPO** | 2603.13* | DPO 生成物理合理人形运动 |

## 📌 新趋势信号

1. **Helios 标志性突破**：首次证明 14B 扩散模型可以在单卡实时运行，且无需传统加速技巧。这对视频生成的实用化意义重大
2. **扩散模型进入医疗影像**：MRI 重建、脑肿瘤分类等方向增多
3. **Flow Matching 继续跨领域扩张**：气象（3DTCR）、几何匹配（SGMatch）、语音（Mask2Flow-TSE）
4. **扩散 LLM 的解码问题**：DAPD 首次解决训练免费的并行解码，扩散 LLM 路线可行性增强
5. **RL + 扩散**成为新组合：GRPO/DPO 与扩散模型结合的论文数量在增长

---

# Diffusion Models 动态更新 #3
更新日期: 2026-03-16 | 补充当日新发现

## 🔥 今日新增热门论文（HF Trending / arXiv）

### 1. Helios: Real Real-Time Long Video Generation Model
- **日期**: Mar 2026 | **机构**: PKU-YuanGroup
- **核心**: 14B 参数自回归扩散模型，实现**实时**长视频生成
- **亮点**: 不依赖传统优化技术即达实时速度，已获 Diffusers/vLLM/SGLang Day-0 支持
- **代码**: https://github.com/PKU-YuanGroup/Helios
- **意义**: 视频生成的实时性门槛正式被突破 🔥🔥

### 2. OpenClaw-RL: Train Any Agent Simply by Talking
- **日期**: Mar 12, 2026 | **机构**: Gen-Verse
- **核心**: 通过对话训练 RL Agent，异步训练 + PRM judges + hindsight-guided distillation
- **代码**: https://github.com/Gen-Verse/OpenClaw-RL
- **意义**: RL + LLM 的训练范式进一步简化，Agent 训练门槛降低

### 3. DVD: Deterministic Video Depth Estimation with Generative Priors
- **日期**: Mar 12, 2026
- **核心**: 将预训练视频扩散模型改编为确定性单次深度回归器
- **亮点**: 使用结构锚点 + 潜流形矫正 + 全局仿射一致性，视频深度估计新 SOTA
- **意义**: 扩散模型的生成先验被成功迁移至判别任务

### 4. SiMPO: Measure Matching for Online Diffusion RL
- **日期**: Mar 10, 2026
- **核心**: 符号测度策略优化，统一扩散策略的 RL 重加权方案
- **亮点**: 解决了 softmax 重加权导致的 over-greedy 问题，能利用负样本反馈
- **意义**: 扩散策略 + RL 的理论和算法进一步成熟

### 5. From Flow to One Step: Real-Time Multi-Modal Trajectory Policies
- **日期**: Mar 10, 2026
- **核心**: 基于隐式最大似然估计的分布蒸馏，从 Flow 模型一步生成轨迹策略
- **意义**: Flow Matching → 单步生成在机器人控制领域的实际应用

### 6. Cheers: Decoupling Patch Details from Semantic Representations
- **日期**: Mar 13, 2026 | **作者**: 清华 (Zhiyuan Liu 组)
- **核心**: 解耦 patch 细节与语义表示，统一多模态理解和生成
- **意义**: 统一多模态架构的重要工作，可能影响下一代多模态模型设计

### 7. Contact-Guided 3D Genome Structure via Diffusion Transformers
- **日期**: Mar 8, 2026
- **核心**: 条件 DiT 框架生成 E. coli 基因组 3D 构象
- **意义**: 扩散模型进入计算生物学领域

## 📊 AutoML/NAS 最新动态

### 新趋势：LLM for AutoML
| 论文 | 日期 | 核心 |
|------|------|------|
| **NNGPT** | Nov 2025 | LLM 作为自我改进的 AutoML 引擎 |
| **LLM as a Neural Architect** | Dec 2025 | LLM 可控生成图像描述模型架构 |
| **confopt** | Jul 2025 | Frank Hutter 组：梯度 one-shot NAS 库 |
| **Auto-nnU-Net** | May 2025 | 自动化医学图像分割的 NAS 框架 |
| **SEAL** | May 2025 | NAS 用于增量学习的可扩展架构搜索 |

### 趋势判断
- **NAS 方向热度下降**：传统 NAS 论文明显减少，重心转向 LLM-based AutoML
- **LLM 正在取代搜索空间**：NNGPT 等表明用 LLM 直接设计架构成为新范式
- **confopt 值得关注**：Frank Hutter 组的 one-shot NAS 工具库，可能是未来实验标准

## 📡 综合趋势更新

### 确认趋势 ✅ (新增)
1. **视频生成进入实时时代** — Helios 14B 实时生成是里程碑事件
2. **扩散策略 + RL 融合加速** — SiMPO、From Flow to One Step 等密集出现
3. **扩散模型成为通用生成基础设施** — 从图像到语音到3D基因组，无处不在
4. **统一多模态是下一代架构方向** — Cheers 等工作预示理解+生成融合

### 新兴信号 📡 (新增)
1. **Agent 训练民主化** — OpenClaw-RL 等降低 RL agent 训练门槛
2. **生成先验迁移到判别任务** — DVD 利用扩散模型做深度估计，思路新颖
3. **LLM for NAS** — AutoML 范式从搜索转向 LLM 推理

### 值得深入的论文 📖
- **Helios** — 实时视频生成的技术细节值得研究
- **SiMPO** — 扩散策略的 RL 训练，理论贡献大
- **Cheers** — 统一多模态，可能是一条大主线
- **confopt** — 如果做 NAS 实验，这个工具库值得关注


## Agent Serving System Optimization — 2026-03-17

**方向**: Agent 服务系统优化
**分类**: 系统类（核心贡献是工程实现/性能优化）
**核心问题**: 如何高效为 LLM Agent 多轮异步有状态工作负载提供推理服务

### 三条技术路线
1. **Core LLM Serving → Agent 扩展**: vLLM(PagedAttention) → SGLang(RadixAttention) → FlashInfer(kernel)
2. **Agent-Native Serving**: Nalar(futures/状态管理/两级控制) → SDN-inspired Serving → IsolateGPT(安全隔离)
3. **调度与 QoS**: Niyama(细粒度QoS) → NexusSched(两层预测调度) → CascadeServe(模型级联)

### 阅读优先级
1. vLLM/PagedAttention (基础)
2. Nalar arXiv:2601.05109 (Agent serving 最完整框架)
3. SGLang (复杂 LLM 程序执行)
4. FlashInfer (kernel 优化)

### 关键研究者
- Ion Stoica (UC Berkeley) — vLLM/SGLang 幕后核心
- Saurabh Agarwal — Nalar + SDN Agentic Serving 作者

### 数据源
- Semantic Scholar: API 限流，未能拉取引用数据
- arXiv: 成功搜索，获取 8 篇核心论文
- GitHub: vLLM(73k), SGLang(25k), Mooncake(5k) 等
- OpenReview: 系统类 topic 跳过

### 知识库
- HTML: output/FrontierPilot_Agent_Serving.html
- JSON: output/fp_data_Agent_Serving.json
