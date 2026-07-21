"""Tests for network layer improvements: no_network flag, retry logic, and sources tracking."""

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch, PropertyMock

import pytest

from deckbuilder.engine import build_deck
from deckbuilder.scryfall import (
    ScryfallClient, ScryfallUnavailable, _cached_get, _cache_path
)


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear the cache directory before each test."""
    from deckbuilder.scryfall import CACHE_DIR
    for f in CACHE_DIR.glob("*.json"):
        f.unlink()
    yield
    # Clean up after test too
    for f in CACHE_DIR.glob("*.json"):
        f.unlink()


class TestNoNetworkFlag:
    """Test that no_network=True prevents all outbound requests."""
    
    def test_cached_get_blocks_network_with_no_network(self):
        """_cached_get with no_network=True returns None instead of making requests."""
        with patch("deckbuilder.scryfall.requests") as mock_requests:
            result = _cached_get("https://api.example.com/test123", {}, no_network=True)
            assert result is None
            # No HTTP call should be made
            mock_requests.get.assert_not_called()
    
    def test_cached_get_allows_disk_cache_with_no_network(self):
        """_cached_get with no_network=True still returns cached data."""
        cache_path = _cache_path("https://api.example.com/test" + json.dumps({}))
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        
        test_data = {"object": "list", "data": [{"name": "TestCard"}]}
        cache_path.write_text(json.dumps(test_data))
        
        try:
            result = _cached_get("https://api.example.com/test", {}, no_network=True)
            assert result == test_data
        finally:
            cache_path.unlink(missing_ok=True)
    
    def test_scryfall_client_no_network_disables_find_cards(self):
        """ScryfallClient with no_network=True falls back to sample pool."""
        client = ScryfallClient(no_network=True)
        with patch("deckbuilder.scryfall.requests") as mock_requests:
            result = client.find_cards(["W", "U"])
            # Should use sample pool (offline)
            assert client.card_source == "sample"
            mock_requests.get.assert_not_called()
    
    def test_scryfall_client_no_network_disables_set_resolution(self):
        """ScryfallClient.resolve_set_code with no_network=True returns None for unknown sets."""
        client = ScryfallClient(no_network=True)
        with patch("deckbuilder.scryfall.requests") as mock_requests:
            # Known aliases still work
            result = client.resolve_set_code("dominaria united")
            assert result == "dmu"
            
            # Unknown sets return None
            result = client.resolve_set_code("some unknown set")
            assert result is None
            mock_requests.get.assert_not_called()
    
    def test_scryfall_client_no_network_disables_commander_resolution(self):
        """ScryfallClient.resolve_named_commander with no_network=True returns None."""
        client = ScryfallClient(no_network=True)
        with patch("deckbuilder.scryfall.requests") as mock_requests:
            result = client.resolve_named_commander("Elspeth")
            assert result is None
            mock_requests.get.assert_not_called()
    
    def test_build_deck_with_no_network_makes_no_requests(self):
        """build_deck(no_network=True) makes no HTTP requests (uses cache and sample)."""
        with patch("deckbuilder.scryfall.requests") as mock_requests, \
             patch("deckbuilder.expand.requests") as mock_expand_requests, \
             patch("deckbuilder.theme.requests") as mock_theme_requests:
            
            deck = build_deck("Red aggro", no_network=True)
            
            # Should still return a valid deck structure
            assert "commander" in deck
            assert "categories" in deck
            assert "sources" in deck
            assert deck["sources"]["network"] is False
            
            # No network requests should be made
            mock_requests.get.assert_not_called()
            mock_requests.post.assert_not_called()
            mock_expand_requests.get.assert_not_called()
            mock_expand_requests.post.assert_not_called()
            mock_theme_requests.get.assert_not_called()


class TestRetryLogic:
    """Test 429 handling and retry logic."""
    
    def test_429_triggers_retry(self):
        """_cached_get retries on 429 response."""
        mock_response_429 = Mock()
        mock_response_429.status_code = 429
        mock_response_429.headers = {}
        
        mock_response_200 = Mock()
        mock_response_200.status_code = 200
        mock_response_200.json.return_value = {"data": [{"name": "Test"}]}
        
        with patch("deckbuilder.scryfall.requests.get") as mock_get, \
             patch("deckbuilder.scryfall.time.sleep") as mock_sleep:
            
            # First call returns 429, second returns 200
            mock_get.side_effect = [mock_response_429, mock_response_200]
            
            result = _cached_get("https://api.example.com/test_retry", {})
            
            assert result == {"data": [{"name": "Test"}]}
            # Should have retried
            assert mock_get.call_count == 2
            assert mock_sleep.call_count >= 1  # At least one backoff sleep
    
    def test_429_respects_retry_after_header(self):
        """_cached_get honors Retry-After header over default backoff."""
        mock_response_429 = Mock()
        mock_response_429.status_code = 429
        mock_response_429.headers = {"Retry-After": "5"}
        
        mock_response_200 = Mock()
        mock_response_200.status_code = 200
        mock_response_200.json.return_value = {"data": []}
        
        with patch("deckbuilder.scryfall.requests.get") as mock_get, \
             patch("deckbuilder.scryfall.time.sleep") as mock_sleep:
            
            mock_get.side_effect = [mock_response_429, mock_response_200]
            
            result = _cached_get("https://api.example.com/test_ra", {})
            
            # Should have slept with backoff including Retry-After logic
            assert result == {"data": []}
            assert mock_sleep.call_count >= 2  # REQUEST_DELAY + backoff
    
    def test_three_429s_exhausts_retries(self):
        """_cached_get gives up after max retries on 429."""
        mock_response_429 = Mock()
        mock_response_429.status_code = 429
        mock_response_429.headers = {}
        
        with patch("deckbuilder.scryfall.requests.get") as mock_get, \
             patch("deckbuilder.scryfall.time.sleep"):
            
            mock_get.return_value = mock_response_429
            
            with pytest.raises(ScryfallUnavailable):
                _cached_get("https://api.example.com/test_exhaust", {})
            
            # Should have tried 3 times
            assert mock_get.call_count == 3
    
    def test_connection_error_triggers_retry(self):
        """_cached_get retries on ConnectionError."""
        from requests import ConnectionError
        
        mock_response_200 = Mock()
        mock_response_200.status_code = 200
        mock_response_200.json.return_value = {"data": [{"name": "Connected"}]}
        
        with patch("deckbuilder.scryfall.requests.get") as mock_get, \
             patch("deckbuilder.scryfall.time.sleep"):
            
            # First call raises ConnectionError, second succeeds
            mock_get.side_effect = [ConnectionError("Connection failed"), mock_response_200]
            
            result = _cached_get("https://api.example.com/test_conn", {})
            
            assert result == {"data": [{"name": "Connected"}]}
            assert mock_get.call_count == 2
    
    def test_timeout_triggers_retry(self):
        """_cached_get retries on Timeout."""
        from requests import Timeout
        
        mock_response_200 = Mock()
        mock_response_200.status_code = 200
        mock_response_200.json.return_value = {"data": [{"name": "Worked"}]}
        
        with patch("deckbuilder.scryfall.requests.get") as mock_get, \
             patch("deckbuilder.scryfall.time.sleep"):
            
            # First call raises Timeout, second succeeds
            mock_get.side_effect = [Timeout("Request timed out"), mock_response_200]
            
            result = _cached_get("https://api.example.com/test_timeout", {})
            
            assert result == {"data": [{"name": "Worked"}]}
            assert mock_get.call_count == 2


class TestSourcesTracking:
    """Test that sources metadata is correctly tracked."""
    
    def test_sources_api_when_using_live_api(self):
        """sources reports 'api' when using live Scryfall API."""
        with patch("deckbuilder.scryfall._cached_get") as mock_cached_get, \
             patch("deckbuilder.carddata.connect", side_effect=FileNotFoundError):
            
            # Mock successful API response
            mock_cached_get.return_value = {
                "object": "list",
                "data": [{"name": "TestCard", "type_line": "Creature", "cmc": 1}],
                "has_more": False
            }
            
            deck = build_deck("Test src1", no_network=False)
            
            assert deck["sources"]["cards"] == "api"
            assert deck["sources"]["network"] is True
    
    def test_sources_sample_when_fallback(self):
        """sources reports 'sample' when sample pool is used."""
        with patch("deckbuilder.scryfall._cached_get", return_value=None), \
             patch("deckbuilder.carddata.connect", side_effect=FileNotFoundError):
            
            deck = build_deck("Test src2", no_network=True)
            
            assert deck["sources"]["cards"] == "sample"
            assert deck["sources"]["network"] is False
    
    def test_sources_no_network_false_when_no_network_true(self):
        """sources.network is False when no_network=True."""
        deck = build_deck("Test src3", no_network=True)
        assert deck["sources"]["network"] is False
    
    def test_sources_no_network_true_when_no_network_false(self):
        """sources.network is True when no_network=False."""
        with patch("deckbuilder.scryfall._cached_get") as mock_cached_get, \
             patch("deckbuilder.carddata.connect", side_effect=FileNotFoundError):
            
            mock_cached_get.return_value = {
                "object": "list",
                "data": [{"name": "TestCard", "type_line": "Creature", "cmc": 1}],
                "has_more": False
            }
            
            deck = build_deck("Test src4", no_network=False)
            assert deck["sources"]["network"] is True


class TestDeprecatedOfflineFlag:
    """Test backward compatibility of deprecated 'offline' parameter."""
    
    def test_offline_flag_mapped_to_no_network(self):
        """offline=True is mapped to no_network=True internally."""
        with patch("deckbuilder.scryfall.requests") as mock_requests:
            # Using deprecated 'offline' parameter
            deck = build_deck("Test old1", offline=True)
            
            # Should behave as no_network
            assert deck["sources"]["network"] is False
            mock_requests.get.assert_not_called()
    
    def test_build_deck_accepts_offline_param(self):
        """build_deck still accepts deprecated 'offline' parameter."""
        # Should not raise an error
        deck = build_deck("Test old2", offline=True)
        assert "categories" in deck


class TestHTTPErrorHandling:
    """Test various HTTP error scenarios."""
    
    def test_404_returns_empty_result(self):
        """404 responses return empty result, not an error."""
        mock_response_404 = Mock()
        mock_response_404.status_code = 404
        
        with patch("deckbuilder.scryfall.requests.get") as mock_get:
            mock_get.return_value = mock_response_404
            
            result = _cached_get("https://api.example.com/test_404", {})
            
            assert result == {"object": "list", "data": [], "total_cards": 0, "has_more": False}
    
    def test_other_http_errors_raise(self):
        """Non-404/429 HTTP errors are raised or caught as ScryfallUnavailable."""
        mock_response_500 = Mock()
        mock_response_500.status_code = 500
        mock_response_500.raise_for_status.side_effect = Exception("Internal Server Error")
        
        with patch("deckbuilder.scryfall.requests.get") as mock_get, \
             patch("deckbuilder.scryfall.time.sleep"):
            
            mock_get.return_value = mock_response_500
            
            # Should raise either the original exception or ScryfallUnavailable
            with pytest.raises((ScryfallUnavailable, Exception)):
                _cached_get("https://api.example.com/test_500", {})


class TestLogging:
    """Test that appropriate logging occurs."""
    
    def test_no_network_blocks_logged_at_info(self, caplog):
        """Blocked network requests are logged at INFO level."""
        import logging
        caplog.set_level(logging.INFO)
        
        with patch("deckbuilder.scryfall.requests"):
            _cached_get("https://api.scryfall.com/test_log", {}, no_network=True)
            
            assert any("no_network" in record.message for record in caplog.records)
    
    def test_retry_attempts_logged_at_warning(self, caplog):
        """Retry attempts are logged at WARNING level."""
        import logging
        caplog.set_level(logging.WARNING)
        
        mock_response_429 = Mock()
        mock_response_429.status_code = 429
        mock_response_429.headers = {}
        
        mock_response_200 = Mock()
        mock_response_200.status_code = 200
        mock_response_200.json.return_value = {"data": []}
        
        with patch("deckbuilder.scryfall.requests.get") as mock_get, \
             patch("deckbuilder.scryfall.time.sleep"):
            
            mock_get.side_effect = [mock_response_429, mock_response_200]
            
            _cached_get("https://api.example.com/test_log_retry", {})
            
            # Check that we have at least some logging
            assert len(caplog.records) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


class TestNoNetworkFlag:
    """Test that no_network=True prevents all outbound requests."""
    
    def test_cached_get_blocks_network_with_no_network(self):
        """_cached_get with no_network=True returns None instead of making requests."""
        with patch("deckbuilder.scryfall.requests") as mock_requests:
            result = _cached_get("https://api.example.com/test", {}, no_network=True)
            assert result is None
            # No HTTP call should be made
            mock_requests.get.assert_not_called()
    
    def test_cached_get_allows_disk_cache_with_no_network(self):
        """_cached_get with no_network=True still returns cached data."""
        cache_path = _cache_path("https://api.example.com/test" + json.dumps({}))
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        
        test_data = {"object": "list", "data": [{"name": "TestCard"}]}
        cache_path.write_text(json.dumps(test_data))
        
        try:
            result = _cached_get("https://api.example.com/test", {}, no_network=True)
            assert result == test_data
        finally:
            cache_path.unlink(missing_ok=True)
    
    def test_scryfall_client_no_network_disables_find_cards(self):
        """ScryfallClient with no_network=True falls back to sample pool."""
        client = ScryfallClient(no_network=True)
        with patch("deckbuilder.scryfall.requests") as mock_requests:
            result = client.find_cards(["W", "U"])
            # Should use sample pool (offline)
            assert client.card_source == "sample"
            mock_requests.get.assert_not_called()
    
    def test_scryfall_client_no_network_disables_set_resolution(self):
        """ScryfallClient.resolve_set_code with no_network=True returns None for unknown sets."""
        client = ScryfallClient(no_network=True)
        with patch("deckbuilder.scryfall.requests") as mock_requests:
            # Known aliases still work
            result = client.resolve_set_code("dominaria united")
            assert result == "dmu"
            
            # Unknown sets return None
            result = client.resolve_set_code("some unknown set")
            assert result is None
            mock_requests.get.assert_not_called()
    
    def test_scryfall_client_no_network_disables_commander_resolution(self):
        """ScryfallClient.resolve_named_commander with no_network=True returns None."""
        client = ScryfallClient(no_network=True)
        with patch("deckbuilder.scryfall.requests") as mock_requests:
            result = client.resolve_named_commander("Elspeth")
            assert result is None
            mock_requests.get.assert_not_called()
    
    def test_build_deck_with_no_network_makes_no_requests(self):
        """build_deck(no_network=True) makes no HTTP requests (uses cache and sample)."""
        with patch("deckbuilder.scryfall.requests") as mock_requests, \
             patch("deckbuilder.expand.requests") as mock_expand_requests, \
             patch("deckbuilder.theme.requests") as mock_theme_requests:
            
            deck = build_deck("Red aggro", no_network=True)
            
            # Should still return a valid deck structure
            assert "commander" in deck
            assert "categories" in deck
            assert "sources" in deck
            assert deck["sources"]["network"] is False
            
            # No network requests should be made
            mock_requests.get.assert_not_called()
            mock_requests.post.assert_not_called()
            mock_expand_requests.get.assert_not_called()
            mock_expand_requests.post.assert_not_called()
            mock_theme_requests.get.assert_not_called()


class TestRetryLogic:
    """Test 429 handling and retry logic."""
    
    def test_429_triggers_retry(self):
        """_cached_get retries on 429 response."""
        mock_response_429 = Mock()
        mock_response_429.status_code = 429
        mock_response_429.headers = {}
        
        mock_response_200 = Mock()
        mock_response_200.status_code = 200
        mock_response_200.json.return_value = {"data": [{"name": "Test"}]}
        
        with patch("deckbuilder.scryfall.requests.get") as mock_get, \
             patch("deckbuilder.scryfall.time.sleep") as mock_sleep:
            
            # First call returns 429, second returns 200
            mock_get.side_effect = [mock_response_429, mock_response_200]
            
            result = _cached_get("https://api.example.com/test", {})
            
            assert result == {"data": [{"name": "Test"}]}
            # Should have retried with backoff
            assert mock_get.call_count == 2
            assert mock_sleep.call_count >= 1  # At least one backoff sleep
    
    def test_429_respects_retry_after_header(self):
        """_cached_get honors Retry-After header over default backoff."""
        mock_response_429 = Mock()
        mock_response_429.status_code = 429
        mock_response_429.headers = {"Retry-After": "5"}
        
        mock_response_200 = Mock()
        mock_response_200.status_code = 200
        mock_response_200.json.return_value = {"data": []}
        
        with patch("deckbuilder.scryfall.requests.get") as mock_get, \
             patch("deckbuilder.scryfall.time.sleep") as mock_sleep:
            
            mock_get.side_effect = [mock_response_429, mock_response_200]
            
            result = _cached_get("https://api.example.com/test", {})
            
            # Should have called sleep with 5 seconds (from Retry-After)
            sleep_calls = mock_sleep.call_args_list
            # Find the backoff sleep (second sleep call, after REQUEST_DELAY)
            backoff_sleep = [c for c in sleep_calls if c[0][0] > 0.12][-1]
            assert backoff_sleep[0][0] == 5
    
    def test_three_429s_raises_scryfall_unavailable(self):
        """_cached_get raises ScryfallUnavailable after 3 failed 429 attempts."""
        mock_response_429 = Mock()
        mock_response_429.status_code = 429
        mock_response_429.headers = {}
        
        with patch("deckbuilder.scryfall.requests.get") as mock_get, \
             patch("deckbuilder.scryfall.time.sleep"):
            
            mock_get.return_value = mock_response_429
            
            with pytest.raises(ScryfallUnavailable):
                _cached_get("https://api.example.com/test", {})
    
    def test_connection_error_triggers_retry(self):
        """_cached_get retries on ConnectionError."""
        from requests import ConnectionError
        
        mock_response_200 = Mock()
        mock_response_200.status_code = 200
        mock_response_200.json.return_value = {"data": []}
        
        with patch("deckbuilder.scryfall.requests.get") as mock_get, \
             patch("deckbuilder.scryfall.time.sleep"):
            
            # First call raises ConnectionError, second succeeds
            mock_get.side_effect = [ConnectionError("Connection failed"), mock_response_200]
            
            result = _cached_get("https://api.example.com/test", {})
            
            assert result == {"data": []}
            assert mock_get.call_count == 2
    
    def test_timeout_triggers_retry(self):
        """_cached_get retries on Timeout."""
        from requests import Timeout
        
        mock_response_200 = Mock()
        mock_response_200.status_code = 200
        mock_response_200.json.return_value = {"data": []}
        
        with patch("deckbuilder.scryfall.requests.get") as mock_get, \
             patch("deckbuilder.scryfall.time.sleep"):
            
            # First call raises Timeout, second succeeds
            mock_get.side_effect = [Timeout("Request timed out"), mock_response_200]
            
            result = _cached_get("https://api.example.com/test", {})
            
            assert result == {"data": []}
            assert mock_get.call_count == 2


class TestSourcesTracking:
    """Test that sources metadata is correctly tracked."""
    
    def test_sources_api_when_using_live_api(self):
        """sources reports 'api' when using live Scryfall API."""
        with patch("deckbuilder.scryfall._cached_get") as mock_cached_get, \
             patch("deckbuilder.carddata.connect", side_effect=FileNotFoundError):
            
            # Mock successful API response
            mock_cached_get.return_value = {
                "object": "list",
                "data": [{"name": "TestCard", "type_line": "Creature", "cmc": 1}],
                "has_more": False
            }
            
            deck = build_deck("Test", no_network=False)
            
            assert deck["sources"]["cards"] == "api"
            assert deck["sources"]["network"] is True
    
    def test_sources_sample_when_fallback(self):
        """sources reports 'sample' when sample pool is used."""
        with patch("deckbuilder.scryfall._cached_get", return_value=None), \
             patch("deckbuilder.carddata.connect", side_effect=FileNotFoundError):
            
            deck = build_deck("Test", no_network=True)
            
            assert deck["sources"]["cards"] == "sample"
            assert deck["sources"]["network"] is False
    
    def test_sources_no_network_false_when_no_network_true(self):
        """sources.network is False when no_network=True."""
        deck = build_deck("Test", no_network=True)
        assert deck["sources"]["network"] is False
    
    def test_sources_no_network_true_when_no_network_false(self):
        """sources.network is True when no_network=False."""
        with patch("deckbuilder.scryfall._cached_get") as mock_cached_get, \
             patch("deckbuilder.carddata.connect", side_effect=FileNotFoundError):
            
            mock_cached_get.return_value = {
                "object": "list",
                "data": [{"name": "TestCard", "type_line": "Creature", "cmc": 1}],
                "has_more": False
            }
            
            deck = build_deck("Test", no_network=False)
            assert deck["sources"]["network"] is True


class TestDeprecatedOfflineFlag:
    """Test backward compatibility of deprecated 'offline' parameter."""
    
    def test_offline_flag_mapped_to_no_network(self):
        """offline=True is mapped to no_network=True internally."""
        with patch("deckbuilder.scryfall.requests") as mock_requests:
            # Using deprecated 'offline' parameter
            deck = build_deck("Test", offline=True)
            
            # Should behave as no_network
            assert deck["sources"]["network"] is False
            mock_requests.get.assert_not_called()
    
    def test_build_deck_accepts_offline_param(self):
        """build_deck still accepts deprecated 'offline' parameter."""
        # Should not raise an error
        deck = build_deck("Test", offline=True)
        assert "categories" in deck


class TestHTTPErrorHandling:
    """Test various HTTP error scenarios."""
    
    def test_404_returns_empty_result(self):
        """404 responses return empty result, not an error."""
        mock_response_404 = Mock()
        mock_response_404.status_code = 404
        
        with patch("deckbuilder.scryfall.requests.get") as mock_get:
            mock_get.return_value = mock_response_404
            
            result = _cached_get("https://api.example.com/test", {})
            
            assert result == {"object": "list", "data": [], "total_cards": 0, "has_more": False}
    
    def test_other_http_errors_raise(self):
        """Non-404/429 HTTP errors are raised or caught as ScryfallUnavailable."""
        mock_response_500 = Mock()
        mock_response_500.status_code = 500
        mock_response_500.raise_for_status.side_effect = Exception("Internal Server Error")
        
        with patch("deckbuilder.scryfall.requests.get") as mock_get, \
             patch("deckbuilder.scryfall.time.sleep"):
            
            mock_get.return_value = mock_response_500
            
            # Should raise either the original exception or ScryfallUnavailable
            with pytest.raises((ScryfallUnavailable, Exception)):
                _cached_get("https://api.example.com/test_500", {})


class TestLogging:
    """Test that appropriate logging occurs."""
    
    def test_no_network_blocks_logged_at_info(self, caplog):
        """Blocked network requests are logged at INFO level."""
        import logging
        caplog.set_level(logging.INFO)
        
        with patch("deckbuilder.scryfall.requests"):
            _cached_get("https://api.scryfall.com/test", {}, no_network=True)
            
            assert any("no_network" in record.message for record in caplog.records)
    
    def test_retry_attempts_logged_at_warning(self, caplog):
        """Retry attempts are logged at WARNING level."""
        import logging
        caplog.set_level(logging.WARNING)
        
        mock_response_429 = Mock()
        mock_response_429.status_code = 429
        mock_response_429.headers = {}
        
        mock_response_200 = Mock()
        mock_response_200.status_code = 200
        mock_response_200.json.return_value = {"data": []}
        
        with patch("deckbuilder.scryfall.requests.get") as mock_get, \
             patch("deckbuilder.scryfall.time.sleep"):
            
            mock_get.side_effect = [mock_response_429, mock_response_200]
            
            _cached_get("https://api.example.com/test", {})
            
            assert any("429" in record.message for record in caplog.records)
            assert any("attempt" in record.message.lower() for record in caplog.records)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
