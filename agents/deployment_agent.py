from agent_framework import Agent
from service.service import OpenAIService
def DeploymentAgent():
    return Agent(
        client= OpenAIService(),
        instructions = """
You are a DevOps Engineer.

Generate deployment instructions.

Include:

- Environment Variables
- Docker
- CI/CD
- Azure Deployment
- Production Checklist

Return markdown.
"""

)