#!/usr/bin/env python3
"""
FrontierPilot Demo Data Preloader

Generates two pre-cached JSON data files for reliable demo:
  - demo_cache/diffusion_models_v1.json  → initial knowledge base
  - demo_cache/diffusion_models_v2.json  → after "one week later" update (proactive update demo)

Usage:
  python3 preload_demo.py [--output-dir demo_cache] [--topic diffusion|automl]

This eliminates API dependencies during the live demo, enabling a fast, reliable presentation.
The v2 file simulates FrontierPilot proactively discovering new papers and updating the knowledge base.
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path


SCRIPT_DIR = Path(__file__).parent
GENERATE_REPORT = SCRIPT_DIR / "generate_report.py"
SOCIAL_AGENT = SCRIPT_DIR / "social_agent.py"


# ─────────────────────────────────────────────────────────────────────────────
# Pre-baked demo data: Diffusion Models v1 (initial knowledge base)
# ─────────────────────────────────────────────────────────────────────────────

DIFFUSION_V1 = {
    "topic": "Diffusion Models",
    "topic_zh": "扩散模型",
    "generated_at": "2026-03-08 10:00",
    "field_overview": (
        "扩散模型的本质问题很简单：如何将一张纯噪声图像逐步「去噪」成一张有意义的图片？"
        "这个看似简单的问题，在 2020-2022 年间引发了生成式 AI 的最大一次范式转变。\n\n"
        "2024 年的主要共识是：扩散模型已经赢得了图像生成的主战场，但计算效率仍是核心痛点。"
        "Reviewer 在几乎所有顶会论文中都会追问「采样速度」——从 DDPM 的 1000 步采样"
        "到 DDIM 的 50 步、再到 Consistency Models 的单步生成，这条效率优化主线贯穿至今。\n\n"
        "当前最大的争议点有两个：第一，Flow Matching 和传统 score-based 方法谁更有前途？"
        "（多数 reviewer 认为 flow matching 的训练目标更简洁，但实验优势仍不够显著）"
        "第二，扩散模型在视频生成中的可扩展性如何？（Sora 的成功让所有人都在追赶，"
        "但对显存和训练时间的需求让学术界难以复现）\n\n"
        "新手建议：先读 DDPM（理解核心数学），再读 DDIM（理解加速），"
        "最后读 Latent Diffusion（理解为什么 Stable Diffusion 能在消费级 GPU 上跑）。"
        "这三篇按顺序读完后，你对整个领域的 80% 内容都会有基本判断力。"
    ),
    "foundation": [
        {
            "year": 2015,
            "title": "Deep Unsupervised Learning using Nonequilibrium Thermodynamics",
            "authors": ["Sohl-Dickstein et al."],
            "description": "首次将热力学非平衡过程引入生成模型，提出扩散过程的理论基础",
            "url": "https://arxiv.org/abs/1503.03585",
            "problem_solved": "为扩散生成模型建立数学基础",
            "problem_left": "图像质量远不如 GAN，纯理论验证",
            "is_key": False,
            "citation_count": 3200,
            "node_id": "N2015_Deep_Unsuperv",
            "arxiv_id": "1503.03585",
            "ss_paper_id": "2dcef55a07f8607a819c21fe84131ea269cc2e3c"
        },
        {
            "year": 2019,
            "title": "Generative Modeling by Estimating Gradients of the Data Distribution (NCSN)",
            "authors": ["Song & Ermon"],
            "description": "提出 score-based 生成范式，证明去噪分数匹配可以高质量采样",
            "url": "https://arxiv.org/abs/1907.05600",
            "problem_solved": "建立 score-based 生成模型方法论",
            "problem_left": "与 DDPM 的连接尚未清晰",
            "is_key": False,
            "citation_count": 4100,
            "node_id": "N2019_NCSN",
            "arxiv_id": "1907.05600",
            "ss_paper_id": "965359b3008ab50dd04e171551220ec0e7f83aba"
        },
        {
            "year": 2020,
            "title": "Denoising Diffusion Probabilistic Models (DDPM)",
            "authors": ["Ho et al.", "NeurIPS 2020"],
            "description": "将扩散过程与 Markov chain 结合，确立现代扩散模型的核心范式",
            "url": "https://arxiv.org/abs/2006.11239",
            "problem_solved": "首次实现超越 GAN 的图像生成质量",
            "problem_left": "采样极慢（需 1000 步），计算开销巨大",
            "is_key": True,
            "citation_count": 18000,
            "node_id": "N2020_DDPM",
            "arxiv_id": "2006.11239",
            "ss_paper_id": "5c126ae3421f05768d8edd97ecd44b1364e2c99a"
        },
        {
            "year": 2021,
            "title": "Denoising Diffusion Implicit Models (DDIM)",
            "authors": ["Song et al.", "ICLR 2021"],
            "description": "将采样过程从随机 Markov 改为确定性过程，实现 20× 加速",
            "url": "https://arxiv.org/abs/2010.02502",
            "problem_solved": "将采样步数从 1000 降至 50，使实际应用成为可能",
            "problem_left": "仍需多步采样，实时生成仍有差距",
            "is_key": True,
            "citation_count": 5800,
            "node_id": "N2021_DDIM",
            "arxiv_id": "2010.02502",
            "ss_paper_id": "014576b866078524286802b1d0e18628520aa886"
        },
        {
            "year": 2022,
            "title": "High-Resolution Image Synthesis with Latent Diffusion Models (LDM)",
            "authors": ["Rombach et al.", "CVPR 2022"],
            "description": "将扩散过程压缩到低维 latent space，大幅降低计算成本，催生 Stable Diffusion",
            "url": "https://arxiv.org/abs/2112.10752",
            "problem_solved": "使高分辨率生成在消费级 GPU 上可行",
            "problem_left": "latent 空间的表达能力有上限",
            "is_key": True,
            "citation_count": 12000,
            "node_id": "N2022_LDM",
            "arxiv_id": "2112.10752",
            "ss_paper_id": "c10075b3746a9f3dd5811970e93c8ca3ad39b39d"
        },
        {
            "year": 2023,
            "title": "Consistency Models",
            "authors": ["Song et al.", "ICML 2023"],
            "description": "训练模型直接从任意噪声级别映射到干净图像，实现单步生成",
            "url": "https://arxiv.org/abs/2303.01469",
            "problem_solved": "单步生成，速度提升数十倍",
            "problem_left": "训练不稳定，质量略低于多步方法",
            "is_key": False,
            "citation_count": 2100,
            "node_id": "N2023_CM",
            "arxiv_id": "2303.01469",
            "ss_paper_id": "ac974291d7e3a152067382675524f3e3c2ded11b"
        }
    ],
    "frontier": [
        {
            "title": "Flow Matching for Generative Modeling",
            "forum_id": "PqvMRDCJT9t",
            "venue": "ICLR",
            "year": 2023,
            "url": "https://openreview.net/forum?id=PqvMRDCJT9t",
            "avg_rating": 7.3,
            "node_id": "N2023_FM",
            "arxiv_id": "2210.02747",
            "ss_paper_id": "4d8b9e5e0ba2fde975e73ba12e0bc81cb1776722",
            "description": "提出 Flow Matching 训练目标，比 DDPM 更简洁优雅，在 ImageNet 256×256 达到 SOTA FID",
            "reviews": [
                {
                    "rating": "8",
                    "strengths": "Training objective 比 DDPM 更简单优雅，理论推导清晰。在 ImageNet 256×256 达到 SOTA FID。",
                    "weaknesses": "缺少与 Consistency Models 的系统比较。Classifier-free guidance 的兼容性未讨论。",
                    "related_work": ["Consistency Models", "Rectified Flow", "EDM (Karras et al.)"]
                },
                {
                    "rating": "6",
                    "strengths": "方法简洁，实现容易，有实用价值。",
                    "weaknesses": "与 score-based SDE 的关系论述不够清晰，创新性存疑。",
                    "related_work": ["Score SDE (Song et al. 2021)", "DDPM"]
                }
            ]
        },
        {
            "title": "Scalable Diffusion Models with Transformers (DiT)",
            "forum_id": "DiT2024",
            "venue": "ICCV",
            "year": 2023,
            "url": "https://arxiv.org/abs/2212.09748",
            "avg_rating": 8.1,
            "node_id": "N2023_DiT",
            "arxiv_id": "2212.09748",
            "ss_paper_id": "bdac9afc46b25f26d6e0eaed13cba2d5f4a8c835",
            "description": "用 Transformer 替换 U-Net 作为扩散模型主干，验证 scaling law 在扩散模型中的有效性，Sora 的前驱工作",
            "reviews": [
                {
                    "rating": "8",
                    "strengths": "用 Transformer 替换 U-Net 作为主干，实验证明 scaling law 在扩散模型中有效。结果非常令人信服。",
                    "weaknesses": "计算成本高昂，学术界难以复现 large scale 实验。",
                    "related_work": ["U-Net (Ronneberger et al.)", "ViT (Dosovitskiy et al.)", "Latent Diffusion"]
                }
            ]
        },
        {
            "title": "Consistency Models",
            "forum_id": "CM_ICML2023",
            "venue": "ICML",
            "year": 2023,
            "url": "https://arxiv.org/abs/2303.01469",
            "avg_rating": 8.5,
            "node_id": "N2023_CM",
            "arxiv_id": "2303.01469",
            "ss_paper_id": "ac974291d7e3a152067382675524f3e3c2ded11b",
            "description": "将扩散过程的多步采样压缩为单步生成，FID 和速度均优于 DDIM 50-step，ICML 2023 最佳论文候选",
            "reviews": [
                {
                    "rating": "9",
                    "strengths": "将扩散过程的多步采样压缩为单步，理论创新突出。FID 和速度均优于 DDIM 50-step。",
                    "weaknesses": "训练稳定性问题未充分讨论。与 score distillation 的联系尚待厘清。",
                    "related_work": ["EDM (Karras et al. 2022)", "Score Distillation Sampling", "DDIM"]
                },
                {
                    "rating": "8",
                    "strengths": "单步生成在实时应用场景极具价值，训练目标简洁。",
                    "weaknesses": "在高分辨率（ImageNet 512×512）的质量与 DDPM 差距仍明显。",
                    "related_work": ["Progressive Distillation", "Denoising Diffusion Samplers"]
                }
            ]
        },
        {
            "title": "Elucidating the Design Space of Diffusion-Based Generative Models (EDM)",
            "forum_id": "EDM_NeurIPS2022",
            "venue": "NeurIPS",
            "year": 2022,
            "url": "https://arxiv.org/abs/2206.00364",
            "avg_rating": 9.0,
            "node_id": "N2022_EDM",
            "arxiv_id": "2206.00364",
            "ss_paper_id": "2f4c451922e227cbbd4f090b74298445bbd900d0",
            "description": "系统性分析扩散模型中预条件、采样方法、噪声调度等设计选项，将多个已有方法统一到同一框架下比较",
            "reviews": [
                {
                    "rating": "9",
                    "strengths": "系统性分析扩散模型中预条件、采样方法、噪声调度等设计选项，极具参考价值。将多个已有方法统一到同一框架下比较，贡献扎实。",
                    "weaknesses": "工程贡献比理论贡献大，部分实验细节过于繁琐。",
                    "related_work": ["DDPM", "NCSN++", "Score SDE"]
                }
            ]
        },
        {
            "title": "Denoising Diffusion Implicit Models (DDIM)",
            "forum_id": "DDIM_ICLR2021",
            "venue": "ICLR",
            "year": 2021,
            "url": "https://openreview.net/forum?id=St1giarCHLP",
            "avg_rating": 8.0,
            "node_id": "N2021_DDIM",
            "arxiv_id": "2010.02502",
            "ss_paper_id": "014576b866078524286802b1d0e18628520aa886",
            "description": "将随机采样转化为确定性过程，实现 20× 加速且支持语义插值，工程影响极大",
            "reviews": [
                {
                    "rating": "8",
                    "strengths": "将随机采样转化为确定性过程，20× 加速且支持语义插值，工程影响极大。",
                    "weaknesses": "理论分析较浅，主要是 DDPM 的工程改进。与 ODE solver 视角的联系未充分挖掘。",
                    "related_work": ["Neural ODE", "DDPM", "Score SDE (concurrent work)"]
                }
            ]
        }
    ],
    "reading_list": [
        {
            "title": "Denoising Diffusion Probabilistic Models (DDPM)",
            "type": "foundation",
            "reason": "必读入门论文，理解扩散模型的核心数学框架",
            "url": "https://arxiv.org/abs/2006.11239"
        },
        {
            "title": "Denoising Diffusion Implicit Models (DDIM)",
            "type": "foundation",
            "reason": "理解如何将采样从 1000 步加速到 50 步",
            "url": "https://arxiv.org/abs/2010.02502"
        },
        {
            "title": "Latent Diffusion Models (Stable Diffusion)",
            "type": "foundation",
            "reason": "理解为什么高分辨率生成可以在普通 GPU 上运行",
            "url": "https://arxiv.org/abs/2112.10752"
        },
        {
            "title": "Flow Matching for Generative Modeling",
            "type": "frontier",
            "reason": "ICLR 2023 方向热点，比 DDPM 训练目标更简洁",
            "url": "https://openreview.net/forum?id=PqvMRDCJT9t"
        },
        {
            "title": "Scalable Diffusion Models with Transformers (DiT)",
            "type": "frontier",
            "reason": "验证 Transformer 在扩散模型中的 scaling law，Sora 的前驱工作",
            "url": "https://arxiv.org/abs/2212.09748"
        },
        {
            "title": "Consistency Models",
            "type": "frontier",
            "reason": "ICML 2023 最佳论文候选；单步生成突破，速度与质量平衡的里程碑",
            "url": "https://arxiv.org/abs/2303.01469"
        },
        {
            "title": "EDM: Elucidating the Design Space of Diffusion-Based Generative Models",
            "type": "frontier",
            "reason": "NeurIPS 2022 Outstanding Paper；系统性分析扩散模型所有设计选项，工程必读",
            "url": "https://arxiv.org/abs/2206.00364"
        },
        {
            "title": "Rectified Flow",
            "type": "recommended",
            "reason": "来源：Reviewer 要求与之比较；Flow Matching 的直接相关工作，SD3 技术底座",
            "url": "https://arxiv.org/abs/2209.03003"
        },
        {
            "title": "Score SDE: Score-Based Generative Modeling through Stochastic Differential Equations",
            "type": "recommended",
            "reason": "来源：Reviewer 推荐；将 NCSN 和 DDPM 统一在 SDE 框架下，理论深度最强",
            "url": "https://arxiv.org/abs/2011.13456"
        }
    ],
    "top_authors": [
        {
            "name": "Yang Song",
            "institution": "OpenAI / Stanford University",
            "papers_count": 52,
            "recent_work": "Score-based models, DDIM, Consistency Models, Flow Matching",
            "url": "https://yang-song.net"
        },
        {
            "name": "Jonathan Ho",
            "institution": "Google DeepMind",
            "papers_count": 38,
            "recent_work": "DDPM, Classifier-free guidance, Video Diffusion Models",
            "url": "https://scholar.google.com/citations?user=14gRbVgAAAAJ"
        },
        {
            "name": "Robin Rombach",
            "institution": "Stability AI / LMU Munich",
            "papers_count": 31,
            "recent_work": "Latent Diffusion Models, Stable Diffusion, ControlNet",
            "url": "https://scholar.google.com/citations?user=ygdQhrIAAAAJ"
        },
        {
            "name": "Tero Karras",
            "institution": "NVIDIA Research",
            "papers_count": 44,
            "recent_work": "EDM, StyleGAN→Diffusion, Progressive training strategies",
            "url": "https://scholar.google.com/citations?user=3VrWgWkAAAAJ"
        },
        {
            "name": "William Peebles",
            "institution": "OpenAI / UC Berkeley",
            "papers_count": 18,
            "recent_work": "DiT (Diffusion Transformers), Sora architecture",
            "url": "https://www.wpeebles.com"
        }
    ],
    "resources": {
        "github": [
            {
                "name": "CompVis/stable-diffusion",
                "stars": "52k",
                "description": "Latent Diffusion Models 官方实现，Stable Diffusion 原始代码",
                "url": "https://github.com/CompVis/stable-diffusion"
            },
            {
                "name": "AUTOMATIC1111/stable-diffusion-webui",
                "stars": "134k",
                "description": "最流行的 Stable Diffusion Web UI，功能最全面",
                "url": "https://github.com/AUTOMATIC1111/stable-diffusion-webui"
            },
            {
                "name": "lucidrains/denoising-diffusion-pytorch",
                "stars": "8k",
                "description": "教学向 PyTorch 实现，代码简洁，适合新手学习原理",
                "url": "https://github.com/lucidrains/denoising-diffusion-pytorch"
            },
            {
                "name": "huggingface/diffusers",
                "stars": "24k",
                "description": "HuggingFace 官方扩散模型库，集成最新模型，工业级可用",
                "url": "https://github.com/huggingface/diffusers"
            }
        ],
        "bilibili": [
            {
                "title": "李沐·DDPM 论文精读【论文精读】",
                "url": "https://www.bilibili.com/video/BV1b541197HX",
                "view_count": 1800000
            },
            {
                "title": "扩散模型从入门到精通（10集）",
                "url": "https://www.bilibili.com/video/BV1RG4y197h5",
                "view_count": 450000
            },
            {
                "title": "【熟肉】Understanding Diffusion Models: 官方讲解中字",
                "url": "https://www.bilibili.com/video/BV1gA411D7E3",
                "view_count": 280000
            }
        ],
        "wechat": [
            {
                "title": "量子位·Stable Diffusion 完整技术解析：从原理到实践",
                "url": "https://mp.weixin.qq.com/s/stable-diffusion-technical-deep-dive"
            },
            {
                "title": "机器之心·2024 生成模型综述：扩散模型的新进展",
                "url": "https://mp.weixin.qq.com/s/diffusion-models-2024-survey"
            },
            {
                "title": "PaperWeekly·Flow Matching 详解：比 DDPM 更优雅的训练目标",
                "url": "https://mp.weixin.qq.com/s/flow-matching-explained"
            }
        ]
    },
    "paper_clusters": [
        {
            "id": "cluster_sde",
            "name": "Score-based / SDE Methods",
            "subgraph_style": "fill:#eff6ff,stroke:#2563eb",
            "paper_node_ids": ["N2019_NCSN", "N2020_DDPM", "N2021_DDIM"]
        },
        {
            "id": "cluster_flow",
            "name": "Flow-based Samplers",
            "subgraph_style": "fill:#faf5ff,stroke:#7c3aed",
            "paper_node_ids": ["N2021_SDE", "N2022_EDM", "N2023_FM", "N2023_CM"]
        },
        {
            "id": "cluster_latent",
            "name": "Latent / Efficient Methods",
            "subgraph_style": "fill:#f0fdf4,stroke:#059669",
            "paper_node_ids": ["N2022_LDM", "N2023_DiT"]
        }
    ],
    "graph_mermaid": """flowchart LR
  classDef foundation fill:#dbeafe,stroke:#2563eb,color:#1e40af
  classDef key fill:#2563eb,stroke:#1e40af,color:white
  classDef frontier fill:#f5f3ff,stroke:#7c3aed,color:#4c1d95

  subgraph cluster_sde["🔵 Score-based / SDE Methods"]
    style cluster_sde fill:#eff6ff,stroke:#2563eb
    N2019_NCSN["2019 NCSN\\n⭐ 4k"]:::foundation
    N2020_DDPM["2020 DDPM\\n⭐ 18k"]:::key
    N2021_DDIM["2021 DDIM\\n⭐ 6k"]:::key
  end

  subgraph cluster_flow["🟣 Flow-based Samplers"]
    style cluster_flow fill:#faf5ff,stroke:#7c3aed
    N2022_EDM["2022 EDM\\n⭐ 3k"]:::foundation
    N2023_FM["2023 Flow Matching"]:::frontier
    N2023_CM["2023 Consistency\\nModels\\n⭐ 2k"]:::frontier
  end

  subgraph cluster_latent["🟢 Latent / Efficient Methods"]
    style cluster_latent fill:#f0fdf4,stroke:#059669
    N2022_LDM["2022 LDM / SD\\n⭐ 12k"]:::key
    N2023_DiT["2023 DiT\\n(Peebles et al.)"]:::frontier
  end

  N2019_NCSN --> N2020_DDPM
  N2020_DDPM --> N2021_DDIM
  N2020_DDPM --> N2022_LDM
  N2020_DDPM --> N2023_FM
  N2021_DDIM --> N2022_EDM
  N2021_DDIM --> N2023_CM
  N2022_LDM --> N2023_DiT""",
    "latest_updates": [],
    "social_actions": [
        {
            "platform": "xiaohongshu",
            "action": "search",
            "query": "扩散模型 学习",
            "result_count": 23,
            "timestamp": "2026-03-08 10:15",
            "status": "done"
        },
        {
            "platform": "xiaohongshu",
            "action": "follow",
            "target_name": "李沐_学习圈",
            "target_id": "u123456",
            "target_url": "https://www.xiaohongshu.com/user/profile/u123456",
            "reason": "发布了 12 篇扩散模型学习笔记，互动活跃",
            "timestamp": "2026-03-08 10:17",
            "status": "followed"
        },
        {
            "platform": "xiaohongshu",
            "action": "follow",
            "target_name": "AIGC研究生日常",
            "target_id": "u789012",
            "target_url": "https://www.xiaohongshu.com/user/profile/u789012",
            "reason": "专注扩散模型应用，粉丝 8k",
            "timestamp": "2026-03-08 10:17",
            "status": "followed"
        },
        {
            "platform": "xiaohongshu",
            "action": "follow",
            "target_name": "CV_Paper_Daily",
            "target_id": "u345678",
            "target_url": "https://www.xiaohongshu.com/user/profile/u345678",
            "reason": "每日更新 AIGC 论文速递，已关注",
            "timestamp": "2026-03-08 10:17",
            "status": "skipped"
        },
        {
            "platform": "wechat_group",
            "action": "qr_found",
            "group_name": "扩散模型交流群",
            "source_url": "https://www.xiaohongshu.com/explore/68ca3213000000001300ea23",
            "weixin_link": "https://weixin.qq.com/g/AQYAAC4h9kAhq-Mw8Luc1Z-1RTlrosHsudU9kCrry2ak72FoxNJESGvEW9OmynAP",
            "draft_message": "您好！我是研究扩散模型方向的研究生，希望加入「扩散模型交流群」和大家交流学习，也可以分享我们组的最新进展。感谢！",
            "timestamp": "2026-03-08 10:20",
            "status": "ready"
        }
    ]
}


# ─────────────────────────────────────────────────────────────────────────────
# Pre-baked demo data: Diffusion Models v2 (after "one week" proactive update)
# ─────────────────────────────────────────────────────────────────────────────

DIFFUSION_V2 = {
    **DIFFUSION_V1,
    "generated_at": "2026-03-08 10:00",
    "last_updated_at": "2026-03-15 09:30",
    "latest_updates": [
        {
            "date": "2026-03-14",
            "title": "Consistency Flow Matching: Improving Flow Matching with Consistency Regularization",
            "url": "https://arxiv.org/abs/2407.02398",
            "summary": "将 consistency training 思想引入 flow matching，实现单步采样 FID 1.9（ImageNet 256×256），超越此前所有单步方法",
            "source": "arXiv"
        },
        {
            "date": "2026-03-12",
            "title": "SDXL-Turbo: Adversarial Diffusion Distillation",
            "url": "https://arxiv.org/abs/2311.17042",
            "summary": "对抗性蒸馏使 SDXL 实现单步实时生成，质量与多步 SDXL 相当，部署成本降低 50× ",
            "source": "arXiv"
        },
        {
            "date": "2026-03-10",
            "title": "Scaling Rectified Flow Transformers for High-Resolution Image Synthesis",
            "url": "https://arxiv.org/abs/2403.03206",
            "summary": "Stable Diffusion 3 技术报告：将 rectified flow + DiT 扩展到 80 亿参数，多模态生成质量全面超越 DALL-E 3",
            "source": "arXiv"
        }
    ]
}


# ─────────────────────────────────────────────────────────────────────────────
# Pre-baked demo data: AutoML (backup topic)
# ─────────────────────────────────────────────────────────────────────────────

AUTOML_V1 = {
    "topic": "AutoML",
    "topic_zh": "自动机器学习",
    "generated_at": "2026-03-08 10:00",
    "field_overview": (
        "AutoML 的核心问题是：如何自动找到最优的机器学习 pipeline（模型架构 + 超参数 + 数据预处理）？"
        "这个问题从 2019 年前后开始爆发，驱动力是深度学习的普及让「找到最优架构」的需求变得迫切。\n\n"
        "2024 年的主要共识是：NAS（神经架构搜索）已从早期的 RL/进化算法转向可微分方法（DARTS 族）"
        "和零样本代理（Zero-shot NAS）。Reviewer 最常追问的问题是「搜索代价」和「迁移性」——"
        "在一个数据集上搜索到的架构能否在其他任务上泛化？\n\n"
        "当前最大争议：LLM 能否取代传统 NAS？不少 2024 论文尝试用 GPT-4 直接生成架构配置，"
        "结果参差不齐，但方向被广泛关注。HPO（超参数优化）领域已相当成熟，"
        "SMAC3 和 Optuna 是工业界主流工具。\n\n"
        "新手建议：先理解 DARTS（可微分 NAS），再看 EfficientNet（了解自动化 scaling），"
        "最后关注 HPO 工具（Optuna/SMAC3），这是最快产出实际价值的路径。"
    ),
    "foundation": [
        {
            "year": 2017,
            "title": "Neural Architecture Search with Reinforcement Learning",
            "authors": ["Zoph & Le", "ICLR 2017"],
            "description": "用强化学习自动搜索神经网络架构，NAS 领域奠基之作",
            "url": "https://arxiv.org/abs/1611.01578",
            "problem_solved": "首次证明自动设计架构优于人工设计",
            "problem_left": "计算成本极高（需要800 GPU×30天）",
            "is_key": True,
            "citation_count": 8200
        },
        {
            "year": 2019,
            "title": "DARTS: Differentiable Architecture Search",
            "authors": ["Liu et al.", "ICLR 2019"],
            "description": "将架构搜索转化为可微分优化问题，将搜索成本从数百 GPU 天降至 4 GPU 天",
            "url": "https://arxiv.org/abs/1806.09055",
            "problem_solved": "搜索效率提升 1000×，使 NAS 实际可用",
            "problem_left": "搜索结果在不同数据集上泛化性差",
            "is_key": True,
            "citation_count": 6500
        },
        {
            "year": 2020,
            "title": "EfficientNet: Rethinking Model Scaling for Convolutional Neural Networks",
            "authors": ["Tan & Le", "ICML 2019"],
            "description": "提出复合缩放法则，自动化确定 depth/width/resolution 的最优比例",
            "url": "https://arxiv.org/abs/1905.11946",
            "problem_solved": "用更少参数达到更高精度，缩放法则自动化",
            "problem_left": "对新型架构（ViT）不适用",
            "is_key": False,
            "citation_count": 12000
        }
    ],
    "frontier": [
        {
            "title": "Zero-Cost Proxies for Lightweight NAS",
            "forum_id": "0CMNGjOEVkZ",
            "venue": "ICLR",
            "year": 2021,
            "url": "https://openreview.net/forum?id=0CMNGjOEVkZ",
            "avg_rating": 7.0,
            "description": "不需要训练模型即可评估架构质量，极大降低 NAS 搜索成本",
            "reviews": [
                {
                    "rating": "7",
                    "strengths": "不需要训练模型即可评估架构质量，极大降低 NAS 搜索成本",
                    "weaknesses": "与 SMAC3 和 BOHB 等成熟超参数优化方法缺少比较，代理指标可靠性存疑",
                    "related_work": ["SMAC3", "BOHB (Falkner et al.)", "DARTS"]
                }
            ]
        }
    ],
    "reading_list": [
        {
            "title": "DARTS: Differentiable Architecture Search",
            "type": "foundation",
            "reason": "可微分 NAS 必读，理解现代 NAS 的基础",
            "url": "https://arxiv.org/abs/1806.09055"
        },
        {
            "title": "EfficientNet",
            "type": "foundation",
            "reason": "理解自动化模型缩放的思路",
            "url": "https://arxiv.org/abs/1905.11946"
        },
        {
            "title": "SMAC3",
            "type": "recommended",
            "reason": "来源：Reviewer 推荐；工业级 HPO 工具，值得了解",
            "url": "https://arxiv.org/abs/2109.09950"
        }
    ],
    "top_authors": [
        {
            "name": "Frank Hutter",
            "institution": "University of Freiburg / ML4Science",
            "papers_count": 180,
            "recent_work": "HPO, SMAC, Auto-Sklearn, LLM for AutoML",
            "url": "https://ml.informatik.uni-freiburg.de/profile/hutter/"
        },
        {
            "name": "Quoc V. Le",
            "institution": "Google Brain",
            "papers_count": 120,
            "recent_work": "NAS with RL, EfficientNet, Neural Architecture Search",
            "url": "https://scholar.google.com/citations?user=vfT6-XIAAAAJ"
        }
    ],
    "resources": {
        "github": [
            {
                "name": "automl/auto-sklearn",
                "stars": "7k",
                "description": "基于 sklearn 的 AutoML 框架，Kaggle 竞赛常用",
                "url": "https://github.com/automl/auto-sklearn"
            },
            {
                "name": "optuna-org/optuna",
                "stars": "10k",
                "description": "超参数优化框架，工业界广泛使用",
                "url": "https://github.com/optuna-org/optuna"
            }
        ],
        "bilibili": [
            {
                "title": "AutoML 入门：神经架构搜索原理详解",
                "url": "https://www.bilibili.com/search?keyword=AutoML+NAS",
                "view_count": 85000
            }
        ],
        "wechat": [
            {
                "title": "机器之心·AutoML 2024年综述：从 DARTS 到 LLM-guided NAS",
                "url": "https://mp.weixin.qq.com/s/automl-2024-survey"
            }
        ]
    },
    "graph_mermaid": """flowchart LR
  classDef foundation fill:#dbeafe,stroke:#2563eb,color:#1e40af
  classDef key fill:#2563eb,stroke:#1e40af,color:white
  classDef frontier fill:#f5f3ff,stroke:#7c3aed,color:#4c1d95

  NAS_RL["2017 NAS+RL\\n⭐ 8k citations"]:::key
  DARTS["2019 DARTS\\n⭐ 6k citations"]:::key
  EfficientNet["2019 EfficientNet\\n⭐ 12k citations"]:::foundation
  ZeroCost["2021 Zero-Cost NAS"]:::frontier
  LLM4NAS["2024 LLM-guided NAS"]:::frontier

  NAS_RL --> DARTS
  DARTS --> ZeroCost
  DARTS --> LLM4NAS
  EfficientNet --> LLM4NAS""",
    "latest_updates": []
}


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

DATASETS = {
    "diffusion": {
        "v1": DIFFUSION_V1,
        "v2": DIFFUSION_V2,
        "label": "Diffusion Models"
    },
    "automl": {
        "v1": AUTOML_V1,
        "v2": None,
        "label": "AutoML"
    }
}


def run_social_agent(topic_zh: str, fallback_wechat: dict = None) -> list[dict]:
    """Run social_agent.py and convert results to social_actions format for HTML."""
    import os
    env = {k: v for k, v in os.environ.items() if k.upper() not in ("ALL_PROXY", "all_proxy")}
    print(f"  🌐 Running social agent for '{topic_zh}'...")
    result = subprocess.run(
        [sys.executable, str(SOCIAL_AGENT), "--topic-zh", topic_zh],
        capture_output=True, text=True, timeout=120, env=env
    )
    # Extract JSON summary from stdout (last JSON block)
    try:
        lines = result.stdout.strip().splitlines()
        # Find the start of the JSON block
        json_start = next(i for i, l in enumerate(lines) if l.strip() == "{")
        summary = json.loads("\n".join(lines[json_start:]))
    except Exception as e:
        print(f"  ⚠️  Social agent parse error: {e}")
        print(result.stderr[:300])
        return []

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    actions = []

    # Search result
    posts = summary.get("xiaohongshu_posts", [])
    if posts:
        actions.append({
            "platform": "xiaohongshu", "action": "search",
            "query": f"{topic_zh} 学习",
            "result_count": len(posts),
            "timestamp": now_str, "status": "done"
        })

    # Follow results
    follow_results = summary.get("follow_results", [])
    posts_by_id = {p["author_id"]: p for p in posts if p.get("author_id")}
    for f in follow_results:
        aid = f["author_id"]
        post = posts_by_id.get(aid, {})
        actions.append({
            "platform": "xiaohongshu", "action": "follow",
            "target_name": post.get("author", aid),
            "target_id": aid,
            "target_url": f"https://www.xiaohongshu.com/user/profile/{aid}",
            "reason": f"在小红书发布扩散模型相关内容，点赞数 {post.get('likes', '?')}",
            "timestamp": now_str,
            "status": f.get("status", "followed"),
        })

    # WeChat group — use real result if found, otherwise fallback
    wechat_added = False
    for g in summary.get("wechat_groups", []):
        if g.get("status") == "ready" and g.get("weixin_link"):
            actions.append({
                "platform": "wechat_group", "action": "qr_found",
                "group_name": g.get("group_name", "交流群"),
                "source_url": g.get("source_url", ""),
                "weixin_link": g.get("weixin_link", ""),
                "draft_message": g.get("draft_message", ""),
                "timestamp": now_str, "status": "ready",
            })
            wechat_added = True
            break

    if not wechat_added and fallback_wechat:
        fallback_wechat["timestamp"] = now_str
        actions.append(fallback_wechat)
        print(f"  ℹ️  未找到新微信群，使用上次已知群链接")

    return actions


def save_and_generate(data: dict, json_path: Path, html_path: Path) -> None:
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  📄 JSON saved: {json_path}")

    result = subprocess.run(
        [sys.executable, str(GENERATE_REPORT), "--data", str(json_path), "--output", str(html_path)],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        print(f"  ✅ HTML generated: {html_path}")
        if result.stdout:
            for line in result.stdout.strip().split("\n"):
                print(f"     {line}")
    else:
        print(f"  ❌ HTML generation failed!")
        print(result.stderr)


def main():
    parser = argparse.ArgumentParser(description="FrontierPilot demo data preloader")
    parser.add_argument("--output-dir", default="demo_cache", help="Output directory for cached files")
    parser.add_argument("--topic", choices=["diffusion", "automl", "all"], default="all",
                        help="Which topic to preload")
    parser.add_argument("--json-only", action="store_true", help="Only save JSON, skip HTML generation")
    parser.add_argument("--social", action="store_true",
                        help="Run social_agent.py to fetch real social_actions data")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"📁 Output directory: {output_dir.resolve()}")

    topics = ["diffusion", "automl"] if args.topic == "all" else [args.topic]

    for topic_key in topics:
        dataset = DATASETS[topic_key]
        label = dataset["label"]
        print(f"\n{'='*50}")
        print(f"🔄 Preloading: {label}")
        print(f"{'='*50}")

        # v1: initial knowledge base
        v1_data = dict(dataset["v1"])
        v1_json = output_dir / f"{topic_key}_v1.json"
        v1_html = output_dir / f"{topic_key}_v1.html"

        # Optionally fetch real social actions
        if args.social:
            topic_zh = v1_data.get("topic_zh", topic_key)
            # Extract fallback wechat entry from static data
            fallback_wechat = next(
                (a for a in v1_data.get("social_actions", []) if a.get("action") == "qr_found"),
                None
            )
            real_actions = run_social_agent(topic_zh, fallback_wechat=fallback_wechat)
            if real_actions:
                v1_data["social_actions"] = real_actions
                print(f"  ✅ 社交行动：{len(real_actions)} 条真实数据已写入")
            else:
                print(f"  ⚠️  社交数据获取失败，保留预置数据")

        print(f"\n[v1] Initial knowledge base →")
        if args.json_only:
            v1_json.write_text(json.dumps(v1_data, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"  📄 JSON saved: {v1_json}")
        else:
            save_and_generate(v1_data, v1_json, v1_html)

        # v2: after proactive update (if exists)
        if dataset["v2"] is not None:
            v2_json = output_dir / f"{topic_key}_v2.json"
            v2_html = output_dir / f"{topic_key}_v2.html"
            print(f"\n[v2] After proactive update (simulating 'one week later') →")
            if args.json_only:
                v2_json.write_text(json.dumps(dataset["v2"], ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"  📄 JSON saved: {v2_json}")
            else:
                save_and_generate(dataset["v2"], v2_json, v2_html)
            print(f"\n  📰 Update contains {len(dataset['v2']['latest_updates'])} new papers")

    print(f"\n{'='*50}")
    print("✅ Demo preloading complete!")
    print(f"\n📋 Demo presentation guide:")
    print(f"   1. Open diffusion_v1.html → 'This is what FrontierPilot generates on first use'")
    print(f"   2. Switch to diffusion_v2.html → 'One week later, OpenClaw proactively updated the knowledge base'")
    print(f"   3. Click '最新动态' tab to show the 3 new papers discovered")
    print(f"   4. Open '我的笔记' tab → 'Users can build on the knowledge base over time'")


if __name__ == "__main__":
    main()
