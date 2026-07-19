"""Versioned thresholds for the single-trace deterministic ruleset.

Centralized so later ruleset versions can adjust values without hunting through
rule implementations.
"""

from __future__ import annotations

RULESET_VERSION = "single-trace-v1"

# latency_concentration
LATENCY_CONCENTRATION_WARN = 0.50
LATENCY_CONCENTRATION_ERROR = 0.80

# repeated sibling calls
REPEATED_SIBLING_MIN_COUNT = 3

# serial_sibling_operations
SERIAL_MIN_SIBLINGS = 3
SERIAL_MIN_PARENT_FRACTION = 0.60
SERIAL_WARN_PARENT_FRACTION = 0.85
# Overlap tolerance for timestamp precision (milliseconds).
SERIAL_OVERLAP_TOLERANCE_MS = 1.0

# Attribute / statement bounds
MAX_ATTR_STRING_LEN = 64
MAX_STATUS_MESSAGE_LEN = 128
MAX_STATEMENT_LEN = 512
MAX_SUPPORTING_ATTRS = 12
