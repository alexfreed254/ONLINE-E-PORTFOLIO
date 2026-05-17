# ONLINE-E-PORTFOLIO

Online E-Portfolio Management System for **Thika Technical Training Institute** — Electrical Department.

Flask + Supabase app with role-based dashboards:

- **Super Admin** — users, departments, system logs
- **Department Admin** — courses, units, classes, trainers, trainees
- **Trainer** — review and approve/reject assessments
- **Trainee** — upload marked PDF scripts and linked photo/video evidence

## Setup

1. Copy `.env.example` to `.env` and set Supabase credentials.
2. Run `supabase_schema.sql` then `bootstrap_super_admin.sql` in Supabase SQL Editor.
3. Create storage buckets: `assessment-scripts`, `assessment-evidence` (public).
4. Install and run:

```bash
pip install -r requirements.txt
python run.py
```

## Deploy (Render)

See `render.yaml` and set environment variables in the Render dashboard (`SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `SECRET_KEY`, `FLASK_ENV=production`).

**Do not commit `.env` to Git.**
