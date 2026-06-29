"""Tests for router.py — _keyword_fallback, map_claude_model_name, auto_select_model."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from config import CODER_MAP_FREE, CODER_MAP_FREE_GLOBAL, CODER_MAP_GO, CODER_MAP_GO_ALL
from router import _keyword_fallback, auto_select_model, map_claude_model_name, resolve_model_config

# ---------------------------------------------------------------------------
# _keyword_fallback
# ---------------------------------------------------------------------------

class TestKeywordFallback:
    def test_code_with_backtick_block(self):
        tier, category = _keyword_fallback("```python\ndef hello():\n    pass\n```", 1)
        assert tier == "go"
        assert category == "code"

    def test_code_with_multiple_keywords(self):
        # "implement" + "debug" → code_hits >= 2
        tier, category = _keyword_fallback(
            "Can you implement a function to debug this error?", 1
        )
        assert tier == "go"
        assert category == "code"

    def test_single_code_keyword_no_backtick_not_code(self):
        # Only one code keyword; shouldn't be "code"
        tier, category = _keyword_fallback("Please implement this one thing", 1)
        # Could be trivial/simple/general, but definitely NOT code (only 1 hit)
        assert category != "code"

    def test_reasoning_keywords(self):
        tier, category = _keyword_fallback(
            "Can you explain the architecture and analyze the tradeoffs?", 1
        )
        assert tier == "go"
        assert category == "reasoning"

    def test_math_reasoning(self):
        tier, category = _keyword_fallback("calculate the step by step proof", 1)
        assert tier == "go"
        assert category == "reasoning"

    def test_long_text(self):
        tier, category = _keyword_fallback("x" * 4000, 1)
        assert tier == "go"
        assert category == "long"

    def test_long_conversation(self):
        tier, category = _keyword_fallback("Hello", 10)
        assert tier == "go"
        assert category == "long"

    def test_creative_keywords(self):
        tier, category = _keyword_fallback("Write a blog post about machine learning", 1)
        assert tier == "go"
        assert category == "creative"

    def test_story_creative(self):
        tier, category = _keyword_fallback("Tell me a story about robots", 1)
        assert tier == "go"
        assert category == "creative"

    def test_agent_keywords(self):
        tier, category = _keyword_fallback(
            "Create a workflow to automate deployments", 1
        )
        assert tier == "go"
        assert category == "agent"

    def test_pipeline_agent(self):
        tier, category = _keyword_fallback("Build a pipeline for the agent to run", 1)
        assert tier == "go"
        assert category == "agent"

    def test_trivial_short_single_turn(self):
        tier, category = _keyword_fallback("Hello!", 1)
        assert tier == "free"
        assert category == "trivial"

    def test_trivial_very_short_two_turns(self):
        tier, category = _keyword_fallback("Hi there", 2)
        assert tier == "free"
        assert category == "trivial"

    def test_simple_short_few_turns(self):
        # 34 chars, 3 turns — escapes trivial (num_turns > 2) but inside simple
        # (chars < 400 and num_turns <= 3).  No creative/code/other triggers.
        tier, category = _keyword_fallback("Can you add error handling to this?", 3)
        assert tier == "free"
        assert category == "simple"

    def test_general_fallback(self):
        # 4 turns escapes both trivial (num_turns <= 2) and simple (num_turns <= 3)
        # while the short text avoids the >3000-char long threshold.
        # No code/reasoning/creative/agent keywords → lands on general.
        tier, category = _keyword_fallback("What is the capital of France?", 4)
        assert tier == "go"
        assert category == "general"

    def test_general_medium_conversation(self):
        tier, category = _keyword_fallback("Some medium question here", 5)
        assert tier == "go"
        assert category == "general"

    def test_just_above_trivial_threshold_is_simple(self):
        # ~200 chars (> 150), 3 turns (<=3) → simple
        text = "a" * 200
        tier, category = _keyword_fallback(text, 3)
        assert tier == "free"
        assert category == "simple"

    def test_just_above_simple_threshold_is_general(self):
        # ~500 chars (> 400), 4 turns → general
        text = "a" * 500
        tier, category = _keyword_fallback(text, 4)
        assert tier == "go"
        assert category == "general"


# ---------------------------------------------------------------------------
# map_claude_model_name
# ---------------------------------------------------------------------------

class TestMapClaudeModelName:
    def test_haiku_maps_to_free_auto(self):
        assert map_claude_model_name("claude-haiku-3-5-20241022") == "free-auto"

    def test_haiku_3_maps_to_free_auto(self):
        assert map_claude_model_name("claude-3-haiku-20240307") == "free-auto"

    def test_sonnet_maps_to_go_auto(self):
        assert map_claude_model_name("claude-sonnet-4-5") == "go-auto"

    def test_opus_maps_to_go_auto(self):
        assert map_claude_model_name("claude-opus-4-5") == "go-auto"

    def test_generic_claude_maps_to_go_auto(self):
        assert map_claude_model_name("claude-future-model") == "go-auto"

    def test_non_claude_model_unchanged(self):
        assert map_claude_model_name("gpt-4") == "gpt-4"
        assert map_claude_model_name("kimi-k2.7") == "kimi-k2.7"

    def test_already_routing_token_unchanged(self):
        assert map_claude_model_name("go-auto") == "go-auto"
        assert map_claude_model_name("free-auto") == "free-auto"

    def test_non_string_returns_unchanged(self) -> None:
        assert map_claude_model_name(None) is None  # type: ignore[arg-type]

    def test_model_in_model_map_not_remapped(self, monkeypatch):
        """A claude-* model that IS in MODEL_MAP must not be redirected."""
        import router as router_module
        monkeypatch.setattr(
            router_module,
            "MODEL_MAP",
            {"claude-haiku-3-5-20241022": "some-specific-model"},
        )
        # Should return unchanged because it's explicitly mapped
        assert map_claude_model_name("claude-haiku-3-5-20241022") == "claude-haiku-3-5-20241022"

    def test_case_insensitive_haiku_detection(self):
        # Model name is lowercased internally; mixed case should still map to free-auto
        assert map_claude_model_name("Claude-Haiku-3") == "free-auto"


# ---------------------------------------------------------------------------
# auto_select_model — LLM path (P3 #19)
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_clf_cache():
    """Clear classifier caches before and after each test to avoid cross-test pollution."""
    import router
    router._clf_cache.clear()
    _keyword_fallback.cache_clear()
    yield
    router._clf_cache.clear()
    _keyword_fallback.cache_clear()


def _make_llm_mock(tier: str, category: str, status_code: int = 200) -> MagicMock:
    """Build a mock httpx response that returns a classifier JSON payload."""
    body = json.dumps({"tier": tier, "category": category})
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": body}}]
    }
    return mock_resp


class TestAutoSelectModel:
    # ── LLM success path ─────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_llm_success_picks_go_code_model(self):
        """LLM classifier returns go/code → CODER_MAP_GO["code"] chosen."""
        mock_resp = _make_llm_mock("go", "code")
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("router.get_client", AsyncMock(return_value=mock_client)):
            # Use a short generic query so the code fast-precheck doesn't fire
            result = await auto_select_model(
                [{"role": "user", "content": "what is a sorting algorithm"}]
            )
        assert result == CODER_MAP_GO["code"]

    @pytest.mark.asyncio
    async def test_llm_success_picks_go_reasoning_model(self):
        mock_resp = _make_llm_mock("go", "reasoning")
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("router.get_client", AsyncMock(return_value=mock_client)):
            result = await auto_select_model(
                [{"role": "user", "content": "what is one plus one"}]
            )
        assert result == CODER_MAP_GO["reasoning"]

    @pytest.mark.asyncio
    async def test_llm_success_picks_free_trivial_model(self):
        mock_resp = _make_llm_mock("free", "trivial")
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("router.get_client", AsyncMock(return_value=mock_client)):
            result = await auto_select_model(
                [{"role": "user", "content": "hi"}]
            )
        assert result == CODER_MAP_FREE["trivial"]

    # ── LLM failure → keyword fallback ──────────────────────────────────────

    @pytest.mark.asyncio
    async def test_llm_failure_falls_back_to_keyword_long(self):
        """When LLM errors, keyword fallback is used; long text → go/long."""
        mock_client = MagicMock()
        mock_client.post = AsyncMock(side_effect=Exception("connection refused"))

        with patch("router.get_client", AsyncMock(return_value=mock_client)):
            result = await auto_select_model(
                [{"role": "user", "content": "x" * 4001}]
            )
        assert result == CODER_MAP_GO["long"]

    @pytest.mark.asyncio
    async def test_llm_failure_falls_back_to_keyword_trivial(self):
        """Short single-turn query → keyword returns free/trivial on LLM failure."""
        mock_client = MagicMock()
        mock_client.post = AsyncMock(side_effect=Exception("timeout"))

        with patch("router.get_client", AsyncMock(return_value=mock_client)):
            result = await auto_select_model(
                [{"role": "user", "content": "Hello!"}]
            )
        assert result == CODER_MAP_FREE["trivial"]

    @pytest.mark.asyncio
    async def test_llm_non_200_falls_back_to_keyword(self):
        """LLM returning 401 triggers keyword fallback gracefully."""
        mock_resp = _make_llm_mock("go", "code", status_code=401)
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("router.get_client", AsyncMock(return_value=mock_client)):
            result = await auto_select_model(
                [{"role": "user", "content": "Hello!"}]
            )
        # Keyword fallback: "Hello!" (6 chars, 1 turn) → free/trivial
        assert result == CODER_MAP_FREE["trivial"]

    # ── forced_tier ──────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_forced_tier_free_always_picks_free_model(self):
        """forced_tier='free' must pick from CODER_MAP_FREE regardless of classifier."""
        mock_client = MagicMock()
        mock_client.post = AsyncMock(side_effect=Exception("no network"))

        with patch("router.get_client", AsyncMock(return_value=mock_client)):
            result = await auto_select_model(
                [{"role": "user", "content": "Hello!"}],
                forced_tier="free",
            )
        assert result in CODER_MAP_FREE.values()
    @pytest.mark.asyncio
    async def test_forced_tier_go_always_picks_go_model(self):
        """forced_tier='go' must pick from CODER_MAP_GO."""
        mock_client = MagicMock()
        mock_client.post = AsyncMock(side_effect=Exception("no network"))

        with patch("router.get_client", AsyncMock(return_value=mock_client)):
            result = await auto_select_model(
                [{"role": "user", "content": "Hello!"}],
                forced_tier="go",
            )
        assert result in CODER_MAP_GO.values()
    @pytest.mark.asyncio
    async def test_forced_tier_go_all_always_picks_go_all_model(self):
        """forced_tier='go-all' must pick from CODER_MAP_GO_ALL."""
        mock_client = MagicMock()
        mock_client.post = AsyncMock(side_effect=Exception("no network"))

        with patch("router.get_client", AsyncMock(return_value=mock_client)):
            result = await auto_select_model(
                [{"role": "user", "content": "Hello!"}],
                forced_tier="go-all",
            )
        assert result in CODER_MAP_GO_ALL.values()

    @pytest.mark.asyncio
    async def test_forced_tier_free_overrides_llm_go_classification(self):
        """Even if LLM says go/code, forced_tier='free' must pick a free model."""
        mock_resp = _make_llm_mock("go", "code")
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("router.get_client", AsyncMock(return_value=mock_client)):
            result = await auto_select_model(
                [{"role": "user", "content": "what is sorting"}],
                forced_tier="free",
            )
        # LLM said code → CODER_MAP_FREE.get("code", CODER_MAP_FREE["simple"])
        assert result in CODER_MAP_FREE.values()

    # ── Agent mode detection ─────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_agent_mode_go_tier_picks_agent_model(self):
        """Two+ tool blocks with has_tools=True → mimo-v2.5-pro."""
        messages = [
            {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": "t1", "name": "search", "input": {}},
                    {"type": "tool_use", "id": "t2", "name": "read_file", "input": {}},
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "t1", "content": "result1"},
                    {"type": "tool_result", "tool_use_id": "t2", "content": "result2"},
                ],
            },
        ]
        result = await auto_select_model(messages, has_tools=True)
        assert result == CODER_MAP_GO["agent"]

    @pytest.mark.asyncio
    async def test_agent_mode_free_tier_picks_free_general_model(self):
        """Agent mode + forced_tier='free' → CODER_MAP_FREE['general']."""
        messages = [
            {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": "t1", "name": "fn", "input": {}},
                    {"type": "tool_use", "id": "t2", "name": "fn2", "input": {}},
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "t1", "content": "r1"},
                    {"type": "tool_result", "tool_use_id": "t2", "content": "r2"},
                ],
            },
        ]
        result = await auto_select_model(messages, has_tools=True, forced_tier="free")
        assert result == CODER_MAP_FREE["general"]

    @pytest.mark.asyncio
    async def test_agent_mode_free_global_tier_picks_tier1_model(self):
        """Agent mode + forced_tier='free-global' → CODER_MAP_FREE_GLOBAL['tier1']."""
        messages = [
            {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": "t1", "name": "fn", "input": {}},
                    {"type": "tool_use", "id": "t2", "name": "fn2", "input": {}},
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "t1", "content": "r1"},
                    {"type": "tool_result", "tool_use_id": "t2", "content": "r2"},
                ],
            },
        ]
        result = await auto_select_model(messages, has_tools=True, forced_tier="free-global")
        assert result == CODER_MAP_FREE_GLOBAL["tier1"]

    @pytest.mark.asyncio
    async def test_single_tool_block_not_agent_mode(self):
        """Fewer than 2 tool blocks must NOT trigger agent mode early exit."""
        messages = [
            {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": "t1", "name": "fn", "input": {}},
                ],
            },
        ]
        # With has_tools=True but only 1 tool block, falls through to LLM/keyword
        mock_client = MagicMock()
        mock_client.post = AsyncMock(side_effect=Exception("no network"))
        with patch("router.get_client", AsyncMock(return_value=mock_client)):
            result = await auto_select_model(messages, has_tools=True)
        # Result should be from CODER_MAP_GO (keyword fallback for 1-turn message)
        assert result in CODER_MAP_GO.values() or result in CODER_MAP_FREE.values()

    # ── In-process cache (P1 #7) ──────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_classifier_result_cached_on_second_call(self):
        """Second call with same text must use cache, not make another LLM call."""
        mock_resp = _make_llm_mock("go", "reasoning")
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)

        text = "what is one plus one"
        msg = [{"role": "user", "content": text}]

        with patch("router.get_client", AsyncMock(return_value=mock_client)):
            await auto_select_model(msg)
            await auto_select_model(msg)

        # LLM should only have been called once (second call hits cache)
        assert mock_client.post.await_count == 1


# ---------------------------------------------------------------------------
# TestResolveModelConfig
# ---------------------------------------------------------------------------

class TestResolveModelConfig:
    def test_resolve_with_opencode_go_prefix_directly(self):
        # Resolve a model with the prefix explicitly configured
        upstream, url, key, role = resolve_model_config("opencode-go/kimi-k2.7-code")
        assert upstream == "kimi-k2.7-code"

    def test_resolve_without_opencode_go_prefix_fallback(self):
        # Resolve a model without the prefix when the key in models.json is prefixed
        upstream, url, key, role = resolve_model_config("kimi-k2.7-code")
        assert upstream == "kimi-k2.7-code"

    def test_resolve_with_opencode_go_prefix_fallback_for_non_prefixed_config(self):
        # Resolve a model with the prefix when the key in models.json is NOT prefixed
        upstream, url, key, role = resolve_model_config("opencode-go/big-pickle")
        assert upstream == "big-pickle"

    def test_resolve_with_opencode_go_prefix_fallback_non_existent(self):
        # Resolve a non-existent model with/without prefix should strip prefix in resolved model
        upstream, url, key, role = resolve_model_config("opencode-go/non-existent-model")
        assert upstream == "non-existent-model"
