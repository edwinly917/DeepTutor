"""
Mindmap Generator Service
Converts Markdown research reports to Mermaid mindmap syntax
"""

import re
from typing import Optional


def extract_structure_from_markdown(markdown: str) -> dict:
    """Extract hierarchical structure from markdown headings."""
    lines = markdown.split('\n')
    result = {'title': 'Research Report', 'sections': []}
    current_h1 = None

    for line in lines:
        line = line.strip()
        if line.startswith('# '):
            title = line[2:].strip()
            if not current_h1:
                result['title'] = title
            else:
                result['sections'].append({'name': title, 'children': []})
            current_h1 = title
        elif line.startswith('## '):
            result['sections'].append({'name': line[3:].strip(), 'children': []})
        elif line.startswith('### '):
            if result['sections']:
                result['sections'][-1]['children'].append({
                    'name': line[4:].strip(), 'children': []
                })
        elif line.startswith('#### '):
            if result['sections'] and result['sections'][-1]['children']:
                result['sections'][-1]['children'][-1]['children'].append(line[5:].strip())

    return result


def escape_mermaid_text(text: str) -> str:
    """Escape special characters for Mermaid mindmap."""
    for old, new in [('(', '（'), (')', '）'), ('[', '【'), (']', '】'),
                     ('{', '｛'), ('}', '｝'), ('<', '＜'), ('>', '＞'), ('\n', ' ')]:
        text = text.replace(old, new)
    if len(text) > 30:
        text = text[:27] + '...'
    return text.strip()


def generate_mindmap_code(markdown: str) -> str:
    """Generate Mermaid mindmap code from markdown content."""
    structure = extract_structure_from_markdown(markdown)
    lines = ['mindmap']
    title = escape_mermaid_text(structure['title'])
    lines.append('  root((' + title + '))')

    for section in structure['sections'][:7]:
        lines.append('    ' + escape_mermaid_text(section['name']))
        for subsection in section.get('children', [])[:5]:
            if isinstance(subsection, dict):
                lines.append('      ' + escape_mermaid_text(subsection['name']))
                for point in subsection.get('children', [])[:3]:
                    if isinstance(point, str):
                        lines.append('        ' + escape_mermaid_text(point))

    return '\n'.join(lines)


_LLM_PROMPT = (
    "Convert the following research report to Mermaid mindmap syntax.\n\n"
    "Rules:\n"
    "1. Use report title as center node root((title))\n"
    "2. Main sections as first-level branches\n"
    "3. Key points as second-level branches\n"
    "4. Max 7 nodes per level\n"
    "5. Max 20 chars per node\n"
    "6. No special chars like () [] {}\n\n"
    "Example:\n"
    "mindmap\n"
    "  root((Topic))\n"
    "    Branch1\n"
    "      Point1a\n"
    "    Branch2\n"
    "      Point2a\n\n"
    "Content:\n{content}\n\n"
    "Output mermaid mindmap code only:"
)


async def generate_mindmap_with_llm(markdown: str, llm_callable: Optional[callable] = None) -> str:
    """Generate mindmap using LLM for better structure extraction."""
    if llm_callable is None:
        return generate_mindmap_code(markdown)

    try:
        result = await llm_callable(_LLM_PROMPT.format(content=markdown[:4000]))
        if '```mermaid' in result:
            match = re.search(r'```mermaid\s*(.*?)\s*```', result, re.DOTALL)
            if match:
                return match.group(1).strip()
        elif '```' in result:
            match = re.search(r'```\s*(.*?)\s*```', result, re.DOTALL)
            if match:
                return match.group(1).strip()
        if result.strip().startswith('mindmap'):
            return result.strip()
        return generate_mindmap_code(markdown)
    except Exception:
        return generate_mindmap_code(markdown)
