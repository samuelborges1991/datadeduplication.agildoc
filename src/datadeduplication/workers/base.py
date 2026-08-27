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
        """Claim a single task using FOR UPDATE SKIP LOCKED."""
        query = text("""
            SELECT id FROM tarefas
            WHERE tipo = :tipo AND status = :status
            ORDER BY prioridade DESC
            LIMIT 1
            FOR UPDATE SKIP LOCKED
        """)

        result = session.execute(
            query,
            {
                "tipo": self.task_type.value,
                "status": TaskStatus.QUEUED.value,
            },
        )

        row = result.fetchone()
        if not row:
            return None

        tarefa = session.get(Tarefa, row[0])
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