import React from 'react';
import { MfuzzParams } from '../types';

interface MfuzzParameterPanelProps {
  params: MfuzzParams;
  onChange: (params: MfuzzParams) => void;
  onRun: () => void;
  isRunning: boolean;
  isCollapsed: boolean;
  onToggleCollapse: () => void;
}

export const MfuzzParameterPanel = React.memo(function MfuzzParameterPanel({
  params,
  onChange,
  onRun,
  isRunning,
  isCollapsed,
  onToggleCollapse
}: MfuzzParameterPanelProps) {
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
          <h3 className="text-lg font-semibold text-gray-800">Mfuzz Parameters</h3>
          <p className="text-sm text-gray-600 mt-1">
            Configure parameters for fuzzy c-means clustering
          </p>
        </div>
        <div className="p-4 space-y-4 max-h-[calc(100vh-200px)] overflow-y-auto">
        {/* Source Type Selection */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-3">
            Input Source Type
          </label>
          <div className="space-y-2">
            {/* DEG-filtered */}
            <label className={`
              flex items-start gap-3 p-3 border rounded-lg cursor-pointer transition-all
              ${params.sourceType === 'deg' ? 'border-blue-500 bg-blue-50' : 'border-gray-300 hover:border-gray-400'}
            `}>
              <input
                type="radio"
                name="sourceType"
                value="deg"
                checked={params.sourceType === 'deg'}
                onChange={(e) => onChange({ ...params, sourceType: e.target.value as 'deg' | 'variance' | 'tmm' })}
                className="mt-1"
              />
              <div className="flex-1">
                <div className="font-medium text-sm text-gray-800">DEG-filtered</div>
                <p className="text-xs text-gray-600 mt-1">
                  Uses DEGs filtered by P-value and Fold Change (~2,000 genes)
                </p>
              </div>
            </label>

            {/* Variance-filtered (Recommended) */}
            <label className={`
              flex items-start gap-3 p-3 border-2 rounded-lg cursor-pointer transition-all
              ${params.sourceType === 'variance' ? 'border-blue-500 bg-blue-50' : 'border-blue-400 hover:border-blue-500'}
            `}>
              <input
                type="radio"
                name="sourceType"
                value="variance"
                checked={params.sourceType === 'variance'}
                onChange={(e) => onChange({ ...params, sourceType: e.target.value as 'deg' | 'variance' | 'tmm' })}
                className="mt-1"
              />
              <div className="flex-1">
                <div className="font-medium text-sm text-gray-800">
                  Variance-filtered
                  <span className="ml-2 text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded">Recommended</span>
                </div>
                <p className="text-xs text-gray-600 mt-1">
                  Selects top N highly variable genes by MAD. Best for pattern discovery.
                </p>
              </div>
            </label>

            {/* Full TMM */}
            <label className={`
              flex items-start gap-3 p-3 border rounded-lg cursor-pointer transition-all
              ${params.sourceType === 'tmm' ? 'border-blue-500 bg-blue-50' : 'border-gray-300 hover:border-gray-400'}
            `}>
              <input
                type="radio"
                name="sourceType"
                value="tmm"
                checked={params.sourceType === 'tmm'}
                onChange={(e) => onChange({ ...params, sourceType: e.target.value as 'deg' | 'variance' | 'tmm' })}
                className="mt-1"
              />
              <div className="flex-1">
                <div className="font-medium text-sm text-gray-800">
                  Full TMM
                  <span className="ml-2 text-xs bg-yellow-100 text-yellow-700 px-2 py-0.5 rounded">Not Recommended</span>
                </div>
                <p className="text-xs text-gray-600 mt-1">
                  Uses entire TMM matrix (all genes). May introduce noise.
                </p>
              </div>
            </label>
          </div>
        </div>

        {/* DEG Parameters */}
        {params.sourceType === 'deg' && (
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
                  value={params.pValue ?? 0.05}
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
                  value={params.foldChange ?? 2}
                  onChange={(e) => onChange({ ...params, foldChange: parseFloat(e.target.value) })}
                  className="w-full px-2 py-1.5 text-sm border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="2.0"
                />
                <p className="text-xs text-gray-500 mt-1">Log2 fold change cutoff</p>
              </div>
            </div>
          </div>
        )}

        {/* Variance Parameters */}
        {params.sourceType === 'variance' && (
          <div className="bg-green-50 border border-green-200 rounded-lg p-3">
            <h4 className="text-sm font-medium text-gray-800 mb-3">Variance Filter</h4>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">
                Top N Genes
              </label>
              <input
                type="number"
                value={params.topNGenes}
                onChange={(e) => onChange({ ...params, topNGenes: parseInt(e.target.value) })}
                className="w-full px-2 py-1.5 text-sm border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-green-500"
                placeholder="8000"
                min="1000"
                max="20000"
              />
              <p className="text-xs text-gray-500 mt-1">
                Select top N highly variable genes (3,000-10,000 recommended)
              </p>
            </div>
          </div>
        )}

        {/* TMM Warning */}
        {params.sourceType === 'tmm' && (
          <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-3">
            <p className="text-xs text-yellow-800">
              ⚠️ Using all genes may introduce noise. Consider variance-filtered option for better results.
            </p>
          </div>
        )}

        {/* Clustering Parameters */}
        <div className="bg-gray-50 border border-gray-200 rounded-lg p-3">
          <h4 className="text-sm font-medium text-gray-800 mb-3">Clustering</h4>
          <div className="space-y-3">
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">
                Cluster Count
              </label>
              <input
                type="number"
                value={params.clusterCount}
                onChange={(e) => onChange({ ...params, clusterCount: parseInt(e.target.value) })}
                className="w-full px-2 py-1.5 text-sm border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="16"
                min="2"
                max="20"
              />
              <p className="text-xs text-gray-500 mt-1">Number of clusters (c)</p>
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">
                M value
              </label>
              <input
                type="number"
                step="0.1"
                value={params.mValue ?? ''}
                onChange={(e) => onChange({ ...params, mValue: e.target.value ? parseFloat(e.target.value) : null })}
                className="w-full px-2 py-1.5 text-sm border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="auto"
              />
              <p className="text-xs text-gray-500 mt-1">Fuzzification (auto-estimated)</p>
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">
                Min Membership
              </label>
              <input
                type="number"
                step="0.1"
                value={params.minMembership}
                onChange={(e) => onChange({ ...params, minMembership: parseFloat(e.target.value) })}
                className="w-full px-2 py-1.5 text-sm border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="0.5"
                min="0"
                max="1"
              />
              <p className="text-xs text-gray-500 mt-1">Membership cutoff</p>
            </div>
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
