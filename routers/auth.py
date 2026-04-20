"""
POST /api/auth/owner-login
POST /api/auth/kiosk-verify
"""

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status

from core.database import get_db
from core.security import verify_password, create_token
from models.schemas import (
    OwnerLoginRequest,
    OwnerLoginResponse,
    KioskVerifyRequest,
    KioskVerifyResponse,
)

router = APIRouter(prefix="/api/auth", tags=["Auth"])


@router.post("/owner-login", response_model=OwnerLoginResponse)
async def owner_login(
    body: OwnerLoginRequest,
    db: asyncpg.Connection = Depends(get_db),
):
    # Verify company
    company = await db.fetchrow(
        "SELECT id FROM companies WHERE company_code = $1",
        body.company_code,
    )
    if not company:
        print(f"DEBUG: Company not found for code: {body.company_code}")
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Invalid company code"
        )

    # Verify admin credentials
    admin = await db.fetchrow(
        "SELECT id, name, password_hash FROM admins "
        "WHERE email = $1 AND company_id = $2",
        body.email,
        company["id"],
    )
    
    if not admin:
        print(f"DEBUG: Admin not found for email: {body.email}")
    elif not verify_password(body.password, admin["password_hash"]):
        print(f"DEBUG: Password verification failed for admin: {body.email}")

    if not admin or not verify_password(body.password, admin["password_hash"]):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Invalid credentials"
        )

    token = create_token(
        {
            "sub": str(admin["id"]),
            "role": "owner",
            "company_id": company["id"],
            "name": admin["name"],
        }
    )
    return OwnerLoginResponse(token=token, name=admin["name"])


@router.post("/kiosk-verify", response_model=KioskVerifyResponse)
async def kiosk_verify(
    body: KioskVerifyRequest,
    db: asyncpg.Connection = Depends(get_db),
):
    company = await db.fetchrow(
        "SELECT id FROM companies WHERE company_code = $1",
        body.company_code,
    )
    if not company:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Invalid company code"
        )

    token = create_token(
        {
            "sub": "kiosk",
            "role": "kiosk",
            "company_id": company["id"],
        }
    )
    return KioskVerifyResponse(token=token, company_id=company["id"])
