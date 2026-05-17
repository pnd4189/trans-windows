#!/usr/bin/env python3
"""Tests for model_registry.py — pure functions only."""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.lib.model_registry import (
    discover_used_models,
    is_preview,
    model_tier,
    model_version,
    rank_flash_candidates,
    rank_pro_candidates,
)


class TestModelTier:
    def test_pro(self):
        assert model_tier("gemini-3.1-pro-preview") == "pro"
        assert model_tier("gemini-2.5-pro") == "pro"
        assert model_tier("gemini-4-pro") == "pro"

    def test_flash(self):
        assert model_tier("gemini-2.5-flash") == "flash"
        assert model_tier("gemini-3-flash-preview") == "flash"

    def test_lite(self):
        assert model_tier("gemini-2.5-flash-lite") == "lite"
        assert model_tier("gemini-2.5-flash-8b") == "lite"

    def test_ultra(self):
        assert model_tier("gemini-ultra") == "ultra"

    def test_unknown(self):
        assert model_tier("random") == "unknown"
        assert model_tier("") == "unknown"
        assert model_tier(None) == "unknown"

    def test_flash_lite_not_misclassified(self):
        """flash-lite must return 'lite', not 'flash'."""
        assert model_tier("gemini-2.5-flash-lite") == "lite"


class TestModelVersion:
    def test_major_minor(self):
        assert model_version("gemini-3.1-pro-preview") == (3, 1)
        assert model_version("gemini-2.5-flash") == (2, 5)

    def test_major_only(self):
        assert model_version("gemini-4-pro") == (4, 0)

    def test_unparseable(self):
        assert model_version("nope") == (0, 0)
        assert model_version("") == (0, 0)
        assert model_version(None) == (0, 0)


class TestIsPreview:
    def test_preview(self):
        assert is_preview("gemini-3.1-pro-preview") is True

    def test_exp(self):
        assert is_preview("gemini-3-pro-thinking-exp") is True

    def test_experimental(self):
        assert is_preview("gemini-experimental") is True

    def test_ga(self):
        assert is_preview("gemini-2.5-pro") is False
        assert is_preview("gemini-3-flash") is False


class TestRankProCandidates:
    def test_sorts_by_version_desc(self):
        candidates = ["gemini-2.5-pro", "gemini-3.1-pro-preview", "gemini-3-flash-preview"]
        result = rank_pro_candidates(candidates)
        assert result == ["gemini-3.1-pro-preview", "gemini-2.5-pro"]

    def test_ga_before_preview(self):
        candidates = ["gemini-3-pro", "gemini-3-pro-preview", "gemini-2.5-pro"]
        result = rank_pro_candidates(candidates)
        assert result == ["gemini-3-pro", "gemini-3-pro-preview", "gemini-2.5-pro"]

    def test_filters_non_pro(self):
        candidates = ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-ultra"]
        result = rank_pro_candidates(candidates)
        assert result == ["gemini-2.5-pro"]

    def test_empty(self):
        assert rank_pro_candidates([]) == []
        assert rank_pro_candidates(["gemini-2.5-flash"]) == []


class TestRankFlashCandidates:
    def test_sorts_by_version_desc(self):
        candidates = ["gemini-2.5-flash", "gemini-3-flash-preview", "gemini-2.5-pro"]
        result = rank_flash_candidates(candidates)
        assert result == ["gemini-3-flash-preview", "gemini-2.5-flash"]

    def test_filters_non_flash(self):
        candidates = ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.5-flash-lite"]
        result = rank_flash_candidates(candidates)
        assert result == ["gemini-2.5-flash"]

    def test_empty(self):
        assert rank_flash_candidates([]) == []
        assert rank_flash_candidates(["gemini-2.5-pro"]) == []


class TestDiscoverUsedModels:
    def test_returns_list(self):
        result = discover_used_models()
        assert isinstance(result, list)

    def test_all_start_with_gemini(self):
        result = discover_used_models()
        for model in result:
            assert model.startswith("gemini-"), f"Unexpected model: {model}"


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
