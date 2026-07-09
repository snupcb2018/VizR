
import React, { useState, useEffect } from 'react';
import Sidebar from './components/Sidebar';
import Header from './components/Header';
import Dashboard from './pages/Dashboard';
import WorkbenchDetail from './pages/WorkbenchDetail';
import Settings from './pages/Settings';
import AdminCreateUser from './pages/AdminCreateUser';
import UserManagement from './pages/UserManagement';
import ComingSoonModal from './components/ComingSoonModal';
import Login from './pages/Login';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import { UserSettingsProvider } from './contexts/UserSettingsContext';
import { NavigationState, Workbench } from './types';

function AppContent(): React.ReactNode {
  const { isAuthenticated, isLoading, logout, user } = useAuth();
  const [navigationState, setNavigationState] = useState<NavigationState>({ page: 'dashboard' });
  const [isComingSoonModalOpen, setComingSoonModalOpen] = useState(false);

  // Admin 계정이면 Create Account 페이지로 자동 이동
  useEffect(() => {
    if (user?.username === 'admin' && navigationState.page === 'dashboard') {
      setNavigationState({ page: 'admin-create-user' });
    }
  }, [user]);

  const showComingSoon = () => setComingSoonModalOpen(true);

  const handleLogout = async () => {
    try {
      await logout();
      setNavigationState({ page: 'dashboard' });
    } catch (error) {
      console.error('Logout failed:', error);
    }
  };

  const handleNavigate = (state: NavigationState) => {
    setNavigationState(state);
  };

  const handleSelectWorkbench = (workbench: Workbench) => {
    setNavigationState({
      page: 'workbench',
      workbenchId: workbench.id,
      tab: 'overview',
    });
  };

  const handleNavigateToDashboard = () => {
    setNavigationState({ page: 'dashboard' });
  };

  const renderPage = (): React.ReactNode => {
    switch (navigationState.page) {
      case 'dashboard':
        return <Dashboard onSelectWorkbench={handleSelectWorkbench} showComingSoon={showComingSoon} />;
      case 'workbench':
        if (navigationState.workbenchId) {
          return (
            <WorkbenchDetail
              workbenchId={navigationState.workbenchId}
              activeTab={navigationState.tab || 'overview'}
              onNavigateToTab={(tab) => setNavigationState({
                page: 'workbench',
                workbenchId: navigationState.workbenchId,
                tab,
              })}
              showComingSoon={showComingSoon}
              onNavigateToDashboard={handleNavigateToDashboard}
            />
          );
        }
        // Fallback to dashboard if no workbench ID
        return <Dashboard onSelectWorkbench={handleSelectWorkbench} showComingSoon={showComingSoon} />;
      case 'settings':
        return <Settings showComingSoon={showComingSoon} />;
      case 'admin-create-user':
        return <AdminCreateUser />;
      case 'user-management':
        return <UserManagement />;
      default:
        return <Dashboard onSelectWorkbench={handleSelectWorkbench} showComingSoon={showComingSoon} />;
    }
  };

  // Show loading spinner while checking authentication
  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-screen bg-slate-100">
        <div className="animate-spin rounded-full h-32 w-32 border-b-2 border-indigo-600"></div>
      </div>
    );
  }

  // Show login page if not authenticated
  if (!isAuthenticated) {
    return <Login />;
  }

  const mainClasses = navigationState.page === 'workbench'
    ? "flex-1 flex flex-col min-h-0"
    : "flex-1 overflow-y-auto p-4";

  return (
    <div className="flex h-screen bg-slate-100 font-sans text-slate-800">
      <ComingSoonModal isOpen={isComingSoonModalOpen} onClose={() => setComingSoonModalOpen(false)} />
      <Sidebar onNavigate={handleNavigate} navigationState={navigationState} showComingSoon={showComingSoon} />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header showComingSoon={showComingSoon} onLogout={handleLogout} onNavigate={handleNavigate} />
        <main className={mainClasses}>
          {renderPage()}
        </main>
      </div>
    </div>
  );
}

export default function App(): React.ReactNode {
  return (
    <AuthProvider>
      <UserSettingsProvider>
        <AppContent />
      </UserSettingsProvider>
    </AuthProvider>
  );
}
