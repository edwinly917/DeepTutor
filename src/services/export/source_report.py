import html
import re
from typing import Any, Dict, List, Optional

import requests

from src.logging import get_logger
from src.services.llm import complete as llm_complete
from src.services.llm import get_llm_config, get_token_limit_kwargs
from src.services.rag.service import RAGService

logger = get_logger("SourceReport")


class SourceReportGenerator:
    """
    Generate a structured Markdown report from selected sources.
    """

    def __init__(
        self,
        max_source_chars: int = 4000,
        max_total_chars: int = 16000,
        request_timeout: int = 15,
    ):
        self.max_source_chars = max_source_chars
        self.max_total_chars = max_total_chars
        self.request_timeout = request_timeout

    async def _collect_sources(
        self, sources: List[Dict[str, Any]], topic: Optional[str]
    ) -> Dict[str, Any]:
        if not sources:
            raise ValueError("No sources provided.")

        compiled_sources: List[str] = []
        used_sources: List[Dict[str, Any]] = []
        skipped_sources: List[Dict[str, Any]] = []
        total_chars = 0

        for idx, source in enumerate(sources, start=1):
            source_type = (source.get("type") or "").lower()
            title = source.get("title") or f"Source {idx}"
            url = source.get("url") or ""

            content = ""
            try:
                if source_type == "report":
                    content = source.get("content") or ""
                elif source_type == "web" and url:
                    content = self._fetch_web_content(url)
                elif source_type == "kb":
                    content = await self._fetch_kb_summary(title, topic)
                else:
                    skipped_sources.append(
                        {"title": title, "url": url, "reason": "unsupported_source"}
                    )
                    continue
            except Exception as exc:
                logger.warning(f"Source fetch failed for {title}: {exc}")
                skipped_sources.append({"title": title, "url": url, "reason": "fetch_failed"})
                continue

            content = content.strip()
            if not content:
                skipped_sources.append({"title": title, "url": url, "reason": "empty_content"})
                continue

            content = content[: self.max_source_chars]
            source_block = (
                f"[{idx}] {title}\n"
                f"URL: {url or 'N/A'}\n"
                f"Content:\n{content}\n"
            )

            total_chars += len(source_block)
            if total_chars > self.max_total_chars:
                break

            compiled_sources.append(source_block)
            used_sources.append({"title": title, "url": url, "type": source_type})

        if not compiled_sources:
            raise ValueError("No usable source content available.")

        return {
            "compiled_sources": compiled_sources,
            "used_sources": used_sources,
            "skipped_sources": skipped_sources,
        }

    async def generate(self, sources: List[Dict[str, Any]], topic: Optional[str] = None) -> Dict[str, Any]:
        result = await self._collect_sources(sources, topic)
        compiled_sources = result["compiled_sources"]
        used_sources = result["used_sources"]
        skipped_sources = result["skipped_sources"]

        system_prompt = (
            "You are a research assistant. Use only the provided source excerpts to write "
            "a concise, structured Markdown report. Do not invent facts. "
            "Include a clear title (#), sections (##), and bullet points when helpful. "
            "If sources are insufficient, briefly note limitations."
        )

        topic_line = f"Topic: {topic}\n\n" if topic else ""
        user_prompt = (
            f"{topic_line}"
            "Sources:\n"
            f"{chr(10).join(compiled_sources)}\n\n"
            "Write the report in Markdown. Cite sources inline using [1], [2], ... "
            "when referencing a specific source."
        )

        llm_cfg = get_llm_config()
        kwargs = {"temperature": 0.4}
        kwargs.update(get_token_limit_kwargs(llm_cfg.model, 2000))

        markdown = await llm_complete(
            prompt=user_prompt,
            system_prompt=system_prompt,
            model=llm_cfg.model,
            api_key=llm_cfg.api_key,
            base_url=llm_cfg.base_url,
            **kwargs,
        )

        return {
            "markdown": (markdown or "").strip(),
            "used_sources": used_sources,
            "skipped_sources": skipped_sources,
        }

    async def generate_style_prompt(
        self, sources: List[Dict[str, Any]], topic: Optional[str] = None
    ) -> Dict[str, Any]:
        result = await self._collect_sources(sources, topic)
        compiled_sources = result["compiled_sources"]

        system_prompt = (
            "You are a presentation designer. Create a short style brief for a slide deck "
            "based on the provided sources. Focus on tone, color palette, and layout feel. "
            "Output 2-4 sentences, plain text only."
        )
        topic_line = f"Topic: {topic}\n\n" if topic else ""
        user_prompt = (
            f"{topic_line}"
            "Sources:\n"
            f"{chr(10).join(compiled_sources)}\n\n"
            "Return only the style brief."
        )

        llm_cfg = get_llm_config()
        kwargs = {"temperature": 0.5}
        kwargs.update(get_token_limit_kwargs(llm_cfg.model, 600))

        style_prompt = await llm_complete(
            prompt=user_prompt,
            system_prompt=system_prompt,
            model=llm_cfg.model,
            api_key=llm_cfg.api_key,
            base_url=llm_cfg.base_url,
            **kwargs,
        )

        return {
            "style_prompt": (style_prompt or "").strip(),
            "used_sources": result["used_sources"],
            "skipped_sources": result["skipped_sources"],
        }

    def _fetch_web_content(self, url: str) -> str:
        headers = {"User-Agent": "DeepTutor/1.0"}
        resp = requests.get(url, headers=headers, timeout=self.request_timeout)
        resp.raise_for_status()
        text = resp.text or ""

        text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\\1>", " ", text)
        text = re.sub(r"(?is)<[^>]+>", " ", text)
        text = html.unescape(text)
        text = re.sub(r"\\s+", " ", text).strip()

        return text

    async def _fetch_kb_summary(self, kb_name: str, topic: Optional[str]) -> str:
        query = topic or f"Summarize the key points in knowledge base: {kb_name}."
        rag = RAGService()
        result = await rag.search(query=query, kb_name=kb_name, mode="hybrid")
        return result.get("answer") or result.get("content") or ""
