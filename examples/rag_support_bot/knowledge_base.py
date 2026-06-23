"""Deterministic local knowledge base for the RAG support bot demo."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class KnowledgeChunk:
    doc_id: str
    title: str
    body: str
    tags: tuple[str, ...]


KNOWLEDGE_BASE: tuple[KnowledgeChunk, ...] = (
    KnowledgeChunk(
        doc_id="docs/security.md",
        title="API key rotation",
        body=(
            "Rotate API keys by creating a new key, updating clients, validating traffic, "
            "then revoking the old key. Use overlapping validity windows to avoid downtime."
        ),
        tags=("api", "keys", "rotation", "security", "downtime"),
    ),
    KnowledgeChunk(
        doc_id="docs/observability.md",
        title="Trace export",
        body=(
            "Helios supports exporting trace summaries to Datadog via webhook adapters. "
            "Configure HELIOS_EXPORT_WEBHOOK and map span fields in the project settings."
        ),
        tags=("datadog", "export", "traces", "observability"),
    ),
    KnowledgeChunk(
        doc_id="docs/rag-quality.md",
        title="Citation coverage",
        body=(
            "Missing citations usually indicate low retrieval recall or weak reranking. "
            "Inspect retriever hit rate, chunk overlap, and reranker uplift in RAG analytics."
        ),
        tags=("rag", "citation", "reranker", "retrieval", "quality"),
    ),
    KnowledgeChunk(
        doc_id="docs/billing.md",
        title="Annual refunds",
        body="Annual plans include a 14-day refund window after purchase for new subscriptions.",
        tags=("billing", "refund", "annual"),
    ),
)


def keyword_search(query: str, top_k: int = 3) -> list[tuple[KnowledgeChunk, float]]:
    terms = [term.strip("?.!,").lower() for term in query.lower().split() if term.strip("?.!,")]
    scored: list[tuple[KnowledgeChunk, float]] = []

    for chunk in KNOWLEDGE_BASE:
        haystack = " ".join([chunk.title, chunk.body, " ".join(chunk.tags)]).lower()
        score = sum(1.0 for term in terms if term in haystack)
        if score > 0:
            scored.append((chunk, score))

    scored.sort(key=lambda item: item[1], reverse=True)
    return scored[:top_k]


def rerank_chunks(query: str, candidates: list[tuple[KnowledgeChunk, float]]) -> list[tuple[KnowledgeChunk, float]]:
    """Simple deterministic reranker: boost title/tag overlap."""
    reranked: list[tuple[KnowledgeChunk, float]] = []
    query_lower = query.lower()
    for chunk, score in candidates:
        boost = 0.0
        if any(tag in query_lower for tag in chunk.tags):
            boost += 0.5
        if chunk.title.lower() in query_lower:
            boost += 0.25
        reranked.append((chunk, round(score + boost, 2)))
    reranked.sort(key=lambda item: item[1], reverse=True)
    return reranked
