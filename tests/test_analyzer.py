"""Tests for analyzer module."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from datadeduplication.analyzer import Analyzer, TEMP_EXTENSIONS


@pytest.fixture
def mock_config():
    return MagicMock()


@pytest.fixture
def mock_db():
    return MagicMock()


def test_temp_extensions():
    """Test that TEMP_EXTENSIONS contains expected values."""
    assert ".tmp" in TEMP_EXTENSIONS
    assert ".bak" in TEMP_EXTENSIONS
    assert ".old" in TEMP_EXTENSIONS
    assert ".log" in TEMP_EXTENSIONS


def test_analyzer_init(mock_config, mock_db):
    """Test Analyzer initialization."""
    analyzer = Analyzer(mock_config, mock_db)
    assert analyzer.config == mock_config
    assert analyzer.db == mock_db
