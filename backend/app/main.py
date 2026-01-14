from fastapi import FastAPI, Request
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from .workflow import ConversationManager
import os

app = FastAPI(title="University Assistant")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

manager = ConversationManager()

class ChatRequest(BaseModel):
    session_id: str | None = None
    message: str

class ChatResponse(BaseModel):
    response: str
    session_id: str

@app.post('/chat', response_model=ChatResponse)
async def chat(req: ChatRequest):
    # ensure session id is returned so frontend can persist it
    session_id = req.session_id or None
    response_text = await manager.handle_message(session_id, req.message)
    # manager may have created a new session; return its id
    # find the correct session id (the manager returns state.session_id if a new one was created)
    # For simplicity, if req.session_id was None, get the last created session id from manager
    if req.session_id:
        sid = req.session_id
    else:
        # take the last session key (the one just created)
        sid = list(manager.sessions.keys())[-1]
    return ChatResponse(response=response_text, session_id=sid)

@app.get('/health')
async def health():
    return {"status": "ok"}
