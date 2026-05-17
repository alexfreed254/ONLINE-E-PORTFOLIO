-- ============================================================
-- SUPER ADMIN SETUP (choose ONE method)
-- ============================================================

-- ── METHOD A (recommended): Supabase Authentication → Add user ──
-- 1. Dashboard → Authentication → Users → Add user
-- 2. Email + password, tick "Auto Confirm User"
-- 3. Run: link_super_admin_from_auth.sql

-- ── METHOD B: SQL only (legacy, no Supabase Auth) ──
-- Uses werkzeug password hash in public.users only.
-- Default password: Admin@1234

/*
INSERT INTO users (email, password_hash, full_name, role, is_active)
VALUES (
    'superadmin@ttieportfolio.ac.ke',
    'scrypt:32768:8:1$qvQYsYQ4WnXc2Gud$a0da4d08aeca7dddee115d64f62a99571784c88622f1d32607f70fdfd660f4b4d3e75a4daec2f9a2ab1b51804df6208625bac575c5876bdf166cb200a26357ea',
    'Super Administrator',
    'super_admin',
    TRUE
)
ON CONFLICT (email) DO NOTHING;
*/
