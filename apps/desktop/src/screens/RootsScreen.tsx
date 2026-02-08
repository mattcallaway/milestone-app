import { useState, useEffect } from 'react';
import { api, Drive, Root } from '../api';
import './Screens.css';

export function RootsScreen() {
    const [drives, setDrives] = useState<Drive[]>([]);
    const [roots, setRoots] = useState<Root[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [selectedDrive, setSelectedDrive] = useState<number | null>(null);
    const [newPath, setNewPath] = useState('');
    const [adding, setAdding] = useState(false);

    const loadData = async () => {
        try {
            setLoading(true);
            const [drivesData, rootsData] = await Promise.all([
                api.getDrives(),
                api.getRoots(),
            ]);
            setDrives(drivesData.drives);
            setRoots(rootsData.roots);
            setError(null);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to load data');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        loadData();
    }, []);

    const handleAddRoot = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!selectedDrive || !newPath.trim()) return;

        try {
            setAdding(true);
            await api.createRoot(selectedDrive, newPath.trim());
            setNewPath('');
            await loadData();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to add root');
        } finally {
            setAdding(false);
        }
    };

    const handleDeleteRoot = async (id: number) => {
        if (!confirm('Delete this root? Associated files will be removed.')) return;

        try {
            await api.deleteRoot(id);
            await loadData();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to delete root');
        }
    };

    const handleToggleExclude = async (root: Root) => {
        try {
            await api.updateRoot(root.id, !root.excluded);
            await loadData();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to update root');
        }
    };

    const getDriveName = (driveId: number): string => {
        const drive = drives.find((d) => d.id === driveId);
        return drive?.mount_path || 'Unknown';
    };

    const rootsByDrive = drives.map((drive) => ({
        drive,
        roots: roots.filter((r) => r.drive_id === drive.id),
    }));

    return (
        <div className="screen">
            <div className="screen-header">
                <h2>Root Folders</h2>
                <p className="subtitle">Manage folders to scan within each drive</p>
            </div>

            {drives.length === 0 ? (
                <div className="empty-state">
                    <p>No drives registered yet.</p>
                    <p className="hint">Add a drive first, then add root folders to scan.</p>
                </div>
            ) : (
                <>
                    <form className="add-form" onSubmit={handleAddRoot}>
                        <select
                            value={selectedDrive || ''}
                            onChange={(e) => setSelectedDrive(Number(e.target.value) || null)}
                            className="input select"
                        >
                            <option value="">Select a drive...</option>
                            {drives.map((drive) => (
                                <option key={drive.id} value={drive.id}>
                                    {drive.mount_path}
                                </option>
                            ))}
                        </select>
                        <input
                            type="text"
                            placeholder="Enter folder path"
                            value={newPath}
                            onChange={(e) => setNewPath(e.target.value)}
                            className="input"
                            disabled={!selectedDrive}
                        />
                        <button
                            type="submit"
                            className="btn btn-primary"
                            disabled={adding || !selectedDrive}
                        >
                            {adding ? 'Adding...' : 'Add Root'}
                        </button>
                    </form>

                    {error && <div className="error-banner">{error}</div>}

                    {loading ? (
                        <div className="loading">Loading roots...</div>
                    ) : (
                        <div className="roots-list">
                            {rootsByDrive.map(({ drive, roots: driveRoots }) => (
                                <div key={drive.id} className="drive-section">
                                    <h3 className="drive-title">
                                        <span className="drive-icon">💾</span>
                                        {drive.mount_path}
                                    </h3>
                                    {driveRoots.length === 0 ? (
                                        <p className="no-roots">No roots added to this drive.</p>
                                    ) : (
                                        <ul className="root-items">
                                            {driveRoots.map((root) => (
                                                <li
                                                    key={root.id}
                                                    className={`root-item ${root.excluded ? 'excluded' : ''}`}
                                                >
                                                    <span className="root-icon">📁</span>
                                                    <span className="root-path">{root.path}</span>
                                                    <div className="root-actions">
                                                        <button
                                                            className={`btn btn-sm ${root.excluded ? 'btn-success' : 'btn-warning'}`}
                                                            onClick={() => handleToggleExclude(root)}
                                                            title={root.excluded ? 'Include in scan' : 'Exclude from scan'}
                                                        >
                                                            {root.excluded ? 'Include' : 'Exclude'}
                                                        </button>
                                                        <button
                                                            className="btn btn-sm btn-danger"
                                                            onClick={() => handleDeleteRoot(root.id)}
                                                            title="Delete root"
                                                        >
                                                            Delete
                                                        </button>
                                                    </div>
                                                </li>
                                            ))}
                                        </ul>
                                    )}
                                </div>
                            ))}
                        </div>
                    )}
                </>
            )}
        </div>
    );
}
