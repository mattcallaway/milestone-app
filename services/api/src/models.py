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


class Drive(BaseModel):
    id: int
    mount_path: str
    volume_serial: Optional[str] = None
    volume_label: Optional[str] = None
    created_at: datetime
    free_space: Optional[int] = None
    total_space: Optional[int] = None


class DriveList(BaseModel):
    drives: list[Drive]


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
    signature_stub: Optional[str] = None


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
