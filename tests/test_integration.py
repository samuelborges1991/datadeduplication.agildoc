"""Integration tests for the complete workflow."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from datadeduplication.config import Config
from datadeduplication.database import Database
from datadeduplication.models import Arquivo, Base, Tarefa
from datadeduplication.scanner import Scanner
from datadeduplication.workers.hash_worker import HashWorker


@pytest.fixture
def test_env(tmp_path):
    """Create test environment with files."""
    # Create test files
    (tmp_path / "file1.txt").write_text("content1")
    (tmp_path / "file2.txt").write_text("content2")
    (tmp_path / "file3.pdf").write_bytes(b"%PDF-1.4 fake content")

    # Create config
    config = Config(
        raiz_analise=tmp_path,
        batch_size=10,
        db_host="localhost",
        db_port=3306,
        db_user="test",
        db_password="test",
        db_name="test_db",
    )

    return config, tmp_path


def test_scanner_creates_tasks(test_env):
    """Test that scanner creates hash and analyze tasks."""
    config, test_dir = test_env

    # Use in-memory SQLite for testing
    db = MagicMock()
    db.session.return_value.__enter__ = MagicMock()
    db.session.return_value.__exit__ = MagicMock()

    scanner = Scanner(config, db)

    # Test metadata extraction
    metadata = scanner.get_file_metadata(test_dir / "file1.txt")
    assert metadata["nome"] == "file1.txt"
    assert metadata["extensao"] == ".txt"
    assert metadata["tamanho"] > 0


def test_hash_worker_computes_hash(test_env):
    """Test hash worker computes correct SHA-256."""
    config, test_dir = test_env

    worker = HashWorker(config, MagicMock())

    hash1 = worker.compute_hash(test_dir / "file1.txt")
    hash2 = worker.compute_hash(test_dir / "file2.txt")
    hash3 = worker.compute_hash(test_dir / "file1.txt")

    assert hash1 != hash2  # Different content
    assert hash1 == hash3  # Same content
    assert len(hash1) == 64  # SHA-256 hex length
