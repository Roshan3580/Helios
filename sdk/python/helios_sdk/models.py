from typing import Literal

SpanType = Literal["input", "rag", "llm", "tool", "output", "evaluator"]
SpanStatus = Literal["success", "warning", "error"]
TraceStatus = Literal["success", "warning", "error"]

SPAN_TYPES: set[str] = {"input", "rag", "llm", "tool", "output", "evaluator"}
SPAN_STATUSES: set[str] = {"success", "warning", "error"}
TRACE_STATUSES: set[str] = {"success", "warning", "error"}
