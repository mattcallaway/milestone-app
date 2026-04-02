import { useState, useEffect, useCallback } from 'react';
import { sidecarApi, SidecarCopy, SidecarCompleteness } from '../api';
import '../screens/Screens.css';

interface SidecarPanelProps {
    itemId: number;
}

const CATEGORY_META: Record<string, { icon: string; label: string; color: string }> = {
    subtitle: { icon: '💬', label: 'Subtitle',  color: '#2196f3' },
    metadata: { icon: '📋', label: 'Metadata',  color: '#9c27b0' },
    artwork:  { icon: '🖼️', label: 'Artwork',    color: '#ff9800' },
    primary:  { icon: '🎬', label: 'Video',      color: '#4caf50' },
};

const COMPLETENESS_META: Record<string, { icon: string; label: string; color: string; bg: string }> = {
    complete:    { icon: '✅', label: 'Complete',    color: '#4caf50', bg: 'rgba(76,175,80,.1)' },
    partial:     { icon: '⚠️', label: 'Partial',     color: '#ff9800', bg: 'rgba(255,152,0,.1)' },
    no_sidecars: { icon: '➖', label: 'No Sidecars', color: '#888',    bg: 'rgba(255,255,255,.05)' },
};

function formatBytes(bytes: number | null | undefined): string {
    if (!bytes) return '';
    const units = ['B', 'KB', 'MB', 'GB'];
    let v = bytes, u = 0;
    while (v >= 1024 && u < units.length - 1) { v /= 1024; u++; }
    return `${v.toFixed(1)} ${units[u]}`;
}

function basename(path: string): string {
    return path.replace(/\\/g, '/').split('/').pop() ?? path;
}

export function SidecarPanel({ itemId }: SidecarPanelProps) {
    const [copies, setCopies] = useState<SidecarCopy[]>([]);
    const [completeness, setCompleteness] = useState<SidecarCompleteness | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [expanded, setExpanded] = useState(false);
    const [includeArtwork, setIncludeArtwork] = useState(false);

    const load = useCallback(async () => {
        try {
            setLoading(true);
            const [sc, comp] = await Promise.all([
                sidecarApi.getSidecars(itemId),
                sidecarApi.getCompleteness(itemId, true, true, false),
            ]);
            setCopies(sc.copies);
            setCompleteness(comp);
            setError(null);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to load sidecars');
        } finally {
            setLoading(false);
        }
    }, [itemId]);

    const reloadCompleteness = async (artwork: boolean) => {
        try {
            const comp = await sidecarApi.getCompleteness(itemId, true, true, artwork);
            setCompleteness(comp);
        } catch { /* ignore */ }
    };

    useEffect(() => { load(); }, [load]);

    const totalSidecars = copies.reduce((sum: number, c: SidecarCopy) => sum + c.sidecar_count, 0);
    const cm = completeness ? COMPLETENESS_META[completeness.completeness] : null;

    return (
        <div className="sidecar-panel">
            {/* Header — always visible */}
            <div
                className="sidecar-panel-header"
                onClick={() => setExpanded((e: boolean) => !e)}
                id="sidecar-panel-toggle"
            >
                <div className="sidecar-summary-left">
                    <span className="sidecar-panel-title">🗂️ Companion Files</span>
                    {cm && (
                        <span
                            className="sidecar-completeness-badge"
                            style={{ background: cm.bg, color: cm.color }}
                        >
                            {cm.icon} {cm.label}
                        </span>
                    )}
                </div>
                <div className="sidecar-summary-right">
                    {!loading && (
                        <span className="sidecar-count-hint">
                            {totalSidecars === 0
                                ? 'No companion files detected'
                                : `${totalSidecars} companion file${totalSidecars !== 1 ? 's' : ''} across ${copies.length} cop${copies.length !== 1 ? 'ies' : 'y'}`
                            }
                        </span>
                    )}
                    <span className="sidecar-chevron">{expanded ? '▲' : '▼'}</span>
                </div>
            </div>

            {expanded && (
                <div className="sidecar-panel-body">
                    {error && <div className="error-banner">{error}</div>}
                    {loading ? (
                        <div className="sidecar-loading">Scanning companion files…</div>
                    ) : (
                        <>
                            {/* Completeness summary */}
                            {completeness && completeness.completeness !== 'no_sidecars' && (
                                <div className="sidecar-completeness-row">
                                    <div className="sidecar-completeness-info">
                                        <strong>
                                            {completeness.total_unique_sidecars} unique companion file{completeness.total_unique_sidecars !== 1 ? 's' : ''}
                                        </strong>
                                        {completeness.missing_on_any_drive && (
                                            <span className="sidecar-missing-warn">
                                                — some backup copies are incomplete
                                            </span>
                                        )}
                                    </div>
                                    <label className="sidecar-artwork-toggle">
                                        <input
                                            type="checkbox"
                                            checked={includeArtwork}
                                            onChange={(e: React.ChangeEvent<HTMLInputElement>) => {
                                                setIncludeArtwork(e.target.checked);
                                                reloadCompleteness(e.target.checked);
                                            }}
                                        />
                                        Include artwork
                                    </label>
                                </div>
                            )}

                            {/* Per-copy breakdown */}
                            {copies.length === 0 ? (
                                <div className="sidecar-empty">
                                    No video copies found for this item.
                                </div>
                            ) : (
                                <div className="sidecar-copies">
                                    {copies.map((copy) => {
                                        const missingNames = completeness?.drives?.[copy.drive_id]?.missing ?? [];
                                        return (
                                            <div key={copy.file_id} className="sidecar-copy-card">
                                                <div className="sidecar-copy-header">
                                                    <span className="sidecar-copy-icon">💿</span>
                                                    <div className="sidecar-copy-info">
                                                        <span className="sidecar-drive-label">
                                                            {copy.drive_mount}
                                                        </span>
                                                        <span className="sidecar-primary-file hint">
                                                            {basename(copy.primary_path)}
                                                        </span>
                                                    </div>
                                                    <span className="sidecar-copy-count">
                                                        {copy.sidecar_count} file{copy.sidecar_count !== 1 ? 's' : ''}
                                                    </span>
                                                </div>

                                                {/* Sidecars on this copy */}
                                                {copy.sidecars.length > 0 ? (
                                                    <div className="sidecar-file-list">
                                                        {copy.sidecars.map((sc, si) => {
                                                            const meta = CATEGORY_META[sc.category] ?? CATEGORY_META.subtitle;
                                                            return (
                                                                <div key={si} className="sidecar-file-row">
                                                                    <span
                                                                        className="sidecar-cat-badge"
                                                                        style={{
                                                                            background: `${meta.color}22`,
                                                                            color: meta.color,
                                                                        }}
                                                                    >
                                                                        {meta.icon} {meta.label}
                                                                    </span>
                                                                    <span className="sidecar-file-name">
                                                                        {basename(sc.path)}
                                                                    </span>
                                                                    {sc.size && (
                                                                        <span className="sidecar-file-size hint">
                                                                            {formatBytes(sc.size)}
                                                                        </span>
                                                                    )}
                                                                </div>
                                                            );
                                                        })}
                                                    </div>
                                                ) : (
                                                    <div className="sidecar-none-on-copy hint">
                                                        No companion files on this copy
                                                    </div>
                                                )}

                                                {/* Missing sidecars warning */}
                                                {missingNames.length > 0 && (
                                                    <div className="sidecar-missing-block">
                                                        <span className="sidecar-missing-label">
                                                            ❌ Missing ({missingNames.length}):
                                                        </span>
                                                        <div className="sidecar-missing-list">
                                                            {missingNames.map((name, mi) => (
                                                                <span key={mi} className="sidecar-missing-file">
                                                                    {name}
                                                                </span>
                                                            ))}
                                                        </div>
                                                    </div>
                                                )}
                                            </div>
                                        );
                                    })}
                                </div>
                            )}

                            {/* No sidecars anywhere */}
                            {totalSidecars === 0 && copies.length > 0 && (
                                <div className="sidecar-empty-hint">
                                    <p>No subtitle, metadata, or artwork files were detected alongside this item&apos;s video files.</p>
                                    <p className="hint">Companion files are detected by matching filenames in the same folder as the video.</p>
                                </div>
                            )}
                        </>
                    )}
                </div>
            )}
        </div>
    );
}
