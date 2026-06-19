from agently import Agently

agent = Agently.create_agent()

result = (
    agent.input("Classify this production incident")
    .output({"status": (str, None, True), "severity": (str, None, True)})
    .get_result()
)

data = result.get_data(
    validate_handler=lambda result, context: (
        result["status"] == "ready"
        and result["severity"] in {"P0", "P1", "P2", "P3"}
    ),
    max_retries=2,
)

print(data)
