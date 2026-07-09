import React, { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import { ClusterParams, ClusterInfo, ClusterPreview, TreeMergeSpec, TreeCuttingDendrogramData } from '../types';
import { apiService } from '../services/api';
import { TreeClusteringParameterPanel } from '../components/TreeClusteringParameterPanel';
import { ClusterSidebar, ClusterSidebarItem } from '../components/ClusterSidebar';
import { ClusterDetail } from '../components/ClusterDetail';
import { ClusterOverviewGrid, ClusterOverviewItem } from '../components/ClusterOverviewGrid';
import { MergedClusterDetail } from '../components/MergedClusterDetail';
import { TreeClusterDendrogramPanel } from '../components/TreeClusterDendrogramPanel';
import { VennSetSummary } from '../components/VennSetMenu';

interface WorkbenchDetailClusteringTreeProps {
  workbenchId: number;
  onNavigateToVennDiagram: (genes: string[], targetSetIndex?: number) => void;
  vennSetSummaries?: VennSetSummary[];
}

const isMergedClusterId = (clusterId: string | null) => Boolean(clusterId && clusterId.startsWith('merged_'));

const sortClusterIds = (clusterIds: string[]) => {
  const toNumber = (id: string) => {
    const match = id.match(/\d+/);
    return match ? parseInt(match[0], 10) : Number.MAX_SAFE_INTEGER;
  };
  return [...clusterIds].sort((a, b) => toNumber(a) - toNumber(b));
};

export function WorkbenchDetailClusteringTree({ workbenchId, onNavigateToVennDiagram, vennSetSummaries }: WorkbenchDetailClusteringTreeProps) {
  const [params, setParams] = useState<ClusterParams>({
    pValue: 0.05,
    foldChange: 2,
    ptree: 30
  });
  const [activeParams, setActiveParams] = useState<ClusterParams>({
    pValue: 0.05,
    foldChange: 2,
    ptree: 30
  });
  const [clusters, setClusters] = useState<ClusterInfo[]>([]);
  const [selectedCluster, setSelectedCluster] = useState<string | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedGenes, setSelectedGenes] = useState<Set<string>>(new Set());
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [isSearchResult, setIsSearchResult] = useState<boolean>(false);
  const [isParamsPanelCollapsed, setIsParamsPanelCollapsed] = useState<boolean>(false);
  const [clusterPreviews, setClusterPreviews] = useState<Record<string, ClusterPreview>>({});
  const [isPreviewLoading, setIsPreviewLoading] = useState<boolean>(false);
  const [mergeSpecs, setMergeSpecs] = useState<TreeMergeSpec[]>([]);
  const [mergedPreviews, setMergedPreviews] = useState<Record<string, ClusterPreview>>({});
  const [dendrogramData, setDendrogramData] = useState<TreeCuttingDendrogramData | null>(null);
  const [isDendrogramLoading, setIsDendrogramLoading] = useState<boolean>(false);
  const [dendrogramError, setDendrogramError] = useState<string | null>(null);
  const [isDendrogramOpen, setIsDendrogramOpen] = useState<boolean>(true);
  const [hoveredClusterId, setHoveredClusterId] = useState<string | null>(null);
  const [overviewSplitRatio, setOverviewSplitRatio] = useState(42);
  const [isResizingOverviewSplit, setIsResizingOverviewSplit] = useState(false);
  const mergeCounterRef = useRef(1);
  const prevParamsKeyRef = useRef(`${activeParams.pValue}|${activeParams.foldChange}|${activeParams.ptree}`);
  const overviewSplitContainerRef = useRef<HTMLDivElement | null>(null);
  const overviewSplitDragRef = useRef<{ startY: number; startRatio: number } | null>(null);

  const [showIndividualGenes, setShowIndividualGenes] = useState(false);
  const [showMean, setShowMean] = useState(true);
  const [showMedian, setShowMedian] = useState(true);

  const clearMerges = useCallback((resetCounter: boolean) => {
    setMergeSpecs([]);
    setMergedPreviews({});
    if (resetCounter) {
      mergeCounterRef.current = 1;
    }
    setSelectedCluster((prev) => (isMergedClusterId(prev) ? null : prev));
  }, []);

  useEffect(() => {
    const currentKey = `${activeParams.pValue}|${activeParams.foldChange}|${activeParams.ptree}`;
    if (prevParamsKeyRef.current !== currentKey) {
      clearMerges(true);
      prevParamsKeyRef.current = currentKey;
    }
  }, [activeParams.pValue, activeParams.foldChange, activeParams.ptree, clearMerges]);

  useEffect(() => {
    loadExistingClusters(undefined, activeParams);
  }, [workbenchId, activeParams.pValue, activeParams.foldChange, activeParams.ptree]);

  const loadExistingClusters = async (search?: string, targetParams: ClusterParams = activeParams) => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await apiService.getTreeCuttingClusters(workbenchId, {
        p_value: targetParams.pValue,
        fold_change: targetParams.foldChange,
        ptree: targetParams.ptree,
        search,
        auto_run: true
      });

      if (response.exists) {
        setClusters(response.clusters);
        setIsSearchResult(response.is_search_result);
        setSearchQuery(response.search_query);

        if (response.clusters.length > 0) {
          if (!selectedCluster || (response.is_search_result && !isMergedClusterId(selectedCluster))) {
            setSelectedCluster(null);
          } else if (!isMergedClusterId(selectedCluster)) {
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
        clearMerges(true);
      }
    } catch (loadError: any) {
      console.error('Failed to load clusters:', loadError);
      setError(loadError.message || 'Failed to load clusters');
    } finally {
      setIsLoading(false);
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
        const clusterIds = clusters.map((cluster) => cluster.id);
        const response = await apiService.getTreeCuttingClusterPreviews(workbenchId, {
          p_value: activeParams.pValue,
          fold_change: activeParams.foldChange,
          ptree: activeParams.ptree,
          cluster_ids: clusterIds
        });

        const previewMap: Record<string, ClusterPreview> = {};
        (response.previews || []).forEach((preview) => {
          previewMap[preview.id] = preview;
        });
        setClusterPreviews(previewMap);
      } catch (previewError) {
        console.error('Failed to load cluster previews:', previewError);
        setClusterPreviews({});
      } finally {
        setIsPreviewLoading(false);
      }
    };

    loadClusterPreviews();
  }, [workbenchId, activeParams.pValue, activeParams.foldChange, activeParams.ptree, clusters]);

  useEffect(() => {
    const loadDendrogram = async () => {
      if (clusters.length === 0) {
        setDendrogramData(null);
        setDendrogramError(null);
        setIsDendrogramLoading(false);
        return;
      }

      setIsDendrogramLoading(true);
      setDendrogramError(null);
      try {
        const response = await apiService.getTreeCuttingDendrogram(workbenchId, {
          p_value: activeParams.pValue,
          fold_change: activeParams.foldChange,
          ptree: activeParams.ptree
        });
        setDendrogramData(response);
      } catch (dendroError: any) {
        console.error('Failed to load tree dendrogram:', dendroError);
        setDendrogramError(dendroError?.message || 'Failed to load dendrogram');
        setDendrogramData(null);
      } finally {
        setIsDendrogramLoading(false);
      }
    };

    loadDendrogram();
  }, [workbenchId, activeParams.pValue, activeParams.foldChange, activeParams.ptree, clusters.length]);

  const handleClusterSearch = (query: string) => {
    if (query.trim()) {
      if (!isMergedClusterId(selectedCluster)) {
        setSelectedCluster(null);
      }
      loadExistingClusters(query.trim(), activeParams);
    } else {
      loadExistingClusters(undefined, activeParams);
    }
  };

  const runClustering = async () => {
    const nextParams = {
      pValue: params.pValue,
      foldChange: params.foldChange,
      ptree: params.ptree
    };
    const nextKey = `${nextParams.pValue}|${nextParams.foldChange}|${nextParams.ptree}`;
    const activeKey = `${activeParams.pValue}|${activeParams.foldChange}|${activeParams.ptree}`;

    if (nextKey !== activeKey) {
      setActiveParams(nextParams);
      return;
    }

    setIsRunning(true);
    try {
      await loadExistingClusters(undefined, nextParams);
    } finally {
      setIsRunning(false);
    }
  };

  const displayClusters = useMemo<ClusterOverviewItem[]>(() => {
    const visibleBaseIds = new Set(clusters.map((cluster) => cluster.id));
    const hiddenBaseIds = new Set<string>();
    const hiddenMergedIds = new Set<string>();

    mergeSpecs.forEach((mergeSpec) => {
      (mergeSpec.source_item_ids || []).forEach((itemId) => {
        if (itemId.startsWith('merged_')) {
          hiddenMergedIds.add(itemId);
        }
      });
    });

    const mergedItems: ClusterOverviewItem[] = mergeSpecs
      .filter((mergeSpec) => !hiddenMergedIds.has(mergeSpec.id))
      .map((mergeSpec) => {
      const matchedSourceIds = mergeSpec.source_cluster_ids.filter((id) => visibleBaseIds.has(id));
      if (matchedSourceIds.length > 0) {
        matchedSourceIds.forEach((id) => hiddenBaseIds.add(id));
      }
      const preview = mergedPreviews[mergeSpec.id];
      return {
        id: mergeSpec.id,
        file_name: `${mergeSpec.id}.matrix`,
        gene_count: preview?.gene_count ?? 0,
        is_merged: true,
        source_cluster_ids: mergeSpec.source_cluster_ids,
        matched_source_ids: matchedSourceIds
      };
    });

    const baseItems = clusters.filter((cluster) => !hiddenBaseIds.has(cluster.id));
    return [...mergedItems, ...baseItems];
  }, [clusters, mergeSpecs, mergedPreviews]);

  const sidebarClusters = useMemo<ClusterSidebarItem[]>(
    () => displayClusters.map((cluster) => ({ ...cluster })),
    [displayClusters]
  );

  const mergedClusterMap = useMemo(() => {
    const map: Record<string, TreeMergeSpec> = {};
    mergeSpecs.forEach((spec) => { map[spec.id] = spec; });
    return map;
  }, [mergeSpecs]);

  const allPreviews = useMemo(
    () => ({ ...clusterPreviews, ...mergedPreviews }),
    [clusterPreviews, mergedPreviews]
  );

  useEffect(() => {
    if (!selectedCluster) return;
    const exists = displayClusters.some((cluster) => cluster.id === selectedCluster);
    if (!exists) {
      setSelectedCluster(null);
    }
  }, [displayClusters, selectedCluster]);

  useEffect(() => {
    if (selectedCluster !== null) {
      setHoveredClusterId(null);
    }
  }, [selectedCluster]);

  useEffect(() => {
    if (!isResizingOverviewSplit) {
      overviewSplitDragRef.current = null;
      document.body.style.removeProperty('cursor');
      document.body.style.removeProperty('user-select');
      return;
    }

    const handlePointerMove = (event: MouseEvent) => {
      if (!overviewSplitDragRef.current) return;

      const deltaY = event.clientY - overviewSplitDragRef.current.startY;
      const ratioDelta = (deltaY / 980) * 100;
      const nextRatio = overviewSplitDragRef.current.startRatio + ratioDelta;
      const clamped = Math.min(70, Math.max(28, nextRatio));
      setOverviewSplitRatio(clamped);
    };

    const handlePointerUp = () => setIsResizingOverviewSplit(false);

    document.body.style.cursor = 'row-resize';
    document.body.style.userSelect = 'none';
    window.addEventListener('mousemove', handlePointerMove);
    window.addEventListener('mouseup', handlePointerUp);

    return () => {
      document.body.style.removeProperty('cursor');
      document.body.style.removeProperty('user-select');
      window.removeEventListener('mousemove', handlePointerMove);
      window.removeEventListener('mouseup', handlePointerUp);
    };
  }, [isResizingOverviewSplit]);

  const handleApplyDendrogramPtree = useCallback((nextPtree: number) => {
    const clamped = Math.max(1, Math.min(100, Math.round(nextPtree)));
    const nextParams = { ...params, ptree: clamped };
    const nextKey = `${nextParams.pValue}|${nextParams.foldChange}|${nextParams.ptree}`;
    const activeKey = `${activeParams.pValue}|${activeParams.foldChange}|${activeParams.ptree}`;
    if (nextKey === activeKey) return;
    setSelectedCluster(null);
    setParams(nextParams);
    setActiveParams(nextParams);
  }, [params, activeParams]);

  const handleCreateMerge = async (clusterIds: string[]) => {
    const selectedItemIds = sortClusterIds([...new Set(clusterIds)]);
    if (selectedItemIds.length < 2) return null;

    const expandedBaseIds = new Set<string>();
    selectedItemIds.forEach((itemId) => {
      const source = mergedClusterMap[itemId];
      if (source) {
        source.source_cluster_ids.forEach((id) => expandedBaseIds.add(id));
      } else {
        expandedBaseIds.add(itemId);
      }
    });
    const normalized = sortClusterIds([...expandedBaseIds]);
    if (normalized.length < 2) return null;

    const existing = mergeSpecs.find((spec) =>
      spec.source_cluster_ids.length === normalized.length &&
      spec.source_cluster_ids.every((id, index) => id === normalized[index])
    );
    if (existing) {
      return { mergedId: existing.id };
    }

    const mergedId = `merged_${mergeCounterRef.current++}`;
    const response = await apiService.getTreeCuttingMergedPreview(workbenchId, {
      p_value: activeParams.pValue,
      fold_change: activeParams.foldChange,
      ptree: activeParams.ptree,
      merged_id: mergedId,
      cluster_ids: normalized
    });

    if (!response.preview) {
      throw new Error('Failed to generate merged preview');
    }

    setMergeSpecs((prev) => [...prev, {
      id: mergedId,
      source_cluster_ids: normalized,
      source_item_ids: selectedItemIds,
      created_at: Date.now()
    }]);
    setMergedPreviews((prev) => ({
      ...prev,
      [mergedId]: {
        id: response.preview.id,
        gene_count: response.preview.gene_count,
        samples: response.preview.samples,
        statistics: response.preview.statistics
      }
    }));

    return { mergedId };
  };

  const handleUnmerge = (mergedId: string) => {
    setMergeSpecs((prev) => prev.filter((spec) => spec.id !== mergedId));
    setMergedPreviews((prev) => {
      const next = { ...prev };
      delete next[mergedId];
      return next;
    });
    if (selectedCluster === mergedId) {
      setSelectedCluster(null);
    }
  };

  const selectedMergeSpec = selectedCluster ? mergedClusterMap[selectedCluster] : undefined;
  const overviewSectionBaseHeight = 980;
  const dendrogramSectionHeight = Math.round((overviewSplitRatio / 100) * overviewSectionBaseHeight);
  const overviewSectionHeight = Math.max(320, overviewSectionBaseHeight - dendrogramSectionHeight);
  const dendrogramPlotHeight = Math.max(220, dendrogramSectionHeight - 150);

  return (
    <div className="space-y-4">
      {(isLoading || isRunning) && (
        <div className="fixed inset-0 bg-black bg-opacity-30 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-8 flex flex-col items-center gap-4 shadow-xl">
            <div className="animate-spin w-12 h-12 border-4 border-blue-500 border-t-transparent rounded-full"></div>
            <p className="text-lg font-medium text-gray-800">
              {isRunning ? 'Running Tree Clustering...' : 'Loading clusters...'}
            </p>
            <p className="text-sm text-gray-600">
              {isRunning ? 'This may take a few minutes depending on dataset size' : 'Please wait...'}
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
          <TreeClusteringParameterPanel
            params={params}
            onChange={setParams}
            onRun={runClustering}
            isRunning={isRunning}
            isCollapsed={isParamsPanelCollapsed}
            onToggleCollapse={() => setIsParamsPanelCollapsed(!isParamsPanelCollapsed)}
          />
        </div>

        <div className="flex-shrink-0 w-64">
          <ClusterSidebar
            clusters={clusters}
            displayClusters={sidebarClusters}
            selectedCluster={selectedCluster}
            onSelectCluster={setSelectedCluster}
            onSelectOverview={() => setSelectedCluster(null)}
            onSearch={handleClusterSearch}
            isSearchResult={isSearchResult}
            searchQuery={searchQuery}
            previewsByCluster={allPreviews}
          />
        </div>

        <div className="flex-1 min-w-0">
          {selectedCluster !== null ? (
            selectedMergeSpec ? (
              <MergedClusterDetail
                workbenchId={workbenchId}
                mergedClusterId={selectedCluster}
                sourceClusterIds={selectedMergeSpec.source_cluster_ids}
                sourcePreviews={clusterPreviews}
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
                onOpenSourceCluster={setSelectedCluster}
              />
            ) : (
              <ClusterDetail
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
            )
          ) : displayClusters.length > 0 ? (
            <div ref={overviewSplitContainerRef} className="flex flex-col min-h-[980px]">
              <div style={{ height: isDendrogramOpen ? `${dendrogramSectionHeight}px` : undefined }}>
                <TreeClusterDendrogramPanel
                  data={dendrogramData}
                  isLoading={isDendrogramLoading}
                  error={dendrogramError}
                  isOpen={isDendrogramOpen}
                  onToggleOpen={() => setIsDendrogramOpen((prev) => !prev)}
                  currentPtree={activeParams.ptree}
                  onApplyPtree={handleApplyDendrogramPtree}
                  highlightedClusterId={hoveredClusterId}
                  onHoverCluster={setHoveredClusterId}
                  onSelectCluster={setSelectedCluster}
                  plotHeight={dendrogramPlotHeight}
                />
              </div>
              <div
                role="separator"
                aria-orientation="horizontal"
                aria-label="Resize dendrogram and cluster overview"
                onMouseDown={(event) => {
                  overviewSplitDragRef.current = {
                    startY: event.clientY,
                    startRatio: overviewSplitRatio
                  };
                  setIsResizingOverviewSplit(true);
                }}
                className={`relative my-3 hidden h-5 flex-shrink-0 cursor-row-resize items-center justify-center xl:flex ${
                  isResizingOverviewSplit ? 'bg-indigo-50' : ''
                }`}
              >
                <div className="absolute inset-x-0 h-px bg-slate-200 transition-colors hover:bg-indigo-300" />
                <div className="absolute inset-x-0 flex items-center justify-center">
                  <div className="flex h-2 w-10 items-center justify-center gap-1 rounded-full border border-slate-200 bg-white shadow-sm">
                    <span className="h-1 w-1 rounded-full bg-slate-400" />
                    <span className="h-1 w-1 rounded-full bg-slate-400" />
                    <span className="h-1 w-1 rounded-full bg-slate-400" />
                  </div>
                </div>
              </div>
              <div style={isDendrogramOpen ? { minHeight: `${overviewSectionHeight}px` } : undefined}>
                <ClusterOverviewGrid
                  clusters={displayClusters}
                  previewsByCluster={allPreviews}
                  onSelectCluster={setSelectedCluster}
                  onCreateMerge={handleCreateMerge}
                  onUnmerge={handleUnmerge}
                  onResetMerges={() => clearMerges(false)}
                  highlightedClusterId={hoveredClusterId}
                  onHoverCluster={setHoveredClusterId}
                />
              </div>
            </div>
          ) : (
            <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-12 text-center">
              <svg className="w-16 h-16 mx-auto text-gray-400 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
              </svg>
              <h3 className="text-lg font-medium text-gray-900 mb-2">No Cluster Selected</h3>
              <p className="text-gray-500">
                {clusters.length === 0
                  ? 'Run hierarchical tree clustering to detect expression patterns'
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
