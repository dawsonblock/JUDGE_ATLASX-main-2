"""LLM integration for THE-JUDGE reviewer assistance.

This package provides a citation-locked LLM adapter boundary.

Architecture:
  - All LLM calls go through LLMProvider (provider.py)
  - Concrete providers: OllamaProvider, OpenAIProvider
  - ReviewerAssistant orchestrates evidence-grounded queries
  - All responses carry citations, confidence, and unsupported_claims
  - LLM may NEVER publish records, assign guilt, or make legal conclusions

Import hierarchy:
  app.llm.schemas          → data contracts (no I/O)
  app.llm.provider         → abstract base
  app.llm.ollama_provider  → Ollama implementation
  app.llm.openai_provider  → OpenAI implementation
  app.llm.reviewer_assistant → orchestration layer
"""
