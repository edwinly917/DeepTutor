# 更新日志 / Changelog

## v1.1.0 (2026-01-17)

### 🎯 主要更新 / Major Updates

#### 1. PPT 导出功能重构与独立配置

新增了专用的 PPT 模型配置系统，支持使用独立的 LLM 模型来生成演示文稿的样式和结构。

**后端更改：**
- 新增 `src/services/export/ppt_generator.py` - 独立的 PPT 生成服务模块
- 更新 `src/services/config/loader.py` - 添加 `PPTConfig` 数据类和 `get_ppt_config()` 函数
- 更新 `src/api/routers/research.py` - 支持 `style_api_key` 和 `style_base_url` 参数
- 更新 `config/main.yaml` - 新增 `export.ppt` 配置块

**新增配置项 (`config/main.yaml`)：**
```yaml
export:
  ppt:
    model: ""          # PPT 专用模型名称
    api_key: ""        # PPT 专用 API Key
    base_url: ""       # PPT 专用 API Base URL
    binding: "openai"  # API 绑定类型
    temperature: 0.7   # 生成温度
    max_tokens: 4096   # 最大 token
```

**配置优先级：**
1. API 请求参数（最高优先级）
2. `main.yaml` 中的 `export.ppt` 配置
3. 环境变量
4. 默认 LLM 配置（最低优先级）

**前端更改：**
- 在研究页面添加 PPT 模型配置 UI，支持设置：
  - 模型名称
  - API Key
  - Base URL

---

#### 2. 中文文件名支持修复

修复了 PPT 导出时无法处理中文文件名的问题。

**更改：**
- 重写 `_sanitize_filename()` 方法，允许 Unicode 字符（中文等）
- 仅过滤文件系统不支持的特殊字符（`/ \ : * ? " < > |`）

---

#### 3. 国际化 (i18n) 扩展

大幅扩展了中英文翻译支持，涵盖更多 UI 组件。

**新增翻译内容：**
- 设置页面完整翻译
- 聊天会话详情页面
- 活动详情组件
- 问题生成模块
- 研究模块
- 笔记本模块
- 侧边栏和系统状态组件
- 错误消息和表单验证

---

#### 4. UI/UX 优化

**组件更新：**
- `web/app/research/page.tsx` - 研究页面重构
- `web/components/research/ResearchDashboard.tsx` - 研究仪表板增强
- `web/components/Sidebar.tsx` - 侧边栏优化
- `web/components/CoWriterEditor.tsx` - 协作编辑器改进
- `web/app/preview/ppt/page.tsx` - 新增 PPT 预览页面

**品牌更新：**
- 项目名称从 "DeepTutor" 更新为 "Hi-NoteBook"
- 更新 Logo 文件 (`web/public/logo.png`)

---

#### 5. 开发与测试

**新增验证脚本：**
- `scripts/verify_ppt.py` - PPT 功能端到端测试
- `scripts/verify_ppt_config.py` - PPT 配置验证
- `scripts/verify_ppt_isolated.py` - 隔离环境 PPT 测试

**依赖更新：**
- `requirements.txt` - 新增 `python-pptx` 依赖
- `docker-compose.dev.yml` - 开发环境配置更新

---

### 📁 变更文件清单 / Changed Files

| 类别 | 文件路径 | 描述 |
|------|----------|------|
| 配置 | `config/main.yaml` | 新增 PPT 导出配置块 |
| 后端 | `src/services/export/ppt_generator.py` | 新增 PPT 生成服务 |
| 后端 | `src/services/config/loader.py` | 添加 PPT 配置加载器 |
| 后端 | `src/api/routers/research.py` | 扩展 PPT 导出 API |
| 前端 | `web/app/research/page.tsx` | PPT 配置 UI |
| 前端 | `web/lib/i18n.ts` | 国际化扩展 |
| 前端 | `web/app/preview/ppt/page.tsx` | 新增 PPT 预览页 |
| 前端 | `web/components/*` | 多个组件优化 |
| 脚本 | `scripts/verify_ppt*.py` | 验证脚本 |
| 依赖 | `requirements.txt` | 添加 python-pptx |

---

### 🔧 升级指南 / Upgrade Guide

1. **安装新依赖：**
   ```bash
   pip install python-pptx
   ```

2. **配置 PPT 模型（可选）：**
   编辑 `config/main.yaml`，在 `export.ppt` 下配置专用模型。

3. **前端重新构建：**
   ```bash
   cd web && npm install && npm run build
   ```

---

### 🐛 Bug 修复 / Bug Fixes

- 修复中文文件名导出失败问题
- 修复 PPT 样式生成 JSON 解析失败时的错误处理
- 改进 LLM 响应的 JSON 提取逻辑

---

*Last updated: 2026-01-17*
