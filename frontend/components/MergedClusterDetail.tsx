import React, { useEffect, useState } from 'react';
import { ClusterData, ClusterParams, ClusterPreview } from '../types';
import { apiService } from '../services/api';
import { ClusterPatternChart } from './ClusterPatternChart';
import { ClusterGeneTable } from './ClusterGeneTable';
import { ClusterMiniPattern } from './ClusterMiniPattern';
import { VennSetSummary } from './VennSetMenu';

interface MergedClusterDetailProps {
  workbenchId: number;
  mergedClusterId: string;
  sourceClusterIds: string[];
  sourcePreviews: Record<string, ClusterPreview>;
  params: ClusterParams;
  selectedGenes: Set<string>;
  onSelectionChange: (genes: Set<string>) => void;
  showIndividualGenes: boolean;
  setShowIndividualGenes: (show: boolean) => void;
  showMean: boolean;
  setShowMean: (show: boolean) => void;
  showMedian: boolean;
  setShowMedian: (show: boolean) => void;
  onNavigateToVennDiagram: (genes: string[], targetSetIndex?: number) => void;
  vennSetSummaries?: VennSetSummary[];
  onOpenSourceCluster: (clusterId: string) => void;
}

export function MergedClusterDetail({
  workbenchId,
  mergedClusterId,
  sourceClusterIds,
  sourcePreviews,
  params,
  selectedGenes,
  onSelectionChange,
  showIndividualGenes,
  setShowIndividualGenes,
  showMean,
  setShowMean,
  showMedian,
  setShowMedian,
  onNavigateToVennDiagram,
  vennSetSummaries,
  onOpenSourceCluster
}: MergedClusterDetailProps) {
  const [data, setData] = useState<ClusterData | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    onSelectionChange(new Set());
    loadMergedData();
  }, [mergedClusterId, params.pValue, params.foldChange, params.ptree]);

  const loadMergedData = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await apiService.getTreeCuttingMergedClusterData(workbenchId, {
        p_value: params.pValue,
        fold_change: params.foldChange,
        ptree: params.ptree,
        merged_id: mergedClusterId,
        cluster_ids: sourceClusterIds
      });
      setData(response);
    } catch (loadError: any) {
      console.error('Failed to load merged cluster data:', loadError);
      setError(loadError.message || 'Failed to load merged cluster data');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="space-y-4 relative">
      {isLoading && (
        <div className="absolute inset-0 bg-white bg-opacity-75 flex items-center justify-center z-50 rounded-lg">
          <div className="flex flex-col items-center gap-2">
            <div className="animate-spin w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full"></div>
            <p className="text-sm text-gray-600">Loading merged cluster data...</p>
          </div>
        </div>
      )}

      {error && !isLoading && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded">
          {error}
        </div>
      )}

      {data && (
        <>
          <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-base font-semibold text-slate-800">
                Source Clusters ({sourceClusterIds.length})
              </h3>
              <span className="text-xs text-slate-500">
                Split comparison panel
              </span>
            </div>
            <div className="grid gap-2" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))' }}>
              {sourceClusterIds.map((clusterId) => {
                const preview = sourcePreviews[clusterId];
                return (
                  <button
                    key={clusterId}
                    onClick={() => onOpenSourceCluster(clusterId)}
                    className="border border-slate-200 rounded-md p-2 text-left hover:bg-slate-50 transition-colors"
                  >
                    <div className="text-xs font-medium text-slate-700 mb-1">
                      {clusterId.replace('subcluster_', 'Cluster ')}
                    </div>
                    {preview ? (
                      <ClusterMiniPattern
                        mean={preview.statistics.mean}
                        median={preview.statistics.median}
                        width={160}
                        height={42}
                      />
                    ) : (
                      <div className="h-[42px] rounded border border-slate-200 bg-slate-50" />
                    )}
                  </button>
                );
              })}
            </div>
          </div>

          <ClusterPatternChart
            data={data}
            clusterId={mergedClusterId}
            params={params}
            showIndividualGenes={showIndividualGenes}
            setShowIndividualGenes={setShowIndividualGenes}
            showMean={showMean}
            setShowMean={setShowMean}
            showMedian={showMedian}
            setShowMedian={setShowMedian}
          />

          <ClusterGeneTable
            genes={data.genes}
            samples={data.samples}
            clusterId={mergedClusterId}
            workbenchId={workbenchId}
            params={params}
            mergedSourceClusterIds={sourceClusterIds}
            selectedGenes={selectedGenes}
            onSelectionChange={onSelectionChange}
            onNavigateToVennDiagram={onNavigateToVennDiagram}
            vennSetSummaries={vennSetSummaries}
          />
        </>
      )}
    </div>
  );
}
