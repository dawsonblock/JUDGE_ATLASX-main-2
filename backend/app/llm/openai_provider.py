"""OpenAI LLM provider.

Calls the OpenAI Chat Completions API using gpt-4o-mini by default.

Configuration (via environment or Settings):
  OPENAI_API_KEY    Required.  Must be set or calls will return an error response.
  OPENAI_MODEL      Model to use (default: gpt-4o-mini)
  OPENAI_BASE_URL   Override base URL for compatible APIs (default: OpenAI default)

Evidence grounding:
  evidence_texts from the request are injected as context in the system
  message.  The model is instructed to cite only text from the provided
  context.  Citations are extracted from the response.
"""

from __future__ import annotations

import logging
import os

from app.llm.provider import LLMProvider
from app.llm.schemas import Citation, LLMRequest, LLMResponse

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "gpt-4o-mini"

_SYSTEM_MESSAGE = """You are a legal research assistant helping a human reviewer examine legal records.
You must ONLY use the evidence texts provided in the user message.
Do NOT make claims unsupported by the provided evidence.
Do NOT assign guilt, infer criminality, score dangerousness, or make legal conclusions.
Do NOT recommend publishing any record.
If you cannot answer from the provided evidence, respond: "I cannot answer without cited evidence."
Always end your response with a "CITATIONS:" section listing the source URLs you referenced."""


class OpenAIProvider(LLMProvider):
    """LLM provider that calls the OpenAI Chat Completions API."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = _DEFAULT_MODEL,
        base_url: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY") or ""
        self._model = model
        self._base_url = base_url
        self._timeout = timeout

    @property
    def provider_name(self) -> str:
        return f"OpenAIProvider({self._model})"

    def _call(self, request: LLMRequest) -> LLMResponse:
        if not self._api_key:
            logger.warning("OPENAI_API_KEY not set; returning empty response")
            return LLMResponse(
                answer=None,
                citations=[],
                confidence=0.0,
                unsupported_claims=["OPENAI_API_KEY not configured"],
                requires_human_review=True,
                task_type=request.task_type,
                model_name=self._model,
            )

        try:
            import openai
        except ImportError:
            return LLMResponse(
                answer=None,
                citations=[],
                confidence=0.0,
                unsupported_claims=["openai package not installed"],
                requires_human_review=True,
                task_type=request.task_type,
                model_name=self._model,
            )

        evidence_block = self._format_evidence(request)
        user_content = (
            f"Evidence texts:\n{evidence_block}\n\n"
            f"Question: {request.prompt}"
        )

        kwargs: dict = {
            "api_key": self._api_key,
            "timeout": self._timeout,
        }
        if self._base_url:
            kwargs["base_url"] = self._base_url

        client = openai.OpenAI(**kwargs)

        try:
            completion = client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": _SYSTEM_MESSAGE},
                    {"role": "user", "content": user_content},
                ],
                max_tokens=1024,
                temperature=0.1,  # Low temperature for factual answers
            )
            raw_text = completion.choices[0].message.content or ""
        except Exception as exc:
            logger.warning("OpenAI call failed: %s", exc)
            return LLMResponse(
                answer=None,
                citations=[],
                confidence=0.0,
                unsupported_claims=[f"provider_error: {exc}"],
                requires_human_review=True,
                task_type=request.task_type,
                model_name=self._model,
            )

        citations = self._extract_citations(raw_text, request.evidence_urls)
        answer, unsupported = self._parse_answer(raw_text, citations)
        confidence = 0.8 if citations else 0.0

        return LLMResponse(
            answer=answer,
            citations=citations,
            confidence=confidence,
            unsupported_claims=unsupported,
            requires_human_review=(not citations or confidence < 0.7),
            task_type=request.task_type,
            model_name=self._model,
            raw_response=raw_text,
        )

    @staticmethod
    def _format_evidence(request: LLMRequest) -> str:
        if not request.evidence_texts:
            return "(No evidence provided)"
        parts = []
        for i, text in enumerate(request.evidence_texts):
            url = request.evidence_urls[i] if i < len(request.evidence_urls) else "unknown"
            parts.append(f"[{i + 1}] Source: {url}\n{text[:3000]}")
        return "\n\n".join(parts)

    @staticmethod
    def _extract_citations(raw_text: str, evidence_urls: list[str]) -> list[Citation]:
        citations = []
        for url in evidence_urls:
            if url in raw_text:
                citations.append(Citation(source_url=url))
        return citations

    @staticmethod
    def _parse_answer(raw_text: str, citations: list[Citation]) -> tuple[str | None, list[str]]:
        if not citations:
            return None, ["no_citations_found"]
        answer_part = raw_text.split("CITATIONS:")[0].strip()
        return answer_part or None, []
