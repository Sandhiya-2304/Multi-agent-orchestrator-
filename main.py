import asyncio

from orchestrator import SDLCOrchestrator


async def main():

    print("=" * 60)
    print("AI Multi-Agent SDLC Framework")
    print("=" * 60)
    task_name = input("Enter Task Name : ")


    task = input("Enter Software Requirement : ")

    orchestrator = SDLCOrchestrator()


    await orchestrator.execute(
        task_name=task_name,
        user_request=task,
    )


if __name__ == "__main__":  #directly run the script
    asyncio.run(main())     #starts async system and runs the main function   