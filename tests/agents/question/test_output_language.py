#!/usr/bin/env python
"""
Tests for question-generation output language resolution.
"""

import asyncio
import json
from pathlib import Path
import sys

import pytest

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from src.agents.question.agents import Message
import src.agents.question.coordinator as coordinator_module
from src.agents.question.coordinator import AgentCoordinator
from src.agents.question.language import resolve_output_language
from src.agents.question.tools.exam_mimic import generate_question_from_reference


class FakeQuestionAgent:
    def __init__(self, language: str = "en", **kwargs):
        self.language = language
        self.language_history = [language]
        self.requirement = None
        self.retrieved_knowledge = []
        self.current_question = None
        self.submitted = False
        self.inbox = []
        self.client = None
        self.model = "fake-model"

    def set_language(self, language: str | None):
        self.language = language or "zh"
        self.language_history.append(self.language)

    def set_requirement(self, requirement: dict):
        self.requirement = requirement

    def receive_message(self, message: Message):
        self.inbox.append(message)

    async def run(self, task: str, context: dict | None = None, send_message_callback=None):
        question = {
            "question_type": "written",
            "question": "中文题目" if self.language == "zh" else "English question",
            "correct_answer": "中文答案" if self.language == "zh" else "English answer",
            "explanation": "中文解析" if self.language == "zh" else "English explanation",
        }
        self.current_question = question
        self.submitted = True

        if send_message_callback:
            await send_message_callback(
                Message(
                    from_agent="QuestionGenerationAgent",
                    to_agent="QuestionValidationWorkflow",
                    message_type="validate_request",
                    content={"question": question},
                )
            )

        return {"success": True, "result": question, "iterations": 1}


class FakeValidationWorkflow:
    def __init__(self, language: str = "en", **kwargs):
        self.language = language
        self.language_history = [language]

    def set_language(self, language: str | None):
        self.language = language or "zh"
        self.language_history.append(self.language)

    async def validate(self, question: dict, reference_question: str | None = None):
        return {
            "decision": "approve",
            "issues": [],
            "suggestions": [],
            "reasoning": f"validated in {self.language}",
        }

    async def analyze_relevance(self, question: dict, knowledge_summary: str):
        return {
            "relevance": "high",
            "kb_coverage": f"relevance analyzed in {self.language}",
            "extension_points": "",
        }

    async def analyze_extension(self, question: dict, shared_context: str):
        return {
            "kb_connection": "",
            "extended_aspect": "",
            "reasoning": f"extension analyzed in {self.language}",
        }


@pytest.fixture
def coordinator_with_fakes(monkeypatch):
    monkeypatch.setattr(coordinator_module, "QuestionGenerationAgent", FakeQuestionAgent)
    monkeypatch.setattr(coordinator_module, "QuestionValidationWorkflow", FakeValidationWorkflow)
    coordinator = AgentCoordinator(kb_name="test_kb")
    monkeypatch.setattr(coordinator, "_suppress_logging", lambda: None)
    return coordinator


@pytest.mark.parametrize(
    ("input_texts", "fallback_output_language", "system_language", "expected"),
    [
        (["牛顿迭代法"], "en", "en", "zh"),
        (["Newton's method"], "zh", "zh", "en"),
        (["请基于牛顿迭代法 Newton method 说明其局部收敛速度"], "en", "en", "zh"),
        (["PCA"], "zh", "en", "zh"),
        ([""], "en", "zh", "en"),
        ([""], None, "en", "en"),
    ],
)
def test_resolve_output_language(input_texts, fallback_output_language, system_language, expected):
    assert (
        resolve_output_language(
            input_texts,
            fallback_output_language=fallback_output_language,
            system_language=system_language,
        )
        == expected
    )


@pytest.mark.parametrize(
    (
        "knowledge_point",
        "fallback_output_language",
        "expected_language",
        "expected_plan_snippet",
        "expected_question_snippet",
    ),
    [
        (
            "牛顿迭代法",
            "en",
            "zh",
            "输出语言：中文",
            "question、correct_answer、explanation 必须全部使用中文",
        ),
        (
            "Newton's method",
            "zh",
            "en",
            "Output language: English",
            "The question, correct_answer, and explanation fields must all be written in English",
        ),
    ],
)
def test_generate_questions_custom_uses_resolved_output_language_prompts(
    coordinator_with_fakes,
    monkeypatch,
    knowledge_point,
    fallback_output_language,
    expected_language,
    expected_plan_snippet,
    expected_question_snippet,
):
    coordinator = coordinator_with_fakes
    llm_calls = []

    async def fake_call_llm(
        system_prompt: str,
        user_prompt: str,
        response_format: dict | None = None,
        stage: str = "",
    ):
        llm_calls.append({"stage": stage, "system": system_prompt, "user": user_prompt})

        if stage == "generate_search_queries":
            query = "牛顿迭代法" if expected_language == "zh" else "Newton's method"
            return json.dumps({"queries": [query]}, ensure_ascii=False)

        if stage == "generate_question_plan":
            focus = (
                "牛顿迭代法的收敛分析"
                if expected_language == "zh"
                else "Convergence of Newton's method"
            )
            return json.dumps(
                {"focuses": [{"id": "q_1", "focus": focus, "type": "written"}]},
                ensure_ascii=False,
            )

        if stage == "generate_question_q_1":
            question = {
                "question_type": "written",
                "question": "请说明牛顿迭代法的收敛条件。"
                if expected_language == "zh"
                else "Explain the convergence conditions of Newton's method.",
                "correct_answer": "中文答案" if expected_language == "zh" else "English answer",
                "explanation": "中文解析" if expected_language == "zh" else "English explanation",
            }
            return json.dumps(question, ensure_ascii=False)

        raise AssertionError(f"Unexpected LLM stage: {stage}")

    async def fake_gather_retrieval_context_naive(queries: list[str]):
        return [{"query": queries[0], "answer": "knowledge context"}]

    monkeypatch.setattr(coordinator, "_call_llm", fake_call_llm)
    monkeypatch.setattr(
        coordinator,
        "_gather_retrieval_context_naive",
        fake_gather_retrieval_context_naive,
    )

    result = asyncio.run(
        coordinator.generate_questions_custom(
            base_requirement={
                "knowledge_point": knowledge_point,
                "difficulty": "medium",
                "question_type": "written",
                "additional_requirements": "",
                "output_language": fallback_output_language,
            },
            num_questions=1,
        )
    )

    assert result["success"] is True
    assert result["resolved_output_language"] == expected_language
    assert coordinator.question_agent.language_history[-1] == expected_language
    assert coordinator.validation_workflow.language_history[-1] == expected_language

    plan_call = next(call for call in llm_calls if call["stage"] == "generate_question_plan")
    question_call = next(call for call in llm_calls if call["stage"] == "generate_question_q_1")

    assert expected_plan_snippet in plan_call["user"]
    assert expected_question_snippet in question_call["system"]


def test_legacy_generate_question_updates_runtime_language(coordinator_with_fakes):
    coordinator = coordinator_with_fakes

    requirement = {
        "reference_question": "Use Newton's method to solve f(x)=0 and discuss convergence.",
        "additional_requirements": "",
        "output_language": "zh",
    }

    result = asyncio.run(coordinator.generate_question(requirement))

    assert result["success"] is True
    assert result["resolved_output_language"] == "en"
    assert coordinator.question_agent.language_history[-1] == "en"
    assert coordinator.validation_workflow.language_history[-1] == "en"
    assert coordinator.question_agent.requirement["resolved_output_language"] == "en"


def test_mimic_reference_generation_prefers_reference_language():
    class DummyCoordinator:
        default_language = "zh"

        def __init__(self):
            self.requirement = None

        async def generate_question(self, requirement: dict):
            self.requirement = requirement
            return {
                "success": True,
                "question": {},
                "validation": {},
                "rounds": 1,
                "resolved_output_language": requirement["resolved_output_language"],
            }

    coordinator = DummyCoordinator()
    reference_question = {
        "question_text": "已知牛顿迭代法用于求方程根，说明其局部收敛条件。",
        "images": [],
    }

    result = asyncio.run(
        generate_question_from_reference(
            reference_question=reference_question,
            coordinator=coordinator,
            kb_name="test_kb",
            output_language="en",
        )
    )

    assert result["success"] is True
    assert coordinator.requirement["resolved_output_language"] == "zh"
    assert coordinator.requirement["output_language"] == "en"
    assert "最终题目、答案和解析必须使用中文" in coordinator.requirement["additional_requirements"]
