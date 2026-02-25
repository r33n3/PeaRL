"""Worker registry mapping job types to worker classes."""

from pearl.workers.base import BaseWorker

_registry: dict[str, type[BaseWorker]] = {}


def register_worker(job_type: str, worker_class: type[BaseWorker]):
    """Register a worker class for a job type."""
    _registry[job_type] = worker_class


def get_worker(job_type: str) -> BaseWorker | None:
    """Get a worker instance for a job type."""
    cls = _registry.get(job_type)
    return cls() if cls else None
