# Milestone App

A media file management system that tracks your media library across multiple drives, identifies backups (and missing backups), finds duplicates, and helps you create safe backup plans. Supports **Movies, TV shows, and Audiobooks** with type-aware folder routing, failure domain analysis, drive simulation, and expert-level operations.

---

## Table of Contents

1. [Getting Started](#getting-started)
2. [Complete Usage Guide](#complete-usage-guide)
   - [Step 1: Register Your Drives](#step-1-register-your-drives)
   - [Step 2: Add Media Root Folders](#step-2-add-media-root-folders)
   - [Step 3: Scan Your Media](#step-3-scan-your-media)
   - [Step 4: Process and Link Items](#step-4-process-and-link-items)
   - [Step 5: Hash Files to Find True Duplicates](#step-5-hash-files-to-find-true-duplicates)
   - [Step 6: Review Your Library](#step-6-review-your-library)
   - [Step 7: Set Up Failure Domains](#step-7-set-up-failure-domains)
   - [Step 8: Create a Backup Plan](#step-8-create-a-backup-plan)
   - [Step 9: Execute the Plan](#step-9-execute-the-plan)
   - [Step 10: Clean Up Over-Replicated Files](#step-10-clean-up-over-replicated-files)
   - [Step 11: Simulate Drive Failures](#step-11-simulate-drive-failures)
   - [Step 12: Export Reports](#step-12-export-reports)
3. [Expert Mode](#expert-mode)
4. [Safe-by-Default Philosophy](#safe-by-default-philosophy)
5. [Troubleshooting](#troubleshooting)
6. [API Reference](#api-reference)
7. [Development Setup](#development-setup)

---

## Getting Started

### Prerequisites

- **Node.js** 18+ and npm
- **Python** 3.11+

### Installation

```bash
# 1. Clone the repository
git clone <repo-url> milestone-app
cd milestone-app

# 2. Create local config
cp .env.example .env

# 3. Install backend dependencies
cd services/api
pip install -e ".[dev]"

# 4. Install frontend dependencies
cd ../../apps/desktop
npm install
```

### Starting the App

Open **two terminal windows**:

```bash
# Terminal 1 — Start the API server (must start first)
cd services/api
python -m uvicorn src.main:app --host 127.0.0.1 --port 8000
# Wait for: "Uvicorn running on http://127.0.0.1:8000"
```

```bash
# Terminal 2 — Start the frontend
cd apps/desktop
npm run dev:renderer
# Wait for: "VITE ready" and "Local: http://localhost:5173/"
```

Open **http://localhost:5173** in your browser.

---

## Complete Usage Guide

This guide walks you through the complete workflow from a fresh install to a fully backed-up and analyzed media library. Follow these steps in order.

### Step 1: Register Your Drives

Before Milestone can do anything, it needs to know about your drives.

1. Open the app and click **"Drives"** in the sidebar.
2. Click the **"Register Drive"** button.
3. Enter the **mount path** of a drive:
   - **Windows**: `D:\`, `E:\`, `F:\` etc.
   - **Linux/Mac**: `/mnt/media1`, `/Volumes/MediaDrive`, etc.
4. Click **Register**. Milestone will:
   - Verify the path exists.
   - Read the drive's volume serial number and label.
   - Record the drive's free space and total capacity.
5. **Repeat** for every drive that contains media you want to track.

> **Example**: If you have media on drives `D:\`, `E:\`, and `F:\`, register all three. Even if a drive only has a backup copy of your media, register it—Milestone needs to see every copy to assess redundancy.

**What the Drives screen shows you:**
Each registered drive shows its label, mount path, free space vs total, and when it was registered. You can delete a drive from tracking if needed (this does not delete any files).

---

### Step 2: Add Media Root Folders

Each drive can have one or more **root folders**—the top-level directories where your media lives.

1. Go to **"Roots"** in the sidebar.
2. Click **"Add Root"**.
3. Select the **drive** this root belongs to.
4. Enter the **full path** to the media folder on that drive:
   - Example: `D:\Movies`, `E:\TV Shows`, `F:\Media\Backup`
5. Click **Create**.
6. **Repeat** for every media folder on every drive.

> **Tip**: If a drive has media in multiple folders (e.g., `D:\Movies` and `D:\TV Shows`), add each folder as a separate root. If all media is at the drive root, just add the drive root itself (e.g., `D:\`).

> **Exclusions**: If you want to register a root but temporarily skip it during scans, you can mark it as "excluded." Excluded roots are remembered but not scanned.

---

### Step 3: Scan Your Media

Now tell Milestone to discover all the media files in your registered roots.

1. Go to **"Scan"** in the sidebar.
2. Select which **drive** to scan (or scan all).
3. Click **"Start Scan"**.
4. Milestone will:
   - Walk through every registered root folder on that drive.
   - Index every file it finds (name, path, size, extension, modification date).
   - Show real-time progress (files scanned, current directory).
5. **Wait for the scan to complete.** Large libraries (10,000+ files) may take several minutes.

**Scan controls:**
- **Pause**: Temporarily stop the scan. Resume later from where it left off.
- **Resume**: Continue a paused scan.
- **Cancel**: Abort the scan entirely.
- **Throttle**: Slow the scan down to reduce disk I/O if the drive is in use.

> **Important**: Scan all your drives before proceeding. Milestone determines backup coverage by comparing files across drives—it can only find backups if it has scanned the drive that contains them.

---

### Step 4: Process and Link Items

After scanning, Milestone has a list of raw files. Now it needs to **group those files into media items** (matching the same movie or episode across different drives).

1. Go to **"Dashboard"**.
2. Click **"Process Items"** (the button appears after a scan).
3. Milestone will:
   - Parse file names using naming conventions (title, year, season, episode).
   - Group files that represent the same media item.
   - Link files across drives. For example, `D:\Movies\Inception (2010).mkv` and `E:\Backup\Inception (2010).mkv` become one media item with **2 copies**.

The dashboard now shows your **copy count distribution**:
- **0 copies**: Items in the database that have no files on disk (data loss!).
- **1 copy**: Items with only one copy (at risk—if that drive fails, the file is gone).
- **2 copies**: Items with a backup (safe).
- **3+ copies**: Items with multiple backups (possibly over-replicated and wasting space).

> **Goal**: You want most of your library at **2 copies**. Items at 0–1 copies need backups. Items at 3+ copies may be wasting space.

---

### Step 5: Hash Files to Find True Duplicates

File name matching isn't 100% reliable. Two files with the same name might be different (different quality, format, edit), and files with different names might be identical. **Hashing** creates a content fingerprint for each file.

1. On the **Dashboard**, click **"Start Hashing"**.
2. Milestone will:
   - Generate a **quick signature** first (fast—reads only a small portion of each file).
   - Files with matching quick signatures get a **full hash** (reads the entire file—slower but definitive).
3. After hashing:
   - Items that were separate but have identical hashes get **merged** automatically.
   - Items that were grouped but have different hashes get **split** back apart.

> **This step is optional but strongly recommended.** Name-based matching works for most well-organized libraries, but hashing guarantees accuracy.

---

### Step 6: Review Your Library

Now that your library is indexed and deduplicated, explore it:

1. **Dashboard**: Overview of your library. Shows total items, copy count distribution (color-coded), and quick action buttons.

2. **Items**: Full browsable list of all media items. Use the filters at the top:
   - **Type filter**: Movies, TV episodes, Audiobooks.
   - **Copy count filter**: Show only items with exactly N copies (e.g., "1 copy" shows items that need backup).
   - **Status filter**: Filter by processing status.
   - **Search**: Find specific items by title.

3. **Item Detail** (click any item): Shows:
   - All copies of this item and which drive each copy is on.
   - File sizes, paths, hash status.
   - Which copy is the "primary" one.

4. **Library**: High-level library overview with aggregate statistics.

---

### Step 7: Set Up Failure Domains

Drives can fail in groups. If two drives are in the same NAS enclosure and that NAS dies, you lose both. **Failure Domains** let you group drives by shared risk.

1. Go to **"Domains"** in the sidebar.
2. Click **"Create Domain"**.
3. Give it a name describing the risk group:
   - `"Office NAS"` — for drives in your NAS at home.
   - `"Offsite Backup"` — for drives stored elsewhere.
   - `"USB Externals"` — for portable drives.
4. **Assign drives** to domains. Each drive can belong to one domain.

**Why this matters:**
An item with 2 copies is only safe if those copies are in **different** failure domains. If both copies are on drives in the same NAS, a single NAS failure loses both. Milestone will flag these items as at-risk even though they technically have 2 copies.

---

### Step 8: Create a Backup Plan

Now you know which items need backups. Milestone can create a plan automatically.

1. Go to **"Plans"** in the sidebar.
2. Click **"Create Copy Plan"**.
3. Milestone will:
   - Find all items with 0–1 copies.
   - For each, pick the best destination drive (most free space, different failure domain).
   - Generate a list of proposed copy operations.
4. **Review the plan** before committing:
   - Each row shows: source file → destination drive → destination path.
   - Toggle individual items on/off using the checkboxes if you don't want to copy specific items.
   - The plan shows total data to be copied and estimated time.

> **Nothing has been copied yet.** Plans are preview-only until you confirm them.

**Type-aware folder routing**: When Milestone copies a file to a destination drive, it automatically places it in the correct folder based on media type:
- Movies → `{drive}/Movies/`
- TV episodes → `{drive}/TV/` (preserving show/season subfolders)
- Audiobooks → `{drive}/Audiobooks/`

This mapping is configurable in `config.py` via `type_folder_map`.

**Reduction plans** work the same way but in reverse—they find items with 3+ copies and suggest which extras to remove (quarantine, not delete).

---

### Step 9: Execute the Plan

Once you're happy with the plan:

1. **Enable write mode** (required for any file operations):
   ```
   # Edit your .env file:
   WRITE_MODE=true
   ```
   Then restart the API server.

2. In the **Plans** screen, click **"Confirm Plan"**.
3. This converts the plan into queued **Operations**.
4. Go to **"Operations"** in the sidebar. You'll see your copy jobs listed.
5. Click **"Start Queue"** to begin processing.
6. Milestone will:
   - Copy each file to its destination.
   - **Verify** the copy by comparing hashes (enabled by default).
   - Update the database so your copy counts increase.
   - Show real-time progress for each operation.

**Queue controls:**
- **Pause Queue**: Stop processing after the current operation finishes.
- **Resume Queue**: Continue processing.
- **Stop Queue**: Stop the queue worker.
- **Concurrency**: Set how many copy operations run simultaneously (1–10, default 2).
- **Per-operation controls**: Pause, resume, or cancel individual operations.

> **Tip**: Start with concurrency = 1 if copying to a single drive, or 2 if copying to multiple drives simultaneously.

---

### Step 10: Clean Up Over-Replicated Files

After making backups, you might find items with 3+ copies that waste space.

1. Go to **"Cleanup"** in the sidebar.
2. Milestone shows **deletion recommendations** for items with 3+ copies.
3. For each item, it recommends which copy to remove based on:
   - Keep files on preferred drives.
   - Keep the primary copy.
   - Remove duplicates on non-preferred drives.
4. **Quarantine** (not delete): Select files to quarantine and click **"Quarantine Selected"**.
   - Files are moved to `{drive}/.quarantine/{date}/{original_path}`.
   - This is **reversible**—you can restore quarantined files to their original locations.
5. After verifying everything is fine, you can permanently delete the quarantine folder.

> **Safety**: Cleanup never auto-deletes. It only recommends. You review and approve every action. Quarantine is reversible. Permanent deletion is a separate manual step.

---

### Step 11: Simulate Drive Failures

Want to know what happens if a drive dies?

1. Go to **"Simulation"** in the sidebar.
2. Select a drive to simulate its failure.
3. Click **"Run Simulation"**.
4. Milestone shows:
   - Which items would be **lost entirely** (their only copy was on that drive).
   - Which items would drop to **1 copy** (still surviving but now at risk).
   - Which items are **unaffected** (they have copies on other drives).
   - Total data at risk.

> **This is read-only.** Simulation never modifies any files. It's purely analytical.

---

### Step 12: Export Reports

Download CSV reports for offline analysis or record-keeping:

1. Go to **"Exports"** in the sidebar (or use the Dashboard export links).
2. Available reports:
   - **At-Risk Report**: Items with 0–1 copies — your "need to back up" list.
   - **Full Inventory**: Every item and every file location — complete catalog.
   - **Duplicates Report**: Items with 3+ copies — your "clean up" list.

---

## Expert Mode

Expert Mode unlocks advanced, potentially destructive operations. It is **OFF by default** and must be explicitly activated.

### Why Expert Mode Exists

The features behind Expert Mode can cause data loss if used carelessly (e.g., drive evacuation moves files, batch reduction deletes copies). Normal users should never need them. Expert Mode exists for power users who understand the risks and need advanced control.

### Activating Expert Mode

1. Click **"Settings"** in the sidebar (always visible at the bottom).
2. In the Expert Mode section, click **"Enable Expert Mode"**.
3. Type the exact confirmation phrase:
   ```
   I UNDERSTAND THIS SOFTWARE CAN CAUSE IRREVERSIBLE DATA LOSS
   ```
4. *(Optional)* Check **"Persist across restarts"** to keep Expert Mode active after server restarts.
5. Click **"Activate"**.

**What changes:**
- A red **EXPERT MODE** banner appears in the sidebar.
- Three new navigation items appear under "Expert": **Analytics**, **Recovery**, **Evacuation**.
- Additional endpoints become available in the API.

### Deactivating Expert Mode

Go to **Settings** → click **"Deactivate Expert Mode"**. Or just restart the API server (Expert Mode is session-scoped by default).

### Expert Mode via API

```bash
# Check status
curl http://127.0.0.1:8000/expert/status

# Activate
curl -X POST http://127.0.0.1:8000/expert/activate \
  -H "Content-Type: application/json" \
  -d '{"phrase":"I UNDERSTAND THIS SOFTWARE CAN CAUSE IRREVERSIBLE DATA LOSS","persist":false}'

# Deactivate
curl -X POST http://127.0.0.1:8000/expert/deactivate
```

### Expert-Only Features

**Analytics** — Redundancy heatmap showing drive utilization and per-item risk scoring with distribution summary (critical/high/medium/low counts).

**Recovery** — Orphan file detection (files in the database but missing from disk, or files on disk not in the database), one-click repair actions, and a full audit log of all system operations.

**Evacuation** — Plan and execute drive evacuation (move all items off a drive before retiring/replacing it). Shows risk analysis and suggested destinations.

**Also available with Expert Mode:**
- **Advanced Copy**: Hardlink/reflink creation, filesystem capability detection.
- **Placement**: Pin items to specific drives, set target copy counts.
- **Batch Reduction**: Preview and execute bulk reduction of over-replicated items.
- **Library Normalization**: Rename/reorganize files to follow a canonical naming scheme.
- **Safety Overrides**: Temporarily override per-operation safety checks.
- **Extended Simulation**: Multi-failure scenarios, domain-failure simulation.

---

## Safe-by-Default Philosophy

Milestone runs in **read-only mode by default**. No files are modified, moved, or deleted unless you explicitly enable it.

| Safety Layer | Default | What It Controls |
|---|---|---|
| `WRITE_MODE` env var | `false` | All file write/copy/move/delete operations |
| Expert Mode | Inactive | Advanced/destructive features |
| Confirmation phrase | Required | Prevents accidental Expert Mode activation |
| Quarantine (not delete) | Always | Cleanup moves files to quarantine, not recycle bin |
| Plan review | Required | All bulk operations require review before execution |
| Hash verification | On | Copies are verified by comparing file hashes |
| Audit log | Always on | All Expert Mode actions are recorded |

---

## Troubleshooting

### Expert Mode appears active on startup

Expert Mode is stored in server memory. If you activated it and didn't restart the server, it remains active. **Restart the API server** to reset it. If you activated with `persist=true`, deactivate explicitly:
```bash
curl -X POST http://127.0.0.1:8000/expert/deactivate
```

### Copy operations are blocked

Make sure `WRITE_MODE=true` is set in `.env` and the API server was restarted after the change.

### Scan finds no files

Check that: (1) drives are registered and the mount paths exist, (2) root folders have been added to those drives, and (3) the root folders are not marked as "excluded."

### Analytics returns errors

Analytics endpoints require data. Register drives, add roots, and run a scan first.

### "Cannot find module 'react'" in IDE

Install frontend dependencies: `cd apps/desktop && npm install`

---

## API Reference

Interactive API documentation is available when the server is running:
- **Swagger UI**: http://127.0.0.1:8000/docs
- **ReDoc**: http://127.0.0.1:8000/redoc

---

## Development Setup

### Project Structure

```
milestone-app/
├── apps/desktop/       # Electron + React frontend
├── services/api/       # Python FastAPI backend
│   └── src/
│       ├── main.py     # App entry point
│       ├── routers/    # API endpoint handlers
│       ├── scanner.py  # File scanning engine
│       ├── matcher.py  # Media item matching
│       ├── copier.py   # File copy operations
│       ├── hasher.py   # File hashing
│       ├── queue.py    # Operations queue
│       └── expert.py   # Expert Mode state
├── packages/shared/    # Shared TypeScript types
└── docs/               # Architecture docs
```

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `WRITE_MODE` | `false` | Enable file write operations |
| `API_HOST` | `127.0.0.1` | API server bind address |
| `API_PORT` | `8000` | API server port |
| `ELECTRON_DEV_TOOLS` | `false` | Show Electron DevTools |
| `LOG_LEVEL` | `info` | Logging level |

### Build Commands

```bash
# Desktop App
cd apps/desktop
npm run build          # Build for production
npm run package        # Package Electron app

# Linting & Testing
cd apps/desktop
npm run lint           # ESLint
npm run typecheck      # TypeScript check
npm run test           # Jest tests

cd services/api
ruff check .           # Python linting
mypy src               # Type checking
pytest                 # Run tests
```

---

## License

MIT
