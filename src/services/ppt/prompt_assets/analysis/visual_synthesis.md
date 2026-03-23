You are consolidating visual analysis findings from multiple template pages into reusable PPT guidance.

Your job is to identify the stable design system and stable layout grammar across the previews. Do not concatenate page-by-page notes.

Consolidation rules:
- Extract only the recurring style invariants shared across the pages.
- Extract only the recurring layout logic that appears reusable across the deck.
- Ignore one-off content details, specific slide titles, accidental anomalies, and page-specific illustrations that do not reflect the template system.
- If there are multiple page archetypes, keep the dominant shared rules and express variation only when it is clearly part of the template family.
- Prefer deck-wide guidance over screenshot commentary.
- `reference_style_prompt` should directly guide palette discipline, typography mood, rendering treatment, chart/illustration style, decorative motifs, and overall tone.
- `reference_layout_prompt` should directly guide title/body relationship, region partitioning, dominant focal area, media-text balance, alignment rhythm, and whitespace logic.
- Both outputs should be concise, operational, and ready for direct injection into downstream PPT prompts.

Per-page findings:
$page_findings_json

Return JSON only with keys:
- reference_style_prompt
- reference_layout_prompt
