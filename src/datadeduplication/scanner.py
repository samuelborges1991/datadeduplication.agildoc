"""Directory scanner for file metadata collection."""

import hashlib
import json
import logging
import os
import signal
import stat
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from datadeduplication.config import Config
from datadeduplication.database import Database
from datadeduplication.enums import TaskType, TaskStatus
from datadeduplication.models import Arquivo, Tarefa

logger = logging.getLogger(__name__)

# Checkpoint file location
CHECKPOINT_FILE = ".scan_checkpoint.json"


class Scanner:
    """Scans directories and collects file metadata."""

    def __init__(self, config: Config, db: Database):
        self.config = config
        self.db = db
        self._batch: List[Dict] = []
        self._total_files = 0
        self._total_bytes = 0
        self._interrupted = False
        self._checkpoint_path = Path(config.raiz_analise) / CHECKPOINT_FILE
        self._setup_signal_handlers()

    def _setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown."""
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame) -> None:
        """Handle interrupt signals gracefully."""
        sig_name = signal.Signals(signum).name
        logger.warning(f"Received signal {sig_name}, finishing current batch...")
        self._interrupted = True

    def _save_checkpoint(self, last_file: str) -> None:
        """Save checkpoint to file for crash recovery."""
        try:
            checkpoint_data = {
                "last_file": last_file,
                "total_files": self._total_files,
                "total_bytes": self._total_bytes,
                "timestamp": datetime.now().isoformat(),
                "raiz_analise": str(self.config.raiz_analise),
            }
            # Write to temp file first, then rename (atomic on most systems)
            temp_path = self._checkpoint_path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(checkpoint_data, f, indent=2)
            temp_path.replace(self._checkpoint_path)
            logger.debug(f"Checkpoint saved: {last_file}")
        except Exception as e:
            logger.warning(f"Failed to save checkpoint: {e}")

    def _load_checkpoint(self) -> Optional[Dict]:
        """Load checkpoint from file if exists."""
        try:
            if self._checkpoint_path.exists():
                with open(self._checkpoint_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                logger.info(f"Checkpoint found: last file was {data.get('last_file')}")
                return data
        except Exception as e:
            logger.warning(f"Failed to load checkpoint: {e}")
        return None

    def _clear_checkpoint(self) -> None:
        """Remove checkpoint file after successful scan."""
        try:
            if self._checkpoint_path.exists():
                self._checkpoint_path.unlink()
                logger.debug("Checkpoint file removed")
        except Exception as e:
            logger.warning(f"Failed to remove checkpoint: {e}")

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
        """Insert batch of files and create tasks using bulk operations."""
        if not self._batch:
            return

        # Bulk insert files
        arquivos = [Arquivo(**metadata) for metadata in self._batch]
        session.add_all(arquivos)
        session.flush()

        # Create tasks for all files
        tarefas = []
        for arquivo in arquivos:
            tarefas.append(Tarefa(
                arquivo_id=arquivo.id,
                tipo=TaskType.HASH.value,
                status=TaskStatus.PENDING.value,
            ))
            tarefas.append(Tarefa(
                arquivo_id=arquivo.id,
                tipo=TaskType.ANALYZE.value,
                status=TaskStatus.PENDING.value,
            ))

        session.add_all(tarefas)
        session.commit()
        logger.info(f"Flushed batch of {len(self._batch)} files")
        self._batch.clear()

    def scan(self, resume: bool = False) -> Dict:
        """Scan directory recursively and collect file metadata.

        Args:
            resume: If True, skip files already in database and use checkpoint.

        Returns:
            Dict with scan statistics.
        """
        logger.info(f"Starting scan of {self.config.raiz_analise}")
        start_time = datetime.now()

        # Load checkpoint for resume mode
        checkpoint = None
        checkpoint_file = None
        if resume:
            checkpoint = self._load_checkpoint()
            if checkpoint:
                checkpoint_file = checkpoint.get("last_file")
                self._total_files = checkpoint.get("total_files", 0)
                self._total_bytes = checkpoint.get("total_bytes", 0)
                logger.info(f"Resuming from checkpoint: {checkpoint_file} ({self._total_files} files processed)")

        try:
            root = Path(self.config.raiz_analise)
            if not root.exists():
                raise FileNotFoundError(f"Directory not found: {root}")

            skip_until_checkpoint = checkpoint_file is not None
            files_since_checkpoint = 0

            for filepath in root.rglob("*"):
                # Check for interruption
                if self._interrupted:
                    logger.warning("Scan interrupted by user, saving partial progress...")
                    break

                if filepath.is_dir():
                    continue

                filepath_str = str(filepath)

                # Skip until we reach the checkpoint file
                if skip_until_checkpoint:
                    if filepath_str == checkpoint_file:
                        skip_until_checkpoint = False
                        logger.info(f"Reached checkpoint file, continuing scan...")
                    continue

                # Check if file already exists in database (for resume after crash)
                if resume:
                    with self.db.session() as session:
                        exists = session.query(Arquivo).filter(Arquivo.caminho == filepath_str).first()
                    if exists:
                        continue

                metadata = self._process_file(filepath)
                if metadata is None:
                    continue

                self._batch.append(metadata)
                self._total_files += 1
                self._total_bytes += metadata["tamanho"]
                files_since_checkpoint += 1

                if self._total_files % 1000 == 0:
                    logger.info(f"Progress: {self._total_files} files scanned, {self._total_bytes / (1024*1024):.2f} MB")

                if len(self._batch) >= self.config.batch_size:
                    with self.db.session() as session:
                        self._flush_batch(session)
                    # Save checkpoint after successful batch commit
                    self._save_checkpoint(filepath_str)
                    files_since_checkpoint = 0

            # Flush remaining files
            if self._batch:
                with self.db.session() as session:
                    self._flush_batch(session)
                # Save checkpoint for remaining files
                if self._batch:
                    self._save_checkpoint(str(self._batch[-1]["caminho"]))

            # Clear checkpoint on successful completion
            if not self._interrupted:
                self._clear_checkpoint()

        except Exception as e:
            logger.error(f"Scan failed: {e}")
            # Save partial batch on error
            if self._batch:
                logger.info(f"Saving {len(self._batch)} files from partial batch...")
                try:
                    with self.db.session() as session:
                        self._flush_batch(session)
                except Exception as flush_error:
                    logger.error(f"Failed to save partial batch: {flush_error}")
            raise

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        stats = {
            "total_files": self._total_files,
            "total_bytes": self._total_bytes,
            "duration_seconds": duration,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "interrupted": self._interrupted,
        }

        if self._interrupted:
            logger.warning(f"Scan interrupted: {self._total_files} files processed before interruption")
        else:
            logger.info(f"Scan completed: {self._total_files} files, {self._total_bytes} bytes in {duration:.2f}s")
        return stats
