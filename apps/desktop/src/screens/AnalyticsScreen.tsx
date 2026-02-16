import React, { useState, useEffect } from 'react';
import { analyticsApi, HeatmapDrive, RiskScoreItem } from '../api';
import './Screens.css';

function formatBytes(bytes: number): string {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

function riskColor(level: string): string {
    switch (level) {
        case 'critical': return '#f44336';
        case 'high': return '#ff9800';
        case 'medium': return '#ffc107';
        case 'low': return '#4caf50';
        default: return '#888';
    }
}

export default function AnalyticsScreen() {
    const [tab, setTab] = useState<'heatmap' | 'risk'>('heatmap');
    const [drives, setDrives] = useState<HeatmapDrive[]>([]);
    const [riskItems, setRiskItems] = useState<RiskScoreItem[]>([]);
    const [riskDist, setRiskDist] = useState<Record<string, number>>({});
    const [hotSpots, setHotSpots] = useState(0);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');

    const loadHeatmap = async () => {
        setLoading(true);
        try {
            const data = await analyticsApi.heatmap();
            setDrives(data.drives);
            setHotSpots(data.hot_spots.single_drive_items);
        } catch (e: any) {
            setError(e.message);
        } finally {
            setLoading(false);
        }
    };

    const loadRiskScores = async () => {
        setLoading(true);
        try {
            const data = await analyticsApi.riskScores('score', 100, 0);
            setRiskItems(data.items);
            setRiskDist(data.risk_distribution);
        } catch (e: any) {
            setError(e.message);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        if (tab === 'heatmap') loadHeatmap();
        else loadRiskScores();
    }, [tab]);

    return (
        <div className="screen">
            <div className="screen-header">
                <h2>📊 Analytics</h2>
                <p className="subtitle">Storage utilization, redundancy heatmap, and risk scoring</p>
            </div>

            <div className="tab-bar">
                <button className={`tab ${tab === 'heatmap' ? 'active' : ''}`} onClick={() => setTab('heatmap')}>
                    🗺️ Heatmap
                </button>
                <button className={`tab ${tab === 'risk' ? 'active' : ''}`} onClick={() => setTab('risk')}>
                    ⚠️ Risk Scores
                </button>
            </div>

            {error && <p className="error-text">{error}</p>}

            {tab === 'heatmap' && (
                <div className="analytics-section">
                    {hotSpots > 0 && (
                        <div className="analytics-alert warning">
                            <strong>⚠️ {hotSpots} items</strong> exist on only a single drive
                        </div>
                    )}

                    {loading ? (
                        <div className="loading">Loading heatmap...</div>
                    ) : (
                        <div className="heatmap-table-wrapper">
                            <table className="files-table">
                                <thead>
                                    <tr>
                                        <th>Drive</th>
                                        <th>Label</th>
                                        <th>Domain</th>
                                        <th>Files</th>
                                        <th>Items</th>
                                        <th>Used</th>
                                        <th>Utilization</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {drives.map(drive => (
                                        <tr key={drive.drive_id}>
                                            <td className="mono">{drive.mount_path}</td>
                                            <td>{drive.volume_label || '—'}</td>
                                            <td>{drive.domain_name || '—'}</td>
                                            <td>{drive.file_count.toLocaleString()}</td>
                                            <td>{drive.item_count.toLocaleString()}</td>
                                            <td>{formatBytes(drive.used_bytes)}</td>
                                            <td>
                                                <div className="utilization-cell">
                                                    <div className="usage-bar small">
                                                        <div
                                                            className="usage-fill"
                                                            style={{
                                                                width: `${drive.utilization_pct}%`,
                                                                background: drive.utilization_pct > 90
                                                                    ? '#f44336'
                                                                    : drive.utilization_pct > 75
                                                                        ? '#ff9800'
                                                                        : undefined
                                                            }}
                                                        />
                                                    </div>
                                                    <span className="utilization-value">{drive.utilization_pct}%</span>
                                                </div>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}
                </div>
            )}

            {tab === 'risk' && (
                <div className="analytics-section">
                    {/* Risk distribution summary */}
                    <div className="risk-summary">
                        {['critical', 'high', 'medium', 'low'].map(level => (
                            <div key={level} className="risk-summary-card" style={{ borderColor: riskColor(level) }}>
                                <span className="risk-count" style={{ color: riskColor(level) }}>
                                    {riskDist[level] || 0}
                                </span>
                                <span className="risk-label">{level}</span>
                            </div>
                        ))}
                    </div>

                    {loading ? (
                        <div className="loading">Loading risk scores...</div>
                    ) : (
                        <div className="items-list">
                            {riskItems.map(item => (
                                <div key={item.item_id} className="item-row">
                                    <div className="risk-score-badge" style={{ background: riskColor(item.risk_level) }}>
                                        {item.risk_score}
                                    </div>
                                    <div className="item-info">
                                        <span className="item-title">{item.title || `Item #${item.item_id}`}</span>
                                        <span className="item-meta">
                                            {item.type} · {item.copy_count} copies · {item.domain_count} domains · {item.verified_copies} verified
                                        </span>
                                    </div>
                                    <span className={`risk-badge ${item.risk_level}`}>
                                        {item.risk_level}
                                    </span>
                                </div>
                            ))}
                            {riskItems.length === 0 && (
                                <div className="empty-state">
                                    <p>No items scored yet</p>
                                </div>
                            )}
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}
