import React from 'react';
import { WgcnaParams } from '../types';

interface WgcnaParameterPanelProps {
  params: WgcnaParams;
  onChange: (params: WgcnaParams) => void;
  onRun: () => void;
  isRunning: boolean;
  isCollapsed: boolean;
  onToggleCollapse: () => void;
}

export const WgcnaParameterPanel = React.memo(function WgcnaParameterPanel({
  params,
  onChange,
  onRun,
  isRunning,
  isCollapsed,
  onToggleCollapse
}: WgcnaParameterPanelProps) {
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
          <h3 className="text-lg font-semibold text-gray-800">WGCNA Parameters</h3>
          <p className="text-sm text-gray-600 mt-1">
            Configure parameters for weighted gene co-expression network analysis
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
                  Selects top N highly variable genes by MAD. Best for network analysis.
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
                <div className="font-medium text-sm text-gray-800">Full TMM Matrix</div>
                <p className="text-xs text-gray-600 mt-1">
                  Uses entire TMM-normalized matrix (all genes)
                </p>
              </div>
            </label>
          </div>
        </div>

        {/* DEG Parameters */}
        {params.sourceType === 'deg' && (
          <div className="space-y-3 pt-2 border-t border-gray-200">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                P-value Cutoff
              </label>
              <input
                type="number"
                step="0.001"
                value={params.pValue || 0.05}
                onChange={(e) => onChange({ ...params, pValue: parseFloat(e.target.value) })}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Fold Change Cutoff
              </label>
              <input
                type="number"
                step="0.1"
                value={params.foldChange || 2}
                onChange={(e) => onChange({ ...params, foldChange: parseFloat(e.target.value) })}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500"
              />
            </div>
          </div>
        )}

        {/* Variance Parameters */}
        {params.sourceType === 'variance' && (
          <div className="pt-2 border-t border-gray-200">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Top N Variable Genes
            </label>
            <input
              type="number"
              step="100"
              value={params.topNGenes}
              onChange={(e) => onChange({ ...params, topNGenes: parseInt(e.target.value) })}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500"
            />
            <p className="text-xs text-gray-500 mt-1">
              Recommended: 3000-5000 for best results
            </p>
          </div>
        )}

        {/* Soft Thresholding Power */}
        <div className="pt-2 border-t border-gray-200">
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Soft Thresholding Power
          </label>
          <div className="flex gap-2">
            <select
              value={params.softPower === 'auto' ? 'auto' : 'manual'}
              onChange={(e) => {
                if (e.target.value === 'auto') {
                  onChange({ ...params, softPower: 'auto' });
                } else {
                  onChange({ ...params, softPower: 6 });
                }
              }}
              className="px-3 py-2 border border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500"
            >
              <option value="auto">Auto-detect</option>
              <option value="manual">Manual</option>
            </select>
            {params.softPower !== 'auto' && (
              <input
                type="number"
                min="1"
                max="30"
                value={params.softPower}
                onChange={(e) => onChange({ ...params, softPower: parseInt(e.target.value) })}
                className="flex-1 px-3 py-2 border border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500"
              />
            )}
          </div>
          <p className="text-xs text-gray-500 mt-1">
            Auto-detect recommended. Typical range: 4-12
          </p>
        </div>

        {/* Advanced Parameters */}
        <details className="pt-2 border-t border-gray-200">
          <summary className="cursor-pointer text-sm font-medium text-gray-700 hover:text-gray-900">
            Advanced Parameters
          </summary>
          <div className="mt-3 space-y-3">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Min Module Size
              </label>
              <input
                type="number"
                min="10"
                max="200"
                value={params.minModuleSize}
                onChange={(e) => onChange({ ...params, minModuleSize: parseInt(e.target.value) })}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500"
              />
              <p className="text-xs text-gray-500 mt-1">
                Minimum genes per module (default: 30)
              </p>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Deep Split (0-4)
              </label>
              <input
                type="number"
                min="0"
                max="4"
                value={params.deepSplit}
                onChange={(e) => onChange({ ...params, deepSplit: parseInt(e.target.value) })}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500"
              />
              <p className="text-xs text-gray-500 mt-1">
                Sensitivity to cluster splitting (default: 2)
              </p>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Merge Cut Height
              </label>
              <input
                type="number"
                step="0.01"
                min="0"
                max="1"
                value={params.mergeCutHeight}
                onChange={(e) => onChange({ ...params, mergeCutHeight: parseFloat(e.target.value) })}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500"
              />
              <p className="text-xs text-gray-500 mt-1">
                Threshold for merging similar modules (default: 0.25)
              </p>
            </div>
          </div>
        </details>

        {/* Run Button */}
        <div className="pt-4 border-t border-gray-200">
          <button
            onClick={onRun}
            disabled={isRunning}
            className="w-full px-4 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed font-medium flex items-center justify-center gap-2"
          >
            {isRunning ? (
              <>
                <div className="animate-spin w-4 h-4 border-2 border-white border-t-transparent rounded-full"></div>
                Running...
              </>
            ) : (
              <>
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
                Run WGCNA Analysis
              </>
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
