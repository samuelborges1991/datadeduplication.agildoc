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
