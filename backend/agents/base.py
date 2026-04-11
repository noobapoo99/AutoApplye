from __future__ import annotations

from abc import ABC
from abc import abstractmethod
import json
import logging
import re
from typing import Any
from typing import Protocol
from typing import runtime_checkable

from core.llm import hallucination_scorer
from core.llm import llm_client
from core.websocket import ws_manager


logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    agent_name: str = "base"

    def __init__(self, llm: Any | None = None, scorer: Any | None = None) -> None:
        self.llm = llm or llm_client
        self.scorer = scorer or hallucination_scorer

    def validate_input(self, payload: Any) -> bool:
        return True

    @abstractmethod
    async def process(self, payload: Any) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def emit_result(
        self,
        result: dict[str, Any],
        original_payload: Any,
    ) -> None:
        raise NotImplementedError

    async def run(self, payload: Any) -> dict[str, Any]:
        if not self.validate_input(payload):
            await ws_manager.publish_event(
                "agent_error",
                agent=self.agent_name,
                error="Invalid payload"
            )
            raise ValueError(f"Invalid payload for agent '{self.agent_name}'")

        await ws_manager.publish_event(
            "agent_started",
            agent=self.agent_name,
            payload_summary={
                "job_id": payload.get("job_id"),
                "company": payload.get("company_name"),
                "role": payload.get("role_title")
            }
        )

        result = await self.process(payload)

        try:
            hallucination_result = await self.scorer.score(result, payload)
        except Exception as exc:
            logger.warning(
                "Agent %s hallucination scorer raised an exception: %s — continuing",
                self.agent_name, exc,
            )
            hallucination_result = {"score": 0, "max_score": 6, "passed": False, "error": str(exc)}

        result["hallucination_check"] = hallucination_result

        passed = bool(hallucination_result.get("passed"))
        score = hallucination_result.get("score")
        max_score = hallucination_result.get("max_score")

        if passed:
            logger.info(
                "Agent %s hallucination score %s/%s passed=True",
                self.agent_name, score, max_score,
            )
        else:
            # Log a warning but DO NOT block the pipeline.
            # Set a flag so downstream agents can route to human review if needed.
            logger.warning(
                "Agent %s hallucination score %s/%s passed=False — continuing with flagged result",
                self.agent_name, score, max_score,
            )
            # Only flag for human review if the score is particularly low (< 2/6)
            if isinstance(score, (int, float)) and isinstance(max_score, (int, float)):
                if max_score > 0 and (score / max_score) < 0.20:
                    result.setdefault("needs_human_review", True)
                    result.setdefault(
                        "flag_reason",
                        f"Low hallucination score {score}/{max_score} — flagged for human review.",
                    )

        await self.emit_result(result, payload)
        
        await ws_manager.publish_event(
            "agent_completed",
            agent=self.agent_name,
            job_id=result.get("job_id"),
            passed=passed,
            score=f"{score}/{max_score}" if max_score else "N/A"
        )
        logger.info("Agent %s completed", self.agent_name)
        return result


@runtime_checkable
class ResumeEditStrategy(Protocol):
    strategy_name: str

    async def edit(
        self,
        resume_text: str,
        jd_text: str,
        gap_skills: list[str],
    ) -> dict[str, Any]:
        ...


async def _complete_json_response(
    *,
    llm: Any,
    prompt: str,
    system: str,
) -> dict[str, Any]:
    response = await llm.complete(prompt=prompt, system=system, use_cache=False)
    candidate = _extract_json_text(response)

    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ValueError("LLM response did not contain valid JSON") from exc

    if not isinstance(parsed, dict):
        raise ValueError("LLM response must be a JSON object")
    return parsed


def _extract_json_text(response: str) -> str:
    stripped = response.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped

    fenced_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", stripped, re.DOTALL)
    if fenced_match:
        return fenced_match.group(1).strip()

    json_match = re.search(r"(\{.*\})", stripped, re.DOTALL)
    if json_match:
        return json_match.group(1).strip()

    raise ValueError("No JSON object found in LLM response")


class KeywordInjectionStrategy:
    strategy_name = "keyword_injection"

    def __init__(self, llm: Any | None = None) -> None:
        self.llm = llm or llm_client

    async def edit(
        self,
        resume_text: str,
        jd_text: str,
        gap_skills: list[str],
    ) -> dict[str, Any]:
        system = (
            "You are a factual resume editor. Only make grounded edits based on the "
            "existing resume and the supplied gap skills. Return JSON only."
        )
        prompt = (
            "Inject ALL the following missing skills naturally into existing resume "
            "bullet points or the skills section without inventing experience or "
            "credentials. Ensure the edits look indistinguishable from original content.\n\n"
            f"Gap skills: {json.dumps(gap_skills, ensure_ascii=False)}\n\n"
            "Resume text:\n"
            f"{resume_text}\n\n"
            "Job description:\n"
            f"{jd_text}\n\n"
            "Return a JSON object with this exact shape:\n"
            '{"edited_sections": {"Technical Skills": "updated content", "Experience": "updated bullets..."}, "changes": ["List of specific keywords added"]}'
        )
        result = await _complete_json_response(llm=self.llm, prompt=prompt, system=system)
        if "edited_sections" not in result or "changes" not in result:
            raise ValueError("KeywordInjectionStrategy response is missing required keys")
        return result


class SummaryRewriteStrategy:
    strategy_name = "summary_rewrite"

    def __init__(self, llm: Any | None = None) -> None:
        self.llm = llm or llm_client

    async def edit(
        self,
        resume_text: str,
        jd_text: str,
        gap_skills: list[str],
    ) -> dict[str, Any]:
        system = (
            "You are a factual resume editor. Rewrite only the professional summary "
            "to align with the job description without fabricating experience. "
            "Return JSON only."
        )
        prompt = (
            "Rewrite the professional summary so it better aligns with the job "
            "description and highlights relevant existing experience while handling "
            "the supplied gap skills carefully.\n\n"
            f"Gap skills: {json.dumps(gap_skills, ensure_ascii=False)}\n\n"
            "Resume text:\n"
            f"{resume_text}\n\n"
            "Job description:\n"
            f"{jd_text}\n\n"
            "Return a JSON object with this exact shape:\n"
            '{"new_summary": "rewritten summary", "changes": []}'
        )
        result = await _complete_json_response(llm=self.llm, prompt=prompt, system=system)
        if "new_summary" not in result or "changes" not in result:
            raise ValueError("SummaryRewriteStrategy response is missing required keys")
        
        # Add edited_sections for easier reconstruction
        result.setdefault("edited_sections", {})
        result["edited_sections"]["Summary"] = result["new_summary"]
        return result


class SkillsReorderStrategy:
    strategy_name = "skills_reorder"

    def __init__(self, llm: Any | None = None) -> None:
        self.llm = llm or llm_client

    async def edit(
        self,
        resume_text: str,
        jd_text: str,
        gap_skills: list[str],
    ) -> dict[str, Any]:
        system = (
            "You are a factual resume editor. Reorder the skills section to prioritize "
            "job-relevant skills without inventing new skills. Return JSON only."
        )
        prompt = (
            "Reorder the skills section to prioritize job-relevant skills while "
            "keeping the resume truthful. Use the job description and gap skills as "
            "guidance for prioritization only.\n\n"
            f"Gap skills: {json.dumps(gap_skills, ensure_ascii=False)}\n\n"
            "Resume text:\n"
            f"{resume_text}\n\n"
            "Job description:\n"
            f"{jd_text}\n\n"
            "Return a JSON object with this exact shape:\n"
            '{"reordered_skills": [], "changes": []}'
        )
        result = await _complete_json_response(llm=self.llm, prompt=prompt, system=system)
        if "reordered_skills" not in result or "changes" not in result:
            raise ValueError("SkillsReorderStrategy response is missing required keys")
            
        # Add edited_sections for easier reconstruction
        result.setdefault("edited_sections", {})
        result["edited_sections"]["Technical Skills"] = "\n".join(result["reordered_skills"])
        return result


RESUME_STRATEGIES: dict[str, ResumeEditStrategy] = {
    "keyword_injection": KeywordInjectionStrategy(),
    "summary_rewrite": SummaryRewriteStrategy(),
    "skills_reorder": SkillsReorderStrategy(),
}


class AgentFactory:
    _registry: dict[str, type[BaseAgent]] = {}

    @classmethod
    def register(cls, name: str) -> Any:
        def decorator(agent_cls: type[BaseAgent]) -> type[BaseAgent]:
            if not issubclass(agent_cls, BaseAgent):
                raise TypeError("Only BaseAgent subclasses can be registered")
            if name in cls._registry:
                raise ValueError(f"Agent type '{name}' is already registered")

            cls._registry[name] = agent_cls
            return agent_cls

        return decorator

    @classmethod
    def create(cls, agent_type: str, **kwargs: Any) -> BaseAgent:
        agent_cls = cls._registry.get(agent_type)
        if agent_cls is None:
            raise ValueError(f"Unknown agent type: {agent_type}")
        return agent_cls(**kwargs)

    @classmethod
    def available(cls) -> list[str]:
        return sorted(cls._registry.keys())


__all__ = [
    "AgentFactory",
    "BaseAgent",
    "KeywordInjectionStrategy",
    "RESUME_STRATEGIES",
    "ResumeEditStrategy",
    "SkillsReorderStrategy",
    "SummaryRewriteStrategy",
]
