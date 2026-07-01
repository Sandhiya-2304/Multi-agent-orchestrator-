from dotenv import load_dotenv
load_dotenv()

import os
from agent_framework.openai import OpenAIChatCompletionClient,OpenAIChatClient

def OpenAIService():
    return OpenAIChatCompletionClient(
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
        model=os.getenv("AZURE_OPENAI_DEPLOYMENT"),
    )