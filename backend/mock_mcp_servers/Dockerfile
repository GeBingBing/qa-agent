# mock-internal-mcp 镜像：纯 stdlib，把 4 域工具暴露为 MCP-over-HTTP。
# 仅依赖 backend/kb_qa_agent/{core/tool_registry.py, domains/*}（无 chromadb / openai / agently）。
# 该 Dockerfile 由 docker-compose.yml 在 context=./backend 下构建。
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY kb_qa_agent ./kb_qa_agent
COPY mock_mcp_servers ./mock_mcp_servers

EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8765/health', timeout=2).status==200 else 1)" || exit 1

CMD ["python", "-m", "mock_mcp_servers.internal_systems_mcp"]
