import json
from pathlib import Path
from pydantic import BaseModel


def dump_json(obj: dict[str, object] | BaseModel, path: Path) -> None:
    data = obj.model_dump(mode="json") if isinstance(obj, BaseModel) else obj
    text = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False)
    path.write_text(text + "\n", encoding="utf-8", newline="\n")


def _fmt(value: object) -> str:
    if isinstance(value, float):
        return f"{value:.6f}"
    return str(value)


def write_csv(rows: list[dict[str, object]], columns: list[str], path: Path) -> None:
    lines = [",".join(columns)]
    lines.extend(",".join(_fmt(row[c]) for c in columns) for row in rows)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
