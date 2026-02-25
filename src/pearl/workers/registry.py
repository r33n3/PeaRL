"""Worker registry mapping job types to worker classes."""

from pearl.workers.base import BaseWorker


def _build_registry() -> dict[str, type[BaseWorker]]:
    from pearl.workers.compile_worker import CompileContextWorker
    from pearl.workers.normalize_worker import NormalizeFindingsWorker
    from pearl.workers.remediation_worker import GenerateRemediationWorker
    from pearl.workers.report_worker import GenerateReportWorker
    from pearl.workers.scan_worker import ScanWorker

    return {
        "compile_context": CompileContextWorker,
        "scan_source": ScanWorker,
        "normalize_findings": NormalizeFindingsWorker,
        "generate_remediation_spec": GenerateRemediationWorker,
        "report": GenerateReportWorker,
    }


_registry: dict[str, type[BaseWorker]] = {}


def _ensure_registry() -> None:
    if not _registry:
        _registry.update(_build_registry())


def register_worker(job_type: str, worker_class: type[BaseWorker]) -> None:
    """Register a worker class for a job type."""
    _registry[job_type] = worker_class


def get_worker(job_type: str) -> BaseWorker | None:
    """Get a worker instance for a job type."""
    _ensure_registry()
    cls = _registry.get(job_type)
    return cls() if cls else None
