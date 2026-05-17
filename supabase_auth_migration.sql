-- Run once if you already created public.users before Supabase Auth integration.

ALTER TABLE users
  ADD COLUMN IF NOT EXISTS auth_user_id UUID UNIQUE;

ALTER TABLE users
  ALTER COLUMN password_hash DROP NOT NULL;

COMMENT ON COLUMN users.auth_user_id IS 'Links to auth.users.id for staff using Supabase Authentication';
