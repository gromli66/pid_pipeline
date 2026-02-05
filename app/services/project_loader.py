"""
Project Loader - загрузка конфигурации проектов из YAML файлов.
"""

import yaml
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass
from functools import lru_cache

from app.config import settings


@dataclass
class ClassInfo:
    """Информация о классе."""
    id: int
    name: str


@dataclass
class YoloConfig:
    """Конфигурация YOLO модели."""
    weights: str
    num_classes: int
    confidence: float
    class_mapping: Dict[int, int]  # YOLO class_id → CVAT category_id


@dataclass
class ProjectConfig:
    """Полная конфигурация проекта из YAML."""
    code: str
    name: str
    cvat_project_name: str
    classes: List[ClassInfo]
    yolo: YoloConfig
    config_path: str
    
    @property
    def num_classes(self) -> int:
        return len(self.classes)
    
    def get_cvat_category_id(self, yolo_class_id: int) -> int:
        """YOLO class_id → CVAT category_id."""
        return self.yolo.class_mapping.get(yolo_class_id, yolo_class_id + 1)
    
    def get_class_name(self, cvat_category_id: int) -> Optional[str]:
        """CVAT category_id → class name."""
        for cls in self.classes:
            if cls.id == cvat_category_id:
                return cls.name
        return None


class ProjectLoader:
    """Загрузчик конфигураций проектов из YAML."""
    
    def __init__(self, configs_dir: Optional[Path] = None):
        self.configs_dir = configs_dir or Path(settings.PROJECTS_CONFIG_DIR)
        self._cache: Dict[str, ProjectConfig] = {}
    
    def _parse_yaml(self, yaml_path: Path) -> ProjectConfig:
        """Парсинг YAML в ProjectConfig."""
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        
        project = data.get("project", {})
        cvat = data.get("cvat", {})
        yolo_data = data.get("yolo", {})
        classes_data = data.get("classes", [])
        
        classes = [ClassInfo(id=c["id"], name=c["name"]) for c in classes_data]
        
        yolo = YoloConfig(
            weights=yolo_data.get("weights", ""),
            num_classes=yolo_data.get("num_classes", 36),
            confidence=yolo_data.get("confidence", 0.8),
            class_mapping=yolo_data.get("class_mapping", {}),
        )
        
        return ProjectConfig(
            code=project.get("code", yaml_path.stem),
            name=project.get("name", yaml_path.stem),
            cvat_project_name=cvat.get("project_name", f"P&ID {project.get('name', '')}"),
            classes=classes,
            yolo=yolo,
            config_path=str(yaml_path),
        )
    
    def load(self, project_code: str) -> Optional[ProjectConfig]:
        """Загрузить конфигурацию проекта по коду."""
        if project_code in self._cache:
            return self._cache[project_code]
        
        for ext in [".yaml", ".yml"]:
            yaml_path = self.configs_dir / f"{project_code}{ext}"
            if yaml_path.exists():
                config = self._parse_yaml(yaml_path)
                self._cache[project_code] = config
                return config
        
        return None
    
    def load_all(self) -> List[ProjectConfig]:
        """Загрузить все конфигурации."""
        configs = []
        if not self.configs_dir.exists():
            return configs
        
        for yaml_path in self.configs_dir.glob("*.yaml"):
            try:
                config = self._parse_yaml(yaml_path)
                self._cache[config.code] = config
                configs.append(config)
            except Exception as e:
                print(f"⚠️ Ошибка загрузки {yaml_path}: {e}")
        
        for yaml_path in self.configs_dir.glob("*.yml"):
            if yaml_path.stem not in self._cache:
                try:
                    config = self._parse_yaml(yaml_path)
                    self._cache[config.code] = config
                    configs.append(config)
                except Exception as e:
                    print(f"⚠️ Ошибка загрузки {yaml_path}: {e}")
        
        return configs
    
    def list_codes(self) -> List[str]:
        """Список кодов доступных проектов."""
        codes = set()
        if self.configs_dir.exists():
            for p in self.configs_dir.glob("*.yaml"):
                codes.add(p.stem)
            for p in self.configs_dir.glob("*.yml"):
                codes.add(p.stem)
        return sorted(codes)


@lru_cache()
def get_project_loader() -> ProjectLoader:
    """Глобальный экземпляр ProjectLoader."""
    return ProjectLoader()
