"""Ollama LLM provider.

Calls a locally-running Ollama instance (https://ollama.com).

Configuration (via environment or Settings):
  OLLAMA_BASE_URL   Ollama server URL (default: http://localhost:11434)
  OLLAMA_MODEL      Model to use (default: llama3)

Evidence grounding:
  evidence_texts from the request are injected as context in the system
  prompt.  The model is instructed to cite only text from the provided
  context.  Citations are extracted from the response heuristically.
"""

from __future__ import annotations

import logging
from typing import Any

from app.llm.provider import LLMProvider
from app.llm.schemas import Citation, LLMRequest, LLMResponse

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "http://localhost:11434"
_DEFAULT_MODEL = "llama3"

_SYSTEM_PROMPT_TEMPLATE = """You are a legal research assistant helping a human reviewer.
You must ONLY use the evidence texts provided below.
Do NOT make claims unsupported by the provided evidence.
Do NOT assign guilt, infer criminality, score dangerousness, or make legal conclusions.
Do NOT recommend publishing any record.
If you cannot answer from the provided evidence, say: "I cannot answer without cited evidence."

Evidence texts:
{evidence_block}

Answer the question below using ONLY the evidence above.
Include a "CITATIONS:" section at the end listing the source URLs you used.
"""


class OllamaProvider(LLMProvider):
    """LLM provider that calls a local Ollama server."""

    def __init__(
        self,
        base_url: str = _DEFAULT_BASE_URL,
        model: str = _DEFAULT_MODEL,
        timeout: float = 60.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

    @property
    def provider_name(self) -> str:
        return f"OllamaProvider({self._model})"

    def _call(self, request: LLMRequest) -> LLMResponse:
        try:
            import httpx
        except ImportError:
            return LLMResponse(
                answer=None,
                citations=[],
                confidence=0.0,
                unsupported_claims=["httpx not installed"],
                requires_human_review=True,
                task_type=request.task_type,
                model_name=self._model,
            )

        evidence_block = self._format_evidence(request)
        system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(evidence_block=evidence_block)
        full_prompt = f"{system_prompt}\n\nQuestion: {request.prompt}"

        payload: dict[str, Any] = {
            "model": self._model,
            "prompt": full_prompt,
            "stream": False,
        }

        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.post(
                    f"{self._base_url}/api/generate",
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.warning("Ollama call failed: %s", exc)
            return LLMResponse(
                answer=None,
                citations=[],
                confidence=0.0,
                unsupported_claims=[f"provider_error: {exc}"],
                requires_human_review=True,
                task_type=request.task_type,
                model_name=self._model,
            )

        raw_text: str = data.get("response", "")
        citations = self._extract_citations(raw_text, request.evidence_urls)
        answer, unsupported = self._parse_answer(raw_text, citations)
        confidence = 0.75 if citations else 0.0

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
            parts.append(f"[{i + 1}] Source: {url}\n{text[:2000]}")
        return "\n\n".join(parts)

    @staticmethod
    def _extract_citations(raw_text: str, evidence_urls: list[str]) -> list[Citation]:
        """Extract citations by matching evidence URLs mentioned in the response."""
        citations = []
        for url in evidence_urls:
            if url in raw_text:
                citations.append(Citation(source_url=url))
        return citations

    @staticmethod
    def _parse_answer(raw_text: str, citations: list[Citation]) -> tuple[str | None, list[str]]:
        """Split the raw response into answer and unsupported claims."""
        if not citations:
            return None, ["no_citations_found"]
        # Remove the CITATIONS section from the visible answer
        answer_part = raw_text.split("CITATIONS:")[0].strip()
        return answer_part or None, []
