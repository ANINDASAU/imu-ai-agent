import os
import asyncio
from dotenv import load_dotenv
from supabase import create_client, Client

# Load .env to ensure SUPABASE_* and WEBHOOK_URL are available when running locally
load_dotenv()

SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')

class SupabaseClient:
    def __init__(self):
        self.url = SUPABASE_URL
        self.key = SUPABASE_KEY
        if not self.url or not self.key:
            # Client not configured; remain None and log (print for demo)
            self.client = None
            print("[supabase] SUPABASE_URL or SUPABASE_KEY not found in environment; supabase inserts disabled.")
        else:
            self.client: Client = create_client(self.url, self.key)

    async def insert_record(self, table: str, record: dict):
        if not self.client:
            # In dev, do nothing or log
            print(f"[supabase] Skipping insert (no client): {record}")
            return
        # Supabase client is synchronous; run in thread
        loop = asyncio.get_running_loop()
        def _insert():
            res = self.client.table(table).insert(record).execute()
            return res
        try:
            result = await loop.run_in_executor(None, _insert)
            print(f"[supabase] Inserted record into {table}: {record}")
            return result
        except Exception as e:
            print(f"[supabase] Insert failed: {e}")
            return None
