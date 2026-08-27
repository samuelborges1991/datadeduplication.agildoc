# Data Deduplication Tool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python tool for Windows directory analysis, identifying files for removal via deduplication, cleanup, and inventory using an orchestrator+workers architecture with MySQL task queue.

**Architecture:** Orchestrator creates prioritized tasks in MySQL. Separate worker processes poll for tasks using `FOR UPDATE SKIP LOCKED`. Scanner inserts file metadata in batches of 1000. Workers compute SHA-256 hashes and collect lightweight metadata (pages, lines, dimensions, duration).

**Tech Stack:** Python 3.10+, SQLAlchemy, PyMySQL, PyPDF2, python-docx, openpyxl, python-pptx, Pillow, mutagen, pandas, python-dotenv

## Global Constraints

- MySQL 8+ required (uses `FOR UPDATE SKIP LOCKED`)
- Windows-only (pywin32 for file owner, ctypes for attributes)
- Batch inserts of 1000 records
- No symlinks/junctions by default (configurable)
- All credentials via `.env` file, never hardcoded
- Logging to file and console

---

## File Structure

```
datadeduplication/
├── src/
│   └── datadeduplication/
│       ├── __init__.py
│       ├── __main__.py
│       ├── config.py
│       ├── database.py
│       ├── models.py
│       ├── enums.py
│       ├── scanner.py
│       ├── orchestrator.py
│       ├── workers/
│       │   ├── __init__.py
│       │   ├── base.py
│       │   ├── hash_worker.py
│       │   └── analyze_worker.py
│       ├── analyzer.py
│       └── quarantine.py
├── tests/
│   ├── __init__.py
│   ├── test_config.py
│   ├── test_models.py
│   ├── test_scanner.py
│   ├── test_hash_worker.py
│   ├── test_analyze_worker.py
│   └── test_analyzer.py
├── .env.example
├── requirements.txt
└── README.md
```

---

### Task 1: Project Setup and Configuration

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `src/datadeduplication/__init__.py`
- Create: `src/datadeduplication/config.py`
- Create: `tests/__init__.py`
- Create: `tests/test_config.py`

**Interfaces:**
- Produces: `Config` dataclass with all settings from `.env`

- [ ] **Step 1: Create requirements.txt**

```
python-dotenv>=1.0.0
sqlalchemy>=2.0.0
pymysql>=1.1.0
PyPDF2>=3.0.0
python-docx>=1.0.0
openpyxl>=3.1.0
python-pptx>=0.6.21
Pillow>=10.0.0
mutagen>=1.47.0
pandas>=2.0.0
```

- [ ] **Step 2: Create .env.example**

```env
# Diretório raiz para análise
RAIZ_ANALISE=C:\dados

# MySQL
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=
DB_NAME=datadeduplication

# Scanner
BATCH_SIZE=1000
SEGUIR_SYMLINKS=false

# Análise de metadata
ANALISAR_METADATA=true
TAMANHO_MAX_PARA_ANALISE=52428800
TIPOS_ANALISE=pdf,docx,xlsx,pptx,txt,jpg,png,mp3,mp4

# Quarentena
QUARENTENA_PATH=C:\quarentena

# Orquestrador
ORCHESTRATE_INTERVAL=30
MAX_TENTATIVAS=3

# Workers
WORKER_HASH_BATCH=100
WORKER_HASH_THREADS=4
WORKER_ANALYZE_BATCH=50
WORKER_ANALYZE_PROCESSES=4

# Logging
LOG_LEVEL=INFO
LOG_FILE=datadeduplication.log
```

- [ ] **Step 3: Create src/datadeduplication/__init__.py**

```python
"""Data Deduplication Tool - Análise de diretórios para identificação de arquivos candidatos à remoção."""

__version__ = "1.0.0"
```

- [ ] **Step 4: Create src/datadeduplication/config.py**

```python
"""Configuration loader from .env file."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from dotenv import load_dotenv


@dataclass
class Config:
    """Application configuration loaded from environment variables."""

    # Directory
    raiz_analise: Path

    # Database
    db_host: str = "localhost"
    db_port: int = 3306
    db_user: str = "root"
    db_password: str = ""
    db_name: str = "datadeduplication"

    # Scanner
    batch_size: int = 1000
    seguir_symlinks: bool = False

    # Analysis
    analisar_metadata: bool = True
    tamanho_max_para_analise: int = 52428800  # 50MB
    tipos_analise: List[str] = field(default_factory=lambda: [
        "pdf", "docx", "xlsx", "pptx", "txt", "jpg", "png", "mp3", "mp4"
    ])

    # Quarantine
    quarentena_path: Path = Path("C:\\quarentena")

    # Orchestrator
    orchestrate_interval: int = 30
    max_tentativas: int = 3

    # Workers
    worker_hash_batch: int = 100
    worker_hash_threads: int = 4
    worker_analyze_batch: int = 50
    worker_analyze_processes: int = 4

    # Logging
    log_level: str = "INFO"
    log_file: str = "datadeduplication.log"

    @property
    def db_url(self) -> str:
        """SQLAlchemy database URL."""
        return f"mysql+pymysql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}?charset=utf8mb4"

    @classmethod
    def from_env(cls, env_path: str = None) -> "Config":
        """Load configuration from .env file."""
        load_dotenv(env_path)

        tipos_raw = os.getenv("TIPOS_ANALISE", "pdf,docx,xlsx,pptx,txt,jpg,png,mp3,mp4")
        tipos_list = [t.strip() for t in tipos_raw.split(",")]

        return cls(
            raiz_analise=Path(os.getenv("RAIZ_ANALISE", "C:\\dados")),
            db_host=os.getenv("DB_HOST", "localhost"),
            db_port=int(os.getenv("DB_PORT", "3306")),
            db_user=os.getenv("DB_USER", "root"),
            db_password=os.getenv("DB_PASSWORD", ""),
            db_name=os.getenv("DB_NAME", "datadeduplication"),
            batch_size=int(os.getenv("BATCH_SIZE", "1000")),
            seguir_symlinks=os.getenv("SEGUIR_SYMLINKS", "false").lower() == "true",
            analisar_metadata=os.getenv("ANALISAR_METADATA", "true").lower() == "true",
            tamanho_max_para_analise=int(os.getenv("TAMANHO_MAX_PARA_ANALISE", "52428800")),
            tipos_analise=tipos_list,
            quarentena_path=Path(os.getenv("QUARENTENA_PATH", "C:\\quarentena")),
            orchestrate_interval=int(os.getenv("ORCHESTRATE_INTERVAL", "30")),
            max_tentativas=int(os.getenv("MAX_TENTATIVAS", "3")),
            worker_hash_batch=int(os.getenv("WORKER_HASH_BATCH", "100")),
            worker_hash_threads=int(os.getenv("WORKER_HASH_THREADS", "4")),
            worker_analyze_batch=int(os.getenv("WORKER_ANALYZE_BATCH", "50")),
            worker_analyze_processes=int(os.getenv("WORKER_ANALYZE_PROCESSES", "4")),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            log_file=os.getenv("LOG_FILE", "datadeduplication.log"),
        )
```

- [ ] **Step 5: Create tests/__init__.py**

```python
```

- [ ] **Step 6: Create tests/test_config.py**

```python
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
```

- [ ] **Step 7: Run tests to verify**

Run: `pytest tests/test_config.py -v`
Expected: PASS (3 tests)

- [ ] **Step 8: Commit**

```bash
git add requirements.txt .env.example src/ tests/
git commit -m "feat: project setup with config module and tests"
```

---

### Task 2: Enums and Database Models

**Files:**
- Create: `src/datadeduplication/enums.py`
- Create: `src/datadeduplication/models.py`
- Create: `tests/test_models.py`

**Interfaces:**
- Produces: `TaskType` enum (HASH, ANALYZE, CLEANUP)
- Produces: `TaskStatus` enum (PENDING, QUEUED, RUNNING, DONE, ERROR, RETRY)
- Produces: `Arquivo`, `Tarefa`, `LogProcessamento` ORM models

- [ ] **Step 1: Create src/datadeduplication/enums.py**

```python
"""Enums for task types and statuses."""

from enum import Enum


class TaskType(str, Enum):
    """Types of tasks that can be processed by workers."""
    HASH = "hash"
    ANALYZE = "analyze"
    CLEANUP = "cleanup"


class TaskStatus(str, Enum):
    """Status of tasks in the queue."""
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"
    RETRY = "retry"
```

- [ ] **Step 2: Create src/datadeduplication/models.py**

```python
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
```

- [ ] **Step 3: Create tests/test_models.py**

```python
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
```

- [ ] **Step 4: Run tests to verify**

Run: `pytest tests/test_models.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/datadeduplication/enums.py src/datadeduplication/models.py tests/test_models.py
git commit -m "feat: add enums and database models"
```

---

### Task 3: Database Connection and Table Creation

**Files:**
- Create: `src/datadeduplication/database.py`

**Interfaces:**
- Produces: `Database` class with `engine`, `session_factory`, `create_tables()`, `drop_tables()`
- Consumes: `Config.db_url`, `models.Base`

- [ ] **Step 1: Create src/datadeduplication/database.py**

```python
"""Database connection and session management."""

import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from datadeduplication.config import Config
from datadeduplication.models import Base

logger = logging.getLogger(__name__)


class Database:
    """Database connection manager."""

    def __init__(self, config: Config):
        self.config = config
        self.engine = create_engine(
            config.db_url,
            pool_size=10,
            max_overflow=20,
            pool_recycle=3600,
            echo=False,
        )
        self.session_factory = sessionmaker(bind=self.engine)

    def create_tables(self) -> None:
        """Create all tables if they don't exist."""
        logger.info("Creating database tables...")
        Base.metadata.create_all(self.engine)
        logger.info("Database tables created successfully.")

    def drop_tables(self) -> None:
        """Drop all tables. Use with caution."""
        logger.warning("Dropping all database tables...")
        Base.metadata.drop_all(self.engine)
        logger.info("Database tables dropped.")

    @contextmanager
    def session(self) -> Generator[Session, None, None]:
        """Provide a transactional session scope."""
        session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def test_connection(self) -> bool:
        """Test database connectivity."""
        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("Database connection successful.")
            return True
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            return False
```

- [ ] **Step 2: Run existing tests to verify no regressions**

Run: `pytest tests/ -v`
Expected: PASS (7 tests)

- [ ] **Step 3: Commit**

```bash
git add src/datadeduplication/database.py
git commit -m "feat: add database connection manager"
```

---

### Task 4: Scanner Module

**Files:**
- Create: `src/datadeduplication/scanner.py`
- Create: `tests/test_scanner.py`

**Interfaces:**
- Produces: `Scanner` class with `scan()`, `get_file_metadata()`, `get_file_owner()`, `get_file_attributes()`
- Consumes: `Config`, `Database`, `Arquivo`, `Tarefa`, `TaskType`, `TaskStatus`

- [ ] **Step 1: Create tests/test_scanner.py**

```python
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
    test_file = test_file = tmp_path / "test.txt"
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_scanner.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'datadeduplication.scanner'"

- [ ] **Step 3: Create src/datadeduplication/scanner.py**

```python
"""Directory scanner for file metadata collection."""

import hashlib
import logging
import os
import stat
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from datadeduplication.config import Config
from datadeduplication.database import Database
from datadeduplication.enums import TaskType, TaskStatus
from datadeduplication.models import Arquivo, Tarefa

logger = logging.getLogger(__name__)


class Scanner:
    """Scans directories and collects file metadata."""

    def __init__(self, config: Config, db: Database):
        self.config = config
        self.db = db
        self._batch: List[Dict] = []
        self._total_files = 0
        self._total_bytes = 0

    def get_file_metadata(self, filepath: Path) -> Dict:
        """Extract basic metadata from a file."""
        stat_result = filepath.stat()
        return {
            "caminho": str(filepath),
            "nome": filepath.name,
            "extensao": filepath.suffix.lower(),
            "tamanho": stat_result.st_size,
            "data_criacao": datetime.fromtimestamp(stat_result.st_ctime),
            "data_modificacao": datetime.fromtimestamp(stat_result.st_mtime),
            "data_acesso": datetime.fromtimestamp(stat_result.st_atime),
        }

    def get_file_attributes(self, filepath: Path) -> str:
        """Get Windows file attributes."""
        attrs = []
        try:
            st = filepath.stat()
            if st.st_file_attributes & stat.FILE_ATTRIBUTE_READONLY:
                attrs.append("readonly")
            if st.st_file_attributes & stat.FILE_ATTRIBUTE_HIDDEN:
                attrs.append("hidden")
            if st.st_file_attributes & stat.FILE_ATTRIBUTE_SYSTEM:
                attrs.append("system")
            if st.st_file_attributes & stat.FILE_ATTRIBUTE_ARCHIVE:
                attrs.append("archive")
        except (AttributeError, OSError):
            pass
        return ",".join(attrs) if attrs else "normal"

    def get_file_owner(self, filepath: Path) -> str:
        """Get file owner using ctypes."""
        try:
            import ctypes
            from ctypes import wintypes

            advapi32 = ctypes.windll.advapi32
            kernel32 = ctypes.windll.kernel32

            # Get file security info
            SECURITY_INFO_OWNER = 0x00000001
            ERROR_INSUFFICIENT_BUFFER = 122

            # First call to get buffer size
            size = wintypes.DWORD(0)
            advapi32.GetFileSecurityW(
                str(filepath),
                SECURITY_INFO_OWNER,
                None,
                0,
                ctypes.byref(size),
            )

            # Allocate buffer and get security descriptor
            buf = ctypes.create_string_buffer(size.value)
            advapi32.GetFileSecurityW(
                str(filepath),
                SECURITY_INFO_OWNER,
                buf,
                size,
                ctypes.byref(size),
            )

            # Get owner SID
            sid = ctypes.c_void_p()
            defaulted = wintypes.BOOL()
            advapi32.GetSecurityDescriptorOwner(
                buf,
                ctypes.byref(sid),
                ctypes.byref(defaulted),
            )

            # Lookup account name
            name_size = wintypes.DWORD(256)
            domain_size = wintypes.DWORD(256)
            name = ctypes.create_unicode_buffer(name_size.value)
            domain = ctypes.create_unicode_buffer(domain_size.value)
            use = wintypes.DWORD()

            advapi32.LookupAccountSidW(
                None,
                sid,
                name,
                ctypes.byref(name_size),
                domain,
                ctypes.byref(domain_size),
                ctypes.byref(use),
            )

            return f"{domain.value}\\{name.value}"
        except Exception:
            return "unknown"

    def get_mime_type(self, filepath: Path) -> str:
        """Get MIME type using mimetypes module."""
        import mimetypes
        mime_type, _ = mimetypes.guess_type(str(filepath))
        return mime_type or "application/octet-stream"

    def _process_file(self, filepath: Path) -> Optional[Dict]:
        """Process a single file and return metadata dict."""
        try:
            if not filepath.is_file():
                return None

            if not self.config.seguir_symlinks and filepath.is_symlink():
                return None

            metadata = self.get_file_metadata(filepath)
            metadata["atributos"] = self.get_file_attributes(filepath)
            metadata["proprietario"] = self.get_file_owner(filepath)
            metadata["tipo_mime"] = self.get_mime_type(filepath)

            return metadata
        except PermissionError:
            logger.warning(f"Permission denied: {filepath}")
            return None
        except Exception as e:
            logger.error(f"Error processing {filepath}: {e}")
            return None

    def _flush_batch(self, session) -> None:
        """Insert batch of files and create tasks."""
        if not self._batch:
            return

        for metadata in self._batch:
            arquivo = Arquivo(**metadata)
            session.add(arquivo)
            session.flush()

            # Create hash task
            tarefa_hash = Tarefa(
                arquivo_id=arquivo.id,
                tipo=TaskType.HASH.value,
                status=TaskStatus.PENDING.value,
            )
            session.add(tarefa_hash)

            # Create analyze task
            tarefa_analyze = Tarefa(
                arquivo_id=arquivo.id,
                tipo=TaskType.ANALYZE.value,
                status=TaskStatus.PENDING.value,
            )
            session.add(tarefa_analyze)

        session.commit()
        logger.info(f"Flushed batch of {len(self._batch)} files")
        self._batch.clear()

    def scan(self, resume: bool = False) -> Dict:
        """Scan directory recursively and collect file metadata.

        Args:
            resume: If True, skip files already in database.

        Returns:
            Dict with scan statistics.
        """
        logger.info(f"Starting scan of {self.config.raiz_analise}")
        start_time = datetime.now()

        # Get existing files for resume mode
        existing_files = set()
        if resume:
            with self.db.session() as session:
                results = session.query(Arquivo.caminho).all()
                existing_files = {r[0] for r in results}
            logger.info(f"Resume mode: {len(existing_files)} files already in database")

        try:
            root = Path(self.config.raiz_analise)
            if not root.exists():
                raise FileNotFoundError(f"Directory not found: {root}")

            for filepath in root.rglob("*"):
                if filepath.is_dir():
                    continue

                filepath_str = str(filepath)
                if resume and filepath_str in existing_files:
                    continue

                metadata = self._process_file(filepath)
                if metadata is None:
                    continue

                self._batch.append(metadata)
                self._total_files += 1
                self._total_bytes += metadata["tamanho"]

                if len(self._batch) >= self.config.batch_size:
                    with self.db.session() as session:
                        self._flush_batch(session)

            # Flush remaining files
            if self._batch:
                with self.db.session() as session:
                    self._flush_batch(session)

        except Exception as e:
            logger.error(f"Scan failed: {e}")
            raise

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        stats = {
            "total_files": self._total_files,
            "total_bytes": self._total_bytes,
            "duration_seconds": duration,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
        }

        logger.info(f"Scan completed: {self._total_files} files, {self._total_bytes} bytes in {duration:.2f}s")
        return stats
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_scanner.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/datadeduplication/scanner.py tests/test_scanner.py
git commit -m "feat: add scanner module with file metadata collection"
```

---

### Task 5: Worker Base and Hash Worker

**Files:**
- Create: `src/datadeduplication/workers/__init__.py`
- Create: `src/datadeduplication/workers/base.py`
- Create: `src/datadeduplication/workers/hash_worker.py`
- Create: `tests/test_hash_worker.py`

**Interfaces:**
- Produces: `BaseWorker` class with `run()`, `process_task()`, `claim_task()`, `complete_task()`
- Produces: `HashWorker` class extending `BaseWorker`
- Consumes: `Config`, `Database`, `Tarefa`, `Arquivo`, `TaskType`, `TaskStatus`

- [ ] **Step 1: Create src/datadeduplication/workers/__init__.py**

```python
"""Worker modules for task processing."""
```

- [ ] **Step 2: Create src/datadeduplication/workers/base.py**

```python
"""Base worker class for task processing."""

import logging
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

from sqlalchemy import text

from datadeduplication.config import Config
from datadeduplication.database import Database
from datadeduplication.enums import TaskStatus, TaskType
from datadeduplication.models import Arquivo, Tarefa

logger = logging.getLogger(__name__)


class BaseWorker(ABC):
    """Base class for all workers."""

    def __init__(self, config: Config, db: Database, task_type: TaskType):
        self.config = config
        self.db = db
        self.task_type = task_type
        self.worker_id = f"{task_type.value}-{uuid.uuid4().hex[:8]}"
        self._running = False

    @abstractmethod
    def process_task(self, tarefa: Tarefa, arquivo: Arquivo) -> None:
        """Process a single task. Must be implemented by subclasses."""
        pass

    @property
    def batch_size(self) -> int:
        """Number of tasks to claim at once."""
        return 100

    def claim_task(self, session) -> Optional[Tarefa]:
        """Claim a task using FOR UPDATE SKIP LOCKED."""
        query = text("""
            SELECT id FROM tarefas
            WHERE tipo = :tipo AND status = :status
            ORDER BY prioridade DESC
            LIMIT :batch_size
            FOR UPDATE SKIP LOCKED
        """)

        result = session.execute(
            query,
            {
                "tipo": self.task_type.value,
                "status": TaskStatus.QUEUED.value,
                "batch_size": self.batch_size,
            },
        )

        task_ids = [row[0] for row in result.fetchall()]
        if not task_ids:
            return None

        # Get the first task and mark as running
        tarefa = session.get(Tarefa, task_ids[0])
        if tarefa:
            tarefa.status = TaskStatus.RUNNING.value
            tarefa.worker_id = self.worker_id
            tarefa.data_inicio = datetime.now()
            session.commit()

        return tarefa

    def complete_task(self, session, tarefa: Tarefa, success: bool, error_msg: str = None) -> None:
        """Mark a task as completed or failed."""
        if success:
            tarefa.status = TaskStatus.DONE.value
            tarefa.data_conclusao = datetime.now()
        else:
            tarefa.tentativas += 1
            if tarefa.tentativas >= tarefa.max_tentativas:
                tarefa.status = TaskStatus.ERROR.value
            else:
                tarefa.status = TaskStatus.RETRY.value
            tarefa.mensagem_erro = error_msg
            tarefa.data_conclusao = datetime.now()

        session.commit()

    def run(self, batch_size: int = None) -> dict:
        """Run the worker processing loop.

        Returns:
            Dict with processing statistics.
        """
        self._running = True
        processed = 0
        errors = 0

        logger.info(f"Worker {self.worker_id} starting")

        while self._running:
            with self.db.session() as session:
                tarefa = self.claim_task(session)

                if tarefa is None:
                    logger.debug(f"Worker {self.worker_id}: no tasks available")
                    break

                arquivo = session.get(Arquivo, tarefa.arquivo_id)
                if arquivo is None:
                    self.complete_task(session, tarefa, False, "File not found in database")
                    errors += 1
                    continue

                try:
                    self.process_task(tarefa, arquivo)
                    self.complete_task(session, tarefa, True)
                    processed += 1
                except Exception as e:
                    logger.error(f"Worker {self.worker_id}: error processing task {tarefa.id}: {e}")
                    self.complete_task(session, tarefa, False, str(e))
                    errors += 1

        logger.info(f"Worker {self.worker_id} finished: {processed} processed, {errors} errors")
        return {"processed": processed, "errors": errors}

    def stop(self) -> None:
        """Stop the worker."""
        self._running = False
```

- [ ] **Step 3: Create src/datadeduplication/workers/hash_worker.py**

```python
"""Hash worker for SHA-256 computation."""

import hashlib
import logging
from pathlib import Path

from datadeduplication.config import Config
from datadeduplication.database import Database
from datadeduplication.enums import TaskType
from datadeduplication.models import Arquivo, Tarefa
from datadeduplication.workers.base import BaseWorker

logger = logging.getLogger(__name__)


class HashWorker(BaseWorker):
    """Worker that computes SHA-256 hashes for files."""

    def __init__(self, config: Config, db: Database):
        super().__init__(config, db, TaskType.HASH)

    @property
    def batch_size(self) -> int:
        return self.config.worker_hash_batch

    def compute_hash(self, filepath: Path) -> str:
        """Compute SHA-256 hash of a file."""
        sha256 = hashlib.sha256()
        try:
            with open(filepath, "rb") as f:
                while True:
                    chunk = f.read(8192)
                    if not chunk:
                        break
                    sha256.update(chunk)
            return sha256.hexdigest()
        except PermissionError:
            logger.warning(f"Permission denied: {filepath}")
            raise
        except Exception as e:
            logger.error(f"Error computing hash for {filepath}: {e}")
            raise

    def process_task(self, tarefa: Tarefa, arquivo: Arquivo) -> None:
        """Compute and store SHA-256 hash."""
        filepath = Path(arquivo.caminho)
        if not filepath.exists():
            raise FileNotFoundError(f"File not found: {filepath}")

        hash_value = self.compute_hash(filepath)
        arquivo.hash_sha256 = hash_value
        logger.debug(f"Hash computed for {arquivo.caminho}: {hash_value[:16]}...")
```

- [ ] **Step 4: Create tests/test_hash_worker.py**

```python
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
```

- [ ] **Step 5: Run tests to verify**

Run: `pytest tests/test_hash_worker.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
git add src/datadeduplication/workers/ tests/test_hash_worker.py
git commit -m "feat: add worker base class and hash worker"
```

---

### Task 6: Analyze Worker

**Files:**
- Create: `src/datadeduplication/workers/analyze_worker.py`
- Create: `tests/test_analyze_worker.py`

**Interfaces:**
- Produces: `AnalyzeWorker` class extending `BaseWorker`
- Methods: `analyze_pdf()`, `analyze_docx()`, `analyze_xlsx()`, `analyze_image()`, `analyze_audio()`, `analyze_video()`, `analyze_text()`
- Consumes: `Config`, `Database`, `Arquivo`, `Tarefa`, `TaskType`

- [ ] **Step 1: Create src/datadeduplication/workers/analyze_worker.py**

```python
"""Analyze worker for metadata extraction."""

import json
import logging
import subprocess
from pathlib import Path
from typing import Dict, Optional

from datadeduplication.config import Config
from datadeduplication.database import Database
from datadeduplication.enums import TaskType
from datadeduplication.models import Arquivo, Tarefa
from datadeduplication.workers.base import BaseWorker

logger = logging.getLogger(__name__)


class AnalyzeWorker(BaseWorker):
    """Worker that extracts lightweight metadata from files."""

    def __init__(self, config: Config, db: Database):
        super().__init__(config, db, TaskType.ANALYZE)

    @property
    def batch_size(self) -> int:
        return self.config.worker_analyze_batch

    def analyze_pdf(self, filepath: Path) -> Dict:
        """Extract metadata from PDF files."""
        try:
            from PyPDF2 import PdfReader

            reader = PdfReader(str(filepath))
            info = reader.metadata

            return {
                "paginas": len(reader.pages),
                "autor": info.author if info else None,
                "titulo": info.title if info else None,
                "versao": reader.pdf_header if hasattr(reader, "pdf_header") else None,
            }
        except Exception as e:
            logger.warning(f"Error analyzing PDF {filepath}: {e}")
            return {"erro": str(e)}

    def analyze_docx(self, filepath: Path) -> Dict:
        """Extract metadata from DOCX files."""
        try:
            from docx import Document

            doc = Document(str(filepath))
            props = doc.core_properties

            return {
                "paragrafos": len(doc.paragraphs),
                "autor": props.author,
                "titulo": props.title,
                "palavras": sum(len(p.text.split()) for p in doc.paragraphs),
            }
        except Exception as e:
            logger.warning(f"Error analyzing DOCX {filepath}: {e}")
            return {"erro": str(e)}

    def analyze_xlsx(self, filepath: Path) -> Dict:
        """Extract metadata from XLSX files."""
        try:
            from openpyxl import load_workbook

            wb = load_workbook(str(filepath), read_only=True)

            return {
                "sheets": len(wb.sheetnames),
                "sheet_names": wb.sheetnames,
                "linhas": sum(ws.max_row or 0 for ws in wb.worksheets),
                "colunas": max(ws.max_column or 0 for ws in wb.worksheets),
            }
        except Exception as e:
            logger.warning(f"Error analyzing XLSX {filepath}: {e}")
            return {"erro": str(e)}

    def analyze_pptx(self, filepath: Path) -> Dict:
        """Extract metadata from PPTX files."""
        try:
            from pptx import Presentation

            prs = Presentation(str(filepath))

            return {
                "slides": len(prs.slides),
                "autor": prs.core_properties.author,
                "titulo": prs.core_properties.title,
            }
        except Exception as e:
            logger.warning(f"Error analyzing PPTX {filepath}: {e}")
            return {"erro": str(e)}

    def analyze_text(self, filepath: Path) -> Dict:
        """Extract metadata from text files."""
        try:
            content = filepath.read_text(encoding="utf-8", errors="ignore")
            lines = content.split("\n")

            return {
                "linhas": len(lines),
                "caracteres": len(content),
                "vazio": len(content.strip()) == 0,
            }
        except Exception as e:
            logger.warning(f"Error analyzing text {filepath}: {e}")
            return {"erro": str(e)}

    def analyze_image(self, filepath: Path) -> Dict:
        """Extract metadata from image files."""
        try:
            from PIL import Image
            from PIL.ExifTags import TAGS

            img = Image.open(str(filepath))
            metadata = {
                "largura": img.width,
                "altura": img.height,
                "formato": img.format,
                "modo": img.mode,
            }

            # Extract EXIF data if available
            exif_data = img.getexif()
            if exif_data:
                exif_dict = {}
                for tag_id, value in exif_data.items():
                    tag_name = TAGS.get(tag_id, tag_id)
                    if isinstance(value, (str, int, float)):
                        exif_dict[tag_name] = value
                if exif_dict:
                    metadata["exif"] = exif_dict

            return metadata
        except Exception as e:
            logger.warning(f"Error analyzing image {filepath}: {e}")
            return {"erro": str(e)}

    def analyze_audio(self, filepath: Path) -> Dict:
        """Extract metadata from audio files."""
        try:
            from mutagen import File as MutagenFile

            audio = MutagenFile(str(filepath))
            if audio is None:
                return {"erro": "Unsupported audio format"}

            metadata = {
                "duracao_segundos": round(audio.info.length, 2) if audio.info else None,
                "bitrate": audio.info.bitrate if audio.info else None,
                "sample_rate": audio.info.sample_rate if audio.info else None,
                "canais": audio.info.channels if audio.info else None,
            }

            # Add tags if available
            if audio.tags:
                metadata["tags"] = {str(k): str(v) for k, v in audio.tags.items() if isinstance(v, (str, int))}

            return metadata
        except Exception as e:
            logger.warning(f"Error analyzing audio {filepath}: {e}")
            return {"erro": str(e)}

    def analyze_video(self, filepath: Path) -> Dict:
        """Extract metadata from video files using ffprobe."""
        try:
            cmd = [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                str(filepath),
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                return {"erro": f"ffprobe failed: {result.stderr}"}

            data = json.loads(result.stdout)

            metadata = {
                "duracao_segundos": float(data.get("format", {}).get("duration", 0)),
                "tamanho_bytes": int(data.get("format", {}).get("size", 0)),
            }

            # Extract video stream info
            for stream in data.get("streams", []):
                if stream.get("codec_type") == "video":
                    metadata["largura"] = stream.get("width")
                    metadata["altura"] = stream.get("height")
                    metadata["codec_video"] = stream.get("codec_name")
                    metadata["fps"] = stream.get("r_frame_rate")
                    break

            # Extract audio stream info
            for stream in data.get("streams", []):
                if stream.get("codec_type") == "audio":
                    metadata["codec_audio"] = stream.get("codec_name")
                    metadata["sample_rate"] = stream.get("sample_rate")
                    break

            return metadata
        except subprocess.TimeoutExpired:
            return {"erro": "ffprobe timeout"}
        except FileNotFoundError:
            return {"erro": "ffprobe not installed"}
        except Exception as e:
            logger.warning(f"Error analyzing video {filepath}: {e}")
            return {"erro": str(e)}

    def get_analyzer_for_extension(self, ext: str):
        """Get the appropriate analyzer function for a file extension."""
        analyzers = {
            ".pdf": self.analyze_pdf,
            ".docx": self.analyze_docx,
            ".xlsx": self.analyze_xlsx,
            ".pptx": self.analyze_pptx,
            ".txt": self.analyze_text,
            ".csv": self.analyze_text,
            ".json": self.analyze_text,
            ".jpg": self.analyze_image,
            ".jpeg": self.analyze_image,
            ".png": self.analyze_image,
            ".tiff": self.analyze_image,
            ".bmp": self.analyze_image,
            ".mp3": self.analyze_audio,
            ".flac": self.analyze_audio,
            ".wav": self.analyze_audio,
            ".ogg": self.analyze_audio,
            ".mp4": self.analyze_video,
            ".avi": self.analyze_video,
            ".mkv": self.analyze_video,
            ".mov": self.analyze_video,
        }
        return analyzers.get(ext)

    def process_task(self, tarefa: Tarefa, arquivo: Arquivo) -> None:
        """Analyze file and store metadata."""
        filepath = Path(arquivo.caminho)
        if not filepath.exists():
            raise FileNotFoundError(f"File not found: {filepath}")

        # Check file size limit
        if filepath.stat().st_size > self.config.tamanho_max_para_analise:
            logger.debug(f"Skipping large file: {filepath}")
            arquivo.metadados_json = {"skipped": "file too large"}
            return

        # Check if extension is in allowed list
        ext = arquivo.extensao.lower()
        if ext not in [f".{t}" for t in self.config.tipos_analise]:
            logger.debug(f"Skipping unsupported extension: {ext}")
            arquivo.metadados_json = {"skipped": f"extension {ext} not in analysis list"}
            return

        analyzer = self.get_analyzer_for_extension(ext)
        if analyzer is None:
            arquivo.metadados_json = {"skipped": f"no analyzer for {ext}"}
            return

        metadata = analyzer(filepath)
        arquivo.metadados_json = metadata
        logger.debug(f"Analyzed {filepath}: {json.dumps(metadata)[:100]}...")
```

- [ ] **Step 2: Create tests/test_analyze_worker.py**

```python
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
```

- [ ] **Step 3: Run tests to verify**

Run: `pytest tests/test_analyze_worker.py -v`
Expected: PASS (3 tests)

- [ ] **Step 4: Commit**

```bash
git add src/datadeduplication/workers/analyze_worker.py tests/test_analyze_worker.py
git commit -m "feat: add analyze worker for metadata extraction"
```

---

### Task 7: Orchestrator

**Files:**
- Create: `src/datadeduplication/orchestrator.py`

**Interfaces:**
- Produces: `Orchestrator` class with `run()`, `queue_pending_tasks()`, `retry_failed_tasks()`, `get_stats()`
- Consumes: `Config`, `Database`, `Tarefa`, `TaskStatus`

- [ ] **Step 1: Create src/datadeduplication/orchestrator.py**

```python
"""Orchestrator for task queue management."""

import logging
import time
from datetime import datetime
from typing import Dict

from sqlalchemy import text

from datadeduplication.config import Config
from datadeduplication.database import Database
from datadeduplication.enums import TaskStatus
from datadeduplication.models import Tarefa

logger = logging.getLogger(__name__)


class Orchestrator:
    """Manages task queue priority and retries."""

    def __init__(self, config: Config, db: Database):
        self.config = config
        self.db = db
        self._running = False

    def queue_pending_tasks(self) -> int:
        """Move pending tasks to queued status.

        Returns:
            Number of tasks queued.
        """
        with self.db.session() as session:
            result = session.execute(
                text("""
                    UPDATE tarefas
                    SET status = :new_status
                    WHERE status = :old_status
                """),
                {
                    "new_status": TaskStatus.QUEUED.value,
                    "old_status": TaskStatus.PENDING.value,
                },
            )
            count = result.rowcount
            if count > 0:
                logger.info(f"Queued {count} pending tasks")
            return count

    def retry_failed_tasks(self) -> int:
        """Move retryable tasks back to queued status.

        Returns:
            Number of tasks retried.
        """
        with self.db.session() as session:
            result = session.execute(
                text("""
                    UPDATE tarefas
                    SET status = :new_status, tentativas = tentativas + 1
                    WHERE status = :old_status AND tentativas < max_tentativas
                """),
                {
                    "new_status": TaskStatus.QUEUED.value,
                    "old_status": TaskStatus.RETRY.value,
                },
            )
            count = result.rowcount
            if count > 0:
                logger.info(f"Retried {count} failed tasks")
            return count

    def set_priority_by_size(self) -> int:
        """Set task priority based on file size (smaller files first).

        Returns:
            Number of tasks updated.
        """
        with self.db.session() as session:
            result = session.execute(
                text("""
                    UPDATE tarefas t
                    JOIN arquivos a ON t.arquivo_id = a.id
                    SET t.prioridade = CASE
                        WHEN a.tamanho < 1024 THEN 100
                        WHEN a.tamanho < 1048576 THEN 50
                        WHEN a.tamanho < 10485760 THEN 10
                        ELSE 1
                    END
                    WHERE t.status = :status
                """),
                {"status": TaskStatus.QUEUED.value},
            )
            count = result.rowcount
            if count > 0:
                logger.info(f"Updated priority for {count} tasks")
            return count

    def get_stats(self) -> Dict:
        """Get queue statistics."""
        with self.db.session() as session:
            result = session.execute(
                text("""
                    SELECT status, tipo, COUNT(*) as count
                    FROM tarefas
                    GROUP BY status, tipo
                """)
            )

            stats = {}
            for row in result.fetchall():
                status, tipo, count = row
                if tipo not in stats:
                    stats[tipo] = {}
                stats[tipo][status] = count

            return stats

    def run(self, interval: int = None) -> None:
        """Run orchestrator continuously.

        Args:
            interval: Seconds between iterations. Defaults to config value.
        """
        self._running = True
        interval = interval or self.config.orchestrate_interval

        logger.info(f"Orchestrator starting with {interval}s interval")

        while self._running:
            try:
                self.queue_pending_tasks()
                self.retry_failed_tasks()
                self.set_priority_by_size()

                stats = self.get_stats()
                logger.info(f"Queue stats: {stats}")

            except Exception as e:
                logger.error(f"Orchestrator error: {e}")

            time.sleep(interval)

    def stop(self) -> None:
        """Stop the orchestrator."""
        self._running = False
```

- [ ] **Step 2: Run existing tests to verify no regressions**

Run: `pytest tests/ -v`
Expected: PASS (all tests)

- [ ] **Step 3: Commit**

```bash
git add src/datadeduplication/orchestrator.py
git commit -m "feat: add orchestrator for task queue management"
```

---

### Task 8: Analyzer Module

**Files:**
- Create: `src/datadeduplication/analyzer.py`
- Create: `tests/test_analyzer.py`

**Interfaces:**
- Produces: `Analyzer` class with `find_duplicates()`, `find_large()`, `find_old()`, `find_temp()`, `find_empty()`, `search_content()`
- Consumes: `Config`, `Database`, `Arquivo`

- [ ] **Step 1: Create src/datadeduplication/analyzer.py**

```python
"""Analysis queries for file inventory."""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
from sqlalchemy import text

from datadeduplication.config import Config
from datadeduplication.database import Database

logger = logging.getLogger(__name__)

# Common temporary file extensions
TEMP_EXTENSIONS = {".tmp", ".bak", ".old", ".log", ".temp", ".swp", ".swo", "~"}


class Analyzer:
    """Queries for file analysis and reporting."""

    def __init__(self, config: Config, db: Database):
        self.config = config
        self.db = db

    def find_duplicates(self, min_size: int = 0) -> List[Dict]:
        """Find duplicate files by SHA-256 hash.

        Args:
            min_size: Minimum file size in bytes to consider.

        Returns:
            List of duplicate groups with file details.
        """
        with self.db.session() as session:
            result = session.execute(
                text("""
                    SELECT hash_sha256, COUNT(*) as count, SUM(tamanho) as total_size
                    FROM arquivos
                    WHERE hash_sha256 IS NOT NULL AND tamanho >= :min_size
                    GROUP BY hash_sha256
                    HAVING COUNT(*) > 1
                    ORDER BY total_size DESC
                """),
                {"min_size": min_size},
            )

            duplicates = []
            for row in result.fetchall():
                hash_value, count, total_size = row

                # Get all files with this hash
                files_result = session.execute(
                    text("""
                        SELECT id, caminho, nome, tamanho, data_criacao, data_modificacao
                        FROM arquivos
                        WHERE hash_sha256 = :hash
                        ORDER BY data_criacao ASC
                    """),
                    {"hash": hash_value},
                )

                files = []
                for file_row in files_result.fetchall():
                    files.append({
                        "id": file_row[0],
                        "caminho": file_row[1],
                        "nome": file_row[2],
                        "tamanho": file_row[3],
                        "data_criacao": file_row[4].isoformat() if file_row[4] else None,
                        "data_modificacao": file_row[5].isoformat() if file_row[5] else None,
                    })

                duplicates.append({
                    "hash": hash_value,
                    "count": count,
                    "total_size": total_size,
                    "wasted_size": total_size - files[0]["tamanho"] if files else 0,
                    "files": files,
                    "suggestion": f"Keep oldest: {files[0]['caminho']}" if files else None,
                })

            return duplicates

    def find_large(self, min_bytes: int = 104857600) -> List[Dict]:
        """Find files larger than threshold.

        Args:
            min_bytes: Minimum size in bytes (default 100MB).

        Returns:
            List of large files.
        """
        with self.db.session() as session:
            result = session.execute(
                text("""
                    SELECT id, caminho, nome, extensao, tamanho, data_modificacao
                    FROM arquivos
                    WHERE tamanho >= :min_bytes
                    ORDER BY tamanho DESC
                """),
                {"min_bytes": min_bytes},
            )

            return [
                {
                    "id": row[0],
                    "caminho": row[1],
                    "nome": row[2],
                    "extensao": row[3],
                    "tamanho": row[4],
                    "tamanho_mb": round(row[4] / 1048576, 2),
                    "data_modificacao": row[5].isoformat() if row[5] else None,
                }
                for row in result.fetchall()
            ]

    def find_old(self, days: int = 365) -> List[Dict]:
        """Find files not accessed in specified days.

        Args:
            days: Number of days since last access.

        Returns:
            List of old files.
        """
        cutoff = datetime.now() - timedelta(days=days)

        with self.db.session() as session:
            result = session.execute(
                text("""
                    SELECT id, caminho, nome, tamanho, data_acesso, data_modificacao
                    FROM arquivos
                    WHERE data_acesso < :cutoff
                    ORDER BY data_acesso ASC
                """),
                {"cutoff": cutoff},
            )

            return [
                {
                    "id": row[0],
                    "caminho": row[1],
                    "nome": row[2],
                    "tamanho": row[3],
                    "data_acesso": row[4].isoformat() if row[4] else None,
                    "data_modificacao": row[5].isoformat() if row[5] else None,
                    "dias_sem_acesso": (datetime.now() - row[4]).days if row[4] else None,
                }
                for row in result.fetchall()
            ]

    def find_temp(self) -> List[Dict]:
        """Find temporary files by extension.

        Returns:
            List of temporary files.
        """
        with self.db.session() as session:
            # Build LIKE conditions for each extension
            conditions = " OR ".join(
                [f"extensao LIKE '%{ext}'" for ext in TEMP_EXTENSIONS]
            )

            result = session.execute(
                text(f"""
                    SELECT id, caminho, nome, extensao, tamanho, data_modificacao
                    FROM arquivos
                    WHERE {conditions}
                    ORDER BY tamanho DESC
                """)
            )

            return [
                {
                    "id": row[0],
                    "caminho": row[1],
                    "nome": row[2],
                    "extensao": row[3],
                    "tamanho": row[4],
                    "data_modificacao": row[5].isoformat() if row[5] else None,
                }
                for row in result.fetchall()
            ]

    def find_empty(self) -> List[Dict]:
        """Find empty files (0 bytes).

        Returns:
            List of empty files.
        """
        with self.db.session() as session:
            result = session.execute(
                text("""
                    SELECT id, caminho, nome, extensao, data_modificacao
                    FROM arquivos
                    WHERE tamanho = 0
                    ORDER BY caminho
                """)
            )

            return [
                {
                    "id": row[0],
                    "caminho": row[1],
                    "nome": row[2],
                    "extensao": row[3],
                    "data_modificacao": row[4].isoformat() if row[4] else None,
                }
                for row in result.fetchall()
            ]

    def search_content(self, keyword: str) -> List[Dict]:
        """Search in metadata JSON fields.

        Args:
            keyword: Search term to find in metadata.

        Returns:
            List of files with matching metadata.
        """
        with self.db.session() as session:
            result = session.execute(
                text("""
                    SELECT id, caminho, nome, extensao, tamanho, metadados_json
                    FROM arquivos
                    WHERE JSON_SEARCH(metadados_json, 'one', :keyword) IS NOT NULL
                    ORDER BY caminho
                """),
                {"keyword": f"%{keyword}%"},
            )

            return [
                {
                    "id": row[0],
                    "caminho": row[1],
                    "nome": row[2],
                    "extensao": row[3],
                    "tamanho": row[4],
                    "metadados": row[5],
                }
                for row in result.fetchall()
            ]

    def export_report(self, data: List[Dict], output_path: str, format: str = "json") -> str:
        """Export analysis results to file.

        Args:
            data: List of dicts to export.
            output_path: Path to output file.
            format: Output format ('json' or 'csv').

        Returns:
            Path to exported file.
        """
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        if format == "json":
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        elif format == "csv":
            df = pd.DataFrame(data)
            df.to_csv(path, index=False)
        else:
            raise ValueError(f"Unsupported format: {format}")

        logger.info(f"Report exported to {path}")
        return str(path)
```

- [ ] **Step 2: Create tests/test_analyzer.py**

```python
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
```

- [ ] **Step 3: Run tests to verify**

Run: `pytest tests/test_analyzer.py -v`
Expected: PASS (2 tests)

- [ ] **Step 4: Commit**

```bash
git add src/datadeduplication/analyzer.py tests/test_analyzer.py
git commit -m "feat: add analyzer module with duplicate and cleanup queries"
```

---

### Task 9: Quarantine Module

**Files:**
- Create: `src/datadeduplication/quarantine.py`

**Interfaces:**
- Produces: `QuarantineManager` class with `move_to_quarantine()`, `list_quarantine()`, `restore_from_quarantine()`
- Consumes: `Config`, `Database`, `Arquivo`

- [ ] **Step 1: Create src/datadeduplication/quarantine.py**

```python
"""Quarantine manager for safe file removal."""

import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from datadeduplication.config import Config
from datadeduplication.database import Database
from datadeduplication.models import Arquivo

logger = logging.getLogger(__name__)


class QuarantineManager:
    """Manages file quarantine operations."""

    def __init__(self, config: Config, db: Database):
        self.config = config
        self.db = db
        self.quarantine_path = config.quarentena_path
        self.quarantine_path.mkdir(parents=True, exist_ok=True)

    def _get_quarantine_dest(self, filepath: Path) -> Path:
        """Generate unique quarantine destination path."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest_dir = self.quarantine_path / timestamp
        dest_dir.mkdir(parents=True, exist_ok=True)
        return dest_dir / filepath.name

    def move_to_quarantine(self, file_ids: List[int], dry_run: bool = False) -> Dict:
        """Move files to quarantine directory.

        Args:
            file_ids: List of file IDs to quarantine.
            dry_run: If True, only list what would be moved.

        Returns:
            Dict with operation results.
        """
        results = {"moved": [], "skipped": [], "errors": []}

        with self.db.session() as session:
            for file_id in file_ids:
                arquivo = session.get(Arquivo, file_id)
                if arquivo is None:
                    results["skipped"].append({"id": file_id, "reason": "not found"})
                    continue

                filepath = Path(arquivo.caminho)
                if not filepath.exists():
                    results["skipped"].append({"id": file_id, "caminho": str(filepath), "reason": "file not found"})
                    continue

                if dry_run:
                    results["moved"].append({
                        "id": file_id,
                        "caminho": str(filepath),
                        "destino": str(self._get_quarantine_dest(filepath)),
                    })
                    continue

                try:
                    dest = self._get_quarantine_dest(filepath)
                    shutil.move(str(filepath), str(dest))

                    # Save original path for potential restore
                    metadata_file = dest.with_suffix(dest.suffix + ".quarantine.json")
                    with open(metadata_file, "w") as f:
                        json.dump({
                            "original_path": str(filepath),
                            "quarantine_date": datetime.now().isoformat(),
                            "file_id": file_id,
                        }, f)

                    results["moved"].append({
                        "id": file_id,
                        "caminho": str(filepath),
                        "destino": str(dest),
                    })
                    logger.info(f"Quarantined: {filepath} -> {dest}")

                except Exception as e:
                    results["errors"].append({
                        "id": file_id,
                        "caminho": str(filepath),
                        "erro": str(e),
                    })
                    logger.error(f"Error quarantining {filepath}: {e}")

        return results

    def list_quarantine(self) -> List[Dict]:
        """List all quarantined files.

        Returns:
            List of quarantined file details.
        """
        items = []

        for metadata_file in self.quarantine_path.rglob("*.quarantine.json"):
            try:
                with open(metadata_file) as f:
                    metadata = json.load(f)

                quarantined_file = metadata_file.with_suffix("")
                items.append({
                    "original_path": metadata["original_path"],
                    "quarantine_path": str(quarantined_file),
                    "quarantine_date": metadata["quarantine_date"],
                    "file_id": metadata["file_id"],
                    "exists": quarantined_file.exists(),
                })
            except Exception as e:
                logger.error(f"Error reading quarantine metadata {metadata_file}: {e}")

        return items

    def restore_from_quarantine(self, quarantine_path: str) -> Dict:
        """Restore a file from quarantine.

        Args:
            quarantine_path: Path to the quarantined file.

        Returns:
            Dict with operation result.
        """
        qpath = Path(quarantine_path)
        metadata_file = qpath.with_suffix(qpath.suffix + ".quarantine.json")

        if not metadata_file.exists():
            return {"success": False, "error": "Quarantine metadata not found"}

        try:
            with open(metadata_file) as f:
                metadata = json.load(f)

            original_path = Path(metadata["original_path"])

            # Ensure original directory exists
            original_path.parent.mkdir(parents=True, exist_ok=True)

            if original_path.exists():
                return {"success": False, "error": "Original path already exists"}

            shutil.move(str(qpath), str(original_path))
            metadata_file.unlink()

            logger.info(f"Restored: {qpath} -> {original_path}")
            return {"success": True, "original_path": str(original_path)}

        except Exception as e:
            logger.error(f"Error restoring {quarantine_path}: {e}")
            return {"success": False, "error": str(e)}
```

- [ ] **Step 2: Run existing tests to verify no regressions**

Run: `pytest tests/ -v`
Expected: PASS (all tests)

- [ ] **Step 3: Commit**

```bash
git add src/datadeduplication/quarantine.py
git commit -m "feat: add quarantine manager for safe file removal"
```

---

### Task 10: CLI Entry Point

**Files:**
- Create: `src/datadeduplication/__main__.py`

**Interfaces:**
- Produces: CLI with commands `scan`, `orchestrate`, `worker-hash`, `worker-analyze`, `analyze`, `quarantine`, `clean`
- Consumes: All modules (Config, Database, Scanner, Orchestrator, HashWorker, AnalyzeWorker, Analyzer, QuarantineManager)

- [ ] **Step 1: Create src/datadeduplication/__main__.py**

```python
"""CLI entry point for datadeduplication tool."""

import argparse
import json
import logging
import sys
from pathlib import Path

from datadeduplication.analyzer import Analyzer
from datadeduplication.config import Config
from datadeduplication.database import Database
from datadeduplication.orchestrator import Orchestrator
from datadeduplication.quarantine import QuarantineManager
from datadeduplication.scanner import Scanner
from datadeduplication.workers.analyze_worker import AnalyzeWorker
from datadeduplication.workers.hash_worker import HashWorker


def setup_logging(config: Config) -> None:
    """Configure logging to file and console."""
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(config.log_level)
    console_handler.setFormatter(logging.Formatter(log_format))

    # File handler
    file_handler = logging.FileHandler(config.log_file, encoding="utf-8")
    file_handler.setLevel("DEBUG")
    file_handler.setFormatter(logging.Formatter(log_format))

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel("DEBUG")
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)


def cmd_scan(args, config: Config, db: Database) -> None:
    """Execute scan command."""
    scanner = Scanner(config, db)
    stats = scanner.scan(resume=args.resume)
    print(json.dumps(stats, indent=2))


def cmd_orchestrate(args, config: Config, db: Database) -> None:
    """Execute orchestrate command."""
    orchestrator = Orchestrator(config, db)
    try:
        orchestrator.run(interval=args.interval)
    except KeyboardInterrupt:
        orchestrator.stop()
        print("\nOrchestrator stopped.")


def cmd_worker_hash(args, config: Config, db: Database) -> None:
    """Execute hash worker command."""
    worker = HashWorker(config, db)
    try:
        result = worker.run(batch_size=args.batch_size)
        print(json.dumps(result, indent=2))
    except KeyboardInterrupt:
        worker.stop()
        print("\nWorker stopped.")


def cmd_worker_analyze(args, config: Config, db: Database) -> None:
    """Execute analyze worker command."""
    worker = AnalyzeWorker(config, db)
    try:
        result = worker.run(batch_size=args.batch_size)
        print(json.dumps(result, indent=2))
    except KeyboardInterrupt:
        worker.stop()
        print("\nWorker stopped.")


def cmd_analyze(args, config: Config, db: Database) -> None:
    """Execute analyze command."""
    analyzer = Analyzer(config, db)

    analysis_type = args.type
    output_format = args.format
    output_path = args.output

    if analysis_type == "duplicates":
        data = analyzer.find_duplicates(min_size=args.min_size)
    elif analysis_type == "large":
        limit_bytes = parse_size(args.limit)
        data = analyzer.find_large(min_bytes=limit_bytes)
    elif analysis_type == "old":
        data = analyzer.find_old(days=args.days)
    elif analysis_type == "temp":
        data = analyzer.find_temp()
    elif analysis_type == "empty":
        data = analyzer.find_empty()
    elif analysis_type == "search":
        if not args.keyword:
            print("Error: --keyword required for search analysis")
            sys.exit(1)
        data = analyzer.search_content(keyword=args.keyword)
    else:
        print(f"Error: Unknown analysis type: {analysis_type}")
        sys.exit(1)

    print(f"Found {len(data)} results")

    if output_path:
        path = analyzer.export_report(data, output_path, format=output_format)
        print(f"Report saved to: {path}")
    else:
        print(json.dumps(data, indent=2, default=str))


def cmd_quarantine(args, config: Config, db: Database) -> None:
    """Execute quarantine command."""
    quarantine_mgr = QuarantineManager(config, db)

    if args.list:
        items = quarantine_mgr.list_quarantine()
        print(json.dumps(items, indent=2))
        return

    if not args.from_report:
        print("Error: --from-report required")
        sys.exit(1)

    with open(args.from_report) as f:
        report = json.load(f)

    file_ids = [item["id"] for item in report if "id" in item]

    if not file_ids:
        print("No files to quarantine")
        return

    result = quarantine_mgr.move_to_quarantine(file_ids, dry_run=args.dry_run)
    print(json.dumps(result, indent=2))


def cmd_clean(args, config: Config, db: Database) -> None:
    """Execute clean command (permanent deletion)."""
    if not args.confirm:
        print("Error: --confirm required for permanent deletion")
        sys.exit(1)

    if not args.from_report:
        print("Error: --from-report required")
        sys.exit(1)

    with open(args.from_report) as f:
        report = json.load(f)

    file_paths = [item["caminho"] for item in report if "caminho" in item]

    if not file_paths:
        print("No files to delete")
        return

    print(f"WARNING: About to permanently delete {len(file_paths)} files")
    for path in file_paths[:10]:
        print(f"  - {path}")
    if len(file_paths) > 10:
        print(f"  ... and {len(file_paths) - 10} more")

    confirm = input("Type 'DELETE' to confirm: ")
    if confirm != "DELETE":
        print("Cancelled")
        return

    deleted = 0
    errors = 0
    for path in file_paths:
        try:
            Path(path).unlink()
            deleted += 1
        except Exception as e:
            print(f"Error deleting {path}: {e}")
            errors += 1

    print(f"Deleted: {deleted}, Errors: {errors}")


def parse_size(size_str: str) -> int:
    """Parse size string like '1GB', '500MB' to bytes."""
    size_str = size_str.upper().strip()
    multipliers = {
        "B": 1,
        "KB": 1024,
        "MB": 1048576,
        "GB": 1073741824,
        "TB": 1099511627776,
    }

    for suffix, multiplier in multipliers.items():
        if size_str.endswith(suffix):
            number = size_str[:-len(suffix)]
            return int(float(number) * multiplier)

    return int(size_str)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Data Deduplication Tool - File analysis and cleanup",
        prog="datadeduplication",
    )
    parser.add_argument("--env", help="Path to .env file", default=None)

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Scan command
    scan_parser = subparsers.add_parser("scan", help="Scan directory and collect file metadata")
    scan_parser.add_argument("--path", help="Directory path to scan (overrides .env)")
    scan_parser.add_argument("--resume", action="store_true", help="Resume from last checkpoint")

    # Orchestrate command
    orch_parser = subparsers.add_parser("orchestrate", help="Run task orchestrator")
    orch_parser.add_argument("--interval", type=int, default=30, help="Seconds between iterations")

    # Worker hash command
    hash_parser = subparsers.add_parser("worker-hash", help="Run hash computation worker")
    hash_parser.add_argument("--batch-size", type=int, default=100, help="Tasks per batch")

    # Worker analyze command
    analyze_parser = subparsers.add_parser("worker-analyze", help="Run metadata analysis worker")
    analyze_parser.add_argument("--batch-size", type=int, default=50, help="Tasks per batch")

    # Analyze command
    analysis_parser = subparsers.add_parser("analyze", help="Run analysis queries")
    analysis_parser.add_argument("--type", required=True, choices=[
        "duplicates", "large", "old", "temp", "empty", "search"
    ], help="Analysis type")
    analysis_parser.add_argument("--min-size", type=int, default=0, help="Min size for duplicates")
    analysis_parser.add_argument("--limit", default="100MB", help="Size limit for large files")
    analysis_parser.add_argument("--days", type=int, default=365, help="Days for old files")
    analysis_parser.add_argument("--keyword", help="Search keyword")
    analysis_parser.add_argument("--output", help="Output file path")
    analysis_parser.add_argument("--format", choices=["json", "csv"], default="json", help="Output format")

    # Quarantine command
    quarantine_parser = subparsers.add_parser("quarantine", help="Manage file quarantine")
    quarantine_parser.add_argument("--from-report", help="JSON report file")
    quarantine_parser.add_argument("--dry-run", action="store_true", help="List without moving")
    quarantine_parser.add_argument("--list", action="store_true", help="List quarantined files")

    # Clean command
    clean_parser = subparsers.add_parser("clean", help="Permanently delete files")
    clean_parser.add_argument("--from-report", required=True, help="JSON report file")
    clean_parser.add_argument("--confirm", action="store_true", help="Confirm deletion")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Load config
    config = Config.from_env(args.env)

    # Override scan path if provided
    if hasattr(args, "path") and args.path:
        config.raiz_analise = Path(args.path)

    # Setup logging
    setup_logging(config)

    # Initialize database
    db = Database(config)
    db.create_tables()

    # Execute command
    commands = {
        "scan": cmd_scan,
        "orchestrate": cmd_orchestrate,
        "worker-hash": cmd_worker_hash,
        "worker-analyze": cmd_worker_analyze,
        "analyze": cmd_analyze,
        "quarantine": cmd_quarantine,
        "clean": cmd_clean,
    }

    try:
        commands[args.command](args, config, db)
    except KeyboardInterrupt:
        print("\nOperation cancelled.")
    except Exception as e:
        logging.error(f"Command failed: {e}", exc_info=True)
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run all tests to verify**

Run: `pytest tests/ -v`
Expected: PASS (all tests)

- [ ] **Step 3: Commit**

```bash
git add src/datadeduplication/__main__.py
git commit -m "feat: add CLI entry point with all commands"
```

---

### Task 11: README Documentation

**Files:**
- Create: `README.md`

- [ ] **Step 1: Create README.md**

```markdown
# Data Deduplication Tool

Ferramenta Python para análise completa de diretórios Windows, identificando arquivos candidatos à remoção via deduplicação, limpeza e inventário.

## Arquitetura

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│  scan        │────▶│  MySQL       │◀────│  orchestrate     │
│  (coleta)    │     │  (tarefas)   │     │  (prioridade)    │
└─────────────┘     └──────┬───────┘     └─────────────────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │ worker-  │ │ worker-  │ │ (futuro) │
        │ hash     │ │ analyze  │ │ cleanup  │
        └──────────┘ └──────────┘ └──────────┘
```

## Instalação

```bash
pip install -r requirements.txt
```

## Configuração

Copie `.env.example` para `.env` e configure:

```bash
cp .env.example .env
```

### Variáveis de Ambiente

| Variável | Descrição | Padrão |
|----------|-----------|--------|
| `RAIZ_ANALISE` | Diretório raiz para análise | `C:\dados` |
| `DB_HOST` | Host MySQL | `localhost` |
| `DB_PORT` | Porta MySQL | `3306` |
| `DB_USER` | Usuário MySQL | `root` |
| `DB_PASSWORD` | Senha MySQL | (vazio) |
| `DB_NAME` | Nome do banco | `datadeduplication` |
| `BATCH_SIZE` | Tamanho do batch para inserts | `1000` |
| `ANALISAR_METADATA` | Habilitar análise de metadata | `true` |
| `TAMANHO_MAX_PARA_ANALISE` | Tamanho máximo para análise (bytes) | `52428800` (50MB) |
| `QUARENTENA_PATH` | Pasta de quarentena | `C:\quarentena` |

## Uso

### 1. Varredura (Scan)

```bash
# Varredura completa
python -m datadeduplication scan --path "C:\dados"

# Retomar varredura interrompida
python -m datadeduplication scan --path "C:\dados" --resume
```

### 2. Orquestrador

```bash
# Rodar orquestrador continuamente
python -m datadeduplication orchestrate

# Com intervalo customizado (segundos)
python -m datadeduplication orchestrate --interval 60
```

### 3. Workers

```bash
# Worker de hash (SHA-256)
python -m datadeduplication worker-hash --batch-size 100

# Worker de análise de metadata
python -m datadeduplication worker-analyze --batch-size 50
```

### 4. Análises

```bash
# Arquivos duplicados
python -m datadeduplication analyze --type duplicates

# Arquivos grandes (>100MB)
python -m datadeduplication analyze --type large --limit 100MB

# Arquivos antigos (não acessados há >1 ano)
python -m datadeduplication analyze --type old --days 365

# Arquivos temporários
python -m datadeduplication analyze --type temp

# Arquivos vazios
python -m datadeduplication analyze --type empty

# Busca por conteúdo
python -m datadeduplication analyze --type search --keyword "contrato"

# Exportar relatório
python -m datadeduplication analyze --type duplicates --output report.json --format json
```

### 5. Quarentena

```bash
# Listar arquivos em quarentena
python -m datadeduplication quarantine --list

# Simular quarentena (dry-run)
python -m datadeduplication quarantine --from-report report.json --dry-run

# Mover para quarentena
python -m datadeduplication quarantine --from-report report.json
```

### 6. Limpeza

```bash
# Excluir permanentemente (requer --confirm)
python -m datadeduplication clean --from-report report.json --confirm
```

## Fluxo Recomendado

1. **Scan**: `python -m datadeduplication scan --path "C:\dados"`
2. **Orchestrate**: `python -m datadeduplication orchestrate` (em terminal separado)
3. **Workers**: Inicie workers em terminais separados:
   - `python -m datadeduplication worker-hash`
   - `python -m datadeduplication worker-analyze`
4. **Análise**: Após workers completarem:
   - `python -m datadeduplication analyze --type duplicates --output duplicates.json`
   - `python -m datadeduplication analyze --type old --output old_files.json`
5. **Quarentena**: `python -m datadeduplication quarantine --from-report duplicates.json --dry-run`
6. **Limpeza**: `python -m datadeduplication clean --from-report duplicates.json --confirm`

## Requisitos

- Python 3.10+
- MySQL 8+ (para `FOR UPDATE SKIP LOCKED`)
- Windows (para atributos de arquivo e proprietário)

## Dependências

- `python-dotenv` - Carregamento de variáveis de ambiente
- `sqlalchemy` - ORM e conexão com banco
- `pymysql` - Driver MySQL
- `PyPDF2` - Análise de PDF
- `python-docx` - Análise de DOCX
- `openpyxl` - Análise de XLSX
- `python-pptx` - Análise de PPTX
- `Pillow` - Análise de imagens
- `mutagen` - Análise de áudio
- `pandas` - Exportação de relatórios
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add README with installation and usage instructions"
```

---

### Task 12: Final Integration Test

**Files:**
- Create: `tests/test_integration.py`

- [ ] **Step 1: Create tests/test_integration.py**

```python
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
```

- [ ] **Step 2: Run all tests**

Run: `pytest tests/ -v`
Expected: PASS (all tests)

- [ ] **Step 3: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: add integration tests for workflow"
```

---

## Plan Summary

| Task | Description | Files Created |
|------|-------------|---------------|
| 1 | Project setup and config | `requirements.txt`, `.env.example`, `config.py` |
| 2 | Enums and models | `enums.py`, `models.py` |
| 3 | Database connection | `database.py` |
| 4 | Scanner module | `scanner.py` |
| 5 | Worker base and hash worker | `workers/base.py`, `workers/hash_worker.py` |
| 6 | Analyze worker | `workers/analyze_worker.py` |
| 7 | Orchestrator | `orchestrator.py` |
| 8 | Analyzer module | `analyzer.py` |
| 9 | Quarantine module | `quarantine.py` |
| 10 | CLI entry point | `__main__.py` |
| 11 | README documentation | `README.md` |
| 12 | Integration tests | `tests/test_integration.py` |
