# TriggerFlow Runtime Intervention

Use runtime intervention when outside code may add optional supplemental context
while a TriggerFlow execution is already running. It is an execution-local
ledger and visibility mechanism, not a wait gate and not graph mutation.

Runtime intervention is disabled unless execution creation opts in or the flow
declares an explicit intervention point:

```python
execution = flow.create_execution(
    auto_close=False,
)
```

Prefer `planned` mode when workflow authors know the safe insertion boundary:

```python
(
    flow
    .to(extract_terms)
    .intervention_point(name="before_risk", target="before_risk")
    .to(risk_assessment)
)
```

When a flow declares `intervention_point(...)`, `create_execution(...)` infers
planned mode if `intervention_mode` is omitted. Pass `intervention_mode=None`
only when you deliberately want to disable intervention for that execution.

Use `auto` mode when the service wants TriggerFlow's boundary policy: targeted
items insert before the first matching operator id, name, kind, group id, or
group kind; untargeted items insert at the next chunk boundary. Do not mix auto
mode with explicit `intervention_point(...)` operators.

Add context through the execution handle:

```python
await execution.async_intervene(
    {"text": "Attachment A is the latest price table."},
    author="reviewer",
    target="before_risk",
)
```

Chunks read only inserted context from runtime data:

```python
async def risk_assessment(data):
    supplements = data.get_interventions(status="inserted", target="before_risk")
    result = await assess_with_model(
        {
            "terms": data.input,
            "supplements": [item["payload"] for item in supplements],
        }
    )
    for item in supplements:
        await data.async_mark_intervention_consumed(
            item["id"],
            status="applied",
        )
    return result
```

Reading is not consumption. Consumption is explicit per consumer and supports
`"applied"` or `"ignored"`. Runtime data defaults `consumer` to the current
chunk name; execution-level consumption calls still pass a consumer explicitly.

At close, still-pending interventions become `"expired"`. The ledger remains
available through `execution.result.get_interventions(...)` and the close
snapshot's reserved `"$interventions"` key.

Runtime intervention emits fail-open runtime stream items:

```python
{
    "type": "intervention",
    "action": "append",  # append | insert | expire | consume | reject
    "execution_id": execution.id,
    "intervention": {...},
}
```

Do not use runtime intervention for required human approval. If the workflow
must wait for a user, webhook, or external system, use `pause_for(...)` with an
explicit `resume_to` target and resume with `continue_with(...)`.

For runnable main-repo scenarios, see:

- `examples/step_by_step/11-triggerflow-21_document_review_runtime_intervention.py`
  for planned-mode insertion at an explicit intervention point.
- `examples/step_by_step/11-triggerflow-22_ticket_triage_auto_intervention.py`
  for auto-mode insertion before a matching chunk boundary.
