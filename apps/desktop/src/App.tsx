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
import { CleanupScreen } from './screens/CleanupScreen';
import { FailureDomainsScreen } from './screens/FailureDomainsScreen';
import { SimulationScreen } from './screens/SimulationScreen';
import { RiskScreen } from './screens/RiskScreen';
import { PlanningScreen } from './screens/PlanningScreen';
import { PlanReviewScreen } from './screens/PlanReviewScreen';

import { Screen, ScreenParams, NavigateFunction } from './types';

function App() {
    const [currentScreen, setCurrentScreen] = useState<Screen>('dashboard');
    const [screenParams, setScreenParams] = useState<ScreenParams>({});

    const handleNavigate: NavigateFunction = (screen, params) => {
        setScreenParams(params || {});
        setCurrentScreen(screen);
    };

    const renderScreen = () => {
        switch (currentScreen) {
            case 'dashboard':
                return <DashboardScreen onNavigate={handleNavigate} />;
            case 'drives':
                return <DrivesScreen onNavigate={handleNavigate} />;
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
            case 'cleanup':
                return <CleanupScreen />;
            case 'failure-domains':
                return <FailureDomainsScreen />;
            case 'simulation':
                return <SimulationScreen />;
            case 'risk':
                return <RiskScreen onNavigate={handleNavigate} />;
            case 'planning':
                return <PlanningScreen onNavigate={handleNavigate} />;
            case 'plan-review':
                return (
                    <PlanReviewScreen
                        planId={screenParams.planId!}
                        onBack={() => handleNavigate('planning')}
                        onNavigate={handleNavigate}
                    />
                );
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
