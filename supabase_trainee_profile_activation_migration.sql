-- Add trainee activation and passport profile fields.
-- Run this once in the Supabase SQL Editor for existing deployments.

ALTER TABLE users
ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN DEFAULT FALSE;

ALTER TABLE users
ADD COLUMN IF NOT EXISTS passport_file_path TEXT;

ALTER TABLE users
ADD COLUMN IF NOT EXISTS passport_file_name TEXT;

ALTER TABLE users
ADD COLUMN IF NOT EXISTS mobile_number TEXT;

-- Optional policy for newly preloaded trainees:
-- Department admins should create/import trainees with password_hash = NULL.
-- Trainees receive a temporary password only after self-verifying with admission number + full name.
