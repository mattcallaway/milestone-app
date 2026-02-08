import { useState, useEffect } from 'react';
import { api, ItemStats } from '../api';
import './Screens.css';

interface DashboardScreenProps {
    onNavigate: (screen: string, params?: Record<string, unknown>) => void;
}

export function DashboardScreen({ onNavigate }: DashboardScreenProps) {
    const [stats, setStats] = useState<ItemStats | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [processing, setProcessing] = useState(false);

    const loadStats = async () => {
        try {
            setLoading(true);
            const s = await api.getItemStats();
            setStats(s);
            setError(null);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to load stats');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        loadStats();
    }, []);

    const handleProcessItems = async () => {
        try {
            setProcessing(true);
            const result = await api.processItems();
            await loadStats();
            alert(`Processed ${result.processed} files: ${result.new_items} new items, ${result.linked} linked`);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to process items');
        } finally {
            setProcessing(false);
        }
    };

    const handleStartHashing = async () => {
        try {
            await api.startHashing();
            alert('Hash computation started');
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to start hashing');
        }
    };

    const getCopyCountDisplay = (count: number): string => {
        if (count === 0) return 'No copies';
        if (count === 1) return '1 copy';
        if (count === 2) return '2 copies';
        return '3+ copies';
    };

    const getCopyCountColor = (count: number): string => {
        if (count === 0) return '#f44336'; // Red - missing
        if (count === 1) return '#ff9800'; // Orange - single
        if (count === 2) return '#4caf50'; // Green - backed up
        return '#2196f3'; // Blue - multiple
    };

    // Aggregate copy counts into 0, 1, 2, 3+
    const getCopyCounts = (): Record<string, number> => {
        if (!stats) return { '0': 0, '1': 0, '2': 0, '3+': 0 };

        const result: Record<string, number> = { '0': 0, '1': 0, '2': 0, '3+': 0 };
        Object.entries(stats.by_copy_count).forEach(([count, items]) => {
            const c = parseInt(count);
            if (c === 0) result['0'] += items;
            else if (c === 1) result['1'] += items;
            else if (c === 2) result['2'] += items;
            else result['3+'] += items;
        });
        return result;
    };

    return (
        <div className="screen">
            <div className="screen-header">
                <h2>Dashboard</h2>
                <p className="subtitle">Media library overview</p>
            </div>

            {error && <div className="error-banner">{error}</div>}

            <div className="dashboard-actions">
                <button
                    className="btn btn-primary"
                    onClick={handleProcessItems}
                    disabled={processing}
                >
                    {processing ? 'Processing...' : '🔄 Process Files'}
                </button>
                <button className="btn btn-secondary" onClick={handleStartHashing}>
                    #️⃣ Start Hashing
                </button>
            </div>

            {loading ? (
                <div className="loading">Loading dashboard...</div>
            ) : stats ? (
                <>
                    <section className="dashboard-section">
                        <h3>Copy Distribution</h3>
                        <div className="copy-cards">
                            {Object.entries(getCopyCounts()).map(([count, items]) => (
                                <div
                                    key={count}
                                    className="copy-card"
                                    style={{ borderColor: getCopyCountColor(parseInt(count) || 3) }}
                                    onClick={() => onNavigate('items', {
                                        min_copies: count === '3+' ? 3 : parseInt(count),
                                        max_copies: count === '3+' ? undefined : parseInt(count)
                                    })}
                                >
                                    <span className="copy-count">{items}</span>
                                    <span className="copy-label">
                                        {getCopyCountDisplay(count === '3+' ? 3 : parseInt(count))}
                                    </span>
                                </div>
                            ))}
                        </div>
                    </section>

                    <section className="dashboard-section">
                        <h3>By Type</h3>
                        <div className="type-cards">
                            <div
                                className="type-card"
                                onClick={() => onNavigate('items', { type: 'movie' })}
                            >
                                <span className="type-icon">🎬</span>
                                <span className="type-count">{stats.by_type.movie || 0}</span>
                                <span className="type-label">Movies</span>
                            </div>
                            <div
                                className="type-card"
                                onClick={() => onNavigate('items', { type: 'tv_episode' })}
                            >
                                <span className="type-icon">📺</span>
                                <span className="type-count">{stats.by_type.tv_episode || 0}</span>
                                <span className="type-label">TV Episodes</span>
                            </div>
                            <div
                                className="type-card"
                                onClick={() => onNavigate('items', { type: 'unknown' })}
                            >
                                <span className="type-icon">❓</span>
                                <span className="type-count">{stats.by_type.unknown || 0}</span>
                                <span className="type-label">Unknown</span>
                            </div>
                        </div>
                    </section>

                    {stats.needs_verification > 0 && (
                        <section className="dashboard-section">
                            <div
                                className="verification-banner"
                                onClick={() => onNavigate('items', { status: 'needs_verification' })}
                            >
                                <span className="verification-icon">⚠️</span>
                                <span className="verification-text">
                                    {stats.needs_verification} items need verification
                                </span>
                                <span className="verification-arrow">→</span>
                            </div>
                        </section>
                    )}

                    <section className="dashboard-section">
                        <h3>Summary</h3>
                        <div className="summary-stats">
                            <div className="summary-stat">
                                <span className="stat-value">{stats.total_items}</span>
                                <span className="stat-label">Total Media Items</span>
                            </div>
                        </div>
                    </section>

                    {getCopyCounts()['1'] > 0 && (
                        <section className="dashboard-section">
                            <div
                                className="backup-banner"
                                onClick={() => onNavigate('items', { min_copies: 1, max_copies: 1 })}
                            >
                                <div className="backup-info">
                                    <span className="backup-title">
                                        ⚠️ {getCopyCounts()['1']} items have only 1 copy
                                    </span>
                                    <span className="backup-desc">
                                        Click to view at-risk items and create backup copies
                                    </span>
                                </div>
                                <span className="verification-arrow">→</span>
                            </div>
                        </section>
                    )}
                </>
            ) : null}
        </div>
    );
}
