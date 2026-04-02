import sqlite3
import json
from datetime import datetime
from typing import List, Optional, Dict, Any
from .resilience import compute_item_resilience, UNSAFE_NO_BACKUP, UNSAFE_SINGLE_DOMAIN, OVER_REPLICATED_RESILIENT
from .placement import suggest_destinations
from .models import PlanType, PlanStatus, OperationType, OperationStatus

def create_plan(db: sqlite3.Connection, name: str, plan_type: PlanType, drive_id: Optional[int] = None, min_size_gb: float = 0, min_copies: int = 3) -> int:
    """
    Create a new resilience plan based on the library state.
    """
    cursor = db.cursor()
    
    # Insert plan header
    cursor.execute(
        "INSERT INTO plans (name, type, status) VALUES (?, ?, ?)",
        (name, plan_type.value, PlanStatus.DRAFT.value)
    )
    plan_id = cursor.lastrowid
    
    if plan_type == PlanType.PROTECTION:
        _populate_protection_plan(db, plan_id, min_size_gb)
    elif plan_type == PlanType.REDUCTION:
        _populate_reduction_plan(db, plan_id, min_copies)
    elif plan_type == PlanType.RETIREMENT:
        if drive_id is None:
            raise ValueError("drive_id is required for retirement plan")
        _populate_retirement_plan(db, plan_id, drive_id)
        
    db.commit()
    return plan_id

def _populate_protection_plan(db: sqlite3.Connection, plan_id: int, min_size_gb: float):
    """Plan protection for all unsafe items."""
    cursor = db.cursor()
    
    # 1. Get candidate drives for copies
    cursor.execute("""
        SELECT id, mount_path, volume_label, domain_id, health_status, free_space 
        FROM drives 
        WHERE health_status NOT IN ('degraded', 'avoid_for_new_copies')
    """)
    drives = [dict(row) for row in cursor.fetchall()]
    
    # 2. Get all items and their files
    items = _get_all_media_item_resilience_data(db)
    
    # 3. Filter for unsafe items
    bytes_threshold = min_size_gb * 1024 * 1024 * 1024
    
    for item_id, data in items.items():
        state = data['resilience_state']
        if state not in (UNSAFE_NO_BACKUP, UNSAFE_SINGLE_DOMAIN):
            continue
        
        if data['total_size_bytes'] < bytes_threshold:
            continue
            
        # Suggest one copy
        suggestions = suggest_destinations(data, drives)
        if suggestions:
            best = suggestions[0]
            # Choose a source file (any primary, or just the first one)
            source_file_id = data['files'][0]['id']
            
            cursor.execute("""
                INSERT INTO plan_items (plan_id, media_item_id, source_file_id, dest_drive_id, action, estimated_size)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (plan_id, item_id, source_file_id, best['drive_id'], OperationType.COPY.value, data['total_size_bytes']))

def _populate_reduction_plan(db: sqlite3.Connection, plan_id: int, min_copies: int):
    """Plan reduction for over-replicated items."""
    cursor = db.cursor()
    items = _get_all_media_item_resilience_data(db)
    
    for item_id, data in items.items():
        if data['copy_count'] <= min_copies:
            continue
            
        # We only consider reducing if it's already resilient/safe
        if data['resilience_state'] not in (OVER_REPLICATED_RESILIENT, "safe_two_domains"):
             continue
             
        # Suggest deleting a copy on an over-replicated domain if any, else any copy
        # For now, just suggest deleting the first copy NOT marked as primary
        files = data['files']
        removable = [f for f in files if not f.get('is_primary')]
        if not removable:
            removable = files # fallback
            
        target = removable[-1]
        
        cursor.execute("""
            INSERT INTO plan_items (plan_id, media_item_id, source_file_id, action, estimated_size)
            VALUES (?, ?, ?, ?, ?)
        """, (plan_id, item_id, target['id'], OperationType.DELETE.value, data['total_size_bytes']))

def _populate_retirement_plan(db: sqlite3.Connection, plan_id: int, drive_id: int):
    """Plan drive retirement for selected drive."""
    cursor = db.cursor()
    
    # 1. Get candidate drives (excluding the retiring drive)
    cursor.execute("""
        SELECT id, mount_path, volume_label, domain_id, health_status, free_space 
        FROM drives 
        WHERE id != ? AND health_status NOT IN ('degraded', 'avoid_for_new_copies')
    """, (drive_id,))
    drives = [dict(row) for row in cursor.fetchall()]

    # 2. Get all media items that have a copy on this drive
    items = _get_all_media_item_resilience_data(db)
    
    for item_id, data in items.items():
        on_retired_drive = [f for f in data['files'] if f['drive_id'] == drive_id]
        if not on_retired_drive:
            continue
            
        # VIRTUAL SIMULATION: What is the item's state WITHOUT the retiring drive?
        # We need to find a destination that replaces the lost resilience.
        virtual_files = [f for f in data['files'] if f['drive_id'] != drive_id]
        virtual_res = compute_item_resilience(virtual_files)
        
        # Prepare data for suggest_destinations reflecting the virtual "post-loss" state
        virtual_data = data.copy()
        virtual_data.update(virtual_res)
        # Update current drive/domain sets for the placement advisor
        virtual_data['current_drive_ids'] = {f['drive_id'] for f in virtual_files}
        virtual_data['current_domain_ids'] = {f['domain_id'] for f in virtual_files}
        
        suggestions = suggest_destinations(virtual_data, drives)
        if suggestions:
            best = suggestions[0]
            # Copy from the retiring drive (since it's still online for now) to the best destination
            cursor.execute("""
                INSERT INTO plan_items (plan_id, media_item_id, source_file_id, dest_drive_id, action, estimated_size)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (plan_id, item_id, on_retired_drive[0]['id'], best['drive_id'], OperationType.COPY.value, data['total_size_bytes']))
        
        # Always suggest deleting from the retired drive
        cursor.execute("""
            INSERT INTO plan_items (plan_id, media_item_id, source_file_id, action, estimated_size)
            VALUES (?, ?, ?, ?, ?)
        """, (plan_id, item_id, on_retired_drive[0]['id'], OperationType.DELETE.value, data['total_size_bytes']))

def _get_all_media_item_resilience_data(db: sqlite3.Connection) -> Dict[int, Dict]:
    """
    Helper to fetch all items and their resilience metadata efficiently.
    Returns { media_item_id: {resilience_state, total_size_bytes, files: [...]} }
    """
    cursor = db.cursor()
    # We JOIN media_items, media_item_files, files, and drives to get domain info
    cursor.execute("""
        SELECT 
            m.id as item_id, 
            m.title,
            m.status,
            f.id as file_id,
            f.size,
            d.id as drive_id,
            d.domain_id,
            d.health_status,
            mif.is_primary
        FROM media_items m
        JOIN media_item_files mif ON m.id = mif.media_item_id
        JOIN files f ON mif.file_id = f.id
        JOIN roots r ON f.root_id = r.id
        JOIN drives d ON r.drive_id = d.id
    """)
    
    rows = cursor.fetchall()
    items = {}
    
    for row in rows:
        iid = row['item_id']
        if iid not in items:
            items[iid] = {
                'id': iid,
                'title': row['title'],
                'status': row['status'],
                'files': [],
                'total_size_bytes': 0,
                'current_drive_ids': set(),
                'current_domain_ids': set(),
                'drive_healths': []
            }
        
        items[iid]['files'].append({
            'id': row['file_id'],
            'drive_id': row['drive_id'],
            'domain_id': row['domain_id'],
            'health_status': row['health_status'],
            'is_primary': bool(row['is_primary'])
        })
        items[iid]['total_size_bytes'] += (row['size'] or 0)
        items[iid]['current_drive_ids'].add(row['drive_id'])
        items[iid]['current_domain_ids'].add(row['domain_id'])
        items[iid]['drive_healths'].append(row['health_status'])
        
    # Now compute resilience for each
    for iid, data in items.items():
        res = compute_item_resilience(data['files'])
        data.update(res)
        
    return items

def get_plan(db: sqlite3.Connection, plan_id: int) -> Optional[Dict]:
    cursor = db.cursor()
    cursor.execute("SELECT * FROM plans WHERE id = ?", (plan_id,))
    row = cursor.fetchone()
    if not row:
        return None
        
    plan = dict(row)
    
    cursor.execute("""
        SELECT pi.*, m.title as media_item_title, f.path as source_path, d.mount_path as dest_drive_path, d.domain_id as dest_domain_id
        FROM plan_items pi
        JOIN media_items m ON pi.media_item_id = m.id
        LEFT JOIN files f ON pi.source_file_id = f.id
        LEFT JOIN drives d ON pi.dest_drive_id = d.id
        WHERE pi.plan_id = ?
    """, (plan_id,))
    items = [dict(r) for r in cursor.fetchall()]
    
    # Compute impact
    impact = _calculate_impact(db, plan, items)
    
    return {
        "plan": plan,
        "items": items,
        "impact": impact
    }

def _calculate_impact(db: sqlite3.Connection, planDict: dict, plan_items: list) -> dict:
    """Summarize how library metrics will change."""
    # 1. Get current baseline
    current_items = _get_all_media_item_resilience_data(db)
    
    # 2. Group plan actions by media_item_id
    actions_by_item = {} # {iid: [ {action, dest_domain_id, drive_id, etc} ]}
    for pi in plan_items:
        if not pi['is_included']:
            continue
        iid = pi['media_item_id']
        if iid not in actions_by_item:
            actions_by_item[iid] = []
        actions_by_item[iid].append(pi)
            
    # 3. Simulate new state
    before_counts = {}
    after_counts = {}
    
    for iid, baseline in current_items.items():
        state_before = baseline['resilience_state']
        before_counts[state_before] = before_counts.get(state_before, 0) + 1
        
        # Apply changes for this item
        item_actions = actions_by_item.get(iid, [])
        if not item_actions:
            after_counts[state_before] = after_counts.get(state_before, 0) + 1
            continue
            
        # Clone files list to simulate changes
        new_files = list(baseline['files'])
        for action in item_actions:
            if action['action'] == OperationType.COPY.value:
                # Add a virtual file
                new_files.append({
                    'drive_id': action['dest_drive_id'],
                    'domain_id': action['dest_domain_id'],
                    'health_status': 'healthy' 
                })
            elif action['action'] == OperationType.DELETE.value:
                # Remove the file with source_file_id
                new_files = [f for f in new_files if f['id'] != action['source_file_id']]
                
        new_res = compute_item_resilience(new_files)
        state_after = new_res['resilience_state']
        after_counts[state_after] = after_counts.get(state_after, 0) + 1
        
    return {
        "before": before_counts,
        "after": after_counts
    }

def toggle_item_inclusion(db: sqlite3.Connection, plan_item_id: int, included: bool):
    cursor = db.cursor()
    cursor.execute("UPDATE plan_items SET is_included = ? WHERE id = ?", (1 if included else 0, plan_item_id))
    db.commit()

def execute_plan(db: sqlite3.Connection, plan_id: int):
    """Convert planned items into real operations."""
    cursor = db.cursor()
    
    cursor.execute("SELECT * FROM plans WHERE id = ?", (plan_id,))
    plan = cursor.fetchone()
    if not plan or plan['status'] != PlanStatus.DRAFT.value:
        return
        
    cursor.execute("SELECT * FROM plan_items WHERE plan_id = ? AND is_included = 1", (plan_id,))
    items = cursor.fetchall()
    
    for item in items:
        if item['action'] == OperationType.COPY.value:
            cursor.execute("""
                INSERT INTO operations (type, status, source_file_id, dest_drive_id, total_size)
                VALUES (?, ?, ?, ?, ?)
            """, (OperationType.COPY.value, OperationStatus.PENDING.value, item['source_file_id'], item['dest_drive_id'], item['estimated_size']))
        elif item['action'] == OperationType.DELETE.value:
            cursor.execute("""
                INSERT INTO operations (type, status, source_file_id, total_size)
                VALUES (?, ?, ?, ?)
            """, (OperationType.DELETE.value, OperationStatus.PENDING.value, item['source_file_id'], item['estimated_size']))
            
    cursor.execute("UPDATE plans SET status = ?, executed_at = ? WHERE id = ?", 
                   (PlanStatus.EXECUTED.value, datetime.now().isoformat(), plan_id))
    db.commit()

def list_plans(db: sqlite3.Connection) -> List[Dict]:
    cursor = db.cursor()
    cursor.execute("""
        SELECT p.*, COUNT(pi.id) as item_count, SUM(pi.estimated_size) as total_size
        FROM plans p
        LEFT JOIN plan_items pi ON p.id = pi.plan_id
        GROUP BY p.id
        ORDER BY p.created_at DESC
    """)
    return [dict(r) for r in cursor.fetchall()]
