#!/usr/bin/env python
"""
LocateAgent - Agent for locating and organizing knowledge points
Analyzes notebook content and generates progressive knowledge point learning plans
"""

import json
import re
from typing import Any

from src.agents.base_agent import BaseAgent
from src.services.llm.config import supports_response_format_json_object


class LocateAgent(BaseAgent):
    """Knowledge point location agent"""

    def __init__(self, api_key: str, base_url: str, language: str = "zh", binding: str = "openai"):
        self.binding = binding
        super().__init__(
            module_name="guide",
            agent_name="locate_agent",
            api_key=api_key,
            base_url=base_url,
            language=language,
        )

    @staticmethod
    def _extract_json_payload(text: str) -> Any | None:
        """Extract JSON payload from plain text or fenced code blocks."""
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

    @staticmethod
    def _normalize_knowledge_points(payload: Any) -> list[dict[str, str]]:
        """Normalize model output into the knowledge point schema expected by the UI."""
        if isinstance(payload, list):
            knowledge_points = payload
        elif isinstance(payload, dict):
            knowledge_points = (
                payload.get("knowledge_points") or payload.get("points") or payload.get("data") or []
            )
        else:
            knowledge_points = []

        validated_points = []
        for point in knowledge_points:
            if isinstance(point, dict):
                validated_points.append(
                    {
                        "knowledge_title": point.get("knowledge_title", "Unnamed knowledge point"),
                        "knowledge_summary": point.get("knowledge_summary", ""),
                        "user_difficulty": point.get("user_difficulty", ""),
                    }
                )

        return validated_points

    @staticmethod
    def _force_json_output(prompt: str) -> str:
        return (
            f"{prompt.rstrip()}\n\n"
            "IMPORTANT: Return a single valid JSON object only. "
            'Use the shape {"knowledge_points":[...]} and do not use markdown fences. '
            "Do not add explanations before or after the JSON."
        )

    @staticmethod
    def _should_retry_without_json_mode(exc: Exception) -> bool:
        message = str(exc).lower()
        if "json_object" not in message:
            return False
        return any(
            marker in message
            for marker in ("not supported", "not valid", "invalidparameter", "unsupported")
        )

    def _format_records(self, records: list[dict[str, Any]]) -> str:
        """Format notebook records as readable text"""
        formatted = []
        for i, record in enumerate(records, 1):
            record_type = record.get("type", "unknown")
            title = record.get("title", "Untitled")
            user_query = record.get("user_query", "")
            output = record.get("output", "")

            if len(output) > 2000:
                output = output[:2000] + "\n...[Content truncated]..."

            formatted.append(
                f"""
### Record {i} [{record_type.upper()}]
**Title**: {title}

**User Question/Input**:
{user_query}

**System Output**:
{output}
---"""
            )

        return "\n".join(formatted)

    async def process(
        self, notebook_id: str, notebook_name: str, records: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """
        Analyze notebook content and generate knowledge point learning plan

        Args:
            notebook_id: Notebook ID
            notebook_name: Notebook name
            records: List of records in notebook

        Returns:
            Dictionary containing knowledge point list
        """
        if not records:
            return {"success": False, "error": "No records in notebook", "knowledge_points": []}

        system_prompt = self.get_prompt("system")
        if not system_prompt:
            raise ValueError(
                "LocateAgent missing system prompt, please configure system in prompts/{lang}/locate_agent.yaml"
            )

        user_template = self.get_prompt("user_template")
        if not user_template:
            raise ValueError(
                "LocateAgent missing user_template, please configure user_template in prompts/{lang}/locate_agent.yaml"
            )

        records_content = self._format_records(records)

        user_prompt = user_template.format(
            notebook_id=notebook_id,
            notebook_name=notebook_name,
            record_count=len(records),
            records_content=records_content,
        )

        use_json_mode = supports_response_format_json_object(
            self.get_model(),
            self.binding,
            self.base_url,
        )
        prompt_for_request = user_prompt if use_json_mode else self._force_json_output(user_prompt)

        try:
            try:
                response = await self.call_llm(
                    user_prompt=prompt_for_request,
                    system_prompt=system_prompt,
                    response_format={"type": "json_object"} if use_json_mode else None,
                )
            except Exception as e:
                if not use_json_mode or not self._should_retry_without_json_mode(e):
                    return {"success": False, "error": str(e), "knowledge_points": []}
                response = await self.call_llm(
                    user_prompt=self._force_json_output(user_prompt),
                    system_prompt=system_prompt,
                )

            result = self._extract_json_payload(response)
            if result is None:
                return {
                    "success": False,
                    "error": "JSON parsing failed: model did not return valid JSON",
                    "raw_response": response,
                    "knowledge_points": [],
                }

            validated_points = self._normalize_knowledge_points(result)
            return {
                "success": True,
                "knowledge_points": validated_points,
                "total_points": len(validated_points),
            }

        except Exception as e:
            return {"success": False, "error": str(e), "knowledge_points": []}
