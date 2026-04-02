"""
RAGAnything Pipeline
====================

End-to-end pipeline wrapping RAG-Anything for academic document processing.
"""

import json
from pathlib import Path
import re
import sys
from typing import Any, Awaitable, Callable, Dict, List, Optional

from src.logging import get_logger
from src.logging.adapters import LightRAGLogContext
from src.services.llm.config import supports_response_format_json_object

_KEYWORD_EXTRACTION_JSON_INSTRUCTION = """
Return a single valid JSON object only. Do not use markdown fences.
Use exactly this schema:
{
  "high_level_keywords": ["keyword1", "keyword2"],
  "low_level_keywords": ["keyword1", "keyword2"]
}
Do not include any explanation before or after the JSON.
""".strip()


def _extract_json_payload(text: str) -> Any | None:
    """Extract JSON payload from raw model text or fenced code blocks."""
    if not text:
        return None

    candidates: list[str] = [text.strip()]

    fenced_blocks = re.findall(r"```(?:json)?\s*([\s\S]*?)\s*```", text, flags=re.IGNORECASE)
    candidates.extend(block.strip() for block in fenced_blocks if block.strip())

    for open_char, close_char in (("{", "}"), ("[", "]")):
        start = text.find(open_char)
        end = text.rfind(close_char)
        if start != -1 and end != -1 and end > start:
            snippet = text[start : end + 1].strip()
            if snippet:
                candidates.append(snippet)

    seen: set[str] = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return None


def _normalize_keyword_list(values: Any) -> list[str]:
    if isinstance(values, list):
        return [str(value).strip() for value in values if str(value).strip()]
    if values is None:
        return []
    value = str(values).strip()
    return [value] if value else []


def _coerce_keyword_extraction_response(text: str) -> str:
    """Normalize keyword extraction output into the JSON string LightRAG expects."""
    payload = _extract_json_payload(text)
    if not isinstance(payload, dict):
        payload = {}

    normalized = {
        "high_level_keywords": _normalize_keyword_list(payload.get("high_level_keywords")),
        "low_level_keywords": _normalize_keyword_list(payload.get("low_level_keywords")),
    }
    return json.dumps(normalized, ensure_ascii=False)


def _wrap_keyword_extraction_for_unsupported_models(
    llm_call: Callable[..., Awaitable[str]],
    *,
    model: str,
    base_url: str | None,
    logger,
) -> Callable[..., Awaitable[str]]:
    """
    Fall back to plain-text JSON prompting when the model rejects OpenAI structured output.
    """
    supports_json_mode = supports_response_format_json_object(
        model=model,
        base_url=base_url,
    )

    if supports_json_mode:
        return llm_call

    async def wrapped(
        prompt: str,
        system_prompt: str | None = None,
        history_messages: list[dict[str, Any]] | None = None,
        **kwargs,
    ) -> str:
        keyword_extraction = kwargs.pop("keyword_extraction", False)
        if not keyword_extraction:
            return await llm_call(
                prompt,
                system_prompt=system_prompt,
                history_messages=history_messages,
                **kwargs,
            )

        combined_system_prompt = (
            f"{system_prompt}\n\n{_KEYWORD_EXTRACTION_JSON_INSTRUCTION}"
            if system_prompt
            else _KEYWORD_EXTRACTION_JSON_INSTRUCTION
        )
        prompt_with_json_guard = (
            f"{prompt.rstrip()}\n\nIMPORTANT: {_KEYWORD_EXTRACTION_JSON_INSTRUCTION}"
        )

        logger.info(
            "Model does not support structured response_format during keyword extraction; "
            "falling back to plain-text JSON prompting"
        )

        response = await llm_call(
            prompt_with_json_guard,
            system_prompt=combined_system_prompt,
            history_messages=history_messages,
            **kwargs,
        )
        return _coerce_keyword_extraction_response(response)

    return wrapped


class RAGAnythingPipeline:
    """
    RAG-Anything end-to-end Pipeline.

    Uses RAG-Anything's complete processing:
    - MinerU PDF parsing (multimodal: images, tables, equations)
    - LightRAG knowledge graph construction
    - Hybrid retrieval (hybrid/local/global/naive modes)

    This is a "monolithic" pipeline - best for academic documents.
    """

    name = "raganything"

    def __init__(
        self,
        kb_base_dir: Optional[str] = None,
        enable_image_processing: bool = True,
        enable_table_processing: bool = True,
        enable_equation_processing: bool = True,
    ):
        """
        Initialize RAGAnything pipeline.

        Args:
            kb_base_dir: Base directory for knowledge bases
            enable_image_processing: Enable image extraction and processing
            enable_table_processing: Enable table extraction and processing
            enable_equation_processing: Enable equation extraction and processing
        """
        self.logger = get_logger("RAGAnythingPipeline")
        self.kb_base_dir = kb_base_dir or str(
            Path(__file__).resolve().parent.parent.parent.parent.parent / "data" / "knowledge_bases"
        )
        self.enable_image = enable_image_processing
        self.enable_table = enable_table_processing
        self.enable_equation = enable_equation_processing
        self._instances: Dict[str, Any] = {}

    def _setup_raganything_path(self):
        """Add RAG-Anything to sys.path if available."""
        project_root = Path(__file__).resolve().parent.parent.parent.parent.parent
        raganything_path = project_root.parent / "raganything" / "RAG-Anything"
        if raganything_path.exists() and str(raganything_path) not in sys.path:
            sys.path.insert(0, str(raganything_path))

    def _get_rag_instance(self, kb_name: str):
        """Get or create RAGAnything instance."""
        kb_dir = Path(self.kb_base_dir) / kb_name
        working_dir = str(kb_dir / "rag_storage")

        if working_dir in self._instances:
            return self._instances[working_dir]

        self._setup_raganything_path()

        from lightrag.llm.openai import openai_complete_if_cache
        from raganything import RAGAnything, RAGAnythingConfig

        from src.services.embedding import get_embedding_client
        from src.services.llm import get_llm_client

        llm_client = get_llm_client()
        embed_client = get_embedding_client()

        async def _base_llm_model_func(
            prompt, system_prompt=None, history_messages=None, **kwargs
        ):
            return await openai_complete_if_cache(
                llm_client.config.model,
                prompt,
                system_prompt=system_prompt,
                history_messages=history_messages or [],
                api_key=llm_client.config.api_key,
                base_url=llm_client.config.base_url,
                **kwargs,
            )

        llm_model_func = _wrap_keyword_extraction_for_unsupported_models(
            _base_llm_model_func,
            model=llm_client.config.model,
            base_url=llm_client.config.base_url,
            logger=self.logger,
        )

        async def vision_model_func(
            prompt,
            system_prompt=None,
            history_messages=None,
            image_data=None,
            messages=None,
            **kwargs,
        ):
            # Handle multimodal messages
            if messages:
                clean_kwargs = {
                    k: v
                    for k, v in kwargs.items()
                    if k not in ["messages", "prompt", "system_prompt", "history_messages"]
                }
                return await openai_complete_if_cache(
                    llm_client.config.model,
                    prompt="",
                    messages=messages,
                    api_key=llm_client.config.api_key,
                    base_url=llm_client.config.base_url,
                    **clean_kwargs,
                )
            if image_data:
                # Build image message
                image_message = {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{image_data}"},
                        },
                    ],
                }
                return await openai_complete_if_cache(
                    llm_client.config.model,
                    prompt="",
                    messages=[image_message],
                    api_key=llm_client.config.api_key,
                    base_url=llm_client.config.base_url,
                    **kwargs,
                )
            return await llm_model_func(
                prompt,
                system_prompt=system_prompt,
                history_messages=history_messages,
                **kwargs,
            )

        config = RAGAnythingConfig(
            working_dir=working_dir,
            enable_image_processing=self.enable_image,
            enable_table_processing=self.enable_table,
            enable_equation_processing=self.enable_equation,
        )

        rag = RAGAnything(
            config=config,
            llm_model_func=llm_model_func,
            vision_model_func=vision_model_func,
            embedding_func=embed_client.get_embedding_func(),
        )

        self._instances[working_dir] = rag
        return rag

    async def initialize(
        self,
        kb_name: str,
        file_paths: List[str],
        extract_numbered_items: bool = True,
        **kwargs,
    ) -> bool:
        """
        Initialize KB using RAG-Anything's process_document_complete().

        Args:
            kb_name: Knowledge base name
            file_paths: List of file paths to process
            extract_numbered_items: Whether to extract numbered items after processing
            **kwargs: Additional arguments

        Returns:
            True if successful
        """
        self.logger.info(f"Initializing KB '{kb_name}' with {len(file_paths)} files")

        kb_dir = Path(self.kb_base_dir) / kb_name
        content_list_dir = kb_dir / "content_list"
        content_list_dir.mkdir(parents=True, exist_ok=True)

        with LightRAGLogContext(scene="knowledge_init"):
            rag = self._get_rag_instance(kb_name)
            await rag._ensure_lightrag_initialized()

            for idx, file_path in enumerate(file_paths, 1):
                self.logger.info(f"Processing [{idx}/{len(file_paths)}]: {Path(file_path).name}")
                await rag.process_document_complete(
                    file_path=file_path,
                    output_dir=str(content_list_dir),
                    parse_method="auto",
                )

        if extract_numbered_items:
            await self._extract_numbered_items(kb_name)

        self.logger.info(f"KB '{kb_name}' initialized successfully")
        return True

    async def _extract_numbered_items(self, kb_name: str):
        """Extract numbered items using existing extraction logic."""
        try:
            import json

            from src.knowledge.extract_numbered_items import (
                extract_numbered_items_with_llm_async,
            )
            from src.services.llm import get_llm_client

            kb_dir = Path(self.kb_base_dir) / kb_name
            content_list_dir = kb_dir / "content_list"

            if not content_list_dir.exists():
                self.logger.warning("No content_list directory found, skipping extraction")
                return

            # Load all content list files
            all_content_items = []
            for json_file in content_list_dir.glob("*.json"):
                with open(json_file, "r", encoding="utf-8") as f:
                    content_items = json.load(f)
                    all_content_items.extend(content_items)

            if not all_content_items:
                self.logger.warning("No content items found for extraction")
                return

            self.logger.info(
                f"Extracting numbered items from {len(all_content_items)} content items"
            )

            llm_client = get_llm_client()
            items = await extract_numbered_items_with_llm_async(
                all_content_items,
                api_key=llm_client.config.api_key,
                base_url=llm_client.config.base_url,
            )

            # Save numbered items
            if items:
                output_file = kb_dir / "numbered_items.json"
                with open(output_file, "w", encoding="utf-8") as f:
                    json.dump(items, f, ensure_ascii=False, indent=2)
                self.logger.info(f"Extracted {len(items)} numbered items")

        except ImportError as e:
            self.logger.warning(f"Could not import extraction module: {e}")
        except Exception as e:
            self.logger.error(f"Failed to extract numbered items: {e}")

    async def search(
        self,
        query: str,
        kb_name: str,
        mode: str = "hybrid",
        only_need_context: bool = False,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Search using RAG-Anything's aquery().

        Args:
            query: Search query
            kb_name: Knowledge base name
            mode: Search mode (hybrid, local, global, naive)
            only_need_context: Whether to only return context without answer
            **kwargs: Additional arguments

        Returns:
            Search results dictionary
        """
        with LightRAGLogContext(scene="rag_search"):
            rag = self._get_rag_instance(kb_name)
            await rag._ensure_lightrag_initialized()

            try:
                answer = await rag.aquery(query, mode=mode, only_need_context=only_need_context)
            except TypeError as exc:
                if "expected string or bytes-like object" not in str(exc) or "NoneType" not in str(
                    exc
                ):
                    raise

                self.logger.warning(
                    "VLM-enhanced RAG query returned an invalid prompt; retrying without VLM enhancement"
                )
                answer = await rag.aquery(
                    query,
                    mode=mode,
                    only_need_context=only_need_context,
                    vlm_enhanced=False,
                )
            answer_str = answer if isinstance(answer, str) else str(answer)

            return {
                "query": query,
                "answer": answer_str,
                "content": answer_str,
                "mode": mode,
                "provider": "raganything",
            }

    async def delete(self, kb_name: str) -> bool:
        """
        Delete knowledge base.

        Args:
            kb_name: Knowledge base name

        Returns:
            True if successful
        """
        import shutil

        kb_dir = Path(self.kb_base_dir) / kb_name
        working_dir = str(kb_dir / "rag_storage")

        # Remove from cache
        if working_dir in self._instances:
            del self._instances[working_dir]

        # Delete directory
        if kb_dir.exists():
            shutil.rmtree(kb_dir)
            self.logger.info(f"Deleted KB '{kb_name}'")
            return True

        return False
