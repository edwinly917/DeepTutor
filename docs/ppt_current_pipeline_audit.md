# PPT Current Pipeline Audit

Date: 2026-03-23

## 1. 直接结论

### 1.1 结论 1：PPT 预览和实际导出，当前确实不是同一套渲染物

这是已经被代码和产物同时证明的事实，不是主观观感问题。

当前至少存在 3 条不同语义的“预览/导出”路径：

1. `预览风格` 按钮
   - 只会调用 `POST /api/v1/ppt/style-preview`
   - 后端只根据 style 文本拼一个 `preview_svg`
   - 它不创建项目，不生成大纲，不生成页面图片，也不代表真实导出结果

2. `生成 PPT` 后弹出的 `PPT 预览` 弹窗
   - 走的是新项目链路：`createPptProject -> generatePptFull -> fetchPptProject`
   - 但前端展示组件 `web/components/ppt/SlidePreview.tsx` 只是一个“卡片式版式预览器”
   - 它把 `title / points / layout / generatedImageUrl` 拼成一个示意卡片
   - 这不是最终导出的真实缩略图

3. `导出 PPT`
   - 走的是 `GET /api/v1/ppt/projects/{id}/export/pptx`
   - 后端把每一页已生成的整页图片直接塞进 `python-pptx`
   - 导出的 `.pptx` 每一页只有 1 张图片，没有任何独立文本框、图表对象或结构化布局对象

也就是说：

- 预览弹窗展示的是“结构化卡片”
- 导出 PPT 展示的是“整页生图”
- `预览风格` 展示的只是“伪 SVG 风格示意图”

这三者天然不会一致。

### 1.2 结论 2：当前导出 PPT 是“图片化 PPT”，不是可编辑/结构化 PPT

这也是代码和实际导出文件都能直接证明的事实。

后端导出服务 `src/services/export/ppt_image_export_service.py` 的行为非常直接：

- 新建一个空白 PPT
- 每页插入一张整页图片
- 保存为 `.pptx`

这意味着：

- 导出的标题、正文、图表、图标，并不是 PowerPoint 对象
- 它们如果存在，也只是图片像素的一部分
- 导出结果的质量完全取决于“整页生图”的质量

我对你这次实际导出的文件做了核验：

- 导出文件：`data/user/ppt/projects/4b31c342-c9b6-49a6-ae5b-3397e90e406d/exports/中国新能源汽车出海进入「体系化远征」新阶段_20260323_104212.pptx`
- 项目页图：`data/user/ppt/projects/4b31c342-c9b6-49a6-ae5b-3397e90e406d/pages/*/v1.png`
- 脚本读取该 `.pptx` 后，15 页全部只有 1 个 `PICTURE` shape，没有文本 shape

这正是你看到“导出的 PPT 像整页图片”的根本原因。

### 1.3 结论 3：预览里图片大量不显示，有两个层面的原因

#### 原因 A：你截图那一刻本来就还没生成完

你第一张图顶部写的是：

- `图片生成 0/15`

这说明那一刻页面图片还没开始完成，所以卡片里看不到图是合理的。

#### 原因 B：即使图片已经生成，当前前端还有一个真实的 URL 拼接问题

项目生成完成后，后端给前端的 `generatedImageUrl` 是这种相对路径：

```text
/api/outputs/ppt/projects/<project_id>/pages/<page_id>/v1.jpg
```

但是 `SlidePreview.tsx` 直接这样渲染：

```tsx
<img src={slide.generatedImageUrl} ... />
```

没有走 `apiUrl(...)`。

当前你的前端页面在 `localhost:3783`，后端 API base 在 `web/.env.local` 里是：

```text
NEXT_PUBLIC_API_BASE=http://localhost:8001
```

所以这张图在浏览器里会去请求：

```text
http://localhost:3783/api/outputs/...
```

而不是：

```text
http://localhost:8001/api/outputs/...
```

我直接验证了前端端口上的这个 URL，返回的是 `404 Not Found`。

所以“项目里明明已经有图，但预览里仍然不显示”这件事，在当前代码下是完全可能发生的，而且原因非常具体。

## 2. 这次测试项目的真实实例

本次你测试出来并已经导出 `.pptx` 的项目，实际状态如下：

- `project_id`: `4b31c342-c9b6-49a6-ae5b-3397e90e406d`
- `creation_type`: `from_research`
- `status`: `COMPLETED`
- `page_count`: `15`
- `style_preset_id`: `minimal-business`
- `style_custom_text`: `None`
- `template_image_path`: `None`
- `reference_style_prompt`: `None`
- `reference_layout_prompt`: `None`
- `reference_content_prompt`: `None`
- `normalized_content`: 已存在

实际模型命中情况：

- 全局文本 LLM：`doubao-seed-2-0-pro-260215`
- 全局文本 binding：`openai`
- 大纲模型：`doubao-seed-2-0-pro-260215`
- 图片模型：`doubao-seedream-5-0-260128`
- 图片 binding：`doubao`
- 模板分析视觉模型：`doubao-seed-2-0-pro-260215`
- 模板分析视觉 binding：`doubao`

也就是说，这次项目根本没有使用参考图/模板分析分支，只有：

- 研究报告冻结
- 研究报告归一化
- 大纲生成
- 页面描述 + `image_prompt` 生成
- 整页图片生成
- 图片化 PPT 导出

## 3. 当前真实链路

## 3.1 风格预览链路

入口：

- 前端：`web/app/notebooks/[id]/page.tsx`
- 方法：`handlePreviewPptStyle`
- API：`web/lib/pptApi.ts -> previewPptStyle`
- 后端：`src/api/routers/ppt.py -> /style-preview`
- 服务：`src/services/ppt/orchestrator.py -> preview_style`

行为：

- 只构造 `StyleContext`
- 用 `style_context.preview_prompt(language)` 生成一段风格文本
- 再用 `_build_style_preview_svg()` 画一个假的 SVG 预览卡

这一条链路不接入真实 PPT 项目，也不接入真实页面图片。

所以它只能回答“风格大概长什么味道”，不能回答“最终导出长什么样”。

## 3.2 真实 PPT 生成链路

入口：

- 前端：`web/app/notebooks/[id]/page.tsx`
- 方法：`handleExportPptx`

主流程：

1. 前端构造 `createPayload`
2. `POST /api/v1/ppt/projects`
3. `POST /api/v1/ppt/projects/{id}/generate/full`
4. 前端轮询 task + project
5. 前端把 `project.presentation_outline` 渲染进 `PptPreviewModal`
6. 用户点击导出时，调用 `GET /api/v1/ppt/projects/{id}/export/pptx`

后端 `generate_full` 的实际阶段是：

1. 冻结输入内容
2. 生成 `normalized_content`（DeckSourceBrief）
3. 生成 outline
4. 为每页生成 `description_content` 和 `image_prompt`
5. 为每页生成整页图片
6. 导出时把整页图片写入 PPT

## 3.3 真实导出链路

入口：

- 前端：`web/app/notebooks/[id]/page.tsx -> handleDownloadPptx`
- API：`web/lib/pptApi.ts -> exportPptProjectPptx`
- 后端：`src/api/routers/ppt.py -> /projects/{project_id}/export/pptx`
- 服务：`src/services/ppt/orchestrator.py -> export_pptx_with_title`
- 导出器：`src/services/export/ppt_image_export_service.py`

导出约束：

- 只要有 dirty 页就不允许导出
- 只要有页没有生成图片就不允许导出
- 导出时只收集 `generated_image_path / cached_image_path`
- 完全不读取 `description_text`
- 完全不把 `title / points / layout` 转成 PowerPoint 对象

## 4. 为什么当前质量会明显差于 banana-slides

这不是单一 prompt 的问题，而是“链路语义断裂”。

### 4.1 `layout` 在预览里是刚性的，在导出里只是 prompt 里的一个词

当前系统里 `layout` 有两种完全不同的意义：

1. 在 `SlidePreview.tsx` 里，`layout` 决定卡片怎么排文字和图片区
2. 在最终导出里，`layout` 只是图像模型 prompt 中的 `Target layout: OVERVIEW / TOP_IMAGE / ...`

导出时没有任何真正的版式引擎去执行这些布局。

也就是说：

- 预览是“代码强执行布局”
- 导出是“让生图模型自己猜布局”

这当然会发生明显偏差。

### 4.2 图片 prompt 本来就不是“整页最终成品 prompt”

`src/services/ppt/prompt_assets/image/generation.md` 的定位是：

- `Create one professional slide illustration`
- `Leave usable negative space for slide copy and layout overlays`

这说明它原本更像：

- 配图 / 背景图 / 支撑视觉

而不是：

- 最终整页成品幻灯片

但当前 export 却把这张“留白配图”直接当整页幻灯片导出。

这意味着：

- prompt 语义要求“给文字留空间”
- 真实导出却“根本没有后续文字叠加”

所以最后就会得到“有版式感但没真正内容”的图片化页面。

### 4.3 描述阶段生成了很多文字，但导出阶段根本不消费这些文字

`DescriptionGenerator.generate_page_description()` 输出：

- `text`
- `image_prompt`

但是 `_generate_page_image()` 真正用于生图的只有：

- `page.image_prompt`
- `slide_title`
- `slide_points`
- `layout`
- `style_context`
- `source_brief`

`description_content.text` 本身并不会被渲染进最终导出 PPT。

所以当前系统里：

- 描述文本存在
- 预览卡片里标题和 bullet 也存在
- 但导出时这些结构化文本全部被抛弃

### 4.4 当前图片 prompt 还明确要求“不要文字”

本次项目第一页实际保存的 `image_prompt` 就是这种方向：

```text
16:9 极简商务扁平矢量插画，深炭灰#1A1A2E纯色背景，仅使用白色线稿与冷蓝色#3B82F6点缀，无任何文字、logo、渐变或阴影...
```

而最终 export 又只导出图片。

结果就是：

- 文字被 prompt 禁止
- 文本框又没有后续叠加
- 导出当然只剩图

### 4.5 当前 Doubao 图片请求硬编码了水印

`src/services/ppt/image_generator.py` 的 Doubao 生图请求里写死了：

```python
"watermark": True
```

这正对应了你导出 PPT 里右下角的 `AI生成` 水印。

这不是偶发现象，是当前代码的默认行为。

## 5. Prompt 分阶段映射

下面按“当前项目真实会经过的阶段”来整理。

## 5.1 阶段 0：输入冻结

不是 prompt 阶段，但它决定后续 prompt 的输入源。

对应代码：

- `src/services/ppt/content_extractors.py`

3 种模式：

1. `from_research`
   - 冻结研究报告文本
   - 本次项目命中

2. `from_notebook`
   - 把勾选笔记记录拼成 markdown

3. `from_sources`
   - 先调用 `SourceReportGenerator.generate()` 做来源综述
   - 再进入 DeckSourceBrief 归一化

## 5.2 阶段 0.5：来源综述 prompt

只在 `from_sources` 时命中，本次项目未命中。

对应代码：

- `src/services/export/source_report.py -> generate`

system prompt：

```text
You are a research assistant. Use only the provided source excerpts to write a concise, structured Markdown report. Do not invent facts. Include a clear title (#), sections (##), and bullet points when helpful. If sources are insufficient, briefly note limitations.
```

user prompt 语义：

- 给出 topic
- 给出选中 sources 的摘录
- 要求输出 Markdown
- 引用来源时用 `[1] [2] ...`

输出：

- `markdown`

这个 `markdown` 之后还会再被归一化成 DeckSourceBrief。

## 5.3 阶段 1：参考图 / 模板分析 prompt

只有用户上传参考图或模板文件时命中，本次项目未命中。

对应代码：

- `src/services/ppt/template_analyzer.py`
- prompt 资源位于 `src/services/ppt/prompt_assets/analysis/*`

子 prompt 有 4 组：

1. `style_extraction.md`
   - 视觉系统抽取
   - 输出 `style_prompt / palette_hint / composition_hint`

2. `layout_caption.md`
   - 版式语法抽取
   - 输出 `layout_prompt / layout_regions`

3. `file_content_extraction.md`
   - 从模板文字抽可复用内容骨架
   - 输出 `content_prompt / key_sections`

4. `visual_synthesis.md`
   - 多页分析结果综合
   - 输出 `reference_style_prompt / reference_layout_prompt`

这些内容会进入 `StyleContext`，影响后续 normalization / outline / description / image prompt。

## 5.4 阶段 2：DeckSourceBrief 归一化 prompt

本次项目命中。

对应代码：

- `src/services/ppt/orchestrator.py -> _normalize_to_deck_source_brief`
- `src/services/ppt/prompts.py -> normalization_prompt`

本次项目命中的模板：

- `src/services/ppt/prompt_assets/normalization/research_to_deck_source.md`

system prompt：

```text
You are a presentation strategist. Transform raw DeepTutor source material into a DeckSourceBrief for downstream PPT planning. Return Markdown only.
```

user prompt 语义：

- 输入整份 research report
- 叠加 style context
- 要求产出 `## Core Theme / ## Key Findings / ## Supporting Evidence / ## Source Anchors ...`

本次项目的实际结果：

- `source_content` 大约 13.8k 字
- `normalized_content` 压缩到大约 1.9k 字

这一步的作用是把“长报告”压成“可做 PPT 规划的中间语义层”。

## 5.5 阶段 3：大纲生成 prompt

本次项目命中。

对应代码：

- `src/services/ppt/outline_generator.py`
- `src/services/ppt/prompts.py -> outline_system / outline_user`
- prompt 文件：
  - `src/services/ppt/prompt_assets/outline/system.md`
  - `src/services/ppt/prompt_assets/outline/from_research.md`
  - `src/services/ppt/prompt_assets/outline/from_notebook.md`
  - `src/services/ppt/prompt_assets/outline/from_sources.md`

本次项目命中的模板：

- `system.md`
- `from_research.md`

system prompt 作用：

- 要求输出固定 JSON schema
- 限定 `title / subtitle / themeColor / accentColor / slides[]`
- 每页必须有 `title / points / layout / imagePrompt`

user prompt 作用：

- 输入 `normalized_content`
- 输入 style summary
- 输入允许的 layout 枚举
- 要求把研究逻辑压成最多 15 页

这一阶段的关键输出是：

- `title`
- `slides[n].title`
- `slides[n].points`
- `slides[n].layout`
- `slides[n].imagePrompt`

注意：这里的 `layout` 只是结构规划，不是最终可执行版式。

## 5.6 阶段 4：单页描述 prompt

本次项目命中。

对应代码：

- `src/services/ppt/description_generator.py`
- `src/services/ppt/prompts.py -> page_description`
- prompt 文件：
  - `src/services/ppt/prompt_assets/description/page.md`

system prompt：

```text
You expand a confirmed PPT outline into a production-ready single-slide brief. Return ONLY valid JSON with keys text and image_prompt.
```

user prompt 主要输入：

- 整套 deck 的 outline summary
- 当前页 title
- 当前页 points
- supporting_context
- style_context
- source_brief
- detail level

输出：

- `text`
- `image_prompt`

其中：

- `text` 会进入 `description_content`
- `image_prompt` 会进入 page 记录，后续真正喂给生图模型

这一步非常关键，但也有一个当前设计问题：

- 它生成了较完整的页面文案
- 但导出 PPT 时并不会把这些文案真正渲染进去

## 5.7 阶段 5：图片最终 prompt 包装

本次项目命中。

对应代码：

- `src/services/ppt/image_generator.py -> build_image_prompt`
- `src/services/ppt/prompts.py -> image_generation`
- prompt 文件：
  - `src/services/ppt/prompt_assets/image/generation.md`

这个 prompt 的定位不是“最终整页幻灯片 JSON”，而是：

- “presentation visual designer”
- “slide illustration”
- “leave usable negative space for slide copy and layout overlays”

也就是说，它更像配图 prompt。

最终 user prompt 会拼入：

- deck title
- slide title
- slide points
- target layout
- style_context
- source_brief
- `Image brief`（也就是上一阶段生成好的 `image_prompt`）

本次项目第一页的真实最终生图 prompt 开头就是：

```text
You are an expert presentation visual designer.
Create one professional slide illustration that supports the slide message directly.

Deck title: 中国新能源汽车出海进入「体系化远征」新阶段
Slide title: 中国新能源汽车出海进入「体系化远征」新阶段
Slide points:
- 2022-2023年出口规模连续高增长...
Target layout: OVERVIEW
...
```

所以当前图片模型实际承担的是：

- 既要猜页面版式
- 又要画内容视觉
- 还要承担最终导出成品

这与 banana-slides 那种“结构化页面对象 + 定位明确的视觉素材”思路差别非常大。

## 5.8 阶段 6：图片模型调用

本次项目命中。

对应代码：

- `src/services/ppt/image_generator.py -> _generate_doubao_image`

当前真实模型：

- `doubao-seedream-5-0-260128`

当前硬编码行为：

- `response_format = b64_json`
- `watermark = True`

返回结果：

- `data:image/png;base64,...`

之后：

- 保存为 `v1.png`
- 再转成 `v1.jpg`
- 页面上优先展示 `cached_image_path` 或 `generated_image_path`

## 5.9 阶段 7：导出

本次项目命中。

对应代码：

- `src/services/ppt/orchestrator.py -> export_pptx_with_title`
- `src/services/export/ppt_image_export_service.py -> export_pptx`

这一阶段没有 prompt。

但它是造成最终效果割裂的核心阶段，因为它把所有结构化内容都丢掉了，只保留图片。

## 5.10 阶段 8：单页聊天编辑 prompt

这不是你这次导出前的主链路，但属于当前 PPT 系统的一部分。

对应代码：

- `src/services/ppt/slide_editor.py`
- `src/services/ppt/prompts.py`
- prompt 文件：
  - `src/services/ppt/prompt_assets/edit/classify.md`
  - `src/services/ppt/prompt_assets/edit/outline.md`
  - `src/services/ppt/prompt_assets/edit/description.md`
  - `src/services/ppt/prompt_assets/edit/image.md`

4 个子阶段：

1. `classify`
   - 分类用户是想改 outline / description / image

2. `rewrite_outline`
   - 改标题和 bullet points

3. `rewrite_description`
   - 改页面描述文本

4. `rewrite_image_prompt`
   - 改图片方向

随后会自动触发当前页重生成。

## 6. 当前哪些 prompt / 代码其实已经“半废弃”或未接上

这些内容不是完全没价值，但在当前 Notebook 主路径里并没有真正发挥预期作用。

### 6.1 `web/lib/pptGenerator.ts`

这个文件实现的是“结构化 PPT 生成器”：

- 会把 title / subtitle / points / generatedImageUrl 按 layout 摆进 PPT
- 这是更接近预览卡片逻辑的实现

但是当前 Notebook 页面没有调用它。

搜索结果显示：

- `exportToPptx(...)` 当前没有任何引用

所以它是一个未接入主链路的旧/备用实现。

### 6.2 `generatePptOutline / generatePptDescriptions / generatePptImages`

API 已经存在，但当前 Notebook 页面主链路只用：

- `createPptProject`
- `generatePptFull`
- `regeneratePptPageImage`
- `exportPptProjectPptx`

分阶段生成 API 目前没有接到主页面交互里。

### 6.3 `PptPromptManager.style_briefs`

这个 prompt 的设计是把 style context 进一步拆成：

- `outline_style_brief`
- `description_style_brief`
- `image_style_brief`

但是当前新 Notebook 主链路并没有使用它。

它现在只在旧的、已标记 deprecated 的 research PPT 路由中还有残留引用。

### 6.4 旧 research PPT 路由

`src/api/routers/research.py` 里还保留了这些旧接口：

- `/ppt_outline`
- `/ppt_image`
- `/ppt_config`

它们已经被标记 deprecated。

而且这套旧接口的设计文档仍然在强调：

- `Preview Modal -> pptxgenjs export`

但当前 Notebook 主链路已经不再按这套方案执行。

## 7. 与设计文档的偏差

`docs/banana_ppt_integration_zh.md` 写的目标是：

- Notebook Page -> PPT Mode -> 预览弹窗 -> `pptxgenjs` 导出

这套设计意味着：

- 预览和导出应当共享同一种结构化页面模型

但当前真实主链路已经变成：

- Notebook Page -> 创建项目 -> 全量任务生成 -> 后端 `python-pptx` 图片导出

也就是说：

- 文档里的“结构化导出路径”
- 和代码里的“图片化导出路径”

现在是并存而且互相冲突的。

## 8. 这 3 个问题的最终确认回答

### 8.1 关于问题 1

你的判断是对的。

当前“PPT 预览页面”和“实际导出的 PPT”不是同一套内容物：

- 预览：结构化卡片
- 导出：整页图片

不仅视觉不同，底层对象模型也不同。

### 8.2 关于问题 2

当前生成质量差，不只是模型差，而是整个链路在“最后一公里”上断掉了：

1. 上游 prompt 和预览都在假设“后面还会叠加结构化文字和布局”
2. 下游 export 却把“支撑视觉图”直接当最终幻灯片导出
3. 结果是：
   - 标题/bullet 不进导出
   - layout 不被真正执行
   - 生图模型要独自承担整页成品质量
   - 还自带水印

这才是与 banana-slides 方案差距特别大的关键原因。

### 8.3 关于问题 3

你的猜测部分对，但需要分开看：

1. `预览风格`
   - 的确是另一条完全脱离真实任务的伪预览路径

2. `生成 PPT` 后的预览弹窗
   - 不是完全脱离真实任务
   - 它确实绑定真实项目和真实 task
   - 也确实能在 task 轮询后拿到真实 `generatedImageUrl`

3. 但当前前端预览图不显示的问题又确实存在
   - 一部分是因为你截图时还在 `0/15`
   - 另一部分是因为 `<img src="/api/outputs/...">` 没有走 `apiUrl()`，在前后端分端口部署时会直接 404

所以最终结论是：

- “预览与真实导出不一致”这点成立
- “预览链路完全没挂真实任务”这点不完全成立
- “预览图片显示有真实 bug”这点成立

## 9. 如果下一步要修，优先顺序应该是什么

这部分不是本次改动，只是基于现状排查给出的建议顺序。

1. 先统一“导出对象模型”
   - 决定到底导出结构化 PPT，还是导出图片 PPT
   - 不要继续同时保留“结构化预览 + 图片化导出”

2. 如果目标是接近 banana-slides
   - 应恢复结构化渲染链路
   - 即：标题 / bullet / 图片区域 / layout 都由代码排版，而不是让生图模型猜整页

3. 单独修前端图片 URL
   - `generatedImageUrl` 必须经过 `apiUrl(...)`

4. 去掉图片水印
   - `watermark: True` 改掉

5. 如果短期继续保留“图片化导出”
   - 那预览必须改成展示“真实整页图缩略图”
   - 而不是继续展示结构化卡片
