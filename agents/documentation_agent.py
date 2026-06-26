from agent_framework import Agent
from service.service import OpenAIService
def DocumentationAgent():
    return Agent(
        client= OpenAIService(),
        instructions = """
You are a Technical Writer.

Generate project documentation.

Include:

- Overview
- Installation
- Usage
- API
- Folder Structure

Return markdown.
"""

)