"""Pydantic models for API request/response."""

from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional


# Enums
class ThrottleLevel(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    FAST = "fast"


class ScanState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


# Drive models
class DriveRegister(BaseModel):
    mount_path: str = Field(..., description="Mount path of the drive (e.g., C:\\ or /mnt/data)")


class DriveHealth(str, Enum):
    HEALTHY = "healthy"
    WARNING = "warning"
    DEGRADED = "degraded"
    AVOID = "avoid_for_new_copies"


class Drive(BaseModel):
    id: int
    mount_path: str
    volume_serial: Optional[str] = None
    volume_label: Optional[str] = None
    created_at: datetime
    free_space: Optional[int] = None
    total_space: Optional[int] = None
    domain_id: Optional[int] = None
    domain_name: Optional[str] = None
    health_status: str = "healthy"


class DriveList(BaseModel):
    drives: list[Drive]


# Failure Domain models
class FailureDomainCreate(BaseModel):
    name: str
    description: Optional[str] = None


class FailureDomain(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    created_at: datetime


class FailureDomainList(BaseModel):
    domains: list[FailureDomain]
    unassigned_drives: int = 0


# Root models
class RootCreate(BaseModel):
    drive_id: int
    path: str
    excluded: bool = False


class Root(BaseModel):
    id: int
    drive_id: int
    path: str
    excluded: bool
    created_at: datetime


class RootList(BaseModel):
    roots: list[Root]


# File models
class FileItem(BaseModel):
    id: int
    root_id: int
    path: str
    size: Optional[int] = None
    mtime: Optional[float] = None
    ext: Optional[str] = None
    last_seen: Optional[datetime] = None


class FileList(BaseModel):
    files: list[FileItem]
    total: int
    page: int
    page_size: int


class FileFilters(BaseModel):
    ext: Optional[str] = None
    min_size: Optional[int] = None
    max_size: Optional[int] = None
    path_contains: Optional[str] = None
    missing: Optional[bool] = None


# Scan models
class ScanRequest(BaseModel):
    drive_id: Optional[int] = None  # None = scan all
    throttle: ThrottleLevel = ThrottleLevel.NORMAL


class ScanStatus(BaseModel):
    state: ScanState
    current_root: Optional[str] = None
    files_scanned: int = 0
    files_total: Optional[int] = None
    files_new: int = 0
    files_updated: int = 0
    files_missing: int = 0
    started_at: Optional[datetime] = None
    eta_seconds: Optional[int] = None


class ScanControl(BaseModel):
    action: str = Field(..., pattern="^(pause|resume|cancel)$")


# Planning models
class PlanType(str, Enum):
    PROTECTION = "protection"
    REDUCTION = "reduction"
    RETIREMENT = "retirement"


class PlanStatus(str, Enum):
    DRAFT = "draft"
    EXECUTED = "executed"
    CANCELLED = "cancelled"


class OperationType(str, Enum):
    COPY = "copy"
    MOVE = "move"
    DELETE = "delete"


class OperationStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PlanItem(BaseModel):
    id: int
    plan_id: int
    media_item_id: int
    media_item_title: Optional[str] = None
    source_file_id: Optional[int] = None
    source_path: Optional[str] = None
    dest_drive_id: Optional[int] = None
    dest_drive_path: Optional[str] = None
    action: str  # copy, move, delete
    is_included: bool
    estimated_size: Optional[int] = None


class Plan(BaseModel):
    id: int
    name: str
    type: PlanType
    status: PlanStatus
    created_at: datetime
    executed_at: Optional[datetime] = None
    item_count: int = 0
    total_size: int = 0


class PlanSummary(BaseModel):
    plan: Plan
    items: list[PlanItem]
    impact: dict  # summarized drive/domain space changes


class CreatePlanRequest(BaseModel):
    name: str
    type: PlanType
    drive_id: Optional[int] = None  # for retirement
    min_size_gb: Optional[float] = None
    min_copies: Optional[int] = None
