# HI-NoteBook 产品需求文档（PRD）

**版本**: V1.0
**日期**: 2026-02-28
**状态**: 待评审
**基于代码版本**: DeepTutor-1 (commit: efc3b7d)

---

## 文档说明

本 PRD 基于 DeepTutor-1 仓库的真实代码实现反向编写，所有功能描述、技术实现、数据流均以当前代码为准。本文档旨在为产品化开发、测试验收、私有化交付提供完整的需求规格说明。

---

## 目录

1. [产品总览](#1-产品总览)
2. [信息架构](#2-信息架构)
3. [核心功能详细说明](#3-核心功能详细说明)
4. [代码映射表](#4-代码映射表)
5. [核心链路深度拆解](#5-核心链路深度拆解)
6. [数据模型设计](#6-数据模型设计)
7. [架构设计说明](#7-架构设计说明)
8. [非功能需求](#8-非功能需求)
9. [产品化改造差距分析](#9-产品化改造差距分析)
10. [V1 扩展能力设计](#10-v1-扩展能力设计)
11. [MCP 扩展能力规范](#11-mcp-扩展能力规范)
12. [验收标准](#12-验收标准)

---

## 1. 产品总览

### 1.1 产品定位

HI-NoteBook 是一款 **AI 驱动的知识管理与研究辅助平台**，对标 Google NotebookLM，专为知识工作者、研究人员、学生群体设计。产品核心能力是将用户上传的文档、网页、笔记转化为可交互的知识库，通过多种 AI Agent 提供深度研究、智能问答、内容生成等服务。

**核心差异化**：
- **本地可部署**：支持私有化部署，数据完全自主可控
- **多模态输出**：不仅支持文本问答，还能生成 PPT、播客、思维导图、题目等多种形式
- **深度研究能力**：基于 LightRAG + 多步推理 Agent，提供超越简单 RAG 的深度分析能力
- **工具生态**：支持 MCP 协议扩展，可集成企业内部工具链

### 1.2 目标用户

**主要用户画像**：

1. **企业知识工作者**（优先级 P0）
   - 需要处理大量内部文档、报告、会议纪要
   - 需要快速提取关键信息、生成总结报告
   - 需要私有化部署保障数据安全

2. **研究人员/学生**（优先级 P1）
   - 需要阅读大量论文、书籍
   - 需要进行文献综述、知识整理
   - 需要生成学习笔记、思维导图、题目

3. **内容创作者**（优先级 P2）
   - 需要基于素材生成文章、PPT、播客脚本
   - 需要 AI 辅助写作、润色、扩写

### 1.3 核心价值主张

**对用户的价值**：
- **10 倍效率提升**：将 2 小时的文献阅读压缩到 10 分钟的交互式问答
- **知识沉淀**：对话历史、研究报告、生成内容统一管理在 Notebook 中
- **多形式输出**：一份材料可生成 PPT、播客、题目、思维导图等多种交付物
- **数据安全**：本地部署，数据不出企业内网

**对企业的价值**：
- **降低知识流失**：员工离职后，知识库和研究成果仍保留在系统中
- **提升协作效率**：团队共享知识库，避免重复劳动
- **合规可控**：满足金融、医疗等行业的数据合规要求

### 1.4 产品边界

**包含的能力**：
- ✅ 文档上传与知识库构建（支持 PDF、Word、Markdown、TXT、图片）
- ✅ 基于知识库的智能问答（Grounded QA，必须附引用）
- ✅ 深度研究（主题拆解、多源检索、交叉验证、报告生成）
- ✅ 多模态内容生成（PPT、题目、引导学习）
- ✅ 智能写作辅助（重写、扩写、润色）
- ✅ 智能解题（多步推理、逻辑链展示）
- ✅ 笔记本管理（对话历史、研究报告统一管理）

**不包含的能力**（V1 规划）：
- ❌ 多用户协作（共享、评论、权限管理）
- ❌ 企业连接器（飞书、Confluence、企业网盘）
- ❌ SSO 单点登录
- ❌ 审计日志
- ❌ 管理后台（用户管理、配额管理、模型配置）
- ❌ 运维监控（QPS、延迟、错误率）

### 1.5 Demo vs 产品化差异

| 维度 | Demo 现状 | 产品化要求 | 差距 |
|------|----------|-----------|------|
| **用户体系** | 单用户本地使用 | 多用户、多租户、权限隔离 | 需新增用户认证、权限管理模块 |
| **数据隔离** | 所有数据存储在 `./data/user/` | 按用户/租户隔离数据 | 需重构存储层，引入租户 ID |
| **配置管理** | 环境变量 + YAML 文件 | Web 界面配置 + 管理后台 | 需新增设置页面和管理后台 |
| **错误处理** | 前端 toast 提示 | 完整的错误码体系 + 用户友好提示 | 需统一错误处理机制 |
| **日志审计** | 本地日志文件 | 结构化日志 + 审计日志 + 可查询 | 需引入日志中心 |
| **监控告警** | 无 | QPS、延迟、错误率监控 + 告警 | 需引入 APM 系统 |
| **部署方式** | Docker Compose 单机部署 | K8s 集群部署 + 高可用 | 需提供 Helm Chart |
| **数据备份** | 手动备份文件系统 | 自动备份 + 恢复机制 | 需新增备份恢复功能 |
| **性能优化** | 未优化 | 并发控制、缓存策略、限流 | 需引入 Redis 缓存和限流 |
| **安全加固** | 无认证、无加密 | HTTPS、数据加密、Prompt 注入防护 | 需全面安全加固 |

### 1.6 关键成功指标（KPI）

**产品指标**：
- **用户留存率**：次日留存 > 40%，7 日留存 > 25%
- **核心功能使用率**：
  - 知识库创建率 > 80%（注册用户中）
  - Notebook 使用率 > 60%
  - Deep Research 使用率 > 30%
- **用户满意度**：NPS > 50

**技术指标**：
- **可用性**：系统可用率 > 99.5%
- **性能**：
  - 知识库上传处理：< 5 分钟/100MB
  - 智能问答响应：首 Token < 2 秒，全量 < 30 秒
  - Deep Research 完成：< 10 分钟（medium 模式）
  - PPT 生成：< 60 秒
- **并发能力**：支持 100 并发用户（单实例）
- **错误率**：API 错误率 < 1%

**交付指标**：
- **部署成功率**：私有化部署一次成功率 > 90%
- **文档完整度**：部署文档、用户手册、API 文档齐全
- **培训效果**：用户培训后独立使用率 > 80%

---

## 2. 信息架构

### 2.1 功能树

```
HI-NoteBook
├── Notebook（笔记本）
│   ├── 笔记本管理
│   │   ├── 创建笔记本
│   │   ├── 编辑笔记本
│   │   ├── 删除笔记本
│   │   └── 笔记本列表
│   ├── 记录管理
│   │   ├── 添加记录（从各功能保存）
│   │   ├── 查看记录详情
│   │   ├── 删除记录
│   │   └── 导入/导出记录
│   ├── 深度研究（Deep Research）
│   │   ├── 主题优化
│   │   ├── 主题拆解
│   │   ├── 多源搜索（RAG + Web + Paper）
│   │   ├── 交叉验证
│   │   └── 报告生成
│   ├── Grounded QA（基于知识库的问答）
│   │   ├── 选择知识库
│   │   ├── 提问
│   │   ├── 查看引用来源
│   │   └── 点击定位原文
│   └── Studio 能力（多媒体生成）
│       ├── PPT 生成
│       │   ├── 基于研究报告生成
│       │   ├── 选择样式模板
│       │   ├── 预览编辑
│       │   └── 导出下载
│       ├── 思维导图 [未实现]
│       ├── 播客生成 [部分实现：TTS 语音]
│       ├── 题目生成
│       │   ├── 基于知识库生成
│       │   ├── 模仿参考试卷
│       │   ├── 题目验证
│       │   └── 导出题目
│       └── 引导学习
│           ├── 选择主题和难度
│           ├── 交互式学习步骤
│           ├── 学习过程问答
│           └── 生成学习总结
├── Knowledge（知识库）
│   ├── 知识库管理
│   │   ├── 创建知识库
│   │   ├── 上传文档
│   │   ├── 查看文档列表
│   │   ├── 删除文档
│   │   └── 删除知识库
│   ├── 文档处理
│   │   ├── 文本提取
│   │   ├── 图片提取
│   │   ├── 向量化索引
│   │   └── 知识图谱构建
│   └── 知识检索
│       ├── Naive RAG（向量检索）
│       ├── Hybrid RAG（向量 + 知识图谱）
│       └── Query Item（精确查询）
├── Tools（工具集）
│   ├── 聊天对话（Chat）
│   │   ├── 创建会话
│   │   ├── 选择知识库（可选）
│   │   ├── 启用联网搜索（可选）
│   │   ├── 查看引用来源
│   │   └── 会话历史管理
│   ├── 智能写作（Co-Writer）
│   │   ├── Markdown 编辑器
│   │   ├── AI 辅助编辑（重写、扩写、润色）
│   │   ├── 自动标注
│   │   ├── TTS 语音播放
│   │   └── 导入/导出 Notebook
│   ├── 智能解题（Solver）
│   │   ├── 提交问题
│   │   ├── 多步推理（Investigate → Solve → Response）
│   │   ├── 查看逻辑流
│   │   ├── Token 统计
│   │   └── 保存到 Notebook
│   └── 创意生成（IdeaGen）
│       ├── 基于笔记记录生成想法
│       └── 提取知识点
├── Settings（设置）
│   ├── LLM 配置
│   │   ├── 添加 LLM Provider
│   │   ├── 测试连接
│   │   ├── 设置活跃 Provider
│   │   └── 查看支持的模型
│   ├── Embedding 配置
│   │   ├── 添加 Embedding Provider
│   │   ├── 测试连接
│   │   ├── 设置活跃 Provider
│   │   └── 配置向量维度
│   ├── TTS 配置
│   │   ├── 配置 TTS Provider
│   │   └── 测试语音生成
│   ├── 搜索配置
│   │   ├── 选择搜索引擎（Perplexity / Baidu）
│   │   └── 配置 API Key
│   └── 系统设置
│       ├── 语言设置
│       ├── 日志级别
│       └── 工具开关（Web Search、Paper Search、Code Execution）
└── History（历史记录）
    ├── 查看最近活动
    ├── 按类型筛选（Solve、Question、Research、Co-Writer）
    └── 查看活动详情
```

### 2.2 页面结构图

```
前端路由结构（Next.js App Router）

/                                    # 根页面（重定向到 /notebooks）
├── /notebooks                       # 笔记本列表页
│   └── /notebooks/[id]              # 笔记本详情页（三栏布局）
├── /knowledge                       # 知识库列表页
│   └── /knowledge/[name]            # 知识库详情页
├── /research                        # 深度研究实验室
├── /chat                            # 智能对话
├── /solver                          # 智能解题
├── /question                        # 智能出题
├── /co_writer                       # 智能写作
├── /ideagen                         # 创意生成
├── /guide                           # 引导学习
├── /settings                        # 设置页面
├── /history                         # 历史记录
└── /preview/ppt                     # PPT 预览页
```

### 2.3 功能边界说明

**Notebook 与 Tools 的区别**：
- **Notebook**：强关联笔记本，所有操作结果可保存到笔记本，形成知识沉淀
- **Tools**：弱关联或无关联笔记本，更偏向临时性的工具使用

**Studio 能力的定义**：
- Studio 是 Notebook 的扩展能力，专注于多媒体内容生成
- 所有 Studio 生成的内容（PPT、题目、播客、思维导图）都基于 Notebook 中的材料
- Studio 能力支持 MCP 协议扩展，可持续集成新的生成能力

**MCP 扩展点**：
- **Notebook Studio**：可扩展新的内容生成类型（如视频脚本、海报设计）
- **Tools**：可扩展行业特定工具（如法律文书生成、医疗报告分析）

---

## 3. 核心功能详细说明

### 3.1 笔记本管理（Notebook Management）

#### 3.1.1 功能目标
提供类似 NotebookLM 的笔记本管理能力，用户可以创建多个笔记本，每个笔记本包含多条记录（对话、研究报告、生成内容等），形成知识沉淀。

#### 3.1.2 用户场景
- **场景 1**：用户正在准备一个项目提案，创建名为"项目 A 提案"的笔记本，将相关的研究报告、对话记录、生成的 PPT 都保存在这个笔记本中
- **场景 2**：学生准备期末考试，创建"数据结构复习"笔记本，将学习笔记、生成的题目、引导学习记录都保存在其中
- **场景 3**：研究人员进行文献综述，创建"AI 安全研究"笔记本，将多次深度研究的报告、引用来源都整理在笔记本中

#### 3.1.3 用户路径

**创建笔记本**：
1. 用户访问 `/notebooks` 页面
2. 点击"创建笔记本"按钮
3. 填写笔记本名称、描述
4. 选择颜色和图标（可选）
5. 点击"创建"，系统生成笔记本 ID 并跳转到笔记本详情页

**添加记录到笔记本**：
1. 用户在任意功能页面（Research、Solver、Question、Co-Writer、Chat）完成任务
2. 点击"添加到笔记本"按钮
3. 在弹出的模态框中选择目标笔记本（支持多选）或创建新笔记本
4. 点击"保存"，系统将记录添加到选中的笔记本中
5. 显示成功提示

**查看笔记本详情**：
1. 用户在 `/notebooks` 页面点击某个笔记本卡片
2. 进入 `/notebooks/[id]` 详情页，展示三栏布局：
   - 左栏：笔记本列表（可切换）
   - 中栏：当前笔记本的记录列表（按时间倒序）
   - 右栏：选中记录的详细内容
3. 用户可以点击记录查看详情，支持展开/折叠

**导出笔记本**：
1. 用户在笔记本详情页点击"导出"按钮
2. 选择导出格式（Markdown / PDF）
3. 系统生成导出文件并下载

#### 3.1.4 状态机描述

```
笔记本状态：
- active：正常使用中
- archived：已归档（V1 未实现）

记录状态：
- normal：正常记录
- deleted：已删除（软删除，V1 未实现）
```

#### 3.1.5 关键交互说明
- **三栏布局**：左栏笔记本列表可折叠，中栏记录列表支持滚动加载，右栏详情支持 Markdown 渲染和 LaTeX 公式
- **记录类型标识**：每条记录有类型标签（solve、question、research、co_writer、chat、note），不同类型有不同的图标和颜色
- **快速切换**：用户可以在详情页左栏快速切换到其他笔记本，无需返回列表页

#### 3.1.6 异常处理机制
- **创建失败**：如果笔记本名称为空或重复，显示错误提示
- **保存记录失败**：如果网络异常或后端错误，显示重试按钮
- **导出失败**：如果导出超时（> 60 秒），显示错误提示并建议减少记录数量

#### 3.1.7 性能要求
- 笔记本列表加载：< 500ms
- 记录列表加载（100 条）：< 1 秒
- 记录详情渲染：< 300ms
- 导出 Markdown（100 条记录）：< 5 秒

#### 3.1.8 实现状态
✅ **已实现**：创建、编辑、删除笔记本，添加记录，查看详情，导出 Markdown
⚠️ **部分实现**：导出 PDF（前端有按钮，后端未实现）
❌ **未实现**：笔记本归档、记录软删除、记录搜索、记录标签

---

### 3.2 深度研究（Deep Research）

#### 3.2.1 功能目标
提供超越简单 RAG 的深度研究能力，通过主题拆解、多源检索（RAG + Web + Paper）、交叉验证、多轮迭代，生成高质量的研究报告。

#### 3.2.2 用户场景
- **场景 1**：产品经理需要了解"AI Agent 在企业中的应用现状"，使用 Deep Research 自动拆解为多个子主题（技术架构、应用案例、挑战与风险），并生成综合报告
- **场景 2**：学生写论文需要文献综述，输入"深度学习在医疗影像中的应用"，系统自动检索相关论文、网页、知识库内容，生成结构化综述
- **场景 3**：投资分析师研究某个行业，输入"新能源汽车市场趋势"，系统生成包含市场规模、竞争格局、技术趋势的深度报告

#### 3.2.3 用户路径

**启动深度研究**：
1. 用户访问 `/research` 页面
2. 在左侧配置面板中：
   - 输入研究主题（必填）
   - 选择知识库（可选，支持多选）
   - 选择研究模式（quick / medium / deep / auto）
   - 配置研究工具（RAG、Web Search、Paper Search、Code Execution）
3. 点击"开始研究"按钮
4. 系统创建研究项目并建立 WebSocket 连接

**研究过程实时追踪**：
1. 右侧研究仪表板显示三个阶段标签页：
   - **Planning**：显示主题优化和拆解过程
   - **Researching**：显示所有子主题的研究进度（任务网格）
   - **Reporting**：显示报告生成进度和最终报告
2. 用户可以点击任务网格中的子主题，查看详细的思考过程（sufficiency、plan、tool_call、note、error）
3. 实时日志流显示 Agent 的执行日志

**查看和导出报告**：
1. 研究完成后，Reporting 标签页显示完整的 Markdown 报告
2. 报告支持 Mermaid 图表渲染
3. 用户可以点击"导出 PDF"或"导出 PPT"按钮
4. 选择 PPT 样式模板（6 种预设：Corporate、Academic、Dark、Data、Narrative、Chinese）
5. 系统生成 PPT 并提供下载链接
6. 用户可以点击"保存到笔记本"将报告保存

**中途停止或重新生成**：
1. 用户可以在研究过程中点击"停止"按钮（V1 未实现）
2. 用户可以在报告生成后点击"重新生成"按钮，系统重新执行研究流程

#### 3.2.4 状态机描述

```
研究项目状态：
- created：已创建，未开始
- planning：规划阶段（主题优化、拆解）
- researching：研究阶段（多个子主题并行研究）
- reporting：报告生成阶段
- completed：已完成
- failed：失败

子主题状态：
- pending：等待研究
- researching：研究中
- completed：已完成
- failed：失败
```

#### 3.2.5 关键交互说明
- **任务网格可视化**：每个子主题显示为一个卡片，卡片上显示主题名称、状态、使用的工具图标（RAG、Web、Paper、Code）
- **实时进度更新**：通过 WebSocket 推送进度更新，前端实时刷新任务网格和日志流
- **思考过程展示**：点击子主题后，右侧显示 Agent 的思考过程，包括充分性判断、计划、工具调用、笔记记录、错误信息
- **报告预览**：报告支持 Markdown 渲染、LaTeX 公式、Mermaid 图表、代码高亮

#### 3.2.6 异常处理机制
- **主题拆解失败**：如果 LLM 返回格式错误或超时，显示错误提示并允许重试
- **子主题研究失败**：如果某个子主题研究失败（如工具调用超时），标记为 failed 状态，但不影响其他子主题
- **报告生成失败**：如果报告生成超时（> 5 分钟），显示错误提示并保留已完成的子主题结果
- **PPT 生成失败**：如果 PPT 生成失败（如 BananaPPT API 错误），显示错误提示并提供重试按钮

#### 3.2.7 性能要求
- 主题优化：< 10 秒
- 主题拆解：< 30 秒
- 单个子主题研究（medium 模式）：< 2 分钟
- 完整研究流程（medium 模式，5 个子主题）：< 10 分钟
- 报告生成：< 1 分钟
- PPT 生成：< 60 秒

#### 3.2.8 实现状态
✅ **已实现**：主题优化、主题拆解、多源检索（RAG + Web + Paper）、报告生成、导出 Markdown、导出 PPT
⚠️ **部分实现**：导出 PDF（前端有按钮，后端未实现）、代码执行（配置项存在，但未在 UI 中暴露）
❌ **未实现**：中途停止研究、研究进度保存与恢复、研究模板（预设研究流程）

---

### 3.3 Grounded QA（基于知识库的问答）

#### 3.3.1 功能目标
提供基于用户上传文档的智能问答能力，所有回答必须附引用来源，用户可以点击引用定位到原文，确保回答的可信度和可追溯性。

#### 3.3.2 用户场景
- **场景 1**：用户上传了公司的产品手册，询问"产品的退货政策是什么"，系统基于手册内容回答并附上引用页码
- **场景 2**：学生上传了教材 PDF，询问"什么是二叉搜索树"，系统基于教材回答并附上引用章节
- **场景 3**：律师上传了法律条文，询问"合同违约的赔偿标准"，系统基于条文回答并附上具体条款

#### 3.3.3 用户路径

**创建知识库并上传文档**：
1. 用户访问 `/knowledge` 页面
2. 点击"创建知识库"按钮
3. 填写知识库名称和描述
4. 点击"上传文档"，选择文件（支持 PDF、Word、Markdown、TXT、图片）
5. 系统通过 WebSocket 推送上传进度（文本提取、图片提取、向量化、知识图谱构建）
6. 上传完成后，知识库状态变为"已索引"

**基于知识库问答**：
1. 用户访问 `/chat` 页面
2. 在左侧设置面板中选择知识库（支持多选）
3. 输入问题并发送
4. 系统通过 WebSocket 流式返回回答
5. 回答下方显示引用来源列表，每个来源包含：
   - 来源类型（RAG / Web）
   - 文档名称
   - 引用片段
   - 相似度分数
6. 用户点击引用来源，系统定位到原文（V1 未实现）

**在 Notebook 中使用 Grounded QA**：
1. 用户在 `/notebooks/[id]` 详情页中
2. 右栏有一个"问答"标签页
3. 用户输入问题，系统基于笔记本关联的知识库回答
4. 回答自动保存为笔记本记录

#### 3.3.4 状态机描述

```
知识库状态：
- created：已创建，未上传文档
- indexing：索引中
- indexed：已索引，可使用
- failed：索引失败

文档状态：
- uploading：上传中
- processing：处理中（文本提取、向量化）
- indexed：已索引
- failed：处理失败
```

#### 3.3.5 关键交互说明
- **引用来源展示**：每个引用来源显示为一个卡片，包含文档名称、引用片段（高亮关键词）、相似度分数
- **多知识库支持**：用户可以同时选择多个知识库，系统会在所有选中的知识库中检索
- **流式回答**：回答逐字流式显示，提升用户体验
- **引用定位**：点击引用来源后，系统打开原文档并高亮引用片段（V1 未实现，需要文档预览功能）

#### 3.3.6 异常处理机制
- **知识库为空**：如果用户未选择知识库或知识库中没有文档，显示提示"请先上传文档到知识库"
- **检索超时**：如果 RAG 检索超时（> 30 秒），显示错误提示并允许重试
- **无相关结果**：如果检索结果相似度过低（< 0.3），系统回答"抱歉，我在知识库中没有找到相关信息"
- **LLM 错误**：如果 LLM 调用失败，显示错误提示并保留已检索的引用来源

#### 3.3.7 性能要求
- 文档上传处理：< 5 分钟/100MB
- RAG 检索：< 2 秒
- 首 Token 响应：< 2 秒
- 完整回答生成：< 30 秒

#### 3.3.8 实现状态
✅ **已实现**：知识库创建、文档上传、向量化索引、知识图谱构建、RAG 检索（Naive + Hybrid）、引用来源展示
⚠️ **部分实现**：引用定位（前端有点击事件，但未实现文档预览功能）
❌ **未实现**：文档预览、引用片段高亮、多模态检索（图片检索）、知识库版本管理

---

## 4. 代码映射表

### 4.1 笔记本管理功能映射

| 功能点 | 前端页面 | 关键组件 | API Endpoint | Agent/服务 | 数据存储 | 配置项 |
|--------|---------|---------|-------------|-----------|---------|--------|
| 笔记本列表 | `/notebooks` (`app/notebooks/page.tsx`) | - | `GET /api/notebook` | `NotebookManager` | `data/user/notebook/notebooks_index.json` | - |
| 创建笔记本 | `/notebooks` | - | `POST /api/notebook/create` | `NotebookManager.create_notebook()` | `data/user/notebook/{id}.json` | - |
| 笔记本详情 | `/notebooks/[id]` (`app/notebooks/[id]/page.tsx`) | - | `GET /api/notebook/{notebook_id}` | `NotebookManager.get_notebook()` | `data/user/notebook/{id}.json` | - |
| 添加记录 | 各功能页面 | `AddToNotebookModal.tsx` | `POST /api/notebook/{notebook_id}/sections` | `NotebookManager.add_record()` | `data/user/notebook/{id}.json` | - |
| 导出 Markdown | `/notebooks/[id]` | - | 前端生成 | - | - | - |
| 导出 PDF | `/notebooks/[id]` | - | ❌ 未实现 | - | - | - |

**实现状态**: ✅ 已实现（除导出 PDF）

---

### 4.2 深度研究功能映射

| 功能点 | 前端页面 | 关键组件 | API Endpoint | Agent/服务 | 数据存储 | 配置项 |
|--------|---------|---------|-------------|-----------|---------|--------|
| 研究配置 | `/research` (`app/research/page.tsx`) | 左侧配置面板 | - | - | - | `config/main.yaml: research` |
| 创建研究 | `/research` | - | `POST /api/research/create` | `ResearchOrchestrator` | `data/user/research/cache/{id}/` | - |
| 主题优化 | `/research` | `ResearchDashboard.tsx` | `WebSocket /api/research/{id}/execute` | `RephraseAgent` | `{id}_progress.json` | `config/agents.yaml: research` |
| 主题拆解 | `/research` | `ResearchDashboard.tsx` | WebSocket | `DecomposeAgent` | `{id}_queue.json` | `research.planning.decompose` |
| 子主题研究 | `/research` | `TaskGrid.tsx`, `ActiveTaskDetail.tsx` | WebSocket | `ResearchAgent`, `NoteAgent` | `{id}_queue.json` | `research.researching` |
| 报告生成 | `/research` | `ResearchDashboard.tsx` | WebSocket | `ReportingAgent` | `data/user/research/reports/{id}.md` | - |
| 导出 PPT | `/research` | `PptPreviewModal.tsx` | `GET /api/research/{id}/export/ppt` | BananaPPT API | `data/user/notebook/exports/` | `export.banana_ppt` |
| 导出 PDF | `/research` | - | `GET /api/research/{id}/export/pdf` | ❌ 未实现 | - | - |

**Agent 调用链**:
```
ResearchOrchestrator
  ├─> RephraseAgent (主题优化)
  ├─> DecomposeAgent (主题拆解)
  ├─> ManagerAgent (队列管理)
  ├─> ResearchAgent (多轮检索)
  │     ├─> RAG Tool (rag_naive / rag_hybrid)
  │     ├─> Web Search Tool
  │     ├─> Paper Search Tool
  │     └─> Code Execution Tool
  ├─> NoteAgent (记录摘要)
  └─> ReportingAgent (生成报告)
```

**数据流**:
```
用户输入主题
  → POST /api/research/create
  → 创建 DynamicTopicQueue
  → WebSocket 连接建立
  → RephraseAgent 优化主题
  → DecomposeAgent 拆解子主题
  → 并行执行子主题研究
  → NoteAgent 记录每个子主题的摘要
  → ReportingAgent 生成最终报告
  → 保存到 data/user/research/reports/{id}.md
```

**实现状态**: ✅ 已实现（除导出 PDF）

---

### 4.3 知识库与 RAG 功能映射

| 功能点 | 前端页面 | 关键组件 | API Endpoint | Agent/服务 | 数据存储 | 配置项 |
|--------|---------|---------|-------------|-----------|---------|--------|
| 知识库列表 | `/knowledge` (`app/knowledge/page.tsx`) | - | `GET /api/knowledge` | `KnowledgeBaseManager` | `data/knowledge_bases/kb_config.json` | - |
| 创建知识库 | `/knowledge` | - | `POST /api/knowledge` | `KnowledgeBaseManager.create()` | `data/knowledge_bases/{name}/` | - |
| 上传文档 | `/knowledge` | - | `POST /api/knowledge/{kb_id}/documents` | `DocumentProcessor` | `{name}/raw/`, `{name}/images/` | - |
| 文档处理 | 后台 | - | WebSocket `/api/knowledge/{kb_id}/upload-progress` | `LightRAG.insert()` | `{name}/rag_storage/` | `EMBEDDING_*` 环境变量 |
| 向量检索 | `/chat`, `/research` | - | 内部调用 | `RAGTool.rag_naive()` | `{name}/rag_storage/vdb_*.json` | `tools.rag_tool` |
| 混合检索 | `/chat`, `/research` | - | 内部调用 | `RAGTool.rag_hybrid()` | `{name}/rag_storage/` | `tools.rag_tool` |
| 知识图谱查询 | `/chat`, `/research` | - | 内部调用 | `RAGTool.query_item()` | `{name}/rag_storage/kv_store_*.json` | - |

**文档处理流程**:
```
用户上传文档
  → POST /api/knowledge/{kb_id}/documents
  → DocumentProcessor.process()
  → 文本提取 (PDF/Word/Markdown/TXT)
  → 图片提取 (保存到 images/)
  → 分块 (Chunking)
  → Embedding (调用 Embedding Provider)
  → 向量化索引 (nano_vectordb)
  → 知识图谱构建 (LightRAG)
  → 保存到 rag_storage/
  → WebSocket 推送进度
```

**RAG 检索流程**:
```
用户提问
  → Agent 调用 RAG Tool
  → rag_naive: 纯向量检索
  │   ├─> Embedding 用户问题
  │   ├─> 向量相似度搜索 (vdb_chunks.json)
  │   └─> 返回 top_k 文本块
  → rag_hybrid: 向量 + 知识图谱
  │   ├─> 向量检索 (同 rag_naive)
  │   ├─> 实体识别
  │   ├─> 知识图谱查询 (kv_store_entities.json)
  │   └─> 融合结果
  → 返回检索结果 + 引用来源
```

**实现状态**: ✅ 已实现

---

### 4.4 智能对话功能映射

| 功能点 | 前端页面 | 关键组件 | API Endpoint | Agent/服务 | 数据存储 | 配置项 |
|--------|---------|---------|-------------|-----------|---------|--------|
| 聊天界面 | `/chat` (`app/chat/page.tsx`) | 左侧会话列表 + 右侧聊天 | `WebSocket /api/chat` | `ChatAgent` | `data/user/chat_sessions.json` | `config/agents.yaml: chat` |
| 会话管理 | `/chat` | - | `GET /api/chat/sessions` | `ChatSessionManager` | `data/user/chat_sessions.json` | - |
| 知识库选择 | `/chat` | 左侧设置面板 | - | - | - | - |
| 联网搜索 | `/chat` | 左侧设置面板 | 内部调用 | `WebSearchTool` | - | `tools.web_search`, `SEARCH_PROVIDER` |
| 引用来源 | `/chat` | `ChatSessionDetail.tsx` | - | - | - | - |

**对话流程**:
```
用户发送消息
  → WebSocket /api/chat
  → ChatAgent.process()
  → 如果启用知识库: 调用 RAG Tool
  → 如果启用联网: 调用 Web Search Tool
  → LLM 生成回答
  → 流式返回 (WebSocket)
  → 保存会话到 chat_sessions.json
```

**实现状态**: ✅ 已实现

---

### 4.5 智能解题功能映射

| 功能点 | 前端页面 | 关键组件 | API Endpoint | Agent/服务 | 数据存储 | 配置项 |
|--------|---------|---------|-------------|-----------|---------|--------|
| 解题界面 | `/solver` (`app/solver/page.tsx`) | 左侧聊天 + 右侧逻辑流 | `WebSocket /api/solve/solve` | Solve Agent 链 | `data/user/solve/` | `config/main.yaml: solve` |
| 逻辑流展示 | `/solver` | 右侧面板 | - | - | - | - |
| Token 统计 | `/solver` | 右侧面板 | - | `LLMStats` | - | - |

**Solve Agent 调用链**:
```
用户提交问题
  → WebSocket /api/solve/solve
  → Analysis Loop:
  │   ├─> InvestigateAgent (生成查询)
  │   │     ├─> RAG Tool
  │   │     ├─> Web Search Tool
  │   │     └─> Query Item Tool
  │   └─> NoteAgent (生成摘要)
  → Solve Loop:
  │   ├─> ManagerAgent (规划步骤)
  │   ├─> SolveAgent (工具规划)
  │   ├─> ToolAgent (执行工具)
  │   ├─> ResponseAgent (生成响应)
  │   └─> PrecisionAnswerAgent (精确答案)
  → 流式返回结果
```

**实现状态**: ✅ 已实现

---

### 4.6 题目生成功能映射

| 功能点 | 前端页面 | 关键组件 | API Endpoint | Agent/服务 | 数据存储 | 配置项 |
|--------|---------|---------|-------------|-----------|---------|--------|
| 题目生成 | `/question` (`app/question/page.tsx`) | `QuestionDashboard.tsx` | `WebSocket /api/question/generate` | `QuestionGenerationAgent` | `data/user/question/` | `config/main.yaml: question` |
| 模仿试卷 | `/question` | - | `WebSocket /api/question/mimic` | `QuestionGenerationAgent` | - | - |
| 题目验证 | `/question` | `QuestionTaskGrid.tsx` | - | `QuestionValidationAgent` | - | - |

**题目生成流程**:
```
用户配置题目参数
  → WebSocket /api/question/generate
  → QuestionGenerationAgent (ReAct 架构)
  │   ├─> retrieve: RAG 检索知识点
  │   ├─> generate_question: 生成题目
  │   ├─> refine_question: 优化题目
  │   └─> submit_question: 提交题目
  → QuestionValidationAgent 验证
  → 返回题目列表
```

**实现状态**: ✅ 已实现

---

### 4.7 智能写作功能映射

| 功能点 | 前端页面 | 关键组件 | API Endpoint | Agent/服务 | 数据存储 | 配置项 |
|--------|---------|---------|-------------|-----------|---------|--------|
| Markdown 编辑器 | `/co_writer` (`app/co_writer/page.tsx`) | `CoWriterEditor.tsx` | - | - | - | - |
| AI 辅助编辑 | `/co_writer` | `CoWriterEditor.tsx` | `POST /api/co-writer/edit` | `EditAgent` | `data/user/co-writer/` | `config/agents.yaml: co_writer` |
| 自动标注 | `/co_writer` | `CoWriterEditor.tsx` | `POST /api/co-writer/edit` | `EditAgent` | - | - |
| TTS 语音 | `/co_writer` | `CoWriterEditor.tsx` | `POST /api/co-writer/narrate` | `NarratorAgent` | - | `TTS_*` 环境变量 |

**AI 编辑流程**:
```
用户选中文本 + 选择操作
  → POST /api/co-writer/edit
  → EditAgent.process()
  │   ├─> 如果启用 RAG: 检索相关知识
  │   ├─> 如果启用 Web: 搜索相关信息
  │   └─> LLM 生成编辑结果
  → 返回编辑后的文本
  → 前端替换选中文本
```

**实现状态**: ✅ 已实现

---

## 5. 核心链路深度拆解

### 5.1 链路 1：知识库构建 → RAG 检索 → 问答

#### 5.1.1 调用顺序

```
[用户] 上传文档
  ↓
[前端] POST /api/knowledge/{kb_id}/documents (multipart/form-data)
  ↓
[后端] KnowledgeRouter.upload_documents()
  ↓
[DocumentProcessor] 文档处理
  ├─> extract_text() - 文本提取
  │     ├─> PDF: PyMuPDF
  │     ├─> Word: python-docx
  │     ├─> Markdown/TXT: 直接读取
  │     └─> 保存到 {kb_name}/raw/
  ├─> extract_images() - 图片提取
  │     └─> 保存到 {kb_name}/images/
  ├─> chunk_text() - 文本分块
  │     └─> 按段落/句子分块
  └─> vectorize() - 向量化
        ↓
[LightRAG] insert()
  ├─> Embedding API 调用
  │     ├─> 环境变量: EMBEDDING_HOST, EMBEDDING_API_KEY
  │     └─> 模型: EMBEDDING_MODEL (如 text-embedding-3-large)
  ├─> 向量索引构建 (nano_vectordb)
  │     └─> 保存到 vdb_chunks.json
  ├─> 知识图谱构建
  │     ├─> 实体识别 (LLM)
  │     ├─> 关系抽取 (LLM)
  │     └─> 保存到 kv_store_entities.json, kv_store_relations.json
  └─> WebSocket 推送进度
        ↓
[前端] 显示上传进度
  ↓
[用户] 在 /chat 页面提问
  ↓
[前端] WebSocket /api/chat (query + kb_name)
  ↓
[后端] ChatAgent.process()
  ├─> RAGTool.rag_hybrid()
  │     ├─> Embedding 用户问题
  │     ├─> 向量检索 (vdb_chunks.json)
  │     ├─> 实体识别
  │     ├─> 知识图谱查询 (kv_store_entities.json)
  │     └─> 融合结果 (top_k=30)
  ├─> LLM 生成回答
  │     ├─> Prompt: 系统提示 + 检索结果 + 用户问题
  │     └─> 流式生成
  └─> 返回回答 + 引用来源
        ↓
[前端] 流式显示回答 + 引用来源卡片
```

#### 5.1.2 异常路径

| 异常场景 | 检测点 | 处理策略 | 用户提示 |
|---------|--------|---------|---------|
| 文档格式不支持 | DocumentProcessor.extract_text() | 返回错误，跳过该文档 | "文件格式不支持，请上传 PDF/Word/Markdown/TXT" |
| 文档过大 (> 100MB) | upload_documents() | 返回 413 错误 | "文件过大，请上传小于 100MB 的文件" |
| Embedding API 超时 | LightRAG.insert() | 重试 3 次，间隔 5 秒 | "向量化超时，正在重试..." |
| Embedding API 配额耗尽 | LightRAG.insert() | 停止处理，保存进度 | "Embedding API 配额不足，请检查配置" |
| 向量化失败 | LightRAG.insert() | 标记文档为 failed | "文档处理失败，请重新上传" |
| RAG 检索超时 (> 30s) | RAGTool.rag_hybrid() | 返回空结果 | "检索超时，请重试" |
| 检索结果为空 | ChatAgent.process() | LLM 回答"未找到相关信息" | 正常显示回答 |
| LLM API 超时 | ChatAgent.process() | 重试 2 次 | "生成回答超时，正在重试..." |
| LLM API 错误 | ChatAgent.process() | 返回错误信息 | "AI 服务异常，请稍后重试" |

#### 5.1.3 超时策略

| 操作 | 超时时间 | 重试次数 | 重试间隔 |
|------|---------|---------|---------|
| 文档上传 | 60s | 0 | - |
| 文本提取 | 30s/文档 | 0 | - |
| Embedding API 调用 | 10s/请求 | 3 | 5s |
| 向量索引构建 | 无限制 | 0 | - |
| 知识图谱构建 | 无限制 | 0 | - |
| RAG 检索 | 30s | 0 | - |
| LLM 生成 | 60s | 2 | 3s |

#### 5.1.4 可观测性建议

**日志记录**:
- 文档上传: 文件名、大小、格式、用户 ID
- 文档处理: 处理时长、分块数量、向量化耗时
- RAG 检索: 查询语句、检索耗时、结果数量、相似度分数
- LLM 调用: 模型名称、Token 数量、耗时、错误信息

**监控指标**:
- 文档处理成功率
- 平均处理时长 (按文件大小分段)
- RAG 检索 P50/P95/P99 延迟
- LLM 调用成功率
- Token 消耗量 (按用户/知识库统计)

**告警规则**:
- 文档处理失败率 > 10%
- RAG 检索 P95 延迟 > 5s
- LLM 调用失败率 > 5%
- Embedding API 配额剩余 < 10%

---

### 5.2 链路 2：Deep Research 全流程

#### 5.2.1 调用顺序

```
[用户] 输入研究主题 + 配置参数
  ↓
[前端] POST /api/research/create
  ↓
[后端] ResearchRouter.create_research()
  ├─> 创建研究 ID
  ├─> 初始化 DynamicTopicQueue
  └─> 返回 research_id
        ↓
[前端] WebSocket /api/research/{research_id}/execute
  ↓
[后端] ResearchOrchestrator.execute()
  ↓
[阶段 1: Planning] 主题优化与拆解
  ├─> RephraseAgent.rephrase()
  │     ├─> LLM 优化主题表述
  │     └─> 推送进度: {"stage": "planning", "step": "rephrase"}
  ├─> DecomposeAgent.decompose()
  │     ├─> 如果启用 RAG: 检索背景知识
  │     ├─> LLM 拆解子主题
  │     │     ├─> 模式: manual (指定数量) / auto (自动生成)
  │     │     └─> 输出: [{sub_topic, overview}, ...]
  │     ├─> 创建 TopicBlock 列表
  │     └─> 推送进度: {"stage": "planning", "step": "decompose", "topics": [...]}
  └─> 保存到 {research_id}_queue.json
        ↓
[阶段 2: Researching] 并行研究子主题
  ├─> ManagerAgent.manage_queue()
  │     └─> 选择 pending 状态的子主题
  ├─> 并行执行 (最多 5 个并发)
  │     └─> ResearchAgent.research(topic_block)
  │           ├─> 迭代模式: fixed (固定次数) / flexible (动态停止)
  │           ├─> 每轮迭代:
  │           │     ├─> sufficiency_check() - 判断信息是否充分
  │           │     ├─> plan_tools() - 规划工具调用
  │           │     ├─> execute_tools() - 执行工具
  │           │     │     ├─> rag_naive / rag_hybrid
  │           │     │     ├─> web_search
  │           │     │     ├─> paper_search
  │           │     │     └─> run_code
  │           │     └─> NoteAgent.summarize() - 生成摘要
  │           ├─> 保存 ToolTrace 列表
  │           └─> 推送进度: {"stage": "researching", "block_id": "...", "status": "completed"}
  └─> 等待所有子主题完成
        ↓
[阶段 3: Reporting] 生成报告
  ├─> ReportingAgent.generate_report()
  │     ├─> 收集所有子主题的摘要
  │     ├─> LLM 生成结构化报告
  │     │     ├─> Markdown 格式
  │     │     ├─> 包含引用来源
  │     │     └─> 支持 Mermaid 图表
  │     └─> 保存到 data/user/research/reports/{research_id}.md
  └─> 推送进度: {"stage": "reporting", "status": "completed"}
        ↓
[前端] 显示完整报告
  ↓
[用户] 点击"导出 PPT"
  ↓
[前端] GET /api/research/{research_id}/export/ppt?style=corporate
  ↓
[后端] ResearchRouter.export_ppt()
  ├─> 读取研究报告 Markdown
  ├─> 解析报告结构 (标题、要点、图表)
  ├─> 调用 BananaPPT API
  │     ├─> 环境变量: BANANA_PPT_API_KEY, BANANA_PPT_URL
  │     ├─> 请求体: {content, style, theme_color, accent_color}
  │     └─> 超时: 60s
  ├─> 保存 PPT 文件到 data/user/notebook/exports/
  └─> 返回下载链接
        ↓
[前端] 下载 PPT 文件
```

#### 5.2.2 异常路径

| 异常场景 | 检测点 | 处理策略 | 用户提示 |
|---------|--------|---------|---------|
| 主题拆解失败 | DecomposeAgent.decompose() | 重试 2 次，失败则使用原主题 | "主题拆解失败，将使用原主题进行研究" |
| 子主题研究超时 (> 5min) | ResearchAgent.research() | 标记为 failed，继续其他子主题 | "子主题研究超时，已跳过" |
| 工具调用失败 | ResearchAgent.execute_tools() | 记录错误，继续下一轮迭代 | 在日志中显示错误 |
| RAG 检索无结果 | ResearchAgent.execute_tools() | 尝试 Web Search | 自动切换工具 |
| Web Search 配额耗尽 | WebSearchTool.search() | 跳过 Web Search，仅使用 RAG | "联网搜索配额不足，仅使用知识库" |
| 报告生成失败 | ReportingAgent.generate_report() | 重试 2 次，失败则返回原始摘要 | "报告生成失败，显示原始研究结果" |
| PPT 生成失败 | BananaPPT API | 返回错误信息 + 重试按钮 | "PPT 生成失败: {error_message}，请重试" |
| PPT API 超时 | export_ppt() | 返回 504 错误 | "PPT 生成超时，请稍后重试" |

#### 5.2.3 超时策略

| 操作 | 超时时间 | 重试次数 | 重试间隔 |
|------|---------|---------|---------|
| 主题优化 | 30s | 2 | 5s |
| 主题拆解 | 60s | 2 | 5s |
| 单轮工具调用 | 60s | 0 | - |
| 子主题研究 (总计) | 5min | 0 | - |
| 报告生成 | 120s | 2 | 10s |
| PPT 生成 | 60s | 0 | - |

#### 5.2.4 重试机制

**LLM 调用重试**:
- 触发条件: 超时、429 错误、500 错误
- 重试策略: 指数退避 (1s, 2s, 4s)
- 最大重试: 3 次

**工具调用重试**:
- RAG 检索: 不重试 (快速失败)
- Web Search: 重试 1 次
- Paper Search: 重试 1 次
- Code Execution: 不重试

#### 5.2.5 可观测性建议

**日志记录**:
- 研究创建: research_id, 主题, 配置参数
- 每个阶段: 开始时间、结束时间、状态
- 每个子主题: block_id, 迭代次数、工具调用记录、Token 消耗
- 工具调用: 工具类型、查询语句、结果数量、耗时
- 错误: 错误类型、错误信息、堆栈跟踪

**监控指标**:
- 研究完成率 (按模式统计: quick/medium/deep)
- 平均完成时长
- 子主题失败率
- 工具调用成功率 (按工具类型统计)
- Token 消耗量 (按阶段统计)
- PPT 生成成功率

**告警规则**:
- 研究失败率 > 10%
- 平均完成时长 > 15min (medium 模式)
- 子主题失败率 > 20%
- PPT 生成失败率 > 15%

---
