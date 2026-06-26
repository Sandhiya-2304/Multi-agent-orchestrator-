from agent_framework import Agent
from service.service import OpenAIService
def ArchitectureAgent():
    return Agent(
        client= OpenAIService(),
          instructions = """
You are a Senior Software Architect.

Design the system architecture.

Include:

- Frontend
- Backend
- Database
- APIs
- Authentication
- Deployment
- Folder Structure

Return everything in markdown.
"""

    )