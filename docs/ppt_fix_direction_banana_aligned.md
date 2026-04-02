# PPT Fix Direction: Banana-Aligned

Date: 2026-03-23

## 1. 结论先说

在重新对照：

- `/Users/bytedance/Desktop/notebooklm-ppt-refactor/stateless-kindling-cupcake-PPT改造方案-claude.md`
- banana-slides 的真实实现

之后，我认为当前项目最应该修正成的，不是“结构化预览 + 视觉素材图 + 图片化导出”的混合流，而是：

```text
NormalizedContent
  -> Outline
  -> PageDescription
  -> FullSlideRenderPrompt
  -> SlideImage
  -> Preview / Export
```

也就是：

- **PageDescription 是页面语义真相**
- **SlideImage 是页面视觉真相**
- **Preview 和 Export 必须共享同一张 SlideImage**

这才是最接近 banana-slides 的真实工作方式，也最符合你当前项目“仅保留导出 PPT，不追求可编辑导出”的目标。

---

## 2. 为什么我改了之前的判断

我前一版更偏“抽象分层”，把流程拆成：

- `PageScript`
- `VisualSpec`
- `VisualAsset`
- `RenderedSlide`

这个分层理论上更干净，但它更像一套“自研结构化渲染引擎”的架构。

而 banana-slides 的真实实现并不是这么走的。

从它的 backend prompt 和服务实现看，banana 更接近下面这个模式：

1. 大纲生成
2. 每页生成 **可直接渲染的页面描述**
3. 再把页面描述交给图像模型，直接生成整页 PPT 图
4. Preview 看这张图
5. Export 也基于这张图，进一步做图片化或可编辑提取

也就是说，banana 的关键不是“先生成素材，再自己排版”，而是：

- **先生成页面描述，再让图像模型直接完成整页页面渲染**

所以如果你的目标是：

- 对齐 banana-slides 的思路
- 快速把当前链路从错位状态拉回自洽

那么更优先的不是引入独立 `VisualAsset` 层，而是把当前 5.6 到 5.9 重构成一个 **full-slide rendering pipeline**。

---

## 3. banana-slides 里真正值得学的不是“提示词长什么样”，而是“阶段契约”

从 banana 的实现里，至少能看出 3 个关键约束：

### 3.1 描述阶段就是页面语义真相

banana 的 `get_page_description_prompt(...)` 不是在写“给人看的说明文”，而是在生成一个**会直接被后续渲染消费的页面描述**。

它要求的输出核心是：

- `页面文字`
- `图片素材`
- 可选额外字段

而且 prompt 里明确强调：

- 页面文字会直接渲染到 PPT 页面上

这说明在 banana 里：

- 描述阶段不是附属信息
- 它就是后续图像渲染的权威语义输入

### 3.2 图像阶段不是“配图生成”，而是“整页页面渲染”

banana 的 `get_image_generation_prompt(...)` 明确要求模型：

- 生成设计良好的 PPT 页面
- 把 `页面文字` 段落中的文字准确渲染出来
- 配色和模板风格保持一致

这和当前 DeepTutor 的 `image/generation.md` 有本质区别。

当前 DeepTutor prompt 更像：

- supporting visual
- slide illustration
- 留白给后续文字覆盖

banana 则更像：

- full slide render

所以你现在的问题，不是“image prompt 写得不够好”，而是：

- **你还在用“配图 prompt”，但系统行为已经把它当“整页成品 prompt”用了**

### 3.3 导出阶段消费的是整页渲染结果

banana 的 export service 已经不把“图片”当成普通素材，而是把它当页面成品去处理，甚至再向可编辑 PPT 提取元素。

对你当前项目来说，可编辑提取可以先不要，但至少应该继承这个核心约束：

- Export 必须消费和 Preview 同一个页面级结果

---

## 4. 对当前项目，5.6 到 5.9 应该怎么改

下面直接对应你 audit 文档里的阶段编号。

## 4.1 当前 5.6 应该改成什么

当前 5.6 是：

- `DescriptionGenerator`
- 输出 `text + image_prompt`

这是错位的，因为一个阶段同时在做：

1. 页面语义生成
2. 视觉 prompt 生成

建议改成：

### 新 5.6: `PageDescription`

输入：

- outline page
- deck summary
- supporting context
- style context

输出：

```ts
type PageDescription = {
  pageId: string
  title: string
  bodyText: string
  materialImages: string[]
  extraFields?: {
    visualElements?: string
    visualFocus?: string
    layoutGuidance?: string
    speakerNotes?: string
  }
}
```

要点：

- `bodyText` 是最终页面文字真相
- `materialImages` 是可以直接并入页面的素材引用
- 这里不再持久化“最终 image_prompt”

换句话说：

- 当前 `description_content.text` 不该是边缘信息
- 它应该升级成后续所有页面渲染的主输入

---

## 4.2 当前 5.7 应该改成什么

当前 5.7 是：

- 用 `image/generation.md`
- 把 `slide_title / slide_points / layout / style_context / source_brief / image_prompt` 拼起来

问题是：

- 它还是“插画 prompt”
- 不是“整页页面渲染 prompt”

建议改成：

### 新 5.7: `FullSlideRenderPrompt`

输入：

- `PageDescription`
- `StyleContext`
- 模板分析结果
- 参考图 / 素材图

输出：

```ts
type FullSlideRenderPrompt = {
  pageId: string
  prompt: string
}
```

这个 prompt 的目标必须明确写成：

- 渲染一整页 PPT 页面
- 准确渲染页面文字
- 智能整合 `materialImages`
- 保持模板风格与版式特征
- 不是生成背景图，不是生成插画素材

这一步才是你当前真正缺失的“语义纠偏层”。

---

## 4.3 当前 5.8 应该改成什么

当前 5.8 是：

- 图像模型调用
- 输出 `v1.png / v1.jpg`

这个阶段本身可以保留，但语义必须改变：

### 新 5.8: `SlideImage Generation`

输入：

- `FullSlideRenderPrompt`

输出：

```ts
type SlideImage = {
  pageId: string
  imagePath: string
  cachedPath?: string
  promptUsed: string
  version: number
}
```

关键点：

- 这张图不是视觉素材
- 这张图就是“整页 PPT 页面”

所以生成后：

- Preview 直接显示它
- Export 直接消费它

当前前端那个 `SlidePreview.tsx` 手写布局卡片，应该从“主预览真相”退位，只保留为：

- loading skeleton
- outline preview fallback

而不是正式预览。

---

## 4.4 当前 5.9 应该改成什么

当前 5.9 的问题不是“没有 prompt”，而是它承担了错误的语义后果：

- 它把 upstream 没有统一好的结果，粗暴收敛成“只导图片”

建议改成：

### 新 5.9: `Export from SlideImages`

输入：

- `SlideImage[]`

输出：

- `.pptx`

要求：

- Export 不再决定页面内容
- Export 不再补救 layout
- Export 不再跳过页面文字
- Export 只是把和 Preview 相同的页面级结果打包出去

这样链路才会闭合。

---

## 5. 我对 layout 的修正建议

这一点很关键。

当前你有一个很强的错觉来源：

- `layout` 在前端 preview 中是刚性的代码布局
- `layout` 在后端图像生成中只是 prompt 中的一个弱提示

这两个东西不应该再假装是同一个概念。

建议改成：

### 5.1 保留 layout，但降低它的角色

让它从：

- “最终执行布局类型”

降级为：

- “页面构图意图标签”

例如：

- `cover`
- `section-divider`
- `hero-left`
- `hero-right`
- `top-visual`
- `quote`
- `data-card`
- `comparison`

它的作用是：

- 约束 PageDescription
- 影响 FullSlideRenderPrompt

但不要再在 Preview 里硬编码一个 React 版假布局来冒充最终页。

---

## 6. 对话式编辑应该怎么随之调整

如果采用 banana-aligned full-slide 流，那么三种编辑的失效边界会很清楚：

### 6.1 `outline_edit`

修改：

- `Outline`

失效：

- `PageDescription`
- `FullSlideRenderPrompt`
- `SlideImage`

### 6.2 `description_edit`

修改：

- `PageDescription`

失效：

- `FullSlideRenderPrompt`
- `SlideImage`

### 6.3 `image_edit`

不要直接改 `PageDescription` 主体内容，而是改：

- `render_requirements`
- 或 `image_edit_instruction`

失效：

- `FullSlideRenderPrompt`
- `SlideImage`

这样才符合 banana 的口头编辑思路：

- outline 改结构
- description 改内容表达
- image edit 改视觉实现

---

## 7. 对当前代码最实际的修正顺序

如果你现在要开始改，我建议顺序如下。

### Step 1

先把 `description_content` 升级成真正的 `PageDescription`

也就是：

- 它不再只是“说明文”
- 它要成为后续 full-slide 渲染的主输入

### Step 2

废弃当前页面级持久化 `image_prompt` 的“主语义地位”

可以暂时保留字段兼容，但语义改成：

- `render_prompt_cache`
- 或 `render_instruction_cache`

而不是页面核心真相。

### Step 3

重写 `src/services/ppt/prompt_assets/image/generation.md`

从：

- slide illustration

改成：

- full PPT page render

并明确：

- render all page text sharply
- follow page description strictly
- integrate material images when present
- no watermark / no stray symbols / no template text leakage

### Step 4

让 Preview 直接读真实 `SlideImage`

这样预览和导出天然一致。

### Step 5

导出继续先做图片化 PPT

这一步现在其实不急着改，只要它消费的已经是和 Preview 一致的整页 slide image，链路就已经自洽了。

---

## 8. 最终判断

如果参考 banana-slides 的真实实现，而不是只参考它的抽象分层思路，那么当前项目最合理的修正方向是：

**不要把 5.7 / 5.8 当成“素材图链路”，而要把它们收敛成“整页渲染链路”；不要让 Preview 继续看结构化卡片，而要让 Preview 和 Export 共同消费同一个 SlideImage。**

这才是最小代价、最大一致性的修正路径。
