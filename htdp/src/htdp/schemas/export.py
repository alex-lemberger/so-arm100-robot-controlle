import json
from pathlib import Path

from pydantic import BaseModel

from htdp.schemas import models

_EXPORTED: list[type[BaseModel]] = [
    models.Consent,
    models.DeviceConfig,
    models.EventMarker,
    models.Session,
    models.Manifest,
    models.DatasetRelease,
    models.Participant,
    models.TaskProtocol,
]


def export_json_schemas(out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for model in _EXPORTED:
        path = out_dir / f"{model.__name__}.schema.json"
        path.write_text(
            json.dumps(model.model_json_schema(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        written.append(path)
    return written
