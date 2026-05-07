import React, { useState, useEffect } from 'react';
import { MfuzzParams, MfuzzClusterData } from '../types';
import { apiService } from '../services/api';
import { MfuzzClusterPatternChart } from './MfuzzClusterPatternChart';
import MfuzzClusterGeneTable from './MfuzzClusterGeneTable';
import { VennSetSummary } from './VennSetMenu';

interface MfuzzClusterDetailProps {
  workbenchId: number;
  clusterId: number;
  params: MfuzzParams;
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

export function MfuzzClusterDetail({
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
}: MfuzzClusterDetailProps) {
  const [data, setData] = useState<MfuzzClusterData | null>(null);
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
      const response = await apiService.getMfuzzClusterData(workbenchId, clusterId, {
        source_type: params.sourceType,
        p_value: params.sourceType === 'deg' ? params.pValue : undefined,
        fold_change: params.sourceType === 'deg' ? params.foldChange : undefined,
        top_n_genes: params.sourceType === 'variance' ? params.topNGenes : undefined,
        cluster_count: params.clusterCount,
        m_value: params.mValue,
        min_membership: params.minMembership
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
          <MfuzzClusterPatternChart
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
          <MfuzzClusterGeneTable
            genes={data.genes}
            samples={data.samples}
            clusterId={clusterId}
            workbenchId={workbenchId}
            selectedGenes={selectedGenes}
            onSelectionChange={onSelectionChange}
            params={params}
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
