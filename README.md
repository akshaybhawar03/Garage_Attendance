# Garage Attendance System — Backend API

Face-recognition attendance system for a single garage with 10-15 employees.
Built with **FastAPI + DeepFace (ArcFace) + MediaPipe + Neon PostgreSQL (pgvector)**.

---

## Project Structure

```
├── main.py                  # FastAPI entry point
├── schema.sql               # PostgreSQL DDL (run once on Neon)
├── requirements.txt
├── Dockerfile
├── .env.example
├── core/
│   ├── database.py          # asyncpg connection pool
│   ├── security.py          # JWT + bcrypt helpers
│   └── face_service.py      # ArcFace embeddings + MediaPipe liveness
├── routers/
│   ├── auth.py              # /api/auth/*
│   ├── owner.py             # /api/owner/*  (owner JWT)
│   └── kiosk.py             # /api/kiosk/*  (kiosk JWT)
├── models/
│   └── schemas.py           # Pydantic request / response models
└── utils/
    ├── cloudinary_helper.py  # Profile photo uploads
    └── firebase_helper.py    # FCM push notifications
```

---

## Prerequisites

| Tool       | Version |
|------------|---------|
| Python     | 3.11+   |
| PostgreSQL | Neon (pgvector enabled) |
| Cloudinary | Free account |

---

## 1 — Database Setup (Neon)

1. Create a Neon project at <https://neon.tech>.
2. Enable the **pgvector** extension (enabled by default on Neon).
3. Run `schema.sql` in the Neon SQL Editor to create all tables, indexes, functions, and seed data.

---

## 2 — Local Development

```bash
# Clone & enter directory
cd "Garadge Attendance"

# Create virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS / Linux

# Install dependencies
pip install -r requirements.txt

# Create .env from template
copy .env.example .env       # Windows
# cp .env.example .env       # macOS / Linux

# Fill in your real values in .env:
#   DATABASE_URL, JWT_SECRET, CLOUDINARY_*, etc.

# Run the server
uvicorn main:app --reload --port 8000
```

API docs available at: **http://localhost:8000/docs**

---

## 3 — Deploy to Render.com (Free Tier)

### 3.1 Push to GitHub

```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USER/garage-attendance.git
git push -u origin main
```

### 3.2 Create Render Web Service

1. Go to <https://render.com> → **New → Web Service**.
2. Connect your GitHub repo.
3. Configure:

| Setting         | Value                          |
|-----------------|--------------------------------|
| **Runtime**     | Docker                         |
| **Region**      | Choose nearest                 |
| **Instance**    | Free                           |

4. Add **Environment Variables** in the Render dashboard:

```
DATABASE_URL=postgresql+asyncpg://user:pass@host/db?ssl=require
JWT_SECRET=<generate a strong random string>
JWT_EXPIRE_MINUTES=1440
CLOUDINARY_CLOUD_NAME=your_cloud
CLOUDINARY_API_KEY=your_key
CLOUDINARY_API_SECRET=your_secret
```

5. Click **Deploy**. Render will build the Docker image and start the service.

### 3.3 Verify

```bash
curl https://your-service.onrender.com/health
# → {"status":"healthy"}
```

---

## API Quick Reference

### Auth (no token required)

| Method | Endpoint                | Body |
|--------|-------------------------|------|
| POST   | `/api/auth/owner-login` | `{company_code, email, password}` |
| POST   | `/api/auth/kiosk-verify`| `{company_code}` |

### Kiosk (kiosk JWT)

| Method | Endpoint          | Body |
|--------|-------------------|------|
| POST   | `/api/kiosk/scan` | `{image: "<base64>"}` |

### Owner (owner JWT)

| Method | Endpoint | Params |
|--------|----------|--------|
| GET    | `/api/owner/employees` | — |
| POST   | `/api/owner/employees/register` | `{name, phone, monthly_salary, joining_date, photos:[15]}` |
| PUT    | `/api/owner/employees/{id}` | `{name?, phone?, monthly_salary?, status?}` |
| DELETE | `/api/owner/employees/{id}` | — (soft delete) |
| GET    | `/api/owner/attendance/today` | — |
| GET    | `/api/owner/attendance/all` | `?month=&year=` |
| GET    | `/api/owner/attendance/employee/{id}` | `?month=&year=` |
| GET    | `/api/owner/salary/all` | `?month=&year=` |
| GET    | `/api/owner/salary/{id}` | `?month=&year=` |
| GET    | `/api/owner/reports/monthly` | `?month=&year=` |
| GET    | `/api/owner/settings` | — |
| PUT    | `/api/owner/settings` | `{work_start_time?, work_end_time?, ...}` |

---

## Roles & Access Control

| Role  | Token source | Access |
|-------|-------------|--------|
| **owner** | `/api/auth/owner-login` | All `/api/owner/*` endpoints |
| **kiosk** | `/api/auth/kiosk-verify` | Only `POST /api/kiosk/scan` |

Every database query filters by `company_id` embedded in the JWT — no cross-tenant data leaks.

---

## Face Recognition Flow

### Registration (owner)
1. Owner sends **15 base64 photos** (5 front, 5 left, 5 right).
2. Each photo → `DeepFace.represent(model_name='ArcFace')` → 512-dim vector.
3. Vectors averaged per group → **3 vectors stored** per employee in `face_vectors`.

### Daily Scan (kiosk)
1. **Liveness** — MediaPipe Face Mesh detects 468 landmarks; Eye Aspect Ratio must be > 0.20.
2. **Match** — ArcFace embedding compared via `find_matching_employee(threshold=0.65)` using pgvector cosine distance.
3. **Attendance** — First scan = check-in (present/late); second scan = check-out.

---

## Default Seed Credentials

| Field         | Value                |
|---------------|----------------------|
| Company code  | `GARAGE2024`         |
| Owner email   | `owner@garage.com`   |
| Owner password | *(set via bcrypt hash in schema.sql — update before production)* |
