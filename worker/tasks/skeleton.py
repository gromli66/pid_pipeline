"""
Skeleton Tasks - скелетизация (Phase 3).
"""

from worker.celery_app import celery_app


@celery_app.task(
    bind=True,
    name="worker.tasks.skeleton.task_skeletonize",
    max_retries=2,
    time_limit=1800,
)
def task_skeletonize(self, diagram_uid: str):
    """Полная скелетизация."""
    # TODO: Phase 3
    print(f"⏳ Skeletonization not implemented yet for {diagram_uid}")
    return {"status": "not_implemented", "diagram_uid": diagram_uid}


@celery_app.task(
    bind=True,
    name="worker.tasks.skeleton.task_skeletonize_simple",
    max_retries=1,
    time_limit=600,
)
def task_skeletonize_simple(self, diagram_uid: str):
    """Простая скелетизация валидированной маски."""
    # TODO: Phase 4
    print(f"⏳ Simple skeletonization not implemented yet for {diagram_uid}")
    return {"status": "not_implemented", "diagram_uid": diagram_uid}