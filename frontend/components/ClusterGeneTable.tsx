import React, { useState, useMemo, useRef, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { ClusterGene, ClusterParams } from '../types';
import { apiService } from '../services/api';
import MiniHeatmap from './MiniHeatmap';
import GOAnalysisModal from './GOAnalysisModal';
import HeatmapAnalysisModal from './HeatmapAnalysisModal';
import KEGGPathwayModal from './KEGGPathwayModal';
import SelectableGeneTableShell from './SelectableGeneTableShell';
import VennSetMenu, { VennSetSummary } from './VennSetMenu';
import { useGeneAnalysisActions } from '../hooks/useGeneAnalysisActions';
import { useOverlayStickyTable } from '../hooks/useOverlayStickyTable';

interface ClusterGeneTableProps {
  genes: ClusterGene[];
  samples: string[];
  clusterId: string;
  workbenchId: number;
  params: ClusterParams;
  mergedSourceClusterIds?: string[];
  selectedGenes: Set<string>;
  onSelectionChange: (genes: Set<string>) => void;
  onNavigateToVennDiagram: (genes: string[], targetSetIndex?: number) => void;
  vennSetSummaries?: VennSetSummary[];
}

interface ClusterDataResponse {
  cluster_id: string;
  total_genes: number;
  showing_genes: number;
  current_page: number;
  total_pages: number;
  page_size: number;
  genes: ClusterGene[];
  samples: string[];
  statistics: any;
  is_search_result: boolean;
  search_query: string;
}

export function ClusterGeneTable({
  genes: initialGenes,
  samples: initialSamples,
  clusterId,
  workbenchId,
  params,
  mergedSourceClusterIds,
  selectedGenes,
  onSelectionChange,
  onNavigateToVennDiagram,
  vennSetSummaries
}: ClusterGeneTableProps) {
  const searchInputRef = useRef<HTMLTextAreaElement>(null);
  const [activeSearch, setActiveSearch] = useState('');
  const [sortColumn, setSortColumn] = useState<string>('gene_id');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('asc');
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(500);

  // 백엔드에서 가져온 데이터 상태
  const [clusterData, setClusterData] = useState<ClusterDataResponse | null>(null);
  const [loading, setLoading] = useState(false);

  // Analysis-related states
  const {
    isGOModalOpen: analysisGOModalOpen,
    goAnalysisResult: analysisGOResult,
    isGOLoading: analysisGOLoading,
    closeGOModal: closeAnalysisGO,
    runGOAnalysis,
    isHeatmapModalOpen: analysisHeatmapOpen,
    openHeatmap,
    closeHeatmap: closeAnalysisHeatmap,
    isKEGGModalOpen: analysisKEGGOpen,
    openKEGG,
    closeKEGG: closeAnalysisKEGG,
  } = useGeneAnalysisActions({
    workbenchId,
    selectedGenes: Array.from(selectedGenes),
    description: `Selected genes from ${clusterId}`,
  });
  const [selectAllState, setSelectAllState] = useState<0 | 1 | 2>(0);
  const isMergedCluster = clusterId.startsWith('merged_') && Array.isArray(mergedSourceClusterIds) && mergedSourceClusterIds.length > 1;

  // Fetch cluster data from backend
  const fetchClusterData = async (page: number, search: string, limit: number) => {
    setLoading(true);
    try {
      const response = isMergedCluster
        ? await apiService.getTreeCuttingMergedClusterData(workbenchId, {
            p_value: params.pValue,
            fold_change: params.foldChange,
            ptree: params.ptree,
            merged_id: clusterId,
            cluster_ids: mergedSourceClusterIds || [],
            search,
            page,
            limit
          })
        : await apiService.getTreeCuttingClusterData(workbenchId, clusterId, {
            p_value: params.pValue,
            fold_change: params.foldChange,
            ptree: params.ptree,
            search,
            page,
            limit
          });
      setClusterData(response);
    } catch (error) {
      console.error('❌ [TREE] Failed to fetch cluster data:', error);
    } finally {
      setLoading(false);
    }
  };

  // Initial load and reload when clusterId or params change
  useEffect(() => {
    setCurrentPage(1);
    setActiveSearch('');
    onSelectionChange(new Set());
    setSelectAllState(0);
    if (searchInputRef.current) {
      searchInputRef.current.value = '';
    }
    fetchClusterData(1, '', pageSize);
  }, [clusterId, params]);

  // Use backend data or fallback to props
  const genes = clusterData?.genes || initialGenes;
  const samples = clusterData?.samples || initialSamples;
  const totalPages = clusterData?.total_pages || 1;
  const totalGenes = clusterData?.total_genes || genes.length;
  const tableColumnWidths = {
    select: 48,
    geneId: 150,
    geneSymbol: 120,
    pattern: 240,
    sample: 96
  } as const;
  const tableStickyOffsets = {
    geneId: tableColumnWidths.select,
    geneSymbol: tableColumnWidths.select + tableColumnWidths.geneId,
    pattern: tableColumnWidths.select + tableColumnWidths.geneId + tableColumnWidths.geneSymbol
  } as const;
  const fixedHeaderWidth =
    tableColumnWidths.select +
    tableColumnWidths.geneId +
    tableColumnWidths.geneSymbol +
    tableColumnWidths.pattern;
  const {
    showScrollToTopButton,
    overlayHeader,
    topScrollbarWidth,
    handleScrollToTop,
    refs: {
      tableSectionRef,
      topScrollbarRef,
      floatingTopScrollbarRef,
      tableWrapperRef,
      tableRef,
      tableTheadRef,
    },
  } = useOverlayStickyTable({
    enabled: genes.length > 0,
    dependencyKey: [clusterId, currentPage, pageSize, genes.length, samples.length, activeSearch, loading ? 'loading' : 'idle'].join('|')
  });
  const tableColGroup = (
    <colgroup>
      <col style={{ width: `${tableColumnWidths.select}px` }} />
      <col style={{ width: `${tableColumnWidths.geneId}px` }} />
      <col style={{ width: `${tableColumnWidths.geneSymbol}px` }} />
      <col style={{ width: `${tableColumnWidths.pattern}px` }} />
      {samples.map(sample => (
        <col key={sample} style={{ width: `${tableColumnWidths.sample}px` }} />
      ))}
    </colgroup>
  );

  const handleSearch = () => {
    const searchValue = searchInputRef.current?.value.trim() || '';
    if (searchValue) {
      setActiveSearch(searchValue);
      setCurrentPage(1);
      onSelectionChange(new Set());
      setSelectAllState(0);
      fetchClusterData(1, searchValue, pageSize);
    }
  };

  const handleClearSearch = () => {
    if (searchInputRef.current) {
      searchInputRef.current.value = '';
    }
    setActiveSearch('');
    setCurrentPage(1);
    onSelectionChange(new Set());
    setSelectAllState(0);
    fetchClusterData(1, '', pageSize);
  };

  const handleSort = (column: string) => {
    if (sortColumn === column) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortColumn(column);
      setSortDirection('asc');
    }
  };

  const handleDownload = () => {
    // 선택된 유전자가 있으면 선택된 것만, 없으면 현재 페이지 전체 유전자
    const dataToDownload = selectedGenes.size > 0
      ? genes.filter(gene => selectedGenes.has(gene.gene_id))
      : genes;

    if (dataToDownload.length === 0) {
      alert('No data to download');
      return;
    }

    // TSV 형식으로 데이터 생성
    const headers = ['GeneID', 'GeneSymbol', ...samples];
    const rows = [headers.join('\t')];

    dataToDownload.forEach(gene => {
      const row = [
        gene.gene_id,
        gene.gene_symbol,
        ...samples.map(sample => {
          const value = gene[sample];
          return typeof value === 'number' ? value.toFixed(2) : value;
        })
      ];
      rows.push(row.join('\t'));
    });

    const tsvContent = rows.join('\n');
    const blob = new Blob([tsvContent], { type: 'text/tab-separated-values;charset=utf-8;' });
    const url = URL.createObjectURL(blob);

    // 파일명 생성
    const timestamp = new Date().toISOString().slice(0, 10);
    const selectionType = selectedGenes.size > 0 ? `selected_${selectedGenes.size}` : 'all';
    const filename = `${clusterId}_genes_${selectionType}_${timestamp}.tsv`;

    // 다운로드 트리거
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    link.click();

    URL.revokeObjectURL(url);
  };

  // Pagination handlers
  const handlePageChange = (newPage: number) => {
    setCurrentPage(newPage);
    onSelectionChange(new Set());
    setSelectAllState(0);
    fetchClusterData(newPage, activeSearch, pageSize);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handlePageSizeChange = (newSize: number) => {
    setPageSize(newSize);
    setCurrentPage(1);
    onSelectionChange(new Set());
    setSelectAllState(0);
    fetchClusterData(1, activeSearch, newSize);
  };

  // Handle gene selection
  const fetchAllGeneIds = useCallback(async (): Promise<string[]> => {
    try {
      const response = isMergedCluster
        ? await apiService.getTreeCuttingMergedClusterData(workbenchId, {
            p_value: params.pValue,
            fold_change: params.foldChange,
            ptree: params.ptree,
            merged_id: clusterId,
            cluster_ids: mergedSourceClusterIds || [],
            search: activeSearch,
            page: 1,
            limit: totalGenes
          })
        : await apiService.getTreeCuttingClusterData(workbenchId, clusterId, {
            p_value: params.pValue,
            fold_change: params.foldChange,
            ptree: params.ptree,
            search: activeSearch,
            page: 1,
            limit: totalGenes
          });
      return (response.genes || []).map((g: ClusterGene) => g.gene_id);
    } catch (error) {
      console.error('Failed to fetch all gene IDs:', error);
      return [];
    }
  }, [workbenchId, clusterId, params.pValue, params.foldChange, params.ptree, activeSearch, totalGenes, isMergedCluster, mergedSourceClusterIds]);

  const handleSelectAllCycle = useCallback(async () => {
    if (selectAllState === 0) {
      const newSelected = new Set(selectedGenes);
      genes.forEach(gene => newSelected.add(gene.gene_id));
      onSelectionChange(newSelected);
      setSelectAllState(1);
    } else if (selectAllState === 1) {
      const allIds = await fetchAllGeneIds();
      onSelectionChange(new Set<string>(allIds));
      setSelectAllState(2);
    } else {
      onSelectionChange(new Set());
      setSelectAllState(0);
    }
  }, [selectAllState, genes, selectedGenes, onSelectionChange, fetchAllGeneIds]);

  const handleSelectOne = (geneId: string) => {
    const newSelectedGenes = new Set(selectedGenes);
    if (newSelectedGenes.has(geneId)) {
      newSelectedGenes.delete(geneId);
    } else {
      newSelectedGenes.add(geneId);
    }
    onSelectionChange(newSelectedGenes);
    setSelectAllState(0);
  };

  const tableHeaderRow = (
    <tr>
      <th
        className="px-4 py-3 text-left text-xs font-medium text-gray-700 uppercase tracking-wider w-12"
        style={{ width: `${tableColumnWidths.select}px`, backgroundColor: 'rgb(249 250 251)', position: 'sticky', left: 0, zIndex: 20 }}
      >
        <button
          onClick={handleSelectAllCycle}
          className="flex items-center justify-center w-5 h-5 hover:opacity-75 transition-opacity"
          title={selectAllState === 0 ? 'Select current page' : selectAllState === 1 ? 'Select all pages' : 'Deselect all'}
        >
          <svg viewBox="0 0 16 16" className="w-4 h-4" fill="none" xmlns="http://www.w3.org/2000/svg">
            {selectAllState === 0 && (<rect x="1" y="1" width="14" height="14" rx="2" stroke="#9CA3AF" strokeWidth="1.5"/>)}
            {selectAllState === 1 && (<><rect x="1" y="1" width="14" height="14" rx="2" stroke="#3B82F6" strokeWidth="1.5"/><path d="M4 8.5l2.5 2.5 5-5.5" stroke="#3B82F6" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></>)}
            {selectAllState === 2 && (<><rect x="1" y="1" width="14" height="14" rx="2" fill="#1D4ED8" stroke="#1D4ED8" strokeWidth="1.5"/><path d="M4 8.5l2.5 2.5 5-5.5" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></>)}
          </svg>
        </button>
      </th>
      <th
        onClick={() => handleSort('gene_id')}
        className="px-4 py-3 text-left text-xs font-medium text-gray-700 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
        style={{ width: `${tableColumnWidths.geneId}px`, minWidth: `${tableColumnWidths.geneId}px`, backgroundColor: 'rgb(249 250 251)', position: 'sticky', left: `${tableStickyOffsets.geneId}px`, zIndex: 20 }}
      >
        <div className="flex items-center gap-1">Gene ID{sortColumn === 'gene_id' && <span>{sortDirection === 'asc' ? '↑' : '↓'}</span>}</div>
      </th>
      <th
        onClick={() => handleSort('gene_symbol')}
        className="px-4 py-3 text-left text-xs font-medium text-gray-700 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
        style={{ width: `${tableColumnWidths.geneSymbol}px`, minWidth: `${tableColumnWidths.geneSymbol}px`, backgroundColor: 'rgb(249 250 251)', position: 'sticky', left: `${tableStickyOffsets.geneSymbol}px`, zIndex: 20 }}
      >
        <div className="flex items-center gap-1">Gene Symbol{sortColumn === 'gene_symbol' && <span>{sortDirection === 'asc' ? '↑' : '↓'}</span>}</div>
      </th>
      <th
        className="px-4 py-3 text-center text-xs font-medium text-gray-700 uppercase tracking-wider"
        style={{ width: `${tableColumnWidths.pattern}px`, minWidth: `${tableColumnWidths.pattern}px`, backgroundColor: 'rgb(249 250 251)', position: 'sticky', left: `${tableStickyOffsets.pattern}px`, zIndex: 20 }}
      >
        Expression Pattern
      </th>
      {samples.map(sample => (
        <th
          key={sample}
          onClick={() => handleSort(sample)}
          className="px-4 py-3 text-left text-xs font-medium text-gray-700 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
          style={{ width: `${tableColumnWidths.sample}px`, minWidth: `${tableColumnWidths.sample}px`, backgroundColor: 'rgb(249 250 251)' }}
        >
          <div className="flex items-center gap-1">{sample}{sortColumn === sample && <span>{sortDirection === 'asc' ? '↑' : '↓'}</span>}</div>
        </th>
      ))}
    </tr>
  );

  // Handle GO Analysis
  const handleGOAnalysis = async (provider: 'david' | 'gprofiler') => {
    const genes = Array.from(selectedGenes);
    setGOLoading(true);
    setGOModalOpen(true);

    try {
      const result = await apiService.runGOEnrichment(workbenchId, {
        genes: genes,
        databases: ['GO_BP', 'GO_MF', 'GO_CC'],
        p_value_cutoff: 0.05,
        description: `Selected genes from ${clusterId}`,
        organism: 'arabidopsis',
        provider
      });
      setGOAnalysisResult(result);
    } catch (error) {
      console.error('❌ [GO-ANALYSIS] Failed:', error);
    } finally {
      setGOLoading(false);
    }
  };

  return (
    <div ref={tableSectionRef} className="bg-white rounded-lg border border-gray-200 shadow-sm relative">
      <div className="p-4 border-b border-gray-200">
        <div className="mb-4">
          <h3 className="text-lg font-semibold text-gray-800">
            {isMergedCluster ? `Genes in ${clusterId.replace('merged_', 'Merged ')}` : `Genes in ${clusterId.replace('subcluster_', 'Cluster ')}`}
          </h3>
          <p className="text-sm text-gray-600 mt-1">
            {genes.length.toLocaleString()} genes · log2(median-centered FPKM)
          </p>
        </div>

        {/* Search, Action Buttons, and Pagination */}
        <div className="flex items-center justify-between gap-4">
          {/* Left side: Search and Action Buttons */}
          <div className="flex flex-wrap items-center gap-4">
            <div className="relative">
              <textarea
                ref={searchInputRef}
                placeholder="Search Gene IDs or Symbols (comma, space, tab, or newline separated)..."
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && e.ctrlKey) {
                    handleSearch();
                  }
                }}
                className="pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 w-64 min-h-[40px] max-h-[200px] resize-vertical"
                rows={1}
              />
              <div className="absolute top-2.5 left-0 pl-3 flex items-center pointer-events-none">
                <svg className="h-5 w-5 text-gray-400" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
              </div>
            </div>
            <button
              onClick={handleSearch}
              className="px-4 py-2 h-10 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed font-medium text-sm whitespace-nowrap"
            >
              Search
            </button>
            {activeSearch && (
              <button
                onClick={handleClearSearch}
                className="px-4 py-2 h-10 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 font-medium text-sm whitespace-nowrap"
              >
                Clear
              </button>
            )}
            <SelectableGeneTableShell
              selectedGenes={Array.from(selectedGenes)}
              onHeatmap={openHeatmap}
              onGOAnalysis={(provider) => { void runGOAnalysis(provider); }}
              onKEGG={openKEGG}
              vennMenu={(
                <VennSetMenu
                  summaries={vennSetSummaries}
                  onSelectSet={(targetSetIndex) => {
                    onNavigateToVennDiagram(Array.from(selectedGenes), targetSetIndex);
                  }}
                />
              )}
              afterAnalyzeControls={(
                <button
                  onClick={handleDownload}
                  className="px-4 py-2 h-10 border border-gray-300 rounded-lg hover:bg-gray-50 flex items-center gap-2 font-medium text-sm whitespace-nowrap"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
                    />
                  </svg>
                  Download TSV {selectedGenes.size > 0 ? `(${selectedGenes.size})` : ''}
                </button>
              )}
              analyzeButtonClassName="px-4 py-2 h-10 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed flex items-center gap-1 font-medium text-sm whitespace-nowrap"
              toolbarClassName="contents"
              leftGroupClassName="contents"
              rightGroupClassName="contents"
            />
          </div>

          {/* Right side: Pagination */}
          {totalPages > 0 && (
            <div className="flex items-center space-x-2">
              <span className="text-sm text-gray-600">
                {(currentPage - 1) * pageSize + 1}-{Math.min(currentPage * pageSize, totalGenes)} of {totalGenes.toLocaleString()}
              </span>
              <select
                value={pageSize}
                onChange={(e) => handlePageSizeChange(Number(e.target.value))}
                className="text-sm border border-gray-300 rounded px-2 py-1 focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
              >
                <option value={50}>50</option>
                <option value={100}>100</option>
                <option value={500}>500</option>
                <option value={1000}>1000</option>
                <option value={2000}>2000</option>
              </select>
              <button
                onClick={() => handlePageChange(Math.max(1, currentPage - 1))}
                disabled={currentPage === 1}
                className="px-3 py-1 rounded border border-gray-300 text-sm disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-50"
              >
                Previous
              </button>
              {(() => {
                const getPageNumbers = () => {
                  const pages: (number | string)[] = [];
                  const showEllipsis = totalPages > 7;

                  if (!showEllipsis) {
                    for (let i = 1; i <= totalPages; i++) {
                      pages.push(i);
                    }
                  } else {
                    if (currentPage <= 4) {
                      for (let i = 1; i <= 5; i++) pages.push(i);
                      pages.push('...');
                      pages.push(totalPages);
                    } else if (currentPage >= totalPages - 3) {
                      pages.push(1);
                      pages.push('...');
                      for (let i = totalPages - 4; i <= totalPages; i++) pages.push(i);
                    } else {
                      pages.push(1);
                      pages.push('...');
                      pages.push(currentPage - 1);
                      pages.push(currentPage);
                      pages.push(currentPage + 1);
                      pages.push('...');
                      pages.push(totalPages);
                    }
                  }

                  return pages;
                };

                return getPageNumbers().map((page, idx) =>
                  typeof page === 'number' ? (
                    <button
                      key={idx}
                      onClick={() => handlePageChange(page)}
                      className={`px-3 py-1 rounded text-sm transition-colors ${
                        page === currentPage
                          ? 'bg-blue-600 text-white border border-blue-600'
                          : 'border border-gray-300 hover:bg-gray-50'
                      }`}
                    >
                      {page}
                    </button>
                  ) : (
                    <span key={idx} className="px-2 text-gray-400">
                      {page}
                    </span>
                  )
                );
              })()}
              <button
                onClick={() => handlePageChange(Math.min(totalPages, currentPage + 1))}
                disabled={currentPage === totalPages}
                className="px-3 py-1 rounded border border-gray-300 text-sm disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-50"
              >
                Next
              </button>
            </div>
          )}
        </div>
      </div>

      <div className="border-t border-gray-200 overflow-visible">
        <div ref={topScrollbarRef} className="overflow-x-auto overflow-y-hidden border-b border-gray-200 bg-gray-50">
          <div style={{ width: `${topScrollbarWidth}px`, height: '16px' }} />
        </div>
        <div ref={tableWrapperRef} className="relative" style={{ overflowX: 'auto', overflowY: 'visible' }}>
          <table ref={tableRef} className="min-w-full divide-y divide-gray-200" style={{ minWidth: '800px', tableLayout: 'fixed' }}>
            {tableColGroup}
            <thead ref={tableTheadRef} className="bg-gray-50">
              {tableHeaderRow}
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {genes.length > 0 ? (
                genes.map((gene, idx) => (
                  <tr key={idx} className="hover:bg-gray-50">
                    <td className="px-4 py-3" style={{ position: 'sticky', left: 0, zIndex: 20, backgroundColor: 'white' }}>
                      <input
                        type="checkbox"
                        className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                        checked={selectedGenes.has(gene.gene_id)}
                        onChange={() => handleSelectOne(gene.gene_id)}
                      />
                    </td>
                    <td
                      className="px-4 py-3 whitespace-nowrap text-sm font-mono text-gray-900 cursor-help"
                      style={{ position: 'sticky', left: `${tableStickyOffsets.geneId}px`, zIndex: 20, backgroundColor: 'white', minWidth: `${tableColumnWidths.geneId}px` }}
                      title={gene.gene_description || 'No description available'}
                    >
                      {gene.gene_id}
                    </td>
                    <td
                      className="px-4 py-3 whitespace-nowrap text-sm font-medium text-gray-900"
                      style={{ position: 'sticky', left: `${tableStickyOffsets.geneSymbol}px`, zIndex: 20, backgroundColor: 'white', minWidth: `${tableColumnWidths.geneSymbol}px` }}
                    >
                      {gene.gene_symbol}
                    </td>
                    <td
                      className="px-4 py-3"
                      style={{ position: 'sticky', left: `${tableStickyOffsets.pattern}px`, zIndex: 20, backgroundColor: 'white', minWidth: `${tableColumnWidths.pattern}px` }}
                    >
                      <MiniHeatmap
                        values={samples.map(sample => {
                          const value = gene[sample];
                          return typeof value === 'number' ? value : parseFloat(value as string) || 0;
                        })}
                        samples={samples}
                        width={Math.min(samples.length * 16, 240)}
                        height={20}
                      />
                    </td>
                    {samples.map((sample) => (
                      <td key={sample} className="px-4 py-3 whitespace-nowrap text-sm text-gray-700">
                        {typeof gene[sample] === 'number' ? gene[sample].toFixed(2) : gene[sample]}
                      </td>
                    ))}
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={samples.length + 4} className="px-4 py-8 text-center text-gray-500">
                    No results found
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>


      {overlayHeader.visible && typeof document !== 'undefined' && createPortal(
        <div className="fixed z-[120] pointer-events-none" style={{ top: overlayHeader.top, left: overlayHeader.left, width: overlayHeader.width }}>
          <div
            ref={floatingTopScrollbarRef}
            className="overflow-x-auto overflow-y-hidden bg-gray-50 border border-gray-200 border-b-0 rounded-t-lg pointer-events-auto"
            style={{ width: `${overlayHeader.width}px` }}
          >
            <div style={{ width: `${overlayHeader.tableWidth}px`, height: '16px' }} />
          </div>
          <div className="relative" style={{ width: `${overlayHeader.width}px`, height: `${overlayHeader.height || 57}px` }}>
            <div className="absolute top-0 left-0 overflow-hidden border-x border-b border-gray-200 bg-gray-50 shadow-sm" style={{ width: `${Math.min(fixedHeaderWidth, overlayHeader.width)}px` }}>
              <table className="min-w-full divide-y divide-gray-200" style={{ width: `${Math.min(fixedHeaderWidth, overlayHeader.width)}px`, tableLayout: 'fixed' }}>
                <colgroup>
                  <col style={{ width: `${tableColumnWidths.select}px` }} />
                  <col style={{ width: `${tableColumnWidths.geneId}px` }} />
                  <col style={{ width: `${tableColumnWidths.geneSymbol}px` }} />
                  <col style={{ width: `${tableColumnWidths.pattern}px` }} />
                </colgroup>
                <thead className="bg-gray-50">{tableHeaderRow}</thead>
              </table>
            </div>
            <div className="absolute top-0 overflow-hidden border-r border-b border-gray-200 bg-gray-50 shadow-sm" style={{ left: `${Math.min(fixedHeaderWidth, overlayHeader.width)}px`, width: `${Math.max(0, overlayHeader.width - Math.min(fixedHeaderWidth, overlayHeader.width))}px` }}>
              <div style={{ width: `${Math.max(0, overlayHeader.tableWidth - fixedHeaderWidth)}px`, transform: `translateX(-${overlayHeader.scrollLeft}px)` }}>
                <table className="min-w-full divide-y divide-gray-200" style={{ width: `${Math.max(0, overlayHeader.tableWidth - fixedHeaderWidth)}px`, tableLayout: 'fixed' }}>
                  <colgroup>
                    {samples.map(sample => <col key={sample} style={{ width: `${tableColumnWidths.sample}px` }} />)}
                  </colgroup>
                  <thead className="bg-gray-50">
                    <tr>
                      {samples.map(sample => (
                        <th key={sample} className="px-4 py-3 text-left text-xs font-medium text-gray-700 uppercase tracking-wider" style={{ width: `${tableColumnWidths.sample}px`, minWidth: `${tableColumnWidths.sample}px` }}>
                          <div className="flex items-center gap-1">{sample}{sortColumn === sample && <span>{sortDirection === 'asc' ? '↑' : '↓'}</span>}</div>
                        </th>
                      ))}
                    </tr>
                  </thead>
                </table>
              </div>
            </div>
          </div>
        </div>,
        document.body
      )}

      {showScrollToTopButton && typeof document !== 'undefined' && createPortal(
        <button
          type="button"
          onClick={handleScrollToTop}
          className="scroll-to-top-button fixed bottom-6 right-6 z-[120] rounded-full transition-transform hover:scale-105 w-12 h-12 flex items-center justify-center"
          aria-label="Scroll to top"
          title="Scroll to top"
        >
          <span className="scroll-to-top-icon" aria-hidden="true" />
        </button>,
        document.body
      )}

      {/* GO Analysis Modal */}
      <GOAnalysisModal
        isOpen={analysisGOModalOpen}
        onClose={closeAnalysisGO}
        result={analysisGOResult}
        isLoading={analysisGOLoading}
        workbenchId={workbenchId}
        comparisonName={clusterId}
        toolName="clustering"
      />

      {/* Heatmap Analysis Modal */}
      <HeatmapAnalysisModal
        isOpen={analysisHeatmapOpen}
        onClose={closeAnalysisHeatmap}
        workbenchId={workbenchId}
        selectedGenes={Array.from(selectedGenes)}
        comparisonName={clusterId}
        toolName="clustering"
      />

      {/* KEGG Pathway Modal */}
      <KEGGPathwayModal
        isOpen={analysisKEGGOpen}
        onClose={closeAnalysisKEGG}
        workbenchId={workbenchId}
        selectedGenes={Array.from(selectedGenes)}
        comparisonName={clusterId}
        toolName="clustering"
      />
    </div>
  );
}
