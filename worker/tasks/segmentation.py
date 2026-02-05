"""
Segmentation Tasks - U2-Net++ (Phase 3).
"""

from worker.celery_app import celery_app


@celery_app.task(
    bind=True,
    name="worker.tasks.segmentation.task_segment_pipes",
    max_retries=2,
    time_limit=3600,
)
def task_segment_pipes(self, diagram_uid: str):
    """U2-Net++ сегментация труб."""
    # TODO: Phase 3
    print(f"⏳ Segmentation not implemented yet for {diagram_uid}")
    return {"status": "not_implemented", "diagram_uid": diagram_uid}