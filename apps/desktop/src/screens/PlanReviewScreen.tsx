import { useState, useEffect, useCallback, Fragment } from 'react';
import { planningApi, PlanSummary } from '../api';
import { NavigateFunction } from '../types';
import './Screens.css';

interface PlanReviewScreenProps {
    planId: number;
    onBack: () => void;
    onNavigate: NavigateFunction;
}

export function PlanReviewScreen({ planId, onBack, onNavigate }: PlanReviewScreenProps) {
    const [summary, setSummary] = useState<PlanSummary | null>(null);
    const [loading, setLoading] = useState(true);
    const [executing, setExecuting] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const loadPlan = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const data = await planningApi.getPlan(planId);
            setSummary(data);
        } catch (err) {
            setError(err instanceof Error ? err.message : String(err));
        } finally {
            setLoading(false);
        }
    }, [planId]);

    useEffect(() => {
        loadPlan();
    }, [loadPlan]);

    const handleExecute = async () => {
        if (!confirm('This will queue all included items for execution. Proceed?')) {
            return;
        }
        setExecuting(true);
        try {
            await planningApi.executePlan(planId);
            onNavigate('operations');
        } catch (err) {
            setError(err instanceof Error ? err.message : String(err));
        } finally {
            setExecuting(false);
        }
    };

    const toggleItem = async (itemId: number, current: boolean) => {
        try {
            await planningApi.toggleInclusion(itemId, !current);
            loadPlan(); // Reload summary for updated impact
        } catch (err) {
            setError(err instanceof Error ? err.message : String(err));
        }
    };

    if (loading) return <div className="loading">Loading plan summary...</div>;
    if (error) return <div className="error">{error}</div>;
    if (!summary) return <div className="error">Plan not found.</div>;

    const { plan, items, impact } = summary;
    const includedItems = items.filter(i => i.is_included);
    const totalBytes = includedItems.reduce((sum, item) => sum + (item.estimated_size || 0), 0);
    const timeEstimate = Math.ceil(totalBytes / (50 * 1024 ** 2)); // 50 MB/s

    const formatSize = (bytes: number) => {
        if (!bytes) return '0 B';
        const gb = bytes / (1024 ** 3);
        if (gb >= 1) return `${gb.toFixed(2)} GB`;
        return `${(bytes / (1024 ** 2)).toFixed(2)} MB`;
    };

    const formatTime = (seconds: number) => {
        if (seconds < 60) return `${seconds}s`;
        if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
        return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
    };

    const ALL_STATES = [
        'unsafe_no_backup',
        'unsafe_single_domain',
        'safe_two_domains',
        'over_replicated_but_fragile',
        'over_replicated_and_resilient'
    ];

    const stateLabels: Record<string, string> = {
        'unsafe_no_backup': 'No Backup (Unsafe)',
        'unsafe_single_domain': 'Single Domain (Unsafe)',
        'safe_two_domains': 'Two Domains (Safe)',
        'over_replicated_but_fragile': 'Over-replicated (Fragile)',
        'over_replicated_and_resilient': 'Over-replicated (Resilient)'
    };

    return (
        <div className="screen plan-review-screen">
            <header className="screen-header">
                <div className="header-title">
                    <button className="btn btn-icon" onClick={onBack}>←</button>
                    <h2>Review: {plan.name}</h2>
                </div>
                <div className="header-actions">
                    <button 
                        className="btn btn-primary" 
                        disabled={includedItems.length === 0 || executing}
                        onClick={handleExecute}
                    >
                        Execute Plan ({includedItems.length} items)
                    </button>
                    <span className={`status-tag status-${plan.status}`}>{plan.status}</span>
                </div>
            </header>

            <div className="stats-header">
                <div className="stat card">
                    <span className="stat-label">Queue Size Estimate</span>
                    <span className="stat-value">{formatSize(totalBytes)}</span>
                    <span className="stat-unit">{includedItems.length} ops</span>
                </div>
                <div className="stat card">
                    <span className="stat-label">Time Estimate</span>
                    <span className="stat-value">{formatTime(timeEstimate)}</span>
                    <span className="stat-unit">@ 50 MB/s</span>
                </div>
            </div>

            <div className="impact-card card">
                <h3>Library Resilience Impact</h3>
                <div className="impact-grid">
                    <div className="impact-header">Resilience State</div>
                    <div className="impact-header">Before</div>
                    <div className="impact-header">After</div>
                    <div className="impact-header">Change</div>
                    {ALL_STATES.map(state => {
                        const before = impact.before[state] || 0;
                        const after = impact.after[state] || 0;
                        const change = after - before;
                        if (before === 0 && after === 0) return null;
                        return (
                            <Fragment key={state}>
                                <div>{stateLabels[state] || state}</div>
                                <div className="text-muted">{before}</div>
                                <div className="text-highlight"><strong>{after}</strong></div>
                                <div className={change > 0 && (state.startsWith('safe') || state.includes('resilient')) ? 'text-green' : (change < 0 && (state.startsWith('unsafe') || state.includes('fragile')) ? 'text-green' : 'text-neutral')}>
                                    {change > 0 ? `+${change}` : change === 0 ? '--' : change}
                                </div>
                            </Fragment>
                        );
                    })}
                </div>
            </div>

            <div className="plan-items-list">
                <h3>Action Items</h3>
                <table className="table">
                    <thead>
                        <tr>
                            <th style={{ width: '40px' }}><input type="checkbox" checked={includedItems.length === items.length} readOnly /></th>
                            <th>Action</th>
                            <th>Item Title</th>
                            <th>Destination Drive</th>
                            <th>Size</th>
                            <th>Status (Before Execution)</th>
                        </tr>
                    </thead>
                    <tbody>
                        {items.map((pi) => (
                            <tr key={pi.id} className={pi.is_included ? '' : 'text-muted'}>
                                <td>
                                    <input 
                                        type="checkbox" 
                                        checked={pi.is_included} 
                                        onChange={() => toggleItem(pi.id, pi.is_included)} 
                                    />
                                </td>
                                <td><span className={`badge badge-${pi.action}`}>{pi.action}</span></td>
                                <td>{pi.media_item_title}</td>
                                <td>{pi.dest_drive_path || '-- (Deletion)'}</td>
                                <td>{formatSize(pi.estimated_size || 0)}</td>
                                <td>{pi.is_included ? 'Included' : 'Skipped'}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
