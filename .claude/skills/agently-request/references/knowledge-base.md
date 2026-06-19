# Agently Knowledge Base

Use this skill when embeddings, Workspace recall, and retrieval are the main
capability surface.

## Native-First Rules

- prefer embedding-agent plus Chroma integration before custom vector plumbing
- for multi-turn task information already stored in Workspace, prefer
  `workspace.build_context(goal=..., scope=..., budget=..., profile=...)` so
  RecallPlanner, Retriever, and ContextBuilder plugins own the retrieval path
- use `workspace.search(...)` for low-level debugging or explicit filters, not
  as the normal app-facing recall API
- use `workspace.get_data(...)` for structured records/checkpoints and
  `workspace.links(...)` for decision/evidence lineage when retrieval feeds a
  later loop step
- separate indexing, retrieval, and answer generation concerns
- keep retrieval results explicit when they feed a later request

## Anti-Patterns

- do not hide KB retrieval inside unrelated prompt logic
- do not treat embeddings-only setup and KB-backed answer flow as unrelated stacks
- do not ask business code to hand-write ordinary multi-turn recall filters when
  a Workspace ContextPack is the right shape

## Read Next

- `references/overview.md`
