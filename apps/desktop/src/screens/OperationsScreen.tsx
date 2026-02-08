import { useState, useEffect, useCallback } from 'react';
import { api, Operation, QueueStatus } from '../api';
import './Screens.css';

export function OperationsScreen() {
    const [operations, setOperations] = useState<Operation[]>([]);
    const [queueStatus, setQueueStatus] = useState<QueueStatus | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [filterStatus, setFilterStatus] = useState('');
    const [page, setPage] = useState(1);
    const [total, setTotal] = useState(0);
    const pageSize = 25;

    const loadData = useCallback(async () => {
        try {
            setLoading(true);
            const [opsResult, statusResult] = await Promise.all([
                api.getOperations({
                    status: filterStatus || undefined,
                    page,
                    page_size: pageSize,
                }),
                api.getQueueStatus(),
            ]);
            setOperations(opsResult.operations);
            setTotal(opsResult.total);
            setQueueStatus(statusResult);
            setError(null);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to load operations');
        } finally {
            setLoading(false);
        }
    }, [filterStatus, page]);

    useEffect(() => {
        loadData();
        // Auto-refresh every 3 seconds
        const interval = setInterval(loadData, 3000);
        return () => clearInterval(interval);
    }, [loadData]);

    const handleStartQueue = async () => {
        try {
            await api.startQueue();
            await loadData();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to start queue');
        }
    };

    const handlePauseQueue = async () => {
        try {
            await api.pauseQueue();
            await loadData();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to pause queue');
        }
    };

    const handleResumeQueue = async () => {
        try {
            await api.resumeQueue();
            await loadData();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to resume queue');
        }
    };

    const handleStopQueue = async () => {
        try {
            await api.stopQueue();
            await loadData();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to stop queue');
        }
    };

    const handlePauseOp = async (id: number) => {
        try {
            await api.pauseOperation(id);
            await loadData();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to pause operation');
        }
    };

    const handleResumeOp = async (id: number) => {
        try {
            await api.resumeOperation(id);
            await loadData();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to resume operation');
        }
    };

    const handleCancelOp = async (id: number) => {
        if (!confirm('Cancel this operation?')) return;
        try {
            await api.cancelOperation(id);
            await loadData();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to cancel operation');
        }
    };

    const formatBytes = (bytes: number | null): string => {
        if (bytes === null) return '-';
        const units = ['B', 'KB', 'MB', 'GB'];
        let value = bytes;
        let unitIndex = 0;
        while (value >= 1024 && unitIndex < units.length - 1) {
            value /= 1024;
            unitIndex++;
        }
        return `${value.toFixed(1)} ${units[unitIndex]}`;
    };

    const getProgressPercent = (op: Operation): number => {
        if (!op.total_size || op.total_size === 0) return 0;
        return Math.round((op.progress / op.total_size) * 100);
    };

    const getStatusColor = (status: string): string => {
        switch (status) {
            case 'completed': return '#4caf50';
            case 'running': return '#2196f3';
            case 'paused': return '#ff9800';
            case 'failed': return '#f44336';
            case 'cancelled': return '#888';
            default: return '#666';
        }
    };

    const totalPages = Math.ceil(total / pageSize);

    return (
        <div className="screen">
            <div className="screen-header">
                <h2>Operations Queue</h2>
                <p className="subtitle">{total} operations</p>
            </div>

            {error && <div className="error-banner">{error}</div>}

            {queueStatus && (
                <div className="queue-status-card">
                    <div className="queue-status-header">
                        <span className={`queue-indicator ${queueStatus.running ? 'running' : 'stopped'}`} />
                        <span className="queue-status-text">
                            {queueStatus.paused ? 'Paused' : queueStatus.running ? 'Running' : 'Stopped'}
                        </span>
                        <span className="queue-stats">
                            {queueStatus.running_count} active / {queueStatus.pending_count} pending
                        </span>
                    </div>
                    <div className="queue-controls">
                        {!queueStatus.running ? (
                            <button className="btn btn-primary btn-sm" onClick={handleStartQueue}>
                                ▶ Start Queue
                            </button>
                        ) : queueStatus.paused ? (
                            <button className="btn btn-primary btn-sm" onClick={handleResumeQueue}>
                                ▶ Resume
                            </button>
                        ) : (
                            <button className="btn btn-warning btn-sm" onClick={handlePauseQueue}>
                                ⏸ Pause
                            </button>
                        )}
                        {queueStatus.running && (
                            <button className="btn btn-secondary btn-sm" onClick={handleStopQueue}>
                                ⏹ Stop
                            </button>
                        )}
                    </div>
                </div>
            )}

            <div className="filter-form">
                <select
                    value={filterStatus}
                    onChange={(e) => { setFilterStatus(e.target.value); setPage(1); }}
                    className="input select"
                >
                    <option value="">All status</option>
                    <option value="pending">Pending</option>
                    <option value="running">Running</option>
                    <option value="paused">Paused</option>
                    <option value="completed">Completed</option>
                    <option value="failed">Failed</option>
                    <option value="cancelled">Cancelled</option>
                </select>
            </div>

            {loading && operations.length === 0 ? (
                <div className="loading">Loading operations...</div>
            ) : operations.length === 0 ? (
                <div className="empty-state">
                    <p>No operations in queue.</p>
                    <p className="hint">Create a copy from the Dashboard or Items screen.</p>
                </div>
            ) : (
                <>
                    <div className="operations-list">
                        {operations.map((op) => (
                            <div key={op.id} className="operation-card">
                                <div className="op-header">
                                    <span className="op-type">{op.type.toUpperCase()}</span>
                                    <span
                                        className="op-status"
                                        style={{ color: getStatusColor(op.status) }}
                                    >
                                        {op.status}
                                    </span>
                                </div>

                                <div className="op-paths">
                                    <div className="op-path">
                                        <span className="path-label">From:</span>
                                        <span className="path-value">{op.source_path || '-'}</span>
                                    </div>
                                    <div className="op-path">
                                        <span className="path-label">To:</span>
                                        <span className="path-value">{op.dest_path || '-'}</span>
                                    </div>
                                </div>

                                {op.status === 'running' && (
                                    <div className="op-progress">
                                        <div className="progress-bar">
                                            <div
                                                className="progress-fill"
                                                style={{ width: `${getProgressPercent(op)}%` }}
                                            />
                                        </div>
                                        <span className="progress-text">
                                            {formatBytes(op.progress)} / {formatBytes(op.total_size)} ({getProgressPercent(op)}%)
                                        </span>
                                    </div>
                                )}

                                {op.error && (
                                    <div className="op-error">{op.error}</div>
                                )}

                                <div className="op-actions">
                                    {op.status === 'running' && (
                                        <button className="btn btn-sm btn-warning" onClick={() => handlePauseOp(op.id)}>
                                            Pause
                                        </button>
                                    )}
                                    {op.status === 'paused' && (
                                        <button className="btn btn-sm btn-primary" onClick={() => handleResumeOp(op.id)}>
                                            Resume
                                        </button>
                                    )}
                                    {['pending', 'running', 'paused'].includes(op.status) && (
                                        <button className="btn btn-sm btn-danger" onClick={() => handleCancelOp(op.id)}>
                                            Cancel
                                        </button>
                                    )}
                                </div>
                            </div>
                        ))}
                    </div>

                    <div className="pagination">
                        <button
                            className="btn btn-sm"
                            disabled={page <= 1}
                            onClick={() => setPage(page - 1)}
                        >
                            ← Previous
                        </button>
                        <span className="page-info">
                            Page {page} of {totalPages}
                        </span>
                        <button
                            className="btn btn-sm"
                            disabled={page >= totalPages}
                            onClick={() => setPage(page + 1)}
                        >
                            Next →
                        </button>
                    </div>
                </>
            )}
        </div>
    );
}
