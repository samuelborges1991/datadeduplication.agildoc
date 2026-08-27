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