import React, { useState, useEffect } from 'react';
import { evacuationApi, EvacuationPlan } from '../api';
import './Screens.css';

function formatBytes(bytes: number): string {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

export default function EvacuationScreen() {
    const [driveId, setDriveId] = useState('');
    const [plan, setPlan] = useState<EvacuationPlan | null>(null);
    const [status, setStatus] = useState<{ active: boolean; drive_id: number | null; progress: Record<string, number> | null } | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');

    const loadStatus = async () => {
        try {
            const s = await evacuationApi.status();
            setStatus(s);
        } catch (e: any) {
            setError(e.message);
        }
    };

    useEffect(() => { loadStatus(); }, []);

    const handlePlan = async () => {
        const id = parseInt(driveId);
        if (isNaN(id)) { setError('Enter a valid drive ID'); return; }
        setLoading(true);
        setError('');
        try {
            const p = await evacuationApi.plan(id);
            setPlan(p);
        } catch (e: any) {
            setError(e.message);
        } finally {
            setLoading(false);
        }
    };

    const handleExecute = async () => {
        if (!plan) return;
        const id = parseInt(driveId);
        setLoading(true);
        try {
            await evacuationApi.execute(id);
            await loadStatus();
            setPlan(null);
        } catch (e: any) {
            setError(e.message);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="screen">
            <div className="screen-header">
                <h2>🚚 Drive Evacuation</h2>
                <p className="subtitle">Safely migrate all data off a drive before removal</p>
            </div>

            {/* Active evacuation banner */}
            {status?.active && (
                <div className="analytics-alert warning">
                    <strong>🚚 Evacuation in progress</strong> — Drive #{status.drive_id}
                    {status.progress && (
                        <span> · {status.progress.completed}/{status.progress.queued} operations</span>
                    )}
                </div>
            )}

            {/* Plan form */}
            {!status?.active && (
                <div className="settings-card">
                    <h3>Plan Evacuation</h3>
                    <div className="add-form">
                        <input
                            className="input"
                            type="number"
                            value={driveId}
                            onChange={(e) => setDriveId(e.target.value)}
                            placeholder="Drive ID to evacuate"
                        />
                        <button className="btn btn-primary" onClick={handlePlan} disabled={loading}>
                            {loading ? 'Planning...' : 'Analyze Drive'}
                        </button>
                    </div>
                </div>
            )}

            {error && <p className="error-text">{error}</p>}

            {/* Plan results */}
            {plan && (
                <div className="evacuation-plan">
                    {/* Summary cards */}
                    <div className="risk-summary">
                        <div className="risk-summary-card" style={{ borderColor: '#f44336' }}>
                            <span className="risk-count" style={{ color: '#f44336' }}>{plan.summary.unique_to_drive}</span>
                            <span className="risk-label">Unique to Drive</span>
                        </div>
                        <div className="risk-summary-card" style={{ borderColor: '#ff9800' }}>
                            <span className="risk-count" style={{ color: '#ff9800' }}>{plan.summary.needs_additional_copy}</span>
                            <span className="risk-label">Need Copy</span>
                        </div>
                        <div className="risk-summary-card" style={{ borderColor: '#4caf50' }}>
                            <span className="risk-count" style={{ color: '#4caf50' }}>{plan.summary.already_safe}</span>
                            <span className="risk-label">Already Safe</span>
                        </div>
                        <div className="risk-summary-card" style={{ borderColor: '#667eea' }}>
                            <span className="risk-count" style={{ color: '#667eea' }}>{formatBytes(plan.summary.total_size)}</span>
                            <span className="risk-label">Total Size</span>
                        </div>
                    </div>

                    {/* Critical items */}
                    {plan.risk.critical.length > 0 && (
                        <div className="orphan-section">
                            <h3 style={{ color: '#f44336' }}>🔴 Critical — Only Copies on This Drive</h3>
                            <div className="items-list">
                                {plan.risk.critical.slice(0, 10).map((item: any, idx: number) => (
                                    <div key={idx} className="item-row">
                                        <div className="risk-score-badge" style={{ background: '#f44336' }}>!</div>
                                        <div className="item-info">
                                            <span className="item-title">{item.title || `Item #${item.item_id}`}</span>
                                            <span className="item-meta">{item.type} · {item.total_copies} copies</span>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Available destinations */}
                    {plan.available_destinations.length > 0 && (
                        <div className="orphan-section">
                            <h3>Available Destinations</h3>
                            <div className="items-list">
                                {plan.available_destinations.map((dest: any, idx: number) => (
                                    <div key={idx} className="item-row">
                                        <div className="item-info">
                                            <span className="item-title">{dest.mount_path}</span>
                                            <span className="item-meta">
                                                {dest.volume_label || ''} · Free: {formatBytes(dest.free_space || 0)}
                                                {dest.domain_name && ` · Domain: ${dest.domain_name}`}
                                            </span>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Execute button */}
                    <div className="expert-confirm-actions">
                        <button className="btn btn-danger btn-lg" onClick={handleExecute} disabled={loading}>
                            🚚 Execute Evacuation
                        </button>
                        <button className="btn" onClick={() => setPlan(null)}>Cancel</button>
                    </div>
                </div>
            )}
        </div>
    );
}
