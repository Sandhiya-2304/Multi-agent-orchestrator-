import asyncio

from backend.orchestrator import SDLCOrchestrator


async def main():

    print("=" * 60)
    print("AI Multi-Agent SDLC Framework")
    print("=" * 60)

    task = input("Enter Software Requirement : ")

    orchestrator = SDLCOrchestrator()

    result = await orchestrator.execute_sdlc(user_request=task)

    print("\n" + "=" * 60)
    print("DONE - output written under:", orchestrator.output_root)
    print("=" * 60)


if __name__ == "__main__":  #directly run the script
    asyncio.run(main())     #starts async system and runs the main function   