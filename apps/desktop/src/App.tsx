import { useState } from 'react';
import { Layout } from './components/Layout';
import { DashboardScreen } from './screens/DashboardScreen';
import { DrivesScreen } from './screens/DrivesScreen';
import { RootsScreen } from './screens/RootsScreen';
import { ScanScreen } from './screens/ScanScreen';
import { LibraryScreen } from './screens/LibraryScreen';
import { ItemsScreen } from './screens/ItemsScreen';
import { ItemDetailScreen } from './screens/ItemDetailScreen';
import { OperationsScreen } from './screens/OperationsScreen';

type Screen = 'dashboard' | 'drives' | 'roots' | 'scan' | 'library' | 'items' | 'item-detail' | 'operations';

interface ScreenParams {
    itemId?: number;
    type?: string;
    min_copies?: number;
    max_copies?: number;
    status?: string;
}

function App() {
    const [currentScreen, setCurrentScreen] = useState<Screen>('dashboard');
    const [screenParams, setScreenParams] = useState<ScreenParams>({});

    const handleNavigate = (screen: string, params?: Record<string, unknown>) => {
        setScreenParams(params as ScreenParams || {});
        setCurrentScreen(screen as Screen);
    };

    const renderScreen = () => {
        switch (currentScreen) {
            case 'dashboard':
                return <DashboardScreen onNavigate={handleNavigate} />;
            case 'drives':
                return <DrivesScreen />;
            case 'roots':
                return <RootsScreen />;
            case 'scan':
                return <ScanScreen />;
            case 'library':
                return <LibraryScreen />;
            case 'items':
                return (
                    <ItemsScreen
                        initialFilters={{
                            type: screenParams.type,
                            min_copies: screenParams.min_copies,
                            max_copies: screenParams.max_copies,
                            status: screenParams.status,
                        }}
                        onViewItem={(id) => handleNavigate('item-detail', { itemId: id })}
                    />
                );
            case 'item-detail':
                return (
                    <ItemDetailScreen
                        itemId={screenParams.itemId!}
                        onBack={() => handleNavigate('items')}
                    />
                );
            case 'operations':
                return <OperationsScreen />;
            default:
                return <DashboardScreen onNavigate={handleNavigate} />;
        }
    };

    return (
        <Layout currentScreen={currentScreen} onNavigate={(s) => handleNavigate(s)}>
            {renderScreen()}
        </Layout>
    );
}

export default App;
