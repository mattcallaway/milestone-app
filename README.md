# Milestone

> A local-first media library manager for collectors who store large video archives across multiple physical drives. Milestone tells you what you have, where it lives, whether it's backed up, and helps you safely clean up the excess — without any cloud service, subscription, or internet connection.

---

## Table of Contents

- [What is Milestone?](#what-is-milestone)
- [The Workflow](#the-workflow)
- [Technical Map](#technical-map)
  - [System Architecture](#system-architecture)
  - [Backend Services](#backend-services)
  - [Database Schema](#database-schema)
  - [Frontend & Navigation](#frontend--navigation)
  - [How the Pieces Connect](#how-the-pieces-connect)
- [Prerequisites](#prerequisites)
- [Getting Started](#getting-started)
- [Using Milestone](#using-milestone)
  - [1. Register Your Drives](#1-register-your-drives)
  - [2. Add Scan Roots](#2-add-scan-roots)
  - [3. Scan Your Library](#3-scan-your-library)
  - [4. Process & Group Files into Media Items](#4-process--group-files-into-media-items)
  - [5. Hash for Deduplication & Verification](#5-hash-for-deduplication--verification)
  - [6. Browse Your Library](#6-browse-your-library)
  - [7. Create Backup Copies](#7-create-backup-copies)
  - [8. Clean Up Excess Copies](#8-clean-up-excess-copies)
  - [9. Export Reports](#9-export-reports)
- [Configuration](#configuration)
- [API Reference](#api-reference)
- [Build & Packaging](#build--packaging)
- [Linting & Testing](#linting--testing)
- [Safety Design](#safety-design)
- [License](#license)

---

## What is Milestone?

If you collect movies and TV shows on physical drives, you likely have the same problems:

- **You don't know what you have.** Files spread across 5–10 drives over years, no single view of the whole library.
- **You don't know what's backed up.** Is that 4K rip on just one drive, or do you have it on two?
- **You have too many copies of some things.** Drive space gets wasted on triple-copies of content you'll never re-watch.
- **Deleting files is scary.** What if you delete the wrong one? What if it was the only copy?

Milestone solves all of this. It:

1. **Scans** all your drives and indexes every file
2. **Groups** files into logical media items (movie, TV episode) by filename parsing
3. **Fingerprints** files with SHA-256 hashes for identity verification
4. **Shows** you your copy distribution: what has 0 copies, 1, 2, 3+
5. **Copies** files to other drives through a managed operations queue
6. **Cleans up** excess copies through a reversible quarantine workflow

Everything runs locally. No accounts. No cloud. No data leaves your machine.

---

## The Workflow

The typical Milestone session follows a natural progression:

```
Register drives  →  Add scan roots  →  Run scan  →  Process into items
                                                            ↓
Export reports   ←  Clean up excess  ←  Copy at-risk  ←  Browse & review
```

**First time setup** (takes ~10 minutes):
1. Open Milestone → go to **Drives** → register each drive by its mount path
2. Go to **Roots** → add the folders you want to scan on each drive
3. Go to **Scan** → start a scan; watch it find all your files in real time
4. Back on **Dashboard** → click **Process Files** to group files into movies and episodes
5. Click **Start Hashing** to fingerprint everything (runs in the background)

**Day-to-day use**:
- Check **Dashboard** for your copy distribution at a glance
- See which items have only 1 copy (at risk) and schedule backup copies
- Go to **Cleanup** when copy counts get too high and reclaim drive space
- Re-scan after moving files to keep the index current

---

## Technical Map

This section explains exactly how all the pieces fit together — the architecture, each service, the database, and how data flows between them.

### System Architecture

```
╔═══════════════════════════════════════════════════════════╗
║                    ELECTRON SHELL                         ║
║  ┌─────────────────────────────────────────────────────┐  ║
║  │              REACT RENDERER (Vite)                  │  ║
║  │                                                     │  ║
║  │   Sidebar navigation                                │  ║
║  │   ┌──────────┐  ┌────────┐  ┌──────┐  ┌────────┐  │  ║
║  │   │Dashboard │  │ Drives │  │ Scan │  │ Items  │  │  ║
║  │   └──────────┘  └────────┘  └──────┘  └────────┘  │  ║
║  │   ┌──────────┐  ┌────────┐  ┌──────┐  ┌────────┐  │  ║
║  │   │ Library  │  │  Ops   │  │Roots │  │Cleanup │  │  ║
║  │   └──────────┘  └────────┘  └──────┘  └────────┘  │  ║
║  │                                                     │  ║
║  │   api.ts  ──────────── HTTP fetch ──────────────┐  │  ║
║  └─────────────────────────────────────────────────┼──┘  ║
╚════════════════════════════════════════════════════╪══════╝
                                                     │ :8000
╔════════════════════════════════════════════════════╪══════╗
║                 FASTAPI (uvicorn)                  │      ║
║                                                    ▼      ║
║  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   ║
║  │ /drives  │ │  /roots  │ │  /scan   │ │  /files  │   ║
║  └──────────┘ └──────────┘ └──────────┘ └──────────┘   ║
║  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   ║
║  │  /items  │ │  /hash   │ │   /ops   │ │/cleanup  │   ║
║  └──────────┘ └──────────┘ └──────────┘ └──────────┘   ║
║         ┌──────────┐                                     ║
║         │/exports  │                                     ║
║         └──────────┘                                     ║
║                    │                                     ║
║      ┌─────────────┼──────────────────────┐             ║
║      │             │                      │             ║
║  ┌───▼───┐   ┌─────▼────┐   ┌────────┐  ┌▼──────┐    ║
║  │scanner│   │  hasher  │   │copier  │  │ queue │    ║
║  └───────┘   └──────────┘   └────────┘  └───────┘    ║
║                    │                                     ║
╚════════════════════╪═════════════════════════════════════╝
                     │ aiosqlite (WAL mode, FK enforced)
╔════════════════════╪═════════════════════════════════════╗
║               SQLite  milestone.db                       ║
║   drives │ roots │ files │ media_items │ operations │    ║
║   media_item_files │ user_rules │ events               ║
╚══════════════════════════════════════════════════════════╝
                     │
╔════════════════════╪═════════════════════════════════════╗
║              Physical Drives                             ║
║   D:\Movies    E:\TV    F:\Archive    G:\Backup          ║
╚══════════════════════════════════════════════════════════╝
```

**Key design decisions:**
- The Electron shell and Python backend are **separate processes**. The renderer communicates over HTTP to `localhost:8000` — there is no IPC bridge or native module. This keeps the backends independently replaceable and testable.
- The Python backend is **fully async** (FastAPI + aiosqlite). Blocking work (file I/O, hashing) is dispatched to a thread pool so the API stays responsive during long operations.
- The database uses **WAL (Write-Ahead Logging)** mode so reads never block on writes, which matters when the scanner is committing thousands of records while the UI is polling for status.

---

### Backend Services

The backend lives in `services/api/src/`. There are four core services that the routers call into.

#### `scanner.py` — Filesystem Walker

The scanner is the entry point for everything. It uses `os.walk()` to traverse a directory tree and builds the initial index of what exists.

```
scan_root() called as an asyncio background task
    │
    └─► os.walk(root_path)
           │
           for each directory:
           │   ┌─────────────────────────────────────────────┐
           │   │ for each file:                               │
           │   │   os.stat() → size, mtime                   │
           │   │   SELECT FROM files WHERE root_id=? AND path=?│
           │   │                                              │
           │   │   new file    → INSERT                       │
           │   │   mtime changed → UPDATE (reset hash_status) │
           │   │   unchanged   → touch last_seen              │
           │   └─────────────────────────────────────────────┘
           │   db.commit()  ← per-directory, not per-file
           │
           final pass: mark files not seen this run as missing
           final db.commit()
```

**States:** `IDLE → RUNNING → PAUSED → RUNNING → COMPLETED / CANCELLED`

Pause and cancel are cooperative — the scanner checks `_cancel_requested` and `_pause_requested` flags at the top of each directory loop. On cancel it commits immediately before returning so no work is lost.

**Throttle modes** let the scanner back off with `asyncio.sleep()` between files so it doesn't saturate the drive on slower systems.

---

#### `hasher.py` — SHA-256 Fingerprinting

The hasher assigns two levels of identity to files:

| Hash | What it reads | Speed | Purpose |
|------|--------------|-------|---------|
| `quick_sig` | First 4KB + last 4KB + file size | Fast | Near-duplicate detection without reading the whole file |
| `full_hash` | Entire file (SHA-256) | Slow | Exact identity; used for copy verification and true duplicate detection |

The hasher runs as an asyncio task queue. `_hash_queue` is a list of file IDs. `run_hash_queue()` pops IDs one at a time, calls the sync `compute_full_hash()` function via `run_in_executor` (off the event loop), and writes results back to `files`.

```
start_hash_computation()
    │
    ├─ if file_ids given → load them into _hash_queue
    └─ if none given → query DB for all files WHERE hash_status='pending'
           │
           asyncio.create_task(run_hash_queue())
                  │
                  loop:
                    file_id = _hash_queue.pop(0)
                    quick_sig ← read first/last 4KB
                    full_hash ← run_in_executor(compute_full_hash)
                    UPDATE files SET quick_sig=?, full_hash=?, hash_status='hashed'
```

---

#### `copier.py` — Safe File Copy

Safe copy is a multi-step operation designed so that a failure at any point leaves the filesystem in a clean state:

```
safe_copy(source, dest, verify_hash, overwrite)
    │
    ├─ validate source exists, is a file
    ├─ check dest doesn't exist (unless overwrite=True)
    ├─ dest.parent.mkdir(parents=True, exist_ok=True)
    │
    ├─ write to dest.suffix + ".tmp"  ← staging file
    │   └─ run_in_executor(_copy_file_sync)  ← off the event loop
    │       reads 1MB chunks, calls notify_progress via call_soon_threadsafe
    │
    ├─ verify: temp_dest.stat().st_size == source.stat().st_size
    │
    ├─ if verify_hash:
    │   └─ asyncio.gather(
    │       run_in_executor(compute_full_hash, source),   ← concurrent
    │       run_in_executor(compute_full_hash, temp_dest) ← concurrent
    │     )
    │
    └─ temp_dest.replace(dest)  ← single atomic syscall
                                   no window where both files are absent
```

If anything fails, the `.tmp` file is cleaned up in the `except` block and the exception re-raised. The destination file is never touched until the atomic `replace()` call.

---

#### `queue.py` — Operations Queue Engine

The queue engine picks up pending operations from the database and executes them. It runs as a long-lived asyncio task (`run_queue()`).

```
run_queue() — infinite loop while running=True
    │
    ├─ if paused: sleep and loop
    │
    ├─ SELECT operations WHERE status='pending' LIMIT concurrency
    │
    └─ for each op:
           asyncio.create_task(process_operation(op))
                  │
                  ├─ UPDATE status='running'
                  ├─ safe_copy(source, dest, progress_callback=_on_progress)
                  │     _on_progress fires via call_soon_threadsafe
                  │     → loop.create_task(update_op_status(progress=n))
                  │
                  ├─ success: UPDATE status='completed'
                  └─ failure: UPDATE status='failed', error=str(e)
```

**Concurrency** is configurable (default 2, max 10). Active op IDs are tracked in `_queue_state["active_ops"]` so the queue doesn't double-dispatch an operation that's already running.

**Pausing** works at two levels:
- `pause_queue()` → sets a flag; the run loop stops dispatching new ops (in-flight copies continue)
- `pause_operation(op_id)` → marks a single `pending` op as `paused` before it starts. Running copies cannot be paused mid-transfer — there is no cancellation point inside the copy loop.

---

### Database Schema

The SQLite database lives at `services/api/data/milestone.db` and is created automatically on first startup.

```sql
┌─────────────┐
│   drives    │  Physical storage devices
│─────────────│
│ id          │  Primary key
│ mount_path  │  e.g. "D:\" or "/mnt/archive"
│ volume_serial│  Windows volume serial number
│ volume_label│  Windows volume label
│ created_at  │
└──────┬──────┘
       │ 1:N
┌──────▼──────┐
│    roots    │  Subfolders to scan within a drive
│─────────────│
│ id          │
│ drive_id    │ ──── FK → drives.id CASCADE DELETE
│ path        │  Absolute path of the scan root
│ excluded    │  If true, skip this root during scans
└──────┬──────┘
       │ 1:N
┌──────▼──────┐
│    files    │  Every indexed file
│─────────────│
│ id          │
│ root_id     │ ──── FK → roots.id CASCADE DELETE
│ path        │  Full absolute path
│ size        │  Bytes
│ mtime       │  Last modified timestamp (float)
│ ext         │  Extension without dot, lowercase
│ last_seen   │  Updated on every scan; NULL = missing
│ signature_stub│ (reserved)
│ quick_sig   │  First+last 4KB hash for fast near-dedup
│ full_hash   │  SHA-256 of full file
│ hash_status │  'pending' | 'hashing' | 'hashed' | 'quarantined'
│ original_path│  Set at quarantine time; used for restore
└──────┬──────┘
       │ N:M
┌──────▼────────────────────┐    ┌─────────────────┐
│   media_item_files        │    │   media_items   │  Logical groupings
│───────────────────────────│    │─────────────────│
│ media_item_id  ───────────────►│ id              │
│ file_id (← files.id)     │    │ type            │  movie|tv_episode|unknown
│ is_primary                │    │ title           │
└───────────────────────────┘    │ year            │
                                 │ season          │
                                 │ episode         │
                                 │ status          │  auto|verified|needs_verification
                                 └─────────────────┘

┌─────────────────────────────────────────────────────┐
│                    operations                        │  Copy/move queue
│─────────────────────────────────────────────────────│
│ id, type ('copy'), status ('pending'→'completed')   │
│ source_file_id ──── FK → files.id SET NULL          │
│ dest_drive_id  ──── FK → drives.id SET NULL         │
│ dest_path                                           │
│ progress (bytes), total_size, verify_hash           │
│ error, created_at, started_at, completed_at         │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│                    user_rules                        │  Drive preferences
│─────────────────────────────────────────────────────│
│ rule_type: 'denylist'|'prefer_movie'|'prefer_tv'    │
│            |'prefer_all'                            │
│ drive_id ──── FK → drives.id CASCADE DELETE         │
│ priority                                            │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│                      events                          │  Append-only audit log
│─────────────────────────────────────────────────────│
│ timestamp, event_type, data (JSON)                  │
└─────────────────────────────────────────────────────┘
```

**Relationships and cascade rules:**
- Deleting a **drive** cascades to its roots, which cascade to their files, which cascade to their media_item_files links. Operations whose source or dest were on that drive have their FK set to NULL.
- Files in quarantine retain their DB record — only the `path` and `hash_status` change. `original_path` is set so restore knows exactly where to put the file back.
- Foreign key enforcement is **explicitly enabled per-connection** (`PRAGMA foreign_keys = ON`) — SQLite ignores FKs by default.

---

### Frontend & Navigation

The desktop app is a single-page Electron/React application. Navigation is managed by `App.tsx` with a simple `currentScreen` state variable — no routing library.

```
App.tsx
  │
  ├── Layout (sidebar + content area)
  │     │
  │     └── Sidebar links:
  │           Dashboard  →  'dashboard'
  │           Drives     →  'drives'
  │           Roots      →  'roots'
  │           Scan       →  'scan'
  │           Library    →  'library'
  │           Items      →  'items'
  │           Operations →  'operations'
  │           Cleanup    →  'cleanup'
  │
  └── Screen components (one rendered at a time)
```

Every screen imports from `api.ts`, which exports three namespaced objects:

| Export | Covers |
|--------|--------|
| `api` | Drives, roots, scan, files, items, hash, operations, health |
| `cleanupApi` | Recommendations, quarantine, restore, Explorer integration |
| `exportApi` | Returns download URLs for CSV reports |

All requests go to `http://127.0.0.1:8000`. Non-2xx responses parse the FastAPI `{ "detail": "..." }` JSON and throw an `Error`.

---

### How the Pieces Connect

Here is the complete data flow for each major operation:

#### Scan → Index

```
ScanScreen.tsx
  └─► POST /scan/start  { drive_id?, throttle }
           │
           FastAPI scan router
           └─► asyncio.create_task(scan_root(root_id, path))
                    │
                    scanner.py: os.walk()
                    │   for each file: SELECT → INSERT/UPDATE files
                    │   db.commit() each directory
                    │
           GET /scan/status  (polled by UI every 2s)
           └─► returns { state, files_scanned, files_new, files_updated, ... }
```

#### Files → Media Items

```
Dashboard "Process Files" button
  └─► POST /items/process
           │
           items router: SELECT files WHERE not already in media_item_files
           │
           for each file:
             parse filename → extract title, year, season, episode
             find or create matching media_item
             INSERT media_item_files(media_item_id, file_id, is_primary)
           │
           returns { processed, new_items, linked, skipped }
```

#### Hashing

```
Dashboard "Start Hashing" button
  └─► POST /hash/compute  (no body = all pending)
           │
           hasher.py: query files WHERE hash_status='pending'
           asyncio.create_task(run_hash_queue())
                    │
                    for each file_id:
                      run_in_executor → compute_full_hash()  ← thread pool
                      UPDATE files SET full_hash=?, hash_status='hashed'
           │
           GET /hash/status  (polled by UI)
           └─► { state, files_processed, files_total, current_file }
```

#### Copying a File

```
ItemDetailScreen.tsx "Copy to drive" action
  └─► POST /ops/copy  { source_file_id, dest_drive_id?, verify_hash }
           │
           copier.create_copy_operation():
             if no dest_drive_id → score drives by free space + user_rules
             INSERT operations (status='pending')
           │
  └─► POST /ops/queue/start
           │
           queue.run_queue():
             SELECT operations WHERE status='pending'
             process_operation(op):
               UPDATE status='running'
               safe_copy(source, dest):
                 run_in_executor(_copy_file_sync)  ← write to .tmp
                 call_soon_threadsafe(update_progress)
                 temp.replace(dest)  ← atomic
               UPDATE status='completed'
           │
           OperationsScreen polls GET /ops  every 2s for live progress
```

#### Quarantine & Restore

```
CleanupScreen.tsx
  └─► GET /cleanup/recommendations
           │
           cleanup router:
             items with ≥3 copies
             for each item: classify files as keep/delete
               keep: is_primary=true OR drive in user_rules preferred
               delete: everything else (minimum 2 always kept)
           │
  └─► POST /cleanup/quarantine  { file_ids: [...] }
           │
           for each file_id (independent transaction):
             shutil.move(path → .quarantine/YYYY-MM-DD/rel_path)
             UPDATE files SET
               path = quarantine_path,
               original_path = source_path,   ← saved here
               hash_status = 'quarantined'
             db.commit()  ← immediately, per file
           │
  └─► POST /cleanup/restore  [file_id, ...]
           │
           for each file_id:
             SELECT original_path FROM files
             shutil.move(quarantine_path → original_path)
             UPDATE files SET path=original_path, original_path=NULL, hash_status='pending'
             db.commit()
```

---

## Prerequisites

| Requirement | Minimum | Notes |
|-------------|---------|-------|
| Python | 3.11 | Required for modern type syntax |
| Node.js | 18 LTS | Required by Electron 28 |
| npm | 8+ | Bundled with Node 18 |
| OS | Windows 10/11 | Drive registration reads volume labels via `cmd /c vol`. Explorer integration uses `explorer.exe`. Core scanning and hashing work cross-platform. |

---

## Getting Started

### 1. Clone

```bash
git clone https://github.com/mattcallaway/milestone-app.git
cd milestone-app
```

### 2. Set up the backend

```bash
cd services/api
pip install -e ".[dev]"
```

### 3. Configure environment

```bash
# from the project root
cp .env.example .env
```

Open `.env`. The important setting is `WRITE_MODE`:

```env
# Leave as false for safe read-only browsing
# Set to true only when you're ready to move files
WRITE_MODE=false
```

### 4. Start the backend

```bash
cd services/api
uvicorn src.main:app --reload --host 127.0.0.1 --port 8000
```

Visit `http://127.0.0.1:8000/docs` for the interactive API explorer.

### 5. Set up and start the desktop app

```bash
cd apps/desktop
npm install
npm run dev
```

This starts the Vite dev server (port 5173) and the Electron shell simultaneously.

> [!TIP]
> **Windows/IDE Development Note:** 
> If the Electron window is blank or fails to launch from your terminal/IDE:
> 1. Ensure `ELECTRON_RUN_AS_NODE` is not set (`$env:ELECTRON_RUN_AS_NODE=$null` in PowerShell).
> 2. Use `npm.cmd run dev` if `npm` is blocked by PowerShell execution policies.
> 3. Verify that Vite is running on `http://localhost:5173` before starting Electron.

---

## Windows Development Quick Start

For a reliable development experience on Windows:

1. **Environment Clean Up**:
   ```powershell
   # Open PowerShell and ensure no stale Electron variables are set
   $env:ELECTRON_RUN_AS_NODE = $null
   $env:NODE_ENV = "development"
   ```

2. **Sequential Startup** (if `npm run dev` fails):
   ```powershell
   # Terminal 1: Start the renderer
   cd apps/desktop
   npm run dev:renderer

   # Terminal 2: Once Vite is ready, start the main process
   cd apps/desktop
   npm run dev:main
   ```

3. **Common Diagnoses**:
   - **Blank Window**: Electron is failing to load the dev URL. Check if Vite is on a port other than `5173`.
   - **Error: app.whenReady is undefined**: You are running in standard Node.js mode. Unset `ELECTRON_RUN_AS_NODE`.

---

## Using Milestone

### 1. Register Your Drives

Go to **Drives** → **Register Drive**.

Enter the mount path of each drive you want to manage:

```
D:\
E:\
F:\Archive
```

Milestone reads the Windows volume serial number and label automatically. These are used to identify drives even if they get remounted at a different letter.

You must register a drive before you can scan it.

---

### 2. Add Scan Roots

Go to **Roots** → select a drive → **Add Root**.

A scan root is a specific folder you want Milestone to index. You can have multiple roots per drive, and you can mark roots as **excluded** to skip them without deleting them.

```
Drive D:\
  Root: D:\Movies       ← will be scanned
  Root: D:\TV           ← will be scanned
  Root: D:\System       ← excluded

Drive E:\
  Root: E:\Backup       ← will be scanned
```

> **Tip:** Don't add roots that overlap (e.g. both `D:\` and `D:\Movies`). Files in `D:\Movies` would be indexed twice.

---

### 3. Scan Your Library

Go to **Scan** → **Start Scan**.

Options:
- **Drive filter:** scan only one drive, or all drives
- **Throttle:** `normal` (full speed) or `slow` (adds a small delay between files to reduce I/O pressure)

Watch the counters update in real time: files scanned, new files found, files updated, files missing.

You can **Pause** and **Resume** the scan at any time. You can also **Cancel** — work done up to the cancellation point is committed to the database, so you don't lose progress.

After scanning, go to **Library** to browse the indexed files by extension, hash status, or search term.

---

### 4. Process & Group Files into Media Items

Go to **Dashboard** → **Process Files**.

Milestone parses every file that hasn't been grouped yet. It extracts title, year, season, and episode from the filename using common patterns:

| Filename | Identified as |
|----------|--------------|
| `The.Dark.Knight.2008.mkv` | Movie — "The Dark Knight" (2008) |
| `Breaking.Bad.S03E07.mkv` | TV Episode — S03E07 of "Breaking Bad" |
| `random_file.avi` | Unknown |

Files that match an existing media item get linked to it. New titles create new items.

After processing, go to **Items** to browse your library by type and copy count. Click any item to see all its physical files, which drives they're on, and their hash status.

If the grouping is wrong:
- **Merge** items that should be the same file (e.g. two entries for the same movie)
- **Split** a file that was incorrectly grouped into another item
- **Edit** the item's title, year, season, or episode

---

### 5. Hash for Deduplication & Verification

Hashing is optional but enables the most powerful features. Go to **Dashboard** → **Start Hashing**.

With no file IDs specified, this hashes every pending file. The hasher runs in the background — you can navigate away and it continues.

Monitor progress via the hash status (check `GET /hash/status` or watch the dashboard).

What hashing enables:
- **True duplicate detection:** two files with identical `full_hash` are the same content regardless of filename
- **Copy verification:** when copying, Milestone can compare source and destination hashes to confirm the copy is exact
- **Exports:** the Duplicates report requires full hashes to group files by content

To hash a single file immediately without going through the queue: `POST /hash/file/{file_id}`.

---

### 6. Browse Your Library

**Library screen** — raw file view. Filter by:
- Extension (e.g. `mkv`, `mp4`)
- Hash status (`pending`, `hashed`)
- Search term (matches against path)
- Missing files (files that were indexed but not found in the last scan)

Double-click any file to open it in Windows Explorer.

**Items screen** — media item view. Filter by:
- Type: Movies / TV Episodes / Unknown
- Copy count: exactly 1 copy, exactly 2, 3 or more
- Status: needs verification
- Search: by title

The **Dashboard** gives you the at-a-glance copy distribution:

| Color | Count | Meaning |
|-------|-------|---------|
| 🔴 Red | 0 copies | Something is wrong — item exists but no files found |
| 🟠 Orange | 1 copy | At risk — one drive failure loses this permanently |
| 🟢 Green | 2 copies | Backed up |
| 🔵 Blue | 3+ copies | Over-replicated — cleanup candidate |

Click any count card to jump straight to those items.

---

### 7. Create Backup Copies

Items showing **1 copy** (orange) are the ones that need immediate attention.

From **Items** (filtered to `max_copies=1`), click an item → **Item Detail** → **Create Copy**.

From the Item Detail screen:
1. Click **Create Copy** on the file you want to back up
2. Milestone scores available drives by free space and your copy rules, and auto-selects the best destination
3. Or choose a specific destination drive yourself
4. Optionally enable **hash verification** (recommended) — after copying, Milestone hashes both source and destination and confirms they match
5. The operation is added to the queue as `pending`

Go to **Operations** → click **Start Queue** to begin copying.

**Setting copy rules** (via `POST /ops/rules`):

| Rule | Effect |
|------|--------|
| `prefer_movie` on drive E | Auto-copy destinations prefer E for movie files |
| `prefer_tv` on drive F | Auto-copy prefers F for TV episodes |
| `prefer_all` on drive G | G is preferred for everything |
| `denylist` on drive H | Never copy to drive H |

---

### 8. Clean Up Excess Copies

Items with **3+ copies** (blue) are cleanup candidates. Go to **Cleanup**.

Milestone shows you:
- Which items have excess copies
- Which files to **keep** (primary file + files on preferred drives)
- Which files to **recommend deleting** (secondary copies on non-preferred drives)
- How much disk space you'd recover

To clean up:
1. Review the recommendations — click 📂 to open any file in Explorer and verify it before acting
2. Check boxes next to files you want to remove
3. Click **Quarantine Selected**

**Quarantine is not deletion.** Files are moved to a `.quarantine/YYYY-MM-DD/` folder on the same drive. They're gone from the library view but still physically present.

If you change your mind: use `POST /cleanup/restore` with the file IDs. They'll move back to their exact original paths.

When you're confident: `DELETE /cleanup/permanent` removes them from disk and the database permanently.

> **Quarantine requires `WRITE_MODE=true` in your `.env`** — as do all operations that modify files on disk.

---

### 9. Export Reports

The **Cleanup** screen has three CSV export buttons:

| Report | What's in it |
|--------|-------------|
| **At-Risk Report** | Every media item with only 1 physical file — your most vulnerable content |
| **Full Inventory** | Every indexed file: path, size, extension, drive, full hash |
| **Duplicates Report** | Files grouped by SHA-256 hash, showing all locations of identical content |

These are handy for spreadsheet analysis, sharing with someone else, or keeping an offline record of your library.

---

## Configuration

Copy `.env.example` to `.env` in the project root and edit as needed:

```env
# Master write gate
# false = read-only (safe browsing, no file changes)
# true  = enable all write operations (copy, quarantine, delete)
WRITE_MODE=false

# API server bind settings
API_HOST=127.0.0.1
API_PORT=8000

# Open Electron DevTools automatically
ELECTRON_DEV_TOOLS=false

# Python log level: debug | info | warning | error
LOG_LEVEL=info
```

> **Never commit `.env`** — it's in `.gitignore` by default.

---

## API Reference

With the backend running, visit:

- **Swagger UI:** `http://127.0.0.1:8000/docs` — interactive, try-it-out API explorer
- **ReDoc:** `http://127.0.0.1:8000/redoc` — readable reference docs

All responses are JSON. Errors return `{ "detail": "message" }`.

**Quick endpoint summary:**

```
GET  /health                   → status + write_mode
GET  /mode                     → "read-only" or "write"

GET  /drives                   → list drives
POST /drives/register          → register a drive
DEL  /drives/{id}              → remove a drive

GET  /roots                    → list scan roots
POST /roots                    → add a root
DEL  /roots/{id}               → remove a root
PATCH /roots/{id}              → toggle excluded

POST /scan/start               → start scan
GET  /scan/status              → live scan status
POST /scan/control             → pause | resume | cancel

GET  /files                    → paginated file list
GET  /files/stats              → counts by extension
POST /files/{id}/open-explorer → highlight file in Explorer

GET  /items                    → paginated media items
GET  /items/stats              → copy count distribution
GET  /items/{id}               → item detail with files
PATCH /items/{id}              → edit title/year/season/episode
POST /items/process            → group files into items
POST /items/merge              → merge items together
POST /items/split              → split a file to its own item

POST /hash/compute             → start hashing
GET  /hash/status              → hash progress
POST /hash/stop                → stop hashing
POST /hash/file/{id}           → hash one file immediately

GET  /ops                      → list operations
POST /ops/copy                 → create a copy job
POST /ops/copy/batch           → copy all files for a media item
GET  /ops/queue/status         → queue engine state
POST /ops/queue/start          → start processing
POST /ops/queue/pause          → pause dispatching
POST /ops/queue/resume         → resume
POST /ops/{id}/pause           → pause a pending op
POST /ops/{id}/cancel          → cancel an op
GET  /ops/destinations/{fid}   → scored destination drives
GET  /ops/rules                → list copy rules
POST /ops/rules                → create a rule
DEL  /ops/rules/{id}           → remove a rule

GET  /cleanup/recommendations  → excess-copy cleanup suggestions
POST /cleanup/quarantine       → move files to .quarantine/
POST /cleanup/restore          → restore from quarantine
DEL  /cleanup/permanent        → permanently delete quarantined files

GET  /exports/at-risk          → CSV: single-copy items
GET  /exports/inventory        → CSV: full file inventory
GET  /exports/duplicates       → CSV: files grouped by content hash
```

---

## Build & Packaging

### Development

```bash
# Terminal 1 — backend
cd services/api
uvicorn src.main:app --reload

# Terminal 2 — desktop app
cd apps/desktop
npm install
npm run dev
```

### Production Package

```bash
cd apps/desktop
npm run package   # builds renderer + main process + runs electron-builder
```

Output goes to `apps/desktop/dist/`. electron-builder creates a Windows installer by default.

### Backend (standalone)

```bash
cd services/api
pip install -e .
uvicorn src.main:app --host 0.0.0.0 --port 8000
```

For running as a background service on Windows, use NSSM or wrap with `pywin32`.

---

## Linting & Testing

### Backend

```bash
cd services/api

ruff check .              # fast Python linter
ruff check . --fix        # auto-fix where possible
mypy src                  # strict type checking
pytest                    # run test suite
pytest --cov=src          # with coverage
```

### Desktop

```bash
cd apps/desktop

npm run lint              # ESLint
npm run typecheck         # tsc --noEmit
npm run test              # Jest
```

---

## Safety Design

Milestone is designed to never silently lose data. Every potentially destructive operation has been hardened:

| Concern | What Milestone does |
|---------|-------------------|
| **Overwriting a file during copy** | Writes to a `.tmp` staging file, then uses a single atomic `os.replace()` call. There is no moment where neither source nor destination exists. |
| **Partial quarantine failure** | Each file is committed to the database independently. If file 3 of 10 fails to move, files 1–2 are safely recorded as quarantined and file 4–10 are retried fresh. |
| **Restore without knowing original path** | The `original_path` is stored in the database at quarantine time. Restore reads it directly — no guessing from folder structure. |
| **Orphaned DB records** | `PRAGMA foreign_keys = ON` is set on every connection. Deleting a drive cascades to its roots and files. |
| **Losing scan progress on cancel** | The scanner commits before returning on cancel, not just on completion. |
| **API blocking during large file copy** | File I/O runs in a thread pool via `run_in_executor`. The asyncio event loop stays free to serve other requests. |
| **Accidental deletion** | The default workflow quarantines (moves) files rather than deleting them. Permanent deletion requires a separate explicit API call. |
| **Modifying files in read-only mode** | `WRITE_MODE=false` (the default) causes all file-modifying endpoints to reject requests before touching the filesystem. |

---

## License

MIT
