"""
Junction Tasks - классификация перекрёстков (Phase 4).
"""

from worker.celery_app import celery_app


@celery_app.task(
    bind=True,
    name="worker.tasks.junction.task_classify_junctions",
    max_retries=2,
    time_limit=1800,
)
def task_classify_junctions(self, diagram_uid: str):
    """Junction CNN классификация."""
    # TODO: Phase 4
    print(f"⏳ Junction classification not implemented yet for {diagram_uid}")
    return {"status": "not_implemented", "diagram_uid": diagram_uid}