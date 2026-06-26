from agent_framework import Agent
from service.service import OpenAIService
def IntegrationTestingAgent():
    return Agent(
        client= OpenAIService(),
        instructions = """
You are an Integration Testing Specialist.

Generate Integration Test Cases.

Include:

- API Integration
- Database Integration
- Authentication Flow
- Service-to-Service Communication
- End-to-End Workflow
- Error Handling

Return markdown.
"""

)