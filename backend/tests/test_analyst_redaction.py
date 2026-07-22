"""Attribute safety and redaction for the analyst engine."""

from app.analyst.redaction import (
    bound_string,
    has_token_data,
    is_content_like_key,
    is_secret_like_key,
    read_number_attr,
    read_string_attr,
    sanitize_supporting_attributes,
)


class TestKeyClassification:
    def test_secret_like_keys(self):
        assert is_secret_like_key("Authorization")
        assert is_secret_like_key("x-api-key")
        assert is_secret_like_key("session_id")
        assert is_secret_like_key("db_password")
        assert not is_secret_like_key("gen_ai.request.model")
        assert not is_secret_like_key("tool.name")

    def test_content_like_keys(self):
        assert is_content_like_key("gen_ai.content.prompt")
        assert is_content_like_key("tool.result")
        assert is_content_like_key("retrieval.query")
        assert is_content_like_key("agent.input")
        assert not is_content_like_key("gen_ai.request.model")


class TestReaders:
    def test_string_and_number_readers(self):
        attrs = {
            "tool.name": "  search  ",
            "gen_ai.usage.input_tokens": 12,
            "gen_ai.usage.output_tokens": "7",
            "bad_tokens": "not-a-number",
            "nan": float("nan"),
            "obj": {"nested": 1},
            "lst": [1, 2],
        }
        assert read_string_attr(attrs, "tool.name") == "search"
        assert read_number_attr(attrs, "gen_ai.usage.input_tokens") == 12.0
        assert read_number_attr(attrs, "gen_ai.usage.output_tokens") == 7.0
        assert read_number_attr(attrs, "bad_tokens") is None
        assert read_number_attr(attrs, "nan") is None
        assert read_string_attr(attrs, "obj") is None
        assert read_string_attr(attrs, "lst") is None
        assert read_string_attr(None, "tool.name") is None
        assert read_string_attr("not-a-dict", "tool.name") is None

    def test_bound_string(self):
        assert bound_string("a" * 100, max_len=10).endswith("…")
        assert len(bound_string("a" * 100, max_len=10)) == 10
        assert bound_string(True) == "true"
        assert bound_string({"x": 1}) is None


class TestSanitize:
    def test_allowlist_and_secret_exclusion(self):
        attrs = {
            "helios.span.type": "llm",
            "gen_ai.request.model": "gpt-4o",
            "gen_ai.usage.input_tokens": 11,
            "authorization": "Bearer secret",
            "api_key": "hel_proj_x",
            "gen_ai.content.prompt": "ignore previous instructions",
            "tool.result": "SECRET_DOC",
            "unknown.metric": 99,
        }
        out = sanitize_supporting_attributes(attrs)
        assert out["helios.span.type"] == "llm"
        assert out["gen_ai.request.model"] == "gpt-4o"
        assert out["gen_ai.usage.input_tokens"] == 11
        assert "authorization" not in out
        assert "api_key" not in out
        assert "gen_ai.content.prompt" not in out
        assert "tool.result" not in out
        assert "unknown.metric" not in out

    def test_malformed_tokens_do_not_count(self):
        assert not has_token_data({"gen_ai.usage.input_tokens": "abc"})
        assert has_token_data({"gen_ai.usage.input_tokens": 3})
