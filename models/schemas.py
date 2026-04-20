from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime


# ──── Auth ────────────────────────────────────────────────────────
class OwnerLoginRequest(BaseModel):
    company_code: str
    email: str
    password: str


class OwnerLoginResponse(BaseModel):
    token: str
    role: str = "owner"
    name: str


class KioskVerifyRequest(BaseModel):
    company_code: str


class KioskVerifyResponse(BaseModel):
    token: str
    role: str = "kiosk"
    company_id: int


# ──── Employee ────────────────────────────────────────────────────
class EmployeeRegisterRequest(BaseModel):
    name: str
    phone: Optional[str] = None
    monthly_salary: float
    joining_date: date
    photos: List[str]  # 15 base64 strings (legacy)


class EmployeeCreateRequest(BaseModel):
    """Step 1: Create employee without photos."""
    name: str
    phone: Optional[str] = None
    monthly_salary: float
    joining_date: date


class EmployeeCreateResponse(BaseModel):
    employee_id: int
    name: str


class FacePhotoUploadRequest(BaseModel):
    """Step 2: Upload one photo at a time."""
    photo: str  # single base64 string
    index: int  # 0-14


class FacePhotoUploadResponse(BaseModel):
    success: bool
    received: int


class ProcessFaceVectorsResponse(BaseModel):
    """Step 3: Process all uploaded photos into vectors."""
    success: bool
    vectors_saved: int


class EmployeeUpdateRequest(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    monthly_salary: Optional[float] = None
    status: Optional[str] = None


class EmployeeResponse(BaseModel):
    id: int
    name: str
    phone: Optional[str] = None
    monthly_salary: float
    joining_date: date
    profile_photo_url: Optional[str] = None
    status: str
    created_at: datetime


# ──── Kiosk scan ──────────────────────────────────────────────────
class KioskScanRequest(BaseModel):
    image: str  # base64


class KioskScanResponse(BaseModel):
    success: bool
    employee_name: Optional[str] = None
    profile_photo_url: Optional[str] = None
    action: Optional[str] = None
    time: Optional[str] = None
    match_score: Optional[float] = None
    reason: Optional[str] = None


# ──── Attendance ──────────────────────────────────────────────────
class AttendanceResponse(BaseModel):
    id: int
    employee_id: int
    employee_name: Optional[str] = None
    attendance_date: date
    check_in: Optional[datetime] = None
    check_out: Optional[datetime] = None
    status: str
    match_score: Optional[float] = None


# ──── Salary ──────────────────────────────────────────────────────
class SalaryResponse(BaseModel):
    employee_id: int
    employee_name: Optional[str] = None
    month: int
    year: int
    working_days: int
    present_days: int
    late_days: int
    absent_days: int
    monthly_salary: float
    per_day_salary: float
    deduction_amount: float
    net_pay: float


# ──── Settings ────────────────────────────────────────────────────
class SettingsResponse(BaseModel):
    work_start_time: str
    work_end_time: str
    late_threshold_minutes: int
    working_days_per_week: int


class SettingsUpdateRequest(BaseModel):
    work_start_time: Optional[str] = None
    work_end_time: Optional[str] = None
    late_threshold_minutes: Optional[int] = None
    working_days_per_week: Optional[int] = None


# ──── Monthly report ─────────────────────────────────────────────
class MonthlyReportResponse(BaseModel):
    total_employees: int
    total_present: int
    total_absent: int
    total_late: int
    attendance_rate: float
    employees: List[SalaryResponse]
