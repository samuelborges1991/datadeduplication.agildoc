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
