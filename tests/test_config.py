"""Tests for config module."""

import os
import tempfile
from pathlib import Path

import pytest

from datadeduplication.config import Config


def test_config_from_env_defaults():
    """Test Config loads defaults when no .env file exists."""
    config = Config.from_env()
    assert config.db_host == "localhost"
    assert config.db_port == 3306
    assert config.batch_size == 1000
    assert config.seguir_symlinks is False


def test_config_from_env_custom(tmp_path):
    """Test Config loads custom values from .env file."""
    env_content = """
RAIZ_ANALISE=C:\\test\\path
DB_HOST=192.168.1.100
DB_PORT=3307
BATCH_SIZE=500
SEGUIR_SYMLINKS=true
TIPOS_ANALISE=pdf,docx
"""
    env_file = tmp_path / ".env"
    env_file.write_text(env_content)

    config = Config.from_env(str(env_file))
    assert config.raiz_analise == Path("C:\\test\\path")
    assert config.db_host == "192.168.1.100"
    assert config.db_port == 3307
    assert config.batch_size == 500
    assert config.seguir_symlinks is True
    assert config.tipos_analise == ["pdf", "docx"]


def test_config_db_url():
    """Test db_url property generates correct URL."""
    config = Config(
        raiz_analise=Path("C:\\test"),
        db_user="admin",
        db_password="secret",
        db_host="db.local",
        db_port=3306,
        db_name="testdb",
    )
    assert config.db_url == "mysql+pymysql://admin:secret@db.local:3306/testdb?charset=utf8mb4"
