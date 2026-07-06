from pydantic import BaseModel

class ChatRequest(BaseModel):
    message: str
    attachment_filenames: list[str] = []
    attachment_document_ids: list[int] = []

class LoginRequest(BaseModel):
    email: str
    password: str
# This file defines the structure of incoming API request data and automatically validates it before your FastAPI endpoint processes it.