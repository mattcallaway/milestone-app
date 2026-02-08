import { useState } from 'react';
import { Layout } from './components/Layout';
import { DrivesScreen } from './screens/DrivesScreen';
import { RootsScreen } from './screens/RootsScreen';
import { ScanScreen } from './screens/ScanScreen';
import { LibraryScreen } from './screens/LibraryScreen';

type Screen = 'drives' | 'roots' | 'scan' | 'library';

function App() {
    const [currentScreen, setCurrentScreen] = useState<Screen>('drives');

    const renderScreen = () => {
        switch (currentScreen) {
            case 'drives':
                return <DrivesScreen />;
            case 'roots':
                return <RootsScreen />;
            case 'scan':
                return <ScanScreen />;
            case 'library':
                return <LibraryScreen />;
            default:
                return <DrivesScreen />;
        }
    };

    return (
        <Layout currentScreen={currentScreen} onNavigate={(s) => setCurrentScreen(s as Screen)}>
            {renderScreen()}
        </Layout>
    );
}

export default App;
