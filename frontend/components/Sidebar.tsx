
import React, { useState, useEffect } from 'react';
import { Workbench, NavigationState, WorkbenchTab } from '../types';
import { useAuth } from '../contexts/AuthContext';
import CreateWorkbenchModal from './CreateWorkbenchModal';
import workbenchIcon from '../src/assets/icons/workbench.png';
import alignmentIcon from '../src/assets/icons/alignment.svg';

interface SidebarProps {
  onNavigate: (state: NavigationState) => void;
  navigationState: NavigationState;
  showComingSoon: () => void;
}

const TAB_ITEMS: { id: WorkbenchTab; label: string; icon: React.ReactNode }[] = [
  { id: 'overview', label: 'Overview', icon: '📋' },
  { id: 'rawdata', label: 'Raw Data', icon: '📁' },
  { id: 'qc', label: 'Quality Control', icon: '✅' },
  { id: 'preprocessing', label: 'Preprocessing', icon: '🔧' },
  { id: 'alignment', label: 'Alignment', icon: '🎯' },
  { id: 'pca', label: 'PCA', icon: '📈' },
  { id: 'count', label: 'Counts', icon: '🔢' },
  { id: 'deg', label: 'DEG', icon: '📊' },
  { id: 'clustering', label: 'Clustering', icon: '🔗' },
  { id: 'heatmap', label: 'Heatmap', icon: '🔥' },
  { id: 'venndiagram', label: 'Venn Diagram', icon: '⭕' },
];

const NavItem = ({
  icon,
  label,
  isActive,
  onClick
}: {
  icon: React.ReactNode;
  label: string;
  isActive: boolean;
  onClick: () => void;
}) => (
  <li>
    <a
      href="#"
      onClick={(e) => { e.preventDefault(); onClick(); }}
      className={`flex items-center p-3 my-1 rounded-lg transition-all duration-200 ${
        isActive ? 'bg-primary/20 text-primary-dark font-semibold shadow-sm' : 'hover:bg-slate-200 text-slate-600'
      }`}
    >
      {icon}
      <span className="ml-3">{label}</span>
    </a>
  </li>
);

const WorkbenchTreeItem = ({
  workbench,
  isExpanded,
  isActive,
  onToggle,
  onTabSelect,
  activeTab,
  isLastWorkbench,
}: {
  workbench: Workbench;
  isExpanded: boolean;
  isActive: boolean;
  onToggle: () => void;
  onTabSelect: (tab: WorkbenchTab) => void;
  activeTab?: WorkbenchTab;
  isLastWorkbench: boolean;
}) => {
  const isShared = workbench.permission === 'shared';

  return (
    <div className="my-0.5">
      {/* Workbench Item */}
      <a
        href="#"
        onClick={(e) => { e.preventDefault(); onToggle(); }}
        className={`flex items-center p-2 pl-6 my-1 rounded-lg transition-all duration-200 ${
          isActive ? 'bg-primary/15 text-primary-dark font-medium' : 'hover:bg-slate-50 text-slate-600'
        }`}
      >
        {isShared ? (
          <ShareIcon className="w-5 h-5 mr-2 flex-shrink-0 text-blue-500" />
        ) : (
          <SidebarAssetIcon src={workbenchIcon} alt="" className="mr-2 h-4 w-4 flex-shrink-0" />
        )}
        <span className="text-sm truncate flex-1">
          {workbench.name}
          {isShared && <span className="ml-1 text-xs text-blue-500">(Shared)</span>}
        </span>
        <svg
          className={`w-4 h-4 text-slate-400 transition-transform flex-shrink-0 ${isExpanded ? 'rotate-90' : ''}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
        </svg>
      </a>

      {/* Tabs */}
      {isExpanded && (
        <div className="ml-8 space-y-0.5">
          {TAB_ITEMS.map((tab) => (
            <a
              key={tab.id}
              href="#"
              onClick={(e) => {
                e.preventDefault();
                onTabSelect(tab.id);
              }}
              className={`flex items-center px-3 py-2 text-sm rounded-lg transition-all duration-150 ${
                activeTab === tab.id
                  ? 'bg-primary/10 text-primary-dark border-l-2 border-primary font-medium'
                  : 'text-slate-600 hover:bg-slate-50'
              }`}
            >
              <span className="mr-2 flex h-4 w-4 items-center justify-center select-none">
                {tab.id === 'alignment' ? (
                  <SidebarAssetIcon src={alignmentIcon} alt="" className="h-4 w-4" />
                ) : (
                  tab.icon
                )}
              </span>
              {tab.label}
            </a>
          ))}
        </div>
      )}
    </div>
  );
};

export default function Sidebar({ onNavigate, navigationState, showComingSoon }: SidebarProps): React.ReactNode {
  const { user } = useAuth();
  const [workbenches, setWorkbenches] = useState<Workbench[]>([]);
  const [expandedWorkbenches, setExpandedWorkbenches] = useState<Set<number>>(new Set());
  const [workbenchSectionExpanded, setWorkbenchSectionExpanded] = useState(true);
  const [loading, setLoading] = useState(true);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);

  const isAdmin = user?.username === 'admin';

  // Fetch workbenches
  useEffect(() => {
    const fetchWorkbenches = async () => {
      try {
        setLoading(true);
        const response = await fetch('/api/workbenches/', {
          credentials: 'include'
        });

        if (!response.ok) {
          throw new Error('Failed to fetch workbenches');
        }

        const data = await response.json();
        setWorkbenches(data.workbenches || []);

        // Auto-expand active workbench
        if (navigationState.workbenchId) {
          setExpandedWorkbenches(new Set([navigationState.workbenchId]));
        }
      } catch (err) {
        console.error('Error fetching workbenches:', err);
        setWorkbenches([]);
      } finally {
        setLoading(false);
      }
    };

    fetchWorkbenches();
  }, [navigationState.page]); // navigationState.page가 변경될 때마다 워크벤치 목록 갱신

  // Auto-expand when navigation changes to a workbench
  useEffect(() => {
    if (navigationState.workbenchId) {
      // Check if the workbench exists in the current list
      const workbenchExists = workbenches.some(wb => wb.id === navigationState.workbenchId);

      if (!workbenchExists) {
        // If workbench doesn't exist in the list, fetch the updated list
        const fetchUpdatedWorkbenches = async () => {
          try {
            const response = await fetch('/api/workbenches/', {
              credentials: 'include'
            });

            if (response.ok) {
              const data = await response.json();
              setWorkbenches(data.workbenches || []);
            }
          } catch (err) {
            console.error('Error fetching updated workbenches:', err);
          }
        };

        fetchUpdatedWorkbenches();
      }

      // Expand the workbench
      setExpandedWorkbenches(prev => new Set(prev).add(navigationState.workbenchId!));
    }
  }, [navigationState.workbenchId, workbenches]);

  const toggleWorkbench = (workbenchId: number) => {
    if (expandedWorkbenches.has(workbenchId)) {
      // 이미 펼쳐진 워크벤치를 클릭하면 접기
      setExpandedWorkbenches(new Set());
    } else {
      // 다른 워크벤치를 클릭하면 해당 워크벤치만 펼치기 (나머지는 접기)
      setExpandedWorkbenches(new Set([workbenchId]));

      // 워크벤치 Overview 페이지로 자동 이동
      onNavigate({
        page: 'workbench',
        workbenchId: workbenchId,
        tab: 'overview',
      });
    }
  };

  const handleWorkbenchSelect = (workbench: Workbench) => {
    onNavigate({
      page: 'workbench',
      workbenchId: workbench.id,
      tab: 'overview',
    });
  };

  const handleTabSelect = (workbenchId: number, tab: WorkbenchTab) => {
    onNavigate({
      page: 'workbench',
      workbenchId,
      tab,
    });
  };

  const isPageActive = (page: string) => {
    return navigationState.page === page && !navigationState.workbenchId;
  };

  const isWorkbenchActive = (workbenchId: number) => {
    return navigationState.page === 'workbench' && navigationState.workbenchId === workbenchId;
  };

  const isAnyWorkbenchActive = () => {
    return navigationState.page === 'workbench';
  };

  const toggleWorkbenchSection = () => {
    setWorkbenchSectionExpanded(!workbenchSectionExpanded);
  };

  const handleWorkbenchCreated = async (workbenchId: number) => {
    setIsCreateModalOpen(false);

    // Fetch updated workbench list
    try {
      const response = await fetch('/api/workbenches/', {
        credentials: 'include'
      });

      if (response.ok) {
        const data = await response.json();
        setWorkbenches(data.workbenches || []);
      }
    } catch (err) {
      console.error('Error fetching updated workbenches:', err);
    }

    // Navigate to the newly created workbench
    onNavigate({
      page: 'workbench',
      workbenchId: workbenchId,
      tab: 'overview',
    });

    // Expand the new workbench
    setExpandedWorkbenches(new Set([workbenchId]));
  };

  return (
    <aside className="w-64 bg-white flex-shrink-0 border-r border-slate-200 flex flex-col">
      {/* Create Workbench Modal */}
      <CreateWorkbenchModal
        isOpen={isCreateModalOpen}
        onClose={() => setIsCreateModalOpen(false)}
        showComingSoon={showComingSoon}
        onWorkbenchCreated={handleWorkbenchCreated}
      />

      <div className="h-16 flex items-center justify-center border-b border-slate-200 px-4">
        <div className="flex items-center text-2xl font-bold text-primary">
          <DnaIcon />
          <span className="ml-2">VizR</span>
        </div>
      </div>
      <nav className="flex-1 p-4 overflow-y-auto">
        <ul>
          {isAdmin ? (
            // Admin menu: Create Account and User Management
            <>
              <NavItem
                icon={<UserPlusIcon />}
                label="Create Account"
                isActive={isPageActive('admin-create-user')}
                onClick={() => onNavigate({ page: 'admin-create-user' })}
              />
              <NavItem
                icon={<UsersIcon />}
                label="User Management"
                isActive={isPageActive('user-management')}
                onClick={() => onNavigate({ page: 'user-management' })}
              />
            </>
          ) : (
            // Regular user menu: Dashboard and Workbench
            <>
              <NavItem
                icon={<DashboardIcon />}
                label="Dashboard"
                isActive={isPageActive('dashboard')}
                onClick={() => onNavigate({ page: 'dashboard' })}
              />

              {/* Workbench Section */}
              <li>
                <a
                  href="#"
                  onClick={(e) => { e.preventDefault(); toggleWorkbenchSection(); }}
                  className={`flex items-center p-3 my-1 rounded-lg transition-all duration-200 ${
                    isAnyWorkbenchActive() ? 'bg-primary/20 text-primary-dark font-semibold shadow-sm' : 'hover:bg-slate-200 text-slate-600'
                  }`}
                >
                  <SidebarAssetIcon src={workbenchIcon} alt="" className="h-7 w-7" />
                  <span className="ml-3 flex-1">Workbench</span>

                  {/* Create Workbench Button */}
                  <button
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      setIsCreateModalOpen(true);
                    }}
                    className="p-1 hover:bg-primary/30 rounded transition-colors mr-1"
                    title="Create New Workbench"
                  >
                    <PlusIcon className="w-4 h-4" />
                  </button>

                  <svg
                    className={`w-4 h-4 transition-transform ${workbenchSectionExpanded ? 'rotate-90' : ''}`}
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                  </svg>
                </a>

                {workbenchSectionExpanded && (
                  <div className="ml-3">
                    {loading ? (
                      <div className="flex items-center justify-center py-4">
                        <div className="animate-spin w-5 h-5 border-2 border-primary border-t-transparent rounded-full"></div>
                      </div>
                    ) : workbenches.length === 0 ? (
                      <div className="text-center py-4 px-3">
                        <p className="text-xs text-slate-500">No workbenches yet</p>
                      </div>
                    ) : (
                      <div className="space-y-0.5">
                        {workbenches.map((wb, index) => (
                          <WorkbenchTreeItem
                            key={wb.id}
                            workbench={wb}
                            isExpanded={expandedWorkbenches.has(wb.id)}
                            isActive={isWorkbenchActive(wb.id)}
                            onToggle={() => toggleWorkbench(wb.id)}
                            onTabSelect={(tab) => handleTabSelect(wb.id, tab)}
                            activeTab={isWorkbenchActive(wb.id) ? navigationState.tab : undefined}
                            isLastWorkbench={index === workbenches.length - 1}
                          />
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </li>
            </>
          )}
        </ul>
      </nav>
    </aside>
  );
}

// SVG Icons
const DnaIcon = () => <svg xmlns="http://www.w3.org/2000/svg" className="h-7 w-7" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M15.3 16.7a4.5 4.5 0 1 1-6.4 0 4.5 4.5 0 1 1 6.4 0Z"/><path d="M15.3 7.3a4.5 4.5 0 1 1-6.4 0 4.5 4.5 0 1 1 6.4 0Z"/><path d="M8.9 12A4.5 4.5 0 1 0 15.3 12"/><path d="M4.6 4.6l.9.9"/><path d="M18.5 18.5l.9.9"/><path d="M18.5 4.6l-.9.9"/><path d="M4.6 18.5l.9-.9"/></svg>;
const DashboardIcon = () => <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" /></svg>;
const SidebarAssetIcon = ({ src, alt, className }: { src: string; alt: string; className?: string }) => (
  <img src={src} alt={alt} className={className} aria-hidden={alt === ''} />
);
const BeakerIcon = ({ className = "h-6 w-6" }: { className?: string }) => <svg xmlns="http://www.w3.org/2000/svg" className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547a2 2 0 00-.547 1.806l.477 2.387a6 6 0 00.517 3.86l.158.318a6 6 0 00.517 3.86l2.387.477a2 2 0 001.806-.547a2 2 0 00.547-1.806l-.477-2.387a6 6 0 00-.517-3.86l-.158-.318a6 6 0 01-.517-3.86l-2.387-.477a2 2 0 01.547-1.806z" /><path strokeLinecap="round" strokeLinejoin="round" d="M14.293 4.293a1 1 0 011.414 0l4 4a1 1 0 01-1.414 1.414L15 6.414V10a1 1 0 11-2 0V6.414l-1.293 1.293a1 1 0 01-1.414-1.414l4-4z" /></svg>;
const ChartIcon = ({ className = "h-6 w-6" }: { className?: string }) => <svg xmlns="http://www.w3.org/2000/svg" className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" /></svg>;
const ShareIcon = ({ className = "h-6 w-6" }: { className?: string }) => <svg xmlns="http://www.w3.org/2000/svg" className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" /></svg>;
const UserPlusIcon = () => <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M18 9v3m0 0v3m0-3h3m-3 0h-3m-2-5a4 4 0 11-8 0 4 4 0 018 0zM3 20a6 6 0 0112 0v1H3v-1z" /></svg>;
const UsersIcon = () => <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" /></svg>;
const PlusIcon = ({ className = "h-5 w-5" }: { className?: string }) => <svg xmlns="http://www.w3.org/2000/svg" className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" /></svg>;
