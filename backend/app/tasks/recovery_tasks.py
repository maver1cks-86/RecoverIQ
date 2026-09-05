from __future__ import annotations

from celery import Task

from app.celery_app import celery_app
from app.tasks.batch_tasks import execute_recovery_assignment_task


@celery_app.task(
    bind=True,
    name="app.tasks.recovery_tasks.run_recovery_workflow_task",
    max_retries=3,
)
def run_recovery_workflow_task(
    self: Task,
    assignment_id: int,
) -> dict:
    """Backward-compatible task name that executes a persisted assignment."""
    try:
        return dict(execute_recovery_assignment_task.run(assignment_id))
    except (LookupError, ValueError):
        raise
    except Exception as exc:
        countdown = 2 ** min(self.request.retries, 3)
        raise self.retry(
            exc=exc,
            countdown=countdown,
            max_retries=3,
        )
