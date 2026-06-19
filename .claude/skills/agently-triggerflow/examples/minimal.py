import asyncio

from agently import TriggerFlow

flow = TriggerFlow()


async def finish(data):
    await data.async_set_state("output", {"stage": "done", "input": data.input})


flow.to(finish)


async def main():
    execution = flow.create_execution()
    await execution.async_start("demo")
    await execution.async_close()
    print(
        {
            "output": execution.result.get_state("output"),
            "meta": execution.result.get_meta(),
        }
    )


asyncio.run(main())
