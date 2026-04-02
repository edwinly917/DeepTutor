# Deep Research 详细实现方案

## 1. 系统架构总览

Deep Research 采用 **三阶段流水线**（Planning → Researching → Reporting），通过 WebSocket 实时推送进度，最终生成带引用的 Markdown 研究报告。

```
┌─────────────────────────────────────────────────────────┐
│                      Frontend (Next.js)                 │
│  research/page.tsx ←→ WebSocket ←→ ResearchDashboard    │
└──────────────────────────┬──────────────────────────────┘
                           │ WebSocket /api/v1/research/run
┌──────────────────────────▼──────────────────────────────┐
│                  API Router (FastAPI)                    │
│               src/api/routers/research.py               │
│  - WebSocket handler (run)                              │
│  - REST endpoints (status, export, optimize_topic...)   │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│              ResearchPipeline (Orchestrator)             │
│         src/agents/research/research_pipeline.py        │
│                                                         │
│  Phase 1: Planning                                      │
│    RephraseAgent → DecomposeAgent → ManagerAgent        │
│                                                         │
│  Phase 2: Researching                                   │
│    ResearchAgent ←→ NoteAgent (per TopicBlock)          │
│    Tools: RAG / Web / Paper / Code                      │
│                                                         │
│  Phase 3: Reporting                                     │
│    ReportingAgent (去重 → 大纲 → 写作 → 引用)            │
└─────────────────────────────────────────────────────────┘
```

---

## 2. 关键文件一览

| 文件路径 | 行数 | 职责 |
|---------|------|------|
| `src/api/routers/research.py` | ~924 | WebSocket handler + REST 端点 |
| `src/agents/research/research_pipeline.py` | ~1600 | 三阶段编排引擎 |
| `src/agents/research/data_structures.py` | ~454 | DynamicTopicQueue, TopicBlock, ToolTrace |
| `src/agents/research/agents/rephrase_agent.py` | ~200 | 话题优化 Agent |
| `src/agents/research/agents/decompose_agent.py` | ~300 | 话题分解 Agent |
| `src/agents/research/agents/research_agent.py` | ~600 | 主研究循环 Agent |
| `src/agents/research/agents/note_agent.py` | ~200 | 工具输出摘要 Agent |
| `src/agents/research/agents/reporting_agent.py` | ~600 | 报告生成 Agent |
| `src/agents/research/agents/manager_agent.py` | ~200 | 队列管理 Agent |
| `src/agents/research/utils/citation_manager.py` | ~400 | 引用追踪 |
| `src/agents/research/utils/token_tracker.py` | - | Token 用量追踪 |
| `web/app/research/page.tsx` | ~1200 | 前端主页面 |
| `web/components/research/ResearchDashboard.tsx` | ~600 | 进度看板组件 |
| `web/types/research.ts` | ~163 | TypeScript 类型定义 |
| `config/main.yaml` | - | 运行时配置 (research section) |
| `src/agents/research/prompts/{lang}/` | - | 各 Agent 的 Prompt 模板 |

---

## 3. 数据结构

### 3.1 TopicStatus（话题状态枚举）

```python
class TopicStatus(Enum):
    PENDING      = "pending"       # 等待研究
    RESEARCHING  = "researching"   # 正在研究
    COMPLETED    = "completed"     # 研究完成
    FAILED       = "failed"        # 研究失败
```

### 3.2 ToolType（工具类型枚举）

```python
class ToolType(Enum):
    RAG_NAIVE     # 朴素 RAG 检索
    RAG_HYBRID    # 混合 RAG 检索
    QUERY_ITEM    # 知识库精确查找
    WEB_SEARCH    # 互联网搜索
    PAPER_SEARCH  # 学术论文搜索
    RUN_CODE      # Python 代码执行
```

### 3.3 ToolTrace（工具调用记录）

```python
@dataclass
class ToolTrace:
    tool_id: str          # 唯一工具执行 ID
    citation_id: str      # 引用 ID, 如 "CIT-1-02"
    tool_type: str        # 工具类型
    query: str            # 原始查询
    raw_answer: str       # 工具原始结果（超 50KB 自动截断）
    summary: str          # LLM 生成的摘要
```

- **自动截断策略**: 原始输出超过 50KB 时智能截断，优先保留 JSON 结构完整性
- 支持 `to_dict()` / `from_dict()` 序列化

### 3.4 TopicBlock（话题块）

```python
@dataclass
class TopicBlock:
    block_id: str              # 如 "block_1", "block_2"
    sub_topic: str             # 子话题标题
    overview: str              # 背景描述
    status: TopicStatus        # 当前状态
    tool_traces: List[ToolTrace]  # 该话题的所有工具调用
    iteration_count: int       # 已执行的迭代次数
    created_at: str            # 创建时间
    updated_at: str            # 更新时间
    metadata: dict             # 自定义元数据
```

### 3.5 DynamicTopicQueue（动态话题队列）

```python
class DynamicTopicQueue:
    research_id: str
    blocks: List[TopicBlock]   # 有序话题列表
    block_counter: int         # 自增计数器
    max_length: int | None     # 容量上限
    state_file: str | None     # 自动持久化路径（JSON）
```

**核心方法:**

| 方法 | 说明 |
|------|------|
| `add_block(sub_topic, overview)` | 添加新话题块，返回 TopicBlock |
| `get_pending_block()` | 获取第一个 PENDING 状态的块 |
| `mark_researching(block_id)` | 标记为研究中 |
| `mark_completed(block_id)` | 标记为已完成 |
| `mark_failed(block_id, reason)` | 标记为失败 |
| `has_topic(sub_topic)` | 去重检查 |
| `save_to_json()` / `load_from_json()` | 持久化 |
| `get_statistics()` | 统计: total/pending/researching/completed/failed/total_tool_calls |

---

## 4. Agent 体系

所有 Agent 继承自 `BaseAgent`（`src/agents/base_agent.py`），具备:
- `call_llm(user_prompt, system_prompt, stage)` — LLM 调用
- `get_prompt(section, key)` — Prompt 模板管理
- 配置访问、日志集成

### 4.1 RephraseAgent（话题优化）

- **用途**: 优化用户输入的研究话题，使其更适合自动化研究
- **方法**: `process(user_input, iteration, previous_result)`
- **特性**: 维护多轮对话上下文，支持用户反馈循环（CLI 模式）
- **输出**: `{ topic: str, iteration: int }`
- **可关闭**: 通过 `planning.rephrase.enabled` 配置

### 4.2 DecomposeAgent（话题分解）

- **用途**: 将主题拆解为多个子话题
- **两种模式**:
  - **Manual**: 固定数量子话题（由 `initial_subtopics` 控制）
  - **Auto**: 根据话题复杂度自动决定 3~N 个子话题
- **RAG 集成**: 可选择使用 RAG 检索为分解提供上下文
- **输出**:
  ```json
  {
    "main_topic": "xxx",
    "sub_topics": [{"title": "...", "overview": "..."}],
    "total_subtopics": 5,
    "sub_queries": ["..."],
    "rag_context": "...",
    "mode": "manual"
  }
  ```

### 4.3 ResearchAgent（研究执行）

- **用途**: 对单个 TopicBlock 执行多轮迭代式研究
- **方法**: `process(topic_block, call_tool_callback, ...)`
- **核心循环**:
  1. 检查知识充分性（sufficiency check）
  2. 若不充分 → 生成查询
  3. 调用工具（RAG/Web/Paper/Code）
  4. NoteAgent 摘要化结果
  5. 重复直到充分或达到最大迭代次数

- **工具选择策略（分阶段）**:

  | 阶段 | 迭代位置 | 策略 |
  |------|---------|------|
  | Phase 1（早期） | 前 1/3 迭代 | RAG 为主，知识库探索 |
  | Phase 2（中期） | 中 1/3 迭代 | 深度 RAG + 外部工具（Web、Paper） |
  | Phase 3（后期） | 后 1/3 迭代 | 全工具 + 验证（Code、交叉验证） |

- **输出**:
  ```json
  {
    "iterations": 5,
    "tools_used": ["rag_hybrid", "web_search"],
    "queries_used": ["..."],
    "knowledge_notes": ["..."],
    "new_topics": ["..."]
  }
  ```

### 4.4 NoteAgent（摘要生成）

- **用途**: 将工具原始输出压缩为知识摘要
- **方法**: `process(tool_type, query, raw_answer, citation_id, topic, context)`
- **输出**: 填充后的 `ToolTrace`（含 summary 和 citation_id）

### 4.5 ManagerAgent（队列管理）

- **用途**: 管理 DynamicTopicQueue 的任务调度
- **核心方法**:

  | 方法 | 说明 |
  |------|------|
  | `get_next_task()` | FIFO 获取下一个 PENDING 块 |
  | `complete_task(block_id)` | 标记完成 |
  | `fail_task(block_id, reason)` | 标记失败 |
  | `add_new_topic(sub_topic, overview)` | 动态添加新话题 |
  | `is_research_complete()` | 检查是否全部完成 |

- **并行安全**: 并行模式下使用 `asyncio.Lock()` + Async 变体方法

### 4.6 ReportingAgent（报告生成）

- **用途**: 生成最终 Markdown 研究报告
- **流程**:
  1. `process_deduplication()` — 去除重复话题/内容
  2. `generate_outline()` — 生成报告大纲
  3. `write_report()` — 逐章节 LLM 写作，嵌入引用
  4. `build_structured_sources_and_catalog()` — 构建参考文献列表

- **引用系统**:
  - 行内引用: 文中 `[1]`, `[2]`
  - 参考文献: 报告末尾编号列表
  - 通过 `CitationManager` 统一管理

- **输出**:
  ```json
  {
    "report": "# 报告标题\n...",
    "outline": {"sections": [...]},
    "word_count": 3200,
    "sources": {"web": [...], "rag": [...]},
    "source_catalog": [{"ref_number": 1, "title": "...", "url": "..."}]
  }
  ```

---

## 5. 引用管理系统

### CitationManager (`src/agents/research/utils/citation_manager.py`)

**引用 ID 格式:**

| 阶段 | 格式 | 示例 |
|------|------|------|
| Planning | `PLAN-XX` | `PLAN-01`, `PLAN-02` |
| Research | `CIT-{block}-{seq}` | `CIT-1-01`, `CIT-3-05` |

**核心方法:**

```python
generate_plan_citation_id()           → "PLAN-XX"
generate_research_citation_id(block)  → "CIT-X-XX"
add_citation(id, tool_type, trace, raw)  → 保存到 JSON
get_all_citations()                   → {citation_id: {tool_type, summary, sources}}
get_ref_number_map()                  → {citation_id: [1, 2, 3]}  # 报告引用编号
```

**持久化**: `cache/{research_id}/citations.json`，支持计数器恢复防止 ID 冲突

---

## 6. Pipeline 三阶段详解

### 6.1 Phase 1: Planning（规划阶段）

```
用户输入话题
    │
    ▼
RephraseAgent.process(topic)
    │  LLM 优化话题表述
    │  (可选，由 rephrase.enabled 控制)
    ▼
DecomposeAgent.process(optimized_topic, N, mode)
    │  ├─ RAG 搜索上下文（可选）
    │  └─ LLM 生成 N 个子话题 + 概述
    ▼
ManagerAgent × N
    │  将每个子话题添加为 TopicBlock
    ▼
DynamicTopicQueue: [block_1...block_N 全部 PENDING]
    │
    ▼ 保存至 step1_planning.json
```

### 6.2 Phase 2: Researching（研究阶段）

支持两种执行模式:

#### Series 模式（默认，顺序执行）

```python
while queue.has_pending_blocks():
    block = manager.get_next_task()       # 获取 PENDING 块
    result = research.process(block)      # 单线程执行
    manager.complete_task(block.id)       # 标记完成
```

#### Parallel 模式（并行执行）

```python
semaphore = Semaphore(max_parallel_topics)

for pending_block in initial_blocks:
    asyncio.create_task(research_single_block(block))  # 受信号量控制

# 研究过程中动态添加的新话题也会被并行处理
```

- 使用 `AsyncCitationManagerWrapper` 和 `AsyncManagerAgentWrapper` 保证线程安全
- 活跃任务实时追踪

### 6.3 Phase 3: Reporting（报告阶段）

```
所有 TopicBlock COMPLETED
    │
    ▼
ReportingAgent.deduplicate()      ← 去除重复话题和内容
    │
    ▼
ReportingAgent.generate_outline() ← 生成报告结构大纲
    │
    ▼
ReportingAgent.write_report()     ← 逐章节 LLM 写作
    │  ├─ 引用 ToolTrace 中的知识
    │  └─ CitationManager 解析引用 → [1], [2]
    ▼
构建参考文献列表
    │
    ▼ 输出文件:
    ├─ reports/{research_id}.md           # 最终报告
    ├─ reports/{research_id}_metadata.json # 元数据 + 来源
    ├─ cache/{research_id}/queue.json     # 队列状态
    ├─ cache/{research_id}/citations.json # 引用数据
    └─ cache/{research_id}/token_cost_summary.json # Token 统计
```

---

## 7. 工具集成

### 7.1 工具调用架构

通过 `_call_tool(tool_type, query)` 统一调度:

| 工具 | 类型 | 配置开关 | 返回内容 |
|------|------|---------|---------|
| RAG Hybrid | 知识库 | `enable_rag_hybrid` | JSON {chunks, answer} |
| RAG Naive | 知识库 | `enable_rag_naive` | JSON {chunks, answer} |
| Query Item | 知识库精确 | `enable_query_item` | JSON {matched entries} |
| Web Search | 互联网 | `enable_web_search` | JSON {web_sources: [{title, url, snippet}]} |
| Paper Search | 学术论文 | `enable_paper_search` | JSON {papers: []} (可配年限) |
| Run Code | Python 执行 | `enable_run_code` | JSON {output, error, result} |

### 7.2 容错机制

```python
# 重试 + 超时
_call_tool_with_retry(max_retries=2, timeout=60s)

# 降级策略: RAG hybrid 失败 → 回退到 RAG naive
# 超时处理: 单工具可配超时时间
# 错误恢复: 失败返回 JSON error 对象，不中断流程
```

**配置项:**

```yaml
tool_timeout: 60          # 单工具超时（秒）
tool_max_retries: 2       # 重试次数
paper_search_years_limit: 3  # 论文年限限制
```

---

## 8. API 接口

### 8.1 WebSocket 端点: `/api/v1/research/run`

**完整异步 WebSocket 处理流程:**

1. **Accept** → 接收客户端配置 JSON
2. **初始化 Pipeline**: topic, kb_name, plan_mode, enabled_tools
3. **后台任务**:
   - **Log Pusher**: 通过 `ResearchStdoutInterceptor` 实时推送日志
   - **Progress Pusher**: 通过回调队列推送结构化进度事件
   - **Heartbeat**: 每 30 秒 ping 保持连接

**客户端发送配置:**

```json
{
  "topic": "研究话题",
  "kb_name": "DE-all",
  "plan_mode": "medium",
  "enabled_tools": ["RAG", "Web", "Paper"],
  "skip_rephrase": false
}
```

**服务端推送事件类型:**

| type | 内容 |
|------|------|
| `task_id` | 任务追踪 ID |
| `status` | "started", "already_running" |
| `log` | 实时控制台输出 |
| `planning_started` | 规划阶段开始 |
| `block_started` | 某话题块开始研究 |
| `block_completed` | 某话题块研究完成 |
| `result` | 最终报告数据 |
| `error` | 错误信息 |

### 8.2 REST 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/status/{research_id}` | 获取研究进度 |
| GET | `/latest?topic=...` | 获取最新研究结果 |
| POST | `/optimize_topic` | 话题优化（RephraseAgent） |
| POST | `/compose_from_sources` | 从来源生成报告 |
| POST | `/ppt_style_from_sources` | 生成 PPT 风格 prompt |
| POST | `/export_pdf` | 导出 PDF |
| POST | `/export_mindmap` | 生成 Mermaid 思维导图 |
| GET | `/pptx/{file_id}` | 下载 PPTX 文件 |

---

## 9. 前端实现

### 9.1 页面组件 (`web/app/research/page.tsx`)

**状态管理:**
- `useResearchReducer()` — 中心化状态管理（三阶段进度）
- `localStorage` — 跨会话持久化配置和来源
- `wsRef` — WebSocket 连接引用

**用户配置:**

```typescript
interface ResearchConfig {
  selectedKb: string           // 选定知识库
  planMode: "quick" | "medium" | "deep" | "auto"
  enabledTools: string[]       // ["RAG", "Web", "Paper"]
  enableOptimization: boolean  // 是否启用话题优化
}
```

### 9.2 WebSocket 客户端流程

```javascript
// 1. 建立连接
const ws = new WebSocket("/api/v1/research/run");

// 2. 发送配置
ws.send(JSON.stringify({ topic, kb_name, plan_mode, enabled_tools, skip_rephrase }));

// 3. 接收事件
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  switch(data.type) {
    case "task_id":    // 接收任务 ID
    case "status":     // "started", "already_running"
    case "log":        // 实时日志
    case "result":     // 最终报告
    case "error":      // 错误
    // 进度事件: planning_started, block_started, block_completed ...
  }
};
```

### 9.3 ResearchDashboard 组件

三阶段看板:

| 阶段 | 展示内容 |
|------|---------|
| **Planning** | 原始话题 → 优化话题、分解进度 |
| **Researching** | TaskGrid（所有块状态）、ActiveTaskDetail（选中块详情）、实时迭代信息 |
| **Reporting** | 大纲预览、报告生成进度 |

子组件:
- **TaskGrid**: 展示所有 TopicBlock 状态（PENDING/RESEARCHING/COMPLETED/FAILED）
- **ActiveTaskDetail**: 迭代进度、当前工具/查询、ToolTrace 链、思维链可视化

---

## 10. 配置系统

### 10.1 主配置 (`config/main.yaml` research section)

```yaml
research:
  planning:
    rephrase:
      enabled: true
      max_iterations: 3
    decompose:
      enabled: true
      mode: auto                    # manual | auto
      initial_subtopics: 5
      auto_max_subtopics: 8

  researching:
    max_iterations: 5
    iteration_mode: fixed           # fixed | flexible
    execution_mode: series          # series | parallel
    max_parallel_topics: 1
    enable_rag_naive: true
    enable_rag_hybrid: true
    enable_paper_search: true
    enable_web_search: true
    enable_run_code: true
    tool_timeout: 60
    tool_max_retries: 2
    paper_search_years_limit: 3

  reporting:
    min_section_length: 800
    enable_citation_list: true
    enable_inline_citations: false

  rag:
    kb_name: DE-all
    default_mode: hybrid
    fallback_mode: naive

  queue:
    max_length: 5
```

### 10.2 预设模式

| 模式 | 子话题数 | 最大迭代 | 特点 |
|------|---------|---------|------|
| `quick` | 1 (manual) | 1 | 快速单话题浅层研究 |
| `medium` | 5 | 4 | 中等深度多话题 |
| `deep` | 8 | 7 | 深度全面研究 |
| `auto` | 自动决定 (≤8) | flexible | 根据话题复杂度自适应 |

### 10.3 Prompt 模板

位于 `src/agents/research/prompts/{lang}/`:
- `rephrase_agent.yaml` — 话题优化
- `decompose_agent.yaml` — 子话题生成
- `research_agent.yaml` — 查询生成、充分性检查
- `note_agent.yaml` — 摘要生成
- `reporting_agent.yaml` — 章节写作、去重

---

## 11. 完整数据流

```
用户输入 "量子计算在密码学中的应用"
    │
    ▼ WebSocket /api/v1/research/run
[Router] 初始化 ResearchPipeline(topic, kb="DE-all", mode="medium")
    │
    ▼ ═══ Phase 1: Planning ═══
    │
    ├─ RephraseAgent.process("量子计算在密码学中的应用")
    │  └─ LLM → "量子计算对现代密码学体系的影响与应用前景分析"
    │
    ├─ DecomposeAgent.process(optimized_topic, 5, "manual")
    │  ├─ RAG 搜索相关知识（可选）
    │  └─ LLM → 5 个子话题:
    │     1. 量子计算基础原理
    │     2. Shor 算法与 RSA 破解
    │     3. 后量子密码学方案
    │     4. 量子密钥分发（QKD）
    │     5. 产业应用现状与展望
    │
    └─ DynamicTopicQueue: [block_1...block_5 全部 PENDING]
    │
    ▼ ═══ Phase 2: Researching ═══
    │
    ├─ block_1: "量子计算基础原理" → RESEARCHING
    │  ├─ Iter 1: RAG hybrid → NoteAgent → CIT-1-01
    │  ├─ Iter 2: Web search → NoteAgent → CIT-1-02
    │  ├─ Iter 3: sufficiency check → 已充分
    │  └─ → COMPLETED
    │
    ├─ block_2: "Shor 算法与 RSA 破解" → RESEARCHING
    │  ├─ Iter 1: RAG hybrid → NoteAgent → CIT-2-01
    │  ├─ Iter 2: Paper search → NoteAgent → CIT-2-02
    │  ├─ Iter 3: Web search → NoteAgent → CIT-2-03
    │  └─ → COMPLETED
    │
    ├─ ... (block_3, block_4, block_5 类似)
    │
    ▼ ═══ Phase 3: Reporting ═══
    │
    ├─ 去重: 移除重复内容
    ├─ 生成大纲: 5 个章节 + 引言 + 结论
    ├─ 逐章写作: LLM 生成内容，嵌入 [1][2] 引用
    ├─ 构建参考文献列表
    │
    ▼ 输出:
    ├─ reports/{id}.md              → 完整 Markdown 报告
    ├─ reports/{id}_metadata.json   → 元数据 + 来源
    ├─ cache/{id}/queue.json        → 队列终态
    ├─ cache/{id}/citations.json    → 引用数据
    └─ cache/{id}/token_cost_summary.json → Token 消耗统计
    │
    ▼ WebSocket 推送 type="result"
[Frontend] 渲染 Markdown 报告 + 来源列表
         提供导出: PDF / PPTX / 思维导图
```

---

## 12. 与 PPT 生成的集成

### Research → PPT 流程

1. 前端从研究元数据中提取来源
2. 调用 `POST /api/v1/research/compose_from_sources`
3. `SourceReportGenerator` 生成 **normalized deck source**
4. 使用 Prompt: `normalization/research_to_deck_source.md`
5. 输出传入 PPT 生成器（orchestrator）

**相关文件:**
- `src/services/ppt/prompts.py` — Prompt 管理
- `src/services/ppt/orchestrator.py` — PPT 编排器
- `/api/v1/research/ppt_style_from_sources` — 生成 PPT 风格 Prompt

---

## 13. 错误处理模式

### WebSocket 安全发送

```python
async def safe_send(data: dict) -> bool:
    if not ws_connected:
        return False
    try:
        await websocket.send_json(data)
        return True
    except Exception:
        ws_connected = False
        return False
```

### 工具容错

```python
# 重试 + 超时
try:
    result = await _call_tool_with_timeout(tool_func, timeout=60)
except asyncio.TimeoutError:
    result = await _call_tool_with_retry(fallback_tool, ...)
except Exception:
    return json.dumps({"status": "failed", "error": str(e)})
```

### ResearchAgent 安全机制

- 每次工具调用前检查知识充分性
- 强制迭代上限（`max_iterations`）
- 工具可用性标志检查
- 工具不可用时优雅降级

---

## 14. 性能特性

### Token 追踪

- 通过 `token_tracker.py` 集成
- 按 Agent 追踪消耗
- 保存至 `token_cost_summary.json`

### 并行执行

- Series: 顺序处理（简单、较慢）
- Parallel: 并发执行，受 `max_parallel_topics` 信号量控制
- 线程安全的引用和队列管理

### 截断策略

- 工具输出上限 50KB
- 智能 JSON 截断保留结构完整性
- 记录原始大小和截断标志
- 必要时回退到内容级截断
