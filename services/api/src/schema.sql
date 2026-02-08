-- SQLite schema for Milestone 2

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

-- files: scanned file metadata with hash fields
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    root_id INTEGER NOT NULL,
    path TEXT NOT NULL,
    size INTEGER,
    mtime REAL,
    ext TEXT,
    last_seen TIMESTAMP,
    signature_stub TEXT,
    quick_sig TEXT,
    full_hash TEXT,
    hash_status TEXT DEFAULT 'pending',
    FOREIGN KEY (root_id) REFERENCES roots(id) ON DELETE CASCADE,
    UNIQUE(root_id, path)
);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_files_root_id ON files(root_id);
CREATE INDEX IF NOT EXISTS idx_files_ext ON files(ext);
CREATE INDEX IF NOT EXISTS idx_files_last_seen ON files(last_seen);
CREATE INDEX IF NOT EXISTS idx_files_quick_sig ON files(quick_sig);
CREATE INDEX IF NOT EXISTS idx_files_full_hash ON files(full_hash);
CREATE INDEX IF NOT EXISTS idx_roots_drive_id ON roots(drive_id);

-- settings: key-value config
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

-- media_items: logical grouping of identical/same content files
CREATE TABLE IF NOT EXISTS media_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL DEFAULT 'unknown',
    title TEXT,
    year INTEGER,
    season INTEGER,
    episode INTEGER,
    status TEXT DEFAULT 'auto',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- media_item_files: join table linking files to media items
CREATE TABLE IF NOT EXISTS media_item_files (
    media_item_id INTEGER NOT NULL,
    file_id INTEGER NOT NULL,
    is_primary INTEGER DEFAULT 0,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (media_item_id, file_id),
    FOREIGN KEY (media_item_id) REFERENCES media_items(id) ON DELETE CASCADE,
    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_media_items_type ON media_items(type);
CREATE INDEX IF NOT EXISTS idx_media_items_title ON media_items(title);
CREATE INDEX IF NOT EXISTS idx_media_item_files_file ON media_item_files(file_id);

-- operations: queued file operations (copy, move, delete)
CREATE TABLE IF NOT EXISTS operations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,  -- 'copy', 'move', 'delete'
    status TEXT DEFAULT 'pending',  -- pending, running, paused, completed, failed, cancelled
    source_file_id INTEGER,
    dest_drive_id INTEGER,
    dest_path TEXT,
    progress INTEGER DEFAULT 0,  -- bytes copied
    total_size INTEGER,
    verify_hash INTEGER DEFAULT 0,  -- whether to verify with full hash
    error TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    FOREIGN KEY (source_file_id) REFERENCES files(id) ON DELETE SET NULL,
    FOREIGN KEY (dest_drive_id) REFERENCES drives(id) ON DELETE SET NULL
);

-- user_rules: destination selection preferences
CREATE TABLE IF NOT EXISTS user_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_type TEXT NOT NULL,  -- 'denylist', 'prefer_movie', 'prefer_tv', 'prefer_all'
    drive_id INTEGER,
    priority INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (drive_id) REFERENCES drives(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_operations_status ON operations(status);
CREATE INDEX IF NOT EXISTS idx_operations_source ON operations(source_file_id);
CREATE INDEX IF NOT EXISTS idx_user_rules_type ON user_rules(rule_type);
