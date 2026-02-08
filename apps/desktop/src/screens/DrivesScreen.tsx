import { useState, useEffect } from 'react';
import { api, Drive } from '../api';
import './Screens.css';

export function DrivesScreen() {
    const [drives, setDrives] = useState<Drive[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [newPath, setNewPath] = useState('');
    const [adding, setAdding] = useState(false);

    const loadDrives = async () => {
        try {
            setLoading(true);
            const { drives } = await api.getDrives();
            setDrives(drives);
            setError(null);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to load drives');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        loadDrives();
    }, []);

    const handleAddDrive = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!newPath.trim()) return;

        try {
            setAdding(true);
            await api.registerDrive(newPath.trim());
            setNewPath('');
            await loadDrives();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to add drive');
        } finally {
            setAdding(false);
        }
    };

    const handleDeleteDrive = async (id: number) => {
        if (!confirm('Delete this drive? All associated roots and files will be removed.')) return;

        try {
            await api.deleteDrive(id);
            await loadDrives();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to delete drive');
        }
    };

    const formatBytes = (bytes: number | null): string => {
        if (bytes === null) return 'Unknown';
        const units = ['B', 'KB', 'MB', 'GB', 'TB'];
        let value = bytes;
        let unitIndex = 0;
        while (value >= 1024 && unitIndex < units.length - 1) {
            value /= 1024;
            unitIndex++;
        }
        return `${value.toFixed(1)} ${units[unitIndex]}`;
    };

    const getUsagePercent = (drive: Drive): number => {
        if (!drive.free_space || !drive.total_space) return 0;
        return Math.round(((drive.total_space - drive.free_space) / drive.total_space) * 100);
    };

    return (
        <div className="screen">
            <div className="screen-header">
                <h2>Drives</h2>
                <p className="subtitle">Register drives to scan for files</p>
            </div>

            <form className="add-form" onSubmit={handleAddDrive}>
                <input
                    type="text"
                    placeholder="Enter drive path (e.g., C:\ or /mnt/data)"
                    value={newPath}
                    onChange={(e) => setNewPath(e.target.value)}
                    className="input"
                />
                <button type="submit" className="btn btn-primary" disabled={adding}>
                    {adding ? 'Adding...' : 'Add Drive'}
                </button>
            </form>

            {error && <div className="error-banner">{error}</div>}

            {loading ? (
                <div className="loading">Loading drives...</div>
            ) : drives.length === 0 ? (
                <div className="empty-state">
                    <p>No drives registered yet.</p>
                    <p className="hint">Add a drive path above to get started.</p>
                </div>
            ) : (
                <div className="card-grid">
                    {drives.map((drive) => (
                        <div key={drive.id} className="card">
                            <div className="card-header">
                                <span className="card-icon">💾</span>
                                <div className="card-title">
                                    <h3>{drive.mount_path}</h3>
                                    <span className="card-label">{drive.volume_label || 'Unknown Volume'}</span>
                                </div>
                                <button
                                    className="btn btn-icon btn-danger"
                                    onClick={() => handleDeleteDrive(drive.id)}
                                    title="Delete drive"
                                >
                                    🗑️
                                </button>
                            </div>
                            <div className="card-body">
                                <div className="usage-bar">
                                    <div
                                        className="usage-fill"
                                        style={{ width: `${getUsagePercent(drive)}%` }}
                                    />
                                </div>
                                <div className="usage-stats">
                                    <span>{formatBytes(drive.free_space)} free</span>
                                    <span>{formatBytes(drive.total_space)} total</span>
                                </div>
                                {drive.volume_serial && (
                                    <div className="card-meta">
                                        Serial: {drive.volume_serial}
                                    </div>
                                )}
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
