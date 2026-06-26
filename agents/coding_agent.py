from agent_framework import Agent

from service.service import OpenAIService

def CodingAgent():
    return Agent(
        client=OpenAIService(),
        instructions = """
        You are a Senior Software Engineer.

        Generate production-ready code.

        Requirements:

        - Clean Architecture
        - Best Practices
        - Proper Naming
        - Scalable Design
        - Comments where required

        Always return markdown.
        """
    )