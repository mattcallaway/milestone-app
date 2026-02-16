import { ReactNode, useState, useEffect } from 'react';
import { expertApi } from '../api';
import './Layout.css';

interface LayoutProps {
    children: ReactNode;
    currentScreen: string;
    onNavigate: (screen: string) => void;
}

const coreNavItems = [
    { id: 'dashboard', label: 'Dashboard', icon: '📊' },
    { id: 'items', label: 'Items', icon: '🎬' },
    { id: 'operations', label: 'Operations', icon: '⚙️' },
    { id: 'cleanup', label: 'Cleanup', icon: '🧹' },
    { id: 'plans', label: 'Plans', icon: '📋' },
    { id: 'domains', label: 'Domains', icon: '⚠️' },
    { id: 'simulation', label: 'Simulation', icon: '🔮' },
    { id: 'drives', label: 'Drives', icon: '💾' },
    { id: 'roots', label: 'Roots', icon: '📁' },
    { id: 'scan', label: 'Scan', icon: '🔍' },
    { id: 'library', label: 'Library', icon: '📚' },
];

const expertNavItems = [
    { id: 'analytics', label: 'Analytics', icon: '📈' },
    { id: 'recovery', label: 'Recovery', icon: '🔧' },
    { id: 'evacuation', label: 'Evacuation', icon: '🚚' },
];

export function Layout({ children, currentScreen, onNavigate }: LayoutProps) {
    const [expertActive, setExpertActive] = useState(false);

    useEffect(() => {
        expertApi.status().then(s => setExpertActive(s.active)).catch(() => { });
        const interval = setInterval(() => {
            expertApi.status().then(s => setExpertActive(s.active)).catch(() => { });
        }, 10000);
        return () => clearInterval(interval);
    }, []);

    return (
        <div className="layout">
            <nav className="sidebar">
                <div className="sidebar-header">
                    <h1>Milestone</h1>
                    <span className="version-tag">v2.0</span>
                </div>

                {/* Expert Mode Banner */}
                {expertActive && (
                    <div className="expert-banner">
                        <span>🔴 EXPERT MODE</span>
                    </div>
                )}

                <ul className="nav-list">
                    {coreNavItems.map((item) => (
                        <li key={item.id}>
                            <button
                                className={`nav-item ${currentScreen === item.id ? 'active' : ''}`}
                                onClick={() => onNavigate(item.id)}
                            >
                                <span className="nav-icon">{item.icon}</span>
                                <span className="nav-label">{item.label}</span>
                            </button>
                        </li>
                    ))}

                    {/* Expert-gated nav items */}
                    {expertActive && (
                        <>
                            <li className="nav-separator"><span>Expert</span></li>
                            {expertNavItems.map((item) => (
                                <li key={item.id}>
                                    <button
                                        className={`nav-item expert ${currentScreen === item.id ? 'active' : ''}`}
                                        onClick={() => onNavigate(item.id)}
                                    >
                                        <span className="nav-icon">{item.icon}</span>
                                        <span className="nav-label">{item.label}</span>
                                    </button>
                                </li>
                            ))}
                        </>
                    )}

                    {/* Settings — always visible */}
                    <li className="nav-separator"><span>System</span></li>
                    <li>
                        <button
                            className={`nav-item ${currentScreen === 'settings' ? 'active' : ''}`}
                            onClick={() => onNavigate('settings')}
                        >
                            <span className="nav-icon">⚙️</span>
                            <span className="nav-label">Settings</span>
                        </button>
                    </li>
                </ul>
            </nav>
            <main className="main-content">
                {children}
            </main>
        </div>
    );
}
