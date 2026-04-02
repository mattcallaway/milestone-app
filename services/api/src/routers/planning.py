from fastapi import APIRouter, Depends, HTTPException, Query
import sqlite3
from typing import List, Optional
from ..database import get_db
from ..models import CreatePlanRequest, Plan, PlanSummary, PlanItem
from .. import planning

router = APIRouter(prefix="/planning", tags=["planning"])

@router.get("/plans", response_model=List[Plan])
async def list_plans(db: sqlite3.Connection = Depends(get_db)):
    return planning.list_plans(db)

@router.post("/plans", response_model=int)
async def create_plan(req: CreatePlanRequest, db: sqlite3.Connection = Depends(get_db)):
    try:
        return planning.create_plan(
            db, 
            req.name, 
            req.type, 
            drive_id=req.drive_id, 
            min_size_gb=req.min_size_gb or 0,
            min_copies=req.min_copies or 3
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/plans/{plan_id}", response_model=PlanSummary)
async def get_plan(plan_id: int, db: sqlite3.Connection = Depends(get_db)):
    p = planning.get_plan(db, plan_id)
    if not p:
        raise HTTPException(status_code=404, detail="Plan not found")
    return p

@router.patch("/items/{plan_item_id}/inclusion")
async def toggle_item_inclusion(plan_item_id: int, included: bool, db: sqlite3.Connection = Depends(get_db)):
    planning.toggle_item_inclusion(db, plan_item_id, included)
    return {"status": "ok"}

@router.post("/plans/{plan_id}/execute")
async def execute_plan(plan_id: int, db: sqlite3.Connection = Depends(get_db)):
    planning.execute_plan(db, plan_id)
    return {"status": "ok"}
