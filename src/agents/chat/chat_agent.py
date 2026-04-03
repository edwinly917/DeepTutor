#!/usr/bin/env python
"""
ChatAgent - Lightweight conversational AI with multi-turn support.

This agent provides:
- Multi-turn conversation with history management
- Token-based context truncation
- Optional RAG and Web Search augmentation
- Streaming response generation

Uses the unified LLM factory from BaseAgent for both cloud and local LLM support.
"""

import asyncio
from pathlib import Path
import re
import sys
from typing import Any, AsyncGenerator

# Add project root to path
_project_root = Path(__file__).parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from src.agents.base_agent import BaseAgent
from src.tools import rag_search, web_search


class ChatAgent(BaseAgent):
    """
    Lightweight conversational agent with multi-turn support.

    Features:
    - Conversation history management with token limits
    - RAG (Retrieval-Augmented Generation) support
    - Web search integration
    - Streaming response generation via BaseAgent.stream_llm()
    """

    # Default token limit for conversation history
    DEFAULT_MAX_HISTORY_TOKENS = 32000

    def __init__(
        self,
        language: str = "zh",
        config: dict[str, Any] | None = None,
        max_history_tokens: int | None = None,
        **kwargs,
    ):
        """
        Initialize ChatAgent.

        Args:
            language: Language setting ('zh' | 'en')
            config: Optional configuration dictionary
            max_history_tokens: Maximum tokens for conversation history
            **kwargs: Additional arguments passed to BaseAgent
        """
        super().__init__(
            module_name="chat",
            agent_name="chat_agent",
            language=language,
            config=config,
            **kwargs,
        )

        # Configure history token limit
        self.max_history_tokens = max_history_tokens or self.agent_config.get(
            "max_history_tokens", self.DEFAULT_MAX_HISTORY_TOKENS
        )

        self.logger.info(f"ChatAgent initialized: model={self.model}, base_url={self.base_url}")

    def count_tokens(self, text: str) -> int:
        """
        Count tokens in text using tiktoken.

        Falls back to character-based estimation if tiktoken unavailable.

        Args:
            text: Text to count tokens for

        Returns:
            Estimated token count
        """
        try:
            import tiktoken

            # Use cl100k_base encoding (GPT-4, GPT-3.5-turbo)
            encoding = tiktoken.get_encoding("cl100k_base")
            return len(encoding.encode(text))
        except ImportError:
            # Fallback: rough estimate of 4 characters per token
            return len(text) // 4

    def truncate_history(
        self,
        history: list[dict[str, str]],
        max_tokens: int | None = None,
    ) -> list[dict[str, str]]:
        """
        Truncate conversation history to fit within token limit.

        Keeps the most recent messages, discarding older ones first.

        Args:
            history: List of message dicts with 'role' and 'content'
            max_tokens: Maximum tokens allowed (uses default if None)

        Returns:
            Truncated history list
        """
        max_tokens = max_tokens or self.max_history_tokens

        if not history:
            return []

        # Calculate tokens for each message
        message_tokens = []
        for msg in history:
            content = msg.get("content", "")
            tokens = self.count_tokens(content)
            message_tokens.append((msg, tokens))

        # Build history from newest to oldest, stop when limit reached
        truncated = []
        total_tokens = 0

        for msg, tokens in reversed(message_tokens):
            if total_tokens + tokens > max_tokens:
                break
            truncated.insert(0, msg)
            total_tokens += tokens

        if len(truncated) < len(history):
            self.logger.info(
                f"Truncated history from {len(history)} to {len(truncated)} messages "
                f"({total_tokens} tokens)"
            )

        return truncated

    def _extract_research_reports_from_history(self, history: list[dict[str, str]]) -> str:
        """
        Extract research reports from conversation history.

        Looks for assistant messages containing research reports (marked with specific patterns).

        Args:
            history: Conversation history

        Returns:
            Extracted report content as string
        """
        reports = []
        for msg in history:
            if msg.get("role") != "assistant":
                continue

            content = msg.get("content", "")

            # Check for research report markers
            if "📚 深度研究完成" in content or "# 深度研究报告" in content:
                # Extract the report content, removing the banner
                lines = content.split("\n")
                report_lines = []
                skip_banner = False

                for line in lines:
                    # Skip the completion banner
                    if "📚 深度研究完成" in line or "深度研究完成" in line:
                        skip_banner = True
                        continue
                    if skip_banner and not line.strip():
                        skip_banner = False
                        continue
                    if not skip_banner:
                        report_lines.append(line)

                report_content = "\n".join(report_lines).strip()
                if report_content:
                    reports.append(report_content)

        if reports:
            combined = "\n\n---\n\n".join(reports)
            return f"[Conversation History - Research Reports]\n{combined}"

        return ""

    def format_history_for_prompt(self, history: list[dict[str, str]]) -> str:
        """
        Format conversation history as a string for the prompt.

        Args:
            history: List of message dicts

        Returns:
            Formatted history string
        """
        if not history:
            return ""

        lines = []
        for msg in history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            prefix = "User" if role == "user" else "Assistant"
            lines.append(f"{prefix}: {content}")

        return "\n\n".join(lines)

    def _format_source_catalog_context(self, source_catalog: list[dict[str, Any]] | None) -> str:
        """
        Build a numbered reference index for strict notebook citations.

        Args:
            source_catalog: List of source entries with ref_number/title/url

        Returns:
            Formatted reference index block
        """
        if not source_catalog:
            return ""

        lines = [
            "[Reference Index]",
            "The following numbered references are available for citation:",
        ]

        count = 0
        for item in source_catalog:
            if not isinstance(item, dict):
                continue
            ref = item.get("ref_number")
            title = (item.get("title") or "").strip()
            url = (item.get("url") or "").strip()
            if not isinstance(ref, int) or ref <= 0:
                continue
            if not title:
                title = f"Reference {ref}"
            if url:
                lines.append(f"[{ref}] {title} - {url}")
            else:
                lines.append(f"[{ref}] {title}")
            count += 1
            if count >= 80:
                break

        if count == 0:
            return ""

        lines.append("When you cite, ONLY use bracket numbers from this index, e.g. [1], [2].")
        return "\n".join(lines)

    def _normalize_selected_source_refs(
        self, selected_source_refs: list[dict[str, Any]] | None
    ) -> list[dict[str, Any]]:
        if not selected_source_refs:
            return []

        normalized_refs = []
        for raw in selected_source_refs:
            if not isinstance(raw, dict):
                continue

            source_type = (raw.get("type") or "").strip().lower() or "web"
            if source_type not in {"web", "file", "kb", "report", "paper"}:
                source_type = "web"

            ref_number = raw.get("ref_number")
            if isinstance(ref_number, str) and ref_number.isdigit():
                ref_number = int(ref_number)
            if not isinstance(ref_number, int) or ref_number <= 0:
                ref_number = None

            normalized_refs.append(
                {
                    "id": (raw.get("id") or "").strip(),
                    "type": source_type,
                    "title": (raw.get("title") or "").strip(),
                    "url": (raw.get("url") or "").strip(),
                    "content": (raw.get("content") or "").strip(),
                    "selected": raw.get("selected", True) is not False,
                    "source_key": (raw.get("source_key") or "").strip(),
                    "ref_number": ref_number,
                    "kb_name": (raw.get("kb_name") or "").strip(),
                    "source_file": (raw.get("source_file") or "").strip(),
                    "chunk_id": (raw.get("chunk_id") or "").strip(),
                    "page": raw.get("page"),
                }
            )

        return normalized_refs

    def _extract_selected_kb_reference_context(
        self, selected_source_refs: list[dict[str, Any]] | None
    ) -> tuple[str, list[dict[str, Any]], list[str]]:
        normalized_refs = self._normalize_selected_source_refs(selected_source_refs)
        if not normalized_refs:
            return "", [], []

        context_blocks: list[str] = []
        sources: list[dict[str, Any]] = []
        referenced_kbs: list[str] = []
        seen_context_keys: set[str] = set()
        seen_kbs: set[str] = set()

        for source in normalized_refs:
            if not source.get("selected", True):
                continue

            kb_name = source.get("kb_name") or ""
            if source.get("type") == "kb" and kb_name and kb_name not in seen_kbs:
                referenced_kbs.append(kb_name)
                seen_kbs.add(kb_name)

            snippet = (source.get("content") or "").strip()
            if source.get("type") != "kb" or not kb_name or not snippet:
                continue

            location_parts = []
            if source.get("source_file"):
                location_parts.append(f"File: {source['source_file']}")
            if source.get("page") not in (None, ""):
                location_parts.append(f"Page: {source['page']}")
            if source.get("chunk_id"):
                location_parts.append(f"Chunk: {source['chunk_id']}")
            location = " | ".join(location_parts)

            context_key = (
                source.get("source_key")
                or f"{kb_name}|{source.get('source_file') or ''}|{source.get('page') or ''}|"
                f"{source.get('chunk_id') or ''}|{source.get('title') or ''}"
            )
            if context_key in seen_context_keys:
                continue
            seen_context_keys.add(context_key)

            lines = ["[Selected Knowledge Base Reference]", f"Knowledge Base: {kb_name}"]
            if source.get("title"):
                lines.append(f"Title: {source['title']}")
            if location:
                lines.append(location)
            if source.get("ref_number"):
                lines.append(f"Reference Number: [{source['ref_number']}]")
            lines.append("Excerpt:")
            lines.append(snippet)
            context_blocks.append("\n".join(lines))

            source_entry = {
                "kb_name": kb_name,
                "title": source.get("title") or source.get("source_file") or kb_name,
                "content": snippet[:500] + "..." if len(snippet) > 500 else snippet,
            }
            if source.get("source_file"):
                source_entry["source_file"] = source["source_file"]
            if source.get("page") not in (None, ""):
                source_entry["page"] = source["page"]
            if source.get("chunk_id"):
                source_entry["chunk_id"] = source["chunk_id"]
            if source.get("source_key"):
                source_entry["source_key"] = source["source_key"]
            if source.get("ref_number"):
                source_entry["ref_number"] = source["ref_number"]
            sources.append(source_entry)

        return "\n\n".join(context_blocks), sources, referenced_kbs

    def _normalize_text_for_match(self, text: str | None) -> str:
        return re.sub(r"\s+", "", (text or "")).strip().lower()

    def _normalize_file_basename(self, path_value: str | None) -> str:
        value = (path_value or "").strip()
        if not value:
            return ""
        return Path(value).name.strip().lower()

    def _score_chunk_against_selected_ref(
        self, chunk: dict[str, Any], selected_ref: dict[str, Any]
    ) -> int:
        chunk_id = str(chunk.get("chunk_id") or "").strip()
        chunk_file_name = self._normalize_file_basename(chunk.get("file_path"))
        chunk_content = self._normalize_text_for_match(chunk.get("content"))

        ref_chunk_id = str(selected_ref.get("chunk_id") or "").strip()
        ref_file_name = self._normalize_file_basename(selected_ref.get("source_file"))
        ref_content = self._normalize_text_for_match(selected_ref.get("content"))

        score = 0

        if ref_chunk_id:
            if chunk_id != ref_chunk_id:
                return -1
            score += 100

        if ref_file_name:
            if chunk_file_name != ref_file_name:
                if ref_chunk_id:
                    return -1
            else:
                score += 50

        if ref_content and chunk_content:
            if ref_content in chunk_content or chunk_content in ref_content:
                score += 30
            elif ref_chunk_id:
                return -1

        if ref_chunk_id:
            return score if score >= 100 else -1
        if ref_file_name:
            return score if score >= 50 else -1
        return -1

    def _match_selected_kb_chunks(
        self,
        structured_chunks: list[dict[str, Any]],
        selected_refs: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        matched_chunks: list[dict[str, Any]] = []
        seen_chunk_keys: set[str] = set()

        for chunk in structured_chunks:
            if not isinstance(chunk, dict):
                continue

            best_ref: dict[str, Any] | None = None
            best_score = -1
            for selected_ref in selected_refs:
                score = self._score_chunk_against_selected_ref(chunk, selected_ref)
                if score > best_score:
                    best_score = score
                    best_ref = selected_ref

            if not best_ref or best_score < 0:
                continue

            chunk_key = (
                f"{self._normalize_file_basename(chunk.get('file_path'))}|"
                f"{str(chunk.get('chunk_id') or '').strip()}"
            )
            if chunk_key in seen_chunk_keys:
                continue
            seen_chunk_keys.add(chunk_key)
            matched_chunks.append(
                {
                    "chunk": chunk,
                    "selected_ref": best_ref,
                    "score": best_score,
                }
            )

        return matched_chunks

    async def _retrieve_precise_selected_kb_context(
        self,
        message: str,
        selected_source_refs: list[dict[str, Any]] | None,
    ) -> tuple[str, list[dict[str, Any]], set[str], list[str]]:
        normalized_refs = self._normalize_selected_source_refs(selected_source_refs)
        refs_by_kb: dict[str, list[dict[str, Any]]] = {}

        for selected_ref in normalized_refs:
            if not selected_ref.get("selected", True):
                continue
            if selected_ref.get("type") != "kb":
                continue

            kb_name = selected_ref.get("kb_name") or ""
            if not kb_name:
                continue
            if not selected_ref.get("chunk_id") and not selected_ref.get("source_file"):
                continue

            refs_by_kb.setdefault(kb_name, []).append(selected_ref)

        if not refs_by_kb:
            return "", [], set(), []

        context_blocks: list[str] = []
        sources: list[dict[str, Any]] = []
        matched_kbs: set[str] = set()
        exceptions: list[str] = []

        for kb_name, kb_refs in refs_by_kb.items():
            try:
                self.logger.info(
                    f"Referenced KB precise search: {kb_name} ({message[:50]}...)"
                )
                precise_result = await asyncio.wait_for(
                    rag_search(
                        query=message,
                        kb_name=kb_name,
                        mode="hybrid",
                        only_need_context=True,
                        return_raw_data=True,
                    ),
                    timeout=120,
                )
                raw_data = precise_result.get("raw_data") or {}
                structured_chunks = ((raw_data.get("data") or {}).get("chunks") or [])
                matched_chunks = self._match_selected_kb_chunks(structured_chunks, kb_refs)
                if not matched_chunks:
                    continue

                matched_kbs.add(kb_name)

                for matched in matched_chunks:
                    chunk = matched["chunk"]
                    selected_ref = matched["selected_ref"]
                    file_path = (chunk.get("file_path") or "").strip()
                    chunk_file_name = Path(file_path).name if file_path else ""
                    chunk_id = str(chunk.get("chunk_id") or "").strip()
                    chunk_content = (chunk.get("content") or "").strip()
                    if not chunk_content:
                        continue

                    lines = ["[Selected Knowledge Base Exact Match]", f"Knowledge Base: {kb_name}"]
                    title = selected_ref.get("title") or chunk_file_name or kb_name
                    if title:
                        lines.append(f"Title: {title}")

                    location_parts = []
                    if chunk_file_name:
                        location_parts.append(f"File: {chunk_file_name}")
                    if selected_ref.get("page") not in (None, ""):
                        location_parts.append(f"Page: {selected_ref['page']}")
                    if chunk_id:
                        location_parts.append(f"Chunk: {chunk_id}")
                    if location_parts:
                        lines.append(" | ".join(location_parts))
                    if selected_ref.get("ref_number"):
                        lines.append(f"Reference Number: [{selected_ref['ref_number']}]")
                    lines.append("Excerpt:")
                    lines.append(chunk_content)
                    context_blocks.append("\n".join(lines))

                    source_entry = {
                        "kb_name": kb_name,
                        "title": title,
                        "content": chunk_content[:500] + "..."
                        if len(chunk_content) > 500
                        else chunk_content,
                    }
                    if chunk_file_name:
                        source_entry["source_file"] = chunk_file_name
                    if selected_ref.get("page") not in (None, ""):
                        source_entry["page"] = selected_ref["page"]
                    if chunk_id:
                        source_entry["chunk_id"] = chunk_id
                    if selected_ref.get("source_key"):
                        source_entry["source_key"] = selected_ref["source_key"]
                    if selected_ref.get("ref_number"):
                        source_entry["ref_number"] = selected_ref["ref_number"]
                    sources.append(source_entry)
            except asyncio.TimeoutError:
                self.logger.warning(
                    f"Referenced KB precise search timed out after 120s: {kb_name}"
                )
                exceptions.append(f"来源知识库精确检索超时: {kb_name} (120s)")
            except Exception as e:
                self.logger.warning(f"Referenced KB precise search failed ({kb_name}): {e}")
                exceptions.append(f"来源知识库精确检索异常: {kb_name}: {str(e)}")

        return "\n\n".join(context_blocks), sources, matched_kbs, exceptions

    async def retrieve_context(
        self,
        message: str,
        kb_name: str | None = None,
        sources_kb_name: str | None = None,
        selected_source_refs: list[dict[str, Any]] | None = None,
        enable_rag: bool = False,
        enable_web_search: bool = False,
    ) -> tuple[str, dict[str, Any], list[str]]:
        """
        Retrieve context from RAG and/or Web Search.

        Args:
            message: User message to search for
            kb_name: Knowledge base name for RAG
            sources_kb_name: Knowledge base name for selected sources
            selected_source_refs: Selected source references from the notebook UI
            enable_rag: Whether to use RAG
            enable_web_search: Whether to use Web Search

        Returns:
            Tuple of (context_string, sources_dict, exceptions_list)
        """
        context_parts = []
        sources = {"rag": [], "web": []}
        exceptions = []
        normalized_selected_refs = self._normalize_selected_source_refs(selected_source_refs)
        selected_ref_context, selected_ref_sources, referenced_kb_names = (
            self._extract_selected_kb_reference_context(normalized_selected_refs)
        )
        precise_ref_context, precise_ref_sources, precise_ref_hit_kbs, precise_ref_exceptions = (
            await self._retrieve_precise_selected_kb_context(
                message,
                normalized_selected_refs,
            )
        )

        if selected_ref_context:
            context_parts.append(selected_ref_context)
        if selected_ref_sources:
            sources["rag"].extend(selected_ref_sources)
        if precise_ref_context:
            context_parts.append(precise_ref_context)
        if precise_ref_sources:
            sources["rag"].extend(precise_ref_sources)
        if precise_ref_exceptions:
            exceptions.extend(precise_ref_exceptions)

        # RAG retrieval
        if enable_rag and kb_name:
            try:
                self.logger.info(f"RAG search: {message[:50]}...")
                rag_result = await asyncio.wait_for(
                    rag_search(
                        query=message,
                        kb_name=kb_name,
                        mode="hybrid",
                    ),
                    timeout=120,
                )
                rag_answer = rag_result.get("answer", "")
                if rag_answer:
                    context_parts.append(f"[Knowledge Base: {kb_name}]\n{rag_answer}")
                    sources["rag"].append(
                        {
                            "kb_name": kb_name,
                            "content": rag_answer[:500] + "..."
                            if len(rag_answer) > 500
                            else rag_answer,
                        }
                    )
                    self.logger.info(f"RAG retrieved {len(rag_answer)} chars")
            except asyncio.TimeoutError:
                self.logger.warning("RAG search timed out after 120s, skipping")
                exceptions.append("知识库检索超时: 120s")
            except Exception as e:
                self.logger.warning(f"RAG search failed: {e}")
                exceptions.append(f"知识库检索异常: {str(e)}")

        # Referenced KB retrieval for selected knowledge-base sources.
        for referenced_kb_name in referenced_kb_names:
            if not referenced_kb_name:
                continue
            if enable_rag and kb_name and referenced_kb_name == kb_name:
                continue
            if sources_kb_name and referenced_kb_name == sources_kb_name:
                continue
            if referenced_kb_name in precise_ref_hit_kbs:
                continue

            try:
                self.logger.info(f"Referenced KB search: {referenced_kb_name} ({message[:50]}...)")
                ref_result = await asyncio.wait_for(
                    rag_search(
                        query=message,
                        kb_name=referenced_kb_name,
                        mode="hybrid",
                    ),
                    timeout=120,
                )
                ref_answer = ref_result.get("answer", "")
                if ref_answer:
                    context_parts.append(f"[Referenced Knowledge Base: {referenced_kb_name}]\n{ref_answer}")
                    sources["rag"].append(
                        {
                            "kb_name": referenced_kb_name,
                            "title": referenced_kb_name,
                            "content": ref_answer[:500] + "..."
                            if len(ref_answer) > 500
                            else ref_answer,
                        }
                    )
                    self.logger.info(
                        f"Referenced KB '{referenced_kb_name}' retrieved {len(ref_answer)} chars"
                    )
            except asyncio.TimeoutError:
                self.logger.warning(
                    f"Referenced KB search timed out after 120s: {referenced_kb_name}"
                )
                exceptions.append(f"来源知识库检索超时: {referenced_kb_name} (120s)")
            except Exception as e:
                self.logger.warning(f"Referenced KB search failed ({referenced_kb_name}): {e}")
                exceptions.append(f"来源知识库检索异常: {referenced_kb_name}: {str(e)}")

        # Selected sources KB retrieval (always-on if provided)
        if sources_kb_name and sources_kb_name != kb_name:
            try:
                self.logger.info(f"Sources KB search: {message[:50]}...")
                sources_result = await asyncio.wait_for(
                    rag_search(
                        query=message,
                        kb_name=sources_kb_name,
                        mode="hybrid",
                    ),
                    timeout=120,
                )
                sources_answer = sources_result.get("answer", "")
                if sources_answer:
                    context_parts.append(f"[Selected Sources]\n{sources_answer}")
                    sources["rag"].append(
                        {
                            "kb_name": sources_kb_name,
                            "content": sources_answer[:500] + "..."
                            if len(sources_answer) > 500
                            else sources_answer,
                        }
                    )
                    self.logger.info(f"Sources KB retrieved {len(sources_answer)} chars")
            except asyncio.TimeoutError:
                self.logger.warning("Sources KB search timed out after 120s, skipping")
                exceptions.append("来源检索超时: 120s")
            except Exception as e:
                self.logger.warning(f"Sources KB search failed: {e}")
                exceptions.append(f"来源检索异常: {str(e)}")

        # Web search
        if enable_web_search:
            try:
                self.logger.info(f"Web search: {message[:50]}...")
                web_result = web_search(query=message, verbose=False)
                web_answer = web_result.get("answer", "")
                web_citations = web_result.get("citations", [])

                if web_answer:
                    context_parts.append(f"[Web Search Results]\n{web_answer}")
                    sources["web"] = web_citations[:5]
                    self.logger.info(
                        f"Web search returned {len(web_answer)} chars, "
                        f"{len(web_citations)} citations"
                    )
                elif web_citations:
                    # Fallback for providers that don't return an 'answer' (like volcengine)
                    # Construct a combined context from snippets
                    self.logger.info(
                        f"Web search answer empty, using {len(web_citations)} citations as context"
                    )
                    snippet_parts = []
                    for i, cit in enumerate(web_citations[:10], 1):
                        snippet = cit.get("snippet", "")
                        title = cit.get("title", "")
                        if snippet:
                            snippet_parts.append(f"Source [{i}] ({title}): {snippet}")

                    if snippet_parts:
                        combined_snippets = "\n\n".join(snippet_parts)
                        context_parts.append(
                            f"[Web Search Results (Snippets)]\n{combined_snippets}"
                        )
                        sources["web"] = web_citations[:5]
                        self.logger.info(
                            f"Combined {len(snippet_parts)} snippets into context ({len(combined_snippets)} chars)"
                        )
            except Exception as e:
                self.logger.warning(f"Web search failed: {e}")
                exceptions.append(f"网络搜索异常: {str(e)}")

        context = "\n\n".join(context_parts)
        return context, sources, exceptions

    def build_messages(
        self,
        message: str,
        history: list[dict[str, str]],
        context: str = "",
        enable_rag: bool = False,
        enable_web_search: bool = False,
        require_sources: bool = False,
    ) -> list[dict[str, str]]:
        """
        Build the messages array for the LLM API call.

        Args:
            message: Current user message
            history: Truncated conversation history
            context: Retrieved context (RAG/Web)
            enable_rag: Whether RAG is enabled
            enable_web_search: Whether Web Search is enabled
            require_sources: Whether to enforce strict grounded QA (notebook mode)

        Returns:
            List of message dicts for OpenAI API
        """
        messages = []

        # Select system prompt based on mode
        if require_sources:
            # Notebook mode: use notebook-specific system prompt
            base_system_prompt = self.get_prompt(
                "notebook_system", "You are a knowledgeable AI assistant."
            )
        else:
            # Chat mode: use open chat system prompt
            base_system_prompt = self.get_prompt("system", "You are a knowledgeable AI assistant.")

        instructions = []
        if context:
            if require_sources:
                # Notebook mode: strict grounded QA — only answer from provided sources
                instructions.append(
                    "Answer the user's question based STRICTLY on the provided Reference Information."
                )
                instructions.append(
                    "Do NOT use your own internal knowledge to answer. You must only use the information present in the Reference Information."
                )
                instructions.append(
                    "If the answer is not found in the Reference Information, explicitly state that you cannot find the answer in the provided sources."
                )
                instructions.append("When citing, use plain [N] format only.")
                instructions.append("Do NOT output links like [N](#ref-N).")
                instructions.append('Do NOT output HTML anchors such as <a id="ref-N"></a>.')
            else:
                # Chat mode: use context as supplementary reference, not as strict constraint
                instructions.append(
                    "Reference Information is provided below for your consideration."
                )
                instructions.append(
                    "Use it to enhance your answer, but you may also draw on your own knowledge to provide a comprehensive response."
                )
                instructions.append(
                    "If the Reference Information is relevant, incorporate and cite it; if not, feel free to answer based on your own knowledge."
                )

            if enable_web_search:
                instructions.append("The Reference Information contains Web Search Results.")
                instructions.append(
                    "Please summarize these search results to provide a comprehensive and readable answer."
                )
                instructions.append("Do not just list links; synthesize the information.")

        # Combine instructions
        if instructions:
            system_prompt = f"{base_system_prompt}\n\nInstructions:\n" + "\n".join(
                f"- {i}" for i in instructions
            )
        else:
            system_prompt = base_system_prompt

        messages.append({"role": "system", "content": system_prompt})

        # Add context if available
        if context:
            context_template = self.get_prompt(
                "context_template", "Reference Information:\n{context}"
            )
            context_msg = context_template.format(context=context)
            messages.append({"role": "system", "content": context_msg})

        # Add conversation history
        for msg in history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role in ("user", "assistant"):
                messages.append({"role": role, "content": content})

        # Add current message
        messages.append({"role": "user", "content": message})

        return messages

    async def generate_stream(
        self,
        messages: list[dict[str, str]],
    ) -> AsyncGenerator[str, None]:
        """
        Generate streaming response from LLM.

        Uses BaseAgent.stream_llm() which routes to the appropriate provider
        (cloud or local) based on configuration.

        Args:
            messages: Messages array for OpenAI API

        Yields:
            Response chunks as strings
        """
        # Extract system prompt from messages
        system_prompt = ""
        user_prompt = ""
        for msg in messages:
            if msg.get("role") == "system":
                system_prompt = msg.get("content", "")
                break

        # Get the last user message as user_prompt (for logging/tracking)
        for msg in reversed(messages):
            if msg.get("role") == "user":
                user_prompt = msg.get("content", "")
                break

        # Use BaseAgent's stream_llm which routes through the factory
        async for chunk in self.stream_llm(
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            messages=messages,
            stage="chat_stream",
        ):
            yield chunk

    async def generate(self, messages: list[dict[str, str]]) -> str:
        """
        Generate complete response from LLM (non-streaming).

        Uses BaseAgent.call_llm() which routes to the appropriate provider
        (cloud or local) based on configuration.

        Args:
            messages: Messages array for OpenAI API

        Returns:
            Complete response string
        """
        # Extract system prompt from messages
        system_prompt = ""
        user_prompt = ""
        for msg in messages:
            if msg.get("role") == "system":
                system_prompt = msg.get("content", "")
                break

        # Get the last user message
        for msg in reversed(messages):
            if msg.get("role") == "user":
                user_prompt = msg.get("content", "")
                break

        # Use BaseAgent's call_llm which routes through the factory
        # Note: call_llm expects simple prompt/system_prompt, but for multi-turn
        # we need to use the factory directly with messages
        from src.services.llm import complete as llm_complete

        response = await llm_complete(
            prompt=user_prompt,
            system_prompt=system_prompt,
            model=self.get_model(),
            api_key=self.api_key,
            base_url=self.base_url,
            messages=messages,
            temperature=self.get_temperature(),
        )

        # Track token usage
        self._track_tokens(
            model=self.get_model(),
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response=response,
            stage="chat",
        )

        return response

    async def process(
        self,
        message: str,
        history: list[dict[str, str]] | None = None,
        kb_name: str | None = None,
        sources_kb_name: str | None = None,
        selected_source_refs: list[dict[str, Any]] | None = None,
        enable_rag: bool = False,
        enable_web_search: bool = False,
        require_sources: bool = False,
        source_catalog: list[dict[str, Any]] | None = None,
        stream: bool = False,
    ) -> dict[str, Any] | AsyncGenerator[dict[str, Any], None]:
        """
        Process a chat message with optional context retrieval.

        Args:
            message: User message
            history: Conversation history (will be truncated if needed)
            kb_name: Knowledge base name for RAG
            sources_kb_name: Knowledge base name for selected sources
            selected_source_refs: Selected source references from the notebook UI
            enable_rag: Whether to enable RAG retrieval
            enable_web_search: Whether to enable web search
            require_sources: Whether to require sources before answering
            source_catalog: Optional source index with stable ref_number mapping
            stream: Whether to stream the response

        Returns:
            If stream=False: Dict with 'response', 'sources', 'truncated_history'
            If stream=True: AsyncGenerator yielding chunks
        """
        history = history or []

        # Truncate history to fit token limit
        truncated_history = self.truncate_history(history)

        # Retrieve context if needed
        context, sources, exceptions = await self.retrieve_context(
            message=message,
            kb_name=kb_name,
            sources_kb_name=sources_kb_name,
            selected_source_refs=selected_source_refs,
            enable_rag=enable_rag,
            enable_web_search=enable_web_search,
        )

        # Add source catalog as an explicit numbered reference index for stable [N] citations.
        catalog_context = self._format_source_catalog_context(source_catalog)
        if catalog_context:
            if context:
                context = f"{context}\n\n{catalog_context}"
            else:
                context = catalog_context

        # Extract research reports from conversation history if available
        history_context = self._extract_research_reports_from_history(truncated_history)
        if history_context:
            if context:
                context = f"{context}\n\n{history_context}"
            else:
                context = history_context
            self.logger.info(
                f"Added {len(history_context)} chars from conversation history reports"
            )

        # Check if we should fail without sources
        # Strict Grounded QA Error Handling
        if require_sources:
            if exceptions and not context.strip():
                # If APIs failed and we have no context, explicitly fail
                self.logger.warning(f"Strict mode failed due to exceptions: {exceptions}")
                fallback = (
                    "检索服务发生异常，由于当前为严谨引用问答模式，暂无法为您解答。\n详细错误：\n"
                    + "\n".join([f"- {e}" for e in exceptions])
                )
                if stream:

                    async def stream_generator():
                        yield {
                            "type": "complete",
                            "response": fallback,
                            "sources": sources,
                            "source_catalog": source_catalog or [],
                            "truncated_history": truncated_history,
                        }

                    return stream_generator()
                return {
                    "response": fallback,
                    "sources": sources,
                    "source_catalog": source_catalog or [],
                    "truncated_history": truncated_history,
                }

            elif not context.strip():
                # APis worked but found nothing
                self.logger.warning(
                    f"No context found for query (kb_name={kb_name}, sources_kb_name={sources_kb_name})"
                )
                fallback = "未在已选来源或知识库中找到相关信息。"
                if stream:

                    async def stream_generator():
                        yield {
                            "type": "complete",
                            "response": fallback,
                            "sources": sources,
                            "source_catalog": source_catalog or [],
                            "truncated_history": truncated_history,
                        }

                    return stream_generator()
                return {
                    "response": fallback,
                    "sources": sources,
                    "source_catalog": source_catalog or [],
                    "truncated_history": truncated_history,
                }

        # Build messages for LLM
        messages = self.build_messages(
            message=message,
            history=truncated_history,
            context=context,
            enable_rag=enable_rag,
            enable_web_search=enable_web_search,
            require_sources=require_sources,
        )

        if stream:
            # Return async generator for streaming
            async def stream_generator():
                full_response = ""
                async for chunk in self.generate_stream(messages):
                    full_response += chunk
                    yield {"type": "chunk", "content": chunk}

                # Yield final result with sources
                yield {
                    "type": "complete",
                    "response": full_response,
                    "sources": sources,
                    "source_catalog": source_catalog or [],
                    "truncated_history": truncated_history,
                }

            return stream_generator()
        else:
            # Generate complete response
            response = await self.generate(messages)

            return {
                "response": response,
                "sources": sources,
                "source_catalog": source_catalog or [],
                "truncated_history": truncated_history,
            }


__all__ = ["ChatAgent"]
