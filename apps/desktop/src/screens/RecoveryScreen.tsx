import React, { useState, useEffect } from 'react';
import { recoveryApi, OrphanResult, AuditEntry } from '../api';
import './Screens.css';

export default function RecoveryScreen() {
    const [tab, setTab] = useState<'orphans' | 'audit'>('orphans');
    const [orphans, setOrphans] = useState<OrphanResult | null>(null);
    const [auditEntries, setAuditEntries] = useState<AuditEntry[]>([]);
    const [auditTotal, setAuditTotal] = useState(0);
    const [auditPage, setAuditPage] = useState(1);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const [repairing, setRepairing] = useState(false);

    const loadOrphans = async () => {
        setLoading(true);
        setError('');
        try {
            const result = await recoveryApi.orphans();
            setOrphans(result);
        } catch (e: any) {
            setError(e.message);
        } finally {
            setLoading(false);
        }
    };

    const loadAuditLog = async (page = 1) => {
        setLoading(true);
        try {
            const result = await recoveryApi.auditLog(page);
            setAuditEntries(result.entries);
            setAuditTotal(result.total);
            setAuditPage(page);
        } catch (e: any) {
            setError(e.message);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        if (tab === 'orphans') loadOrphans();
        else loadAuditLog(1);
    }, [tab]);

    const handleRemoveStale = async (fileIds: number[]) => {
        setRepairing(true);
        try {
            await recoveryApi.repair('remove_stale', fileIds);
            await loadOrphans();
        } catch (e: any) {
            setError(e.message);
        } finally {
            setRepairing(false);
        }
    };

    const handleReindex = async (paths: string[]) => {
        setRepairing(true);
        try {
            await recoveryApi.repair('reindex', [], paths);
            await loadOrphans();
        } catch (e: any) {
            setError(e.message);
        } finally {
            setRepairing(false);
        }
    };

    return (
        <div className="screen">
            <div className="screen-header">
                <h2>🔧 Recovery & Forensics</h2>
                <p className="subtitle">Detect orphaned files, repair index inconsistencies, review audit log</p>
            </div>

            <div className="tab-bar">
                <button className={`tab ${tab === 'orphans' ? 'active' : ''}`} onClick={() => setTab('orphans')}>
                    🔍 Orphan Detection
                </button>
                <button className={`tab ${tab === 'audit' ? 'active' : ''}`} onClick={() => setTab('audit')}>
                    📜 Audit Log
                </button>
            </div>

            {error && <p className="error-text">{error}</p>}

            {tab === 'orphans' && (
                <div className="analytics-section">
                    {loading ? (
                        <div className="loading">Scanning for orphans...</div>
                    ) : orphans ? (
                        <>
                            {/* Summary */}
                            <div className="risk-summary">
                                <div className="risk-summary-card" style={{ borderColor: orphans.summary.missing_count > 0 ? '#f44336' : '#4caf50' }}>
                                    <span className="risk-count" style={{ color: orphans.summary.missing_count > 0 ? '#f44336' : '#4caf50' }}>
                                        {orphans.summary.missing_count}
                                    </span>
                                    <span className="risk-label">Missing on Disk</span>
                                </div>
                                <div className="risk-summary-card" style={{ borderColor: orphans.summary.unindexed_count > 0 ? '#ff9800' : '#4caf50' }}>
                                    <span className="risk-count" style={{ color: orphans.summary.unindexed_count > 0 ? '#ff9800' : '#4caf50' }}>
                                        {orphans.summary.unindexed_count}
                                    </span>
                                    <span className="risk-label">Unindexed on Disk</span>
                                </div>
                            </div>

                            {/* Missing on disk */}
                            {orphans.missing_on_disk.length > 0 && (
                                <div className="orphan-section">
                                    <h3>Missing on Disk (DB entries with no file)</h3>
                                    <div className="items-list">
                                        {orphans.missing_on_disk.map(f => (
                                            <div key={f.file_id} className="item-row">
                                                <div className="item-info">
                                                    <span className="mono item-title">{f.path}</span>
                                                    <span className="item-meta">Drive: {f.drive} · File ID: {f.file_id}</span>
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                    <button
                                        className="btn btn-warning"
                                        disabled={repairing}
                                        onClick={() => handleRemoveStale(orphans.missing_on_disk.map(f => f.file_id))}
                                    >
                                        {repairing ? 'Removing...' : `Remove ${orphans.missing_on_disk.length} Stale Entries`}
                                    </button>
                                </div>
                            )}

                            {/* Unindexed on disk */}
                            {orphans.unindexed_on_disk.length > 0 && (
                                <div className="orphan-section">
                                    <h3>Unindexed on Disk (files not in DB)</h3>
                                    <div className="items-list">
                                        {orphans.unindexed_on_disk.map((f, idx) => (
                                            <div key={idx} className="item-row">
                                                <div className="item-info">
                                                    <span className="mono item-title">{f.path}</span>
                                                    <span className="item-meta">Root ID: {f.root_id}</span>
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                    <button
                                        className="btn btn-primary"
                                        disabled={repairing}
                                        onClick={() => handleReindex(orphans.unindexed_on_disk.map(f => f.path))}
                                    >
                                        {repairing ? 'Reindexing...' : `Reindex ${orphans.unindexed_on_disk.length} Files`}
                                    </button>
                                </div>
                            )}

                            {orphans.summary.missing_count === 0 && orphans.summary.unindexed_count === 0 && (
                                <div className="empty-state">
                                    <p>✅ No orphans detected — library is consistent</p>
                                </div>
                            )}
                        </>
                    ) : (
                        <button className="btn btn-primary" onClick={loadOrphans}>
                            Run Orphan Scan
                        </button>
                    )}
                </div>
            )}

            {tab === 'audit' && (
                <div className="analytics-section">
                    {loading ? (
                        <div className="loading">Loading audit log...</div>
                    ) : (
                        <>
                            <div className="files-table-wrapper">
                                <table className="files-table">
                                    <thead>
                                        <tr>
                                            <th>Time</th>
                                            <th>Action</th>
                                            <th>Entity</th>
                                            <th>Details</th>
                                            <th>Expert</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {auditEntries.map(entry => (
                                            <tr key={entry.id}>
                                                <td className="mono">{new Date(entry.created_at).toLocaleString()}</td>
                                                <td><span className="chip">{entry.action}</span></td>
                                                <td>{entry.entity_type} #{entry.entity_id}</td>
                                                <td className="truncate-cell">{entry.details}</td>
                                                <td>{entry.expert_mode ? '🔴' : '—'}</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>

                            {auditTotal > 50 && (
                                <div className="pagination">
                                    <button
                                        className="btn btn-sm"
                                        disabled={auditPage <= 1}
                                        onClick={() => loadAuditLog(auditPage - 1)}
                                    >
                                        ← Prev
                                    </button>
                                    <span className="page-info">Page {auditPage} of {Math.ceil(auditTotal / 50)}</span>
                                    <button
                                        className="btn btn-sm"
                                        disabled={auditPage >= Math.ceil(auditTotal / 50)}
                                        onClick={() => loadAuditLog(auditPage + 1)}
                                    >
                                        Next →
                                    </button>
                                </div>
                            )}

                            {auditEntries.length === 0 && (
                                <div className="empty-state">
                                    <p>No audit entries yet</p>
                                </div>
                            )}
                        </>
                    )}
                </div>
            )}
        </div>
    );
}
