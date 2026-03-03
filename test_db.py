import asyncio

from src.agents.co_writer.narrator_agent import NarratorAgent


async def test_narrator():
    print("Initializing narrator...")
    agent = NarratorAgent()
    print("Done. Ready to generate audio (will skip db save safely)...")


if __name__ == "__main__":
    asyncio.run(test_narrator())
