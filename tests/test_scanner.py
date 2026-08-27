"""Tests for scanner module."""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from datadeduplication.scanner import Scanner


@pytest.fixture
def mock_config():
    """Create mock config."""
    config = MagicMock()
    config.raiz_analise = Path(tempfile.gettempdir())
    config.batch_size = 10
    config.seguir_symlinks = False
    config.tipos_analise = ["txt", "pdf"]
    return config


@pytest.fixture
def mock_db():
    """Create mock database."""
    return MagicMock()


def test_get_file_metadata(tmp_path):
    """Test file metadata extraction."""
    test_file = tmp_path / "test.txt"
    test_file.write_text("hello world")

    scanner = Scanner(MagicMock(), MagicMock())
    metadata = scanner.get_file_metadata(test_file)

    assert metadata["nome"] == "test.txt"
    assert metadata["extensao"] == ".txt"
    assert metadata["tamanho"] == 11
    assert metadata["caminho"] == str(test_file)


def test_get_file_attributes(tmp_path):
    """Test file attributes extraction."""
    test_file = tmp_path / "test.txt"
    test_file.write_text("test")

    scanner = Scanner(MagicMock(), MagicMock())
    attrs = scanner.get_file_attributes(test_file)

    assert isinstance(attrs, str)


def test_get_file_owner(tmp_path):
    """Test file owner extraction."""
    test_file = tmp_path / "test.txt"
    test_file.write_text("test")

    scanner = Scanner(MagicMock(), MagicMock())
    owner = scanner.get_file_owner(test_file)

    assert isinstance(owner, str)
