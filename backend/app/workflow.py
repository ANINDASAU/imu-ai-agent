"""
A minimal LangGraph-like conversation manager implementing the nodes described in the spec.
This is a lightweight, dependency-free orchestrator designed for the demo.
"""
import re
import uuid
from datetime import datetime
import httpx
import os
from typing import Dict, Any
from .supabase_client import SupabaseClient

# Optional Gemini LLM support (google-generativeai)
try:
    import json
    import google.generativeai as genai
    API_KEY = os.getenv('GOOGLE_API_KEY')
    if API_KEY:
        genai.configure(api_key=API_KEY)
        LLM_MODEL = os.getenv('GEN_MODEL', 'models/gemini-2.5-flash')
        LLM_ENABLED = True
    else:
        LLM_ENABLED = False
except Exception:
    # If the package is not installed or configuration fails, the app will fall back to rule-based routing
    genai = None
    LLM_ENABLED = False

SUPABASE = SupabaseClient()
WEBHOOK_URL = os.getenv('WEBHOOK_URL')

# Greeting detection to avoid treating short greets as a query
GREETINGS = {"hi", "hello", "hey", "hii", "hiii", "good morning", "good afternoon", "good evening"}

# Common query prefixes the user may start with; we'll strip them before storing
_QUERY_PREFIX_RE = re.compile(r"^\s*(my\s+query\s+is|query\s+is|question\s+is)\s*[:\-\s]*", re.IGNORECASE)

def is_greeting(text: str) -> bool:
    if not text:
        return False
    t = re.sub(r"[^a-zA-Z0-9\s]", "", text.lower()).strip()
    if not t:
        return False
    if t in GREETINGS:
        return True
    # treat very short messages like "hi", "ok" as greeting/noise
    if len(t.split()) == 1 and len(t) <= 3:
        return True
    return False


def strip_query_prefix(text: str) -> str:
    """Remove leading 'my query is', 'query is', or 'question is' from the text."""
    if not text:
        return text
    return _QUERY_PREFIX_RE.sub('', text).strip()

# Helper functions
YEAR_MAP = {
    '12': '12th_pass', '12th': '12th_pass', '12th_pass': '12th_pass',
    '1': '1st_year', '1st': '1st_year', 'first': '1st_year', '1st_year': '1st_year',
    '2': '2nd_year', '2nd': '2nd_year', 'second': '2nd_year', '2nd_year': '2nd_year',
    '3': '3rd_year', '3rd': '3rd_year', 'third': '3rd_year',
    '4': '4th_year', '4th': '4th_year', 'fourth': '4th_year'
}

UNIT_MAP = {
    'admission': 'admission_scholarship', 'admissions': 'admission_scholarship', 'scholarship': 'admission_scholarship', 'fees': 'admission_scholarship', 'eligibility': 'admission_scholarship',
    'exam': 'academic_support', 'exams': 'academic_support', 'subject': 'academic_support', 'attendance': 'academic_support', 'grading': 'academic_support', 'books': 'academic_support',
    'hostel': 'student_welfare', 'grievance': 'student_welfare', 'grievances': 'student_welfare', 'wellbeing': 'student_welfare', 'well-being': 'student_welfare', 'stressed': 'student_welfare', 'unwell': 'student_welfare',
    'internship': 'career_skill_development', 'placement': 'career_skill_development', 'skills': 'career_skill_development', 'resume': 'career_skill_development'
}

class ConversationState:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.student_name: str | None = None
        self.academic_year: str | None = None
        self.student_query: str | None = None
        self.routed_unit: str | None = None
        self.tone: str | None = None  # 'urgent' | 'normal' inferred by LLM
        self.last_bot_message: str | None = None
        self.created_at = datetime.utcnow()
        self.submitted: bool = False  # prevents duplicate webhook triggers

    def is_complete(self):
        return all([self.student_name, self.academic_year, self.student_query, self.routed_unit])

    def to_record(self) -> Dict[str, Any]:
        return {
            'student_name': self.student_name,
            'academic_year': self.academic_year,
            'student_query': self.student_query,
            'routed_unit': self.routed_unit,
            'tone': self.tone,
            'timestamp': self.created_at.isoformat()
        }

class ConversationManager:
    def __init__(self):
        # In-memory sessions: session_id -> ConversationState
        self.sessions: Dict[str, ConversationState] = {}

    async def handle_message(self, session_id: str | None, message: str) -> str:
        if not session_id:
            session_id = str(uuid.uuid4())
        if session_id not in self.sessions:
            self.sessions[session_id] = ConversationState(session_id)

        state = self.sessions[session_id]
        # Handle explicit start command or simple greeting to show the agent intro
        if message and (message.strip() == "__start__" or (is_greeting(message) and not any([state.student_name, state.academic_year, state.student_query]))):
            state.last_bot_message = ("Hi, My name is iMu. I am here to help you what to do according to your query. "
                                      "Could you please tell me your full name?")
            return state.last_bot_message

        # Try to extract name and academic year from the user's message (user may supply them freely)
        if not state.student_name:
            name = self.extract_name(message)
            if name:
                state.student_name = name
        if not state.academic_year:
            year = self.extract_year(message)
            if year:
                state.academic_year = year

        # If the message contains more than just name/year and it's not a greeting/start, treat it as the student's query
        if not state.student_query and message and not is_greeting(message) and message.strip() != "__start__":
            # If the message explicitly starts with a known query prefix, strip it and accept the remainder as the query
            stripped = strip_query_prefix(message)
            if stripped and stripped != message:
                state.student_query = stripped
                print(f"[workflow] Detected prefixed student_query for session {state.session_id}: {state.student_query}")
            else:
                # If the message is clearly a name or a year, do NOT treat it as the query
                if self.extract_name(message) or self.extract_year(message):
                    # It's likely the user is giving name or year; skip setting query
                    pass
                else:
                    # Heuristic: set as query if reasonably long, contains a question mark, or contains known keywords
                    msg_low = message.lower()
                    keywords = ['scholarship','admission','exam','exams','attendance','grading','hostel','grievance','grievances','wellbeing','internship','placement','skills','fees','subject','fee']
                    if len(message.strip()) > 10 or '?' in message or any(k in msg_low for k in keywords):
                        state.student_query = message
                        print(f"[workflow] Detected student_query for session {state.session_id}: {state.student_query}")

        # Decide what to ask next - ensure we ask only one missing field at a time
        # Order: name -> academic_year -> query
        if not state.student_name:
            state.last_bot_message = "Hi! Could you please tell me your full name?"
            return state.last_bot_message
        if not state.academic_year:
            state.last_bot_message = "Thanks, {name}. Which education year are you in? (12th_pass / 1st_year / 2nd_year / 3rd_year / 4th_year)".format(name=state.student_name)
            return state.last_bot_message
        if not state.student_query:
            state.last_bot_message = ("Thanks, {name}. Could you please briefly describe your question or issue? "
                                      "(You may start with 'My query is', 'Query is', or 'Question is' — optional.)").format(name=state.student_name)
            return state.last_bot_message

        # If we reach here, all fields are present or were set from the message; ensure routed_unit is set from the query
        if not state.routed_unit:
            state.routed_unit = self.router_node(state.student_query or message)
            print(f"[workflow] Routed session {state.session_id} to unit: {state.routed_unit}")

        # If all required collected, store and trigger webhook
        if state.is_complete():
            # Only trigger webhook once and ensure query is not just a greeting
            if not state.submitted and state.student_query and not is_greeting(state.student_query):
                await self.persist_and_send(state)
                state.submitted = True
                state.last_bot_message = "Thank you {name}. Your query has been submitted to the {unit} unit. They will reach out to you.".format(name=state.student_name, unit=self.user_friendly_unit_name(state.routed_unit))
                return state.last_bot_message
            # If query is missing or invalid, ask for it explicitly
            if not state.student_query or is_greeting(state.student_query):
                state.last_bot_message = "Could you please write the full question or issue you'd like help with?"
                return state.last_bot_message
            else:
                return "Your query is already submitted."

        # Fallback
        state.last_bot_message = "Can you provide more details?"
        return state.last_bot_message

    def router_node(self, message: str) -> str:
        text = message.lower()
        # Rule-based classification by keywords
        for kw, unit in UNIT_MAP.items():
            if kw in text:
                return unit
        # Default to Academic Support if not clear
        return 'academic_support'

    def llm_classify(self, message: str) -> tuple[str, str] | None:
        """Call the Gemini LLM to classify the message into a unit and detect tone ('urgent' or 'normal').
        Returns (unit_key, tone) or None on failure."""
        if not message or not LLM_ENABLED:
            return None
        try:
            system_prompt = (
                "You are a concise classifier. Map the student query to one of: "
                "admission_scholarship, academic_support, student_welfare, career_skill_development. "
                "Also determine the tone: 'urgent' if the student is asking for immediate help or indicates an emergency, otherwise 'normal'. "
                "Respond only with a single-line JSON object with keys 'unit' and 'tone', e.g. {\"unit\": \"academic_support\", \"tone\": \"normal\"}."
            )
            user_prompt = f"Student query: {message}"
            resp = genai.chat.create(model=LLM_MODEL, messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}])

            # Robustly extract text from the response
            text = ''
            try:
                # preferred: resp.last.content or resp.candidates
                if hasattr(resp, 'last') and resp.last and hasattr(resp.last, 'content'):
                    text = resp.last.content[0].get('text', '') if isinstance(resp.last.content, list) else str(resp.last.content)
                elif hasattr(resp, 'candidates') and resp.candidates:
                    cand = resp.candidates[0]
                    # candidate may be a dict with content
                    if isinstance(cand, dict) and 'content' in cand:
                        content = cand['content']
                        if isinstance(content, list) and content:
                            text = content[0].get('text', '')
                        else:
                            text = str(content)
                    else:
                        text = str(cand)
                else:
                    text = str(resp)
            except Exception:
                text = str(resp)

            # extract JSON object from the model output
            import re, json
            m = re.search(r"\{.*\}", text, re.S)
            if m:
                obj_text = m.group(0)
                parsed = json.loads(obj_text)
                unit = parsed.get('unit')
                tone = parsed.get('tone', 'normal')
                return unit, tone

            # Fallback: simple keyword extraction from model text
            t_low = text.lower()
            for kw, unit in UNIT_MAP.items():
                if kw in t_low:
                    tone = 'urgent' if any(w in t_low for w in ['urgent', 'emergency', 'immediately', 'asap']) else 'normal'
                    return unit, tone
        except Exception as e:
            print(f"[workflow] Error during LLM classify: {e}")
        return None

    def extract_year(self, message: str) -> str | None:
        t = message.lower()
        # pattern match
        for short, mapped in YEAR_MAP.items():
            if re.search(r"\b" + re.escape(short) + r"\b", t):
                return mapped
        # look for explicit forms like "1st year" or "12th pass"
        m = re.search(r"(\b\d{1}st|\d{1}nd|\d{1}rd|12th)\b", t)
        if m:
            token = m.group(1)
            return YEAR_MAP.get(token, None)
        return None

    def extract_name(self, message: str) -> str | None:
        # Extremely simple heuristic: look for "my name is X" or "I am X"
        m = re.search(r"my name is ([A-Za-z ]{2,50})", message, re.IGNORECASE)
        if m:
            return m.group(1).strip()
        m = re.search(r"^i am ([A-Za-z ]{2,50})", message, re.IGNORECASE)
        if m:
            return m.group(1).strip()
        m = re.search(r"i'm ([A-Za-z ]{2,50})", message, re.IGNORECASE)
        if m:
            return m.group(1).strip()
        return None

    async def persist_and_send(self, state: ConversationState):
        # Store in Supabase
        # Ensure query stored and sent is stripped of leading prefixes
        clean_query = strip_query_prefix(state.student_query or "")
        record = {
            'student_name': state.student_name,
            'academic_year': state.academic_year,
            'student_query': clean_query,
            'routed_unit': state.routed_unit,
            'tone': state.tone,
            'timestamp': state.created_at.isoformat()
        }
        await SUPABASE.insert_record('student_queries', record)

        # Send webhook
        if WEBHOOK_URL:
            payload = {
                "Student Name": state.student_name,
                "Academic Year": state.academic_year,
                "Student Query": clean_query,
                "unit": state.routed_unit,
                "tone": state.tone
            }
            async with httpx.AsyncClient() as client:
                try:
                    await client.post(WEBHOOK_URL, json=payload, timeout=10.0)
                except Exception:
                    # Do not crash; log in real app
                    pass

    def user_friendly_unit_name(self, unit_key: str) -> str:
        mapping = {
            'admission_scholarship': 'Admission/Scholarship Unit',
            'academic_support': 'Academic Support Unit',
            'student_welfare': 'Student Welfare Unit',
            'career_skill_development': 'Career/Skill Development Unit'
        }
        return mapping.get(unit_key, unit_key)
