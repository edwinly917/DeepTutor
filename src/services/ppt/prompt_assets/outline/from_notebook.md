Build a PPT outline from the notebook-derived source brief below.

Deck contract:
- Language: $language
- Max slides: $max_slides
- Find structure across scattered notes instead of listing records one by one.
- Group related ideas into a coherent narrative when the material supports one.
- If the brief omits Audience & Goal or Narrative Arc, do not invent them; use only grounded sections.
- Preserve tensions or contrasting viewpoints when present.

Visual planning brief:
$style_summary

$reference_context_xml

Allowed layouts:
$layout_values_json

Layout guidance:
- Choose layout based on slide function, not decoration.
- Use image-oriented layouts only when the slide benefits from a strong supporting visual.

imagePrompt guidance:
- imagePrompt must directly support the slide's message.
- Describe one professional 16:9 presentation visual concept.
- Prefer editorial, business, analytical, or conceptual visuals.
- Avoid logos, watermarks, readable text, UI screenshots, fantasy spectacle, or decorative-only imagery.

<source_brief>
$source_brief
</source_brief>
