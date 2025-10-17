"""Pytest configuration and fixtures."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pandas as pd
import pytest


@pytest.fixture
def mock_token():
    """Sample JWT token for testing."""
    # This is a mock token with proper JWT structure
    return "eyJhbGciOiJSUzUxMiIsImtpZCI6IkdaeFUiLCJ0eXAiOiJKV1QifQ.eyJ1c2VyX2lkIjo5MTE1MzUxMSwiZXhwIjoyMDAwMDAwMDAwLCJpYXQiOjE3MDAwMDAwMDAsInBsYW4iOiJwcm9fcHJlbWl1bSJ9.signature"


@pytest.fixture
def mock_expired_token():
    """Sample expired JWT token for testing."""
    return "eyJhbGciOiJSUzUxMiIsImtpZCI6IkdaeFUiLCJ0eXAiOiJKV1QifQ.eyJ1c2VyX2lkIjo5MTE1MzUxMSwiZXhwIjoxMDAwMDAwMDAwLCJpYXQiOjk1MDAwMDAwMCwicGxhbiI6InByb19wcmVtaXVtIn0.signature"


@pytest.fixture
def mock_token_cache_file(tmp_path, mock_token):
    """Create a temporary token cache file."""
    token_file = tmp_path / ".tv_token.json"
    token_file.write_text(json.dumps({"token": mock_token}))
    return token_file


@pytest.fixture
def sample_ohlcv_data():
    """Sample OHLCV data for testing."""
    return pd.DataFrame({
        'symbol': ['NASDAQ:AAPL'] * 5,
        'open': [150.0, 151.0, 152.0, 153.0, 154.0],
        'high': [151.5, 152.5, 153.5, 154.5, 155.5],
        'low': [149.5, 150.5, 151.5, 152.5, 153.5],
        'close': [151.0, 152.0, 153.0, 154.0, 155.0],
        'volume': [1000000, 1100000, 1200000, 1300000, 1400000]
    }, index=pd.date_range('2025-01-01', periods=5, freq='D', tz='UTC'))
    

@pytest.fixture
def mock_websocket():
    """Mock WebSocket connection."""
    ws = MagicMock()
    ws.recv.return_value = '~m~50~m~{"m":"series_completed","p":["session"]}'
    ws.send.return_value = None
    ws.close.return_value = None
    return ws


@pytest.fixture
def mock_requests_response():
    """Mock requests response object."""
    response = Mock()
    response.status_code = 200
    response.json.return_value = {
        "user": {
            "username": "testuser",
            "auth_token": "test_token_123"
        }
    }
    return response


@pytest.fixture
def mock_search_response():
    """Mock search API response."""
    return [
        {
            "symbol": "AAPL",
            "description": "Apple Inc",
            "type": "stock",
            "exchange": "NASDAQ"
        },
        {
            "symbol": "MSFT",
            "description": "Microsoft Corporation",
            "type": "stock",
            "exchange": "NASDAQ"
        }
    ]


@pytest.fixture(autouse=True)
def cleanup_token_files(tmp_path, monkeypatch):
    """Automatically clean up token files after tests."""
    # Use tmp_path for token files in tests
    monkeypatch.setenv("HOME", str(tmp_path))
    yield
    # Cleanup is automatic with tmp_path


@pytest.fixture
def mock_create_connection(mock_websocket):
    """Mock websocket create_connection."""
    with patch('tvDatafeed.main.create_connection', return_value=mock_websocket) as mock:
        yield mock


@pytest.fixture
def mock_requests_post(mock_requests_response):
    """Mock requests.post."""
    with patch('tvDatafeed.main.requests.post', return_value=mock_requests_response) as mock:
        yield mock


@pytest.fixture
def mock_requests_get():
    """Mock requests.get."""
    with patch('tvDatafeed.main.requests.get') as mock:
        response = Mock()
        response.status_code = 200
        response.json.return_value = {"status": "ok"}
        response.text = json.dumps({"results": []})
        mock.return_value = response
        yield mock
