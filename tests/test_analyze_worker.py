"""Tests for analyze worker."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from datadeduplication.workers.analyze_worker import AnalyzeWorker


@pytest.fixture
def mock_config():
    config = MagicMock()
    config.worker_analyze_batch = 10
    config.tamanho_max_para_analise = 52428800
    config.tipos_analise = ["pdf", "docx", "xlsx", "txt", "jpg", "mp3", "mp4"]
    return config


@pytest.fixture
def mock_db():
    return MagicMock()


def test_analyze_text(tmp_path, mock_config, mock_db):
    """Test text file analysis."""
    test_file = tmp_path / "test.txt"
    test_file.write_text("line1\nline2\nline3\n")

    worker = AnalyzeWorker(mock_config, mock_db)
    result = worker.analyze_text(test_file)

    assert result["linhas"] == 4
    assert result["caracteres"] > 0
    assert result["vazio"] is False


def test_analyze_text_empty(tmp_path, mock_config, mock_db):
    """Test empty text file analysis."""
    test_file = tmp_path / "empty.txt"
    test_file.write_text("")

    worker = AnalyzeWorker(mock_config, mock_db)
    result = worker.analyze_text(test_file)

    assert result["linhas"] == 1
    assert result["vazio"] is True


def test_get_analyzer_for_extension(mock_config, mock_db):
    """Test analyzer selection by extension."""
    worker = AnalyzeWorker(mock_config, mock_db)

    assert worker.get_analyzer_for_extension(".pdf") == worker.analyze_pdf
    assert worker.get_analyzer_for_extension(".docx") == worker.analyze_docx
    assert worker.get_analyzer_for_extension(".xlsx") == worker.analyze_xlsx
    assert worker.get_analyzer_for_extension(".txt") == worker.analyze_text
    assert worker.get_analyzer_for_extension(".jpg") == worker.analyze_image
    assert worker.get_analyzer_for_extension(".mp3") == worker.analyze_audio
    assert worker.get_analyzer_for_extension(".mp4") == worker.analyze_video
    assert worker.get_analyzer_for_extension(".xyz") is None
