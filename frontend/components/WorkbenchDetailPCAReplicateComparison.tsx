import React, { useState, useEffect } from 'react';
import WorkbenchDetailPCAReplicateFragmentCount from './WorkbenchDetailPCAReplicateFragmentCount';
import WorkbenchDetailPCAReplicateScatter from './WorkbenchDetailPCAReplicateScatter';
import WorkbenchDetailPCAReplicateMA from './WorkbenchDetailPCAReplicateMA';
import WorkbenchDetailPCAReplicateCorrelation from './WorkbenchDetailPCAReplicateCorrelation';

type ReplicateSubTab = 'fragment-count' | 'scatter' | 'ma-plot' | 'correlation';

interface SamplesData {
  workbench_id: number;
  samples: Array<{
    sample_name: string;
    condition: string;
  }>;
  groups: string[];
  status: string;
}

interface WorkbenchDetailPCAReplicateComparisonProps {
  workbenchId: number;
}

const WorkbenchDetailPCAReplicateComparison: React.FC<WorkbenchDetailPCAReplicateComparisonProps> = ({ workbenchId }) => {
  const [activeSubTab, setActiveSubTab] = useState<ReplicateSubTab>('fragment-count');
  const [samplesData, setSamplesData] = useState<SamplesData | null>(null);
  const [selectedGroup, setSelectedGroup] = useState<string>('');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchSamples = async () => {
      setIsLoading(true);
      setError(null);

      try {
        const response = await fetch(`/api/workbenches/${workbenchId}/pca/samples`);
        if (!response.ok) throw new Error('Failed to fetch sample information');
        const result = await response.json();

        if (result.status === 'not_available') {
          setError('Sample information not available');
          setIsLoading(false);
          return;
        }

        setSamplesData(result);

        // Set default selected group
        if (result.groups && result.groups.length > 0) {
          setSelectedGroup(result.groups[0]);
        }

        setIsLoading(false);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error occurred');
        setIsLoading(false);
      }
    };

    fetchSamples();
  }, [workbenchId]);

  const tabs = [
    {
      id: 'fragment-count' as ReplicateSubTab,
      label: 'Fragment Count',
      icon: (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
        </svg>
      ),
    },
    {
      id: 'scatter' as ReplicateSubTab,
      label: 'Scatter Plot',
      icon: (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z" />
        </svg>
      ),
    },
    {
      id: 'ma-plot' as ReplicateSubTab,
      label: 'MA Plot',
      icon: (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 8v8m-4-5v5m-4-2v2m-2 4h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
        </svg>
      ),
    },
    {
      id: 'correlation' as ReplicateSubTab,
      label: 'Correlation Heatmap',
      icon: (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 5a1 1 0 011-1h4a1 1 0 011 1v7a1 1 0 01-1 1H5a1 1 0 01-1-1V5zM14 5a1 1 0 011-1h4a1 1 0 011 1v7a1 1 0 01-1 1h-4a1 1 0 01-1-1V5zM4 16a1 1 0 011-1h4a1 1 0 011 1v3a1 1 0 01-1 1H5a1 1 0 01-1-1v-3zM14 16a1 1 0 011-1h4a1 1 0 011 1v3a1 1 0 01-1 1h-4a1 1 0 01-1-1v-3z" />
        </svg>
      ),
    },
  ];

  const renderSubTabContent = () => {
    switch (activeSubTab) {
      case 'fragment-count':
        return <WorkbenchDetailPCAReplicateFragmentCount workbenchId={workbenchId} selectedGroup={selectedGroup} />;
      case 'scatter':
        return <WorkbenchDetailPCAReplicateScatter workbenchId={workbenchId} selectedGroup={selectedGroup} />;
      case 'ma-plot':
        return <WorkbenchDetailPCAReplicateMA workbenchId={workbenchId} selectedGroup={selectedGroup} />;
      case 'correlation':
        return <WorkbenchDetailPCAReplicateCorrelation workbenchId={workbenchId} selectedGroup={selectedGroup} />;
      default:
        return null;
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-6">
        <div className="flex items-center">
          <svg className="w-6 h-6 text-yellow-500 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <div>
            <h3 className="text-yellow-800 font-semibold">Data Not Available</h3>
            <p className="text-yellow-700 text-sm mt-1">{error}</p>
          </div>
        </div>
      </div>
    );
  }

  if (!samplesData || !selectedGroup) {
    return null;
  }

  return (
    <div className="flex gap-4 h-full">
      {/* Sidebar - Group Selector */}
      <div className="w-64 flex-shrink-0">
        <div className="bg-gray-50 border border-gray-200 rounded-lg p-4 sticky top-4">
          <label className="text-sm font-medium text-gray-700 mb-3 block">
            Select Sample Group
          </label>
          <div className="flex flex-col gap-2">
            {samplesData.groups.map((group) => (
              <button
                key={group}
                onClick={() => setSelectedGroup(group)}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors text-left ${
                  selectedGroup === group
                    ? 'bg-blue-500 text-white shadow-sm'
                    : 'bg-white text-gray-700 border border-gray-300 hover:bg-gray-100'
                }`}
              >
                {group}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 min-w-0 space-y-4">
        {/* Sub-tab Navigation */}
        <div className="border-b border-slate-200">
          <nav className="-mb-px flex space-x-8">
            {tabs.map(tab => (
              <button
                key={tab.id}
                onClick={() => setActiveSubTab(tab.id)}
                className={`
                  flex items-center space-x-2 py-4 px-1 border-b-2 font-medium text-sm transition-colors
                  ${activeSubTab === tab.id
                    ? 'border-blue-500 text-blue-600'
                    : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300'
                  }
                `}
              >
                {tab.icon}
                <span>{tab.label}</span>
              </button>
            ))}
          </nav>
        </div>

        {/* Sub-tab Content */}
        <div className="min-h-0">
          {renderSubTabContent()}
        </div>
      </div>
    </div>
  );
};

export default WorkbenchDetailPCAReplicateComparison;
