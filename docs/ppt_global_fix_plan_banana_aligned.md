# PPT Global Fix Plan (Banana-Aligned, Export-Only)

Date: 2026-03-23

## 1. 目的

这份文档用于修正当前 PPT 改造执行过程中出现的全局偏差，并给出一套可直接落地的统一修复方案。

本方案在重新核对以下内容后得出：

- `/Users/bytedance/Desktop/notebooklm-ppt-refactor/stateless-kindling-cupcake-PPT改造方案-claude.md`
- [ppt-refactor-execution-plan.md](/Users/bytedance/DeepTutor-1-ppt-refactor-execution/docs/ppt-refactor-execution-plan.md)
- `/Users/bytedance/banana-slides` 的真实实现

本期范围明确限定为：

- 保留 AI 图片流导出 PPT
- 保证预览和导出一致
- 保证页面编辑能真实作用于最终结果
- 不做可编辑 PPT 导出

---

## 2. 最终结论

当前大方向没有错：

- 三入口统一编排是对的
- 统一 Prompt 管理是对的
- 图片化导出 PPT 作为本期目标是对的

真正的问题在于执行阶段有 3 个核心契约断裂了：

1. `description_content` 没有成为图片生成的真实主输入
2. 前端主预览仍在消费旧的结构化卡片预览契约
3. 用户编辑后的页面内容没有成为新的权威输入，后续 regeneration 会把它重新覆盖

因此，本期全局修复的最终目标不是重做架构，而是把系统收敛成下面这条单真相链路：

```text
Source Snapshot
  -> NormalizedContent
  -> Outline
  -> DescriptionContent
  -> SlideImage
  -> Preview / Export
```

也就是：

- `DescriptionContent` 是页面语义真相
- `SlideImage` 是页面视觉真相
- `Preview` 和 `Export` 必须共同消费同一个 `SlideImage`

这才是和 banana-slides 的真实工作方式一致、且适配本期“仅图片化导出”的正确形态。

---

## 3. 参考 banana-slides 后必须明确的 4 个原则

## 3.1 页面级主持久化对象应是 `description_content`，不是 `image_prompt`

banana 的页面模型里有：

- `outline_content`
- `description_content`
- `generated_image_path`

没有页面级持久化 `image_prompt` 作为主真相。

这意味着：

- 页面描述才是后续图片生成的权威输入
- `image_prompt` 如果存在，也只应该是运行时拼装结果、缓存或调试字段

## 3.2 图片 prompt 必须由 `description_content` 推导，而不是和它并列存在

banana 的生成链是：

- 先生成页面描述
- 再基于页面描述推导 image prompt
- 再生成整页图片

而不是：

- 页面描述和 image prompt 并列生成
- 再靠 image prompt 单独决定最终结果

如果 `image_prompt` 和 `description_content` 并列持久化为两个主数据源，系统最终一定会出现：

- 哪个才是真相不清晰
- 编辑 description 后，image prompt 没同步
- regeneration 时覆盖人工内容

## 3.3 预览必须直接看真实页图，而不是浏览器端假布局

banana 的预览缩略图直接显示真实生成图，不用卡片布局模拟 PPT。

因此本项目必须遵守：

- 主预览区域显示真实页图
- 缩略图区域显示真实页图
- 不再用 `SlidePreview.tsx` 这种手写 layout 卡片冒充最终页

## 3.4 在本期范围里，导出可以继续图片化，但必须彻底被动

本期不做可编辑导出没有问题。

但导出必须满足：

- 不决定页面内容
- 不补救页面布局
- 不自己再组合标题和正文
- 只消费已经确定好的 `SlideImage`

导出应该是打包器，不应该是第二套渲染器。

---

## 4. 本期正确的数据契约

## 4.1 Project 级数据

保留：

- `creation_type`
- `source_refs`
- `source_content`
- `normalized_content`
- `style_preset_id`
- `style_custom_text`
- `template_image_path`
- `reference_style_prompt`
- `reference_layout_prompt`
- `reference_content_prompt`
- `image_aspect_ratio`
- `language`

要求：

- `source_refs` 是冻结快照输入
- `normalized_content` 是归一化后的 PPT source brief
- 后续 outline / description / image 全部只读取项目冻结数据，不读取运行时左侧栏状态

## 4.2 Page 级数据

建议本期收敛成：

```ts
type PageRecord = {
  id: string
  project_id: string
  order_index: number
  part?: string | null

  outline_content?: {
    title: string
    points: string[]
    layout?: string
  } | null

  description_content?: {
    text: string
    generated_at?: string | null
    detail_level?: string | null
    material_images?: string[]
    render_requirements?: string | null
  } | null

  render_prompt_cache?: string | null

  generated_image_path?: string | null
  cached_image_path?: string | null

  is_dirty: boolean
  status: string
}
```

其中要特别注意：

- `description_content` 是主语义真相
- `render_prompt_cache` 不是主真相，只是缓存
- `generated_image_path` 才是最终视觉真相

## 4.3 废弃或降级的字段

下面这些东西本期不应该再承担主语义职责：

- 页面级 `image_prompt`
- 前端 `layout` 驱动的假页面结构
- `presentation_outline.slides[]` 中作为主预览载体的卡片字段

可以暂时兼容保留，但要降级为：

- 调试字段
- 兼容字段
- 过渡字段

不能再作为主链路的 truth source。

---

## 5. 本期正确的生成流程

## 5.1 Stage 1: Source Snapshot

输入：

- `from_research`
- `from_notebook`
- `from_sources`

要求：

- 项目创建时冻结输入
- 后续生成只依赖项目内快照
- 所有 retry / recovery 都不能回读左侧栏当前状态

输出：

- `source_refs`
- `source_content`

## 5.2 Stage 2: Normalization

输入：

- `source_content`
- `source_refs`
- `style_context`

输出：

- `normalized_content`

要求：

- 它是后续大纲生成唯一的标准化文本输入
- 必须缓存，避免每次重生成重新归一化

## 5.3 Stage 3: Outline Generation

输入：

- `normalized_content`
- `style_context`

输出：

- `outline_content[]`

要求：

- `layout` 只是页面构图意图标签
- `layout` 不代表前端要按它手工渲染页面

## 5.4 Stage 4: Description Generation

输入：

- `outline_content`
- `normalized_content`
- supporting context
- style context

输出：

- `description_content`

要求：

- 产出的是页面可渲染描述，不是普通说明文
- 页面文字要能直接进入最终图像渲染
- 如果有素材图，应该在 `description_content` 中体现
- 这里不再把 `image_prompt` 当成并列主产物

推荐输出心智：

```text
页面标题
副标题（如有）
页面文字
图片素材（如有）
可选 render_requirements
```

## 5.5 Stage 5: Render Prompt Compilation

输入：

- `description_content`
- `outline_content.layout`
- style context
- template analysis

输出：

- `render_prompt_cache`

要求：

- 这是临时生成阶段，不是用户主编辑对象
- prompt 的职责是把 `description_content` 编译成适合图像模型消费的页面渲染指令

注意：

- 这一步不能把 `description_content` 弱化成“背景图提示词”
- 它必须明确要求整页渲染文字

## 5.6 Stage 6: Slide Image Generation

输入：

- `render_prompt_cache`
- 模板图
- 描述中提取的素材图

输出：

- `generated_image_path`
- `cached_image_path`

要求：

- 生成的是整页 PPT 图
- 不是 supporting visual
- 不是背景图
- 不是给前端叠字的底图

## 5.7 Stage 7: Preview / Export

输入：

- `generated_image_path`

输出：

- 主预览
- 缩略图
- 图片化导出 PPT

要求：

- preview 和 export 共同消费同一个视觉结果
- preview 不能继续走浏览器端结构化模拟布局

---

## 6. 5.6 到 5.9 的正式修正

这部分直接替换当前 audit 文档中的错误阶段语义。

## 6.1 新 5.6: `DescriptionContent`

当前错误：

- 同时输出 `text + image_prompt`
- 页面描述没有成为后续渲染的真实主输入

正确做法：

- 只把 `description_content` 作为页面级主语义产物保存
- `image_prompt` 降级为运行时缓存，不再作为主真相

## 6.2 新 5.7: `Render Prompt Compilation`

当前错误：

- 直接复用旧的配图 prompt 模板
- prompt 目标是 supporting visual，不是整页页面渲染

正确做法：

- 新 prompt 必须明确：
  - render all page text
  - follow description strictly
  - integrate material images
  - match template style
  - no watermark
  - no extra template text leakage

## 6.3 新 5.8: `SlideImage`

当前错误：

- 系统行为把页面图当最终 PPT
- prompt 却还把图片当支撑视觉素材

正确做法：

- 页面图的语义必须改成最终成品图
- 预览和导出都直接消费它

## 6.4 新 5.9: `Export from SlideImages`

当前错误：

- 导出被迫承担“最终页面长什么样”的后果

正确做法：

- 导出只打包图片
- 不参与内容决策
- 不修 layout
- 不补文字

---

## 7. Prompt 侧必须做的全局修正

## 7.1 `description/page.md`

当前问题：

- 输出要求仍然把 `image_prompt` 作为同级主结果

必须改成：

- 输出单一 `description_content`
- 如果需要图片素材或渲染要求，在 description 内部结构中表达

推荐约束：

- 页面文字会直接被渲染到 PPT 页面
- 文本必须适合上屏
- 不要输出面向开发者的解释性注释

## 7.2 `image/generation.md`

当前问题：

- 仍然写着 `slide illustration`
- 仍然要求给后续文字留白
- 仍然要求避免 readable text

这些要求和本期真实系统行为完全冲突。

必须改成：

- full PPT page render
- render all supplied page text sharply
- use material images when available
- preserve template visual language
- do not add watermark
- do not omit supplied text
- do not invent unrelated content

## 7.3 编辑相关 prompt

### `outline_edit`

作用：

- 改页面结构
- 不直接决定最终图片表现

### `description_edit`

作用：

- 改 `description_content`
- 这是最终页面语义的直接修改

### `image_edit`

作用：

- 不改 outline 主内容
- 不覆盖 description 主体文案
- 只补充 `render_requirements` 或图片层面的修改要求

---

## 8. 编辑与 regeneration 的正确失效边界

这一条是当前实现里最容易做错、也是最关键的全局修复点。

## 8.1 `outline_edit`

修改：

- `outline_content`

失效：

- `description_content`
- `render_prompt_cache`
- `generated_image_path`

重新生成顺序：

```text
outline -> description -> image
```

## 8.2 `description_edit`

修改：

- `description_content`

失效：

- `render_prompt_cache`
- `generated_image_path`

重新生成顺序：

```text
description -> image
```

关键要求：

- 不能再重新跑 description generator
- 否则会把用户刚编辑过的内容覆盖掉

## 8.3 `manual description patch`

修改：

- `description_content`

失效：

- `render_prompt_cache`
- `generated_image_path`

行为：

- 先标记 `is_dirty=true`
- 等用户手动点 regenerate 或通过 chat 自动触发 regenerate

关键要求：

- 后续 regeneration 必须直接消费用户改后的 description

## 8.4 `image_edit`

修改：

- `description_content.render_requirements`
- 或专门的 `image_edit_instruction`

失效：

- `render_prompt_cache`
- `generated_image_path`

重新生成顺序：

```text
image only
```

关键要求：

- 不要把 image_edit 实现成“重写页面全部 description”

---

## 9. 前端全流程修复要求

## 9.1 主预览 UI

当前必须废弃的行为：

- `PptPreviewModal` 继续把 `SlidePreview.tsx` 当主预览组件

正确结构：

- 左侧：真实页图缩略图 + 状态 badge + dirty overlay
- 中间：选中页真实大图
- 右侧：编辑面板 / chat 历史 / prompt 输入

## 9.2 `SlidePreview.tsx`

处理方式：

- 从 notebook 主流程移除
- 或明确降级成 debug-only 组件

不能继续：

- 作为用户主预览
- 暗示 export 会得到结构化 layout

## 9.3 图片 URL

必须修正：

- 所有后端相对输出 URL，都必须走前端 `apiUrl(...)`

否则在分端口环境下会持续出现：

- 项目有图
- 页面却 404 不显示

## 9.4 预览与导出文件一致性

强要求：

- 主预览大图优先使用 `generated_image_path`
- 导出也使用 `generated_image_path`

`cached_image_path` 的定位：

- 仅用于缩略图优化
- 不应成为和导出不同的另一份视觉真相

如果要追求最强一致性，主预览和缩略图都直接使用 `generated_image_path`。

---

## 10. 后端全流程修复要求

## 10.1 `description_generator.py`

必须修改：

- 删除“主输出 `image_prompt`”的语义
- 输出只以 `description_content` 为核心

可以保留：

- 兼容性 `image_prompt`

但只能作为：

- 运行时缓存
- 过渡期兼容字段

## 10.2 `prompts.py`

必须修改：

- `page_description(...)` 的输出契约
- `image_generation(...)` 的输入契约

目标：

- image prompt 编译必须基于 `description_content`
- 不再以 `slide_title + slide_points + image_prompt` 为中心

## 10.3 `image_generator.py`

必须修改：

- prompt 组装参数改为以 `description_content` 为核心
- 禁用水印

强约束：

- 生成的是整页 PPT 图，不是配图

## 10.4 `orchestrator.py`

必须修改：

- `generate_full`
- `_run_generate_descriptions`
- `_run_generate_images`
- `_run_page_chat_edit`
- `_run_page_regeneration`
- `_generate_page_image`
- `_project_to_presentation_outline`

关键目标：

- regeneration 链路不能覆盖用户改写的 description
- preview model 要指向真实页图
- `presentation_outline` 不再暗含“前端代码模拟版式预览”

## 10.5 `slide_editor.py`

必须修改：

- `description_edit` 修改后，只触发 image regeneration
- `image_edit` 不重写页面主描述

---

## 11. 本期建议的实际改造顺序

为了避免全链路同时改坏，建议严格按下面顺序推进。

## Step 1: 修主数据契约

先完成：

- `description_content` 成为页面主语义真相
- `image_prompt` 从主数据契约里降级

这一步完成前，不要先改前端预览。

## Step 2: 重写成图 prompt

完成：

- `description/page.md`
- `image/generation.md`
- `prompts.py`

确保系统真正进入：

```text
description -> render prompt -> slide image
```

## Step 3: 修 regeneration 语义

完成：

- `description_edit` 不再重新跑 description generation
- manual patch 后 regenerate 直接消费现有 description

这是让编辑真正生效的关键。

## Step 4: 修主预览

完成：

- `PptPreviewModal` 改成真实页图预览
- `SlidePreview.tsx` 从主链路移除
- URL 拼接统一走 `apiUrl(...)`

## Step 5: 收口导出

确认：

- export 只读 `generated_image_path`
- dirty 页阻塞导出
- 缺图页阻塞导出

## Step 6: 清理旧契约

最后再做：

- 移除主流程对旧 preview svg 的依赖
- 清理前端旧 card preview 语义
- 清理文档里仍残留的 `text + image_prompt` 主契约描述

---

## 12. 需要同步修订的文档

## 12.1 `stateless-kindling-cupcake-PPT改造方案-claude.md`

建议修订点：

- 把 `DescriptionGenerator -> {text, image_prompt}` 改成以 `description_content` 为主
- 明确声明 `image_prompt` 不是页面主持久化结果
- 明确 preview/export 都消费真实页图

## 12.2 [ppt-refactor-execution-plan.md](/Users/bytedance/DeepTutor-1-ppt-refactor-execution/docs/ppt-refactor-execution-plan.md)

必须修订点：

- `description_edit -> regenerate description + image_prompt + image`
  改为：
  - `description_edit -> regenerate image only`

- Preview Fidelity 段落需要补充：
  - 主预览必须消费真实页图
  - 不能继续使用 `SlidePreview.tsx`

- 编辑契约需要补充：
  - manual description patch 后 regenerate 不得覆盖人工编辑内容

---

## 13. 风险点与防回退要求

## 13.1 最容易再次做错的点

1. 改了 prompt，但没改 regeneration 失效边界
2. 改了后端，但前端还在吃旧 `presentation_outline` 卡片语义
3. 改了 preview，但 export 继续拿另一份图片
4. 修了 description_edit，但 manual patch 路径仍会被覆盖
5. 保留 `image_prompt` 兼容字段后，旧代码偷偷继续读它当主输入

## 13.2 防回退要求

上线前至少确认：

- 编辑 description 后，重新生成的导出页内容确实变化
- 预览看到的图和导出进 PPT 的图路径一致
- 不再出现“预览是 layout 卡片，导出是整页生图”
- 图片 URL 在前后端分端口环境可正常显示

---

## 14. 验收标准

满足下面条件，才算这次全局修复完成。

## 14.1 生成链路

- `from_research / from_notebook / from_sources` 三入口都能生成
- `description_content` 进入成图链
- 成图 prompt 明确是整页渲染，不是支撑视觉图

## 14.2 编辑链路

- `outline_edit` 能改变最终导出
- `description_edit` 能改变最终导出
- manual patch description 后 regenerate 不会覆盖用户内容
- `image_edit` 只改视觉实现，不污染主文案

## 14.3 预览链路

- 预览缩略图显示真实页图
- 主预览显示真实页图
- dirty/regenerating 状态显示 overlay
- 失败页显示失败占位与 retry affordance

## 14.4 导出链路

- 导出页和主预览视觉一致
- dirty 页阻塞导出
- 缺图页阻塞导出
- 不出现额外水印

---

## 15. 一句话总结

本期全局修复的本质不是“继续微调 prompt”，而是**把系统从“旧 preview 卡片链路 + 新图片导出链路 + 错误 regeneration 语义”的混合状态，收敛成 `DescriptionContent -> SlideImage -> Preview/Export` 的单真相链路**。只要这条主契约不再摇摆，当前 PPT 质量、预览一致性和编辑有效性的问题才会一起收敛。
