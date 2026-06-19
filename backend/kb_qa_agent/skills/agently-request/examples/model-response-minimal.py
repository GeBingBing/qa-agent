from agently import Agently

agent = Agently.create_agent()
result = agent.input("Explain recursion briefly.").output({"answer": (str,)}).get_result()
print(result.get_data())
