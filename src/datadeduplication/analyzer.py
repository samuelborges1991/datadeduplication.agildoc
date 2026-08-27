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
