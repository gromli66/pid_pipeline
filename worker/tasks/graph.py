"""
Graph Tasks - построение графа и FXML (Phase 5).
"""

from worker.celery_app import celery_app


@celery_app.task(
    bind=True,
    name="worker.tasks.graph.task_build_graph",
    max_retries=2,
    time_limit=1800,
)
def task_build_graph(self, diagram_uid: str):
    """Построение графа."""
    # TODO: Phase 5
    print(f"⏳ Graph building not implemented yet for {diagram_uid}")
    return {"status": "not_implemented", "diagram_uid": diagram_uid}


@celery_app.task(
    bind=True,
    name="worker.tasks.graph.task_generate_fxml",
    max_retries=1,
    time_limit=300,
)
def task_generate_fxml(self, diagram_uid: str):
    """Генерация FXML."""
    # TODO: Phase 5
    print(f"⏳ FXML generation not implemented yet for {diagram_uid}")
    return {"status": "not_implemented", "diagram_uid": diagram_uid}