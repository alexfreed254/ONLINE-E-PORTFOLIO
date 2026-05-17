-- ============================================================
-- Link Super Admin after creating them in Supabase Auth
-- ============================================================
-- STEP 1: Supabase Dashboard → Authentication → Users → Add user
--         Email:    superadmin@ttieportfolio.ac.ke  (your choice)
--         Password: your secure password
--         ✓ Auto Confirm User
--
-- STEP 2: Run this SQL (change email/name if needed)

INSERT INTO public.users (email, full_name, role, auth_user_id, password_hash, is_active)
SELECT
  au.email,
  'Super Administrator',
  'super_admin',
  au.id,
  '',
  TRUE
FROM auth.users au
WHERE lower(au.email) = lower('superadmin@ttieportfolio.ac.ke')
ON CONFLICT (email) DO UPDATE SET
  auth_user_id = EXCLUDED.auth_user_id,
  role         = 'super_admin',
  full_name    = EXCLUDED.full_name,
  password_hash = '',
  is_active    = TRUE;
