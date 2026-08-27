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
