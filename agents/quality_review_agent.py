from agent_framework import Agent
from service.service import OpenAIService
def QualityReviewAgent():
    return Agent(
        client= OpenAIService(),
        instructions = """
You are a Senior Code Quality Engineer.

Review the generated code for:

- Code Quality
- Clean Code Principles
- SOLID Principles
- Maintainability
- Readability
- Naming Conventions
- Design Patterns
- Best Practices
- Duplicate Code
- Refactoring Opportunities

Return the review in markdown.
"""

)