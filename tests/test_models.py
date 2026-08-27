"""Tests for database models."""

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from datadeduplication.models import Arquivo, Base, LogProcessamento, Tarefa


@pytest.fixture
def in_memory_db():
    """Create in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def session(in_memory_db):
    """Create database session."""
    with Session(in_memory_db) as session:
        yield session


def test_arquivo_create(session):
    """Test creating an Arquivo record."""
    arquivo = Arquivo(
        caminho="C:\\test\\file.txt",
        nome="file.txt",
        extensao=".txt",
        tamanho=1024,
        data_criacao=datetime.now(),
        data_modificacao=datetime.now(),
    )
    session.add(arquivo)
    session.commit()

    assert arquivo.id is not None
    assert arquivo.caminho == "C:\\test\\file.txt"


def test_tarefa_create(session):
    """Test creating a Tarefa record."""
    arquivo = Arquivo(
        caminho="C:\\test\\file.txt",
        nome="file.txt",
        extensao=".txt",
        tamanho=1024,
    )
    session.add(arquivo)
    session.flush()

    tarefa = Tarefa(
        arquivo_id=arquivo.id,
        tipo="hash",
        status="pending",
    )
    session.add(tarefa)
    session.commit()

    assert tarefa.id is not None
    assert tarefa.arquivo_id == arquivo.id


def test_tarefa_relationship(session):
    """Test Arquivo-Tarefa relationship."""
    arquivo = Arquivo(
        caminho="C:\\test\\file.txt",
        nome="file.txt",
        extensao=".txt",
        tamanho=1024,
    )
    session.add(arquivo)
    session.flush()

    tarefa = Tarefa(arquivo_id=arquivo.id, tipo="hash")
    session.add(tarefa)
    session.commit()

    assert len(arquivo.tarefas) == 1
    assert arquivo.tarefas[0].tipo == "hash"


def test_log_processamento_create(session):
    """Test creating a LogProcessamento record."""
    log = LogProcessamento(
        data_inicio=datetime.now(),
        comando="scan",
        status="running",
    )
    session.add(log)
    session.commit()

    assert log.id is not None
