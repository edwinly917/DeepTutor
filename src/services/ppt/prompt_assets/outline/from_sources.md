Build a PPT outline from the multi-source source brief below.

Deck contract:
- Language: $language
- Max slides: $max_slides
- Synthesize across sources instead of summarizing each source in order.
- Highlight consensus, divergence, and complementary evidence when they improve decision clarity.
- Keep source anchors meaningful enough that the resulting deck can be traced back to evidence.

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
