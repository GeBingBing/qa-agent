---
name: agently-runtime
description: "Use when the user wants Agently runtime extension capabilities: Action Runtime, built-in action packages, legacy tool compatibility, MCP access, Execution Environment lifecycle, FastAPIHelper or streaming API exposure, auto-function helpers, KeyWaiter, or optional agently-devtools observation, evaluation, and playground integration."
---

# Agently Runtime

Use this skill when the app needs model-callable capabilities, managed execution
dependencies, service exposure, or development/runtime tooling around an
existing request or workflow design.

If the owner layer is still undecided, start with `agently`. If the
problem is multi-step orchestration, use `agently-triggerflow` first and return
here for Actions, Execution Environment, service, or DevTools details.

## Route Inside This Skill

- Action Runtime, `@agent.action_func`, `agent.use_actions(...)`, built-in Search/Browse, sandbox actions, or legacy tools -> `references/actions-runtime.md`
- Action vs Execution Environment boundaries, `agent.enable_*` helpers, provider lifecycle, managed MCP/sandbox/process/browser/SQLite resources -> `references/actions-execution-environment.md`
- observation, evaluation, playground, local logs, or `agently-devtools` -> `references/devtools.md`

## Native-First Rules

- prefer `@agent.action_func` and `agent.use_actions(...)`; `tool_func`, `use_tool`, `use_tools`, and `agently.builtins.tools` are compatibility surfaces
- use built-in web packages through `from agently.builtins.actions import Search, Browse` and mount with `agent.use_actions(Search(...))` / `agent.use_actions(Browse(...))`
- do not invent `enable_search(...)`; Search configuration belongs to the Search package/executor, not Execution Environment
- default Agents and TriggerFlow executions expose lazy Foundation Workspace
  bindings; use `agent.use_workspace(...)` or
  `flow.create_execution(workspace=...)` when the app needs an explicit root,
  read-only mode, shared instance, direct backend, or registered provider, and
  keep in mind that ordinary model requests do not persist automatically
- create application-owned shared Workspace instances with
  `Workspace(...)` or `Agently.create_workspace(...)` and bind each participant
  with `agent.use_workspace(shared_workspace)` or
  `flow.create_execution(workspace=shared_workspace)` when Agents,
  TriggerFlow executions, or service workers must share task information; do
  not rely on separate default Workspaces to communicate; use
  `flow.create_execution(workspace=False)` only when an execution should have no
  Workspace binding
- move information between separate Workspaces in application or TriggerFlow
  business logic by searching/reading the source Workspace, writing or
  ingesting into the destination Workspace, and linking refs as needed;
  Workspace itself is not a cross-space messaging or replication protocol
- for durable multi-turn task records, write through `agent.workspace` or
  explicitly configure it with `agent.use_workspace(...)`; for model-callable
  local file actions, use `agent.enable_workspace_file_actions(...)`, which
  exposes the current Workspace file working tree and inherits
  `agent.workspace.files_root`
- use `workspace.build_context(...)` for Workspace-backed Recall; advanced
  model-assisted planners, vector retrieval, rerankers, and compressors should
  plug into RecallPlanner/Retriever/ContextBuilder instead of becoming WorkLoop
  or Action shortcuts
- for explicit TriggerFlow loops, store structured observations and decisions
  in Workspace, link decisions to evidence with `workspace.link(...)` or
  `workspace.link_evidence(...)`, keep large payloads behind
  `workspace.ref_envelope(...)`, recover state with
  `workspace.latest_checkpoint(...)`, bind durable execution ports by creating
  the execution with `flow.create_execution(workspace=workspace)` or with
  `runtime_resources={"snapshot_store": workspace, "runtime_event_store": workspace}`,
  and inspect backend wiring
  with `workspace.capabilities()`; when restoring, read the snapshot state
  through `workspace.latest_checkpoint(...)` / `workspace.get_data(...)` and
  pass it back to TriggerFlow `async_load(...)` so pause/resume and DAG
  join semantics stay owned by TriggerFlow; use
  `flow.declare_resource_requirement(..., resolver=..., provider_kind=...,
  config_ref=..., secret_ref=..., fail_policy=...)` for importable resource
  resolver descriptors when workers can reconstruct live clients from shared
  host/plugin modules, relying on TriggerFlow load diagnostics for
  missing resolver, unhealthy resource, policy-forbidden resource, fail-open,
  and fail-closed cases; use `pause_for(..., channel_id=..., provider_id=...,
  wait_mode=..., hot_wait_timeout=..., cold_persistence_policy=...,
  request_payload_schema=..., response_payload_schema=..., audit_metadata=...)`
  to persist ExternalWait provider/channel/schema/audit metadata, and put a
  stable `exchange_id` in `audit_metadata` when Workspace RuntimeEvent records
  should be queryable by exchange; when the host owns an approval router, queue,
  or exchange transport, bind it with runtime resource key
  `execution_exchange_provider`, and implement provider `publish_request(...)`
  to return `exchange_id`, `audit_metadata`, or `provider_metadata` without
  taking over TriggerFlow resume lifecycle; use
  `execution.set_compaction_policy(...)` for long-running
  TriggerFlow executions that externalize large payloads behind Workspace or
  provider artifact refs while keeping only compaction facts and retained
  lineage anchors in the execution snapshot; use
  `workspace.put_snapshot(..., expected_state_version=...)` for CAS guarded
  snapshot writes, `workspace.claim_lease(...)` /
  `workspace.heartbeat_lease(...)` / `workspace.release_lease(...)` for
  provider-owned lease projection, and `workspace.put_artifact_ref(...)` for
  large durable payload refs
- for restart diagnostics in explicit workflows, persist compact RuntimeEvent
  facts through a configured TriggerFlow runtime event store or explicit
  `workspace.append_runtime_event(...)` calls, then query bounded ranges with
  `workspace.query_runtime_events(...)`; Workspace stores durable facts and refs,
  while TriggerFlow still owns pause/resume, replay, DAG readiness, and
  approval/exchange lifecycle semantics; durable RuntimeEvent records now carry
  parent signal, aggregation scope, operator id, interrupt id, resume request
  id, actor id, lease owner id, snapshot refs, and artifact refs
- for webhook, approval, or external callback resume flows, pass a stable
  `resume_request_id` and actor to `execution.async_continue_with(...)`; the
  TriggerFlow resume ledger records accepted, dispatched, and completed or
  dispatch-failed phases; callbacks delivered to expired execution-local leases
  fail fast before acceptance without writing resume ledger entries, while the interrupt carries an ExternalWait
  request envelope for projection and restart diagnostics
- for distributed TriggerFlow recovery, pass
  `require_distributed_provider=True` when persisting snapshots; this must fail
  closed unless the selected providers report CAS, lease, range-read,
  retention, and RuntimeEvent sequence capabilities and expose matching
  snapshot, lease, and artifact-ref methods; use `inspect_load(...)`
  to surface expired lease warnings and active lease owner conflicts before
  dispatch; the local Workspace backend
  satisfies this seam for single-node development/restart recovery, but do not
  describe it as a production cross-worker Redis/Postgres/object-storage
  backend
- third-party Workspace backends can replace the local backend through
  `agent.use_workspace(backend)` or named provider registration with
  `Agently.workspace.register_backend_provider(name, factory)` plus
  `agent.use_workspace(root, provider=name, provider_options={...})` when they
  implement the Workspace backend protocol; current framework tests include a
  protocol-level remote audit provider proof plus Workspace-backed snapshot
  load tests for pause/continue, policy approval waits, and
  `when(..., mode="and")` join progress, but public guidance must not imply
  production Redis, Postgres, or object-storage support until real adapters and
  operational guarantees exist
- for AgentTaskLoop applications, enable only the bounded capabilities the task
  may use, such as `agent.enable_shell(...)`,
  `agent.enable_workspace_file_actions(...)`, `agent.use_actions(...)`,
  `agent.use_skills(...)`, or `agent.use_dynamic_task(...)`, then create the
  task-strategy AgentExecution draft with `agent.create_task(...)` or the more
  explicit `agent.create_task_loop(...)`; both return AgentExecution drafts, not
  public AgentTask handles. Do not expose broad shell, filesystem, MCP, or
  browser access just because the task loop exists
- for AgentTaskLoop business examples, print or persist AgentExecution
  stream/result/meta items: use `meta.stream_kind=="snapshot"` for intermediate
  state captures such as context readiness, plan, execution evidence summary,
  and verification gaps;
  enable `options={"agent_task": {"stream_progress": True}}` only when
  natural-language progress is needed; omit `progress_model_key` for template
  progress with no model requests, or set `progress_model_key` to run a
  separate background model that summarizes only existing snapshots/task
  metadata without adding main-loop fields or latency; progress model failures
  are side-channel diagnostics/warnings, not main task `model.request_failed`
  errors; progress model inputs should be operator-safe and omit low-level
  Workspace/SQLite fallback diagnostics that remain available in task meta
- for AgentTaskLoop terminal results, treat `completed` as accepted output
  (`accepted=True`, `artifact_status="accepted"`); `max_iterations` can still
  leave useful Workspace files, but those are partial artifacts
  (`accepted=False`, `artifact_status="partial"`); when semantic content quality
  matters, combine deterministic smoke checks with an Agently model-judge
  request and do not use counts or keyword hits as the primary acceptance signal
- AgentTaskLoop strategy persistence writes planning, observation, verification,
  checkpoint, and evidence-link records through the bound Workspace provider;
  checkpoints use the checkpoint-store port and task evidence relationships use
  `workspace.link_evidence(...)`
- for AgentTaskLoop business-system examples, mocks may provide facts, source
  records, policies, missing data, or conflicting inputs, but must not provide
  hidden expected answers, pass/fail fields, or deterministic business-quality
  verdicts; judgment belongs to the AgentTask verifier or an independent
  Agently model-judge request
- for app developers, prefer `agent.enable_python(...)`, `agent.enable_shell(...)`, `agent.enable_workspace_file_actions(...)`, `agent.enable_nodejs(...)`, and `agent.enable_sqlite(...)` before direct manager/provider APIs
- for instruction-heavy Actions, expect later model rounds to see compact execution digests and artifact refs; use `agent.action.read_action_artifact(...)` only when full raw code, command output, SQL results, page content, or logs are needed
- `agent.action.get_action_info()` and `get_action_list()` return visible
  metadata with execution environment `env` values redacted; raw env values are
  only for the execution provider path
- after explicit `agent.get_action_result(prompt=..., store_for_reply=True)`,
  the prompt is marked as having consumed the action loop even when no records
  were produced, so later response materialization should not re-enter
  ActionRuntime for that prompt
- `agent.get_action_result(..., timeout=N)` bounds the full ActionFlow
  lifecycle, including planning/model-owned tool selection; catch
  `RuntimeStageStallError(stage="action_loop_close")` instead of relying on a
  host-side kill as the primary timeout signal
- for native tool-call planning, a zero-tool-call result can surface as a
  skipped diagnostic record with code `action_runtime.native_tool_calls.empty`;
  treat it as planning evidence, not executed work
- use `agent.action.summarize_records(records, validation_command_markers=...)`
  when a host needs authoritative action evidence such as failed actions,
  commands attempted/run, and latest validation result
- treat `Agently.execution_environment` as an advanced framework/plugin surface for lifecycle, policy, approval, health, and release
- Action executors should declare or consume managed resources instead of secretly owning long-lived MCP clients, sandboxes, browsers, SQLite connections, or process runners
- keep permission profiles explicit: search-only, local-files-only, network-read, install-capable shell, or trusted executor
- treat `agently-devtools` as optional PyPI-installed tooling; wire observation through public bridge APIs, not source-repo paths
- for framework internals, preserve Agently's core module style: class-owned
  runtime behavior, typed data contracts, protocol/handler seams for
  replacement, and high-level packages outside `agently/core` when they compose
  several core systems
- official Agently RuntimeEvent records are core-owned: built-in plugins should
  return typed observations, errors, decisions, or route stream facts to core
  rather than importing core RuntimeEvent emitters; plugin-owned custom Event
  Center messages must use plugin-owned namespaces and are not guaranteed as
  framework consumption contracts
- keep runtime naming aligned with DevTools: `agent_execution` is the canonical
  run lineage kind for one bounded Agent execution. The old turn-named runtime
  namespace is removed from the current development-line contract.
  `attempt_index` is model-request retry metadata and must not be treated as an
  AgentExecution counter.
- for framework-side Skills Executor work, prefer the `Agently.skills_executor`
  facade backed by the builtin `SkillsExecutor` plugin; Agently 4.1.2.5 did not
  ship `Agently.skills` as a compatibility alias
- for Agently 4.1.3 Skills runtime work, prefer Action-like management:
  declare installed ids or remote source selectors on `agent.use_skills(...)`
  and let Skills Executor lazily discover, install, and mount selected
  capabilities; keep `install_skills_pack(...)` for prewarming, offline mirrors,
  deterministic CI fixtures, and explicit registry maintenance
- use `install_skills(...)` for one local Skill directory during
  authoring/smoke tests; use `agent.run_skills_task(...)` for explicit Skills
  execution; remote selectors may use git URLs, GitHub shorthand such as
  `anthropics/skills`, and `subpath=` when selecting one Skill from a pack
- when a custom planner, Dynamic Task, or TaskDAG node needs full Skill context
  without forcing the complete Skills execution route, use
  `agent.build_skills_context_pack(...)`,
  `agent.async_build_skills_context_pack(...)`, or
  `Agently.skills_executor.build_context_pack(...)`; the returned
  `agently.skills.context_pack.v1` payload can include `SKILL.md` guidance,
  task-relevant references/examples/assets, citations, diagnostics, optional
  public lookup, and policy-gated script Action candidates
- for DAG-shaped consumers of Skill context, pass
  `Agently.skills_executor.task_dag_resolver()` to `TaskDAGExecutor` and use
  `kind="skill"` nodes; do not build a separate scheduler or execute bundled
  scripts while constructing context packs
- for explicit Skills execution, `effort="fast"` maps to the low-overhead
  single-shot path, `effort="normal"` runs the full preflight -> research ->
  plan -> execute -> verify -> reflect -> finalize runtime chain, and
  `effort="max"` increases retry budget for that chain
- when Skills are reached through Agent auto-orchestration, pass route-owned
  effort with `agent.create_execution(options=ExecutionOptions(routes={
  "skills": SkillsRouteOptions(effort="normal")}))` or the equivalent dict;
  this is an execution option, not a prompt slot
- for application-specific Skills action strategies, use
  `Agently.skills_executor.register_effort_strategy(name, handler)` and invoke
  it with `effort=name`; the handler should compose model requests,
  ActionRuntime/MCP, ExecutionEnvironment, TriggerFlow, or Dynamic Task through
  the Agent runtime context instead of building a parallel tool dispatcher
- Skills effort strategy handlers follow the `SkillsEffortStrategyHandler`
  protocol with keyword arguments `context`, `task`, `plan`, `output_format`,
  `effort`, and `effort_config`; builtin strategies `single_shot`,
  `runtime_chain`, `staged`, and `react` are exposed through the same strategy
  table and can be inspected with `list_effort_strategies()`; their reference
  implementations live under the Agently builtin Skills Executor
  `modules/effort_strategies/` package
- direct `agent.run_skills_task(..., stream_handler=...)` handlers receive
  Skills runtime item dictionaries and can be annotated with
  `SkillRuntimeStreamHandler`; model stream handlers passed to
  `context.async_request_model(..., stream_handler=...)` receive `StreamingData`
  and can be annotated with `ModelStreamingHandler`; the common aliases are
  available from `agently`
- for MCP, prefer Streamable HTTP URLs for service integrations
  (`agent.use_mcp("https://host/mcp")`), use `headers=` for URL auth, and use
  MCP config dictionaries for stdio/multi-server local integrations; treat SSE
  as a legacy compatibility transport
- treat chained Agent quick prompt methods as AgentExecution-local configuration
  for one request/execution surface:
  `agent.input(...).output(...).run_skills_task(...)` maps the execution prompt
  snapshot to the Skill task and maps `output` / `output_format` to the Skills
  execution `output` / `output_format` contract; Agent-level persistent prompt
  must be explicit through `agent.define(...)`, `always=True`,
  `set_agent_prompt(...)`, or stable setup APIs. For multi-statement execution setup, use
  `execution = agent.create_execution()` and mutate the execution, not the
  shared Agent pending prompt. `semantic_outputs=` is only a deprecated
  compatibility alias for direct Skills execution, while Dynamic Task still
  uses `semantic_outputs` inside TaskDAG specs
- for framework-side Skills execution, keep standard `SKILL.md` as the only
  capability definition; selected Skills default to `single_shot` model
  requests using their full Markdown guidance, while declared staged/react
  strategies should compose TriggerFlow and ActionFlow/ActionRuntime rather
  than adding a Skills-local executor
- for Skills `react` tool use, delegate model-owned action planning and
  execution to the Agent ActionRuntime so action/MCP kwargs schemas, policy,
  approvals, concurrency, and managed resources stay on the Action layer
- when Skills `react`, AgentTaskLoop, or another higher-level runtime delegates
  action planning to ActionRuntime, set `action.planning_model_key` to the
  intended `model_pool` business key so action planning uses the same model
  routing as the surrounding task
- Skills are public-standard `SKILL.md` guidance/resources, not Agently-private
  capability manifests; do not author or recommend `allowed-actions`,
  `allow-scripts`, `mcp`, `mcpServers`, `execution`, or `stages` frontmatter as
  Agently capability declarations
- SkillsExecutor discovers selected Skill capability needs from `SKILL.md`,
  resource indexes, public `compatibility`, public `metadata`, and optional
  model-assisted inference, then records structured `capability_needs`; selected
  Skills may guide the model to use capabilities when available, but they do not
  grant them
- host applications control Skills capability loading with
  `agent.configure_skill_capabilities(auto_load={...})`; `allow` can auto-load
  built-in Search/Browse/HTTP/Workspace/Python/shell-script/MCP capabilities,
  while `approval` and `off` fail closed with diagnostics instead of silently
  mounting tools
- for search-oriented Skills, prefer the framework Search package backed by the
  `ddgs` Python package; keep `ddgs` upgraded with
  `python -m pip install --upgrade ddgs` before real search runs, and leave the
  ddgs backend strategy configurable (`auto` by default) instead of hard-coding
  a single backend; Search treats backend-level "no results" as an empty
  successful action result and falls back through configured/default ddgs
  backends when a selected backend returns no usable parsed result; if fallback
  recovers after backend failures, Search reports `status="partial_success"`
  with `success=True` and diagnostics rather than an `action.failed` terminal
  condition
- when observing ActionFlow records, treat `action.approval_required` and
  `action.blocked` as policy/sandbox gate outcomes, not ordinary
  `action.failed` execution failures
- Workspace owns file-action roots and path boundaries; expose file access
  through Workspace-scoped file actions, and treat ActionRuntime as the callable
  surface rather than the owner of Workspace semantics
- Skills capability `approval` is resolved through Agently's global
  PolicyApproval handler, not a SkillsExecutor-local handler:
  `input_timeout_fail` by default, `auto_approve` for tests/trusted local
  profiles, `fail_closed` when a host wants pending diagnostics or TriggerFlow
  policy interrupts, `input` for local CLI interruption, or a host-provided
  durable/network handler
- production services should choose a PolicyApproval handler that matches the
  service wrapping the TriggerFlow execution: database pending record, HTTP
  callback, webhook resume, SSE/WebSocket pending stream, save-and-return
  interrupt id, or another host-owned approval channel; tests may use
  `auto_approve`
- script resources under `scripts/` can be wrapped as scoped shell actions only
  when host policy allows `script_run`; the action root must be the installed
  Skill directory and execution still goes through ActionRuntime /
  ExecutionEnvironment boundaries
- public Agent Skills `allowed-tools` is experimental and, if supported, can
  only restrict or pre-approve already-mounted host tools; it must not create
  tools, synthesize backends, mount MCP, or choose Skills execution strategy by
  itself
- for Agently 4.1.2.x auto-orchestration work, treat
  `agent.use_skills(...).input(...).start()` as route-candidate registration
  owned by the Agent route planner, not prompt-only Skills guidance injection by
  default
- for ambiguous optional route candidates, keep submitted Dynamic Task and
  required Skills deterministic, but let the model choose among optional auto
  Dynamic Task, model-decision Skills, and ordinary Action-backed model request
  routes
- for framework-side Skills, treat standard `SKILL.md` as the only capability
  definition; Agently install metadata and decision cards are descriptive
  runtime aids, not authoring formats or availability gates
- for Skills actions, use the global PolicyApproval contract plus
  Action/ExecutionEnvironment resource boundaries; when the request is
  orchestrated, pending approvals must become TriggerFlow `policy_approval`
  interrupts instead of Skills snapshots
- keep Agent auto-orchestration behind the `AgentOrchestrator` plugin protocol:
  core owns the public `agent.create_execution()` entrypoint, while the active
  plugin owns route planning, execution, and stream bridging
- for unified Agent execution/result work, prefer a response-style
  `agent.create_execution()` object with data/text/meta/stream consumption; use
  TriggerFlow runtime stream plus ModelRequest `instant` checkpoints for process
  streaming, and expose model field deltas only through stable structured paths
  such as `task_dag.tasks.<task_id>.fields.<field_path>` rather than raw provider
  token events
- for bounded developer-owned loops, use
  `agent.create_execution(lineage=..., limits=..., options=...)`; lineage,
  diagnostics, stream correlation metadata, and shared model-request budget
  counting now describe the bounded step without a public mode name
- keep AgentExecution memory explicit: write observations/checkpoints/artifacts
  through the execution's bound Workspace helper, such as
  `await execution.async_record_workspace(collection="observations", checkpoint=True)`,
  which writes requested checkpoints through the Workspace checkpoint-store port
  and records an evidence link between the AgentExecution record and checkpoint;
  then call `workspace.build_context(...)` for the next step; ordinary one-turn
  AgentExecution remains explicit, while AgentTaskLoop owns its strategy-level
  persistence; do not make Workspace depend on AgentExecution-specific strategy
  semantics
- inspect AgentExecution runtime facts through AgentExecutionResult or the
  execution facade: `result = execution.get_result()`, `result.get_text()`,
  `result.get_data()`, `result.get_meta()`, `execution.get_async_generator()`,
  and `await execution.async_get_meta()`. `meta["route"]` records the selected
  route/options, and `meta["logs"]` exposes model response ids, ActionRuntime
  action logs, task refs, and artifact refs when available; use those
  framework-owned records for Workspace persistence instead of asking the model
  to copy raw action stdout into final text
- bound long or nested AgentExecution steps with `limits={"max_seconds": ...,
  "max_no_progress_seconds": ...}` when diagnosing or building host-owned loops;
  catch `RuntimeStageStallError` from the root `agently.core` export or
  `agently.core.application.AgentExecution` and inspect
  `meta["diagnostics"]["last_progress"]`, `["timeouts"]`, and `["stalls"]`
  instead of adding ad hoc polling around the whole app
- for provider stream hangs, prefer framework settings such as
  `OpenAICompatible.stream_idle_timeout`,
  `OpenAIResponsesCompatible.stream_idle_timeout`, and
  `response.materialization_idle_timeout`; use `None` for unlimited budgets and
  avoid permanent debug-only timeout wrappers in examples; provider first-event
  and stream-idle waits should surface as `RuntimeStageStallError` with
  `stage="response_first_event"` or `stage="response_stream"`; OpenAI-compatible
  transient disconnects before output starts use same-request
  `OpenAICompatible.request_retry`; explicit
  response stream errors should propagate from response getters with the
  original provider or ActionFlow reason before materialization timeout is used
  as a fallback
- when high-frequency RuntimeEvent deltas would overload downstream consumers,
  keep producers raw and ask the expensive EventCenter outlet to summarize with
  hook/hooker `delivery_policy={"mode": "summary", "dispatch": "await",
  "emit_interval": ..., "max_items": ...}`; use `dispatch="background"` only
  for best-effort outlets that call `EventCenter.async_flush(...)` or expose an
  owning bridge flush/close point; EventCenter also has an idle flush safety net
  for long-lived loops, but CLI/script shutdown still needs explicit flush for
  background outlets; rely on AgentExecution liveness diagnostics rather than
  public delta frequency for stall detection
- for temporary development debugging, attach an EventCenter observation hook or
  call `.set_settings("debug", True)` / `.set_settings("debug", "detail")` to
  inspect route selection, model requests, ActionRuntime, and Workspace writes;
  remove debug hooks/settings from examples and production snippets after the
  issue is diagnosed

## Anti-Patterns

- do not build a parallel action/tool dispatcher before checking Action Runtime
- do not hand-roll tool schema prompts or kwargs planners in Skills when the
  Agent ActionRuntime can plan against the registered action list
- do not expose core Execution Environment manager APIs as the default app-development mental model
- do not route package installation or filesystem mutation through the Python sandbox
- do not ask users to clone or editable-install DevTools when `pip install agently-devtools` fits
- do not make DevTools the source of truth for workflow structure
- do not present prompt-only Skills disclosure as the default execution meaning
  of `agent.start()` once the 4.1.3 route planner owns Skills candidates
- do not put route-owned Skills, Dynamic Task, or stream-composition logic
  directly in core when a plugin protocol can own the replaceable behavior

## Read Next

- `references/actions-runtime.md`
- `references/actions-execution-environment.md`
- `references/devtools.md`
