from agently import Agently


async def local_handler(context):
    return {
        "task_id": context.task.id,
        "dependency_results": dict(context.dependency_results),
    }


task = Agently.create_dynamic_task(
    target="review policy",
    plan={
        "graph_id": "review",
        "task_schema_version": "task_dag/v1",
        "tasks": [
            {"id": "extract", "kind": "local", "binding": "local_handler"},
            {
                "id": "final",
                "kind": "local",
                "binding": "local_handler",
                "depends_on": ["extract"],
            },
        ],
        "semantic_outputs": {"final": "final"},
    },
    handlers={"local_handler": local_handler},
)


# Expected key output:
# snapshot["semantic_outputs"]["final"]["task_id"] == "final"
async def run():
    snapshot = await task.async_start(timeout=10)
    return snapshot
