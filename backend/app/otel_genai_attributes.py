"""Centralized GenAI attribute keys recognized by Helios analytics.

Only aliases that are standards-compatible and present in the Helios SDK /
OpenAI instrumentor are listed. Analytics must not invent token splits, cost,
or model labels when these attributes are absent.
"""

# Token usage (OpenTelemetry GenAI semantic conventions).
INPUT_TOKEN_KEYS: tuple[str, ...] = ("gen_ai.usage.input_tokens",)
OUTPUT_TOKEN_KEYS: tuple[str, ...] = ("gen_ai.usage.output_tokens",)

# Model identity: request preferred, response as fallback.
REQUEST_MODEL_KEY = "gen_ai.request.model"
RESPONSE_MODEL_KEY = "gen_ai.response.model"
