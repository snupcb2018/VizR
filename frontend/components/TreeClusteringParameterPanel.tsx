import React from 'react';
import { ClusterParams } from '../types';

interface TreeClusteringParameterPanelProps {
  params: ClusterParams;
  onChange: (params: ClusterParams) => void;
  onRun: () => void;
  isRunning: boolean;
  isCollapsed: boolean;
  onToggleCollapse: () => void;
}

export const TreeClusteringParameterPanel = React.memo(function TreeClusteringParameterPanel({
  params,
  onChange,
  onRun,
  isRunning,
  isCollapsed,
  onToggleCollapse
}: TreeClusteringParameterPanelProps) {
  // Collapsed view (vertical sidebar)
  if (isCollapsed) {
    return (
      <div className="bg-gray-50 rounded-lg border-2 border-gray-300 shadow-sm sticky top-4 h-[calc(100vh-120px)] hover:border-blue-400 transition-all">
        <button
          onClick={onToggleCollapse}
          className="w-full h-full hover:bg-gray-100 transition-colors flex flex-col items-center justify-center gap-3 py-6 group"
          title="Expand parameters"
        >
          {/* Top drag handle */}
          <div className="flex flex-col gap-1">
            <div className="w-6 h-0.5 bg-gray-400 rounded group-hover:bg-blue-500 transition-colors"></div>
            <div className="w-6 h-0.5 bg-gray-400 rounded group-hover:bg-blue-500 transition-colors"></div>
            <div className="w-6 h-0.5 bg-gray-400 rounded group-hover:bg-blue-500 transition-colors"></div>
          </div>

          {/* Spacer */}
          <div className="flex-1"></div>

          {/* Vertical text and arrow (grouped together) */}
          <div className="flex flex-col items-center gap-2">
            <div className="text-xs font-semibold text-gray-600 group-hover:text-blue-600 transition-colors" style={{ writingMode: 'vertical-rl', textOrientation: 'mixed' }}>
              Params
            </div>

            {/* Double chevron icon */}
            <svg className="w-5 h-5 text-gray-500 group-hover:text-blue-600 transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M9 5l7 7-7 7" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 5l7 7-7 7" opacity="0.5" />
            </svg>
          </div>

          {/* Spacer */}
          <div className="flex-1"></div>

          {/* Bottom drag handle */}
          <div className="flex flex-col gap-1">
            <div className="w-6 h-0.5 bg-gray-400 rounded group-hover:bg-blue-500 transition-colors"></div>
            <div className="w-6 h-0.5 bg-gray-400 rounded group-hover:bg-blue-500 transition-colors"></div>
            <div className="w-6 h-0.5 bg-gray-400 rounded group-hover:bg-blue-500 transition-colors"></div>
          </div>
        </button>
      </div>
    );
  }

  // Expanded view (normal)
  return (
    <div className="bg-white rounded-lg border border-gray-200 shadow-sm sticky top-4 flex overflow-hidden">
      {/* Main content */}
      <div className="flex-1">
        <div className="p-4 border-b border-gray-200">
          <h3 className="text-lg font-semibold text-gray-800">Clustering Parameters</h3>
          <p className="text-sm text-gray-600 mt-1">
            Configure parameters for hierarchical tree clustering
          </p>
        </div>
        <div className="p-4 space-y-4 max-h-[calc(100vh-200px)] overflow-y-auto">
        {/* DEG Filter Parameters */}
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
          <h4 className="text-sm font-medium text-gray-800 mb-3">DEG Filter</h4>
          <div className="space-y-3">
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">
                P-value
              </label>
              <input
                type="number"
                step="0.01"
                value={params.pValue}
                onChange={(e) => onChange({ ...params, pValue: parseFloat(e.target.value) })}
                className="w-full px-2 py-1.5 text-sm border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="0.05"
              />
              <p className="text-xs text-gray-500 mt-1">Significance cutoff</p>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">
                Fold Change
              </label>
              <input
                type="number"
                step="0.1"
                value={params.foldChange}
                onChange={(e) => onChange({ ...params, foldChange: parseFloat(e.target.value) })}
                className="w-full px-2 py-1.5 text-sm border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="2.0"
              />
              <p className="text-xs text-gray-500 mt-1">Log2 fold change threshold</p>
            </div>
          </div>
        </div>

        {/* Clustering Parameters */}
        <div className="bg-gray-50 border border-gray-200 rounded-lg p-3">
          <h4 className="text-sm font-medium text-gray-800 mb-3">Clustering</h4>
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">
              Ptree
            </label>
            <input
              type="number"
              value={params.ptree}
              onChange={(e) => onChange({ ...params, ptree: parseInt(e.target.value) })}
              className="w-full px-2 py-1.5 text-sm border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="30"
              min="1"
              max="100"
            />
            <p className="text-xs text-gray-500 mt-1">Tree cutting height percentile (1-100)</p>
          </div>
        </div>

        {/* Run Button */}
        <div className="pt-2">
          <button
            onClick={onRun}
            disabled={isRunning}
            className={`
              w-full px-4 py-2.5 rounded-md font-medium text-white text-sm
              transition-colors duration-200
              ${
                isRunning
                  ? 'bg-gray-400 cursor-not-allowed'
                  : 'bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500'
              }
            `}
          >
            {isRunning ? (
              <div className="flex items-center justify-center">
                <div className="animate-spin w-4 h-4 border-2 border-white border-t-transparent rounded-full mr-2"></div>
                Running...
              </div>
            ) : (
              'Run Clustering'
            )}
          </button>
        </div>
      </div>
      </div>

      {/* Vertical collapse button on the right */}
      <button
        onClick={onToggleCollapse}
        className="w-8 bg-gray-50 hover:bg-gray-100 border-l border-gray-200 flex items-center justify-center transition-colors group"
        title="Collapse parameters"
      >
        <svg className="w-4 h-4 text-gray-500 group-hover:text-gray-700" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
        </svg>
      </button>
    </div>
  );
});
