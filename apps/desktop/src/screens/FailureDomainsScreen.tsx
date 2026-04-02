import React, { useState, useEffect } from 'react';
import { api, failureDomainApi, FailureDomain, Drive } from '../api';
import './Screens.css';

export function FailureDomainsScreen() {
    const [domains, setDomains] = useState<FailureDomain[]>([]);
    const [allDrives, setAllDrives] = useState<Drive[]>([]);
    const [unassignedDrives, setUnassignedDrives] = useState<Drive[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    // New domain form
    const [newName, setNewName] = useState('');
    const [newDesc, setNewDesc] = useState('');
    const [creating, setCreating] = useState(false);

    // Edit state
    const [editingId, setEditingId] = useState<number | null>(null);
    const [editName, setEditName] = useState('');
    const [editDesc, setEditDesc] = useState('');

    const load = async () => {
        try {
            setLoading(true);
            const [domainRes, driveRes] = await Promise.all([
                failureDomainApi.list(),
                api.getDrives(),
            ]);
            setDomains(domainRes.domains);
            setAllDrives(driveRes.drives);
            setUnassignedDrives(driveRes.drives.filter(d => d.domain_id == null));
            setError(null);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to load');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => { load(); }, []);

    const handleCreate = async () => {
        if (!newName.trim()) return;
        try {
            setCreating(true);
            await failureDomainApi.create(newName.trim(), newDesc.trim() || undefined);
            setNewName('');
            setNewDesc('');
            await load();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to create domain');
        } finally {
            setCreating(false);
        }
    };

    const handleDelete = async (id: number) => {
        if (!confirm('Delete this failure domain? Drives assigned to it will become unassigned.')) return;
        try {
            await failureDomainApi.delete(id);
            await load();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to delete domain');
        }
    };

    const startEdit = (domain: FailureDomain) => {
        setEditingId(domain.id);
        setEditName(domain.name);
        setEditDesc(domain.description ?? '');
    };

    const handleSaveEdit = async (id: number) => {
        try {
            await failureDomainApi.update(id, editName.trim(), editDesc.trim() || undefined);
            setEditingId(null);
            await load();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to update domain');
        }
    };

    const handleAssignDrive = async (domainId: number, driveId: number) => {
        try {
            await failureDomainApi.assignDrive(domainId, driveId);
            await load();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to assign drive');
        }
    };

    const handleUnassignDrive = async (domainId: number, driveId: number) => {
        try {
            await failureDomainApi.unassignDrive(domainId, driveId);
            await load();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to unassign drive');
        }
    };

    const totalDrives = allDrives.length;
    const assignedCount = allDrives.filter(d => d.domain_id != null).length;
    const mappingPct = totalDrives > 0 ? Math.round((assignedCount / totalDrives) * 100) : 0;

    return (
        <div className="screen">
            <div className="screen-header">
                <h2>Failure Domains</h2>
                <p className="subtitle">
                    Group drives by shared risk (same enclosure, NAS, power circuit, or location).
                    Resilience analysis requires every drive to be assigned to a domain.
                </p>
            </div>

            {error && <div className="error-banner">{error}</div>}

            {/* Domain mapping progress */}
            {totalDrives > 0 && (
                <div className={`domain-coverage ${mappingPct < 100 ? 'incomplete' : 'complete'}`}>
                    <span className="coverage-icon">{mappingPct < 100 ? '⚠️' : '✅'}</span>
                    <span className="coverage-text">
                        <strong>{assignedCount} / {totalDrives}</strong> drives assigned to a domain
                        {mappingPct < 100 && ' — resilience states may be incomplete until all drives are assigned'}
                    </span>
                    <div className="coverage-bar">
                        <div className="coverage-fill" style={{ width: `${mappingPct}%` }} />
                    </div>
                </div>
            )}

            {/* Create new domain */}
            <div className="domain-create-form">
                <h3>New Failure Domain</h3>
                <div className="form-row">
                    <input
                        id="domain-name-input"
                        className="input"
                        placeholder="Domain name (e.g. USB Enclosure A, NAS, Office)"
                        value={newName}
                        onChange={e => setNewName(e.target.value)}
                        onKeyDown={e => e.key === 'Enter' && handleCreate()}
                    />
                    <input
                        id="domain-desc-input"
                        className="input"
                        placeholder="Description (optional)"
                        value={newDesc}
                        onChange={e => setNewDesc(e.target.value)}
                    />
                    <button
                        id="create-domain-btn"
                        className="btn btn-primary"
                        onClick={handleCreate}
                        disabled={!newName.trim() || creating}
                    >
                        {creating ? 'Creating…' : '+ Create Domain'}
                    </button>
                </div>
            </div>

            {loading ? (
                <div className="loading">Loading domains…</div>
            ) : domains.length === 0 ? (
                <div className="empty-state">
                    <p>🗂️ No failure domains defined yet.</p>
                    <p className="hint">
                        Create domains to represent shared-risk groups, then assign your drives to them.
                        Once all drives are assigned, the Items screen will show accurate resilience states.
                    </p>
                </div>
            ) : (
                <div className="domains-list">
                    {domains.map(domain => (
                        <div key={domain.id} className="domain-card">
                            <div className="domain-header">
                                {editingId === domain.id ? (
                                    <div className="domain-edit-row">
                                        <input
                                            className="input"
                                            value={editName}
                                            onChange={e => setEditName(e.target.value)}
                                        />
                                        <input
                                            className="input"
                                            value={editDesc}
                                            placeholder="Description"
                                            onChange={e => setEditDesc(e.target.value)}
                                        />
                                        <button className="btn btn-primary btn-sm" onClick={() => handleSaveEdit(domain.id)}>Save</button>
                                        <button className="btn btn-sm" onClick={() => setEditingId(null)}>Cancel</button>
                                    </div>
                                ) : (
                                    <div className="domain-title-row">
                                        <div>
                                            <strong className="domain-name">{domain.name}</strong>
                                            {domain.description && (
                                                <span className="domain-desc"> — {domain.description}</span>
                                            )}
                                        </div>
                                        <div className="domain-actions">
                                            <span className="domain-drive-count">
                                                {domain.drives?.length ?? 0} drive{(domain.drives?.length ?? 0) !== 1 ? 's' : ''}
                                            </span>
                                            <button className="btn btn-sm" onClick={() => startEdit(domain)}>✏️ Edit</button>
                                            <button className="btn btn-sm btn-danger" onClick={() => handleDelete(domain.id)}>🗑️ Delete</button>
                                        </div>
                                    </div>
                                )}
                            </div>

                            {/* Assigned drives */}
                            <div className="domain-drives">
                                {(domain.drives ?? []).length === 0 ? (
                                    <p className="hint">No drives assigned yet.</p>
                                ) : (
                                    (domain.drives ?? []).map((drive: any) => (
                                        <div key={drive.id} className="domain-drive-row">
                                            <span className="drive-icon">💾</span>
                                            <span className="drive-path">{drive.mount_path}</span>
                                            {drive.volume_label && <span className="drive-label">({drive.volume_label})</span>}
                                            <button
                                                className="btn btn-sm btn-danger"
                                                onClick={() => handleUnassignDrive(domain.id, drive.id)}
                                                title="Remove from this domain"
                                            >
                                                ✕
                                            </button>
                                        </div>
                                    ))
                                )}

                                {/* Assign unassigned drive */}
                                {unassignedDrives.length > 0 && (
                                    <div className="assign-drive-row">
                                        <select
                                            id={`assign-drive-${domain.id}`}
                                            className="input input-sm"
                                            defaultValue=""
                                            onChange={e => {
                                                if (e.target.value) {
                                                    handleAssignDrive(domain.id, parseInt(e.target.value));
                                                    e.target.value = '';
                                                }
                                            }}
                                        >
                                            <option value="">+ Assign an unassigned drive…</option>
                                            {unassignedDrives.map(d => (
                                                <option key={d.id} value={d.id}>
                                                    {d.mount_path}{d.volume_label ? ` (${d.volume_label})` : ''}
                                                </option>
                                            ))}
                                        </select>
                                    </div>
                                )}
                            </div>
                        </div>
                    ))}
                </div>
            )}

            {/* Unassigned drives summary */}
            {unassignedDrives.length > 0 && (
                <div className="unassigned-section">
                    <h3>⚠️ Unassigned Drives ({unassignedDrives.length})</h3>
                    <p className="hint">
                        These drives have no domain. Items whose only copies are on unassigned drives
                        will show incomplete resilience states.
                    </p>
                    <div className="unassigned-list">
                        {unassignedDrives.map(drive => (
                            <div key={drive.id} className="unassigned-drive-row">
                                <span className="drive-icon">💾</span>
                                <span className="drive-path">{drive.mount_path}</span>
                                {drive.volume_label && <span className="drive-label">({drive.volume_label})</span>}
                                <span className="badge badge-warning">No domain</span>
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}
