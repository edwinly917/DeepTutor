# 三个 Issue 执行计划

## Issue 1: 删除 notebook 时清理研究历史

### 目标
删除 notebook 时，同步删除 `user_history.json` 中关联的研究历史条目。

### 步骤

#### 1.1 `src/api/utils/history.py` — `add_entry` 增加 `notebook_id` 参数
- 函数签名增加 `notebook_id: str | None = None`
- 当 `notebook_id` 非空时，写入 entry dict 中：`entry["notebook_id"] = notebook_id`

#### 1.2 `src/api/routers/research.py:1032` — 调用 `add_entry` 时传入 `notebook_id`
- 当前代码（第 1032 行）：
  ```python
  history_manager.add_entry(
      activity_type=ActivityType.RESEARCH,
      title=topic,
      content={...},
      summary=f"Research ID: {result['research_id']}",
  )
  ```
- 增加 `notebook_id=notebook_id`（该变量在第 711 行已从 WebSocket 消息中获取）

#### 1.3 `src/api/utils/history.py` — 新增 `delete_entries_by_notebook` 方法
```python
def delete_entries_by_notebook(self, notebook_id: str) -> int:
    history = self._load_history()
    original_len = len(history)
    history = [e for e in history if e.get("notebook_id") != notebook_id]
    self._save_history(history)
    return original_len - len(history)
```

#### 1.4 `src/api/notebook_manager.py` — `delete_notebook` 中调用清理
- 在 `delete_notebook` 方法中（更新 index 之前），调用：
  ```python
  from src.api.utils.history import history_manager
  history_manager.delete_entries_by_notebook(notebook_id)
  ```

---

## Issue 2: 快速研究结果不应出现在来源列表

### 目标
快速研究返回的来源不应加入 `sources` 状态，即不出现在左侧来源列表中。

### 步骤

#### 2.1 `web/app/notebooks/[id]/page.tsx` — 移除快速研究中将 source 加入 sources 的逻辑
快速研究的 `ws.onmessage` 中 `data.type === "sources"` 分支（约第 2513-2559 行）：
- 删除或注释掉 `setSources(...)` 调用（约第 2555 行），使快速研究的 web/rag source 不写入 `sources` 状态
- 保留 `setCitationRegistryVersion` 调用（如果 citation 渲染需要）
- 保留 source_catalog 的处理逻辑（如果 chat message 中的引用标注需要）

注意：不要修改深度研究的 source 处理逻辑（约第 854、885、901 行），也不要修改 `applyResearchResult` 中的 report source（第 773 行）。

---

## Issue 3: 深度研究进度百分比覆盖全流程（方案 B）

### 目标
进度百分比应覆盖 Planning → Researching → Reporting 全部阶段，采用统一步骤计数。

### 阶段-步骤映射

| 阶段 | 事件 | 步骤数 |
|------|------|--------|
| Planning | `planning_started` → `rephrase_completed/skipped` → `decompose_completed` → `planning_completed` | 3 步 |
| Researching | N 个 `block_completed` | N 步（N = 子主题数量，planning 完成后已知） |
| Reporting | `reporting_started` → `deduplicate_completed` → `outline_completed` → M 个 `writing_section` → `writing_completed` | 动态，初始 3 步，`outline_completed` 后更新为 2 + M + 1 步 |

总步骤 = 3 (planning) + N (researching) + R (reporting)

其中 R 初始估算为 3，在 `outline_completed` 事件到达时更新为 2 + M + 1（M = section 数量）。

### 步骤

#### 3.1 新增前端状态变量
在 `page.tsx` 中新增状态（或复用现有 `researchProgress`）：
```typescript
// 全局步骤追踪
const [globalProgress, setGlobalProgress] = useState({ completed: 0, total: 0 });
```

#### 3.2 修改进度事件处理逻辑（`page.tsx` 约第 3039-3104 行）

各事件对应的处理：

| 事件 | 操作 |
|------|------|
| `planning_started` | `total = 3 + 0 + 3`（N 未知，先设 planning 部分），`completed = 0` |
| `rephrase_completed` / `rephrase_skipped` | `completed += 1` |
| `decompose_completed` | `completed += 1`；此时 N 已知（`data.generated_subtopics`），更新 `total = 3 + N + 3` |
| `planning_completed` | `completed += 1`（此时 completed = 3） |
| `researching_started` | 无需额外操作（total 已在 decompose_completed 时设好） |
| `block_completed` | `completed += 1` |
| `reporting_started` | 无需额外操作 |
| `deduplicate_completed` | `completed += 1` |
| `outline_completed` | `completed += 1`；M 已知（`data.sections` 的长度），更新 `total = 3 + N + 2 + M + 1` |
| `writing_section` | `completed += 1` |
| `writing_completed` | `completed += 1`（此时 completed = total，即 100%） |

#### 3.3 修改进度条渲染（`page.tsx` 约第 4265-4298 行）

- 渲染条件从 `researchPhase === "researching" && researchProgress.total > 0` 改为 `globalProgress.total > 0`
- 百分比计算改为 `Math.round((globalProgress.completed / globalProgress.total) * 100)`
- 进度条标签从固定的"子主题进度"改为根据阶段动态显示：
  - planning: "规划中"
  - researching: "研究中"
  - reporting: "生成报告中"
- ETA 计算基于 `globalProgress.completed / globalProgress.total`

#### 3.4 清理旧的 `researchProgress` 状态
- 评估是否可以用 `globalProgress` 完全替代 `researchProgress`，如果可以则移除 `researchProgress`
- 如果其他地方还依赖 `researchProgress`（如 block_started 中的显示），则保留但进度条只用 `globalProgress`

---

## 执行顺序

1. Issue 1（步骤 1.1 → 1.2 → 1.3 → 1.4）
2. Issue 2（步骤 2.1）
3. Issue 3（步骤 3.1 → 3.2 → 3.3 → 3.4）

每完成一个关键步骤后，回看本文档确认未偏离计划。
