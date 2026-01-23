from datetime import datetime
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfgen import canvas
except ImportError:
    A4 = None
    mm = None
    pdfmetrics = None
    UnicodeCIDFont = None
    canvas = None

from src.logging import get_logger

logger = get_logger("PDFGenerator")


class PDFGenerator:
    """
    Service for generating a simple PDF document from Markdown content.
    """

    def __init__(self, export_dir: Union[str, Path]):
        self.export_dir = Path(export_dir)
        self.export_dir.mkdir(parents=True, exist_ok=True)
        self.font_name = "Helvetica"
        if canvas is None:
            logger.warning("reportlab not installed. PDF export will fail.")
        else:
            self._configure_fonts()

    def _configure_fonts(self) -> None:
        """Register a CJK-capable font when available."""
        try:
            pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
            self.font_name = "STSong-Light"
        except Exception:
            self.font_name = "Helvetica"

    async def generate(
        self,
        markdown: str,
        title: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate a PDF file from markdown.

        Args:
            markdown: Markdown content.
            title: Optional title for the document.

        Returns:
            Dict containing filename, relative_path, and download_url.
        """
        if canvas is None:
            raise ImportError("reportlab is required for PDF export.")

        extracted_title = self._extract_title(markdown)
        final_title = (title or "").strip() or extracted_title
        safe_title = self._sanitize_filename(final_title)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{safe_title}_{timestamp}.pdf"
        output_path = self.export_dir / filename

        page_width, page_height = A4
        margin = 18 * mm
        line_spacing = 1.4

        pdf = canvas.Canvas(str(output_path), pagesize=A4)
        pdf.setTitle(final_title)

        y = page_height - margin

        def draw_text(
            text: str,
            font_size: int,
            indent: float = 0.0,
            extra_spacing: float = 0.0,
            font_override: Optional[str] = None,
        ) -> None:
            nonlocal y

            if text == "":
                y -= font_size * line_spacing
                return

            font_name = font_override or self.font_name
            pdf.setFont(font_name, font_size)
            max_width = page_width - margin * 2 - indent
            lines = self._wrap_text(text, font_name, font_size, max_width)
            for line in lines:
                if y <= margin:
                    pdf.showPage()
                    pdf.setFont(font_name, font_size)
                    y = page_height - margin
                pdf.drawString(margin + indent, y, line)
                y -= font_size * line_spacing

            if extra_spacing:
                y -= extra_spacing

        for text, style in self._iter_markdown_lines(markdown):
            if style == "h1":
                draw_text(text, 18, extra_spacing=4)
            elif style == "h2":
                draw_text(text, 15, extra_spacing=2)
            elif style == "h3":
                draw_text(text, 13, extra_spacing=1)
            elif style == "code":
                draw_text(text, 10, indent=10, font_override="Courier")
            elif style == "bullet":
                draw_text(f"- {text}", 11, indent=6)
            elif style == "blank":
                draw_text("", 11)
            else:
                draw_text(text, 11)

        pdf.save()

        try:
            parts = output_path.parts
            if "data" in parts and "user" in parts:
                user_idx = parts.index("user")
                relative_path = "/".join(parts[user_idx + 1 :])
            else:
                relative_path = f"notebook/exports/{filename}"
        except ValueError:
            relative_path = f"notebook/exports/{filename}"

        return {
            "filename": filename,
            "relative_path": relative_path,
            "download_url": f"/api/outputs/{relative_path}",
        }

    def _extract_title(self, markdown: str) -> str:
        for line in markdown.splitlines():
            line = line.strip()
            if line.startswith("# "):
                return line[2:].strip()
        return "Notebook Export"

    def _sanitize_filename(self, value: str) -> str:
        value = value.replace("\0", "")
        cleaned = re.sub(r'[\\/*?:"<>|\n\r]+', "", value)
        cleaned = cleaned.strip()
        return cleaned or "export"

    def _iter_markdown_lines(self, markdown: str) -> List[Tuple[str, str]]:
        lines: List[Tuple[str, str]] = []
        in_code_block = False
        for raw_line in markdown.splitlines():
            line = raw_line.rstrip()
            stripped = line.strip()

            if stripped.startswith("```"):
                in_code_block = not in_code_block
                continue

            if in_code_block:
                lines.append((line, "code"))
                continue

            if not stripped:
                lines.append(("", "blank"))
                continue

            if stripped.startswith("# "):
                lines.append((self._strip_inline(stripped[2:]), "h1"))
            elif stripped.startswith("## "):
                lines.append((self._strip_inline(stripped[3:]), "h2"))
            elif stripped.startswith("### "):
                lines.append((self._strip_inline(stripped[4:]), "h3"))
            elif stripped.startswith(("- ", "* ", "+ ")):
                lines.append((self._strip_inline(stripped[2:]), "bullet"))
            else:
                lines.append((self._strip_inline(stripped), "body"))
        return lines

    def _strip_inline(self, text: str) -> str:
        text = re.sub(r"!\[(.*?)\]\(.*?\)", r"\1", text)
        text = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", text)
        text = re.sub(r"`([^`]+)`", r"\1", text)
        text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
        text = re.sub(r"\*(.*?)\*", r"\1", text)
        text = re.sub(r"__(.*?)__", r"\1", text)
        text = re.sub(r"_(.*?)_", r"\1", text)
        return text.strip()

    def _wrap_text(
        self, text: str, font_name: str, font_size: int, max_width: float
    ) -> List[str]:
        if not text:
            return [""]

        if " " not in text:
            return self._wrap_text_no_spaces(text, font_name, font_size, max_width)

        words = text.split()
        lines: List[str] = []
        current = ""

        for word in words:
            candidate = f"{current} {word}".strip()
            if pdfmetrics.stringWidth(candidate, font_name, font_size) <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                if pdfmetrics.stringWidth(word, font_name, font_size) > max_width:
                    lines.extend(
                        self._wrap_text_no_spaces(word, font_name, font_size, max_width)
                    )
                    current = ""
                else:
                    current = word

        if current:
            lines.append(current)

        return lines

    def _wrap_text_no_spaces(
        self, text: str, font_name: str, font_size: int, max_width: float
    ) -> List[str]:
        lines: List[str] = []
        current = ""
        for char in text:
            candidate = f"{current}{char}"
            if pdfmetrics.stringWidth(candidate, font_name, font_size) <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = char
        if current:
            lines.append(current)
        return lines
