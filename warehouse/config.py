import json
from pathlib import Path
from dataclasses import dataclass, asdict

@dataclass
class WarehouseConfig:
    fast_path_enabled: bool = True
    pypdf_threshold: int = 50
    export_dir: str = "warehouse/exports"

    def to_dict(self) -> dict:
        return asdict(self)

class ConfigManager:
    def __init__(self, config_path: str = "warehouse/data/config.json"):
        self.path = Path(config_path)
        self.config = WarehouseConfig()
        self.load()

    def load(self):
        if self.path.exists():
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.config = WarehouseConfig(**data)
            except Exception:
                pass
        else:
            self.save()

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.config.to_dict(), f, indent=2)

    def update(self, new_data: dict):
        current_dict = self.config.to_dict()
        for k, v in new_data.items():
            if k in current_dict:
                setattr(self.config, k, v)
        self.save()
