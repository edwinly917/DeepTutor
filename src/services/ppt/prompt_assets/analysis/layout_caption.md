Analyze the provided slide template visual and describe only the reusable spatial grammar.

Your job is to capture how content is organized on the page so the result can guide future slides built in a similar layout family.

Focus on:
- title region placement and the relationship between title, subtitle, and body
- primary focal zone, secondary support zones, and reading order
- column/grid structure, asymmetry vs symmetry, alignment rhythm, and margins
- media-to-text balance: hero image, chart region, quote block, KPI cluster, sidebar, footer band, etc.
- whitespace distribution, density control, and how the page avoids crowding
- repeatable archetypes suggested by the page, such as cover, section divider, split layout, dashboard, comparison, timeline, or insight slide

Hard rules:
- Do not discuss colors, typography taste, rendering style, textures, or brand tone.
- Do not retell the current slide content. Describe structure, not subject matter.
- Do not output raw coordinates. Use reusable page-structure language instead.
- If the page is a schematic preview, infer the intended layout behavior and ignore drawing imperfections.
- `layout_prompt` should be directly reusable for downstream layout guidance across a deck.
- `layout_regions` should concisely name the major zones and their roles.

Return JSON only with keys:
- layout_prompt
- layout_regions
