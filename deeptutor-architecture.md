# DeepTutor 项目架构分析

## 项目概述

**DeepTutor** 是一个 AI 驱动的个性化学习助手，采用全栈 Web 应用架构。项目使用 FastAPI 后端（Python）、Next.js/React 前端（TypeScript），并集成了多种高级 AI 能力，包括多智能体推理、RAG（检索增强生成）、网络搜索和演示文稿生成。

---

## 1. 项目结构

```
DeepTutor-1/
├── src/                           # Python 后端源代码
│   ├── agents/                    # AI 智能体实现
│   │   ├── solve/                 # 问题求解智能体
│   │   ├── research/              # 深度研究智能体
│   │   ├── question/              # 问题生成智能体
│   │   ├── guide/                 # 引导学习智能体
│   │   ├── ideagen/               # 自动创意生成
│   │   ├── co_writer/             # 交互式创意/协作写作
│   │   └── chat/                  # 聊天智能体
│   ├── api/                       # FastAPI 应用
│   │   ├── routers/               # API 端点路由
│   │   │   ├── research.py        # 研究端点（含 PPT 导出）
│   │   │   ├── question.py        # 问题生成端点
│   │   │   ├── guide.py           # 引导学习端点
│   │   │   ├── solve.py           # 问题求解端点
│   │   │   └── notebook.py        # 笔记本端点
│   │   └── utils/                 # API 工具函数
│   ├── services/                  # 服务层
│   │   ├── export/                # 导出服务
│   │   │   ├── ppt_generator.py   # PPT 生成服务
│   │   │   ├── pdf_generator.py   # PDF 生成服务
│   │   │   ├── mindmap_generator.py
│   │   │   └── source_report.py
│   │   ├── llm/                   # LLM 客户端和提供者
│   │   ├── embedding/             # 嵌入向量提供者
│   │   ├── rag/                   # RAG 服务
│   │   └── config/                # 配置加载器
│   ├── knowledge/                 # 知识库管理
│   ├── tools/                     # 工具实现
│   ├── logging/                   # 日志配置
│   └── core/                      # 核心工具
├── web/                           # Next.js 前端
│   ├── app/                       # 应用路由
│   │   ├── research/              # 研究页面
│   │   ├── preview/ppt/           # PPT 预览页面
│   │   ├── solver/                # 问题求解页面
│   │   ├── question/              # 问题生成页面
│   │   ├── guide/                 # 引导学习页面
│   │   ├── ideagen/               # 创意生成页面
│   │   ├── notebook/              # 笔记本页面
│   │   ├── co_writer/             # 交互式创意页面
│   │   └── knowledge/             # 知识库页面
│   ├── components/                # React 组件
│   │   └── research/              # 研究相关组件
│   ├── lib/                       # 前端工具函数
│   ├── types/                     # TypeScript 类型
│   ├── hooks/                     # React Hooks
│   └── context/                   # React Context
├── config/                        # 配置文件
│   ├── main.yaml                  # 主配置
│   ├── agents.yaml                # 智能体参数
│   └── research_config.yaml
├── data/                          # 数据存储
│   ├── knowledge_bases/           # 知识库数据
│   └── user/                      # 用户数据
│       ├── research/              # 研究输出
│       ├── question/              # 问题生成输出
│       ├── solve/                 # 问题求解输出
│       └── notebook/              # 笔记本数据
├── requirements.txt               # Python 依赖
└── web/package.json               # 前端依赖
```

---

## 2. 技术栈

### 前端
| 技术 | 版本 | 用途 |
|------|------|------|
| Next.js | 16 | React 框架 |
| React | 19 | UI 库 |
| TypeScript | 5 | 类型安全 |
| TailwindCSS | 3.4 | 样式框架 |
| React Markdown | 10.1 | Markdown 渲染 |
| pptxgenjs | 4.0.1 | PPT 生成（前端） |
| html2canvas | 1.4.1 | 图像导出 |
| jsPDF | 4.0.0 | PDF 导出 |
| Framer Motion | - | 动画效果 |

### 后端
| 技术 | 版本 | 用途 |
|------|------|------|
| FastAPI | 0.100+ | Web 框架 |
| Python | 3.10+ | 后端语言 |
| Uvicorn | 0.24+ | ASGI 服务器 |
| websockets | 12.0+ | 实时通信 |
| python-pptx | 0.6.23 | PPT 生成（后端） |
| reportlab | 4.2+ | PDF 生成 |
| OpenAI SDK | 1.30+ | LLM 集成 |
| LightRAG | 1.0+ | RAG 系统 |

### AI 与搜索
| 技术 | 用途 |
|------|------|
| OpenAI API | LLM 推理 |
| Perplexity AI | 网络搜索 |
| Arxiv API | 论文搜索 |
| 多种嵌入提供者 | OpenAI, Jina, Cohere, Ollama |

---

## 3. 核心功能模块

### 模块概览

| 模块 | 功能描述 |
|------|----------|
| **Solve/问题求解** | 双循环推理，结合 RAG、网络搜索、代码执行 |
| **Question/问题生成** | 自定义和模拟考试的问题生成 |
| **Guide/引导学习** | 带视觉解释的交互式学习 |
| **Research/深度研究** | 多智能体研究，动态主题队列 |
| **IdeaGen/创意生成** | 自动化和交互式头脑风暴 |
| **Co-Writer/协作写作** | AI 辅助 Markdown 编辑器，支持 TTS |
| **Notebook/笔记本** | 个人学习记录管理 |
| **Dashboard/仪表板** | 活动跟踪和系统概览 |

---

## 4. PPT 生成功能详解

### 4.1 架构概述

DeepTutor 的 PPT 生成功能将研究报告和其他 Markdown 内容转换为专业的 PowerPoint 演示文稿。

### 4.2 后端 PPT 服务

**文件位置**: `src/services/export/ppt_generator.py`

**核心类**: `PPTGenerator`

```python
class PPTGenerator:
    """从 Markdown 内容生成 PowerPoint 演示文稿的服务"""

    async def generate(
        self,
        markdown: str,
        title: Optional[str] = None,
        style_prompt: Optional[str] = None,
        style_model: Optional[str] = None,
        style_api_key: Optional[str] = None,
        style_base_url: Optional[str] = None,
        max_slides: int = 15,
        template_path: Optional[Union[str, Path]] = None,
    ) -> Dict[str, Any]
```

**使用的技术**:
- **python-pptx** (0.6.23) - 创建/修改 PPTX 文件的核心库
- **LLM（可选）** - 使用 LLM 生成演示规格（幻灯片结构、样式）
- **Markdown 解析器** - 将 Markdown 解析为章节并提取要点

### 4.3 数据流程

```
1. 输入: Markdown 内容
   ↓
2. 解析 Markdown 为标题和章节
   ↓
3. 可选: 调用 LLM 生成 PPT 规格（结构 + 主题）
   ↓
4. 使用模板或默认设置创建演示文稿
   ↓
5. 构建幻灯片:
   - 标题幻灯片
   - 带要点的内容幻灯片
   - 应用主题/颜色
   ↓
6. 保存 PPTX 文件
   ↓
7. 返回: {filename, relative_path, download_url}
```

### 4.4 核心功能特性

#### Markdown 解析
- 按 H1/H2 标题分割 Markdown
- 从内容中提取要点
- 处理代码块、列表和格式化文本

#### 主题/样式生成
- 可选的基于 LLM 的样式生成
- 生成包含以下内容的 JSON 规格：
  - 标题和主题颜色
  - 背景色、强调色、标题色、正文色
  - 带标题和要点的幻灯片结构
- LLM 不可用时回退到默认主题

#### 模板支持
- 可使用自定义 PPTX 模板
- 模板存储在 `/data/user/notebook/ppt_templates/`
- 通过 `pptx.Presentation(template_path)` 加载模板

#### 幻灯片创建
- 带背景色的标题幻灯片
- 带要点的内容幻灯片
- 强调条装饰
- 字体样式（名称、大小、颜色）
- 文本换行和布局处理

#### 文件名处理
- Unicode 安全（支持中文字符）
- 移除无效的文件系统字符
- 基于时间戳命名: `{title}_{YYYYMMDD_HHMMSS}.pptx`

### 4.5 API 端点

**文件位置**: `src/api/routers/research.py`

| 端点 | 方法 | 功能 |
|------|------|------|
| `/export_pptx` | POST | 从 Markdown 生成 PPTX |
| `/ppt_templates` | GET | 列出可用的 PPTX 模板 |
| `/ppt_templates/upload` | POST | 上传自定义 PPTX 模板 |
| `/ppt_style_preview` | POST | 预览生成的主题颜色 |
| `/ppt_style_from_sources` | POST | 从选定来源生成样式提示 |
| `/ppt_style_templates` | GET | 返回预定义的 PPT 样式模板 |

**导出 PPTX 请求格式**:
```json
{
  "markdown": "报告内容...",
  "title": "演示标题",
  "max_slides": 15,
  "style_prompt": "样式描述",
  "style_model": "模型名称",
  "style_api_key": "API密钥",
  "style_base_url": "API地址",
  "template_name": "模板名称"
}
```

**响应格式**:
```json
{
  "filename": "report_20240110_120000.pptx",
  "relative_path": "research/exports/report_20240110_120000.pptx",
  "download_url": "/api/outputs/research/exports/..."
}
```

### 4.6 配置

**文件位置**: `config/main.yaml`

```yaml
export:
  ppt:
    # PPT 生成专用 LLM（留空则使用默认 LLM）
    model: ""                    # 如 "nano-banana", "gpt-4" 等
    api_key: ""                  # PPT 专用 API 密钥
    base_url: ""                 # PPT 专用 API 端点
    binding: "openai"            # API 兼容类型

    # 生成参数
    temperature: 0.4             # 较低以保持结构一致性
    max_tokens: 2000             # 足够生成 JSON 规格
    max_slides: 15               # 默认最大幻灯片数

    # 默认样式提示
    default_style_prompt: ""

    # 预设样式模板
    style_templates:
      - id: "clean"
        name: "Clean Minimal"
        prompt: "..."
      - id: "academic"
        name: "Academic Report"
        prompt: "..."
      - id: "business"
        name: "Business Pitch"
        prompt: "..."
```

**配置加载器**: `src/services/config/loader.py`

```python
@dataclass
class PPTConfig:
    """PPT 生成配置"""
    model: str
    api_key: str
    base_url: str
    binding: str = "openai"
    temperature: float = 0.4
    max_tokens: int = 2000
    max_slides: int = 15
    default_style_prompt: str = ""
    style_templates: list[dict[str, str]] = field(default_factory=list)
```

**配置优先级**:
1. `main.yaml`: `export.ppt` 部分
2. 环境变量: `PPT_MODEL`, `PPT_API_KEY`, `PPT_BASE_URL`
3. 默认 LLM 配置（来自 `LLM_*` 环境变量）

### 4.7 前端集成

**文件位置**: `web/components/research/ResearchDashboard.tsx`

**预定义样式模板**:

```typescript
const PPT_STYLE_TEMPLATES: PptStyleTemplate[] = [
  {
    id: "corporate-minimal",
    label: "Corporate (Minimal)",
    prompt: "干净的商务风格幻灯片。使用浅色背景与充足留白..."
  },
  {
    id: "academic-lecture",
    label: "Academic (Lecture)",
    prompt: "学术讲义风格。层级清晰、配色沉稳..."
  },
  {
    id: "dark-tech",
    label: "Dark (Tech)",
    prompt: "现代深色科技风。深色背景、亮色强调..."
  },
  {
    id: "data-report",
    label: "Data (Report)",
    prompt: "数据型报告风格。突出数字、强调清晰..."
  },
  {
    id: "storyboard",
    label: "Narrative (Pitch)",
    prompt: "路演/故事板风格。叙事节奏强..."
  },
  {
    id: "chinese-formal",
    label: "Chinese (Formal)",
    prompt: "中文正式/公文风格。版式均衡..."
  },
];
```

**UI 组件**:
- 样式模板下拉选择器
- 自定义样式提示输入框
- 带加载状态的导出按钮

**API 调用**:
```typescript
POST /api/v1/research/export_pptx
{
  markdown: report.generatedReport,
  title: report.title,
  style_prompt: pptStylePrompt,
  style_model: pptStyleModel,
  style_api_key: pptApiKey,
  style_base_url: pptBaseUrl,
  max_slides: 15,
  template_name: templateName
}
```

### 4.8 PPTGenerator 核心方法

| 方法 | 功能 |
|------|------|
| `generate()` | 主入口，协调整个流程 |
| `_split_markdown_into_sections()` | 按标题解析 Markdown |
| `_generate_ppt_spec()` | 调用 LLM 创建幻灯片规格 |
| `_extract_json()` | 从 LLM 响应中提取 JSON |
| `_build_presentation()` | 构建 PPTX 结构 |
| `_parse_theme()` | 将主题字典转换为 RGB 颜色 |
| `_parse_hex_color()` | 将十六进制颜色转换为 RGB 元组 |
| `_add_title_slide()` | 创建标题幻灯片 |
| `_apply_slide_style()` | 应用背景/强调样式 |
| `_set_bullets()` | 向幻灯片添加要点 |
| `_extract_bullets()` | 从 Markdown 提取要点 |
| `_sanitize_filename()` | Unicode 安全的文件名清理 |

### 4.9 数据存储

```
/data/user/research/exports/          # 研究报告 → PPT
  ├── report_20240110_120000.pptx
  ├── research_summary_20240110_143022.pptx
  └── ...

/data/user/notebook/ppt_templates/    # 自定义 PPTX 模板
  ├── my_template.pptx
  └── company_branding.pptx
```

---

## 5. 完整数据流图

```
┌─────────────────────────────────────────────────────────────────┐
│                        用户界面                                  │
│  Research Dashboard → PPT 导出按钮 → 样式选择器                  │
└────────────────────────┬──────────────────────────────────────┬─┘
                         │                                      │
                    [选择模板]                          [自定义提示]
                         │                                      │
┌────────────────────────▼──────────────────────────────────────▼─┐
│                    前端 (Next.js/React)                          │
│  ResearchDashboard.tsx                                           │
│  ├─ pptStylePrompt (状态)                                        │
│  ├─ PPT_STYLE_TEMPLATES (预定义样式)                             │
│  └─ onExportPptx() 处理器                                        │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         │ POST /api/v1/research/export_pptx
                         │ {markdown, title, style_prompt, ...}
                         │
┌────────────────────────▼────────────────────────────────────────┐
│                  API 层 (FastAPI)                                │
│  research.py: export_pptx() 端点                                 │
│  ├─ 验证请求                                                     │
│  ├─ 初始化 PPTGenerator                                          │
│  └─ 调用 generator.generate()                                    │
└────────────────────────┬────────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────────┐
│            PPT 生成器 (服务层)                                   │
│  ppt_generator.py: PPTGenerator 类                               │
│                                                                  │
│  1. 解析 Markdown                                                │
│     └─ 按标题分割，提取要点                                      │
│                                                                  │
│  2. 生成样式规格 (如有 style_prompt)                             │
│     ├─ 用 markdown + style_prompt 调用 LLM                       │
│     ├─ 获取 JSON 响应: {theme, slides}                           │
│     └─ 解析主题颜色                                              │
│                                                                  │
│  3. 创建演示文稿                                                 │
│     ├─ 加载模板或创建空白                                        │
│     ├─ 添加带主题的标题幻灯片                                    │
│     ├─ 添加带要点的内容幻灯片                                    │
│     └─ 应用样式（字体、颜色、间距）                              │
│                                                                  │
│  4. 保存 PPTX                                                    │
│     └─ 写入 /data/user/research/exports/                         │
└────────────────────────┬────────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────────┐
│              LLM 服务 (可选)                                     │
│  services/llm: complete() 函数                                   │
│  ├─ 使用 PPT 专用配置（如已配置）                                │
│  ├─ 回退到默认 LLM                                               │
│  └─ 生成带主题 + 幻灯片结构的 JSON 规格                          │
└────────────────────────┬────────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────────┐
│            文件存储 & 响应                                       │
│  ├─ 将 .pptx 文件保存到磁盘                                      │
│  ├─ 返回 {filename, relative_path, download_url}                 │
│  └─ 下载 URL: /api/outputs/research/exports/{filename}           │
└────────────────────────┬────────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────────┐
│              前端下载                                            │
│  ├─ 接收带 download_url 的响应                                   │
│  ├─ 触发浏览器下载                                               │
│  └─ 用户获得 .pptx 文件                                          │
└──────────────────────────────────────────────────────────────────┘
```

---

## 6. 环境变量

```bash
# PPT 生成必需
LLM_MODEL=gpt-4                    # 默认 LLM
LLM_API_KEY=sk-...                 # 默认 LLM API 密钥
LLM_HOST=https://api.openai.com/v1 # 默认 LLM 端点

# 可选: PPT 专用 LLM（回退链）
PPT_MODEL=nano-banana              # PPT 专用模型
PPT_API_KEY=...                    # PPT 专用密钥
PPT_BASE_URL=https://...           # PPT 专用端点
PPT_BINDING=openai                 # API 类型

# 前端
NEXT_PUBLIC_API_BASE=http://localhost:8001
```

---

## 7. 入口点

### 后端入口

**启动脚本**: `scripts/start_web.py`
- 后端: uvicorn 端口 8001
- 前端: Next.js 端口 3782

**API 服务器**: `src/api/main.py`

```python
from fastapi import FastAPI
from src.api.routers import research  # 包含 PPT 端点

app = FastAPI()
app.include_router(research.router, prefix="/api/v1/research")
```

### 前端入口

- **主页面**: `web/app/research/page.tsx`
- **PPT 预览**: `web/app/preview/ppt/page.tsx`

---

## 8. 关键文件路径

| 文件 | 路径 |
|------|------|
| PPT 生成服务 | `src/services/export/ppt_generator.py` |
| Research API 路由 | `src/api/routers/research.py` |
| 配置加载器 | `src/services/config/loader.py` |
| 主配置 | `config/main.yaml` |
| Research Dashboard | `web/components/research/ResearchDashboard.tsx` |
| Research 页面 | `web/app/research/page.tsx` |
| PPT 预览 | `web/app/preview/ppt/page.tsx` |
| PDF 生成器 | `src/services/export/pdf_generator.py` |
| 来源报告生成器 | `src/services/export/source_report.py` |
| 后端入口 | `src/api/main.py` |

---

## 9. 总结

**DeepTutor 的 PPT 生成**是一个成熟的生产级系统：

1. **转换研究报告** - 从 Markdown 到专业 PowerPoint 演示文稿
2. **利用 LLM** - 生成智能幻灯片结构和配色方案
3. **支持自定义** - 通过模板、样式提示和预定义主题
4. **多语言支持** - 包括中文，Unicode 安全的文件名
5. **无缝集成** - 与研究工作流和用户界面
6. **优雅降级** - LLM 不可用时提供回退方案
7. **专业质量** - 通过 python-pptx 库的格式化能力

**与 BananaPPT 的对比**:

| 特性 | DeepTutor | BananaPPT |
|------|-----------|-----------|
| PPT 库 | python-pptx (后端) | PptxGenJS (前端) |
| AI 图像 | 不支持 | Gemini 图像生成 |
| 布局类型 | 基于 Markdown 结构 | 10 种预定义布局 |
| 样式系统 | LLM 生成 + 模板 | LLM 生成主题 |
| 集成方式 | 研究报告导出 | 独立应用 |
| 编辑功能 | 无（导出后编辑） | 实时预览编辑 |
