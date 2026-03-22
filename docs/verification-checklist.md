# PPT Refactor Implementation Verification Checklist

## 目标
验证 `/Users/bytedance/DeepTutor-1-ppt-refactor-execution` (分支 `codex/ppt-refactor-execution-plan`) 的实现是否完整符合执行计划 `ppt-refactor-execution-plan.md`

## 验证方法
1. 对照执行计划的每个 Phase，逐项检查代码实现
2. 验证测试覆盖率是否充分
3. 检查是否有遗漏或偏离计划的实现
4. 识别潜在的代码质量问题

---

## Phase 1: Spec Alignment

### 1.1 主规格文档更新
- [ ] `docs/ppt-refactor-plan.md` 是否包含 `source_refs` schema 表格
- [ ] 是否包含完整的页面状态转换表
- [ ] 是否包含前端持久化 vs runtime-only 字段表格
- [ ] 是否明确了 `from_sources` 快照语义
- [ ] 是否明确了手动 patch API 语义
- [ ] 是否定义了轻量级并发保护规则
- [ ] 是否包含 SSRF 防护要求

---

## Phase 2: Storage and Model Changes

### 2.1 数据库 Schema 变更
- [ ] `ppt_projects.source_refs` (JSON) - 已添加
- [ ] `ppt_projects.normalized_content` (TEXT) - 已添加
- [ ] `ppt_projects.content_cached_at` (DateTime) - 已添加
- [ ] `ppt_projects.record_ids` (JSON) - 已添加（for from_notebook）
- [ ] `ppt_pages.is_dirty` (Boolean) - 已添加
- [ ] `ppt_slide_chat_messages` 表 - 已创建
  - [ ] id (主键)
  - [ ] page_id (外键)
  - [ ] role (user/assistant)
  - [ ] content (TEXT)
  - [ ] created_at (DateTime)

### 2.2 ppt_store.py CRUD 扩展
- [ ] `source_refs` 的读写支持
- [ ] `record_ids` 的读写支持
- [ ] `is_dirty` 的读写支持
- [ ] chat message 的 CRUD 方法
- [ ] task progress 支持 warnings 字段

### 2.3 Migration Strategy
- [ ] 是否有明确的迁移脚本或说明
- [ ] 是否遵循了正确的 rollout 顺序

---

## Phase 3: Orchestrator and Backend API

### 3.1 API 端点扩展
- [ ] `POST /api/v1/ppt/projects` - `creation_type` 扩展
  - [ ] 支持 `from_research`
  - [ ] 支持 `from_notebook`
  - [ ] 支持 `from_sources`
  - [ ] 保留旧的 `idea/outline/descriptions` 兼容
- [ ] `POST /projects/{id}/generate/full` - 新增
- [ ] `POST /projects/{id}/pages/{page_id}/chat` - 新增
- [ ] `GET /projects/{id}/pages/{page_id}/chat-history` - 新增

### 3.2 Content Extractors
- [ ] `ResearchExtractor` - 实现
  - [ ] 从 notebook_manager 获取 session
  - [ ] 提取 research_report
  - [ ] 输出 NormalizedContent
- [ ] `NotebookExtractor` - 实现
  - [ ] 从 notebook_manager 获取 records
  - [ ] 按 record_ids 过滤
  - [ ] 输出 NormalizedContent
- [ ] `SourcesExtractor` - 实现
  - [ ] 调用 SourceReportGenerator.generate()
  - [ ] 支持 report/web/kb
  - [ ] 对 paper/file 返回 warnings
  - [ ] 输出 NormalizedContent

### 3.3 导出保护
- [ ] 检查 dirty 页面 → 拒绝导出
- [ ] 检查缺失图片 → 拒绝导出
- [ ] 检查活跃的页面重生成任务 → 拒绝导出

### 3.4 并发保护
- [ ] 项目级全量生成冲突检查
- [ ] 同页重生成冲突检查
- [ ] 不引入 DB 锁字段

### 3.5 SSRF 防护
- [ ] 只允许 http/https
- [ ] 使用 socket.getaddrinfo() 解析所有地址
- [ ] 检查所有解析的 IP（包括 IPv6）
- [ ] 拒绝 loopback/private/link-local/multicast/reserved
- [ ] allow_redirects=False
- [ ] redirect 目标重新验证

---

## Phase 4: Editing Pipeline

### 4.1 SlideEditor
- [ ] 实现 chat 编辑分类
  - [ ] outline_edit
  - [ ] description_edit
  - [ ] image_edit
- [ ] 自动触发重生成
  - [ ] outline_edit → description + image_prompt + image
  - [ ] description_edit → description + image_prompt + image
  - [ ] image_edit → image only

### 4.2 手动 Patch API
- [ ] `PUT /pages/{page_id}` 只更新字段
- [ ] 设置 `is_dirty=true`
- [ ] 设置 `status="DRAFT"`
- [ ] 不自动触发重生成

### 4.3 单页重生成任务
- [ ] 返回独立的 PptTask
- [ ] task_type 区分全局和单页任务
- [ ] 支持 DESCRIPTION_QUEUED / IMAGE_QUEUED 状态

---

## Phase 5: Frontend Integration

### 5.1 类型定义更新
- [ ] `web/types/ppt.ts` - PptCreationMode 扩展
- [ ] source_refs 类型定义
- [ ] is_dirty 字段
- [ ] chat message 类型

### 5.2 API 客户端更新
- [ ] `web/lib/pptApi.ts` - 新端点支持
  - [ ] createPptProject 支持新 creation_type
  - [ ] generatePptFull
  - [ ] chatWithSlide
  - [ ] getChatHistory

### 5.3 Notebook 页面集成
- [ ] `web/app/notebooks/[id]/page.tsx`
  - [ ] from_notebook 入口
  - [ ] record_ids 勾选
  - [ ] 创建时冻结 record_ids
  - [ ] 不误读左侧实时来源

### 5.4 预览组件更新
- [ ] `web/components/ppt/PptPreviewModal.tsx`
  - [ ] dirty 页面 overlay
  - [ ] warnings 显示
  - [ ] selectedSlideId 持久化和恢复
  - [ ] 恢复时验证 slide 存在性

### 5.5 任务轮询
- [ ] `waitForPageRegenTask()` 不修改全局 `pptActiveTaskId`
- [ ] `generate_full` 使用现有全局恢复路径

---

## Phase 6: Validation

### 6.1 功能测试
- [ ] from_sources with report content - 端到端
- [ ] 页面 chat 编辑影响最终导出
- [ ] 手动 PUT /pages 产生 dirty 页面并阻止导出
- [ ] 刷新恢复 - generate_full
- [ ] 刷新恢复 - 预览重新打开
- [ ] 刷新恢复 - selectedSlideId 恢复
- [ ] unsupported source warnings 用户可见
- [ ] from_sources 不随侧边栏变化
- [ ] SSRF 验证拒绝内网 URL

### 6.2 自动化测试
- [ ] 后端测试覆盖率
  - [ ] from_notebook 快照
  - [ ] from_sources report 冻结
  - [ ] dirty 页重生成
  - [ ] 导出拦截
  - [ ] SSRF 防护
- [ ] 前端类型检查通过
- [ ] 前端构建通过

---

## 代码质量检查

### 7.1 代码一致性
- [ ] 命名规范一致
- [ ] 错误处理完整
- [ ] 日志记录充分
- [ ] 注释清晰

### 7.2 潜在问题
- [ ] 是否有未处理的 TODO
- [ ] 是否有硬编码的配置
- [ ] 是否有性能瓶颈
- [ ] 是否有安全漏洞

### 7.3 文档完整性
- [ ] 代码变更与文档一致
- [ ] API 文档更新
- [ ] 测试文档完整

---

## 验证结果汇总

### 完成度评分
- Phase 1: __/7 项
- Phase 2: __/10 项
- Phase 3: __/15 项
- Phase 4: __/8 项
- Phase 5: __/10 项
- Phase 6: __/9 项
- 代码质量: __/10 项

### 总体评分: __/69 项 (__%)

### 发现的问题
1. [待填写]
2. [待填写]

### 建议
1. [待填写]
2. [待填写]
