You are extracting reusable presentation content structure from a template file.

File name: $file_name

Extracted text:
$file_text

Interpret the text as evidence about the template's reusable content skeleton, not as a topic that must be copied.

Return JSON only with keys:
- content_prompt
- key_sections

Rules:
- Do not dump OCR text or paragraph-level prose back to the user.
- Infer recurring page archetypes, section progression, and content modules when the text supports them.
- Prefer deck-level structure such as "cover -> agenda -> section divider -> analysis -> comparison -> conclusion" over literal subject retelling.
- Preserve meaningful recurring labels, but normalize noisy variants into a concise pattern.
- If the text suggests chart-led, case-study, KPI, timeline, comparison, or recommendation pages, summarize those as reusable modules.
- `content_prompt` should be suitable for direct injection into downstream prompt assembly as template content guidance.
- `key_sections` should be a compact list of stable section labels or archetypes, not a transcript.
- If the extracted text is too weak or too noisy to support a confident pattern, return empty strings instead of inventing structure.
