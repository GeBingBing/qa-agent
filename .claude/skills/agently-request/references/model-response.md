# Agently Model Result

Use this skill when the output contract is already chosen and the remaining issue is how the result facade should be consumed or reused.

The user does not need to say `get_result()`. Requests to reuse one result as text, parsed data, metadata, or progressive updates should route here.

## Native-First Rules

- prefer `get_result()` when one request result must be consumed more than once
- default to async-first response APIs in services, streaming paths, TriggerFlow steps, and any integration that may overlap work
- treat sync getters and generators as convenience wrappers for scripts, REPL use, or compatibility bridges
- use `delta`, `instant`, `specific`, or `all` instead of custom stream splitting logic
- annotate common stream consumers from `agently`: `StreamingData` for
  `instant` / `streaming_parse`, `AgentlySpecificResultMessage` for
  `specific`, and `AgentlyModelResultMessage` for `all`; use
  `agently.types.data` when the full typed data namespace is needed
- subscribe to `reasoning_delta` / `reasoning_done` through `type="specific"`
  when reasoning output is needed. Provider-native reasoning and a leading
  outer `<think>...</think>` before the answer payload belong in reasoning
  events; `original_delta` / `original_done` keep the raw provider content.
  Payload-internal `<think>` remains ordinary answer text
- treat `instant` `.is_complete` as path completion, not a global display-order
  barrier. For Web UI, SSE, or WebSocket consumers, render each path into its
  own slot. For CLI consumers that print multiple paths into one terminal area,
  use a small state flag or buffer and flush later-path deltas only after the
  earlier path's completion event has been handled

## Anti-Patterns

- do not re-issue the same request to obtain text, data, and metadata separately
- do not build ad hoc field-level stream parsers when `instant` or `streaming_parse` already fits
- do not strip reasoning tags inside format-specific parsers

## Read Next

- `references/overview.md`
