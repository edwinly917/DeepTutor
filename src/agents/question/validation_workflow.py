#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Question Validation Workflow: retrieve -> validate -> return.
Uses unified PromptManager for prompt loading.
"""

from collections.abc import Callable
import json
import os
from pathlib import Path
import sys
from typing import Any

from openai import AsyncOpenAI

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from src.logging import get_logger
from src.services.config import get_agent_params, load_config_with_main, parse_language
from src.services.prompt import get_prompt_manager
from src.tools.rag_tool import rag_search

from .language import get_language_label

# Module logger
logger = get_logger("QuestionValidation")


class QuestionValidationWorkflow:
    """Question validation workflow - fixed pipeline"""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        kb_name: str | None = None,
        token_stats_callback: Callable | None = None,
        language: str = "en",
    ):
        """
        Initialize validation workflow.

        Args:
            api_key: API key
            base_url: API endpoint
            model: Model name
            kb_name: Knowledge base name
            token_stats_callback: Callback function to update token statistics
            language: Language for prompts ("en" or "zh")
        """
        # API configuration
        if not api_key:
            api_key = os.getenv("LLM_API_KEY")
        if not base_url:
            base_url = os.getenv("LLM_HOST")
        if model is None:
            model = os.getenv("LLM_MODEL", "gpt-4o")

        # For local LLM servers, use placeholder key if none provided
        client_api_key = api_key or "sk-no-key-required"
        self.client = AsyncOpenAI(api_key=client_api_key, base_url=base_url)
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.kb_name = kb_name
        self.token_stats_callback = token_stats_callback
        self.language = parse_language(language)

        self._prompts = {}
        self.set_language(language)

        # Get agent parameters from unified config
        self._agent_params = get_agent_params("question")

        # Load config for RAG settings
        self._config = load_config_with_main("question_config.yaml", project_root)

    def set_language(self, language: str | None):
        """Reload prompts when request language changes."""
        lang_code = parse_language(language)
        self.language = lang_code
        self._prompts = get_prompt_manager().load_prompts(
            module_name="question",
            agent_name="validation_workflow",
            language=lang_code,
        )

    async def validate(
        self, question: dict[str, Any], reference_question: str | None = None
    ) -> dict[str, Any]:
        """
        Validate question - fixed pipeline: retrieve → validate → return

        Args:
            question: Question content
                {
                    "question_type": str,
                    "question": str,
                    "options": Dict (for multiple choice),
                    "correct_answer": str,
                    "explanation": str,
                    "knowledge_point": str (optional)
                }

        Returns:
            Dict: Validation result
                {
                    "decision": "approve" | "request_modification" | "request_regeneration",
                    "issues": List[str],
                    "suggestions": List[str],
                    "reasoning": str,
                    "retrieved_knowledge": List[Dict]
                }
        """
        logger.info("Starting question validation")

        # Step 1: Retrieve related knowledge
        logger.info("Step 1/2: Retrieving validation knowledge")
        retrieved_knowledge = await self._retrieve_knowledge(question)
        logger.debug(f"Retrieved {len(retrieved_knowledge)} knowledge items")

        # Step 2: Validate question
        logger.info("Step 2/2: Validating question")
        validation_result = await self._validate_question(
            question, retrieved_knowledge, reference_question
        )
        logger.info(f"Validation decision: {validation_result['decision']}")

        # Add retrieved knowledge to result
        validation_result["retrieved_knowledge"] = retrieved_knowledge

        logger.success("Validation completed")

        return validation_result

    async def _generate_retrieval_query(self, question: dict[str, Any]) -> str:
        """Use LLM to generate retrieval query"""
        knowledge_point = question.get("knowledge_point", "")
        question_text = question.get("question", "")
        options = question.get("options", {})
        correct_answer = question.get("correct_answer", "")
        output_language = get_language_label(self.language, self.language)
        system_prompt = self._prompts.get("retrieval_query_system", "")
        if not system_prompt:
            system_prompt = (
                "你是一名专业的知识检索专家。"
                if self.language == "zh"
                else "You are a professional knowledge retrieval expert."
            )

        prompt_template = self._prompts.get("retrieval_query", "")
        if not prompt_template:
            if self.language == "zh":
                prompt_template = (
                    "请分析以下题目，并生成一个简洁的检索查询，用于从知识库中检索验证该题所需的相关理论知识。\n\n"
                    "题目信息：\n"
                    "- 知识点：{knowledge_point}\n"
                    "- 题目：{question_text}\n"
                    "{options_section}"
                    "{answer_section}"
                    "请提取题目涉及的**核心知识点和概念**，生成一个简洁的检索查询（不超过100字）。\n\n"
                    "要求：\n"
                    "1. 提取题目中的核心数学/物理概念、定理、方法\n"
                    "2. 如果存在具体公式或算法，提取关键术语\n"
                    "3. 不要包含题目中的具体数值和细节\n"
                    "4. 查询应能检索到验证该题所需的理论知识\n"
                    "5. 检索查询使用{output_language}\n\n"
                    "直接输出检索查询，不要包含额外内容。"
                )
            else:
                prompt_template = (
                    "Analyze the following question and generate a concise retrieval query to "
                    "retrieve relevant knowledge from the knowledge base to validate this question.\n\n"
                    "Question information:\n"
                    "- Knowledge point: {knowledge_point}\n"
                    "- Question: {question_text}\n"
                    "{options_section}"
                    "{answer_section}"
                    "Please extract the **core knowledge points and concepts** involved in the question "
                    "and generate a concise retrieval query (no more than 100 words).\n\n"
                    "Requirements:\n"
                    "1. Extract core mathematical/physical concepts, theorems, methods from the question\n"
                    "2. If specific formulas or algorithms exist, extract key terminology\n"
                    "3. Do not include specific numerical values and details from the question\n"
                    "4. Query should be able to retrieve theoretical knowledge needed to validate the question\n"
                    "5. Write the retrieval query in {output_language}\n\n"
                    "Output the retrieval query directly, no additional content."
                )

        options_section = ""
        if options:
            prefix = "- 选项：" if self.language == "zh" else "- Options: "
            options_section = f"{prefix}{json.dumps(options, ensure_ascii=False)}\n"

        answer_section = ""
        if correct_answer:
            prefix = "- 答案：" if self.language == "zh" else "- Answer: "
            answer_section = f"{prefix}{correct_answer}\n"

        prompt = prompt_template.format(
            knowledge_point=knowledge_point,
            question_text=question_text,
            options_section=options_section,
            answer_section=answer_section,
            output_language=output_language,
        )

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
        )

        # Extract response content
        response_content = response.choices[0].message.content.strip()

        # Update token statistics if callback is available
        input_tokens = 0
        output_tokens = 0
        cost = 0.0
        if hasattr(response, "usage") and response.usage:
            input_tokens = response.usage.prompt_tokens
            output_tokens = response.usage.completion_tokens
            cost = input_tokens * 0.00000015 + output_tokens * 0.0000006
            if self.token_stats_callback:
                self.token_stats_callback(
                    input_tokens=input_tokens, output_tokens=output_tokens, model=self.model
                )

        # Log LLM call with detailed information
        logger.log_llm_call(
            model=self.model,
            stage="generate_query",
            system_prompt=system_prompt,
            user_prompt=prompt,
            response=response_content,
            agent_name="QuestionValidationWorkflow",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost,
            level="DEBUG",
        )

        return response_content

    async def _retrieve_knowledge(self, question: dict[str, Any]) -> list[dict[str, Any]]:
        """Retrieve knowledge needed for validation."""
        # Use LLM to generate retrieval query
        query = await self._generate_retrieval_query(question)

        logger.debug(f"LLM generated query: {query[:100]}...")

        # Get RAG mode from config
        question_cfg = self._config.get("question", {})
        rag_mode = question_cfg.get("rag_mode", "hybrid")

        # Execute retrieval using unified RAG tool
        try:
            result = await rag_search(
                query=query,
                kb_name=self.kb_name,
                mode=rag_mode,
                only_need_context=True,
            )

            # Return retrieval results with raw answer
            retrieved = []
            if result and result.get("answer"):
                retrieved.append(
                    {
                        "query": query,
                        "answer": result.get("answer", ""),
                    }
                )

            return retrieved

        except Exception as e:
            logger.warning(f"Retrieval failed: {e!s}")
            return []

    async def _validate_question(
        self,
        question: dict[str, Any],
        retrieved_knowledge: list[dict[str, Any]],
        reference_question: str = None,
    ) -> dict[str, Any]:
        """Validate question"""
        knowledge_str = self._format_knowledge(retrieved_knowledge)

        question_str = json.dumps(question, ensure_ascii=False, indent=2)

        reference_section = ""
        innovation_section = ""
        if reference_question:
            reference_section = f"""Reference question (for comparison):
{reference_question}
"""
            innovation_section = self._prompts.get("innovation_section", "")

        prompt_template = self._prompts.get("validate", "")
        prompt = prompt_template.format(
            question=question_str,
            reference_section=reference_section,
            innovation_section=innovation_section,
            validation_knowledge=knowledge_str,
        )
        system_prompt = self._prompts.get("validate_system", "")
        if not system_prompt:
            system_prompt = (
                "你是一名专业的题目验证专家，严格基于知识库内容验证题目。"
                if self.language == "zh"
                else "You are a professional question validation expert who strictly validates questions based on knowledge base content."
            )

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": system_prompt,
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=self._agent_params["temperature"],
                max_tokens=self._agent_params["max_tokens"],
                response_format={"type": "json_object"},
            )

            # Extract response content
            response_content = response.choices[0].message.content

            # Update token statistics if callback is available
            input_tokens = 0
            output_tokens = 0
            cost = 0.0
            if hasattr(response, "usage") and response.usage:
                input_tokens = response.usage.prompt_tokens
                output_tokens = response.usage.completion_tokens
                cost = input_tokens * 0.00000015 + output_tokens * 0.0000006
                if self.token_stats_callback:
                    self.token_stats_callback(
                        input_tokens=input_tokens, output_tokens=output_tokens, model=self.model
                    )

            # Log LLM call with detailed information
            logger.log_llm_call(
                model=self.model,
                stage="validate",
                system_prompt=system_prompt,
                user_prompt=prompt,
                response=response_content,
                agent_name="QuestionValidationWorkflow",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost=cost,
                level="DEBUG",
            )

            result = json.loads(response_content)

            # Ensure issues and suggestions are lists (handle case where LLM returns dict)
            issues = result.get("issues", [])
            if not isinstance(issues, list):
                if isinstance(issues, dict):
                    # If issues is a dict, convert to list
                    issues = [issues]
                else:
                    issues = []

            suggestions = result.get("suggestions", [])
            if not isinstance(suggestions, list):
                if isinstance(suggestions, dict):
                    # If suggestions is a dict, convert to list
                    suggestions = [suggestions]
                else:
                    suggestions = []

            return {
                "decision": result.get("decision", "request_regeneration"),
                "issues": issues,
                "suggestions": suggestions,
                "reasoning": result.get("reasoning", ""),
            }

        except Exception as e:
            logger.warning(f"Validation failed: {e!s}")
            return {
                "decision": "request_regeneration",
                "issues": [f"Validation error: {e!s}"],
                "suggestions": ["Please regenerate the question"],
                "reasoning": "An error occurred during validation",
            }

    def _format_knowledge(self, retrieved_knowledge: list[dict[str, Any]]) -> str:
        """Format retrieved knowledge."""
        if not retrieved_knowledge:
            return "No validation knowledge retrieved"

        knowledge_parts = []
        for k in retrieved_knowledge:
            knowledge_parts.append(f"=== Query: {k['query']} ===")
            answer = k.get("answer", "")
            if answer:
                # Truncate very long answers
                if len(answer) > 3000:
                    answer = answer[:3000] + "...[truncated]"
                knowledge_parts.append(answer)
            knowledge_parts.append("")

        return (
            "\n".join(knowledge_parts) if knowledge_parts else "No validation knowledge retrieved"
        )

    async def analyze_extension(
        self, question: dict[str, Any], shared_context: str
    ) -> dict[str, Any]:
        """
        Analyze how a question extends beyond the knowledge base.

        This is called when a question doesn't pass validation after max rounds,
        to provide insights about how it relates to and extends from the KB.

        Args:
            question: The question that wasn't fully validated
            shared_context: The shared knowledge context from RAG

        Returns:
            Dict with:
                - kb_connection: How the question relates to the knowledge base
                - extended_aspect: What knowledge areas the question extends to
                - reasoning: Detailed explanation
        """
        logger.info("Analyzing question extension from knowledge base")

        question_str = json.dumps(question, ensure_ascii=False, indent=2)

        # Truncate context if too long
        context_str = shared_context
        if len(context_str) > 4000:
            context_str = context_str[:4000] + "...[truncated]"
        prompt_template = self._prompts.get("extension_analysis", "")
        if not prompt_template:
            if self.language == "zh":
                prompt_template = (
                    "分析以下题目如何与知识库内容相关，并在其基础上延展。\n\n"
                    "题目：\n{question}\n\n"
                    "知识库内容：\n{knowledge}\n\n"
                    "请从知识延展的角度分析，并以JSON格式输出：\n"
                    "{{\n"
                    '    "kb_connection": "描述这道题目如何连接到知识库内容。知识库中的哪些概念、理论或方法与该题相关？",\n'
                    '    "extended_aspect": "描述这道题超出了核心知识库内容的哪些知识领域。它探索了哪些额外概念、应用或视角？",\n'
                    '    "reasoning": "详细说明这道题与知识库之间的关系，以及这种延展为什么对学习有价值。"\n'
                    "}}\n\n"
                    "要求：\n"
                    "1. 强调积极意义，这是一道在知识库基础上延展的题目\n"
                    "2. kb_connection 要指出题目建立在哪些知识库基础概念之上\n"
                    "3. extended_aspect 要说明它提供了哪些新的学习机会\n"
                    "4. 保持分析具有建设性和教学性\n\n"
                    "只输出JSON，不要包含额外文本。"
                )
            else:
                prompt_template = (
                    "Analyze how the following question relates to and extends from the knowledge base content.\n\n"
                    "Question:\n{question}\n\n"
                    "Knowledge Base Content:\n{knowledge}\n\n"
                    "Please analyze from the perspective of knowledge extension and provide a JSON response:\n"
                    "{{\n"
                    '    "kb_connection": "Describe how this question connects to the knowledge base content. What concepts, theories, or methods from the KB are relevant to this question?",\n'
                    '    "extended_aspect": "Describe what knowledge areas this question extends to beyond the core KB content. What additional concepts, applications, or perspectives does it explore?",\n'
                    '    "reasoning": "Provide a detailed explanation of the relationship between this question and the knowledge base, and why this extension is valuable for learning."\n'
                    "}}\n\n"
                    "Guidelines:\n"
                    '1. Focus on the POSITIVE aspects - this is an "extended" question that goes beyond basic KB content\n'
                    "2. kb_connection should identify the foundation concepts from the KB that the question builds upon\n"
                    "3. extended_aspect should highlight what new learning opportunities this question provides\n"
                    "4. Keep the analysis constructive and educational\n\n"
                    "Output only the JSON, no additional text."
                )

        prompt = prompt_template.format(question=question_str, knowledge=context_str)
        system_prompt = self._prompts.get("extension_analysis_system", "")
        if not system_prompt:
            system_prompt = (
                "你是一名教育内容分析专家，擅长识别知识联系和学习延展。"
                if self.language == "zh"
                else "You are an educational content analyst specializing in identifying knowledge connections and learning extensions."
            )

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": system_prompt,
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                response_format={"type": "json_object"},
            )

            response_content = response.choices[0].message.content

            # Update token statistics
            if hasattr(response, "usage") and response.usage:
                input_tokens = response.usage.prompt_tokens
                output_tokens = response.usage.completion_tokens
                cost = input_tokens * 0.00000015 + output_tokens * 0.0000006
                if self.token_stats_callback:
                    self.token_stats_callback(
                        input_tokens=input_tokens, output_tokens=output_tokens, model=self.model
                    )

            result = json.loads(response_content)

            logger.info("Extension analysis completed")

            return {
                "kb_connection": result.get("kb_connection", ""),
                "extended_aspect": result.get("extended_aspect", ""),
                "reasoning": result.get("reasoning", ""),
            }

        except Exception as e:
            logger.warning(f"Extension analysis failed: {e!s}")
            return {
                "kb_connection": "Unable to analyze connection to knowledge base",
                "extended_aspect": "This question explores areas beyond the core knowledge base content",
                "reasoning": f"Analysis could not be completed: {e!s}",
            }

    async def analyze_relevance(
        self,
        question: dict[str, Any],
        knowledge_summary: str,
    ) -> dict[str, Any]:
        """
        Analyze the relevance between a question and the knowledge base content.

        This is used in custom mode where we don't iterate - we just analyze
        how the question relates to the knowledge base.

        Args:
            question: The generated question dict
            knowledge_summary: Summary of background knowledge from RAG

        Returns:
            Dict with:
                - relevance: "high" or "partial"
                - kb_coverage: Description of what KB content the question tests
                - extension_points: Description of any extensions (only if partial)
        """
        logger.info("Analyzing question relevance to knowledge base")

        question_str = json.dumps(question, ensure_ascii=False, indent=2)

        # Truncate context if too long
        context_str = knowledge_summary
        if len(context_str) > 4000:
            context_str = context_str[:4000] + "...[truncated]"
        prompt_template = self._prompts.get("relevance_analysis", "")
        prompt = prompt_template.format(question=question_str, knowledge=context_str)
        system_prompt = self._prompts.get("relevance_analysis_system", "")
        if not system_prompt:
            system_prompt = (
                "你是一名教育内容分析专家，擅长分析考试题与知识库内容之间的关系。"
                if self.language == "zh"
                else "You are an educational content analyst specializing in analyzing the relationship between exam questions and knowledge base content."
            )

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": system_prompt,
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                response_format={"type": "json_object"},
            )

            response_content = response.choices[0].message.content

            # Update token statistics
            input_tokens = 0
            output_tokens = 0
            if hasattr(response, "usage") and response.usage:
                input_tokens = response.usage.prompt_tokens
                output_tokens = response.usage.completion_tokens
                cost = input_tokens * 0.00000015 + output_tokens * 0.0000006
                if self.token_stats_callback:
                    self.token_stats_callback(
                        input_tokens=input_tokens, output_tokens=output_tokens, model=self.model
                    )

            # Log LLM call
            logger.log_llm_call(
                model=self.model,
                stage="analyze_relevance",
                system_prompt=system_prompt,
                user_prompt=prompt,
                response=response_content,
                agent_name="QuestionValidationWorkflow",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost=input_tokens * 0.00000015 + output_tokens * 0.0000006,
                level="DEBUG",
            )

            result = json.loads(response_content)

            relevance = result.get("relevance", "partial")
            if relevance not in ["high", "partial"]:
                relevance = "partial"

            logger.info(f"Relevance analysis completed: {relevance}")

            return {
                "relevance": relevance,
                "kb_coverage": result.get("kb_coverage", ""),
                "extension_points": result.get("extension_points", "")
                if relevance == "partial"
                else "",
            }

        except Exception as e:
            logger.warning(f"Relevance analysis failed: {e!s}")
            return {
                "relevance": "partial",
                "kb_coverage": "Unable to analyze knowledge base coverage",
                "extension_points": f"Analysis could not be completed: {e!s}",
            }
