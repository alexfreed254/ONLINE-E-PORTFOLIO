"""
Supabase client — uses the SERVICE ROLE key so the Flask backend
can bypass Row Level Security for all operations.
"""
import os
from supabase import create_client, Client

_client: Client | None = None

def get_db() -> Client:
    global _client
    if _client is None:
        url = os.getenv('SUPABASE_URL')
        key = os.getenv('SUPABASE_SERVICE_KEY')
        if not url or not key:
            raise RuntimeError(
                'SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in .env'
            )
        _client = create_client(url, key)
    return _client
