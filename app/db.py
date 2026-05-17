"""
Supabase clients:
- get_db()        — service role (backend CRUD, admin auth API)
- get_auth_client() — anon key (staff sign-in with password)
"""
import os
from supabase import create_client, Client

_db_client: Client | None = None
_auth_client: Client | None = None


def get_db() -> Client:
    global _db_client
    if _db_client is None:
        url = os.getenv('SUPABASE_URL')
        key = os.getenv('SUPABASE_SERVICE_KEY')
        if not url or not key:
            raise RuntimeError(
                'SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in .env'
            )
        _db_client = create_client(url, key)
    return _db_client


def get_auth_client() -> Client:
    """Anon client for Supabase Auth sign-in (staff email + password)."""
    global _auth_client
    if _auth_client is None:
        url = os.getenv('SUPABASE_URL')
        key = os.getenv('SUPABASE_KEY') or os.getenv('SUPABASE_ANON_KEY')
        if not url or not key:
            raise RuntimeError(
                'SUPABASE_URL and SUPABASE_KEY (anon) must be set in .env'
            )
        _auth_client = create_client(url, key)
    return _auth_client
