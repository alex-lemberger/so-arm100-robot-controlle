"""Ontology contract tests — make ontology/ load-bearing.

Self-contained structural checks (no dependency on the dev-time ontology-building
skill tooling): the ontology must stay internally valid, every competency question
must remain answerable, and the event-marker classes must stay in bijection with
the EventMarker.schema.json label enum (single source of truth guard).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parents[1]
ONTOLOGY = ROOT / "ontology" / "htdp-tasks.yaml"
CQS = ROOT / "ontology" / "competency-questions.yaml"
MARKER_SCHEMA = ROOT / "docs" / "schemas" / "EventMarker.schema.json"


@pytest.fixture(scope="module")
def onto():
    data = yaml.safe_load(ONTOLOGY.read_text())
    for c in data["classes"]:
        p = c.get("is_a")
        c["is_a"] = [p] if isinstance(p, str) else (p or [])
    return data


@pytest.fixture(scope="module")
def cidx(onto):
    return {c["id"]: c for c in onto["classes"]}


@pytest.fixture(scope="module")
def ridx(onto):
    return {r["id"]: r for r in onto["relations"]}


def ancestors(cid, cidx, seen=None):
    seen = seen or set()
    out = set()
    for p in cidx.get(cid, {}).get("is_a", []):
        if p not in seen:
            seen.add(p)
            out.add(p)
            out |= ancestors(p, cidx, seen)
    return out


def test_ids_unique(onto):
    class_ids = [c["id"] for c in onto["classes"]]
    rel_ids = [r["id"] for r in onto["relations"]]
    assert len(class_ids) == len(set(class_ids)), "duplicate class ids"
    assert len(rel_ids) == len(set(rel_ids)), "duplicate relation ids"
    assert not set(class_ids) & set(rel_ids), "class/relation id collision"


def test_definitions_real(onto):
    for c in onto["classes"]:
        d = str(c.get("definition") or "").strip()
        assert d, f"missing definition: {c['id']}"
        assert d.lower() != str(c.get("label", "")).strip().lower(), (
            f"definition merely restates label: {c['id']}"
        )


def test_is_a_targets_exist_and_acyclic(onto, cidx):
    for c in onto["classes"]:
        for p in c["is_a"]:
            assert p in cidx, f"dangling is_a: {c['id']} -> {p}"
    for c in onto["classes"]:
        assert c["id"] not in ancestors(c["id"], cidx), f"is_a cycle through {c['id']}"


def test_edges_well_typed(onto, cidx, ridx):
    for e in onto["edges"]:
        assert isinstance(e, list) and len(e) == 3, f"malformed edge: {e!r}"
        s, rel, o = e
        assert s in cidx, f"edge subject unknown: {s}"
        assert o in cidx, f"edge object unknown: {o}"
        assert rel in ridx, f"edge relation undeclared: {rel}"
        dom, rng = ridx[rel]["domain"], ridx[rel]["range"]
        assert dom == s or dom in ancestors(s, cidx), (
            f"domain violation: [{s}, {rel}, {o}] (need {dom})"
        )
        assert rng == o or rng in ancestors(o, cidx), (
            f"range violation: [{s}, {rel}, {o}] (need {rng})"
        )


def test_competency_questions_answerable(onto, cidx, ridx):
    cq = yaml.safe_load(CQS.read_text())
    used_relations = {e[1] for e in onto["edges"] if isinstance(e, list) and len(e) == 3}
    for q in cq["questions"]:
        needs = q.get("needs") or {}
        for c in needs.get("classes") or []:
            assert c in cidx, f"{q['id']}: needs missing class {c}"
        for r in needs.get("relations") or []:
            assert r in ridx, f"{q['id']}: needs missing relation {r}"
            if q.get("requires_instances"):
                assert r in used_relations, f"{q['id']}: relation {r} has no edges"


def test_marker_classes_match_schema_enum(onto, cidx):
    """EventMarker.schema.json label enum and ontology marker classes: bijection."""
    schema = json.loads(MARKER_SCHEMA.read_text())
    enum = set(schema["$defs"]["EventLabel"]["enum"])
    marker_ids = {
        c["id"] for c in onto["classes"] if "event_marker" in ancestors(c["id"], cidx)
    }
    assert {f"marker_{label}" for label in enum} == marker_ids, (
        "EventMarker enum and ontology marker classes diverged — "
        "update ontology/htdp-tasks.yaml and the schema together"
    )
