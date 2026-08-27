"""Tests for hash worker."""

import hashlib
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from datadeduplication.workers.hash_worker import HashWorker


@pytest.fixture
def mock_config():
    config = MagicMock()
    config.worker_hash_batch = 10
    return config


@pytest.fixture
def mock_db():
    return MagicMock()


def test_compute_hash(tmp_path, mock_config, mock_db):
    """Test SHA-256 hash computation."""
    test_file = tmp_path / "test.txt"
    test_content = b"hello world"
    test_file.write_bytes(test_content)

    expected_hash = hashlib.sha256(test_content).hexdigest()

    worker = HashWorker(mock_config, mock_db)
    result = worker.compute_hash(test_file)

    assert result == expected_hash


def test_compute_hash_large_file(tmp_path, mock_config, mock_db):
    """Test hash computation for larger file."""
    test_file = tmp_path / "large.bin"
    test_content = b"x" * 100000
    test_file.write_bytes(test_content)

    expected_hash = hashlib.sha256(test_content).hexdigest()

    worker = HashWorker(mock_config, mock_db)
    result = worker.compute_hash(test_file)

    assert result == expected_hash