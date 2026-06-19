from agently import Agently

agent = Agently.create_agent()
result = (
    agent.input("Summarize the repo")
    .output({"summary": (str, None, True), "risks": [(str, None, True)]})
    .validate(lambda result, context: len(result["summary"].strip()) > 0)
    .start(max_retries=1)
)
print(result)
