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
