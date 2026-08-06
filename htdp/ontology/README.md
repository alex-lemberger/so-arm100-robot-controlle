# HTDP Task Ontology

Annotation vocabulary for demonstrations — tasks, phases, actions, objects, effectors, event markers, failure modes — aligned across real capture (reach-grasp-place protocol) and simulation (M2.5 pick_place).

## Files

| File | Role |
|---|---|
| `htdp-tasks.yaml` | The ontology (classes, typed relations, edges) |
| `competency-questions.yaml` | What the ontology must answer — its test suite |

## Binding decision (2026-07-06)

**All demonstration annotations use ontology class ids.** Concretely:

1. **Phase/action labels** in any segmentation or annotation artifact (including R1b teleop demos) come from `htdp-tasks.yaml` class ids (`reach_phase`, `grasp`, ...) — never free text.
2. **Event markers**: `docs/schemas/EventMarker.schema.json` label enum and the ontology `marker_*` classes are held in bijection by `tests/test_ontology.py`. Change them together or CI goes red.
3. **LeRobot metadata**: episode task names use ontology task ids (`pick_place`, `reach_grasp_place`); sim/real correspondence is the `variant_of` edge, not naming convention.
4. **New labels** follow the ontology-building skill workflow: competency question first, then class, then `validate.py` green. No drive-by vocabulary.

## Guards

- `tests/test_ontology.py` (runs in the default suite): structural validity, all competency questions answerable, marker/schema bijection.
- Dev-time tooling (richer validation, exports, stats, instance checking, diff) lives in the personal `ontology-building` skill; the repo test is deliberately self-contained.
