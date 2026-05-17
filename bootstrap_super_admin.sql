-- ============================================================
-- ONE-TIME: Create the first Super Administrator
-- Run this in Supabase → SQL Editor AFTER supabase_schema.sql
-- Default password: Admin@1234  (change immediately after login)
-- ============================================================

INSERT INTO users (email, password_hash, full_name, role, is_active)
VALUES (
    'superadmin@ttieportfolio.ac.ke',
    'scrypt:32768:8:1$qvQYsYQ4WnXc2Gud$a0da4d08aeca7dddee115d64f62a99571784c88622f1d32607f70fdfd660f4b4d3e75a4daec2f9a2ab1b51804df6208625bac575c5876bdf166cb200a26357ea',
    'Super Administrator',
    'super_admin',
    TRUE
)
ON CONFLICT (email) DO NOTHING;
