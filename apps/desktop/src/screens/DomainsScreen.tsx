import { useState, useEffect } from 'react';
import './Screens.css';

const API_BASE = 'http://localhost:8000';

interface FailureDomain {
    id: number;
    name: string;
    description: string | null;
    domain_type: string;
    drive_count: number;
    drives: { id: number; mount_path: string; volume_label: string }[];
}

interface Drive {
    id: number;
    mount_path: string;
    volume_label: string;
    failure_domain_id: number | null;
}

export function DomainsScreen() {
    const [domains, setDomains] = useState<FailureDomain[]>([]);
    const [drives, setDrives] = useState<Drive[]>([]);
    const [loading, setLoading] = useState(true);
    const [newDomain, setNewDomain] = useState({ name: '', description: '', domain_type: 'enclosure' });
    const [showForm, setShowForm] = useState(false);

    useEffect(() => {
        loadData();
    }, []);

    const loadData = async () => {
        try {
            const [domainsRes, drivesRes] = await Promise.all([
                fetch(`${API_BASE}/domains`),
                fetch(`${API_BASE}/drives`)
            ]);
            const domainsData = await domainsRes.json();
            const drivesData = await drivesRes.json();
            setDomains(domainsData.domains || []);
            setDrives(drivesData.drives || []);
        } catch (err) {
            console.error('Failed to load data:', err);
        } finally {
            setLoading(false);
        }
    };

    const createDomain = async () => {
        if (!newDomain.name.trim()) return;
        try {
            await fetch(`${API_BASE}/domains`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(newDomain)
            });
            setNewDomain({ name: '', description: '', domain_type: 'enclosure' });
            setShowForm(false);
            loadData();
        } catch (err) {
            console.error('Failed to create domain:', err);
        }
    };

    const deleteDomain = async (id: number) => {
        if (!confirm('Delete this failure domain? Drives will be unassigned.')) return;
        try {
            await fetch(`${API_BASE}/domains/${id}`, { method: 'DELETE' });
            loadData();
        } catch (err) {
            console.error('Failed to delete domain:', err);
        }
    };

    const assignDrive = async (driveId: number, domainId: number | null) => {
        try {
            const url = domainId
                ? `${API_BASE}/domains/drives/${driveId}/domain?domain_id=${domainId}`
                : `${API_BASE}/domains/drives/${driveId}/domain`;
            await fetch(url, { method: 'PUT' });
            loadData();
        } catch (err) {
            console.error('Failed to assign drive:', err);
        }
    };

    const unassignedDrives = drives.filter(d =>
        !domains.some(dom => dom.drives.some(dd => dd.id === d.id))
    );

    if (loading) return <div className="screen">Loading...</div>;

    return (
        <div className="screen">
            <div className="screen-header">
                <h2>⚠️ Failure Domains</h2>
                <button className="btn btn-primary" onClick={() => setShowForm(!showForm)}>
                    {showForm ? 'Cancel' : '+ New Domain'}
                </button>
            </div>

            <p className="screen-description">
                Group drives by shared failure risk. Items need copies in 2+ distinct domains to be safe.
            </p>

            {showForm && (
                <div className="form-card">
                    <input
                        type="text"
                        placeholder="Domain name (e.g., USB Hub 1, NAS)"
                        value={newDomain.name}
                        onChange={e => setNewDomain({ ...newDomain, name: e.target.value })}
                    />
                    <input
                        type="text"
                        placeholder="Description (optional)"
                        value={newDomain.description}
                        onChange={e => setNewDomain({ ...newDomain, description: e.target.value })}
                    />
                    <select
                        value={newDomain.domain_type}
                        onChange={e => setNewDomain({ ...newDomain, domain_type: e.target.value })}
                    >
                        <option value="enclosure">Enclosure</option>
                        <option value="nas">NAS</option>
                        <option value="location">Location</option>
                        <option value="power">Power</option>
                    </select>
                    <button className="btn btn-primary" onClick={createDomain}>Create</button>
                </div>
            )}

            <div className="domains-grid">
                {domains.map(domain => (
                    <div key={domain.id} className="domain-card">
                        <div className="domain-header">
                            <h3>{domain.name}</h3>
                            <span className="domain-type">{domain.domain_type}</span>
                            <button className="btn btn-sm btn-danger" onClick={() => deleteDomain(domain.id)}>
                                🗑️
                            </button>
                        </div>
                        {domain.description && <p className="domain-desc">{domain.description}</p>}
                        <div className="domain-drives">
                            <h4>Drives ({domain.drive_count})</h4>
                            {domain.drives.map(drive => (
                                <div key={drive.id} className="drive-tag">
                                    💾 {drive.volume_label || drive.mount_path}
                                    <button
                                        className="btn-remove"
                                        onClick={() => assignDrive(drive.id, null)}
                                        title="Remove from domain"
                                    >×</button>
                                </div>
                            ))}
                            {domain.drive_count === 0 && (
                                <span className="no-drives">No drives assigned</span>
                            )}
                        </div>
                    </div>
                ))}
            </div>

            {unassignedDrives.length > 0 && (
                <div className="unassigned-section">
                    <h3>Unassigned Drives</h3>
                    <p>These drives are not in any failure domain.</p>
                    <div className="unassigned-drives">
                        {unassignedDrives.map(drive => (
                            <div key={drive.id} className="unassigned-drive">
                                <span>💾 {drive.volume_label || drive.mount_path}</span>
                                <select onChange={e => {
                                    const val = e.target.value;
                                    if (val) assignDrive(drive.id, parseInt(val));
                                }}>
                                    <option value="">Assign to domain...</option>
                                    {domains.map(d => (
                                        <option key={d.id} value={d.id}>{d.name}</option>
                                    ))}
                                </select>
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}
