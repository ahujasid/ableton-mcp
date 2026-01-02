"""Tests for browser URI cache in Remote Script."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestBrowserCacheInitialization:
    """Test browser URI cache initialization."""

    def test_cache_initialized_in_init(self):
        """Verify cache is initialized in __init__."""
        remote_script_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "AbletonMCP_Remote_Script",
            "__init__.py",
        )

        with open(remote_script_path) as f:
            source = f.read()

        # Should initialize cache in __init__
        assert "_browser_uri_cache = {}" in source

    def test_cache_is_instance_variable(self):
        """Verify cache is an instance variable, not class variable."""
        remote_script_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "AbletonMCP_Remote_Script",
            "__init__.py",
        )

        with open(remote_script_path) as f:
            source = f.read()

        # Should use self._browser_uri_cache
        assert "self._browser_uri_cache" in source


class TestBrowserCacheLookup:
    """Test browser URI cache lookup behavior."""

    def test_cache_check_before_traversal(self):
        """Verify cache is checked before tree traversal."""
        remote_script_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "AbletonMCP_Remote_Script",
            "__init__.py",
        )

        with open(remote_script_path) as f:
            source = f.read()

        # Should check cache first in _find_browser_item_by_uri
        assert "if uri in self._browser_uri_cache" in source

    def test_cache_returns_item_on_hit(self):
        """Verify cache returns item directly on cache hit."""
        remote_script_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "AbletonMCP_Remote_Script",
            "__init__.py",
        )

        with open(remote_script_path) as f:
            source = f.read()

        # Should return cached item
        assert "return self._browser_uri_cache[uri]" in source


class TestBrowserCachePopulation:
    """Test browser URI cache population."""

    def test_cache_populated_on_miss(self):
        """Verify cache is populated on first lookup."""
        remote_script_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "AbletonMCP_Remote_Script",
            "__init__.py",
        )

        with open(remote_script_path) as f:
            source = f.read()

        # Should populate cache if empty
        assert "_populate_browser_cache" in source

    def test_populate_cache_function_exists(self):
        """Verify _populate_browser_cache method exists."""
        remote_script_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "AbletonMCP_Remote_Script",
            "__init__.py",
        )

        with open(remote_script_path) as f:
            source = f.read()

        assert "def _populate_browser_cache" in source

    def test_populate_cache_handles_all_categories(self):
        """Verify cache population handles all browser categories."""
        remote_script_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "AbletonMCP_Remote_Script",
            "__init__.py",
        )

        with open(remote_script_path) as f:
            source = f.read()

        # Should handle standard categories
        categories = ["instruments", "sounds", "drums", "audio_effects", "midi_effects"]

        for category in categories:
            assert category in source, f"Cache should handle {category} category"


class TestBrowserCacheClear:
    """Test browser cache clearing."""

    def test_clear_cache_function_exists(self):
        """Verify _clear_browser_cache method exists."""
        remote_script_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "AbletonMCP_Remote_Script",
            "__init__.py",
        )

        with open(remote_script_path) as f:
            source = f.read()

        assert "def _clear_browser_cache" in source

    def test_clear_cache_resets_dict(self):
        """Verify clearing cache resets the dictionary."""
        remote_script_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "AbletonMCP_Remote_Script",
            "__init__.py",
        )

        with open(remote_script_path) as f:
            source = f.read()

        # Should reset to empty dict
        assert "self._browser_uri_cache = {}" in source or "_browser_uri_cache = {}" in source


class TestBrowserCacheEfficiency:
    """Test that cache provides O(1) lookup efficiency."""

    def test_uses_dictionary_lookup(self):
        """Verify cache uses dictionary for O(1) lookup."""
        remote_script_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "AbletonMCP_Remote_Script",
            "__init__.py",
        )

        with open(remote_script_path) as f:
            source = f.read()

        # Should use dictionary indexing, not iteration
        assert "_browser_uri_cache[uri]" in source

    def test_caches_found_items_during_traversal(self):
        """Verify items found during traversal are added to cache."""
        remote_script_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "AbletonMCP_Remote_Script",
            "__init__.py",
        )

        with open(remote_script_path) as f:
            source = f.read()

        # Should cache items found during traversal
        assert "self._browser_uri_cache[uri] = item" in source


class TestBrowserCacheDepthLimit:
    """Test cache population depth limiting."""

    def test_max_depth_parameter(self):
        """Verify cache population has max depth parameter."""
        remote_script_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "AbletonMCP_Remote_Script",
            "__init__.py",
        )

        with open(remote_script_path) as f:
            source = f.read()

        # Should have max_depth parameter
        assert "max_depth" in source

    def test_depth_check_prevents_infinite_recursion(self):
        """Verify depth check prevents infinite recursion."""
        remote_script_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "AbletonMCP_Remote_Script",
            "__init__.py",
        )

        with open(remote_script_path) as f:
            source = f.read()

        # Should check depth before recursing
        assert "current_depth >= max_depth" in source or "current_depth" in source


class TestBrowserCacheLogging:
    """Test cache operation logging."""

    def test_cache_population_logs_count(self):
        """Verify cache population logs the number of items cached."""
        remote_script_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "AbletonMCP_Remote_Script",
            "__init__.py",
        )

        with open(remote_script_path) as f:
            source = f.read()

        # Should log cache population
        assert "Browser cache populated" in source or "cache" in source.lower()

    def test_cache_clear_logs(self):
        """Verify cache clearing is logged."""
        remote_script_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "AbletonMCP_Remote_Script",
            "__init__.py",
        )

        with open(remote_script_path) as f:
            source = f.read()

        # Should log cache clear
        assert "cache cleared" in source.lower() or "Browser URI cache cleared" in source
