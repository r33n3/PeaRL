"""Worker for compile_context jobs."""

from sqlalchemy.ext.asyncio import AsyncSession

from pearl.services.compiler.context_compiler import compile_context
from pearl.workers.base import BaseWorker


class CompileContextWorker(BaseWorker):
    async def process(self, job_id: str, payload: dict, session: AsyncSession) -> dict:
        project_id = payload.get("project_id", "")
        trace_id = payload.get("trace_id", "")
        apply_exceptions = payload.get("apply_active_exceptions", True)

        package = await compile_context(
            project_id=project_id,
            trace_id=trace_id,
            apply_exceptions=apply_exceptions,
            session=session,
        )

        return {
            "result_refs": [
                {
                    "ref_id": package.package_metadata.package_id,
                    "kind": "artifact",
                    "summary": "Compiled context package",
                }
            ]
        }
