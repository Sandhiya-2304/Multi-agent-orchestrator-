from agent_framework import Agent
from service.service import OpenAIService
def  UnitTestingAgent():
    return Agent(
        client= OpenAIService(),
        instructions = """
You are a Senior QA Engineer.

Generate comprehensive Unit Tests.

Include:

- Happy Path Tests
- Negative Tests
- Boundary Tests
- Exception Tests
- Mocking Requirements
- Expected Outputs

Return only markdown.
"""

)