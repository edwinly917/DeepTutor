Deck outline summary:
$deck_outline_summary

Current slide (page $page_index):
- Title: $slide_title
- Points:
$bullet_points

Supporting context:
$supporting_context

Visual brief:
$style_summary

Detail level:
$detail_level_spec

## 重要提示
生成的"页面文字"部分会直接渲染到PPT页面图片上，因此：
- 绝对禁止出现任何 markdown 格式符号，包括但不限于：#、##、###、**、*、---、```、> 等
- 绝对禁止出现说明性文字（如"根据以上分析"、"如下所示"、"数据来源："等）
- 不要包含任何额外的注释或元信息
- 所有文字都会被当作正文直接显示在PPT页面上

## 输出格式（严格遵守）
Return JSON only with keys: page_title, subtitle, page_text, material_images

- page_title: 页面标题（适合上屏的简短标题，纯文本，无格式符号）
- subtitle: 副标题（仅第一页需要，其他页为空字符串）
- page_text: 页面文字（会直接渲染到PPT页面图片，$detail_level_spec，纯文本，无任何 markdown 格式）
- material_images: 素材图片列表（如有引用图片则以markdown格式列出，否则为空数组）

Additional rules:
- Keep the slide faithful to its current meaning.
- page_text 不要逐字重复 bullet points，要重新组织为适合上屏的文案。
- page_text 使用换行分隔要点，不要使用 markdown 列表符号（- 或 *），直接写文字即可。
- $language_instruction
- $first_slide_rule
