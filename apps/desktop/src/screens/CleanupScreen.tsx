import { useState, useEffect } from 'react';
import { cleanupApi, exportApi, CleanupRecommendation } from '../api';
import './Screens.css';

export function CleanupScreen() {
    const [recommendations, setRecommendations] = useState<CleanupRecommendation[]>([]);
    const [totalSavingsGb, setTotalSavingsGb] = useState(0);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [selectedFileIds, setSelectedFileIds] = useState<Set<number>>(new Set());
    const [quarantining, setQuarantining] = useState(false);

    const loadRecommendations = async () => {
        try {
            setLoading(true);
            const res = await cleanupApi.getRecommendations(3);
            setRecommendations(res.recommendations);
            setTotalSavingsGb(res.total_savings_gb);
            setError(null);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to load recommendations');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        loadRecommendations();
    }, []);

    const toggleFile = (fileId: number) => {
        setSelectedFileIds(prev => {
            const next = new Set(prev);
            if (next.has(fileId)) {
                next.delete(fileId);
            } else {
                next.add(fileId);
            }
            return next;
        });
    };

    const selectAllForItem = (rec: CleanupRecommendation) => {
        setSelectedFileIds(prev => {
            const next = new Set(prev);
            rec.files_to_delete.forEach(f => next.add(f.id));
            return next;
        });
    };

    const handleQuarantine = async () => {
        if (selectedFileIds.size === 0) return;

        try {
            setQuarantining(true);
            const result = await cleanupApi.quarantineFiles(Array.from(selectedFileIds));
            alert(`Quarantined ${result.moved} files. ${result.errors} errors.`);
            setSelectedFileIds(new Set());
            loadRecommendations();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to quarantine');
        } finally {
            setQuarantining(false);
        }
    };

    const handleOpenExplorer = async (fileId: number) => {
        try {
            await cleanupApi.openInExplorer(fileId);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to open explorer');
        }
    };

    const formatBytes = (bytes: number) => {
        if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
        if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
        return `${(bytes / 1024).toFixed(0)} KB`;
    };

    return (
        <div className="screen">
            <div className="screen-header">
                <h2>Cleanup</h2>
                <p className="subtitle">Review deletion recommendations for items with 3+ copies</p>
            </div>

            {error && <div className="error-banner">{error}</div>}

            {/* Export Buttons */}
            <div className="export-section">
                <h4>📊 Export Reports</h4>
                <div className="export-buttons">
                    <a href={exportApi.getAtRiskUrl()} className="btn btn-sm" download>
                        ⬇️ At-Risk Report
                    </a>
                    <a href={exportApi.getInventoryUrl()} className="btn btn-sm" download>
                        ⬇️ Full Inventory
                    </a>
                    <a href={exportApi.getDuplicatesUrl()} className="btn btn-sm" download>
                        ⬇️ Duplicates Report
                    </a>
                </div>
            </div>

            {/* Summary Banner */}
            {recommendations.length > 0 && (
                <div className="cleanup-summary">
                    <div className="summary-stat">
                        <span className="stat-value">{recommendations.length}</span>
                        <span className="stat-label">Items with excess copies</span>
                    </div>
                    <div className="summary-stat">
                        <span className="stat-value">{totalSavingsGb} GB</span>
                        <span className="stat-label">Potential savings</span>
                    </div>
                    <div className="summary-stat">
                        <span className="stat-value">{selectedFileIds.size}</span>
                        <span className="stat-label">Files selected</span>
                    </div>
                    <button
                        className="btn btn-warning"
                        onClick={handleQuarantine}
                        disabled={selectedFileIds.size === 0 || quarantining}
                    >
                        {quarantining ? 'Moving...' : `🗑️ Quarantine ${selectedFileIds.size} Files`}
                    </button>
                </div>
            )}

            {loading ? (
                <div className="loading">Loading recommendations...</div>
            ) : recommendations.length === 0 ? (
                <div className="empty-state">
                    <p>✅ No items with 3+ copies found.</p>
                    <p className="hint">All your media items are at optimal copy counts.</p>
                </div>
            ) : (
                <div className="recommendations-list">
                    {recommendations.map(rec => (
                        <div key={rec.item_id} className="recommendation-card">
                            <div className="rec-header">
                                <div className="rec-title">
                                    <span className="rec-type">{rec.type.toUpperCase()}</span>
                                    <strong>{rec.title || `Item #${rec.item_id}`}</strong>
                                </div>
                                <div className="rec-meta">
                                    <span>{rec.total_copies} copies</span>
                                    <span className="savings">Save {formatBytes(rec.savings_bytes)}</span>
                                </div>
                            </div>

                            <div className="rec-files">
                                <div className="files-section keep">
                                    <h5>✅ Keep ({rec.keep_count})</h5>
                                    {rec.files_to_keep.map(f => (
                                        <div key={f.id} className="file-row keep">
                                            <span className="file-path" title={f.path}>
                                                {f.path.split(/[/\\]/).pop()}
                                            </span>
                                            <span className="file-drive">{f.drive}</span>
                                        </div>
                                    ))}
                                </div>

                                <div className="files-section delete">
                                    <h5>
                                        🗑️ Recommend Delete ({rec.delete_count})
                                        <button
                                            className="btn btn-sm"
                                            onClick={() => selectAllForItem(rec)}
                                        >
                                            Select All
                                        </button>
                                    </h5>
                                    {rec.files_to_delete.map(f => (
                                        <div key={f.id} className="file-row delete">
                                            <label className="file-checkbox">
                                                <input
                                                    type="checkbox"
                                                    checked={selectedFileIds.has(f.id)}
                                                    onChange={() => toggleFile(f.id)}
                                                />
                                                <span className="file-path" title={f.path}>
                                                    {f.path.split(/[/\\]/).pop()}
                                                </span>
                                            </label>
                                            <span className="file-size">{formatBytes(f.size || 0)}</span>
                                            <span className="file-drive">{f.drive}</span>
                                            <button
                                                className="btn btn-sm"
                                                onClick={() => handleOpenExplorer(f.id)}
                                                title="Open in Explorer"
                                            >
                                                📂
                                            </button>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
