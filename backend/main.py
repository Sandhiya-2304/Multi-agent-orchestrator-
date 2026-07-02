from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.db import init_db
from backend.routes import router

from pathlib import Path

FRONTEND_DIR = Path(__file__).resolve().parent / "frontend"
# FRONTEND_DIR = Path(__file__).resolve().parent.parent / "public"

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")



@app.on_event("startup")
def startup():
    init_db()



@app.get("/chat/{conversation_id}")
async def chat_page(conversation_id: str):
    return FileResponse(str(FRONTEND_DIR / "index.html"))

# Mount static files last as a catch-all for local development
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="static")
else:
    @app.get("/")
    async def fallback_home():
        return {"error": f"Frontend directory not found at {FRONTEND_DIR}"}