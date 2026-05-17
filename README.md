# ONLINE E-PORTFOLIO

**Thika Technical Training Institute — Online E-Portfolio Management System**

A Flask + Supabase web application for managing assessment submissions, trainer reviews, and departmental oversight across all courses and classes.

---

## Roles

| Role | Login | Access |
|------|-------|--------|
| Super Admin | Email + Password | Full system — users, departments, logs, all assessments |
| Dept Admin | Email + Password | Courses, units, classes, trainers, trainees for their department |
| Trainer | Email + Password | Review/approve/reject assessments for assigned units only |
| Trainee | Admission No + Password | Upload PDF scripts, attach photo/video evidence |

---

## Features

- Dual-tab login — staff (email) vs trainee (admission number)
- Trainee uploads scanned PDF assessment scripts
- Each PDF is linked to a class, unit, term, cycle, year and assessment type
- Trainees attach photo/video evidence to each assessment
- Trainers approve or reject — trainee name appended to filename on review
- Trainers restricted to their assigned units only
- Dept Admin assigns units to trainers
- Super Admin manages all users, departments, and views system logs
- CSV report download per unit
- Supabase Storage for all files (PDFs + media)

---

## Tech Stack

- **Backend:** Python 3.11 / Flask 3
- **Database & Storage:** Supabase (PostgreSQL + Storage)
- **Auth:** Flask-Login with Werkzeug password hashing
- **Frontend:** Tailwind CSS (CDN) + Font Awesome

---

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/alexfreed254/ONLINE-E-PORTFOLIO.git
cd ONLINE-E-PORTFOLIO
```

### 2. Create a virtual environment and install dependencies

```bash
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

### 3. Configure environment variables

Copy `.env.example` to `.env` and fill in your Supabase credentials:

```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=your-service-role-key
SECRET_KEY=your-random-flask-secret
FLASK_ENV=development
```

### 4. Set up the database

Run `supabase_schema.sql` in your Supabase SQL Editor.

Then create the two storage buckets in Supabase (set both to **public**):
- `assessment-scripts`
- `assessment-evidence`

### 5. Create the first Super Admin

In the Supabase Table Editor, insert a row into the `users` table:

| Field | Value |
|-------|-------|
| email | your@email.com |
| full_name | Super Administrator |
| role | super_admin |
| password_hash | *(generate with `python -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('YourPassword'))"`)* |
| is_active | true |

### 6. Run the app

```bash
python run.py
```

Open `http://localhost:5000` and log in with the super admin credentials.

---

## Project Structure

```
ONLINE-E-PORTFOLIO/
├── app/
│   ├── blueprints/
│   │   ├── auth.py          # Login / logout / change password
│   │   ├── super_admin.py   # Super admin routes
│   │   ├── dept_admin.py    # Dept admin routes
│   │   ├── trainer.py       # Trainer routes
│   │   └── trainee.py       # Trainee routes
│   ├── __init__.py          # App factory
│   ├── db.py                # Supabase client
│   ├── models.py            # Flask-Login User model
│   └── utils.py             # Helpers (storage, logging, CSV)
├── templates/
│   ├── base.html
│   ├── auth/
│   ├── super_admin/
│   ├── dept_admin/
│   ├── trainer/
│   └── trainee/
├── .env.example
├── requirements.txt
├── run.py
└── supabase_schema.sql
```

---

## License

For internal use at Thika Technical Training Institute.
