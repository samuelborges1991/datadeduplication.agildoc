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
