import { useState, useEffect } from 'react';
import { riskApi, RiskSummary, RiskItem, planningApi } from '../api';
import { RISK_COLORS, HEALTH_COLORS, getRiskColor } from '../theme';
import { NavigateFunction } from '../types';
import './Screens.css';

const HEALTH_META: Record<string, { icon: string; color: string; label: string }> = {
    healthy:              { icon: '✅', color: HEALTH_COLORS.healthy, label: 'Healthy' },
    warning:              { icon: '⚠️', color: HEALTH_COLORS.warning, label: 'Warning' },
    degraded:             { icon: '🔴', color: HEALTH_COLORS.degraded, label: 'Degraded' },
    avoid_for_new_copies: { icon: '🚫', color: HEALTH_COLORS.avoid_for_new_copies, label: 'Avoid for New Copies' },
};

function RiskBar({ score }: { score: number }) {
    const pct = Math.min(100, score);
    const color = getRiskColor(score);
    return (
        <div className="risk-bar-wrapper">
            <div className="risk-bar-track">
                <div
                    className="risk-bar-fill"
                    style={{ width: `${pct}%`, background: color }}
                />
            </div>
            <span className="risk-bar-value" style={{ color }}>{score}</span>
        </div>
    );
}

function formatBytes(bytes: number | null): string {
    if (!bytes) return '—';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let v = bytes, u = 0;
    while (v >= 1024 && u < units.length - 1) { v /= 1024; u++; }
    return `${v.toFixed(1)} ${units[u]}`;
}

export function RiskScreen({ onNavigate }: { onNavigate: NavigateFunction }) {
    const [data, setData] = useState<RiskSummary | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [activeTab, setActiveTab] = useState<'top-risk' | 'biggest' | 'drives'>('top-risk');

    useEffect(() => {
        loadSummary();
    }, []);

    const loadSummary = async () => {
        try {
            setLoading(true);
            const res = await riskApi.getSummary();
            setData(res);
            setError(null);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to load risk data');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="screen">
            <div className="screen-header">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    <div>
                        <h2>📊 Risk Dashboard</h2>
                        <p className="subtitle">
                            Health-aware risk scoring across your library — showing which items need attention most urgently.
                        </p>
                    </div>
                    <div className="header-actions">
                        <button 
                            className="btn btn-primary"
                            onClick={async () => {
                                try {
                                    const name = `Protection Plan - ${new Date().toLocaleString()}`;
                                    const planId = await planningApi.createPlan({ name, type: 'protection' });
                                    onNavigate('plan-review', { planId });
                                } catch (err) {
                                    alert('Failed to create plan: ' + err);
                                }
                            }}
                        >
                            🛡️ Plan Protection
                        </button>
                    </div>
                </div>
            </div>

            {error && <div className="error-banner">{error}</div>}
            {loading && <div className="loading">Computing risk scores…</div>}

            {data && (
                <>
                    {/* Tab strip */}
                    <div className="risk-tabs">
                        <button
                            id="tab-top-risk"
                            className={`risk-tab ${activeTab === 'top-risk' ? 'active' : ''}`}
                            onClick={() => setActiveTab('top-risk')}
                        >
                            🔴 Highest Risk Items
                            <span className="risk-tab-count">{data.top_risk_items.length}</span>
                        </button>
                        <button
                            id="tab-biggest"
                            className={`risk-tab ${activeTab === 'biggest' ? 'active' : ''}`}
                            onClick={() => setActiveTab('biggest')}
                        >
                            💾 Biggest Vulnerable
                            <span className="risk-tab-count">{data.biggest_vulnerable.length}</span>
                        </button>
                        <button
                            id="tab-drives"
                            className={`risk-tab ${activeTab === 'drives' ? 'active' : ''}`}
                            onClick={() => setActiveTab('drives')}
                        >
                            💿 Fragile Drives
                            <span className="risk-tab-count">{data.fragile_drives.length}</span>
                        </button>
                    </div>

                    {/* Tab: Top Risk Items */}
                    {activeTab === 'top-risk' && (
                        <div className="risk-list">
                            {data.top_risk_items.length === 0 ? (
                                <div className="empty-state">
                                    <p>🎉 No high-risk items found!</p>
                                </div>
                            ) : (
                                data.top_risk_items.map(item => (
                                    <RiskItemRow key={item.id} item={item} />
                                ))
                            )}
                        </div>
                    )}

                    {/* Tab: Biggest Vulnerable */}
                    {activeTab === 'biggest' && (
                        <div className="risk-list">
                            {data.biggest_vulnerable.length === 0 ? (
                                <div className="empty-state">
                                    <p>No vulnerable items found.</p>
                                </div>
                            ) : (
                                data.biggest_vulnerable.map(item => (
                                    <RiskItemRow key={item.id} item={item} showSize />
                                ))
                            )}
                        </div>
                    )}

                    {/* Tab: Fragile Drives */}
                    {activeTab === 'drives' && (
                        <div className="risk-list">
                            {data.fragile_drives.length === 0 ? (
                                <div className="empty-state">
                                    <p>No fragile drives found.</p>
                                </div>
                            ) : (
                                data.fragile_drives.map(drive => (
                                    <div key={drive.drive_id} className="risk-drive-row">
                                        <span className="risk-drive-icon">
                                            {HEALTH_META[drive.health_status]?.icon ?? '💿'}
                                        </span>
                                        <div className="risk-drive-info">
                                            <span className="risk-drive-name">
                                                {drive.volume_label || drive.mount_path}
                                            </span>
                                            <span className="risk-drive-path hint">{drive.mount_path}</span>
                                        </div>
                                        <div className="risk-drive-stats">
                                            <span
                                                className="badge"
                                                style={{
                                                    background: `${HEALTH_META[drive.health_status]?.color ?? '#888'}22`,
                                                    color: HEALTH_META[drive.health_status]?.color ?? '#888',
                                                }}
                                            >
                                                {HEALTH_META[drive.health_status]?.label ?? drive.health_status}
                                            </span>
                                            <span className="risk-drive-count">
                                                {drive.at_risk_items} at-risk item{drive.at_risk_items !== 1 ? 's' : ''}
                                            </span>
                                        </div>
                                    </div>
                                ))
                            )}
                        </div>
                    )}
                </>
            )}
        </div>
    );
}

function RiskItemRow({ item, showSize }: { item: RiskItem; showSize?: boolean }) {
    const labelColor = RISK_COLORS[item.label] ?? '#888';
    return (
        <div className="risk-item-row">
            <div className="risk-item-header">
                <span className="risk-item-type">
                    {item.type === 'movie' ? '🎬' : '📺'}
                </span>
                <span className="risk-item-title">{item.title}</span>
                <span
                    className="risk-label-badge"
                    style={{ background: `${labelColor}22`, color: labelColor }}
                >
                    {item.label}
                </span>
                {showSize && (
                    <span className="risk-size hint">{formatBytes(item.total_size_bytes)}</span>
                )}
            </div>
            <RiskBar score={item.score} />
            <div className="risk-item-action">
                <span className="risk-action-icon">💡</span>
                <span className="risk-action-text">{item.recommended_action}</span>
            </div>
            <div className="risk-item-meta hint">
                {item.copy_count} cop{item.copy_count === 1 ? 'y' : 'ies'} ·
                {' '}{item.resilience_state?.replace(/_/g, ' ')}
            </div>
        </div>
    );
}
