"""Versioned thresholds and hard bounds for the project-window ruleset.

Centralized so a later ruleset version can adjust values without touching rule
implementations. None of these values are overridable through the API.
"""

from __future__ import annotations

PROJECT_RULESET_VERSION = "project-window-v1"

# Window semantics (request-level; also validated by the API schema).
MIN_WINDOW_HOURS = 1
MAX_WINDOW_HOURS = 720
DEFAULT_WINDOW_HOURS = 24

# ---------------------------------------------------------------------------
# Hard bounds on candidate/example extraction. Aggregate metrics (counts,
# percentiles, rates) always cover every matching row; only example traces,
# per-entity breakdowns, and the Python-side error-span candidate set are
# capped. Truncation is reported in the response bounds metadata.
# ---------------------------------------------------------------------------
MAX_PROJECT_FINDINGS = 50
MAX_EXAMPLE_TRACES_PER_FINDING = 5
MAX_SERVICES_ANALYZED = 100
MAX_MODELS_ANALYZED = 100
MAX_ERROR_GROUPS = 50
# The one bounded candidate load: ERROR span rows fetched (newest first) for
# deterministic signature clustering. Chosen instead of the suggested
# MAX_CANDIDATE_TRACES because error-span clustering is the only place rows
# (rather than aggregates) are pulled into Python.
MAX_ERROR_SPAN_CANDIDATES = 500

# Bounded supporting span IDs attached to a single finding.
MAX_SUPPORTING_SPAN_IDS = 10

# ---------------------------------------------------------------------------
# Rule 1 — service_error_rate_regression
# ---------------------------------------------------------------------------
ERROR_RATE_MIN_TRACES_PER_WINDOW = 10
ERROR_RATE_MIN_PP_INCREASE = 0.10          # +10 percentage points
ERROR_RATE_ERROR_PP_INCREASE = 0.25        # +25 pp -> severity error
ERROR_RATE_MIN_RELATIVE_FACTOR = 1.5       # unless baseline rate is zero
ERROR_RATE_ZERO_BASELINE_MIN_ERRORS = 3
REGRESSION_HIGH_CONFIDENCE_MIN_SAMPLE = 30  # per window (traces or spans)

# ---------------------------------------------------------------------------
# Rules 2 & 3 — service_latency_regression / model_latency_regression
# ---------------------------------------------------------------------------
LATENCY_MIN_SAMPLE_PER_WINDOW = 10          # traces (rule 2) / spans (rule 3)
LATENCY_MIN_FACTOR = 1.5
LATENCY_ERROR_FACTOR = 2.0
LATENCY_MIN_ABSOLUTE_INCREASE_MS = 100.0

# ---------------------------------------------------------------------------
# Rule 4 — model_token_usage_regression
# ---------------------------------------------------------------------------
TOKEN_MIN_SPANS_PER_WINDOW = 10
TOKEN_MIN_FACTOR = 1.5
TOKEN_MIN_ABSOLUTE_INCREASE = 500.0
TOKEN_HIGH_CONFIDENCE_MIN_SPANS = 30

# ---------------------------------------------------------------------------
# Rule 5 — trace_latency_outliers
# ---------------------------------------------------------------------------
OUTLIER_MIN_CURRENT_TRACES = 20
OUTLIER_P95_FACTOR = 2.0
OUTLIER_MIN_DURATION_MS = 500.0
OUTLIER_ERROR_MAX_FACTOR = 4.0

# ---------------------------------------------------------------------------
# Rule 6 — recurring_error_cluster
# ---------------------------------------------------------------------------
ERROR_CLUSTER_MIN_OCCURRENCES = 3
ERROR_CLUSTER_MIN_DISTINCT_TRACES = 2
ERROR_CLUSTER_ERROR_OCCURRENCES = 10
# Signature normalization bounds (redaction, not presentation).
SIGNATURE_MESSAGE_MAX_LEN = 64
SIGNATURE_TOKEN_MAX_LEN = 24
SIGNATURE_EXCEPTION_TYPE_MAX_LEN = 64

# ---------------------------------------------------------------------------
# Rule 7 — genai_instrumentation_gap
# ---------------------------------------------------------------------------
GENAI_GAP_MIN_MODEL_LIKE_SPANS = 5
GENAI_GAP_INFO_RATE = 0.20
GENAI_GAP_WARNING_RATE = 0.50

# ---------------------------------------------------------------------------
# Rule 8 — error_concentration_by_service
# ---------------------------------------------------------------------------
CONCENTRATION_MIN_ERROR_TRACES = 5
CONCENTRATION_MIN_SERVICES_OBSERVED = 2
CONCENTRATION_WARN_SHARE = 0.70
CONCENTRATION_ERROR_SHARE = 0.90
CONCENTRATION_ERROR_MIN_ERROR_TRACES = 10

# Statement bound (mirrors the single-trace engine).
MAX_STATEMENT_LEN = 512
