import { useState, useEffect } from 'react';
import './Screens.css';

const API_BASE = 'http://localhost:8000';

interface Drive {
    id: number;
    mount_path: string;
    volume_label: string;
    domain_name: string | null;
    file_count: number;
    total_size: number;
}

interface SimulationResult {
    simulated_failures: Drive[];
    summary: {
        total_loss_count: number;
        at_risk_count: number;
        domain_violation_count: number;
    };
    total_loss: { item_id: number; type: string; title: string; current_copies: number }[];
    at_risk: { item_id: number; type: string; title: string; current_copies: number; remaining_copies: number }[];
    domain_violations: { item_id: number; type: string; title: string; current_domains: number; remaining_domains: number }[];
}

function formatBytes(bytes: number): string {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

export function SimulationScreen() {
    const [drives, setDrives] = useState<Drive[]>([]);
    const [selectedDrives, setSelectedDrives] = useState<Set<number>>(new Set());
    const [result, setResult] = useState<SimulationResult | null>(null);
    const [loading, setLoading] = useState(true);
    const [simulating, setSimulating] = useState(false);

    useEffect(() => {
        loadDrives();
    }, []);

    const loadDrives = async () => {
        try {
            const res = await fetch(`${API_BASE}/drives`);
            const data = await res.json();
            setDrives(data.drives || []);
        } catch (err) {
            console.error('Failed to load drives:', err);
        } finally {
            setLoading(false);
        }
    };

    const toggleDrive = (id: number) => {
        const next = new Set(selectedDrives);
        if (next.has(id)) next.delete(id);
        else next.add(id);
        setSelectedDrives(next);
        setResult(null);
    };

    const runSimulation = async () => {
        if (selectedDrives.size === 0) return;
        setSimulating(true);
        try {
            const res = await fetch(`${API_BASE}/simulation/drive-failure`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ drive_ids: Array.from(selectedDrives) })
            });
            setResult(await res.json());
        } catch (err) {
            console.error('Simulation failed:', err);
        } finally {
            setSimulating(false);
        }
    };

    if (loading) return <div className="screen">Loading...</div>;

    return (
        <div className="screen">
            <div className="screen-header">
                <h2>🔮 Drive Failure Simulation</h2>
            </div>

            <p className="screen-description">
                Select drives to simulate failure. See what items would be at risk or lost.
                This is purely analytical - no writes are performed.
            </p>

            <div className="simulation-drives">
                <h3>Select Drives to Fail</h3>
                <div className="drive-select-grid">
                    {drives.map(drive => (
                        <div
                            key={drive.id}
                            className={`drive-select-card ${selectedDrives.has(drive.id) ? 'selected' : ''}`}
                            onClick={() => toggleDrive(drive.id)}
                        >
                            <div className="drive-select-icon">💾</div>
                            <div className="drive-select-info">
                                <strong>{drive.volume_label || drive.mount_path}</strong>
                                <span>{drive.mount_path}</span>
                            </div>
                        </div>
                    ))}
                </div>
                <button
                    className="btn btn-primary"
                    onClick={runSimulation}
                    disabled={selectedDrives.size === 0 || simulating}
                >
                    {simulating ? 'Simulating...' : `Simulate ${selectedDrives.size} Drive Failure(s)`}
                </button>
            </div>

            {result && (
                <div className="simulation-results">
                    <h3>Simulation Results</h3>

                    <div className="sim-summary">
                        <div className="sim-stat critical">
                            <span className="stat-value">{result.summary.total_loss_count}</span>
                            <span className="stat-label">Total Loss</span>
                        </div>
                        <div className="sim-stat warning">
                            <span className="stat-value">{result.summary.at_risk_count}</span>
                            <span className="stat-label">At Risk (&lt;2 copies)</span>
                        </div>
                        <div className="sim-stat info">
                            <span className="stat-value">{result.summary.domain_violation_count}</span>
                            <span className="stat-label">Domain Violations</span>
                        </div>
                    </div>

                    {result.total_loss.length > 0 && (
                        <div className="sim-section critical">
                            <h4>🔴 Total Loss ({result.total_loss.length})</h4>
                            <p>These items would lose ALL copies.</p>
                            <div className="sim-items">
                                {result.total_loss.slice(0, 20).map(item => (
                                    <div key={item.item_id} className="sim-item">
                                        <span className="item-type">{item.type}</span>
                                        <span className="item-title">{item.title}</span>
                                        <span className="item-copies">{item.current_copies} → 0</span>
                                    </div>
                                ))}
                                {result.total_loss.length > 20 && (
                                    <div className="more-items">...and {result.total_loss.length - 20} more</div>
                                )}
                            </div>
                        </div>
                    )}

                    {result.at_risk.length > 0 && (
                        <div className="sim-section warning">
                            <h4>🟠 At Risk ({result.at_risk.length})</h4>
                            <p>These items would fall below 2 copies.</p>
                            <div className="sim-items">
                                {result.at_risk.slice(0, 20).map(item => (
                                    <div key={item.item_id} className="sim-item">
                                        <span className="item-type">{item.type}</span>
                                        <span className="item-title">{item.title}</span>
                                        <span className="item-copies">
                                            {item.current_copies} → {item.remaining_copies}
                                        </span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {result.domain_violations.length > 0 && (
                        <div className="sim-section info">
                            <h4>🔵 Domain Violations ({result.domain_violations.length})</h4>
                            <p>These items would lose failure-domain redundancy.</p>
                            <div className="sim-items">
                                {result.domain_violations.slice(0, 20).map(item => (
                                    <div key={item.item_id} className="sim-item">
                                        <span className="item-type">{item.type}</span>
                                        <span className="item-title">{item.title}</span>
                                        <span className="item-copies">
                                            {item.current_domains} → {item.remaining_domains} domains
                                        </span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {result.summary.total_loss_count === 0 &&
                        result.summary.at_risk_count === 0 &&
                        result.summary.domain_violation_count === 0 && (
                            <div className="sim-section success">
                                <h4>✅ All Clear</h4>
                                <p>No items would be at risk if these drives failed.</p>
                            </div>
                        )}
                </div>
            )}
        </div>
    );
}
