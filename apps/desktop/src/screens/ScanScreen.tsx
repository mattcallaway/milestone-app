import { useState, useEffect, useRef } from 'react';
import { api, ScanStatus } from '../api';
import './Screens.css';

export function ScanScreen() {
    const [status, setStatus] = useState<ScanStatus | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [throttle, setThrottle] = useState<'low' | 'normal' | 'fast'>('normal');
    const pollingRef = useRef<number | null>(null);

    const loadStatus = async () => {
        try {
            const s = await api.getScanStatus();
            setStatus(s);
            setError(null);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to get status');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        loadStatus();

        // Poll for status updates when scan is running
        pollingRef.current = window.setInterval(() => {
            loadStatus();
        }, 1000);

        return () => {
            if (pollingRef.current) {
                clearInterval(pollingRef.current);
            }
        };
    }, []);

    const handleStart = async () => {
        try {
            setError(null);
            await api.startScan(undefined, throttle);
            await loadStatus();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to start scan');
        }
    };

    const handleControl = async (action: 'pause' | 'resume' | 'cancel') => {
        try {
            setError(null);
            await api.controlScan(action);
            await loadStatus();
        } catch (err) {
            setError(err instanceof Error ? err.message : `Failed to ${action} scan`);
        }
    };

    const getStateColor = (state: string): string => {
        switch (state) {
            case 'running':
                return '#4caf50';
            case 'paused':
                return '#ff9800';
            case 'completed':
                return '#2196f3';
            case 'cancelled':
                return '#f44336';
            default:
                return '#666';
        }
    };

    const formatDuration = (seconds: number | null): string => {
        if (seconds === null) return '--';
        const mins = Math.floor(seconds / 60);
        const secs = seconds % 60;
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    };

    const isActive = status?.state === 'running' || status?.state === 'paused';

    return (
        <div className="screen">
            <div className="screen-header">
                <h2>Scan</h2>
                <p className="subtitle">Scan registered roots for files</p>
            </div>

            {error && <div className="error-banner">{error}</div>}

            {loading ? (
                <div className="loading">Loading scan status...</div>
            ) : (
                <>
                    <div className="scan-controls">
                        <div className="control-group">
                            <label>Throttle:</label>
                            <select
                                value={throttle}
                                onChange={(e) => setThrottle(e.target.value as 'low' | 'normal' | 'fast')}
                                className="input select"
                                disabled={isActive}
                            >
                                <option value="low">Low (slower, less CPU)</option>
                                <option value="normal">Normal</option>
                                <option value="fast">Fast (no delay)</option>
                            </select>
                        </div>

                        <div className="control-buttons">
                            {!isActive ? (
                                <button className="btn btn-primary btn-lg" onClick={handleStart}>
                                    🚀 Start Scan
                                </button>
                            ) : (
                                <>
                                    {status?.state === 'running' ? (
                                        <button
                                            className="btn btn-warning btn-lg"
                                            onClick={() => handleControl('pause')}
                                        >
                                            ⏸️ Pause
                                        </button>
                                    ) : (
                                        <button
                                            className="btn btn-success btn-lg"
                                            onClick={() => handleControl('resume')}
                                        >
                                            ▶️ Resume
                                        </button>
                                    )}
                                    <button
                                        className="btn btn-danger btn-lg"
                                        onClick={() => handleControl('cancel')}
                                    >
                                        ⏹️ Cancel
                                    </button>
                                </>
                            )}
                        </div>
                    </div>

                    <div className="scan-status-card">
                        <div className="status-header">
                            <span
                                className="status-indicator"
                                style={{ backgroundColor: getStateColor(status?.state || 'idle') }}
                            />
                            <span className="status-label">
                                {status?.state?.toUpperCase() || 'IDLE'}
                            </span>
                        </div>

                        {status?.current_root && (
                            <div className="current-root">
                                <span className="label">Scanning:</span>
                                <span className="value">{status.current_root}</span>
                            </div>
                        )}

                        <div className="stats-grid">
                            <div className="stat">
                                <span className="stat-value">{status?.files_scanned || 0}</span>
                                <span className="stat-label">Files Scanned</span>
                            </div>
                            <div className="stat">
                                <span className="stat-value">{status?.files_new || 0}</span>
                                <span className="stat-label">New Files</span>
                            </div>
                            <div className="stat">
                                <span className="stat-value">{status?.files_updated || 0}</span>
                                <span className="stat-label">Updated</span>
                            </div>
                            <div className="stat">
                                <span className="stat-value">{status?.files_missing || 0}</span>
                                <span className="stat-label">Missing</span>
                            </div>
                        </div>

                        {status?.started_at && (
                            <div className="started-at">
                                Started: {new Date(status.started_at).toLocaleString()}
                            </div>
                        )}
                    </div>
                </>
            )}
        </div>
    );
}
