"""SQLAlchemy ORM models."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    """Base class for all models."""
    pass


class Arquivo(Base):
    """File metadata stored in database."""
    __tablename__ = "arquivos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    caminho = Column(String(1024), nullable=False, unique=True)
    nome = Column(String(255), nullable=False)
    extensao = Column(String(20))
    tamanho = Column(BigInteger, nullable=False)
    data_criacao = Column(DateTime)
    data_modificacao = Column(DateTime)
    data_acesso = Column(DateTime)
    atributos = Column(String(255))
    proprietario = Column(String(255))
    hash_sha256 = Column(String(64))
    tipo_mime = Column(String(100))
    metadados_json = Column(JSON)
    data_processamento = Column(DateTime, server_default=func.now())

    tarefas = relationship("Tarefa", back_populates="arquivo", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_hash", "hash_sha256"),
        Index("idx_tamanho", "tamanho"),
        Index("idx_data_modificacao", "data_modificacao"),
        Index("idx_extensao", "extensao"),
    )


class Tarefa(Base):
    """Task queue for workers."""
    __tablename__ = "tarefas"

    id = Column(Integer, primary_key=True, autoincrement=True)
    arquivo_id = Column(Integer, ForeignKey("arquivos.id", ondelete="CASCADE"), nullable=False)
    tipo = Column(Enum("hash", "analyze", "cleanup", name="task_type_enum"), nullable=False)
    status = Column(
        Enum("pending", "queued", "running", "done", "error", "retry", name="task_status_enum"),
        default="pending",
    )
    prioridade = Column(Integer, default=0)
    tentativas = Column(Integer, default=0)
    max_tentativas = Column(Integer, default=3)
    mensagem_erro = Column(Text)
    worker_id = Column(String(100))
    data_criacao = Column(DateTime, server_default=func.now())
    data_inicio = Column(DateTime)
    data_conclusao = Column(DateTime)

    arquivo = relationship("Arquivo", back_populates="tarefas")

    __table_args__ = (
        Index("idx_status_tipo", "status", "tipo"),
        Index("idx_prioridade", "prioridade"),
    )


class LogProcessamento(Base):
    """Processing log for audit."""
    __tablename__ = "logs_processamento"

    id = Column(Integer, primary_key=True, autoincrement=True)
    data_inicio = Column(DateTime, nullable=False)
    data_fim = Column(DateTime)
    total_arquivos = Column(BigInteger, default=0)
    total_bytes = Column(BigInteger, default=0)
    status = Column(
        Enum("running", "completed", "failed", name="log_status_enum"),
        default="running",
    )
    mensagem_erro = Column(Text)
    comando = Column(String(50))
