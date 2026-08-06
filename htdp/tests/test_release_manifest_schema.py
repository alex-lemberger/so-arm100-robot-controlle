import json
from pathlib import Path

from htdp.schemas.models import DatasetRelease


def test_model_has_per_session_field():
    assert "absent_modalities_by_session" in DatasetRelease.model_fields


def test_exported_schema_includes_field():
    schema = json.loads(Path("docs/schemas/DatasetRelease.schema.json").read_text(encoding="utf-8"))
    assert "absent_modalities_by_session" in schema["properties"]
