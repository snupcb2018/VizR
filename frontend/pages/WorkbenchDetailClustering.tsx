import React, { useState } from 'react';
import { WorkbenchDetailClusteringTree } from './WorkbenchDetailClusteringTree';
import { WorkbenchDetailClusteringMfuzz } from './WorkbenchDetailClusteringMfuzz';
import { WorkbenchDetailClusteringWgcna } from './WorkbenchDetailClusteringWgcna';
import { Workbench } from '../types';
import { VennSetSummary } from '../components/VennSetMenu';

type ClusteringSubTab = 'tree' | 'mfuzz' | 'wgcna';

interface WorkbenchDetailClusteringProps {
  workbench: Workbench;
  onNavigateToVennDiagram: (genes: string[], targetSetIndex?: number) => void;
  vennSetSummaries?: VennSetSummary[];
}

export default function WorkbenchDetailClustering({ workbench, onNavigateToVennDiagram, vennSetSummaries }: WorkbenchDetailClusteringProps) {
  const [activeSubTab, setActiveSubTab] = useState<ClusteringSubTab>('tree');

  const tabs = [
    {
      id: 'tree' as ClusteringSubTab,
      label: 'Hierarchical Tree Clustering',
      disabled: false,
    },
    {
      id: 'mfuzz' as ClusteringSubTab,
      label: 'Mfuzz',
      disabled: false,
    },
    {
      id: 'wgcna' as ClusteringSubTab,
      label: 'WGCNA',
      disabled: false,
    },
  ];

  const renderContent = () => {
    switch (activeSubTab) {
      case 'tree':
        return <WorkbenchDetailClusteringTree workbenchId={workbench.id} onNavigateToVennDiagram={onNavigateToVennDiagram} vennSetSummaries={vennSetSummaries} />;
      case 'mfuzz':
        return <WorkbenchDetailClusteringMfuzz workbenchId={workbench.id} onNavigateToVennDiagram={onNavigateToVennDiagram} vennSetSummaries={vennSetSummaries} />;
      case 'wgcna':
        return <WorkbenchDetailClusteringWgcna workbenchId={workbench.id} onNavigateToVennDiagram={onNavigateToVennDiagram} vennSetSummaries={vennSetSummaries} />;
      default:
        return null;
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-gray-800">Clustering Analysis</h2>
        <p className="text-gray-600 mt-1">
          Perform clustering analysis on differential expression data
        </p>
      </div>

      {/* 탭 버튼 */}
      <div className="border-b border-gray-200">
        <nav className="-mb-px flex space-x-4">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => !tab.disabled && setActiveSubTab(tab.id)}
              disabled={tab.disabled}
              className={`
                whitespace-nowrap py-3 px-4 border-b-2 font-medium text-sm
                transition-colors duration-200
                ${
                  activeSubTab === tab.id
                    ? 'border-blue-500 text-blue-600'
                    : tab.disabled
                    ? 'border-transparent text-gray-400 cursor-not-allowed'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }
              `}
            >
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      {/* 탭 내용 */}
      <div className="mt-6">{renderContent()}</div>
    </div>
  );
}
