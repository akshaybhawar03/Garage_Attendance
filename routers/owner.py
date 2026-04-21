"""
Owner-only endpoints — employees, attendance, salary, reports, settings.
Every query is scoped by company_id extracted from the JWT.
"""

import asyncpg
import calendar
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from core.database import get_db
from core.security import require_owner
from core.face_service import compute_registration_vectors
from utils.cloudinary_helper import upload_base64_image
from models.schemas import (
    EmployeeRegisterRequest,
    EmployeeUpdateRequest,
    EmployeeResponse,
    AttendanceResponse,
    SalaryResponse,
    MonthlyReportResponse,
    SettingsResponse,
    SettingsUpdateRequest,
)

router = APIRouter(prefix="/api/owner", tags=["Owner"])


# ━━━━━━━━━━━━━━━━━━━━━━━━━  EMPLOYEES  ━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/employees", response_model=list[EmployeeResponse])
async def list_employees(
    user: dict = Depends(require_owner),
    db: asyncpg.Connection = Depends(get_db),
):
    rows = await db.fetch(
        "SELECT id, name, phone, monthly_salary, joining_date, "
        "profile_photo_url, status, created_at "
        "FROM employees WHERE company_id = $1 AND status = 'active' "
        "ORDER BY name",
        user["company_id"],
    )
    return [dict(r) for r in rows]


@router.post("/employees/register", response_model=EmployeeResponse)
async def register_employee(
    body: EmployeeRegisterRequest,
    user: dict = Depends(require_owner),
    db: asyncpg.Connection = Depends(get_db),
):
    try:
        company_id = user["company_id"]

        # Upload first photo as profile pic
        import anyio
        print("DEBUG: Uploading profile photo to Cloudinary...")
        profile_url = await anyio.to_thread.run_sync(upload_base64_image, body.photos[0])
        print(f"DEBUG: Profile photo uploaded: {profile_url}")

        # Compute 3 averaged ArcFace vectors (front / left / right)
        print("DEBUG: Computing registration vectors...")
        vectors = await anyio.to_thread.run_sync(compute_registration_vectors, body.photos)
        print("DEBUG: Registration vectors computed successfully.")

        # Insert employee and vectors in a transaction
        async with db.transaction():
            # Insert employee
            row = await db.fetchrow(
                "INSERT INTO employees "
                "(company_id, name, phone, monthly_salary, joining_date, profile_photo_url) "
                "VALUES ($1, $2, $3, $4, $5, $6) "
                "RETURNING id, name, phone, monthly_salary, joining_date, "
                "profile_photo_url, status, created_at",
                company_id,
                body.name,
                body.phone,
                body.monthly_salary,
                body.joining_date,
                profile_url,
            )

            # Insert face vectors
            print(f"DEBUG: Saving {len(vectors)} face vectors for employee {row['id']}...")
            for angle, vec in vectors.items():
                # Pass the list/array directly, pgvector-python handles the conversion
                await db.execute(
                    "INSERT INTO face_vectors (employee_id, face_vector, angle_type) "
                    "VALUES ($1, $2, $3)",
                    row["id"],
                    vec,
                    angle,
                )
            print("DEBUG: All face vectors saved successfully.")

        return dict(row)
    except ValueError as ve:
        print(f"DEBUG: Validation error during registration: {str(ve)}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        import traceback
        error_msg = f"REGISTRATION ERROR: {str(e)}\n{traceback.format_exc()}"
        print(error_msg)
        with open("error.log", "a") as f:
            f.write(f"\n--- {datetime.now()} ---\n{error_msg}\n")
        raise HTTPException(status_code=500, detail=str(e))



@router.put("/employees/{emp_id}", response_model=EmployeeResponse)
async def update_employee(
    emp_id: int,
    body: EmployeeUpdateRequest,
    user: dict = Depends(require_owner),
    db: asyncpg.Connection = Depends(get_db),
):
    company_id = user["company_id"]

    # Build dynamic SET clause
    fields, values, idx = [], [], 1
    for col in ("name", "phone", "monthly_salary", "status"):
        val = getattr(body, col, None)
        if val is not None:
            fields.append(f"{col} = ${idx}")
            values.append(val)
            idx += 1

    if not fields:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No fields to update")

    values.extend([emp_id, company_id])
    sql = (
        f"UPDATE employees SET {', '.join(fields)} "
        f"WHERE id = ${idx} AND company_id = ${idx + 1} "
        "RETURNING id, name, phone, monthly_salary, joining_date, "
        "profile_photo_url, status, created_at"
    )
    row = await db.fetchrow(sql, *values)
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee not found")
    return dict(row)


@router.delete("/employees/{emp_id}")
async def delete_employee(
    emp_id: int,
    user: dict = Depends(require_owner),
    db: asyncpg.Connection = Depends(get_db),
):
    """Soft-delete: set status = 'inactive'."""
    result = await db.execute(
        "UPDATE employees SET status = 'inactive' "
        "WHERE id = $1 AND company_id = $2",
        emp_id,
        user["company_id"],
    )
    if result == "UPDATE 0":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee not found")
    return {"message": "Employee deactivated"}


# ━━━━━━━━━━━━━━━━━━━━━━━━  ATTENDANCE  ━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/attendance/today", response_model=list[AttendanceResponse])
async def attendance_today(
    user: dict = Depends(require_owner),
    db: asyncpg.Connection = Depends(get_db),
):
    today = date.today()
    rows = await db.fetch(
        "SELECT a.id, a.employee_id, e.name AS employee_name, "
        "a.attendance_date, a.check_in, a.check_out, a.status, a.match_score "
        "FROM attendance a JOIN employees e ON e.id = a.employee_id "
        "WHERE a.company_id = $1 AND a.attendance_date = $2 "
        "ORDER BY a.check_in",
        user["company_id"],
        today,
    )
    return [dict(r) for r in rows]


@router.get("/attendance/all", response_model=list[AttendanceResponse])
async def attendance_all(
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2020),
    user: dict = Depends(require_owner),
    db: asyncpg.Connection = Depends(get_db),
):
    start = date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    end = date(year, month, last_day)

    rows = await db.fetch(
        "SELECT a.id, a.employee_id, e.name AS employee_name, "
        "a.attendance_date, a.check_in, a.check_out, a.status, a.match_score "
        "FROM attendance a JOIN employees e ON e.id = a.employee_id "
        "WHERE a.company_id = $1 "
        "AND a.attendance_date BETWEEN $2 AND $3 "
        "ORDER BY a.attendance_date, e.name",
        user["company_id"],
        start,
        end,
    )
    return [dict(r) for r in rows]


@router.get(
    "/attendance/employee/{emp_id}",
    response_model=list[AttendanceResponse],
)
async def attendance_by_employee(
    emp_id: int,
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2020),
    user: dict = Depends(require_owner),
    db: asyncpg.Connection = Depends(get_db),
):
    start = date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    end = date(year, month, last_day)

    rows = await db.fetch(
        "SELECT a.id, a.employee_id, e.name AS employee_name, "
        "a.attendance_date, a.check_in, a.check_out, a.status, a.match_score "
        "FROM attendance a JOIN employees e ON e.id = a.employee_id "
        "WHERE a.employee_id = $1 AND a.company_id = $2 "
        "AND a.attendance_date BETWEEN $3 AND $4 "
        "ORDER BY a.attendance_date",
        emp_id,
        user["company_id"],
        start,
        end,
    )
    return [dict(r) for r in rows]


# ━━━━━━━━━━━━━━━━━━━━━━━━━  SALARY  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _count_working_days(year: int, month: int, days_per_week: int) -> int:
    """Count weekday working days in a month respecting days_per_week setting."""
    total = 0
    last_day = calendar.monthrange(year, month)[1]
    for d in range(1, last_day + 1):
        wd = date(year, month, d).weekday()  # 0=Mon … 6=Sun
        if days_per_week == 7:
            total += 1
        elif days_per_week == 6 and wd < 6:  # Mon-Sat
            total += 1
        elif days_per_week == 5 and wd < 5:  # Mon-Fri
            total += 1
    return total


async def _compute_salary(
    db: asyncpg.Connection,
    emp: dict,
    month: int,
    year: int,
    company_id: int,
) -> dict:
    """Build salary dict for one employee × one month."""
    settings = await db.fetchrow(
        "SELECT working_days_per_week FROM settings WHERE company_id = $1",
        company_id,
    )
    days_per_week = settings["working_days_per_week"] if settings else 6

    working_days = _count_working_days(year, month, days_per_week)

    start = date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    end = date(year, month, last_day)

    present = await db.fetchval(
        "SELECT COUNT(*) FROM attendance "
        "WHERE employee_id = $1 AND company_id = $2 "
        "AND attendance_date BETWEEN $3 AND $4 "
        "AND status IN ('present', 'late')",
        emp["id"],
        company_id,
        start,
        end,
    )
    late = await db.fetchval(
        "SELECT COUNT(*) FROM attendance "
        "WHERE employee_id = $1 AND company_id = $2 "
        "AND attendance_date BETWEEN $3 AND $4 "
        "AND status = 'late'",
        emp["id"],
        company_id,
        start,
        end,
    )

    present_days = int(present or 0)
    late_days = int(late or 0)
    absent_days = max(working_days - present_days, 0)

    monthly_salary = float(emp["monthly_salary"])
    per_day = round(monthly_salary / working_days, 2) if working_days else 0
    deduction = round(absent_days * per_day, 2)
    net_pay = round(monthly_salary - deduction, 2)

    return {
        "employee_id": emp["id"],
        "employee_name": emp["name"],
        "month": month,
        "year": year,
        "working_days": working_days,
        "present_days": present_days,
        "late_days": late_days,
        "absent_days": absent_days,
        "monthly_salary": monthly_salary,
        "per_day_salary": per_day,
        "deduction_amount": deduction,
        "net_pay": net_pay,
    }


@router.get("/salary/all", response_model=list[SalaryResponse])
async def salary_all(
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2020),
    user: dict = Depends(require_owner),
    db: asyncpg.Connection = Depends(get_db),
):
    company_id = user["company_id"]
    employees = await db.fetch(
        "SELECT id, name, monthly_salary FROM employees "
        "WHERE company_id = $1 AND status = 'active' ORDER BY name",
        company_id,
    )
    results = []
    for emp in employees:
        results.append(
            await _compute_salary(db, dict(emp), month, year, company_id)
        )
    return results


@router.get("/salary/{emp_id}", response_model=SalaryResponse)
async def salary_employee(
    emp_id: int,
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2020),
    user: dict = Depends(require_owner),
    db: asyncpg.Connection = Depends(get_db),
):
    company_id = user["company_id"]
    emp = await db.fetchrow(
        "SELECT id, name, monthly_salary FROM employees "
        "WHERE id = $1 AND company_id = $2",
        emp_id,
        company_id,
    )
    if not emp:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee not found")
    return await _compute_salary(db, dict(emp), month, year, company_id)


# ━━━━━━━━━━━━━━━━━━━━━━━━  MONTHLY REPORT  ━━━━━━━━━━━━━━━━━━━━━

@router.get("/reports/monthly", response_model=MonthlyReportResponse)
async def monthly_report(
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2020),
    user: dict = Depends(require_owner),
    db: asyncpg.Connection = Depends(get_db),
):
    company_id = user["company_id"]
    employees = await db.fetch(
        "SELECT id, name, monthly_salary FROM employees "
        "WHERE company_id = $1 AND status = 'active'",
        company_id,
    )

    salary_list = []
    total_present = 0
    total_late = 0
    total_absent = 0

    for emp in employees:
        s = await _compute_salary(db, dict(emp), month, year, company_id)
        salary_list.append(s)
        total_present += s["present_days"]
        total_late += s["late_days"]
        total_absent += s["absent_days"]

    total_emp = len(employees)
    settings = await db.fetchrow(
        "SELECT working_days_per_week FROM settings WHERE company_id = $1",
        company_id,
    )
    days_per_week = settings["working_days_per_week"] if settings else 6
    working_days = _count_working_days(year, month, days_per_week)
    possible = total_emp * working_days
    rate = round((total_present / possible) * 100, 2) if possible else 0.0

    return MonthlyReportResponse(
        total_employees=total_emp,
        total_present=total_present,
        total_absent=total_absent,
        total_late=total_late,
        attendance_rate=rate,
        employees=salary_list,
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━  SETTINGS  ━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/settings", response_model=SettingsResponse)
async def get_settings(
    user: dict = Depends(require_owner),
    db: asyncpg.Connection = Depends(get_db),
):
    row = await db.fetchrow(
        "SELECT work_start_time, work_end_time, "
        "late_threshold_minutes, working_days_per_week "
        "FROM settings WHERE company_id = $1",
        user["company_id"],
    )
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Settings not found")
    return SettingsResponse(
        work_start_time=str(row["work_start_time"]),
        work_end_time=str(row["work_end_time"]),
        late_threshold_minutes=row["late_threshold_minutes"],
        working_days_per_week=row["working_days_per_week"],
    )


@router.put("/settings", response_model=SettingsResponse)
async def update_settings(
    body: SettingsUpdateRequest,
    user: dict = Depends(require_owner),
    db: asyncpg.Connection = Depends(get_db),
):
    company_id = user["company_id"]

    fields, values, idx = [], [], 1
    for col in (
        "work_start_time",
        "work_end_time",
        "late_threshold_minutes",
        "working_days_per_week",
    ):
        val = getattr(body, col, None)
        if val is not None:
            fields.append(f"{col} = ${idx}")
            values.append(val)
            idx += 1

    if not fields:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No fields to update")

    values.append(company_id)
    sql = (
        f"UPDATE settings SET {', '.join(fields)} "
        f"WHERE company_id = ${idx} "
        "RETURNING work_start_time, work_end_time, "
        "late_threshold_minutes, working_days_per_week"
    )
    row = await db.fetchrow(sql, *values)
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Settings not found")
    return SettingsResponse(
        work_start_time=str(row["work_start_time"]),
        work_end_time=str(row["work_end_time"]),
        late_threshold_minutes=row["late_threshold_minutes"],
        working_days_per_week=row["working_days_per_week"],
    )
