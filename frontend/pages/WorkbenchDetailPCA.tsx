import React, { useState, useEffect } from 'react';
import WorkbenchDetailPCAScatterPlot from '../components/WorkbenchDetailPCAScatterPlot';
import WorkbenchDetailPCACorrelationHeatmap from '../components/WorkbenchDetailPCACorrelationHeatmap';
import WorkbenchDetailPCAReplicateComparison from '../components/WorkbenchDetailPCAReplicateComparison';
import WorkbenchDetailPCAGeneLoadingsTable from '../components/WorkbenchDetailPCAGeneLoadingsTable';

type PCASubTab = 'pca-plot' | 'correlation' | 'replicate' | 'loadings';

interface WorkbenchDetailPCAProps {
  workbenchId: number;
}

const WorkbenchDetailPCA: React.FC<WorkbenchDetailPCAProps> = ({ workbenchId }) => {
  const [activeSubTab, setActiveSubTab] = useState<PCASubTab>('pca-plot');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hasInsufficientReplicates, setHasInsufficientReplicates] = useState(false);
  const [sampleStructure, setSampleStructure] = useState<Record<string, number>>({});

  useEffect(() => {
    const checkReplicates = async () => {
      try {
        setIsLoading(true);

        const response = await fetch(`/api/workbenches/${workbenchId}`, {
          credentials: 'include'
        });

        if (!response.ok) {
          throw new Error('Failed to fetch workbench data');
        }

        const data = await response.json();
        const samples = data.samples || [];

        // Count replicates per group
        const groupCounts: Record<string, number> = {};
        samples.forEach((sample: any) => {
          const groupName = sample.groupName || sample.group_name || sample.group || 'Unknown';
          groupCounts[groupName] = (groupCounts[groupName] || 0) + 1;
        });

        setSampleStructure(groupCounts);

        // Check if any group has less than 2 replicates
        const insufficient = Object.values(groupCounts).some(count => count < 2);
        setHasInsufficientReplicates(insufficient);

        setIsLoading(false);
      } catch (err) {
        console.error('Error checking replicates:', err);
        setError('Failed to load sample information');
        setIsLoading(false);
      }
    };

    checkReplicates();
  }, [workbenchId]);

  const tabs = [
    {
      id: 'pca-plot' as PCASubTab,
      label: 'PCA Plot',
      icon: (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
        </svg>
      ),
    },
    {
      id: 'correlation' as PCASubTab,
      label: 'Sample Correlation',
      icon: (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 5a1 1 0 011-1h4a1 1 0 011 1v7a1 1 0 01-1 1H5a1 1 0 01-1-1V5zM14 5a1 1 0 011-1h4a1 1 0 011 1v7a1 1 0 01-1 1h-4a1 1 0 01-1-1V5zM4 16a1 1 0 011-1h4a1 1 0 011 1v3a1 1 0 01-1 1H5a1 1 0 01-1-1v-3zM14 16a1 1 0 011-1h4a1 1 0 011 1v3a1 1 0 01-1 1h-4a1 1 0 01-1-1v-3z" />
        </svg>
      ),
    },
    {
      id: 'replicate' as PCASubTab,
      label: 'Replicate Comparison',
      icon: (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
        </svg>
      ),
    },
    {
      id: 'loadings' as PCASubTab,
      label: 'Gene Loadings',
      icon: (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 10h18M3 14h18m-9-4v8m-7 0h14a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
        </svg>
      ),
    },
  ];

  const renderSubTabContent = () => {
    switch (activeSubTab) {
      case 'pca-plot':
        return <WorkbenchDetailPCAScatterPlot workbenchId={workbenchId} />;
      case 'correlation':
        return <WorkbenchDetailPCACorrelationHeatmap workbenchId={workbenchId} />;
      case 'replicate':
        return <WorkbenchDetailPCAReplicateComparison workbenchId={workbenchId} />;
      case 'loadings':
        return <WorkbenchDetailPCAGeneLoadingsTable workbenchId={workbenchId} />;
      default:
        return null;
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-6">
        <div className="flex items-center">
          <svg className="w-6 h-6 text-red-500 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <div>
            <h3 className="text-red-800 font-semibold">Error Loading PCA Data</h3>
            <p className="text-red-600 text-sm mt-1">{error}</p>
          </div>
        </div>
      </div>
    );
  }

  // Insufficient replicates warning message
  if (hasInsufficientReplicates) {
    const sampleStructureText = Object.entries(sampleStructure)
      .map(([group, count]) => `${group} (${count})`)
      .join(', ');

    return (
      <div className="flex flex-col h-full">
        <div className="flex-1 flex flex-col min-h-0 bg-white rounded-lg shadow-sm border border-gray-200">
          <div className="p-6 border-b border-gray-200 flex-shrink-0">
            <h2 className="text-2xl font-bold text-gray-900 mb-2">
              PCA Analysis
            </h2>
            <p className="text-gray-600 text-sm">
              Principal Component Analysis of gene expression data with interactive visualizations
            </p>
          </div>

          <div className="flex-1 flex items-center justify-center p-6">
            <div className="max-w-2xl w-full bg-amber-50 border-2 border-amber-200 rounded-xl p-8">
              <div className="flex items-start">
                <svg className="w-12 h-12 text-amber-500 mr-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
                <div className="flex-1">
                  <h3 className="text-xl font-bold text-amber-900 mb-3">
                    ⚠️ Insufficient Replicates for PCA Analysis
                  </h3>
                  <div className="space-y-3 text-amber-800">
                    <p className="text-base">
                      PCA analysis requires at least <span className="font-semibold">2 biological replicates per group</span>.
                    </p>
                    <p className="text-base">
                      Current sample structure: <span className="font-semibold">{sampleStructureText}</span>
                    </p>
                    <div className="mt-4 pt-4 border-t border-amber-300">
                      <p className="text-sm text-amber-700">
                        Please add more biological replicates to enable PCA analysis and ensure statistically valid results.
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 flex flex-col min-h-0 bg-white rounded-lg shadow-sm border border-gray-200">
        <div className="p-6 border-b border-gray-200 flex-shrink-0">
          <h2 className="text-2xl font-bold text-gray-900 mb-2">
            PCA Analysis
          </h2>
          <p className="text-gray-600 text-sm">
            Principal Component Analysis of gene expression data with interactive visualizations
          </p>
        </div>

        <div className="flex-1 flex flex-col min-h-0 p-6">
          {/* 탭 네비게이션 */}
          <div className="border-b border-slate-200 mb-6 flex-shrink-0">
            <nav className="-mb-px flex space-x-8">
              {tabs.map(tab => (
                <button
                  key={tab.id}
                  onClick={() => setActiveSubTab(tab.id)}
                  className={`
                    flex items-center space-x-2 py-4 px-1 border-b-2 font-medium text-sm transition-colors
                    ${activeSubTab === tab.id
                      ? 'border-primary text-primary'
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

          {/* 탭 컨텐츠 */}
          <div className="flex-1 overflow-auto min-h-0">
            {renderSubTabContent()}
          </div>
        </div>
      </div>
    </div>
  );
};

export default WorkbenchDetailPCA;
