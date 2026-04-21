"""
POST /api/kiosk/scan
Liveness → ArcFace match → attendance check-in / check-out.
"""

import asyncpg
from datetime import datetime, date, timezone, time, timedelta

from fastapi import APIRouter, Depends, HTTPException

from core.database import get_db
from core.security import require_kiosk
from core.face_service import decode_base64_image, check_liveness, get_embedding
from models.schemas import KioskScanRequest, KioskScanResponse

router = APIRouter(prefix="/api/kiosk", tags=["Kiosk"])


@router.post("/scan", response_model=KioskScanResponse)
async def scan_face(
    body: KioskScanRequest,
    user: dict = Depends(require_kiosk),
    db: asyncpg.Connection = Depends(get_db),
):
    company_id: int = user["company_id"]
    now = datetime.now(timezone.utc)
    today = date.today()

    # ── Step 1: Liveness ──────────────────────────────────────────
    import anyio
    import gc
    import cv2
    try:
        image = await anyio.to_thread.run_sync(decode_base64_image, body.image)
        # Resize to save memory
        image = cv2.resize(image, (400, 400))
    except ValueError:
        return KioskScanResponse(success=False, reason="invalid_image")

    gc.collect()
    if not await anyio.to_thread.run_sync(check_liveness, image):
        return KioskScanResponse(success=False, reason="liveness_failed")

    # ── Step 2: ArcFace embedding → DB match ──────────────────────
    try:
        print("DEBUG: Extracting embedding from scan image...")
        gc.collect()
        embedding = await anyio.to_thread.run_sync(get_embedding, image)
        print("DEBUG: Embedding extracted successfully.")
    except ValueError:
        print("DEBUG: No face detected in scan image.")
        return KioskScanResponse(success=False, reason="no_face_detected")
    finally:
        del image
        gc.collect()

    print(f"DEBUG: Vector length: {len(embedding)}")
    if len(embedding) != 512:
        print(f"ERROR: Vector length mismatch! Expected 512, got {len(embedding)}")
        return KioskScanResponse(success=False, reason="ai_error")

    print(f"DEBUG: Searching for match in company {company_id}...")

    try:
        # Pass embedding list directly, pgvector-python handles it
        match = await db.fetchrow(
            "SELECT * FROM find_matching_employee($1, $2, $3)",
            embedding,
            0.80, # Increased from 0.75 for maximum security (MediaPipe ensures high quality)
            company_id,
        )
    except Exception as sql_e:
        print(f"SQL ERROR during matching: {str(sql_e)}")
        return KioskScanResponse(success=False, reason="db_error")

    if not match:
        print("DEBUG: No match found (threshold 0.65).")
        return KioskScanResponse(success=False, reason="no_match")

    emp_id: int = match["employee_id"]
    emp_name: str = match["employee_name"]
    similarity: float = round(float(match["similarity"]), 4)
    print(f"DEBUG: Match found! Employee: {emp_name}, Score: {similarity}")

    # Fetch profile photo
    emp = await db.fetchrow(
        "SELECT profile_photo_url FROM employees WHERE id = $1", emp_id
    )
    photo_url = emp["profile_photo_url"] if emp else None

    # ── Step 3: Attendance logic ──────────────────────────────────
    try:
        now_naive = datetime.now() # Naive local time for DB
        print(f"DEBUG: Checking existing attendance for employee {emp_id} today...")
        existing = await db.fetchrow(
            "SELECT id, check_in, check_out FROM attendance "
            "WHERE employee_id = $1 AND attendance_date = $2",
            emp_id,
            today,
        )

        if existing is None:
            print("DEBUG: No existing attendance record. Performing Check-in...")
            # First scan → check_in
            settings = await db.fetchrow(
                "SELECT work_start_time, late_threshold_minutes "
                "FROM settings WHERE company_id = $1",
                company_id,
            )
            work_start = settings["work_start_time"] if settings else time(9, 0)
            late_mins = settings["late_threshold_minutes"] if settings else 15

            # Determine present / late
            deadline = (
                datetime.combine(today, work_start)
                + timedelta(minutes=late_mins)
            )
            current_time_today = datetime.combine(today, now_naive.time())
            att_status = (
                "present" if current_time_today <= deadline else "late"
            )

            await db.execute(
                "INSERT INTO attendance "
                "(employee_id, company_id, attendance_date, check_in, "
                " status, match_score) "
                "VALUES ($1, $2, $3, $4, $5, $6)",
                emp_id,
                company_id,
                today,
                now_naive,
                att_status,
                similarity,
            )
            print(f"DEBUG: Check-in recorded with status: {att_status}")

            return KioskScanResponse(
                success=True,
                employee_name=emp_name,
                profile_photo_url=photo_url,
                action="check_in",
                time=now_naive.isoformat(),
                match_score=similarity,
                reason=att_status,
            )

        elif existing["check_out"] is None:
            print("DEBUG: Employee already checked in. Performing Check-out...")
            # Second scan → check_out
            await db.execute(
                "UPDATE attendance SET check_out = $1 WHERE id = $2",
                now_naive,
                existing["id"],
            )
            print("DEBUG: Check-out recorded.")
            return KioskScanResponse(
                success=True,
                employee_name=emp_name,
                profile_photo_url=photo_url,
                action="check_out",
                time=now_naive.isoformat(),
                match_score=similarity,
                reason="checked_out",
            )

        else:
            print("DEBUG: Employee already checked in and out today.")
            # Already checked in and out today
            return KioskScanResponse(
                success=True,
                employee_name=emp_name,
                profile_photo_url=photo_url,
                action="check_out",
                time=existing["check_out"].isoformat(),
                match_score=similarity,
                reason="already_completed",
            )
    except Exception as e:
        print(f"CRITICAL ERROR in Attendance Logic: {str(e)}")
        import traceback
        traceback.print_exc()
        return KioskScanResponse(success=False, reason="db_error")
