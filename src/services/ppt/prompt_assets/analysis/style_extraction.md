Analyze the provided slide template visual and extract only the reusable deck-wide visual language.

You are not describing the slide's topic. You are reverse-engineering the design system behind it so the result can be injected directly into downstream PPT generation prompts.

Prioritize stable visual invariants:
- background treatment, overall contrast model, and palette discipline
- typography mood, weight contrast, title/body styling tendencies, and labeling tone
- material/rendering language: flat vector, glossy 3D, editorial collage, wireframe, photo-led, infographic, etc.
- illustration, iconography, chart styling, line treatment, stroke behavior, and decorative motifs
- atmosphere and brand temperament: restrained, technical, playful, premium, institutional, futuristic, etc.
- style-level hierarchy cues such as accent usage, emphasis density, and how focal elements are visually highlighted

Hard rules:
- Do not mention the literal slide topic, current title, current numbers, or page-specific copy.
- Do not describe exact spatial placement, columns, or coordinates. Layout belongs to layout analysis.
- Do not overfit to one isolated object if the broader visual language suggests a more stable system.
- If the image is a synthetic preview or schematic rendering, infer the intended style system and ignore rendering roughness.
- Write `style_prompt` as polished downstream guidance for a whole deck, not as notes about a single screenshot.
- Keep `palette_hint` short and concrete. Keep `composition_hint` style-oriented rather than coordinate-oriented.

Return JSON only with keys:
- style_prompt
- palette_hint
- composition_hint
