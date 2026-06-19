# TaskDAG / Dynamic Task Overview

TaskDAG is the Agently DAG foundation capability. It owns graph data,
planning, validation, handler resolution, execution, dependency results,
semantic outputs, and runtime placeholders. Dynamic Task is the current
compatibility and convenience facade over that DAG substrate. It belongs above
TriggerFlow conceptually:

```text
Agently.create_dynamic_task(...)
        |
        v
DynamicTask facade
        |
        +-- AgentlyTaskDAGPlanner
        +-- TaskDAGValidator
        +-- DynamicTaskResolver
        +-- TaskDAGExecutor
                |
                v
          TriggerFlow execution substrate
```

Layer ownership:

- `TaskDAG` and `TaskDAGNode` are data contracts under `agently.types.data`;
  reviewed DAGs can be loaded with `TaskDAG.from_yaml(...)` or
  `TaskDAG.from_json(...)`.
- `AgentlyTaskDAGPlanner` is a plugin and owns planner output schema,
  `ensure_keys`, model instructions, and retry validation wiring.
- `TaskDAGValidator`, `TaskDAGResolver`, and `TaskDAGExecutor` are core
  runtime owners.
- `Agently.create_dynamic_task(...)` and `agent.create_dynamic_task(...)` are
  the app-facing facade entrypoints.
- In Agent mode, chained quick prompt methods create an AgentExecution-local
  ModelRequest draft. `agent.create_dynamic_task()` consumes that execution prompt snapshot:
  rendered prompt text becomes the DynamicTask target, the `output` slot becomes
  `output_schema`, `output_format` becomes the default model-task format, and
  the `input` slot remains structured graph input for `${INIT...}`
  placeholders. `set_agent_prompt(...)` / `always=True` values are inherited and
  preserved; multi-statement setup should capture
  `execution = agent.create_execution()` instead of mutating the shared Agent
  pending prompt. Explicit facade arguments override prompt-derived defaults.

Use TaskDAG modules when the graph is submitted as data and must be planned,
validated, pruned, customized, resolved to handlers, and executed. Use the
Dynamic Task facade when ordinary app code wants one compact compatibility
entrypoint. Use TriggerFlow directly when the developer owns a stable workflow
topology in code.

When a DAG is selected inside one long Agent-owned business task, keep the
outer handle as `agent.create_task(...)` or `agent.create_task_loop(...)`. Both
return task-strategy AgentExecution drafts; read final data, text, stream,
metadata, and task refs through AgentExecutionResult or the execution stream/meta
facade instead of introducing a separate public AgentTask handle.

The executor does not require an Agent instance. Agent or model-provider access
belongs to the facade, planner, model adapter, or resolver handler. That keeps
the core executor reusable for submitted local DAGs, model DAGs, action DAGs,
and Skills Executor context-pack integration.

When a submitted DAG needs Skill guidance, use the Skills Executor resolver
adapter instead of inventing a scheduler. Register
`Agently.skills_executor.task_dag_resolver()` with `TaskDAGExecutor` and model
that step as `kind: "skill"` with `inputs.skill_ids`, `inputs.task`,
`inputs.intent`, and optional include flags. The node result is an
`agently.skills.context_pack.v1` payload for downstream planner or model steps;
script Actionization and public lookup stay policy-gated by the host.

For model tasks, keep result control on the model task contract. Use
`inputs.output_schema` for the task result shape and `inputs.output_format` for
the response-control strategy: omit `inputs.output_format` to let the request
read `prompt.default_output_format` (global default `json`); use `json` for compact machine-control data,
standalone booleans/numbers, judges, dense all-typed arrays/objects, and strict extraction;
`xml_field` for flat string long text/code/HTML/Markdown fields; explicit
`hybrid` for long prose/code fields mixed with typed list/object/boolean/number
fields when retry latency is acceptable; explicit `flat_markdown` only for
legacy section-header compatibility; explicit `yaml_literal` only when
a YAML target document is intentionally desired; and `auto` only when structural
schema-driven selection and retry latency are acceptable after the target model
has passed representative stability checks.
If the host facade supplies `create_dynamic_task(..., output_schema=...,
ensure_keys=...)`, that semantic-output contract owns the frontstage shape. A
planner-chosen `inputs.output_format="flat_markdown"` must not break a
multi-field structured host contract; the framework coerces it back to `auto`.

Submitted DAG `inputs` support runtime placeholders for simple wiring:
`${INIT}` / `${INIT.foo}` read initial graph input,
`${DEPS.task_id.path}` reads dependency results, `${STATE...}` reads
execution-local state, and `${TRIGGER...}` reads the raw TriggerFlow trigger
payload.
Whole-string placeholders preserve the original value type; embedded
placeholders stringify into the surrounding text. Use placeholders for direct
references, and keep larger transformations in handlers or model tasks.
Use the same slot naming style as Prompt references: uppercase slot names in
examples (`INIT`, `DEPS`, `STATE`, `TRIGGER`), with path access after the dot.

When a submitted DAG runs behind `agent.use_dynamic_task(...).create_execution()`,
`${INIT...}` reads graph input from `use_dynamic_task(graph_input=...)` when it
is provided. If omitted, it reads the execution prompt snapshot `input` slot
captured by `create_execution()`, then falls back to `{"target": task_target}`.
Use the explicit `graph_input` argument only when the DAG input should differ
from the Agent prompt input or when the precedence should be visible in code.

When Dynamic Task runs behind `agent.create_execution()`, the Agent execution
stream bridges the underlying TriggerFlow runtime stream. If a DAG chunk fails,
the Agent stream must terminate and surface the original error to the consumer;
do not add external timeout workarounds or swallow failing chunks in examples.
For developer-owned loops, wrap the Agent execution as
`create_execution(lineage=..., limits=...)` so Dynamic Task model planning/tasks
share the AgentExecution model-request budget and stream items carry execution
lineage metadata.

Recommended API boundaries:

- app code: `Agently.create_dynamic_task(...)` or `agent.create_dynamic_task(...)`
- planner control: `AgentlyTaskDAGPlanner`
- graph validation: `TaskDAGValidator`
- handler lookup: `DynamicTaskResolver`
- execution integration: `TaskDAGExecutor`

For Skills Executor work, use Dynamic Task as the DAG substrate rather than
placing Skills execution under TriggerFlow directly. Skills execution may
provide resolver handlers, context-pack adapters, or facade defaults, but the
public concept remains Dynamic Task.
