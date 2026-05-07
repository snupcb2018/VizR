import React, { useEffect, useState } from 'react';
import { MfuzzClusterInfo, MfuzzClusterPreview, MfuzzParams } from '../types';
import { apiService } from '../services/api';
import { MfuzzParameterPanel } from '../components/MfuzzParameterPanel';
import { MfuzzClusterSidebar } from '../components/MfuzzClusterSidebar';
import { MfuzzClusterDetail } from '../components/MfuzzClusterDetail';
import { MfuzzClusterOverviewGrid } from '../components/MfuzzClusterOverviewGrid';
import { VennSetSummary } from '../components/VennSetMenu';

interface WorkbenchDetailClusteringMfuzzProps {
  workbenchId: number;
  onNavigateToVennDiagram: (genes: string[], targetSetIndex?: number) => void;
  vennSetSummaries?: VennSetSummary[];
}

export function WorkbenchDetailClusteringMfuzz({ workbenchId, onNavigateToVennDiagram, vennSetSummaries }: WorkbenchDetailClusteringMfuzzProps) {
  const [params, setParams] = useState<MfuzzParams>({
    sourceType: 'variance',
    pValue: 0.05,
    foldChange: 2,
    topNGenes: 8000,
    clusterCount: 16,
    mValue: null,
    minMembership: 0.5
  });

  // activeParams are run-confirmed params. Data loading follows this state only.
  const [activeParams, setActiveParams] = useState<MfuzzParams>({
    sourceType: 'variance',
    pValue: 0.05,
    foldChange: 2,
    topNGenes: 8000,
    clusterCount: 16,
    mValue: null,
    minMembership: 0.5
  });

  const [clusters, setClusters] = useState<MfuzzClusterInfo[]>([]);
  const [selectedCluster, setSelectedCluster] = useState<number | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedGenes, setSelectedGenes] = useState<Set<string>>(new Set());
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [isSearchResult, setIsSearchResult] = useState<boolean>(false);
  const [isParamsPanelCollapsed, setIsParamsPanelCollapsed] = useState<boolean>(false);
  const [clusterPreviews, setClusterPreviews] = useState<Record<number, MfuzzClusterPreview>>({});
  const [isPreviewLoading, setIsPreviewLoading] = useState<boolean>(false);

  const [showIndividualGenes, setShowIndividualGenes] = useState(false);
  const [showMean, setShowMean] = useState(true);
  const [showMedian, setShowMedian] = useState(true);

  const paramsToRequest = (target: MfuzzParams) => ({
    source_type: target.sourceType as 'deg' | 'variance' | 'tmm',
    p_value: target.sourceType === 'deg' ? target.pValue : undefined,
    fold_change: target.sourceType === 'deg' ? target.foldChange : undefined,
    top_n_genes: target.sourceType === 'variance' ? target.topNGenes : undefined,
    cluster_count: target.clusterCount,
    m_value: target.mValue,
    min_membership: target.minMembership
  });

  const executeMfuzzRun = async (targetParams: MfuzzParams) => {
    setIsRunning(true);
    setError(null);
    try {
      const response = await apiService.runMfuzz(workbenchId, paramsToRequest(targetParams));
      if (response.success) {
        setClusters(response.clusters);
        setSelectedCluster(null);
        setIsSearchResult(false);
        setSearchQuery('');
        return true;
      }

      const errorMsg = response.error || 'Clustering failed';
      setError(errorMsg);
      alert(`Error: ${errorMsg}`);
      return false;
    } catch (runError: any) {
      console.error('Failed to run Mfuzz clustering:', runError);
      const errorMsg = runError.message || 'Failed to run clustering';
      setError(errorMsg);
      alert(`Error: ${errorMsg}`);
      return false;
    } finally {
      setIsRunning(false);
    }
  };

  const loadExistingClusters = async (
    search?: string,
    targetParams: MfuzzParams = activeParams,
    autoRunIfMissing = false
  ) => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await apiService.getMfuzzClusters(workbenchId, {
        ...paramsToRequest(targetParams),
        search
      });

      if (response.exists) {
        setClusters(response.clusters);
        setIsSearchResult(response.is_search_result);
        setSearchQuery(response.search_query);

        if (response.clusters.length > 0) {
          if (!selectedCluster || response.is_search_result) {
            setSelectedCluster(null);
          } else {
            const selectedStillExists = response.clusters.some((cluster) => cluster.id === selectedCluster);
            if (!selectedStillExists) {
              setSelectedCluster(null);
            }
          }
        }
      } else {
        setClusters([]);
        setSelectedCluster(null);
        setIsSearchResult(false);
        setSearchQuery('');
        if (!search && autoRunIfMissing) {
          setIsLoading(false);
          await executeMfuzzRun(targetParams);
          return;
        }
      }
    } catch (loadError: any) {
      console.error('Failed to load Mfuzz clusters:', loadError);
      setError(loadError.message || 'Failed to load clusters');
    } finally {
      setIsLoading(false);
    }
  };

  // Load only active(run-confirmed) param set.
  useEffect(() => {
    loadExistingClusters(undefined, activeParams, true);
  }, [
    workbenchId,
    activeParams.sourceType,
    activeParams.pValue,
    activeParams.foldChange,
    activeParams.topNGenes,
    activeParams.clusterCount,
    activeParams.mValue,
    activeParams.minMembership
  ]);

  const runClustering = async () => {
    const nextParams: MfuzzParams = {
      sourceType: params.sourceType,
      pValue: params.pValue,
      foldChange: params.foldChange,
      topNGenes: params.topNGenes,
      clusterCount: params.clusterCount,
      mValue: params.mValue,
      minMembership: params.minMembership
    };

    try {
      // 1) Try loading cached result for exact param set first.
      const existing = await apiService.getMfuzzClusters(workbenchId, paramsToRequest(nextParams));
      if (existing.exists) {
        setClusters(existing.clusters);
        setSelectedCluster(null);
        setIsSearchResult(false);
        setSearchQuery('');
        setActiveParams(nextParams);
        return;
      }

      // 2) No cached result: run clustering.
      const runSucceeded = await executeMfuzzRun(nextParams);
      if (runSucceeded) {
        setActiveParams(nextParams);
      }
    } catch (runError: any) {
      console.error('Failed to run Mfuzz clustering:', runError);
      const errorMsg = runError.message || 'Failed to run clustering';
      setError(errorMsg);
      alert(`Error: ${errorMsg}`);
    }
  };

  const handleClusterSearch = (query: string) => {
    if (query.trim()) {
      setSelectedCluster(null);
      loadExistingClusters(query.trim(), activeParams);
    } else {
      loadExistingClusters(undefined, activeParams);
    }
  };

  useEffect(() => {
    const loadClusterPreviews = async () => {
      if (clusters.length === 0) {
        setClusterPreviews({});
        return;
      }

      setIsPreviewLoading(true);
      try {
        const response = await apiService.getMfuzzClusterPreviews(workbenchId, {
          ...paramsToRequest(activeParams),
          cluster_ids: clusters.map((cluster) => cluster.id)
        });

        const previewMap: Record<number, MfuzzClusterPreview> = {};
        (response.previews || []).forEach((preview) => {
          previewMap[preview.id] = preview;
        });
        setClusterPreviews(previewMap);
      } catch (previewError) {
        console.error('Failed to load Mfuzz cluster previews:', previewError);
        setClusterPreviews({});
      } finally {
        setIsPreviewLoading(false);
      }
    };

    loadClusterPreviews();
  }, [
    workbenchId,
    activeParams.sourceType,
    activeParams.pValue,
    activeParams.foldChange,
    activeParams.topNGenes,
    activeParams.clusterCount,
    activeParams.mValue,
    activeParams.minMembership,
    clusters
  ]);

  return (
    <div className="space-y-4">
      {(isLoading || isRunning) && (
        <div className="fixed inset-0 bg-black bg-opacity-30 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-8 flex flex-col items-center gap-4 shadow-xl">
            <div className="animate-spin w-12 h-12 border-4 border-blue-500 border-t-transparent rounded-full"></div>
            <p className="text-lg font-medium text-gray-800">
              {isRunning ? 'Running Mfuzz Clustering...' : 'Loading clusters...'}
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
          <MfuzzParameterPanel
            params={params}
            onChange={setParams}
            onRun={runClustering}
            isRunning={isRunning}
            isCollapsed={isParamsPanelCollapsed}
            onToggleCollapse={() => setIsParamsPanelCollapsed(!isParamsPanelCollapsed)}
          />
        </div>

        <div className="flex-shrink-0 w-64">
          <MfuzzClusterSidebar
            clusters={clusters}
            selectedCluster={selectedCluster}
            onSelectCluster={setSelectedCluster}
            onSelectOverview={() => setSelectedCluster(null)}
            onSearch={handleClusterSearch}
            isSearchResult={isSearchResult}
            searchQuery={searchQuery}
            previewsByCluster={clusterPreviews}
          />
        </div>

        <div className="flex-1 min-w-0">
          {selectedCluster !== null ? (
            <MfuzzClusterDetail
              workbenchId={workbenchId}
              clusterId={selectedCluster}
              params={activeParams}
              selectedGenes={selectedGenes}
              onSelectionChange={setSelectedGenes}
              showIndividualGenes={showIndividualGenes}
              setShowIndividualGenes={setShowIndividualGenes}
              showMean={showMean}
              setShowMean={setShowMean}
              showMedian={showMedian}
              setShowMedian={setShowMedian}
              onNavigateToVennDiagram={onNavigateToVennDiagram}
              vennSetSummaries={vennSetSummaries}
            />
          ) : clusters.length > 0 ? (
            <MfuzzClusterOverviewGrid
              clusters={clusters}
              previewsByCluster={clusterPreviews}
              onSelectCluster={setSelectedCluster}
            />
          ) : (
            <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-12 text-center">
              <svg className="w-16 h-16 mx-auto text-gray-400 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
              </svg>
              <h3 className="text-lg font-medium text-gray-900 mb-2">No Cluster Selected</h3>
              <p className="text-gray-500">
                {clusters.length === 0
                  ? 'Run Mfuzz clustering to detect temporal expression patterns'
                  : 'Select a cluster from the sidebar to view details'}
              </p>
            </div>
          )}

          {isPreviewLoading && clusters.length > 0 && selectedCluster === null && (
            <div className="mt-3 text-sm text-slate-500">Loading cluster previews...</div>
          )}
        </div>
      </div>
    </div>
  );
}
