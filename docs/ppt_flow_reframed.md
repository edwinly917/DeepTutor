# PPT Flow Reframed

Date: 2026-03-23

Reference inputs:

- Current audit: `docs/ppt_current_pipeline_audit.md`
- Target architecture note: `/Users/bytedance/Desktop/notebooklm-ppt-refactor/stateless-kindling-cupcake-PPT改造方案-claude.md`

## 1. 这份文档解决什么问题

`docs/ppt_current_pipeline_audit.md` 已经把问题定位清楚了，尤其是：

- 4.2 图片 prompt 语义像“支撑视觉”，却被当成最终整页导出
- 4.3 描述阶段产出的文字没有进入最终导出
- 5.6 / 5.7 / 5.8 / 5.9 四个阶段之间的数据契约不干净

这份文档不再做问题罗列，而是直接回答：

- 这 4 个阶段应该分别承担什么职责
- 它们之间传什么数据才不会再次语义错位
- Preview / Export 应该挂在哪个阶段的产物上

---

## 2. 先定一个总原则

**三入口只在 Extractor 层分叉；从 `NormalizedContent` 开始，后面必须是统一主链路。**

也就是说：

1. `from_research`
2. `from_notebook`
3. `from_sources`

这三条路的区别只在“原始输入怎么冻结、怎么清洗、怎么归一化”。

从这里开始：

```text
NormalizedContent
  -> Outline
  -> PageScript
  -> VisualSpec
  -> VisualAsset
  -> RenderedSlide
  -> Preview / Export
```

后面不应该再因为入口不同而长出不同语义的子流程。

---

## 3. 我建议的“干净版主流程”

## 3.1 Stage A: Content Extract / Normalize

输入：

- research report
- notebook records
- selected sources

输出：

- `NormalizedContent`

建议数据契约：

```ts
type NormalizedContent = {
  sourceType: "research" | "notebook" | "sources"
  topic: string
  markdown: string
  sourceRefs: SourceRef[]
}
```

职责边界：

- 只解决“原始材料 -> 可做 PPT 规划的中间语义层”
- 不碰 layout
- 不碰页面图像
- 不碰 preview

这一层和附件方案完全一致。

---

## 3.2 Stage B: Outline Generation

输入：

- `NormalizedContent`
- `StyleContext`

输出：

- `Outline`

建议数据契约：

```ts
type Outline = {
  title: string
  subtitle: string
  themeColor: string
  accentColor: string
  slides: Array<{
    pageId: string
    title: string
    points: string[]
    layout: LayoutType
  }>
}
```

职责边界：

- 只决定 deck 结构
- 只决定每页讲什么
- 只给出 `layout hint`
- 这里不要生成最终 `imagePrompt`

理由：

- `imagePrompt` 是视觉层的事，不应该在结构规划层提前“钉死”
- 一旦大纲阶段就输出 `imagePrompt`，后面 description / visual 层容易重复改写同一概念

如果为了兼容旧接口短期必须保留 `imagePrompt` 字段，也建议把它视为：

- `visualSeed`

而不是最终 prompt。

---

## 3.3 Stage C: Page Script Generation

这一步对应你当前文档里的 **5.6 单页描述 prompt**，但我建议换名字。

不要再叫 `description`，建议叫：

- `PageScript`
- 或 `PageSemanticSpec`

因为它的职责不是“写一段文案”，而是**定义这一页的权威语义**。

输入：

- `Outline.slide`
- `deck summary`
- `supporting context`
- `StyleContext`

输出：

- `PageScript`

建议数据契约：

```ts
type PageScript = {
  pageId: string
  title: string
  points: string[]
  keyMessage: string
  supportingFacts: string[]
  narrativeRole: "cover" | "section" | "analysis" | "comparison" | "conclusion"
  layout: LayoutType
  speakerNote?: string
}
```

关键点：

- `title` / `points` 仍然是最终页面文本的权威来源
- `keyMessage` 是给视觉和编辑层用的摘要
- `supportingFacts` 是给后续 visual prompt 和单页编辑用的证据层
- `layout` 仍然保留，但只是 render contract 的输入之一

这一步**不要输出最终生图 prompt**。

为什么：

1. 当前 5.6 同时输出 `text` 和 `image_prompt`，把“语义层”和“视觉层”绑死了
2. 一旦用户改 description，就会连带 image prompt 也一起污染
3. 这会让单页编辑失效边界变得非常混乱

所以建议：

- 5.6 只产出 `PageScript`
- 不在这里做图片 prompt

---

## 3.4 Stage D: Visual Spec Generation

这一步对应你当前文档里的 **5.7 图片最终 prompt 包装**，但我建议把它提升为一个独立、显式的语义层。

建议命名：

- `VisualSpec`
- 或 `VisualBrief`

输入：

- `PageScript`
- `StyleContext`
- `NormalizedContent` 的 relevant slice

输出：

- `VisualSpec`

建议数据契约：

```ts
type VisualSpec = {
  pageId: string
  assetRole: "hero" | "supporting" | "background" | "diagrammatic"
  compositionIntent: string
  focalElements: string[]
  forbiddenElements: string[]
  imagePrompt: string
}
```

职责边界：

- 把“这一页需要什么视觉”说清楚
- 但仍然不要承担 Preview / Export 的最终成品职责

这里要非常明确一件事：

**`VisualSpec` 的产物是“视觉素材说明”，不是“最终整页 PPT 页面说明”。**

所以 prompt 应该明确写成：

- supporting visual
- hero visual
- background visual
- diagrammatic visual

而不要混成：

- full slide
- final presentation page

否则就会再次回到当前 audit 里 4.2 的问题。

---

## 3.5 Stage E: Visual Asset Generation

这一步对应你当前文档里的 **5.8 图片模型调用**。

输入：

- `VisualSpec`

输出：

- `VisualAsset`

建议数据契约：

```ts
type VisualAsset = {
  pageId: string
  imagePath: string
  thumbnailPath?: string
  model: string
  promptUsed: string
  version: number
}
```

职责边界：

- 只负责生成视觉素材
- 不负责页面文字
- 不负责最终 slide preview
- 不负责导出 PPT 对象

这一步的 prompt 需要满足：

1. 不生成大段可读文字
2. 不生成 logo / watermark
3. 明确自己只是视觉素材，不是假装替代整页 PPT

所以如果你保留 Doubao / Gemini 这类模型，这一步更应该生成：

- 背景图
- 主题插图
- 图解型视觉素材

而不是整个 slide screenshot。

---

## 3.6 Stage F: Slide Render

这是当前流程里**缺失但必须存在**的一层。

它正是当前 5.6-5.9 之间最大的语义断裂点。

输入：

- `PageScript`
- `VisualAsset`
- `StyleContext`

输出：

- `RenderedSlide`

建议数据契约：

```ts
type RenderedSlide = {
  pageId: string
  previewImagePath: string
  exportImagePath: string
  renderVersion: number
}
```

职责边界：

- 真正把 title / points / layout / visual asset 组合成一页完整 slide
- Preview 读这个
- Export 也读这个

这是最关键的统一点：

**Preview 和 Export 必须共享同一个 `RenderedSlide` 产物。**

不管你最后用：

- HTML/CSS 渲染转图
- Canvas 渲染
- 服务端模板渲染
- 未来的 PPT engine

都没关系。

关键是不能再出现：

- Preview 看 `Outline + raw image`
- Export 看 `full image only`

这样的双语义链路。

---

## 3.7 Stage G: Export

这一步对应当前文档里的 **5.9 导出**。

输入：

- `RenderedSlide[]`

输出：

- `.pptx`

职责边界：

- 只负责打包导出
- 不再做页面语义决策
- 不再做图片 prompt 拼装
- 不再决定是否显示标题/正文

也就是说，export 是纯 IO 层：

```text
RenderedSlide[] -> PPTX
```

不是：

```text
imagePrompt + generated image -> 猜测最终页面 -> PPTX
```

---

## 4. 为什么我推荐这版，而不是继续沿用当前 5.6-5.9

因为当前 5.6 到 5.9 混了 3 类不同语义：

1. 页面语义
2. 视觉素材语义
3. 最终页面渲染语义

当前具体混乱点：

### 4.1 当前 5.6 同时承担“语义页脚本”和“视觉 prompt 种子”

问题：

- 一个阶段同时产出 `text` 和 `image_prompt`
- 用户改 description 时，会间接污染 image generation

建议：

- 拆成 `PageScript`
- 再由下一层生成 `VisualSpec`

### 4.2 当前 5.7 把 Visual Prompt 当 Final Slide Prompt

问题：

- prompt 文案仍然在说 “slide illustration”
- 但系统行为把它当“最终整页 slide”

建议：

- 明确这一步只生成 `VisualSpec`
- 不承担最终页面职责

### 4.3 当前 5.8 产物被误用

问题：

- 视觉素材生成出来后，被直接拿去 export

建议：

- 只能进入 `Slide Render`
- 不能直接进入 export

### 4.4 当前 5.9 不是 export，而是在“补做最终页面语义决策”

问题：

- 现在 export 阶段实际上决定了“最后只保留图片”
- 这说明上游没有真正产出统一的最终页面对象

建议：

- export 阶段必须降级为纯打包

---

## 5. 如果你坚持保留“图片化导出”，最少也要怎么改

如果你短期内不想引入 `Slide Render`，那么有一个次优但能自洽的版本：

## 5.1 次优方案的数据流

```text
Outline
  -> FullSlidePrompt
  -> FullSlideImage
  -> Preview / Export
```

这意味着：

- 彻底删掉当前 5.6 的 `description_content.text` 语义
- 不再假装后面会叠加文字
- 5.7 直接改写成“整页 slide image prompt”
- Preview 也只展示 `FullSlideImage`
- Export 继续打包图片

这样至少链路一致。

但这个方案有两个天然上限：

1. 文字准确性很差
2. 页面信息密度很难稳定控制

所以它适合：

- 海报式页面
- 情绪版 / 视觉版 deck

不适合：

- 研究汇报
- 数据密集页
- 需要稳定标题和 bullet 的分析型 PPT

---

## 6. 我对你当前项目的明确建议

结合你现在的目标，我建议你不要继续让 `SlidePreview.tsx` 去“模拟 PPT 结构”，而是直接围绕 `RenderedSlide` 重建。

优先级如下：

### Priority 1

先定义统一页面对象：

- `Outline`
- `PageScript`
- `VisualSpec`
- `VisualAsset`
- `RenderedSlide`

### Priority 2

把当前 5.6 改名并收窄职责：

- 从 `description generation`
- 改为 `page script generation`

只负责页面语义，不生成最终 image prompt。

### Priority 3

把当前 5.7 改成真正的 `VisualSpec generation`

明确它只是：

- visual brief
- supporting visual prompt

### Priority 4

新增 `Slide Render` 层

让：

- preview 读 `RenderedSlide.previewImagePath`
- export 读 `RenderedSlide.exportImagePath`

### Priority 5

导出层降级成纯打包

这样 5.9 就终于变成真正的 export，而不是“补做最后一次内容裁决”。

---

## 7. 单页编辑的失效规则也要随之重排

如果采用上面的分层，单页编辑的失效边界会清晰很多：

### 7.1 outline_edit

失效：

- `PageScript`
- `VisualSpec`
- `VisualAsset`
- `RenderedSlide`

### 7.2 description_edit

如果 description 对应的是 `PageScript` 里的语义补充字段，那么失效：

- `PageScript`
- `VisualSpec`
- `VisualAsset`
- `RenderedSlide`

### 7.3 image_edit

只失效：

- `VisualSpec`
- `VisualAsset`
- `RenderedSlide`

不应该重新跑 Outline。

---

## 8. 最终一句话版

如果你想把当前 PPT 流程真正理顺，可以直接记成下面这句话：

**Extractor 只解决输入统一，Outline 只解决结构统一，PageScript 只解决页面语义统一，VisualSpec / VisualAsset 只解决视觉素材统一，RenderedSlide 才是 Preview 和 Export 的共同真相。**
