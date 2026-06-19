# Agently Migration Reference

Use this skill first for migration requests with unresolved migration ownership.

## Native-First Rules

- classify the source system before giving implementation steps
- route LangChain agent-side work to `agently-request` and `agently-runtime`
- route LangGraph orchestration work to `agently-triggerflow`

## Anti-Patterns

- do not mix LangChain and LangGraph migration guidance in one undifferentiated answer
- do not redesign the target stack before mapping the source surface

## Read Next

- `references/overview.md`
