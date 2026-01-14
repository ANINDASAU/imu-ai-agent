# University Assistant (Minimal Demo)

This repository contains a minimal AI-powered Assistant Management System for university students.

Features
- Simple chat UI (React + Vite)
- Backend (FastAPI) with a small LangGraph-like conversation manager
- Rule-based routing to university units
- Collects student name and academic year before submitting
- Stores submissions in Supabase and sends a webhook POST

Getting started

1. Backend
- Create `.env` at `backend/.env` based on `.env.example` and fill `SUPABASE_URL`, `SUPABASE_KEY`, and `WEBHOOK_URL`.
- Install dependencies: `pip install -r backend/requirements.txt`
- Run: `uvicorn app.main:app --reload --port 8000`

2. Frontend
- cd frontend
- `npm install`
- `npm run dev` (Vite will run on `http://localhost:5173`)

Database
- Run `backend/db/init.sql` in your Supabase SQL editor to create the `student_queries` table.

Notes
- This is a minimal demo. Conversation state is stored in-memory per server process. For production, persist sessions in DB.
- The conversation manager is intentionally simple and deterministic to follow the spec (no hallucinations).

Example quick test (curl):

1) Start with an initial message (no session id):

curl -X POST http://localhost:8000/chat -H 'Content-Type: application/json' -d '{"message":"Hello, I have a question about scholarships"}'

2) Server returns response and session_id. Reuse session_id for follow-ups:

curl -X POST http://localhost:8000/chat -H 'Content-Type: application/json' -d '{"session_id":"<session_id>", "message":"My name is Jane Doe"}'

3) Then provide year:
curl -X POST http://localhost:8000/chat -H 'Content-Type: application/json' -d '{"session_id":"<session_id>", "message":"I am in 2nd year"}'

When all fields are collected the record will be stored in Supabase and the webhook will be POSTed with the structured payload.
