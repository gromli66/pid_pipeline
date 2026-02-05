"""
Detection Tasks - YOLO детекция.
"""

import os
import sys
import tempfile
import traceback
from pathlib import Path

from worker.celery_app import celery_app


def detections_to_yolo_txt(detections: list) -> str:
    """
    Конвертация детекций в YOLO формат (для сохранения в файл).
    
    Args:
        detections: Список детекций от NodeDetector.detect()
        
    Returns:
        Строка в YOLO формате (class x_center y_center width height confidence)
    """
    lines = []
    for det in detections:
        line = "{} {:.6f} {:.6f} {:.6f} {:.6f} {:.4f}".format(
            det["class_id"],
            det["x_center"],
            det["y_center"],
            det["width"],
            det["height"],
            det.get("confidence", 1.0),
        )
        lines.append(line)
    return "\n".join(lines)


@celery_app.task(
    bind=True,
    name="worker.tasks.detection.task_detect_yolo",
    max_retries=2,
    default_retry_delay=60,
    time_limit=1800,
    acks_late=True,
)
def task_detect_yolo(self, diagram_uid: str, project_code: str = "thermohydraulics"):
    """
    YOLO детекция с SAHI.
    
    Этапы:
    1. Загрузить изображение из storage
    2. NodeDetector.detect()
    3. Сохранить yolo_predicted.txt
    4. Создать CVAT task + job
    5. Импортировать аннотации в CVAT
    6. Обновить статус → detected
    
    Args:
        diagram_uid: UUID диаграммы
        project_code: Код проекта для загрузки конфигурации (default: thermohydraulics)
    """
    # Добавляем пути для импорта
    sys.path.insert(0, "/app")
    sys.path.insert(0, "/app/modules")
    
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    
    # Подключение к БД
    DATABASE_URL = os.getenv("DATABASE_URL")
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine)
    
    db = SessionLocal()
    
    try:
        print(f"🔍 Starting YOLO detection for {diagram_uid}")
        
        # Импорты внутри task (избегаем circular imports)
        from app.models import Diagram, DiagramStatus, Artifact, ArtifactType
        from app.services.project_loader import get_project_loader
        from app.services.cvat_client import CVATClient, CVATLabel
        from app.services.cvat_export import (
            CVATExporter, 
            Detection,
            detections_to_cvat_detections,
            create_exporter_from_config,
        )
        from modules.yolo_detector import NodeDetector
        
        # ===== 1. Загрузка конфигурации проекта =====
        project_loader = get_project_loader()
        project_config = project_loader.load(project_code)
        if not project_config:
            raise ValueError(f"Project config '{project_code}' not found")
        
        print(f"📋 Project: {project_config.name}")
        
        # ===== 2. Получаем диаграмму из БД =====
        diagram = db.query(Diagram).filter(Diagram.uid == diagram_uid).first()
        if not diagram:
            raise ValueError(f"Diagram {diagram_uid} not found")
        
        # ===== 3. Получаем путь к изображению =====
        storage_path = Path(os.getenv("STORAGE_PATH", "./storage/diagrams"))
        image_path = storage_path / str(diagram_uid) / "original" / "image.png"
        
        # Проверяем существование файла
        if not image_path.exists():
            for ext in [".jpg", ".jpeg", ".tiff", ".tif"]:
                alt_path = image_path.with_suffix(ext)
                if alt_path.exists():
                    image_path = alt_path
                    break
            else:
                raise FileNotFoundError(f"Image not found: {image_path}")
        
        print(f"📁 Image path: {image_path}")
        
        # ===== 4. YOLO детекция =====
        weights_path = Path(project_config.yolo.weights)
        if not weights_path.is_absolute():
            # Относительный путь - относительно /app
            weights_path = Path("/app") / weights_path
        
        detector = NodeDetector(
            weights=weights_path,
            confidence=project_config.yolo.confidence,
            device=os.getenv("YOLO_DEVICE", "cuda"),
            use_sahi=True,
            apply_preprocessing=False,
        )
        
        detections = detector.detect(
            image=image_path,
            return_absolute=False,
            apply_reverse_mapping=True,  # 34→35, 35→38
        )
        
        detection_count = len(detections)
        print(f"✅ Detected {detection_count} objects")
        
        # ===== 5. Сохраняем YOLO predictions =====
        detection_dir = storage_path / str(diagram_uid) / "detection"
        detection_dir.mkdir(parents=True, exist_ok=True)
        
        yolo_path = detection_dir / "yolo_predicted.txt"
        yolo_txt = detections_to_yolo_txt(detections)
        yolo_path.write_text(yolo_txt)
        
        print(f"💾 Saved predictions to {yolo_path}")
        
        # Создаём артефакт YOLO_PREDICTED
        artifact_yolo = Artifact(
            diagram_uid=diagram_uid,
            artifact_type=ArtifactType.YOLO_PREDICTED,
            file_path=str(yolo_path.relative_to(storage_path)),
            file_size=yolo_path.stat().st_size,
        )
        db.add(artifact_yolo)
        
        # ===== 6. Создаём CVAT task =====
        cvat_task_id = None
        cvat_job_id = None
        
        try:
            cvat_client = CVATClient()
            
            # Авторизация (если нет токена в settings)
            cvat_username = os.getenv("CVAT_USERNAME")
            cvat_password = os.getenv("CVAT_PASSWORD")
            if cvat_username and cvat_password:
                cvat_client.login(cvat_username, cvat_password)
            
            # Создаём labels из конфига проекта
            labels = [CVATLabel(name=cls.name) for cls in project_config.classes]
            
            # Получаем или создаём проект
            project_id = cvat_client.get_or_create_project(
                name=project_config.cvat_project_name,
                labels=labels,
            )
            print(f"📂 CVAT project ID: {project_id}")
            
            # Создаём task
            task_name = f"{diagram.name or diagram_uid}"
            cvat_task_id, cvat_job_id = cvat_client.create_task(
                project_id=project_id,
                name=task_name,
                image_path=image_path,
            )
            print(f"📋 CVAT task ID: {cvat_task_id}, job ID: {cvat_job_id}")
            
            # ===== 7. Импортируем аннотации в CVAT =====
            if detections:
                # Конвертируем детекции в формат CVAT
                cvat_detections = detections_to_cvat_detections(detections)
                
                # Создаём exporter с class_mapping из конфига
                exporter = create_exporter_from_config(project_config)
                
                # Создаём временный ZIP для импорта
                with tempfile.TemporaryDirectory() as temp_dir:
                    zip_path = Path(temp_dir) / "annotations.zip"
                    exporter.export_yolo(
                        detections=cvat_detections,
                        image_filename=image_path.name,
                        output_path=zip_path,
                    )
                    
                    # Импортируем в CVAT
                    cvat_client.import_annotations(
                        task_id=cvat_task_id,
                        annotations_path=zip_path,
                        format_name="YOLO 1.1",
                    )
                    print(f"📤 Imported {len(detections)} annotations to CVAT")
            
            # Сохраняем URL для быстрого доступа
            cvat_url = cvat_client.get_task_url(cvat_task_id, cvat_job_id)
            print(f"🔗 CVAT URL: {cvat_url}")
            
        except Exception as cvat_exc:
            # CVAT ошибки не фатальны - детекция выполнена
            print(f"⚠️ CVAT error (non-fatal): {cvat_exc}")
            print(traceback.format_exc())
        
        # ===== 8. Обновляем диаграмму в БД =====
        diagram.status = DiagramStatus.DETECTED
        diagram.detection_count = detection_count
        diagram.cvat_task_id = cvat_task_id
        diagram.cvat_job_id = cvat_job_id
        
        db.commit()
        
        print(f"✅ Detection completed for {diagram_uid}")
        
        return {
            "status": "success",
            "diagram_uid": diagram_uid,
            "detection_count": detection_count,
            "cvat_task_id": cvat_task_id,
            "cvat_job_id": cvat_job_id,
        }
        
    except Exception as exc:
        print(f"❌ Detection failed: {exc}")
        print(traceback.format_exc())
        
        # Обновляем статус на error
        try:
            from app.models import Diagram, DiagramStatus
            diagram = db.query(Diagram).filter(Diagram.uid == diagram_uid).first()
            if diagram:
                diagram.status = DiagramStatus.ERROR
                diagram.error_message = str(exc)[:500]  # Ограничиваем длину
                diagram.error_stage = "detecting"
                db.commit()
        except Exception as db_exc:
            print(f"❌ Failed to update error status: {db_exc}")
        
        # Retry или fail
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        raise
        
    finally:
        db.close()
