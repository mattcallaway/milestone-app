-- SQLite schema for Milestone 1

-- drives: registered storage drives
CREATE TABLE IF NOT EXISTS drives (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mount_path TEXT UNIQUE NOT NULL,
    volume_serial TEXT,
    volume_label TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- roots: folders to scan within drives
CREATE TABLE IF NOT EXISTS roots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    drive_id INTEGER NOT NULL,
    path TEXT NOT NULL,
    excluded INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (drive_id) REFERENCES drives(id) ON DELETE CASCADE,
    UNIQUE(drive_id, path)
);

-- files: scanned file metadata
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    root_id INTEGER NOT NULL,
    path TEXT NOT NULL,
    size INTEGER,
    mtime REAL,
    ext TEXT,
    last_seen TIMESTAMP,
    signature_stub TEXT,
    FOREIGN KEY (root_id) REFERENCES roots(id) ON DELETE CASCADE,
    UNIQUE(root_id, path)
);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_files_root_id ON files(root_id);
CREATE INDEX IF NOT EXISTS idx_files_ext ON files(ext);
CREATE INDEX IF NOT EXISTS idx_files_last_seen ON files(last_seen);
CREATE INDEX IF NOT EXISTS idx_roots_drive_id ON roots(drive_id);

-- settings: key-value config
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
