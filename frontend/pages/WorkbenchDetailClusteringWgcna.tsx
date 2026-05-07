import React, { useEffect, useState } from 'react';
import { WgcnaModuleInfo, WgcnaModulePreview, WgcnaParams } from '../types';
import { apiService } from '../services/api';
import { WgcnaParameterPanel } from '../components/WgcnaParameterPanel';
import { WgcnaModuleSidebar } from '../components/WgcnaModuleSidebar';
import { WgcnaModuleDetail } from '../components/WgcnaModuleDetail';
import { WgcnaModuleOverviewGrid } from '../components/WgcnaModuleOverviewGrid';
import { VennSetSummary } from '../components/VennSetMenu';

interface WorkbenchDetailClusteringWgcnaProps {
  workbenchId: number;
  onNavigateToVennDiagram: (genes: string[], targetSetIndex?: number) => void;
  vennSetSummaries?: VennSetSummary[];
}

export function WorkbenchDetailClusteringWgcna({ workbenchId, onNavigateToVennDiagram, vennSetSummaries }: WorkbenchDetailClusteringWgcnaProps) {
  const [params, setParams] = useState<WgcnaParams>({
    sourceType: 'variance',
    pValue: 0.05,
    foldChange: 2,
    topNGenes: 5000,
    softPower: 'auto',
    minModuleSize: 30,
    deepSplit: 2,
    mergeCutHeight: 0.25
  });

  // activeParams are run-confirmed params. Data loading follows this state only.
  const [activeParams, setActiveParams] = useState<WgcnaParams>({
    sourceType: 'variance',
    pValue: 0.05,
    foldChange: 2,
    topNGenes: 5000,
    softPower: 'auto',
    minModuleSize: 30,
    deepSplit: 2,
    mergeCutHeight: 0.25
  });

  const [modules, setModules] = useState<WgcnaModuleInfo[]>([]);
  const [selectedModule, setSelectedModule] = useState<string | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedGenes, setSelectedGenes] = useState<Set<string>>(new Set());
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [isSearchResult, setIsSearchResult] = useState<boolean>(false);
  const [isParamsPanelCollapsed, setIsParamsPanelCollapsed] = useState<boolean>(false);
  const [modulePreviews, setModulePreviews] = useState<Record<string, WgcnaModulePreview>>({});
  const [isPreviewLoading, setIsPreviewLoading] = useState<boolean>(false);

  const paramsToRequest = (target: WgcnaParams) => ({
    source_type: target.sourceType as 'deg' | 'variance' | 'tmm',
    p_value: target.sourceType === 'deg' ? target.pValue : undefined,
    fold_change: target.sourceType === 'deg' ? target.foldChange : undefined,
    top_n_genes: target.sourceType === 'variance' ? target.topNGenes : undefined,
    soft_power: target.softPower,
    min_module_size: target.minModuleSize,
    deep_split: target.deepSplit,
    merge_cut_height: target.mergeCutHeight
  });

  const executeWgcnaRun = async (targetParams: WgcnaParams) => {
    setIsRunning(true);
    setError(null);
    try {
      const response = await apiService.runWgcna(workbenchId, paramsToRequest(targetParams));
      if (response.success) {
        setModules(response.modules);
        setSelectedModule(null);
        setIsSearchResult(false);
        setSearchQuery('');
        return true;
      }

      const errorMsg = response.error || 'Analysis failed';
      setError(errorMsg);
      alert(`Error: ${errorMsg}`);
      return false;
    } catch (runError: any) {
      console.error('Failed to run WGCNA:', runError);
      const errorMsg = runError.message || 'Failed to run WGCNA analysis';
      setError(errorMsg);
      alert(`Error: ${errorMsg}`);
      return false;
    } finally {
      setIsRunning(false);
    }
  };

  const loadExistingModules = async (
    search?: string,
    targetParams: WgcnaParams = activeParams,
    autoRunIfMissing = false
  ) => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await apiService.getWgcnaModules(workbenchId, {
        ...paramsToRequest(targetParams),
        search
      });

      if (response.exists) {
        setModules(response.modules);
        setIsSearchResult(response.is_search_result);
        setSearchQuery(response.search_query);

        if (response.modules.length > 0) {
          if (!selectedModule || response.is_search_result) {
            setSelectedModule(null);
          } else {
            const selectedStillExists = response.modules.some((module) => module.id === selectedModule);
            if (!selectedStillExists) {
              setSelectedModule(null);
            }
          }
        }
      } else {
        setModules([]);
        setSelectedModule(null);
        setIsSearchResult(false);
        setSearchQuery('');
        if (!search && autoRunIfMissing) {
          setIsLoading(false);
          await executeWgcnaRun(targetParams);
          return;
        }
      }
    } catch (loadError: any) {
      console.error('Failed to load WGCNA modules:', loadError);
      setError(loadError.message || 'Failed to load modules');
    } finally {
      setIsLoading(false);
    }
  };

  // Load only active(run-confirmed) param set.
  useEffect(() => {
    loadExistingModules(undefined, activeParams, true);
  }, [
    workbenchId,
    activeParams.sourceType,
    activeParams.pValue,
    activeParams.foldChange,
    activeParams.topNGenes,
    activeParams.softPower,
    activeParams.minModuleSize,
    activeParams.deepSplit,
    activeParams.mergeCutHeight
  ]);

  const runAnalysis = async () => {
    const nextParams: WgcnaParams = {
      sourceType: params.sourceType,
      pValue: params.pValue,
      foldChange: params.foldChange,
      topNGenes: params.topNGenes,
      softPower: params.softPower,
      minModuleSize: params.minModuleSize,
      deepSplit: params.deepSplit,
      mergeCutHeight: params.mergeCutHeight
    };

    try {
      // 1) Try loading cached result for exact param set first.
      const existing = await apiService.getWgcnaModules(workbenchId, paramsToRequest(nextParams));
      if (existing.exists) {
        setModules(existing.modules);
        setSelectedModule(null);
        setIsSearchResult(false);
        setSearchQuery('');
        setActiveParams(nextParams);
        return;
      }

      // 2) No cached result: run analysis.
      const runSucceeded = await executeWgcnaRun(nextParams);
      if (runSucceeded) {
        setActiveParams(nextParams);
      }
    } catch (runError: any) {
      console.error('Failed to run WGCNA:', runError);
      const errorMsg = runError.message || 'Failed to run WGCNA analysis';
      setError(errorMsg);
      alert(`Error: ${errorMsg}`);
    }
  };

  const handleModuleSearch = (query: string) => {
    if (query.trim()) {
      setSelectedModule(null);
      loadExistingModules(query.trim(), activeParams);
    } else {
      loadExistingModules(undefined, activeParams);
    }
  };

  useEffect(() => {
    const loadModulePreviews = async () => {
      if (modules.length === 0) {
        setModulePreviews({});
        return;
      }

      setIsPreviewLoading(true);
      try {
        const response = await apiService.getWgcnaModulePreviews(workbenchId, {
          ...paramsToRequest(activeParams),
          module_ids: modules.map((module) => module.id)
        });

        const previewMap: Record<string, WgcnaModulePreview> = {};
        (response.previews || []).forEach((preview) => {
          previewMap[preview.id] = preview;
        });
        setModulePreviews(previewMap);
      } catch (previewError) {
        console.error('Failed to load WGCNA module previews:', previewError);
        setModulePreviews({});
      } finally {
        setIsPreviewLoading(false);
      }
    };

    loadModulePreviews();
  }, [
    workbenchId,
    activeParams.sourceType,
    activeParams.pValue,
    activeParams.foldChange,
    activeParams.topNGenes,
    activeParams.softPower,
    activeParams.minModuleSize,
    activeParams.deepSplit,
    activeParams.mergeCutHeight,
    modules
  ]);

  return (
    <div className="space-y-4">
      {(isLoading || isRunning) && (
        <div className="fixed inset-0 bg-black bg-opacity-30 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-8 flex flex-col items-center gap-4 shadow-xl">
            <div className="animate-spin w-12 h-12 border-4 border-blue-500 border-t-transparent rounded-full"></div>
            <p className="text-lg font-medium text-gray-800">
              {isRunning ? 'Running WGCNA Analysis...' : 'Loading modules...'}
            </p>
            <p className="text-sm text-gray-600">
              {isRunning
                ? 'This may take a few minutes depending on dataset size'
                : 'Please wait...'}
            </p>
          </div>
        </div>
      )}

      {error && !isLoading && !isRunning && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded">
          <div className="flex items-center gap-2">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span>{error}</span>
          </div>
        </div>
      )}

      <div className="flex gap-6">
        <div className={`flex-shrink-0 transition-all duration-300 ${isParamsPanelCollapsed ? 'w-16' : 'w-80'}`}>
          <WgcnaParameterPanel
            params={params}
            onChange={setParams}
            onRun={runAnalysis}
            isRunning={isRunning}
            isCollapsed={isParamsPanelCollapsed}
            onToggleCollapse={() => setIsParamsPanelCollapsed(!isParamsPanelCollapsed)}
          />
        </div>

        <div className="flex-shrink-0 w-64">
          <WgcnaModuleSidebar
            modules={modules}
            selectedModule={selectedModule}
            onSelectModule={setSelectedModule}
            onSelectOverview={() => setSelectedModule(null)}
            onSearch={handleModuleSearch}
            isSearchResult={isSearchResult}
            searchQuery={searchQuery}
            previewsByModule={modulePreviews}
          />
        </div>

        <div className="flex-1 min-w-0">
          {selectedModule !== null ? (
            <WgcnaModuleDetail
              workbenchId={workbenchId}
              moduleId={selectedModule}
              params={activeParams}
              selectedGenes={selectedGenes}
              onSelectionChange={setSelectedGenes}
              onNavigateToVennDiagram={onNavigateToVennDiagram}
              vennSetSummaries={vennSetSummaries}
            />
          ) : modules.length > 0 ? (
            <WgcnaModuleOverviewGrid
              modules={modules}
              previewsByModule={modulePreviews}
              onSelectModule={setSelectedModule}
            />
          ) : (
            <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-12 text-center">
              <svg className="w-16 h-16 mx-auto text-gray-400 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
              </svg>
              <h3 className="text-lg font-medium text-gray-900 mb-2">No Module Selected</h3>
              <p className="text-gray-500">
                {modules.length === 0
                  ? 'Run WGCNA analysis to detect co-expression modules'
                  : 'Select a module from the sidebar to view details'}
              </p>
            </div>
          )}

          {isPreviewLoading && modules.length > 0 && selectedModule === null && (
            <div className="mt-3 text-sm text-slate-500">Loading module previews...</div>
          )}
        </div>
      </div>
    </div>
  );
}
