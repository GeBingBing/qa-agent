# Agently DevTools Companion

Use this reference when the request is about attaching official development and debugging tooling to an Agently app without changing the app's owner layer.

## Ownership

Conceptually this is observability work. It belongs to `agently-runtime` in Skills because the app is staying on its current request or workflow design, and the main change is attaching native observation, evaluation, or playground tooling around it.

Route here when the user wants:

- local observation for requests, tools, actions, or TriggerFlow executions
- a local console, logs view, developer guide, or playground for an existing Agently app
- scenario evaluation runs that compare prompt, settings, or flow variants
- a local observation API app through `create_local_observation_app(...)`

If the user also needs to redesign the workflow stages, branch semantics, runtime stream contract, or chunk boundaries, continue with `agently-triggerflow` after this skill.

## Public Package Boundary

- install from PyPI: `pip install -U agently agently-devtools`
- start with the public CLI: `agently-devtools start`
- use only public package entrypoints such as `ObservationBridge`, `EvaluationBridge`, `EvaluationRunner`, and `create_local_observation_app`
- do not require the DevTools source repository, editable install steps, or internal repo paths in user-facing guidance

`agently-devtools` is optional. The Agently app should still run when DevTools is absent.

## Minimal Observation Path

```python
import os

from agently import Agently
from agently_devtools import ObservationBridge

bridge = ObservationBridge(
    Agently,
    endpoint=os.environ["AGENTLY_DEVTOOLS_INGEST_URL"],
    app_id="your_app_id",
    group_id="your_group_id",
)
bridge.watch(Agently)
```

Recommended environment split:

- `AGENTLY_DEVTOOLS_BASE_URL` for local console and evaluation APIs
- `AGENTLY_DEVTOOLS_INGEST_URL` for observation event upload

Keep this wiring in the app or observability layer, not inside prompt helpers or chunk handlers.
`ObservationBridge` uploads through a background queue and coalesces high-frequency events such as `model.streaming`; call `await bridge.flush()` before a short-lived script exits when full delivery matters.

Agently also provides a LazyImport facade when the app wants to keep the
`agently-devtools` import behind Agently:

```python
from agently import Agently

bridge = Agently.create_observation_bridge(
    endpoint=os.environ["AGENTLY_DEVTOOLS_INGEST_URL"],
    app_id="your_app_id",
)
bridge.watch(Agently)
```

For selective observation, pass or watch the target object:

```python
bridge = ObservationBridge(Agently, app_id="your_app_id")
bridge.watch(agent, flow, lookup_reference)
```

The older `bridge = ObservationBridge(...); bridge.register(Agently)` form is a
compatibility path and should be treated as deprecated.

## Local Embedded Listener

Use `create_local_observation_app(...)` when the user needs a local observation API app exposed through FastAPI instead of a separate CLI process.

Prefer the CLI path first for general local use:

```bash
agently-devtools start
```

Use the embedded app path when the host process already owns the local server boundary.

## Project Scaffolding

Use `agently-devtools init <project>` when the user wants a new Agently project scaffold before wiring observation or evaluation tooling.

```bash
agently-devtools init my_project
```

## Scenario Evaluations

Use `EvaluationBridge` and `EvaluationRunner` when the user wants repeated scenario runs with DevTools-backed reports.

The public variant helpers align with Agently capability boundaries:

- prompt-side changes: `EvaluationVariant.from_yaml_prompt(...)` or `.from_json_prompt(...)`
- settings-side changes: `EvaluationVariant.from_settings(...)`
- workflow-side changes: `EvaluationVariant.from_json_flow(...)` or `.from_yaml_flow(...)`

This keeps evaluation setup aligned with the same skill boundaries used during implementation.

## Native-First Rules

- attach DevTools through `Agently.event_center` instead of writing a custom upload bridge first
- keep DevTools optional and local-first; it should support development and debugging without becoming a runtime hard dependency
- let TriggerFlow and requests emit native observation events rather than inventing a second debug event schema
- prefer official console modules such as Runtime Observation, Evaluations, Playground, and Logs before building ad hoc dashboards

## Anti-Patterns

- do not tell users to depend on unpublished or internal DevTools source layout
- do not couple production request logic to DevTools-only classes
- do not rewrite workflow logic just to make it observable when native observation events already exist
