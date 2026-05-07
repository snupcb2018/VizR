import React, { useState, useEffect } from 'react';
import { ClusterParams, ClusterData } from '../types';
import { apiService } from '../services/api';
import { ClusterPatternChart } from './ClusterPatternChart';
import { ClusterGeneTable } from './ClusterGeneTable';
import { VennSetSummary } from './VennSetMenu';

interface ClusterDetailProps {
  workbenchId: number;
  clusterId: string;
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
}

export function ClusterDetail({
  workbenchId,
  clusterId,
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
  vennSetSummaries
}: ClusterDetailProps) {
  const [data, setData] = useState<ClusterData | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // 클러스터 변경 시 선택된 유전자 리셋
    onSelectionChange(new Set());
    loadClusterData();
  }, [clusterId, params]);

  const loadClusterData = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await apiService.getTreeCuttingClusterData(workbenchId, clusterId, {
        p_value: params.pValue,
        fold_change: params.foldChange,
        ptree: params.ptree
      });
      setData(response);
    } catch (error: any) {
      console.error('Failed to load cluster data:', error);
      setError(error.message || 'Failed to load cluster data');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="space-y-4 relative">
      {/* 인라인 로딩 오버레이 */}
      {isLoading && (
        <div className="absolute inset-0 bg-white bg-opacity-75 flex items-center justify-center z-50 rounded-lg">
          <div className="flex flex-col items-center gap-2">
            <div className="animate-spin w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full"></div>
            <p className="text-sm text-gray-600">Loading cluster data...</p>
          </div>
        </div>
      )}

      {/* 에러 메시지 */}
      {error && !isLoading && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded">
          {error}
        </div>
      )}

      {/* 콘텐츠 (로딩 중에도 표시하여 레이아웃 유지) */}
      {data && (
        <>
          {/* 패턴 그래프 */}
          <ClusterPatternChart
            data={data}
            clusterId={clusterId}
            params={params}
            showIndividualGenes={showIndividualGenes}
            setShowIndividualGenes={setShowIndividualGenes}
            showMean={showMean}
            setShowMean={setShowMean}
            showMedian={showMedian}
            setShowMedian={setShowMedian}
          />

          {/* 유전자 테이블 */}
          <ClusterGeneTable
            genes={data.genes}
            samples={data.samples}
            clusterId={clusterId}
            workbenchId={workbenchId}
            params={params}
            selectedGenes={selectedGenes}
            onSelectionChange={onSelectionChange}
            onNavigateToVennDiagram={onNavigateToVennDiagram}
            vennSetSummaries={vennSetSummaries}
          />
        </>
      )}

      {/* 초기 로딩 시 (데이터 없음) */}
      {!data && !isLoading && !error && (
        <div className="flex items-center justify-center py-12">
          <p className="text-gray-500">No data available</p>
        </div>
      )}
    </div>
  );
}
