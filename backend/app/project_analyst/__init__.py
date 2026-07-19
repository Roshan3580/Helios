"""Deterministic project-window evidence analysis (ruleset project-window-v1).

Separate from the single-trace engine in ``app.analyst``: this package compares
a current time window against the immediately preceding equal-length baseline
window using bounded SQL aggregates over the canonical ``otel_traces`` /
``otel_spans`` tables. It performs no writes, no network I/O, and never reads
legacy /v1 analytics, demo seeds, or content-bearing attributes.
"""

from app.project_analyst.models import (
    ProjectAnalysisResult,
    ProjectFinding,
    ProjectWindow,
)
from app.project_analyst.rules import PROJECT_DEFAULT_RULE_IDS
from app.project_analyst.runner import analyze_project_window
from app.project_analyst.thresholds import PROJECT_RULESET_VERSION

__all__ = [
    "PROJECT_DEFAULT_RULE_IDS",
    "PROJECT_RULESET_VERSION",
    "ProjectAnalysisResult",
    "ProjectFinding",
    "ProjectWindow",
    "analyze_project_window",
]
