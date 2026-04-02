# Milestone App

> A local-first media library manager for collectors managing large video file archives across multiple physical drives. Milestone scans, fingerprints, deduplicates, copies, and safely cleans up media files — all without requiring any cloud service or internet connection.

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Project Structure](#project-structure)
4. [Technical Map — Backend](#technical-map--backend)
   - [Entry Point & Lifespan](#entry-point--lifespan)
   - [Database Layer](#database-layer)
   - [Schema](#schema)
   - [Configuration](#configuration)
   - [Core Services](#core-services)
   - [API Routers](#api-routers)
5. [Technical Map — Frontend](#technical-map--frontend)
   - [Electron Main Process](#electron-main-process)
   - [Renderer (React/Vite)](#renderer-reactvite)
   - [API Client](#api-client)
   - [Screens](#screens)
6. [Data Flow Diagrams](#data-flow-diagrams)
7. [Prerequisites](#prerequisites)
8. [How-To: Development Setup](#how-to-development-setup)
9. [How-To: First Run & Drive Registration](#how-to-first-run--drive-registration)
10. [How-To: Scanning a Drive](#how-to-scanning-a-drive)
11. [How-To: Hashing Files](#how-to-hashing-files)
12. [How-To: Media Item Grouping](#how-to-media-item-grouping)
13. [How-To: Copying Files](#how-to-copying-files)
14. [How-To: Cleanup & Quarantine](#how-to-cleanup--quarantine)
15. [How-To: Exporting Reports](#how-to-exporting-reports)
16. [Configuration Reference](#configuration-reference)
17. [API Reference](#api-reference)
18. [Safety Design](#safety-design)
19. [Build & Packaging](#build--packaging)
20. [Linting & Testing](#linting--testing)
21. [License](#license)

---

## Overview

Milestone is a desktop application built as a **monorepo** with two main services:

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Backend API | Python 3.11, FastAPI, aiosqlite | File scanning, hashing, media grouping, operations queue |
| Desktop frontend | Electron 28, React 18, TypeScript, Vite | Native desktop UI, communicates with local API |

The application is **safe by default** — all write operations (file moves, deletions, quarantines) require `WRITE_MODE=true` to be explicitly set.

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│                 Electron Shell                   │
│  ┌───────────────────────────────────────────┐  │
│  │         React Renderer (Vite)             │  │
│  │   Dashboard │ Drives │ Scan │ Items │     │  │
│  │   Ops       │ Cleanup │ Library │ Hash   │  │
│  └──────────────────┬────────────────────────┘  │
│                     │ HTTP fetch to localhost     │
└─────────────────────┼───────────────────────────┘
                      │ port 8000
         ┌────────────▼────────────────┐
         │     FastAPI  (uvicorn)      │
         │                             │
         │  Routers:                   │
         │  /drives  /roots  /files    │
         │  /scan    /items  /hash     │
         │  /ops     /cleanup /exports │
         │                             │
         │  Core services:             │
         │  scanner · hasher · copier  │
         │  queue   · config           │
         └────────────┬────────────────┘
                      │ aiosqlite (async)
         ┌────────────▼────────────────┐
         │    SQLite  milestone.db     │
         │  WAL mode · FK enforcement  │
         └─────────────────────────────┘
                      │
         ┌────────────▼────────────────┐
         │  Physical Storage Drives    │
         │  D:\ E:\ F:\ …              │
         └─────────────────────────────┘
```

The Electron main process starts the React renderer — the renderer talks directly to the FastAPI server over `localhost:8000`. There is **no IPC bridge** between Electron and Python; communication is entirely via HTTP.

---

## Project Structure

```
milestone-app/
├── apps/
│   └── desktop/                    # Electron + React + Vite
│       ├── src/
│       │   ├── main.ts             # Electron main process
│       │   ├── preload.ts          # Context bridge (minimal)
│       │   ├── index.tsx           # React entry point
│       │   ├── App.tsx             # Root component & router
│       │   ├── api.ts              # Typed HTTP client for the backend
│       │   ├── index.css           # Global base styles
│       │   └── screens/            # Full-page view components
│       │       ├── DashboardScreen.tsx
│       │       ├── DrivesScreen.tsx
│       │       ├── RootsScreen.tsx
│       │       ├── ScanScreen.tsx
│       │       ├── LibraryScreen.tsx
│       │       ├── ItemsScreen.tsx
│       │       ├── ItemDetailScreen.tsx
│       │       ├── OperationsScreen.tsx
│       │       ├── CleanupScreen.tsx
│       │       └── Screens.css
│       ├── package.json
│       ├── tsconfig.json           # Renderer TypeScript config
│       └── tsconfig.main.json      # Main process TypeScript config
│
├── services/
│   └── api/                        # Python FastAPI backend
│       ├── src/
│       │   ├── main.py             # FastAPI app, lifespan, CORS
│       │   ├── config.py           # pydantic-settings config
│       │   ├── database.py         # SQLite connection, init, migration
│       │   ├── schema.sql          # DDL — all tables
│       │   ├── scanner.py          # Async filesystem walker
│       │   ├── hasher.py           # SHA-256 hashing service
│       │   ├── copier.py           # Safe file copy (thread-pool I/O)
│       │   ├── queue.py            # Async operations queue engine
│       │   └── routers/
│       │       ├── drives.py       # Drive registration/management
│       │       ├── roots.py        # Scan root management
│       │       ├── scan.py         # Scan start/stop/status
│       │       ├── files.py        # File listing, stats, open-in-explorer
│       │       ├── items.py        # Media item CRUD, merge, split, process
│       │       ├── hash.py         # Hash compute/status/stop
│       │       ├── ops.py          # Operations queue CRUD, copy creation
│       │       ├── cleanup.py      # Recommendations, quarantine, restore
│       │       └── exports.py      # CSV export of at-risk/inventory/duplicates
│       ├── data/
│       │   └── milestone.db        # SQLite database (auto-created)
│       └── pyproject.toml
│
├── packages/
│   └── shared/                     # Shared TypeScript types (future use)
│
├── docs/                           # Architecture notes
├── .env.example                    # Environment variable template
└── README.md
```

---

## Technical Map — Backend

### Entry Point & Lifespan

**`services/api/src/main.py`**

The FastAPI application is created with a `lifespan` context manager (the modern alternative to `on_startup`/`on_shutdown` events). On startup, `init_db()` is called — this runs the full schema DDL and any pending column migrations. All 9 routers are registered on the app. CORS is fully open (`allow_origins=["*"]`) since the only client is the local Electron renderer.

Special endpoints:
- `GET /` — health ping
- `GET /health` — returns `{ status, write_mode }`
- `GET /mode` — returns `"read-only"` or `"write"`

---

### Database Layer

**`services/api/src/database.py`**

The database file lives at `services/api/data/milestone.db` (created automatically).

Two functions:

| Function | Purpose |
|----------|---------|
| `init_db()` | Runs `schema.sql` via `executescript`, then runs pending `ALTER TABLE` column migrations (currently: `original_path` on `files`). Safe to call on every startup — `CREATE TABLE IF NOT EXISTS` makes it idempotent. |
| `get_db()` | Async context manager (`@asynccontextmanager`). Opens a connection, sets `row_factory = aiosqlite.Row` (dict-like rows), applies `PRAGMA foreign_keys = ON` and `PRAGMA journal_mode = WAL`, yields, and closes. Every router uses this. |

**Why WAL mode?** Write-Ahead Logging allows concurrent readers while a write is in progress. The scanner and queue both write to the DB while the API serves read requests — without WAL, those reads would block.

**Why foreign key enforcement?** SQLite disables FK constraints by default. Without `PRAGMA foreign_keys = ON`, deleting a drive would leave orphaned `roots`, `files`, and `operations` records even though the schema defines `ON DELETE CASCADE`.

---

### Schema

**`services/api/src/schema.sql`**

```sql
drives          -- Physical storage devices
  id, mount_path, volume_serial, volume_label, created_at

roots           -- Scan roots within a drive (subfolders to include/exclude)
  id, drive_id → drives.id CASCADE, path, excluded, created_at

files           -- Every file seen by the scanner
  id, root_id → roots.id CASCADE, path, size, mtime, ext,
  last_seen, signature_stub, quick_sig, full_hash, hash_status,
  original_path   ← set when quarantined; cleared on restore

media_items     -- Logical media groupings (a movie, a TV episode, etc.)
  id, type, title, year, season, episode, status, created_at

media_item_files  -- N:M join — one item may span multiple physical files
  media_item_id → media_items.id CASCADE,
  file_id → files.id CASCADE,
  is_primary

operations      -- Copy/move/delete jobs in the queue
  id, type, status, source_file_id → files.id SET NULL,
  dest_drive_id → drives.id SET NULL, dest_path,
  progress, total_size, verify_hash, error,
  created_at, started_at, completed_at

user_rules      -- Per-drive copy preferences and denylists
  id, rule_type, drive_id → drives.id CASCADE, priority

events          -- Append-only audit log
  id, timestamp, event_type, data (JSON)
```

**`files.hash_status`** lifecycle:
```
pending → hashing → hashed
pending → quarantined → pending  (after restore)
```

**`files.original_path`** — written at quarantine time, null otherwise. Enables reliable restore without fragile path reconstruction.

---

### Configuration

**`services/api/src/config.py`** — uses `pydantic-settings`. Reads environment variables (or `.env` file).

| Variable | Default | Description |
|----------|---------|-------------|
| `WRITE_MODE` | `false` | Master safety gate. Must be `"true"` to allow any file writes. |
| `API_HOST` | `127.0.0.1` | Bind address for uvicorn |
| `API_PORT` | `8000` | Bind port |
| `LOG_LEVEL` | `info` | Python logging level |
| `ELECTRON_DEV_TOOLS` | `false` | Open DevTools on launch |

`is_write_enabled()` is a helper that returns `True` only when `WRITE_MODE=true`. Routers that perform destructive operations check this before proceeding.

---

### Core Services

#### `scanner.py` — Filesystem Walker

The scanner uses `os.walk()` (sync, but run on the asyncio event loop since directory listing is fast) to traverse a scan root. For each file it finds:

1. `os.stat()` — gets `size` and `mtime`
2. Checks the `files` table for an existing record by `(root_id, path)`
   - **New file** → `INSERT`
   - **Modified** (`mtime` changed) → `UPDATE` with new size/mtime, reset hash status
   - **Unchanged** → `UPDATE last_seen` only
3. Writes a periodic `commit()` at the end of each directory batch
4. On cancel: **commits immediately** before returning, so progress up to that point is persisted

After the walk, files whose `last_seen` is older than the scan's start time are marked missing.

State machine:
```
IDLE → RUNNING → PAUSED → RUNNING → COMPLETED
                         → CANCELLED
```

Global state (`_scan_state`, `_scan_status`, `_cancel_requested`, `_pause_requested`) is module-level so all concurrent requests see the same state.

---

#### `hasher.py` — SHA-256 Hash Service

Two hash levels:

| Hash | How computed | When used |
|------|-------------|-----------|
| `quick_sig` | First 4 KB + last 4 KB + file size | Fast near-duplicate detection |
| `full_hash` | SHA-256 of entire file | Exact match, copy verification |

`compute_full_hash(path)` is a **synchronous** function called via `run_in_executor` by the copier for off-loop execution.

`run_hash_queue()` is an async task that pops IDs from `_hash_queue`, hashes each file in sequence, and updates the DB. Progress is tracked in `_hash_status`.

`start_hash_computation(file_ids=None)`:
- If `file_ids` is given → loads them directly into the queue
- If `None` → calls `queue_pending_files()` to fetch all files with `hash_status='pending'` from the DB
- Starts `run_hash_queue()` as an asyncio task

---

#### `copier.py` — Safe File Copy

`safe_copy(source, dest, verify_hash, overwrite, progress_callback)`:

1. Validates source exists and dest is free (or `overwrite=True`)
2. Creates `dest.tmp` as a staging file
3. **Off the event loop**: dispatches `_copy_file_sync` via `loop.run_in_executor(None, ...)` — this keeps all other API requests responsive during large file copies
4. Progress notifications cross the thread boundary via `loop.call_soon_threadsafe(callback, bytes_done)`
5. Size verification after copy
6. Optional hash verification via `asyncio.gather` — runs source and dest hashing concurrently in the thread pool
7. **Atomic rename**: `temp_dest.replace(dest)` — single kernel call, no window where both files are simultaneously absent

`_copy_file_sync(source, temp_dest, notify_progress)` is a plain synchronous function safe to run in a thread. It MUST NOT call any asyncio API directly.

`get_destination_drives()` — scores and ranks available drives by free space and user rule preferences.

`create_copy_operation()` — inserts a `pending` operation into the DB; the queue engine picks it up.

---

#### `queue.py` — Operations Queue Engine

Module-level state (`_queue_state`) tracks: `running`, `paused`, `concurrency`, `active_ops`.

`run_queue()` — background asyncio task that loops while running:
1. Skips if paused
2. Fetches `pending` operations from DB up to concurrency limit
3. Creates a task per operation via `process_operation()`

`process_operation(op)`:
1. Updates status → `running`
2. Calls `safe_copy()` with an `_on_progress` callback
3. `_on_progress` uses `loop.create_task()` to schedule a DB status update — this is safe because `call_soon_threadsafe` in copier.py already delivered the callback on the event loop thread
4. On success → status `completed`; on failure → status `failed` with error string

`pause_operation(op_id)`:
- **Only `pending` operations can be paused** — a running copy cannot be interrupted mid-transfer. Attempting to pause a running operation returns `False`, and the API returns a clear 400 explaining why.

---

### API Routers

All routers live in `services/api/src/routers/`.

#### `drives.py` — `/drives`

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/drives` | List all registered drives with optional free-space info |
| `POST` | `/drives/register` | Register a new drive by mount path; reads volume serial/label via `cmd /c vol` |
| `DELETE` | `/drives/{id}` | Delete a drive (cascades to roots, files, operations via FK) |

---

#### `roots.py` — `/roots`

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/roots` | List all roots, optionally filtered by `drive_id` |
| `POST` | `/roots` | Create a scan root for a drive |
| `DELETE` | `/roots/{id}` | Remove a scan root |
| `PATCH` | `/roots/{id}` | Toggle `excluded` flag |

---

#### `scan.py` — `/scan`

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/scan/start` | Start a scan (optionally filter by `drive_id`, set `throttle`) |
| `GET` | `/scan/status` | Current scan state, counters, ETA |
| `POST` | `/scan/control` | `{ action: "pause" | "resume" | "cancel" }` |

---

#### `files.py` — `/files`

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/files` | Paginated file list with filters: `root_id`, `ext`, `hash_status`, `search`, `missing` |
| `GET` | `/files/stats` | Aggregate counts and sizes by extension |
| `POST` | `/files/{id}/open-explorer` | Shell-opens the file in Windows Explorer (highlights it) |
| `POST` | `/files/{id}/open-folder` | Shell-opens the file's parent folder |

---

#### `items.py` — `/items`

Media items are **logical groupings** of physical files (e.g. the same movie on two drives = one media item, two files).

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/items` | Paginated items list with filters: `type`, `min_copies`, `max_copies`, `status`, `search` |
| `GET` | `/items/stats` | Counts by type, copy count distribution, needs-verification count |
| `GET` | `/items/{id}` | Item detail with all associated files |
| `PATCH` | `/items/{id}` | Update title, year, season, episode, type |
| `POST` | `/items/process` | Parse all un-grouped files by filename and create/link media items |
| `POST` | `/items/merge` | Merge multiple items into a target item |
| `POST` | `/items/split` | Split a single file out of an item into its own item |

**HAVING / pagination** use fully parameterized `?` placeholders — no f-string SQL interpolation.

---

#### `hash.py` — `/hash`

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/hash/compute` | Start hashing; optional `file_ids` body; if omitted, hashes all `pending` |
| `GET` | `/hash/status` | Current hash state and progress |
| `POST` | `/hash/stop` | Stop the hash runner after the current file |
| `POST` | `/hash/file/{id}` | Hash a single file immediately (bypasses queue) |

---

#### `ops.py` — `/ops`

> **Route order is significant.** All literal sub-paths (`/queue/*`, `/copy`, `/rules`, `/destinations/*`) are registered **before** the `/{op_id}` catch-all.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/ops` | Paginated operations list with filters: `status`, `type` |
| `GET` | `/ops/queue/status` | Queue engine state + pending/running counts |
| `POST` | `/ops/queue/start` | Start the queue worker |
| `POST` | `/ops/queue/stop` | Stop the queue worker |
| `POST` | `/ops/queue/pause` | Pause all new dispatch (in-flight ops continue) |
| `POST` | `/ops/queue/resume` | Resume dispatch |
| `POST` | `/ops/queue/concurrency` | Set max concurrent operations (1–10) |
| `POST` | `/ops/copy` | Create a single copy operation |
| `POST` | `/ops/copy/batch` | Create copy operations for all files in a media item |
| `GET` | `/ops/rules` | List user drive rules |
| `POST` | `/ops/rules` | Create a rule (`denylist`, `prefer_movie`, `prefer_tv`, `prefer_all`) |
| `DELETE` | `/ops/rules/{id}` | Delete a rule |
| `GET` | `/ops/destinations/{file_id}` | Get ranked destination drives for a file |
| `POST` | `/ops/{id}/pause` | Pause a **pending** operation (running ops cannot be interrupted) |
| `POST` | `/ops/{id}/resume` | Resume a paused operation |
| `POST` | `/ops/{id}/cancel` | Cancel an operation |
| `GET` | `/ops/{id}` | Get a single operation's details ← registered last |

---

#### `cleanup.py` — `/cleanup`

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/cleanup/recommendations` | Items with `≥ min_copies` copies; classifies each file as keep/delete based on is_primary + user_rules |
| `GET` | `/cleanup/quarantine-list` | Files currently in quarantine |
| `POST` | `/cleanup/quarantine` | Move files to `{drive}/.quarantine/{date}/{relative_path}`; writes `original_path` to DB; per-file commit |
| `POST` | `/cleanup/restore` | Move quarantined files back using `original_path` from DB; per-file commit |
| `DELETE` | `/cleanup/permanent` | Permanently delete quarantined files from disk and DB |

**Quarantine lifecycle:**
```
file on disk
    ↓  POST /cleanup/quarantine
file at .quarantine/{date}/...
DB: path=quarantine_path, original_path=original, hash_status='quarantined'
    ↓  POST /cleanup/restore
file back at original_path
DB: path=original_path, original_path=NULL, hash_status='pending'
    ↓  DELETE /cleanup/permanent  (alternative)
file deleted, DB record removed
```

---

#### `exports.py` — `/exports`

Generates CSV downloads (streamed response):

| Path | Contents |
|------|---------|
| `/exports/at-risk` | Files with only a single copy |
| `/exports/inventory` | Full file inventory with drive and hash info |
| `/exports/duplicates` | Files grouped by full_hash showing all locations |

---

## Technical Map — Frontend

### Electron Main Process

**`apps/desktop/src/main.ts`**

Creates a 1200×800 `BrowserWindow` with `contextIsolation: true` and `nodeIntegration: false` (security best practice). In development, loads the Vite dev server at `http://localhost:5173`. In production, loads the static build from `dist/index.html`. Reads `WRITE_MODE` from the environment and logs it to console.

---

### Renderer (React/Vite)

**`apps/desktop/src/App.tsx`**

Root component that renders a sidebar nav and switches between screens based on a `currentScreen` state variable. No external routing library — screen switching is a simple conditional render.

**`apps/desktop/src/index.tsx`**

React 18 entry: `createRoot(document.getElementById('root')).render(<App />)`

---

### API Client

**`apps/desktop/src/api.ts`**

A thin typed wrapper over `fetch`. All requests go to `http://127.0.0.1:8000`. Non-2xx responses are unwrapped from the FastAPI error JSON and thrown as `Error` objects.

Exports three namespaced objects:

| Export | Covers |
|--------|--------|
| `api` | Drives, roots, scan, files, items, hash, operations, health |
| `cleanupApi` | Recommendations, quarantine, restore, open-in-explorer |
| `exportApi` | Returns raw URLs for CSV download links |

All TypeScript interfaces (`Drive`, `Root`, `FileItem`, `MediaItem`, `Operation`, `QueueStatus`, etc.) are defined in this file and re-exported for screen components.

---

### Screens

| Screen | Route key | Purpose |
|--------|-----------|---------|
| `DashboardScreen` | `dashboard` | Overview stats: file count, total size, hash coverage, at-risk count |
| `DrivesScreen` | `drives` | Register/remove drives; shows free space |
| `RootsScreen` | `roots` | Add/remove/exclude scan roots per drive |
| `ScanScreen` | `scan` | Start/pause/cancel scans; live progress bar and counters |
| `LibraryScreen` | `library` | Browse all files with extension and hash filters |
| `ItemsScreen` | `items` | Browse media items; filter by copy count |
| `ItemDetailScreen` | `item-detail` | View all physical files for a media item; copy/quarantine actions |
| `OperationsScreen` | `operations` | Live operations queue; start/stop/pause/cancel individual ops |
| `CleanupScreen` | `cleanup` | Cleanup recommendations; quarantine/restore workflow |

---

## Data Flow Diagrams

### Scan Flow

```
User: "Start Scan"
      │
      ▼
POST /scan/start
      │  starts asyncio task
      ▼
scan_root(root_id, root_path) ─── os.walk() ──► directory
      │                                             │
      │  for each file:                             │
      │  ┌──────────────────────────────┐           │
      │  │ os.stat() → size, mtime      │           │
      │  │ SELECT from files            │           │
      │  │   new   → INSERT             │           │
      │  │   changed → UPDATE           │           │
      │  │   same  → touch last_seen    │           │
      │  └──────────────────────────────┘           │
      │  commit() every directory                   │
      │  commit() on cancel (saves progress)        │
      │                                             │
      └─── mark missing files → final commit ───────┘
```

### Copy Flow

```
User: "Copy file X to drive Y"
      │
      ▼
POST /ops/copy  →  create_copy_operation()  →  INSERT operations (status='pending')
                                                         │
                                              Queue picks it up
                                                         │
                                              process_operation()
                                                         │
                                              safe_copy()
                                                │
                              ┌─────────────────┼─────────────────┐
                              │                 │                 │
                     thread pool           event loop       event loop
                   _copy_file_sync()   call_soon_threadsafe  asyncio.gather
                   (read+write 1MB     (_on_progress)        (hash src+dest)
                    chunks)                  │
                              │       loop.create_task(
                              │         update_op_status(progress=n))
                              │
                   temp_dest.replace(dest)   ← atomic
                              │
                   UPDATE operations SET status='completed'
```

### Quarantine Flow

```
User selects files to quarantine
      │
      ▼
POST /cleanup/quarantine  { file_ids: [...] }
      │
      for each file_id:
      │  ┌──────────────────────────────────────────────────────┐
      │  │  SELECT path, mount_path FROM files JOIN drives       │
      │  │  shutil.move(source → .quarantine/{date}/rel_path)   │
      │  │  UPDATE files SET                                     │
      │  │    path = quarantine_path,                           │
      │  │    original_path = source_path,   ← saved here       │
      │  │    hash_status = 'quarantined'                        │
      │  │  db.commit()   ← per-file, not per-batch             │
      │  └──────────────────────────────────────────────────────┘
      │
POST /cleanup/restore  [file_id, ...]
      │
      for each file_id:
         SELECT original_path FROM files WHERE hash_status='quarantined'
         shutil.move(quarantine_path → original_path)
         UPDATE files SET path=original_path, original_path=NULL, hash_status='pending'
         db.commit()   ← per-file
```

---

## Prerequisites

| Requirement | Minimum version | Notes |
|-------------|----------------|-------|
| Python | 3.11 | Required for `match` statements and modern type syntax |
| Node.js | 18 LTS | Electron 28 requires Node 18+ |
| npm | 8+ | Comes with Node 18 |
| Git | Any | For cloning |
| Windows | 10/11 | Drive registration uses `cmd /c vol`; Explorer integration uses `explorer.exe` |

> **macOS / Linux:** Core scanning and hashing work cross-platform. Drive registration (volume label reading) and open-in-explorer are Windows-specific and will gracefully error on other platforms.

---

## How-To: Development Setup

### 1. Clone the repository

```bash
git clone https://github.com/your-org/milestone-app.git
cd milestone-app
```

### 2. Set up the Python backend

```bash
cd services/api
pip install -e ".[dev]"
```

This installs FastAPI, uvicorn, aiosqlite, pydantic-settings, and all dev tools (pytest, ruff, mypy).

### 3. Configure the environment

```bash
# From the project root
cp .env.example .env
```

Edit `.env` as needed. The most important setting is `WRITE_MODE`. Leave it as `false` for safe read-only exploration.

### 4. Start the backend

```bash
# From services/api/
uvicorn src.main:app --reload --host 127.0.0.1 --port 8000
```

The API will be available at `http://127.0.0.1:8000`. Visit `http://127.0.0.1:8000/docs` for the interactive Swagger UI.

### 5. Set up the desktop frontend

```bash
cd apps/desktop
npm install
```

### 6. Start the desktop app (development)

```bash
npm run dev
```

This runs two processes concurrently:
- `vite` — React renderer dev server on port 5173 with HMR
- `tsc -p tsconfig.main.json && electron .` — Electron loads the Vite dev server URL

### 7. Running both together (from separate terminals)

```
Terminal 1            Terminal 2
─────────────         ──────────────────────────
cd services/api       cd apps/desktop
uvicorn ...           npm run dev
```

---

## How-To: First Run & Drive Registration

1. Open the Milestone desktop app.
2. Navigate to **Drives** in the sidebar.
3. Click **Register Drive**.
4. Enter the mount path (e.g. `D:\` or `E:\Media`).
5. Milestone reads the volume serial and label from Windows and saves the drive to the database.

> You must register a drive before you can add scan roots to it.

---

## How-To: Scanning a Drive

1. Navigate to **Roots** in the sidebar.
2. Select a drive and click **Add Root**.
3. Enter the folder path to scan (e.g. `D:\Movies`). You can add multiple roots per drive.
4. Navigate to **Scan**.
5. Click **Start Scan**. Optionally filter to a single drive or set a throttle level.
6. Watch the live progress counter. You can **Pause**, **Resume**, or **Cancel** at any time — even on cancel, all progress up to that point is committed to the database.
7. After the scan completes, navigate to **Library** to browse the indexed files.

---

## How-To: Hashing Files

Hashing is **not automatic** after scanning — it is a separate opt-in step because hashing large drives is time-consuming.

1. Navigate to the **Items** or **Library** screen.
2. From the API or the UI, trigger `POST /hash/compute` (or use the Hash button if exposed in the UI).
3. With no body, this hashes all files currently in `pending` status.
4. Monitor progress via `GET /hash/status`.
5. To hash a specific file immediately: `POST /hash/file/{file_id}`.
6. To stop hashing: `POST /hash/stop` — the current file will finish, then the runner stops.

Hash results are stored in `files.quick_sig` and `files.full_hash`. The copier uses `full_hash` for post-copy verification.

---

## How-To: Media Item Grouping

Milestone parses filenames to group physical files into logical media items (movies, TV episodes).

1. After scanning, call `POST /items/process`.
2. Milestone parses each un-grouped file by filename using patterns like:
   - `Movie.Title.2024.mkv` → movie
   - `Show.Name.S02E05.mkv` → TV episode
3. Files that match an existing item are linked to it; new items are created for new titles.
4. Browse results in the **Items** screen — filter by `type`, `min_copies`, `max_copies`.
5. If the auto-grouping is wrong, use **Merge** or **Split** to correct it.
6. Use **Update Item** (`PATCH /items/{id}`) to correct the title, year, season, or episode number.

---

## How-To: Copying Files

Milestone copies files safely via the operations queue:

1. Navigate to **Operations**.
2. Use `POST /ops/copy` with a `source_file_id`. Optionally specify `dest_drive_id` or `dest_path` — if omitted, the best available drive is auto-selected based on free space and user rules.
3. To create copies for an entire media item (all physical files): `POST /ops/copy/batch` with `media_item_id`.
4. Click **Start Queue** to begin processing.
5. Each operation shows live progress (bytes copied).
6. You can **pause individual pending operations** — note that running operations (currently copying) cannot be paused mid-transfer.
7. Cancelled operations leave no partial files — the `.tmp` staging file is cleaned up automatically.

### User Rules for destination selection

Add rules via `POST /ops/rules`:

| Rule type | Effect |
|-----------|--------|
| `denylist` | Never copy to this drive |
| `prefer_movie` | Boost this drive's score for movie files |
| `prefer_tv` | Boost this drive's score for TV episode files |
| `prefer_all` | Boost this drive's score for any file type |

---

## How-To: Cleanup & Quarantine

The cleanup workflow is a **reversible soft-delete**, not an immediate delete.

1. Navigate to **Cleanup**.
2. Click **Get Recommendations**. The system finds items with 3+ copies and recommends which to delete (non-primary files on non-preferred drives).
3. Review the recommendations — each shows which files would be kept and which deleted, plus disk savings.
4. Select files to quarantine and click **Quarantine**.
   - Files are **moved** (not deleted) to `{drive_root}/.quarantine/{YYYY-MM-DD}/{relative_path}`.
   - The original path is stored in the database.
   - This is fully reversible.
5. If you want to restore a quarantined file: **Restore** — the file moves back to its original location.
6. If you are satisfied the quarantined files are truly unneeded: `DELETE /cleanup/permanent` — this permanently removes them from disk and the database.

> **Quarantine requires `WRITE_MODE=true`.** In read-only mode, the endpoint will reject the request.

---

## How-To: Exporting Reports

Milestone can export CSV reports for external analysis:

| Export | URL | Contents |
|--------|-----|---------|
| At-Risk Files | `/exports/at-risk` | All files with only one known copy — the ones most at risk if a drive fails |
| Full Inventory | `/exports/inventory` | Every file: path, size, extension, drive, hash status, full hash |
| Duplicates | `/exports/duplicates` | Files grouped by content hash, showing all locations of the same content |

In the desktop app, use the export buttons in the relevant screen, or open the URLs directly in a browser while the API is running.

---

## Configuration Reference

Create a `.env` file in the project root (copy from `.env.example`):

```env
# Master write gate — set true to enable any file modification
WRITE_MODE=false

# API bind settings
API_HOST=127.0.0.1
API_PORT=8000

# Electron - open DevTools on launch
ELECTRON_DEV_TOOLS=false

# Logging level: debug | info | warning | error
LOG_LEVEL=info
```

> **Never commit your `.env` file.** `.gitignore` excludes it by default.

---

## API Reference

The full interactive API reference is available at `http://127.0.0.1:8000/docs` (Swagger UI) or `http://127.0.0.1:8000/redoc` (ReDoc) when the backend is running.

### Base URL

```
http://127.0.0.1:8000
```

### Response Format

All endpoints return JSON. Errors follow the FastAPI standard:
```json
{
  "detail": "Human-readable error message"
}
```

### Pagination

Endpoints that return lists support:
- `page` (default: 1)
- `page_size` (default: 50, max: 200)

Response includes `total`, `page`, `page_size` for client-side paging.

---

## Safety Design

Milestone follows a **safe-by-default philosophy**:

1. **Read-only mode by default** — `WRITE_MODE` defaults to `false`. Without it, all endpoints that modify files on disk reject requests.
2. **Quarantine instead of delete** — The UI workflow moves files to `.quarantine/` rather than permanently deleting them.
3. **Atomic file writes** — The copier always writes to a `.tmp` staging file and uses a single atomic `os.replace()` call to move it to the final destination. There is no window where both source and destination are simultaneously absent.
4. **Per-file transactional commits** — Quarantine and restore commit each file independently so a failure on file N does not corrupt the DB state of files 1 through N-1.
5. **SQLite FK enforcement** — `PRAGMA foreign_keys = ON` is set on every connection so cascaded deletes actually cascade. Without this, SQLite ignores all FK constraints by default.
6. **Preserved scan progress** — The scanner commits on cancel (not just on completion) so interrupted scans don't lose their work.
7. **Thread-safe progress callbacks** — File I/O runs in a thread pool; all asyncio operations (DB writes, task creation) are routed back to the event loop via `call_soon_threadsafe`.

---

## Build & Packaging

### Desktop App

```bash
cd apps/desktop

# Development build (no packaging)
npm run build

# Full production package (creates installer via electron-builder)
npm run package
```

The packaged app is placed in `apps/desktop/dist/` by electron-builder.

### Backend API (production deployment)

The API is designed to run locally alongside the Electron app. For standalone deployment:

```bash
cd services/api
pip install -e .
uvicorn src.main:app --host 0.0.0.0 --port 8000
```

For a Windows service, wrap with `pywin32` or `NSSM`. For a systemd service on Linux, create a standard unit file pointing to the uvicorn command.

---

## Linting & Testing

### Backend

```bash
cd services/api

# Lint (ruff — fast Python linter)
ruff check .

# Auto-fix lint issues
ruff check . --fix

# Type checking (mypy strict mode)
mypy src

# Run tests
pytest

# Run tests with coverage
pytest --cov=src --cov-report=term-missing
```

### Desktop

```bash
cd apps/desktop

# ESLint
npm run lint

# TypeScript type check (no emit)
npm run typecheck

# Jest unit tests
npm run test
```

---

## License

MIT
