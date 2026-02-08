import { useState, useEffect } from 'react';
import { api, MediaItemDetail } from '../api';
import './Screens.css';

interface ItemDetailScreenProps {
    itemId: number;
    onBack: () => void;
}

export function ItemDetailScreen({ itemId, onBack }: ItemDetailScreenProps) {
    const [item, setItem] = useState<MediaItemDetail | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [selectedFiles, setSelectedFiles] = useState<Set<number>>(new Set());
    const [mergeTarget, setMergeTarget] = useState<string>('');

    const loadItem = async () => {
        try {
            setLoading(true);
            const data = await api.getItem(itemId);
            setItem(data);
            setError(null);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to load item');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        loadItem();
    }, [itemId]);

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

    const handleSplitFile = async (fileId: number) => {
        if (!confirm('Split this file into a new media item?')) return;

        try {
            await api.splitFile(fileId);
            await loadItem();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to split file');
        }
    };

    const handleMerge = async () => {
        const targetId = parseInt(mergeTarget);
        if (!targetId || isNaN(targetId)) {
            setError('Enter a valid item ID to merge into');
            return;
        }

        if (!confirm(`Merge this item into item #${targetId}?`)) return;

        try {
            await api.mergeItems(targetId, [itemId]);
            onBack(); // Go back since this item no longer exists
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to merge items');
        }
    };

    const handleHashFile = async (fileId: number) => {
        try {
            await api.hashFile(fileId);
            await loadItem();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to hash file');
        }
    };

    const getTypeLabel = (type: string): string => {
        switch (type) {
            case 'movie': return '🎬 Movie';
            case 'tv_episode': return '📺 TV Episode';
            default: return '❓ Unknown';
        }
    };

    const getStatusColor = (status: string): string => {
        switch (status) {
            case 'verified': return '#4caf50';
            case 'needs_verification': return '#ff9800';
            default: return '#888';
        }
    };

    return (
        <div className="screen">
            <div className="screen-header">
                <button className="btn btn-sm btn-secondary" onClick={onBack}>
                    ← Back
                </button>
                <h2>{item?.title || 'Loading...'}</h2>
            </div>

            {error && <div className="error-banner">{error}</div>}

            {loading ? (
                <div className="loading">Loading item details...</div>
            ) : item ? (
                <>
                    <div className="item-detail-card">
                        <div className="detail-header">
                            <span className="detail-type">{getTypeLabel(item.type)}</span>
                            <span
                                className="detail-status"
                                style={{ color: getStatusColor(item.status) }}
                            >
                                {item.status.replace('_', ' ')}
                            </span>
                        </div>

                        <div className="detail-meta">
                            {item.year && <span className="meta-item">Year: {item.year}</span>}
                            {item.season !== null && (
                                <span className="meta-item">Season: {item.season}</span>
                            )}
                            {item.episode !== null && (
                                <span className="meta-item">Episode: {item.episode}</span>
                            )}
                        </div>

                        <div className="detail-copies">
                            <strong>{item.copy_count}</strong> {item.copy_count === 1 ? 'copy' : 'copies'} across drives
                        </div>
                    </div>

                    <section className="detail-section">
                        <h3>File Instances</h3>
                        <div className="file-instances">
                            {item.files.map((file) => (
                                <div key={file.id} className="file-instance">
                                    <div className="file-instance-header">
                                        <span className="file-drive">{file.drive_path}</span>
                                        {file.is_primary && <span className="badge badge-primary">Primary</span>}
                                        <span className={`hash-status hash-${file.hash_status}`}>
                                            {file.hash_status}
                                        </span>
                                    </div>
                                    <div className="file-path">{file.path}</div>
                                    <div className="file-details">
                                        <span>{formatBytes(file.size)}</span>
                                        <span>.{file.ext || '-'}</span>
                                        {file.full_hash && (
                                            <span className="hash-preview" title={file.full_hash}>
                                                SHA: {file.full_hash.slice(0, 12)}...
                                            </span>
                                        )}
                                    </div>
                                    <div className="file-actions">
                                        {file.hash_status !== 'complete' && (
                                            <button
                                                className="btn btn-sm"
                                                onClick={() => handleHashFile(file.id)}
                                            >
                                                Compute Hash
                                            </button>
                                        )}
                                        {item.copy_count > 1 && (
                                            <button
                                                className="btn btn-sm btn-warning"
                                                onClick={() => handleSplitFile(file.id)}
                                            >
                                                Split Out
                                            </button>
                                        )}
                                    </div>
                                </div>
                            ))}
                        </div>
                    </section>

                    <section className="detail-section">
                        <h3>Merge Into Another Item</h3>
                        <div className="merge-controls">
                            <input
                                type="number"
                                placeholder="Target item ID"
                                value={mergeTarget}
                                onChange={(e) => setMergeTarget(e.target.value)}
                                className="input input-sm"
                            />
                            <button
                                className="btn btn-primary"
                                onClick={handleMerge}
                                disabled={!mergeTarget}
                            >
                                Merge →
                            </button>
                        </div>
                        <p className="hint">
                            This will move all files from this item to the target and delete this item.
                        </p>
                    </section>
                </>
            ) : null}
        </div>
    );
}
