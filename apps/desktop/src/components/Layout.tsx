import { ReactNode } from 'react';
import './Layout.css';

interface LayoutProps {
    children: ReactNode;
    currentScreen: string;
    onNavigate: (screen: string) => void;
}

const navItems = [
    { id: 'dashboard', label: 'Dashboard', icon: '📊' },
    { id: 'items', label: 'Items', icon: '🎬' },
    { id: 'operations', label: 'Operations', icon: '⚙️' },
    { id: 'drives', label: 'Drives', icon: '💾' },
    { id: 'roots', label: 'Roots', icon: '📁' },
    { id: 'scan', label: 'Scan', icon: '🔍' },
    { id: 'library', label: 'Library', icon: '📚' },
];

export function Layout({ children, currentScreen, onNavigate }: LayoutProps) {
    return (
        <div className="layout">
            <nav className="sidebar">
                <div className="sidebar-header">
                    <h1>FileScanner</h1>
                </div>
                <ul className="nav-list">
                    {navItems.map((item) => (
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
                </ul>
            </nav>
            <main className="main-content">
                {children}
            </main>
        </div>
    );
}
