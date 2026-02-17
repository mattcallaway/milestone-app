import { useState, useEffect } from 'react';
import { expertApi, ExpertStatus } from '../api';
import './Screens.css';

const CONFIRMATION_PHRASE = 'I UNDERSTAND THIS SOFTWARE CAN CAUSE IRREVERSIBLE DATA LOSS';

export default function SettingsScreen() {
    const [expertStatus, setExpertStatus] = useState<ExpertStatus | null>(null);
    const [phrase, setPhrase] = useState('');
    const [persist, setPersist] = useState(false);
    const [error, setError] = useState('');
    const [showConfirm, setShowConfirm] = useState(false);

    const loadStatus = async () => {
        try {
            const status = await expertApi.status();
            setExpertStatus(status);
        } catch (e: any) {
            setError(e.message);
        }
    };

    useEffect(() => { loadStatus(); }, []);

    const handleActivate = async () => {
        setError('');
        try {
            const status = await expertApi.activate(phrase, persist);
            setExpertStatus(status);
            setPhrase('');
            setShowConfirm(false);
        } catch (e: any) {
            setError(e.message);
        }
    };

    const handleDeactivate = async () => {
        try {
            await expertApi.deactivate();
            setExpertStatus({ active: false, activated_at: null, persistent: false, confirmation_required: CONFIRMATION_PHRASE });
        } catch (e: any) {
            setError(e.message);
        }
    };

    return (
        <div className="screen">
            <div className="screen-header">
                <h2>⚙️ Settings</h2>
                <p className="subtitle">Application configuration and expert mode controls</p>
            </div>

            {/* Expert Mode Section */}
            <div className="settings-section">
                <h3 className="settings-section-title">
                    <span className="settings-icon">🔓</span>
                    Expert Mode
                </h3>

                <div className="settings-card expert-card">
                    <div className="expert-status-row">
                        <div className="expert-status-info">
                            <span className={`expert-badge ${expertStatus?.active ? 'active' : 'inactive'}`}>
                                {expertStatus?.active ? '🔴 ACTIVE' : '🟢 SAFE MODE'}
                            </span>
                            {expertStatus?.active && expertStatus?.activated_at && (
                                <span className="expert-since">
                                    Since {new Date(expertStatus.activated_at).toLocaleString()}
                                </span>
                            )}
                        </div>
                    </div>

                    <p className="expert-description">
                        Expert Mode unlocks advanced, potentially destructive operations:
                        hardlinks, batch reduction, drive evacuation, library normalization,
                        safety overrides, and multi-failure simulation.
                    </p>

                    {!expertStatus?.active ? (
                        <>
                            {!showConfirm ? (
                                <button
                                    className="btn btn-warning btn-lg"
                                    onClick={() => setShowConfirm(true)}
                                >
                                    ⚠️ Enable Expert Mode
                                </button>
                            ) : (
                                <div className="expert-confirm-panel">
                                    <div className="expert-warning-box">
                                        <p><strong>⚠️ WARNING</strong></p>
                                        <p>Expert Mode enables operations that can cause
                                            <strong> irreversible data loss</strong>. Incorrect use of
                                            expert features can destroy files permanently.</p>
                                        <p>Type the exact phrase below to confirm you understand the risks:</p>
                                        <code className="expert-phrase">{CONFIRMATION_PHRASE}</code>
                                    </div>

                                    <input
                                        className="input expert-input"
                                        type="text"
                                        value={phrase}
                                        onChange={(e) => setPhrase(e.target.value)}
                                        placeholder="Type confirmation phrase..."
                                    />

                                    <label className="expert-persist-label">
                                        <input
                                            type="checkbox"
                                            checked={persist}
                                            onChange={(e) => setPersist(e.target.checked)}
                                        />
                                        <span>Persist across restarts (not recommended)</span>
                                    </label>

                                    <div className="expert-confirm-actions">
                                        <button
                                            className="btn btn-danger"
                                            disabled={phrase !== CONFIRMATION_PHRASE}
                                            onClick={handleActivate}
                                        >
                                            Activate Expert Mode
                                        </button>
                                        <button
                                            className="btn"
                                            onClick={() => { setShowConfirm(false); setPhrase(''); }}
                                        >
                                            Cancel
                                        </button>
                                    </div>
                                </div>
                            )}
                        </>
                    ) : (
                        <div className="expert-active-panel">
                            <p className="expert-active-warning">
                                🔴 Expert Mode is active. Advanced destructive operations are unlocked.
                            </p>
                            <button className="btn btn-success" onClick={handleDeactivate}>
                                Deactivate Expert Mode
                            </button>
                        </div>
                    )}

                    {error && <p className="error-text">{error}</p>}
                </div>
            </div>
        </div>
    );
}
