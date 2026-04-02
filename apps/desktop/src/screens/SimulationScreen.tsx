import { useState, useEffect, useMemo, useCallback } from 'react';
import { simulationApi, SimulationResult, SimDrive, SimDomain } from '../api';
import './Screens.css';

type ScopeType = 'drive' | 'domain';
type SortKey = 'severity' | 'title' | 'type' | 'remaining_copies' | 'size_bytes';
type SortDir = 'asc' | 'desc';

const SEVERITY_ORDER: Record<string, number> = {
    lost: 0,
    degraded_1_copy: 1,
    degraded_domain: 2,
    still_safe: 3,
    unaffected: 4,
};

const SEVERITY_META: Record<string, { label: string; icon: string; color: string }> = {
    lost:             { label: 'Lost Entirely',      icon: '🔴', color: '#f44336' },
    degraded_1_copy:  { label: 'Drops to 1 Copy',   icon: '🟠', color: '#ff5722' },
    degraded_domain:  { label: 'Single Domain Risk', icon: '🟡', color: '#ff9800' },
    still_safe:       { label: 'Still Safe',          icon: '🟢', color: '#4caf50' },
    unaffected:       { label: 'Unaffected',          icon: '⚪', color: '#888' },
};

function formatBytes(bytes: number | null): string {
    if (!bytes) return '—';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let v = bytes, u = 0;
    while (v >= 1024 && u < units.length - 1) { v /= 1024; u++; }
    return `${v.toFixed(1)} ${units[u]}`;
}

export function SimulationScreen() {
    const [scopeType, setScopeType] = useState<ScopeType>('drive');
    const [drives, setDrives] = useState<SimDrive[]>([]);
    const [domains, setDomains] = useState<SimDomain[]>([]);
    const [selectedId, setSelectedId] = useState<number | null>(null);
    const [result, setResult] = useState<SimulationResult | null>(null);
    const [loading, setLoading] = useState(false);
    const [loadingPicker, setLoadingPicker] = useState(true);
    const [error, setError] = useState<string | null>(null);

    // Table controls
    const [sortKey, setSortKey] = useState<SortKey>('severity');
    const [sortDir, setSortDir] = useState<SortDir>('asc');
    const [filterSeverity, setFilterSeverity] = useState<string>('all');

    const loadPicker = useCallback(async () => {
        try {
            setLoadingPicker(true);
            setSelectedId(null);
            setResult(null);
            if (scopeType === 'drive') {
                const res = await simulationApi.listDrives();
                setDrives(res.drives);
            } else {
                const res = await simulationApi.listDomains();
                setDomains(res.domains);
            }
            setError(null);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to load picker');
        } finally {
            setLoadingPicker(false);
        }
    }, [scopeType]);

    useEffect(() => {
        loadPicker();
    }, [loadPicker]);

    const runSimulation = async () => {
        if (!selectedId) return;
        try {
            setLoading(true);
            setError(null);
            const res = scopeType === 'drive'
                ? await simulationApi.runDrive(selectedId)
                : await simulationApi.runDomain(selectedId);
            setResult(res);
            setSortKey('severity');
            setFilterSeverity('all');
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Simulation failed');
        } finally {
            setLoading(false);
        }
    };

    const handleExport = async (format: 'csv' | 'json' | 'checklist') => {
        if (!selectedId || !result) return;
        try {
            const url = scopeType === 'drive'
                ? `http://127.0.0.1:8000/simulation/drive/${selectedId}/export?format=${format}`
                : `http://127.0.0.1:8000/simulation/domain/${selectedId}/export?format=${format}`;
            window.open(url, '_blank');
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Export failed');
        }
    };

    const handleSort = (key: SortKey) => {
        if (sortKey === key) {
            setSortDir(d => d === 'asc' ? 'desc' : 'asc');
        } else {
            setSortKey(key);
            setSortDir('asc');
        }
    };

    const sortedItems = useMemo(() => {
        if (!result) return [];
        let items = [...result.items];
        if (filterSeverity !== 'all') {
            items = items.filter(i => i.severity === filterSeverity);
        }
        items.sort((a, b) => {
            let diff = 0;
            switch (sortKey) {
                case 'severity':
                    diff = (SEVERITY_ORDER[a.severity] ?? 99) - (SEVERITY_ORDER[b.severity] ?? 99);
                    break;
                case 'title':
                    diff = (a.title ?? '').localeCompare(b.title ?? '');
                    break;
                case 'type':
                    diff = (a.type ?? '').localeCompare(b.type ?? '');
                    break;
                case 'remaining_copies':
                    diff = a.remaining_copies - b.remaining_copies;
                    break;
                case 'size_bytes':
                    diff = (a.size_bytes ?? 0) - (b.size_bytes ?? 0);
                    break;
            }
            return sortDir === 'asc' ? diff : -diff;
        });
        return items;
    }, [result, sortKey, sortDir, filterSeverity]);

    const SortTh = ({ col, label }: { col: SortKey; label: string }) => (
        <th
            onClick={() => handleSort(col)}
            style={{ cursor: 'pointer', userSelect: 'none', whiteSpace: 'nowrap' }}
        >
            {label} {sortKey === col ? (sortDir === 'asc' ? '↑' : '↓') : ''}
        </th>
    );


    return (
        <div className="screen">
            <div className="screen-header">
                <h2>🧨 Drive Failure Simulation</h2>
                <p className="subtitle">
                    Model the consequences of losing a drive or failure domain before it happens.
                    Identify at-risk items and export a remediation checklist.
                </p>
            </div>

            {error && <div className="error-banner">{error}</div>}

            {/* Controls */}
            <div className="sim-controls">
                <div className="sim-scope-toggle">
                    <button
                        id="scope-drive-btn"
                        className={`btn ${scopeType === 'drive' ? 'btn-primary' : 'btn-secondary'}`}
                        onClick={() => setScopeType('drive')}
                    >
                        💾 Drive
                    </button>
                    <button
                        id="scope-domain-btn"
                        className={`btn ${scopeType === 'domain' ? 'btn-primary' : 'btn-secondary'}`}
                        onClick={() => setScopeType('domain')}
                    >
                        🛡️ Failure Domain
                    </button>
                </div>

                <div className="sim-picker-row">
                    {loadingPicker ? (
                        <span className="hint">Loading…</span>
                    ) : (
                        <select
                            id="sim-target-select"
                            className="input"
                            value={selectedId ?? ''}
                            onChange={e => setSelectedId(e.target.value ? Number(e.target.value) : null)}
                        >
                            <option value="">
                                — Select a {scopeType === 'drive' ? 'drive' : 'failure domain'} to simulate —
                            </option>
                            {scopeType === 'drive' && drives.map(d => (
                                <option key={d.id} value={d.id}>
                                    {d.mount_path}{d.volume_label ? ` (${d.volume_label})` : ''}
                                    {d.domain_name ? ` · ${d.domain_name}` : ' · No domain'}
                                    {` · ${d.item_count} items`}
                                </option>
                            ))}
                            {scopeType === 'domain' && domains.map(d => (
                                <option key={d.id} value={d.id}>
                                    {d.name} — {d.drive_count} drive{d.drive_count !== 1 ? 's' : ''}, {d.item_count} items
                                </option>
                            ))}
                        </select>
                    )}
                    <button
                        id="run-sim-btn"
                        className="btn btn-primary"
                        onClick={runSimulation}
                        disabled={!selectedId || loading}
                    >
                        {loading ? '⏳ Simulating…' : '▶ Run Simulation'}
                    </button>
                </div>
            </div>

            {/* Results */}
            {result && (
                <>
                    {/* Summary cards */}
                    <div className="sim-summary-header">
                        <h3>
                            Results: Simulating failure of  <span className="sim-target-name">{result.target_label}</span>
                        </h3>
                        {result.failed_drive_count !== undefined && (
                            <span className="hint">({result.failed_drive_count} drives in domain)</span>
                        )}
                    </div>

                    <div className="sim-summary-cards">
                        <div className="sim-card sim-card-lost">
                            <span className="sim-card-value">{result.summary.lost_entirely}</span>
                            <span className="sim-card-label">🔴 Lost Entirely</span>
                        </div>
                        <div className="sim-card sim-card-degraded1">
                            <span className="sim-card-value">{result.summary.degraded_to_1_copy}</span>
                            <span className="sim-card-label">🟠 Drops to 1 Copy</span>
                        </div>
                        <div className="sim-card sim-card-degraded-domain">
                            <span className="sim-card-value">{result.summary.degraded_to_single_domain}</span>
                            <span className="sim-card-label">🟡 Single-Domain</span>
                        </div>
                        <div className="sim-card sim-card-safe">
                            <span className="sim-card-value">{result.summary.still_safe}</span>
                            <span className="sim-card-label">🟢 Still Safe</span>
                        </div>
                        <div className="sim-card sim-card-unaffected">
                            <span className="sim-card-value">{result.summary.unaffected}</span>
                            <span className="sim-card-label">⚪ Unaffected</span>
                        </div>
                    </div>

                    {/* Recommended actions */}
                    {result.recommended_actions.length > 0 && (
                        <div className="sim-actions-section">
                            <h3>Recommended Actions ({result.recommended_actions.length})</h3>
                            <div className="sim-actions-list">
                                {result.recommended_actions.slice(0, 10).map(action => (
                                    <div key={action.item_id} className={`sim-action-row sim-action-${action.action}`}>
                                        <span className="sim-action-icon">
                                            {action.action === 'already_at_risk' ? '🔴' :
                                             action.action === 'backup_before_failure' ? '🟠' : '🟡'}
                                        </span>
                                        <div className="sim-action-body">
                                            <strong>{action.item_title}</strong>
                                            <span className="hint"> — {action.reason}</span>
                                            {action.source_file && (
                                                <div className="sim-action-source">
                                                    Source: <code>{action.source_file}</code>
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                ))}
                                {result.recommended_actions.length > 10 && (
                                    <p className="hint">
                                        …and {result.recommended_actions.length - 10} more. Export the checklist for the full list.
                                    </p>
                                )}
                            </div>
                        </div>
                    )}

                    {/* Export bar */}
                    <div className="sim-export-bar">
                        <span className="hint">Export results:</span>
                        <button id="export-csv-btn" className="btn btn-sm btn-secondary" onClick={() => handleExport('csv')}>
                            📄 CSV
                        </button>
                        <button id="export-json-btn" className="btn btn-sm btn-secondary" onClick={() => handleExport('json')}>
                            { } JSON
                        </button>
                        <button id="export-checklist-btn" className="btn btn-sm btn-secondary" onClick={() => handleExport('checklist')}>
                            ✅ Retirement Checklist
                        </button>
                    </div>

                    {/* Affected items table */}
                    <div className="sim-table-section">
                        <div className="sim-table-controls">
                            <h3>Affected Items ({result.items.length})</h3>
                            <select
                                id="filter-severity-select"
                                className="input input-sm"
                                value={filterSeverity}
                                onChange={e => setFilterSeverity(e.target.value)}
                            >
                                <option value="all">All severities</option>
                                <option value="lost">Lost Entirely</option>
                                <option value="degraded_1_copy">Drops to 1 Copy</option>
                                <option value="degraded_domain">Single-Domain</option>
                                <option value="still_safe">Still Safe</option>
                            </select>
                        </div>

                        {sortedItems.length === 0 ? (
                            <div className="empty-state">
                                <p>No items match the selected filter.</p>
                            </div>
                        ) : (
                            <div className="files-table-wrapper">
                                <table className="files-table sim-table">
                                    <thead>
                                        <tr>
                                            <SortTh col="severity" label="Risk" />
                                            <SortTh col="title" label="Title" />
                                            <SortTh col="type" label="Type" />
                                            <th>Copies Before</th>
                                            <SortTh col="remaining_copies" label="Copies After" />
                                            <th>Domains After</th>
                                            <SortTh col="size_bytes" label="Lost Size" />
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {sortedItems.map(item => {
                                            const meta = SEVERITY_META[item.severity] ?? SEVERITY_META.unaffected;
                                            return (
                                                <tr key={item.id} className={`sim-row-${item.severity}`}>
                                                    <td>
                                                        <span
                                                            className="sim-severity-badge"
                                                            style={{ color: meta.color }}
                                                        >
                                                            {meta.icon} {meta.label}
                                                        </span>
                                                    </td>
                                                    <td className="sim-title-cell">{item.title}</td>
                                                    <td>{item.type === 'movie' ? '🎬' : '📺'} {item.type}</td>
                                                    <td>{item.current_copies}</td>
                                                    <td style={{ color: item.remaining_copies === 0 ? '#f44336' : '#e0e0e0' }}>
                                                        {item.remaining_copies}
                                                    </td>
                                                    <td>{item.remaining_distinct_domains}</td>
                                                    <td className="size-cell">{formatBytes(item.size_bytes)}</td>
                                                </tr>
                                            );
                                        })}
                                    </tbody>
                                </table>
                            </div>
                        )}
                    </div>
                </>
            )}

            {!result && !loading && (
                <div className="sim-idle-state">
                    <div className="sim-idle-icon">🧨</div>
                    <p>Select a drive or failure domain above and click <strong>Run Simulation</strong>.</p>
                    <p className="hint">
                        The simulation shows exactly which items you would lose, which would degrade,
                        and what copies you need to make before this drive is retired or fails.
                    </p>
                </div>
            )}
        </div>
    );
}
