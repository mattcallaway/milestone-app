import { useState, useEffect } from 'react';
import './Screens.css';

const API_BASE = 'http://localhost:8000';

interface Plan {
    id: number;
    name: string;
    plan_type: string;
    status: string;
    total_bytes: number;
    item_count: number;
    created_at: string;
}

interface PlanItem {
    id: number;
    action: string;
    source_path: string;
    size: number;
    dest_drive: string;
    included: number;
}

function formatBytes(bytes: number): string {
    if (!bytes) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

export function PlanScreen() {
    const [plans, setPlans] = useState<Plan[]>([]);
    const [selectedPlan, setSelectedPlan] = useState<Plan & { items: PlanItem[] } | null>(null);
    const [loading, setLoading] = useState(true);
    const [creating, setCreating] = useState(false);
    const [creatingMessage, setCreatingMessage] = useState('');
    const [elapsedSeconds, setElapsedSeconds] = useState(0);

    useEffect(() => {
        loadPlans();
    }, []);

    // Elapsed time counter while creating
    useEffect(() => {
        if (!creating) { setElapsedSeconds(0); return; }
        const interval = setInterval(() => setElapsedSeconds(s => s + 1), 1000);
        return () => clearInterval(interval);
    }, [creating]);

    const loadPlans = async () => {
        try {
            const res = await fetch(`${API_BASE}/plans`);
            const data = await res.json();
            setPlans(data.plans || []);
        } catch (err) {
            console.error('Failed to load plans:', err);
        } finally {
            setLoading(false);
        }
    };

    const loadPlanDetail = async (planId: number) => {
        try {
            const res = await fetch(`${API_BASE}/plans/${planId}`);
            setSelectedPlan(await res.json());
        } catch (err) {
            console.error('Failed to load plan:', err);
        }
    };

    const createCopyPlan = async () => {
        setCreating(true);
        setCreatingMessage('Analyzing at-risk items across all drives...');
        try {
            const res = await fetch(`${API_BASE}/plans/copy-at-risk`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: 'Copy At-Risk Items' })
            });
            const data = await res.json();
            if (data.plan_id) {
                loadPlans();
                loadPlanDetail(data.plan_id);
            } else {
                alert(data.message || 'No at-risk items found');
            }
        } catch (err) {
            console.error('Failed to create plan:', err);
            alert('Failed to create plan. Check that the API server is running.');
        } finally {
            setCreating(false);
            setCreatingMessage('');
        }
    };

    const createReductionPlan = async () => {
        setCreating(true);
        setCreatingMessage('Analyzing over-replicated items...');
        try {
            const res = await fetch(`${API_BASE}/plans/reduce?min_copies=2`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: 'Reduce to 2 Copies' })
            });
            const data = await res.json();
            if (data.plan_id) {
                loadPlans();
                loadPlanDetail(data.plan_id);
            } else {
                alert(data.message || 'No over-replicated items found');
            }
        } catch (err) {
            console.error('Failed to create plan:', err);
            alert('Failed to create plan. Check that the API server is running.');
        } finally {
            setCreating(false);
            setCreatingMessage('');
        }
    };

    const toggleItem = async (itemId: number, included: boolean) => {
        if (!selectedPlan) return;
        try {
            await fetch(`${API_BASE}/plans/${selectedPlan.id}/items/${itemId}?included=${included}`, {
                method: 'PUT'
            });
            loadPlanDetail(selectedPlan.id);
        } catch (err) {
            console.error('Failed to toggle item:', err);
        }
    };

    const confirmPlan = async () => {
        if (!selectedPlan) return;
        if (!confirm('Execute this plan? Included items will be queued as operations.')) return;
        try {
            await fetch(`${API_BASE}/plans/${selectedPlan.id}/confirm`, { method: 'POST' });
            setSelectedPlan(null);
            loadPlans();
            alert('Plan executed! Operations queued.');
        } catch (err) {
            console.error('Failed to confirm plan:', err);
        }
    };

    const cancelPlan = async (planId: number) => {
        if (!confirm('Cancel and delete this plan?')) return;
        try {
            await fetch(`${API_BASE}/plans/${planId}`, { method: 'DELETE' });
            if (selectedPlan?.id === planId) setSelectedPlan(null);
            loadPlans();
        } catch (err) {
            console.error('Failed to cancel plan:', err);
        }
    };

    if (loading) return <div className="screen">Loading...</div>;

    return (
        <div className="screen">
            <div className="screen-header">
                <h2>📋 Bulk Planning</h2>
            </div>

            <p className="screen-description">
                Create plans for bulk operations. Review before executing - no writes until you confirm.
            </p>

            <div className="plan-actions">
                <button
                    className="btn btn-primary"
                    onClick={createCopyPlan}
                    disabled={creating}
                >
                    {creating ? '⏳ Creating...' : '📦 Plan 2nd Copies for At-Risk'}
                </button>
                <button
                    className="btn btn-secondary"
                    onClick={createReductionPlan}
                    disabled={creating}
                >
                    {creating ? '⏳ Creating...' : '🗜️ Plan Reduction to 2 Copies'}
                </button>
            </div>

            {creating && (
                <div className="creating-status" style={{
                    padding: '16px',
                    margin: '12px 0',
                    background: 'var(--surface-2, #1e293b)',
                    borderRadius: '8px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '12px'
                }}>
                    <div className="spinner" style={{
                        width: '20px', height: '20px',
                        border: '3px solid rgba(255,255,255,0.1)',
                        borderTop: '3px solid #60a5fa',
                        borderRadius: '50%',
                        animation: 'spin 1s linear infinite'
                    }} />
                    <div>
                        <div style={{ fontWeight: 600 }}>{creatingMessage}</div>
                        <div style={{ fontSize: '0.85em', opacity: 0.7 }}>
                            {elapsedSeconds > 0 && `${elapsedSeconds}s elapsed — `}
                            This may take a moment for large libraries.
                        </div>
                    </div>
                </div>
            )}

            {plans.length > 0 && (
                <div className="plans-list">
                    <h3>Existing Plans</h3>
                    <table className="data-table">
                        <thead>
                            <tr>
                                <th>Name</th>
                                <th>Type</th>
                                <th>Items</th>
                                <th>Size</th>
                                <th>Status</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {plans.map(plan => (
                                <tr key={plan.id} className={selectedPlan?.id === plan.id ? 'selected' : ''}>
                                    <td>{plan.name}</td>
                                    <td>{plan.plan_type}</td>
                                    <td>{plan.item_count}</td>
                                    <td>{formatBytes(plan.total_bytes)}</td>
                                    <td>
                                        <span className={`status-badge ${plan.status}`}>{plan.status}</span>
                                    </td>
                                    <td>
                                        {plan.status === 'draft' && (
                                            <>
                                                <button
                                                    className="btn btn-sm"
                                                    onClick={() => loadPlanDetail(plan.id)}
                                                >
                                                    Review
                                                </button>
                                                <button
                                                    className="btn btn-sm btn-danger"
                                                    onClick={() => cancelPlan(plan.id)}
                                                >
                                                    Cancel
                                                </button>
                                            </>
                                        )}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}

            {selectedPlan && (
                <div className="plan-detail">
                    <div className="plan-detail-header">
                        <h3>{selectedPlan.name}</h3>
                        <div className="plan-summary">
                            <span>{selectedPlan.items.filter(i => i.included).length} items selected</span>
                            <span>{formatBytes(selectedPlan.items.filter(i => i.included).reduce((s, i) => s + (i.size || 0), 0))}</span>
                        </div>
                        {selectedPlan.status === 'draft' && (
                            <button className="btn btn-primary" onClick={confirmPlan}>
                                ✅ Execute Plan
                            </button>
                        )}
                    </div>

                    <div className="plan-items">
                        {selectedPlan.items.map(item => (
                            <div key={item.id} className={`plan-item ${item.included ? '' : 'excluded'}`}>
                                <input
                                    type="checkbox"
                                    checked={item.included === 1}
                                    onChange={e => toggleItem(item.id, e.target.checked)}
                                    disabled={selectedPlan.status !== 'draft'}
                                />
                                <span className={`action-badge ${item.action}`}>{item.action}</span>
                                <span className="item-path" title={item.source_path}>
                                    {item.source_path?.split(/[/\\]/).pop()}
                                </span>
                                <span className="item-size">{formatBytes(item.size)}</span>
                                {item.dest_drive && (
                                    <span className="item-dest">→ {item.dest_drive}</span>
                                )}
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}
