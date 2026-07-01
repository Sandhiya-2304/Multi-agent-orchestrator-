from agent_framework import Agent
from backend.service.service import OpenAIService
def UserStoryAgent():
    return Agent(
        client= OpenAIService(),

        instructions = """
You are an Agile Product Owner.

Convert software requirements into User Stories.

For every feature provide:

- Title
- User Story
- Acceptance Criteria

Use markdown.
"""

)