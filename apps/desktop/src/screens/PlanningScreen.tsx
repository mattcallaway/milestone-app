import { useState, useEffect } from 'react';
import { planningApi, Plan, PlanType } from '../api';
import { NavigateFunction } from '../types';
import './Screens.css';

interface PlanningScreenProps {
    onNavigate: NavigateFunction;
}

export function PlanningScreen({ onNavigate }: PlanningScreenProps) {
    const [plans, setPlans] = useState<Plan[]>([]);
    const [loading, setLoading] = useState(true);
    const [creating, setCreating] = useState(false);

    const loadPlans = async () => {
        setLoading(true);
        try {
            const data = await planningApi.listPlans();
            setPlans(data);
        } catch (err) {
            console.error('Failed to load plans:', err);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        loadPlans();
    }, []);

    const handleCreatePlan = async (type: PlanType) => {
        setCreating(true);
        try {
            const name = `${type.charAt(0).toUpperCase() + type.slice(1)} Plan - ${new Date().toLocaleString()}`;
            const planId = await planningApi.createPlan({ name, type });
            onNavigate('plan-review', { planId });
        } catch (err) {
            alert('Failed to create plan: ' + err);
        } finally {
            setCreating(false);
        }
    };

    const formatSize = (bytes: number) => {
        if (!bytes) return '0 B';
        const gb = bytes / (1024 ** 3);
        if (gb >= 1) return `${gb.toFixed(2)} GB`;
        return `${(bytes / (1024 ** 2)).toFixed(2)} MB`;
    };

    return (
        <div className="screen planning-screen">
            <header className="screen-header">
                <h2>Resilience Planning</h2>
                <div className="header-actions">
                    <button 
                        className="btn btn-primary" 
                        disabled={creating}
                        onClick={() => handleCreatePlan('protection')}
                    >
                        Plan Protection
                    </button>
                    <button 
                        className="btn btn-secondary" 
                        disabled={creating}
                        onClick={() => handleCreatePlan('reduction')}
                    >
                        Plan Reduction
                    </button>
                </div>
            </header>

            <div className="card bulk-actions-card">
                <h3>Bulk Actions</h3>
                <p className="text-muted">Create a new plan to analyze and improve your library&apos;s resilience.</p>
                <div className="bulk-grid">
                    <div className="bulk-item" onClick={() => handleCreatePlan('protection')}>
                        <span className="bulk-icon">🛡️</span>
                        <div className="bulk-info">
                            <strong>Protect Unsafe Items</strong>
                            <span>Find all items with {"<"} 2 domains and plan copies.</span>
                        </div>
                    </div>
                    <div className="bulk-item" onClick={() => handleCreatePlan('reduction')}>
                        <span className="bulk-icon">✂️</span>
                        <div className="bulk-info">
                            <strong>Reduce Over-Replication</strong>
                            <span>Find items with {">"} 3 copies and plan deletions.</span>
                        </div>
                    </div>
                </div>
            </div>

            <div className="plans-list">
                <h3>Saved Plans</h3>
                {loading ? (
                    <div className="loading">Loading plans...</div>
                ) : plans.length === 0 ? (
                    <div className="empty-state">No plans found. Create one to get started.</div>
                ) : (
                    <table className="table">
                        <thead>
                            <tr>
                                <th>Name</th>
                                <th>Type</th>
                                <th>Status</th>
                                <th>Items</th>
                                <th>Total Size</th>
                                <th>Created</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {plans.map((plan) => (
                                <tr key={plan.id}>
                                    <td><strong>{plan.name}</strong></td>
                                    <td><span className={`badge badge-${plan.type}`}>{plan.type}</span></td>
                                    <td><span className={`status-tag status-${plan.status}`}>{plan.status}</span></td>
                                    <td>{plan.item_count}</td>
                                    <td>{formatSize(plan.total_size)}</td>
                                    <td>{new Date(plan.created_at).toLocaleDateString()}</td>
                                    <td>
                                        <button 
                                            className="btn btn-sm"
                                            onClick={() => onNavigate('plan-review', { planId: plan.id })}
                                        >
                                            Review
                                        </button>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </div>
        </div>
    );
}
