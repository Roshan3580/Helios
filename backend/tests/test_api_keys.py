"""Unit tests for API-key generation, hashing, parsing, and scope validation.

These are pure-function tests (no database)."""

import base64
import inspect

import pytest

from app.security import api_keys
from app.security.api_keys import (
    KEY_TOKEN_PREFIX,
    VALID_SCOPES,
    generate_api_key,
    hash_token,
    parse_lookup_prefix,
    validate_scopes,
    verify_token,
)


class TestGeneration:
    def test_token_has_documented_shape(self):
        generated = generate_api_key()
        assert generated.token.startswith(f"{KEY_TOKEN_PREFIX}_")
        parts = generated.token.split("_")
        assert parts[0] == "hel" and parts[1] == "proj"
        # lookup prefix present and matches the parsed value
        assert parse_lookup_prefix(generated.token) == generated.key_prefix
        assert generated.key_prefix == parts[2]

    def test_secret_entropy_is_sufficient(self):
        generated = generate_api_key()
        secret = "_".join(generated.token.split("_")[3:])
        # token_urlsafe(32) -> >=256 bits; decoded secret has >= 32 bytes.
        padded = secret + "=" * (-len(secret) % 4)
        decoded = base64.urlsafe_b64decode(padded)
        assert len(decoded) >= 32

    def test_two_keys_differ(self):
        a = generate_api_key()
        b = generate_api_key()
        assert a.token != b.token
        assert a.key_prefix != b.key_prefix
        assert a.key_hash != b.key_hash


class TestHashing:
    def test_hash_is_not_plaintext(self):
        generated = generate_api_key()
        assert generated.key_hash != generated.token
        assert generated.token not in generated.key_hash
        # sha256 hex digest length
        assert len(generated.key_hash) == 64

    def test_verify_succeeds_for_correct_token(self):
        generated = generate_api_key()
        assert verify_token(generated.token, generated.key_hash) is True

    def test_verify_fails_for_changed_token(self):
        generated = generate_api_key()
        tampered = generated.token[:-1] + ("A" if generated.token[-1] != "A" else "B")
        assert verify_token(tampered, generated.key_hash) is False

    def test_hash_is_deterministic(self):
        generated = generate_api_key()
        assert hash_token(generated.token) == generated.key_hash

    def test_verify_uses_constant_time_comparison(self):
        # Guard against a regression to a plain `==` comparison.
        source = inspect.getsource(api_keys.verify_token)
        assert "compare_digest" in source


class TestParsing:
    def test_malformed_tokens_return_none(self):
        assert parse_lookup_prefix("") is None
        assert parse_lookup_prefix("nope") is None
        assert parse_lookup_prefix("hel_proj_only") is None  # no secret
        assert parse_lookup_prefix("wrong_prefix_abc_secret") is None
        assert parse_lookup_prefix("hel_proj__secret") is None  # empty lookup


class TestScopeValidation:
    def test_valid_scopes_normalized_and_deduped(self):
        assert validate_scopes(["traces:ingest", "traces:read", "traces:read"]) == [
            "traces:ingest",
            "traces:read",
        ]

    def test_empty_scopes_rejected(self):
        with pytest.raises(ValueError):
            validate_scopes([])

    def test_unknown_scope_rejected(self):
        with pytest.raises(ValueError):
            validate_scopes(["traces:delete"])

    def test_valid_scope_set(self):
        assert VALID_SCOPES == {"traces:ingest", "traces:read"}
