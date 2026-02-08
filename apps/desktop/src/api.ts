/**
 * API client for backend communication
 */

const API_BASE = 'http://127.0.0.1:8000';

async function request<T>(
    method: string,
    path: string,
    body?: unknown
): Promise<T> {
    const options: RequestInit = {
        method,
        headers: {
            'Content-Type': 'application/json',
        },
    };

    if (body) {
        options.body = JSON.stringify(body);
    }

    const response = await fetch(`${API_BASE}${path}`, options);

    if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
        throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
}

// Types
export interface Drive {
    id: number;
    mount_path: string;
    volume_serial: string | null;
    volume_label: string | null;
    created_at: string;
    free_space: number | null;
    total_space: number | null;
}

export interface Root {
    id: number;
    drive_id: number;
    path: string;
    excluded: boolean;
    created_at: string;
}

export interface FileItem {
    id: number;
    root_id: number;
    path: string;
    size: number | null;
    mtime: number | null;
    ext: string | null;
    last_seen: string | null;
    quick_sig?: string | null;
    full_hash?: string | null;
    hash_status?: string;
}

export interface ScanStatus {
    state: 'idle' | 'running' | 'paused' | 'cancelled' | 'completed';
    current_root: string | null;
    files_scanned: number;
    files_total: number | null;
    files_new: number;
    files_updated: number;
    files_missing: number;
    started_at: string | null;
    eta_seconds: number | null;
}

export interface FileStats {
    total_files: number;
    total_size: number;
    by_extension: { ext: string; count: number; size: number }[];
}

export interface MediaItem {
    id: number;
    type: 'movie' | 'tv_episode' | 'unknown';
    title: string | null;
    year: number | null;
    season: number | null;
    episode: number | null;
    status: 'auto' | 'verified' | 'needs_verification';
    created_at: string;
    copy_count: number;
}

export interface MediaItemDetail extends MediaItem {
    files: {
        id: number;
        path: string;
        size: number | null;
        ext: string | null;
        quick_sig: string | null;
        full_hash: string | null;
        hash_status: string;
        is_primary: boolean;
        root_path: string;
        drive_path: string;
    }[];
}

export interface ItemStats {
    total_items: number;
    by_type: Record<string, number>;
    by_copy_count: Record<number, number>;
    needs_verification: number;
}

export interface HashStatus {
    state: 'idle' | 'running' | 'complete' | 'stopped';
    files_total: number;
    files_processed: number;
    current_file: string | null;
    queue_size: number;
}

// API functions
export const api = {
    // Drives
    async getDrives(): Promise<{ drives: Drive[] }> {
        return request('GET', '/drives');
    },

    async registerDrive(mountPath: string): Promise<Drive> {
        return request('POST', '/drives/register', { mount_path: mountPath });
    },

    async deleteDrive(id: number): Promise<void> {
        return request('DELETE', `/drives/${id}`);
    },

    // Roots
    async getRoots(driveId?: number): Promise<{ roots: Root[] }> {
        const query = driveId ? `?drive_id=${driveId}` : '';
        return request('GET', `/roots${query}`);
    },

    async createRoot(driveId: number, path: string): Promise<Root> {
        return request('POST', '/roots', { drive_id: driveId, path });
    },

    async deleteRoot(id: number): Promise<void> {
        return request('DELETE', `/roots/${id}`);
    },

    async updateRoot(id: number, excluded: boolean): Promise<Root> {
        return request('PATCH', `/roots/${id}?excluded=${excluded}`);
    },

    // Scan
    async startScan(driveId?: number, throttle: string = 'normal'): Promise<ScanStatus> {
        return request('POST', '/scan/start', { drive_id: driveId, throttle });
    },

    async getScanStatus(): Promise<ScanStatus> {
        return request('GET', '/scan/status');
    },

    async controlScan(action: 'pause' | 'resume' | 'cancel'): Promise<ScanStatus> {
        return request('POST', '/scan/control', { action });
    },

    // Files
    async getFiles(params: Record<string, unknown> = {}): Promise<{ files: FileItem[]; total: number; page: number; page_size: number }> {
        const query = new URLSearchParams();
        Object.entries(params).forEach(([key, value]) => {
            if (value !== undefined) query.set(key, String(value));
        });
        return request('GET', `/files?${query}`);
    },

    async getFileStats(): Promise<FileStats> {
        return request('GET', '/files/stats');
    },

    // Media Items
    async getItems(params: {
        type?: string;
        min_copies?: number;
        max_copies?: number;
        status?: string;
        search?: string;
        page?: number;
        page_size?: number;
    } = {}): Promise<{ items: MediaItem[]; total: number; page: number; page_size: number }> {
        const query = new URLSearchParams();
        Object.entries(params).forEach(([key, value]) => {
            if (value !== undefined) query.set(key, String(value));
        });
        return request('GET', `/items?${query}`);
    },

    async getItem(id: number): Promise<MediaItemDetail> {
        return request('GET', `/items/${id}`);
    },

    async getItemStats(): Promise<ItemStats> {
        return request('GET', '/items/stats');
    },

    async mergeItems(targetId: number, sourceIds: number[]): Promise<{ target_id: number; files_moved: number; items_merged: number }> {
        return request('POST', `/items/merge?target_id=${targetId}`, sourceIds);
    },

    async splitFile(fileId: number): Promise<{ old_item_id: number; new_item_id: number; file_id: number }> {
        return request('POST', `/items/split?file_id=${fileId}`);
    },

    async processItems(): Promise<{ processed: number; new_items: number; linked: number; skipped: number }> {
        return request('POST', '/items/process');
    },

    async updateItem(id: number, updates: Partial<Pick<MediaItem, 'title' | 'year' | 'season' | 'episode' | 'type'>>): Promise<{ message: string; id: number }> {
        const query = new URLSearchParams();
        Object.entries(updates).forEach(([key, value]) => {
            if (value !== undefined) query.set(key, String(value));
        });
        return request('PATCH', `/items/${id}?${query}`);
    },

    // Hashing
    async startHashing(fileIds?: number[]): Promise<{ message: string; status: HashStatus }> {
        return request('POST', '/hash/compute', fileIds);
    },

    async getHashStatus(): Promise<HashStatus> {
        return request('GET', '/hash/status');
    },

    async stopHashing(): Promise<{ stopped: boolean }> {
        return request('POST', '/hash/stop');
    },

    async hashFile(fileId: number): Promise<{ file_id: number; quick_sig: string | null; full_hash: string | null; status: string }> {
        return request('POST', `/hash/file/${fileId}`);
    },

    // Health
    async getHealth(): Promise<{ status: string; write_mode: boolean }> {
        return request('GET', '/health');
    },
};
