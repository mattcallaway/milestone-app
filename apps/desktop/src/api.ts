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
    domain_id: number | null;
    domain_name: string | null;
}

export interface FailureDomain {
    id: number;
    name: string;
    description: string | null;
    created_at: string;
    drives?: { id: number; mount_path: string; volume_label: string | null }[];
}

export type ResilienceState =
    | 'unsafe_no_backup'
    | 'unsafe_single_domain'
    | 'safe_two_domains'
    | 'over_replicated_but_fragile'
    | 'over_replicated_and_resilient';

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
    resilience_state: ResilienceState | null;
    domain_mapping_complete: boolean;
}

export interface MediaItemDetail extends MediaItem {
    distinct_domains: number;
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
        domain_id: number | null;
        domain_name: string | null;
    }[];
}

export interface ItemStats {
    total_items: number;
    by_type: Record<string, number>;
    by_copy_count: Record<number, number>;
    needs_verification: number;
    by_resilience_state: Record<ResilienceState, number>;
    incomplete_domain_mapping: number;
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

    // Operations
    async getOperations(params: {
        status?: string;
        type?: string;
        page?: number;
        page_size?: number;
    } = {}): Promise<{ operations: Operation[]; total: number; page: number; page_size: number }> {
        const query = new URLSearchParams();
        Object.entries(params).forEach(([key, value]) => {
            if (value !== undefined) query.set(key, String(value));
        });
        return request('GET', `/ops?${query}`);
    },

    async getOperation(id: number): Promise<Operation> {
        return request('GET', `/ops/${id}`);
    },

    async getQueueStatus(): Promise<QueueStatus> {
        return request('GET', '/ops/queue/status');
    },

    async startQueue(): Promise<{ message: string; status: QueueStatus }> {
        return request('POST', '/ops/queue/start');
    },

    async stopQueue(): Promise<{ message: string; status: QueueStatus }> {
        return request('POST', '/ops/queue/stop');
    },

    async pauseQueue(): Promise<{ message: string; status: QueueStatus }> {
        return request('POST', '/ops/queue/pause');
    },

    async resumeQueue(): Promise<{ message: string; status: QueueStatus }> {
        return request('POST', '/ops/queue/resume');
    },

    async createCopy(params: {
        source_file_id: number;
        dest_drive_id?: number;
        dest_path?: string;
        verify_hash?: boolean;
    }): Promise<{ message: string; operation: Operation }> {
        return request('POST', '/ops/copy', params);
    },

    async createBatchCopy(params: {
        media_item_id: number;
        verify_hash?: boolean;
    }): Promise<{ message: string; operations: Operation[]; errors: { file_id: number; error: string }[] }> {
        return request('POST', '/ops/copy/batch', params);
    },

    async getDestinations(fileId: number): Promise<{ drives: Drive[] }> {
        return request('GET', `/ops/destinations/${fileId}`);
    },

    async pauseOperation(id: number): Promise<{ message: string; id: number }> {
        return request('POST', `/ops/${id}/pause`);
    },

    async resumeOperation(id: number): Promise<{ message: string; id: number }> {
        return request('POST', `/ops/${id}/resume`);
    },

    async cancelOperation(id: number): Promise<{ message: string; id: number }> {
        return request('POST', `/ops/${id}/cancel`);
    },
};

// Operation types
export interface Operation {
    id: number;
    type: 'copy' | 'move' | 'delete';
    status: 'pending' | 'running' | 'paused' | 'completed' | 'failed' | 'cancelled';
    source_file_id: number | null;
    source_path?: string;
    dest_drive_id: number | null;
    dest_path: string | null;
    dest_drive_path?: string;
    progress: number;
    total_size: number | null;
    verify_hash: boolean;
    error: string | null;
    created_at: string;
    started_at: string | null;
    completed_at: string | null;
}

export interface QueueStatus {
    running: boolean;
    paused: boolean;
    concurrency: number;
    active_count: number;
    pending_count: number;
    running_count: number;
}

// Cleanup types
export interface CleanupFileToDelete {
    id: number;
    path: string;
    size: number | null;
    drive: string;
}

export interface CleanupRecommendation {
    item_id: number;
    title: string | null;
    type: string;
    total_copies: number;
    keep_count: number;
    delete_count: number;
    savings_bytes: number;
    files_to_delete: CleanupFileToDelete[];
    files_to_keep: { id: number; path: string; drive: string }[];
}

export interface CleanupRecommendationsResponse {
    recommendations: CleanupRecommendation[];
    total_items: number;
    total_files_to_delete: number;
    total_savings_bytes: number;
    total_savings_gb: number;
}

// Cleanup API
export const cleanupApi = {
    async getRecommendations(minCopies: number = 3): Promise<CleanupRecommendationsResponse> {
        return request('GET', `/cleanup/recommendations?min_copies=${minCopies}`);
    },

    async quarantineFiles(fileIds: number[]): Promise<{
        moved: number;
        errors: number;
        files: { file_id: number; original_path: string; quarantine_path: string }[];
        error_details: { file_id: number; error: string }[];
    }> {
        return request('POST', '/cleanup/quarantine', { file_ids: fileIds });
    },

    async restoreFiles(fileIds: number[]): Promise<{
        restored: number;
        errors: number;
        files: { file_id: number; restored_path: string }[];
        error_details: { file_id: number; error: string }[];
    }> {
        return request('POST', '/cleanup/restore', fileIds);
    },

    async openInExplorer(fileId: number): Promise<{ status: string; path: string }> {
        return request('POST', `/files/${fileId}/open-explorer`);
    },

    async openFolder(fileId: number): Promise<{ status: string; folder: string }> {
        return request('POST', `/files/${fileId}/open-folder`);
    },
};

// Export functions (download CSV files)
export const exportApi = {
    getAtRiskUrl: () => `${API_BASE}/exports/at-risk`,
    getInventoryUrl: () => `${API_BASE}/exports/inventory`,
    getDuplicatesUrl: () => `${API_BASE}/exports/duplicates`,
};

// Failure Domains API
export const failureDomainApi = {
    async list(): Promise<{ domains: FailureDomain[]; unassigned_drives: number }> {
        return request('GET', '/failure-domains');
    },

    async get(id: number): Promise<FailureDomain> {
        return request('GET', `/failure-domains/${id}`);
    },

    async create(name: string, description?: string): Promise<FailureDomain> {
        return request('POST', '/failure-domains', { name, description });
    },

    async update(id: number, name?: string, description?: string): Promise<FailureDomain> {
        return request('PATCH', `/failure-domains/${id}`, { name, description });
    },

    async delete(id: number): Promise<{ message: string; id: number }> {
        return request('DELETE', `/failure-domains/${id}`);
    },

    async assignDrive(domainId: number, driveId: number): Promise<{ message: string }> {
        return request('POST', `/failure-domains/${domainId}/drives/${driveId}`);
    },

    async unassignDrive(domainId: number, driveId: number): Promise<{ message: string }> {
        return request('DELETE', `/failure-domains/${domainId}/drives/${driveId}`);
    },
};

// ── Simulation types ───────────────────────────────────────────────────────────

export interface SimDrive {
    id: number;
    mount_path: string;
    volume_label: string | null;
    domain_id: number | null;
    domain_name: string | null;
    file_count: number;
    item_count: number;
}

export interface SimDomain {
    id: number;
    name: string;
    description: string | null;
    drive_count: number;
    item_count: number;
}

export interface SimulationItem {
    id: number;
    title: string;
    type: string;
    status: string;
    severity: 'lost' | 'degraded_1_copy' | 'degraded_domain' | 'still_safe' | 'unaffected';
    current_copies: number;
    remaining_copies: number;
    current_distinct_domains: number;
    remaining_distinct_domains: number;
    size_bytes: number;
    affected_files: { file_id: number; path: string; size: number | null }[];
    surviving_files: { file_id: number; path: string; drive_id: number; domain_id: number | null }[];
}

export interface SimulationAction {
    item_id: number;
    item_title: string;
    action: string;
    reason: string;
    source_file: string | null;
    source_drive_id: number | null;
}

export interface SimulationResult {
    scope: 'drive' | 'domain';
    target_id: number;
    target_label: string;
    scope_label: string;
    failed_drive_count?: number;
    summary: {
        lost_entirely: number;
        degraded_to_1_copy: number;
        degraded_to_single_domain: number;
        still_safe: number;
        unaffected: number;
        total_affected: number;
    };
    items: SimulationItem[];
    recommended_actions: SimulationAction[];
}

// Simulation API
export const simulationApi = {
    async listDrives(): Promise<{ drives: SimDrive[] }> {
        return request('GET', '/simulation/drives');
    },

    async listDomains(): Promise<{ domains: SimDomain[] }> {
        return request('GET', '/simulation/domains');
    },

    async runDrive(driveId: number): Promise<SimulationResult> {
        return request('GET', `/simulation/drive/${driveId}`);
    },

    async runDomain(domainId: number): Promise<SimulationResult> {
        return request('GET', `/simulation/domain/${domainId}`);
    },
};

// ── Risk & Placement types ─────────────────────────────────────────────────────

export type DriveHealth = 'healthy' | 'warning' | 'degraded' | 'avoid_for_new_copies';

export interface RiskItem {
    id: number;
    title: string;
    type: string;
    resilience_state: string | null;
    copy_count: number;
    score: number;
    label: string;
    color: string;
    recommended_action: string;
    total_size_bytes: number;
    drive_ids: number[];
}

export interface RiskDriveEntry {
    drive_id: number;
    mount_path: string;
    volume_label: string | null;
    health_status: DriveHealth;
    at_risk_items: number;
}

export interface RiskSummary {
    top_risk_items: RiskItem[];
    biggest_vulnerable: RiskItem[];
    fragile_drives: RiskDriveEntry[];
}

export interface ItemRisk {
    item_id: number;
    title: string;
    score: number;
    label: string;
    color: string;
    resilience_state: string | null;
    copy_count: number;
    total_size_bytes: number;
    base_score: number;
    health_modifier: number;
    verification_modifier: number;
    domain_modifier: number;
    size_bonus: number;
    factors: string[];
    recommended_action: string;
    improvement_if_acted: number;
}

export interface PlacementSuggestion {
    drive_id: number;
    mount_path: string;
    volume_label: string | null;
    domain_id: number | null;
    health_status: DriveHealth;
    free_space: number;
    placement_score: number;
    reason: string;
}

// Risk API
export const riskApi = {
    async getSummary(limit: number = 10): Promise<RiskSummary> {
        return request('GET', `/risk/summary?limit=${limit}`);
    },

    async getItemRisk(itemId: number): Promise<ItemRisk> {
        return request('GET', `/risk/item/${itemId}`);
    },

    async setDriveHealth(driveId: number, status: DriveHealth): Promise<{ drive_id: number; health_status: DriveHealth }> {
        return request('PATCH', `/drives/${driveId}/health`, { status });
    },

    async getPlacement(itemId: number): Promise<{ item_id: number; item_title: string; resilience_state: string | null; suggestions: PlacementSuggestion[] }> {
        return request('GET', `/risk/placement/${itemId}`);
    },
};

// ── Sidecar types ─────────────────────────────────────────────────────────────

export interface SidecarFile {
    path: string;
    category: 'subtitle' | 'metadata' | 'artwork';
    ext: string;
    size?: number | null;
}

export interface SidecarCopy {
    file_id: number;
    primary_path: string;
    drive_id: number;
    drive_mount: string;
    domain_id: number | null;
    sidecars: SidecarFile[];
    sidecar_count: number;
}

export interface SidecarDriveDetail {
    sidecars: string[];
    missing: string[];
    extra: string[];
}

export interface SidecarCompleteness {
    item_id: number;
    completeness: 'complete' | 'partial' | 'no_sidecars';
    total_unique_sidecars: number;
    missing_on_any_drive: boolean;
    copy_count: number;
    all_covered_categories: string[];
    policy: Record<string, boolean>;
    drives: Record<number, SidecarDriveDetail>;
}

export interface SidecarManifestEntry {
    path: string;
    role: 'primary' | 'subtitle' | 'metadata' | 'artwork';
    size?: number | null;
}

export interface SidecarManifest {
    item_id: number;
    source_drive_id: number;
    policy: Record<string, boolean>;
    manifest: SidecarManifestEntry[];
    file_count: number;
    total_size_bytes: number;
}

// Sidecar API
export const sidecarApi = {
    async getSidecars(itemId: number): Promise<{ item_id: number; copies: SidecarCopy[] }> {
        return request('GET', `/items/${itemId}/sidecars`);
    },

    async getCompleteness(
        itemId: number,
        includeSubtitles = true,
        includeMetadata = true,
        includeArtwork = false,
    ): Promise<SidecarCompleteness> {
        const params = new URLSearchParams({
            include_subtitles: String(includeSubtitles),
            include_metadata: String(includeMetadata),
            include_artwork: String(includeArtwork),
        });
        return request('GET', `/items/${itemId}/sidecars/completeness?${params}`);
    },

    async getManifest(
        itemId: number,
        sourceDriveId: number,
        includeSubtitles = true,
        includeMetadata = true,
        includeArtwork = false,
    ): Promise<SidecarManifest> {
        const params = new URLSearchParams({
            source_drive_id: String(sourceDriveId),
            include_subtitles: String(includeSubtitles),
            include_metadata: String(includeMetadata),
            include_artwork: String(includeArtwork),
        });
        return request('GET', `/items/${itemId}/sidecars/manifest?${params}`);
    },

    async getReport(limit = 50): Promise<{
        total_scanned: number;
        complete: object[];
        partial: object[];
        no_sidecars: object[];
        summary: { complete_count: number; partial_count: number; no_sidecars_count: number };
    }> {
        return request('GET', `/sidecars/report?limit=${limit}`);
    },
};

// ── Planning types ─────────────────────────────────────────────────────────────

export type PlanType = 'protection' | 'reduction' | 'retirement';
export type PlanStatus = 'draft' | 'executed' | 'cancelled';

export interface PlanItem {
    id: number;
    plan_id: number;
    media_item_id: number;
    media_item_title: string | null;
    source_file_id: number | null;
    source_path: string | null;
    dest_drive_id: number | null;
    dest_drive_path: string | null;
    dest_domain_id: number | null;
    action: 'copy' | 'move' | 'delete';
    is_included: boolean;
    estimated_size: number | null;
}

export interface Plan {
    id: number;
    name: string;
    type: PlanType;
    status: PlanStatus;
    created_at: string;
    executed_at: string | null;
    item_count: number;
    total_size: number;
}

export interface PlanSummary {
    plan: Plan;
    items: PlanItem[];
    impact: {
        before: Record<string, number>;
        after: Record<string, number>;
    };
}

// Planning API
export const planningApi = {
    async listPlans(): Promise<Plan[]> {
        return request('GET', '/planning/plans');
    },

    async createPlan(params: {
        name: string;
        type: PlanType;
        drive_id?: number;
        min_size_gb?: number;
        min_copies?: number;
    }): Promise<number> {
        return request('POST', '/planning/plans', params);
    },

    async getPlan(id: number): Promise<PlanSummary> {
        return request('GET', `/planning/plans/${id}`);
    },

    async toggleInclusion(planItemId: number, included: boolean): Promise<void> {
        return request('PATCH', `/planning/items/${planItemId}/inclusion?included=${included}`);
    },

    async executePlan(id: number): Promise<void> {
        return request('POST', `/planning/plans/${id}/execute`);
    },
};
