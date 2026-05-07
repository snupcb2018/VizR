import React, { useState, useMemo, useCallback, useRef, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { WgcnaGene } from '../types';
import MiniHeatmap from './MiniHeatmap';
import GOAnalysisModal from './GOAnalysisModal';
import GOProviderSubmenu from './GOProviderSubmenu';
import CopyGeneListMenuItem from './CopyGeneListMenuItem';
import HeatmapAnalysisModal from './HeatmapAnalysisModal';
import KEGGPathwayModal from './KEGGPathwayModal';
import SelectableGeneTableShell from './SelectableGeneTableShell';
import VennSetMenu, { VennSetSummary } from './VennSetMenu';
import { apiService } from '../services/api';
import { useGeneAnalysisActions } from '../hooks/useGeneAnalysisActions';
import { useOverlayStickyTable } from '../hooks/useOverlayStickyTable';

// ========================================
// Type Definitions
// ========================================

interface WgcnaModuleGeneTableProps {
  genes: WgcnaGene[];
  samples: string[];
  moduleId: string;
  workbenchId: number;
  selectedGenes: Set<string>;
  onSelectionChange: (genes: Set<string>) => void;
  params: any;  // WGCNA 파라미터
  onNavigateToVennDiagram: (genes: string[], targetSetIndex?: number) => void;
  vennSetSummaries?: VennSetSummary[];
}

interface WgcnaModuleDataResponse {
  module_id: string;
  gene_count: number;
  total_genes: number;
  showing_genes: number;
  current_page: number;
  total_pages: number;
  page_size: number;
  genes: WgcnaGene[];
  samples: string[];
  eigengene_values: number[];
  is_search_result: boolean;
  search_query: string;
}

// ========================================
// Utility Hooks
// ========================================

const useTableHeight = () => {
  const [tableHeight, setTableHeight] = useState('60vh');

  useEffect(() => {
    const calculateHeight = () => {
      const viewportHeight = window.innerHeight;
      const headerHeight = 120;  // Page header
      const tabsHeight = 60;      // Tabs navigation
      const paddingHeight = 100;  // General padding
      const toolbarHeight = 120;  // Search bar and buttons
      const tableTitleHeight = 80; // Table title section
      const topPaginationHeight = 60; // Top pagination

      const availableHeight = viewportHeight - headerHeight - tabsHeight - paddingHeight - toolbarHeight - tableTitleHeight - topPaginationHeight;
      const minHeight = Math.max(300, availableHeight);
      const maxHeight = Math.min(viewportHeight * 0.7, minHeight);

      setTableHeight(`${maxHeight}px`);
    };

    calculateHeight();
    window.addEventListener('resize', calculateHeight);

    return () => window.removeEventListener('resize', calculateHeight);
  }, []);

  return tableHeight;
};

// ========================================
// Component Definitions
// ========================================

const Pagination: React.FC<{
  currentPage: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  pageSize: number;
  onPageSizeChange: (size: number) => void;
  totalCount: number;
}> = ({
  currentPage,
  totalPages,
  onPageChange,
  pageSize,
  onPageSizeChange,
  totalCount
}) => {
  const pageSizeOptions = [100, 500, 1000, 2000, 3000];

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

  const startItem = (currentPage - 1) * pageSize + 1;
  const endItem = Math.min(currentPage * pageSize, totalCount);

  return (
    <div className="flex items-center justify-between mt-4 px-4 py-3 bg-white border-t border-slate-200">
      <div className="flex items-center space-x-4">
        <div className="flex items-center space-x-2">
          <span className="text-sm text-slate-600">Rows per page:</span>
          <select
            value={pageSize}
            onChange={(e) => onPageSizeChange(Number(e.target.value))}
            className="text-sm border border-slate-300 rounded px-2 py-1 focus:ring-1 focus:ring-primary focus:border-primary"
          >
            {pageSizeOptions.map(size => (
              <option key={size} value={size}>{size}</option>
            ))}
          </select>
        </div>
        <div className="text-sm text-slate-600">
          {startItem}-{endItem} of {totalCount}
        </div>
        <div className="text-sm text-slate-600">
          Page {currentPage} of {totalPages}
        </div>
      </div>
      <div className="flex items-center space-x-2">
        <button
          onClick={() => onPageChange(currentPage - 1)}
          disabled={currentPage === 1}
          className="px-3 py-1 rounded border border-slate-300 text-sm disabled:opacity-50 disabled:cursor-not-allowed hover:bg-slate-50"
        >
          Previous
        </button>

        {getPageNumbers().map((page, idx) => (
          typeof page === 'number' ? (
            <button
              key={idx}
              onClick={() => onPageChange(page)}
              className={`px-3 py-1 rounded text-sm transition-colors ${
                page === currentPage
                  ? 'bg-blue-600 text-white border border-blue-600'
                  : 'border border-slate-300 hover:bg-slate-50'
              }`}
            >
              {page}
            </button>
          ) : (
            <span key={idx} className="px-2 text-slate-400">
              {page}
            </span>
          )
        ))}

        <button
          onClick={() => onPageChange(currentPage + 1)}
          disabled={currentPage === totalPages}
          className="px-3 py-1 rounded border border-slate-300 text-sm disabled:opacity-50 disabled:cursor-not-allowed hover:bg-slate-50"
        >
          Next
        </button>
      </div>
    </div>
  );
};

// ========================================
// Main Component
// ========================================

const WgcnaModuleGeneTable: React.FC<WgcnaModuleGeneTableProps> = ({
  genes: initialGenes,
  samples: initialSamples,
  moduleId,
  workbenchId,
  selectedGenes,
  onSelectionChange,
  params,
  onNavigateToVennDiagram,
  vennSetSummaries
}) => {
  const searchInputRef = useRef<HTMLTextAreaElement>(null);
  const [activeSearch, setActiveSearch] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(500);
  const [isActionMenuOpen, setActionMenuOpen] = useState(false);
  const actionMenuRef = useRef<HTMLDivElement>(null);
  const tableHeight = useTableHeight();

  // 백엔드에서 가져온 데이터 상태
  const [moduleData, setModuleData] = useState<WgcnaModuleDataResponse | null>(null);
  const [loading, setLoading] = useState(false);

  // Analysis modal states
  const [isGOModalOpen, setGOModalOpen] = useState(false);
  const [goAnalysisResult, setGOAnalysisResult] = useState<any>(null);
  const [isGOLoading, setGOLoading] = useState(false);
  const [isHeatmapModalOpen, setHeatmapModalOpen] = useState(false);
  const [isKEGGModalOpen, setKEGGModalOpen] = useState(false);
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
    description: `WGCNA Module ${moduleId} genes`,
  });
  const [selectAllState, setSelectAllState] = useState<0 | 1 | 2>(0);

  // Fetch module data from backend
  const fetchModuleData = useCallback(async (page: number, search: string, limit: number) => {
    setLoading(true);
    try {
      const response = await apiService.getWgcnaModuleData(workbenchId, moduleId, {
        source_type: params.sourceType,
        p_value: params.sourceType === 'deg' ? params.pValue : undefined,
        fold_change: params.sourceType === 'deg' ? params.foldChange : undefined,
        top_n_genes: params.sourceType === 'variance' ? params.topNGenes : undefined,
        soft_power: params.softPower,
        min_module_size: params.minModuleSize,
        deep_split: params.deepSplit,
        merge_cut_height: params.mergeCutHeight,
        search,
        page,
        limit
      });

      setModuleData(response);
    } catch (error) {
      console.error('❌ [WGCNA] Failed to fetch module data:', error);
    } finally {
      setLoading(false);
    }
  }, [workbenchId, moduleId, params]);

  // Initial load and reload when moduleId or params change
  useEffect(() => {
    setCurrentPage(1);
    setActiveSearch('');
    onSelectionChange(new Set());
    setSelectAllState(0);
    if (searchInputRef.current) {
      searchInputRef.current.value = '';
    }
    fetchModuleData(1, '', pageSize);
  }, [moduleId, params]);

  // Click outside handler for action menu
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (actionMenuRef.current && !actionMenuRef.current.contains(event.target as Node)) {
        setActionMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Use backend data or fallback to props
  const genes = moduleData?.genes || initialGenes;
  const samples = moduleData?.samples || initialSamples;
  const totalPages = moduleData?.total_pages || 1;
  const totalGenes = moduleData?.total_genes || genes.length;
  const tableColumnWidths = {
    select: 48,
    geneId: 150,
    geneSymbol: 120,
    pattern: 240,
    membership: 132,
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
    dependencyKey: [moduleId, currentPage, pageSize, genes.length, samples.length, activeSearch, loading ? 'loading' : 'idle'].join('|')
  });
  const tableColGroup = (
    <colgroup>
      <col style={{ width: `${tableColumnWidths.select}px` }} />
      <col style={{ width: `${tableColumnWidths.geneId}px` }} />
      <col style={{ width: `${tableColumnWidths.geneSymbol}px` }} />
      <col style={{ width: `${tableColumnWidths.pattern}px` }} />
      <col style={{ width: `${tableColumnWidths.membership}px` }} />
      {samples.map(sample => (
        <col key={sample} style={{ width: `${tableColumnWidths.sample}px` }} />
      ))}
    </colgroup>
  );

  // Selection handlers
  const fetchAllGeneIds = useCallback(async (): Promise<string[]> => {
    try {
      const response = await apiService.getWgcnaModuleData(workbenchId, moduleId, {
        source_type: params.sourceType,
        p_value: params.sourceType === 'deg' ? params.pValue : undefined,
        fold_change: params.sourceType === 'deg' ? params.foldChange : undefined,
        top_n_genes: params.sourceType === 'variance' ? params.topNGenes : undefined,
        soft_power: params.softPower,
        min_module_size: params.minModuleSize,
        deep_split: params.deepSplit,
        merge_cut_height: params.mergeCutHeight,
        search: activeSearch,
        page: 1,
        limit: totalGenes
      });
      return (response.genes || []).map((g: WgcnaGene) => g.gene_id);
    } catch (error) {
      console.error('Failed to fetch all gene IDs:', error);
      return [];
    }
  }, [workbenchId, moduleId, params, activeSearch, totalGenes]);

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

  const handleSelectOne = useCallback((geneId: string) => {
    const newSelectedGenes = new Set(selectedGenes);
    if (newSelectedGenes.has(geneId)) {
      newSelectedGenes.delete(geneId);
    } else {
      newSelectedGenes.add(geneId);
    }
    onSelectionChange(newSelectedGenes);
    setSelectAllState(0);
  }, [selectedGenes, onSelectionChange]);

  const tableHeaderRow = (
    <tr>
      <th className="p-2 text-left text-xs font-bold text-slate-600 uppercase tracking-wider w-12" style={{ width: `${tableColumnWidths.select}px`, minWidth: `${tableColumnWidths.select}px`, maxWidth: `${tableColumnWidths.select}px`, backgroundColor: 'rgb(248 250 252)', position: 'sticky', left: 0, zIndex: 24, boxShadow: '2px 0 4px rgba(0,0,0,0.05)' }}>
        <button onClick={handleSelectAllCycle} className="flex items-center justify-center w-5 h-5 hover:opacity-75 transition-opacity" title={selectAllState === 0 ? 'Select current page' : selectAllState === 1 ? 'Select all pages' : 'Deselect all'}>
          <svg viewBox="0 0 16 16" className="w-4 h-4" fill="none" xmlns="http://www.w3.org/2000/svg">
            {selectAllState === 0 && (<rect x="1" y="1" width="14" height="14" rx="2" stroke="#9CA3AF" strokeWidth="1.5"/>)}
            {selectAllState === 1 && (<><rect x="1" y="1" width="14" height="14" rx="2" stroke="#3B82F6" strokeWidth="1.5"/><path d="M4 8.5l2.5 2.5 5-5.5" stroke="#3B82F6" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></>)}
            {selectAllState === 2 && (<><rect x="1" y="1" width="14" height="14" rx="2" fill="#1D4ED8" stroke="#1D4ED8" strokeWidth="1.5"/><path d="M4 8.5l2.5 2.5 5-5.5" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></>)}
          </svg>
        </button>
      </th>
      <th className="px-2 py-2 text-left text-xs font-bold text-slate-600 uppercase tracking-wider" style={{ width: `${tableColumnWidths.geneId}px`, minWidth: `${tableColumnWidths.geneId}px`, maxWidth: `${tableColumnWidths.geneId}px`, backgroundColor: 'rgb(248 250 252)', position: 'sticky', left: `${tableStickyOffsets.geneId}px`, zIndex: 23, boxShadow: '2px 0 4px rgba(0,0,0,0.05)' }}>Gene ID</th>
      <th className="px-2 py-2 text-left text-xs font-bold text-slate-600 uppercase tracking-wider" style={{ width: `${tableColumnWidths.geneSymbol}px`, minWidth: `${tableColumnWidths.geneSymbol}px`, maxWidth: `${tableColumnWidths.geneSymbol}px`, backgroundColor: 'rgb(248 250 252)', position: 'sticky', left: `${tableStickyOffsets.geneSymbol}px`, zIndex: 22, boxShadow: '2px 0 4px rgba(0,0,0,0.05)' }}>Gene Symbol</th>
      <th className="px-2 py-2 text-center text-xs font-bold text-slate-600 uppercase tracking-wider" style={{ width: `${tableColumnWidths.pattern}px`, minWidth: `${tableColumnWidths.pattern}px`, maxWidth: `${tableColumnWidths.pattern}px`, backgroundColor: 'rgb(248 250 252)', position: 'sticky', left: `${tableStickyOffsets.pattern}px`, zIndex: 21, boxShadow: '2px 0 4px rgba(0,0,0,0.05)' }}>Expression Pattern</th>
      <th className="px-3 py-2 text-left text-xs font-bold text-slate-600 uppercase tracking-wider" style={{ width: `${tableColumnWidths.membership}px`, minWidth: `${tableColumnWidths.membership}px`, backgroundColor: 'rgb(248 250 252)' }}>Module Membership</th>
      {samples.map(sample => (
        <th key={sample} className="px-2 py-2 text-left text-xs font-bold text-slate-600 uppercase tracking-wider" style={{ width: `${tableColumnWidths.sample}px`, minWidth: `${tableColumnWidths.sample}px`, backgroundColor: 'rgb(248 250 252)' }}>
          {sample}
        </th>
      ))}
    </tr>
  );

  // Search handlers
  const handleSearch = () => {
    const searchValue = searchInputRef.current?.value.trim() || '';

    if (searchValue) {
      setActiveSearch(searchValue);
      setCurrentPage(1);
      onSelectionChange(new Set());
      setSelectAllState(0);
      fetchModuleData(1, searchValue, pageSize);
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
    fetchModuleData(1, '', pageSize);
  };

  // Pagination handlers
  const handlePageChange = (newPage: number) => {
    setCurrentPage(newPage);
    onSelectionChange(new Set());
    setSelectAllState(0);
    fetchModuleData(newPage, activeSearch, pageSize);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handlePageSizeChange = (newSize: number) => {
    setPageSize(newSize);
    setCurrentPage(1);
    onSelectionChange(new Set());
    setSelectAllState(0);
    fetchModuleData(1, activeSearch, newSize);
  };

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
        description: `WGCNA Module ${moduleId} genes`,
        organism: 'arabidopsis',
        provider
      });
      setGOAnalysisResult(result);
    } catch (error) {
      console.error('❌ [GO-ANALYSIS] Failed:', error);
    } finally {
      setGOLoading(false);
      setActionMenuOpen(false);
    }
  };

  // Handle Download
  const handleDownload = useCallback(() => {
    if (!genes || genes.length === 0) return;

    // Download selected genes if any, otherwise all genes
    const dataToDownload = selectedGenes.size > 0
      ? genes.filter(gene => selectedGenes.has(gene.gene_id))
      : genes;

    if (dataToDownload.length === 0) {
      alert('No data to download');
      return;
    }

    // Create TSV format
    const headers = ['GeneID', 'GeneSymbol', 'ModuleMembership', ...samples];
    const rows = [headers.join('\t')];

    dataToDownload.forEach(gene => {
      const row = [
        gene.gene_id,
        gene.gene_symbol,
        gene.module_membership.toFixed(4),
        ...samples.map(sample => gene[sample])
      ];
      rows.push(row.join('\t'));
    });

    const tsvContent = rows.join('\n');
    const blob = new Blob([tsvContent], { type: 'text/tab-separated-values;charset=utf-8;' });
    const url = URL.createObjectURL(blob);

    // Generate filename
    const timestamp = new Date().toISOString().slice(0, 10);
    const selectionType = selectedGenes.size > 0 ? `selected_${selectedGenes.size}` : 'all';
    const filename = `wgcna_module_${moduleId}_${selectionType}_${timestamp}.tsv`;

    // Trigger download
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    link.click();

    URL.revokeObjectURL(url);
  }, [genes, selectedGenes, moduleId, samples]);

  return (
    <div ref={tableSectionRef} className="mt-6 space-y-4 relative">
      {/* Table Title */}
      <div className="border-b border-slate-200 pb-3">
        <h3 className="text-lg font-semibold text-slate-900">Genes in Module: {moduleId}</h3>
        <p className="text-sm text-slate-500 mt-1">
          {totalGenes.toLocaleString()} genes · WGCNA co-expression module
        </p>
      </div>

      {/* Search Bar and Pagination */}
      <div className="flex items-center justify-between gap-4">
        {/* Left side: Search and Action Buttons */}
        <div className="flex flex-wrap items-center gap-4">
          <div className="relative">
            <textarea
              ref={searchInputRef}
              placeholder="Search Gene IDs or Symbols (comma, space, tab, or newline separated)..."
              onKeyDown={e => {
                if (e.key === 'Enter' && e.ctrlKey) {
                  handleSearch();
                }
              }}
              className="pl-10 pr-4 py-2 border border-slate-300 rounded-lg focus:ring-primary focus:border-primary w-64 min-h-[40px] max-h-[200px] resize-vertical"
              rows={1}
            />
            <div className="absolute top-2.5 left-0 pl-3 flex items-center pointer-events-none">
              <svg className="h-5 w-5 text-slate-400" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
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
              className="px-4 py-2 h-10 bg-slate-200 text-slate-700 rounded-lg hover:bg-slate-300 font-medium text-sm whitespace-nowrap"
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
            analyzeButtonClassName="px-4 py-2 h-10 bg-primary text-white rounded-lg hover:bg-primary-dark disabled:bg-slate-300 disabled:cursor-not-allowed flex items-center gap-1 font-medium text-sm whitespace-nowrap"
            toolbarClassName="contents"
            leftGroupClassName="contents"
            rightGroupClassName="contents"
          />
          <button
            onClick={handleDownload}
            disabled={!genes || genes.length === 0}
            className="px-4 py-2 h-10 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed font-medium text-sm flex items-center gap-2 whitespace-nowrap"
          >
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
            Download {selectedGenes.size > 0 ? `(${selectedGenes.size})` : ''}
          </button>
        </div>

        {/* Right side: Detailed Pagination */}
        {totalPages > 0 && (
          <div className="flex items-center space-x-2">
            <span className="text-sm text-slate-600">
              {(currentPage - 1) * pageSize + 1}-{Math.min(currentPage * pageSize, totalGenes)} of {totalGenes.toLocaleString()}
            </span>
            <select
              value={pageSize}
              onChange={(e) => handlePageSizeChange(Number(e.target.value))}
              className="text-sm border border-slate-300 rounded px-2 py-1 focus:ring-1 focus:ring-primary focus:border-primary"
            >
              <option value={100}>100</option>
              <option value={500}>500</option>
              <option value={1000}>1000</option>
              <option value={2000}>2000</option>
              <option value={3000}>3000</option>
            </select>
            <button
              onClick={() => handlePageChange(Math.max(1, currentPage - 1))}
              disabled={currentPage === 1}
              className="px-3 py-1 rounded border border-slate-300 text-sm disabled:opacity-50 disabled:cursor-not-allowed hover:bg-slate-50"
            >
              Previous
            </button>
            {(() => {
              const getPageNumbers = () => {
                const pages: (number | string)[] = [];
                const showEllipsis = totalPages > 3;

                if (!showEllipsis) {
                  // 3페이지 이하: 모두 표시
                  for (let i = 1; i <= totalPages; i++) {
                    pages.push(i);
                  }
                } else {
                  // 3페이지 초과: 축약 표시
                  if (currentPage <= 2) {
                    // 앞쪽: 1 2 ... 마지막
                    for (let i = 1; i <= 2; i++) pages.push(i);
                    pages.push('...');
                    pages.push(totalPages);
                  } else if (currentPage >= totalPages - 1) {
                    // 뒷쪽: 1 ... 마지막-1 마지막
                    pages.push(1);
                    pages.push('...');
                    for (let i = totalPages - 1; i <= totalPages; i++) pages.push(i);
                  } else {
                    // 중간: 1 ... 현재 ... 마지막
                    pages.push(1);
                    pages.push('...');
                    pages.push(currentPage);
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
                        : 'border border-slate-300 hover:bg-slate-50'
                    }`}
                  >
                    {page}
                  </button>
                ) : (
                  <span key={idx} className="px-2 text-slate-400">
                    {page}
                  </span>
                )
              );
            })()}
            <button
              onClick={() => handlePageChange(Math.min(totalPages, currentPage + 1))}
              disabled={currentPage === totalPages}
              className="px-3 py-1 rounded border border-slate-300 text-sm disabled:opacity-50 disabled:cursor-not-allowed hover:bg-slate-50"
            >
              Next
            </button>
          </div>
        )}
      </div>

      {/* Search Results Info */}
      {moduleData?.is_search_result && (
        <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg">
          <div className="flex items-center justify-between">
            <span className="text-sm text-blue-800">
              🔍 Search results for "{moduleData.search_query}": {totalGenes.toLocaleString()} gene{totalGenes !== 1 ? 's' : ''} found
            </span>
            <button
              onClick={handleClearSearch}
              className="text-xs text-blue-600 hover:text-blue-800 underline"
            >
              Clear search
            </button>
          </div>
        </div>
      )}

      {/* Table */}
      <div className="border border-slate-200 rounded-lg overflow-visible bg-white">
        <div ref={topScrollbarRef} className="overflow-x-auto overflow-y-hidden border-b border-slate-200 bg-slate-50">
          <div style={{ width: `${topScrollbarWidth}px`, height: '16px' }} />
        </div>
        <div ref={tableWrapperRef} className="relative" style={{ overflowX: 'auto', overflowY: 'visible' }}>
        <table ref={tableRef} className="data-table" style={{ position: 'relative', width: '100%' }}>
          {tableColGroup}
          <thead ref={tableTheadRef}>
            {tableHeaderRow}
          </thead>
          <tbody className="divide-y divide-slate-200">
            {genes.map((gene) => (
              <tr key={gene.gene_id} className="table-row">
                <td
                  className="p-2"
                  style={{
                    position: 'sticky',
                    left: 0,
                    zIndex: 24,
                    width: `${tableColumnWidths.select}px`,
                    minWidth: `${tableColumnWidths.select}px`,
                    maxWidth: `${tableColumnWidths.select}px`,
                    backgroundColor: 'white',
                    boxShadow: '2px 0 4px rgba(0,0,0,0.05)'
                  }}
                >
                  <input
                    type="checkbox"
                    className="h-4 w-4 rounded border-slate-300 text-primary focus:ring-primary"
                    checked={selectedGenes.has(gene.gene_id)}
                    onChange={() => handleSelectOne(gene.gene_id)}
                  />
                </td>
                <td
                  className="px-2 py-2 whitespace-nowrap text-sm font-medium text-slate-900 cursor-help"
                  style={{
                    position: 'sticky',
                    left: `${tableStickyOffsets.geneId}px`,
                    zIndex: 23,
                    width: `${tableColumnWidths.geneId}px`,
                    backgroundColor: 'white',
                    boxShadow: '2px 0 4px rgba(0,0,0,0.05)',
                    minWidth: `${tableColumnWidths.geneId}px`,
                    maxWidth: `${tableColumnWidths.geneId}px`
                  }}
                  title={gene.gene_description || 'No description available'}
                >
                  {gene.gene_id}
                </td>
                <td
                  className="px-2 py-2 whitespace-nowrap text-sm text-slate-700"
                  style={{
                    position: 'sticky',
                    left: `${tableStickyOffsets.geneSymbol}px`,
                    zIndex: 22,
                    width: `${tableColumnWidths.geneSymbol}px`,
                    backgroundColor: 'white',
                    boxShadow: '2px 0 4px rgba(0,0,0,0.05)',
                    minWidth: `${tableColumnWidths.geneSymbol}px`,
                    maxWidth: `${tableColumnWidths.geneSymbol}px`
                  }}
                >
                  {gene.gene_symbol}
                </td>
                <td className="px-2 py-2" style={{ position: 'sticky', left: `${tableStickyOffsets.pattern}px`, zIndex: 21, width: `${tableColumnWidths.pattern}px`, backgroundColor: 'white', boxShadow: '2px 0 4px rgba(0,0,0,0.05)', minWidth: `${tableColumnWidths.pattern}px`, maxWidth: `${tableColumnWidths.pattern}px` }}>
                  {(() => {
                    const values = samples.map(sample => {
                      const value = gene[sample];
                      return typeof value === 'number' ? value : parseFloat(value as string) || 0;
                    });

                    if (values.length > 0 && samples.length > 0) {
                      return (
                        <MiniHeatmap
                          values={values}
                          samples={samples}
                          width={Math.min(samples.length * 16, 240)}
                          height={20}
                        />
                      );
                    } else {
                      return <span className="text-xs text-slate-400">N/A</span>;
                    }
                  })()}
                </td>
                <td
                  className="px-3 py-2 whitespace-nowrap text-sm text-slate-600"
                  style={{ minWidth: `${tableColumnWidths.membership}px` }}
                >
                  {gene.module_membership.toFixed(4)}
                </td>
                {samples.map(sample => (
                  <td
                    key={sample}
                    className="px-2 py-2 whitespace-nowrap text-sm text-slate-600"
                  >
                    {typeof gene[sample] === 'number'
                      ? (gene[sample] as number).toFixed(2)
                      : gene[sample]}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      </div>

      {overlayHeader.visible && typeof document !== 'undefined' && createPortal(
        <div className="fixed z-[120] pointer-events-none" style={{ top: overlayHeader.top, left: overlayHeader.left, width: overlayHeader.width }}>
          <div ref={floatingTopScrollbarRef} className="overflow-x-auto overflow-y-hidden bg-slate-50 border border-slate-200 border-b-0 rounded-t-lg pointer-events-auto" style={{ width: `${overlayHeader.width}px` }}>
            <div style={{ width: `${overlayHeader.tableWidth}px`, height: '16px' }} />
          </div>
          <div className="relative" style={{ width: `${overlayHeader.width}px`, height: `${overlayHeader.height || 57}px` }}>
            <div className="absolute top-0 left-0 overflow-hidden border-x border-b border-slate-200 bg-slate-50 shadow-sm" style={{ width: `${Math.min(fixedHeaderWidth, overlayHeader.width)}px` }}>
              <table className="data-table" style={{ width: `${Math.min(fixedHeaderWidth, overlayHeader.width)}px`, tableLayout: 'fixed' }}>
                <colgroup>
                  <col style={{ width: `${tableColumnWidths.select}px` }} />
                  <col style={{ width: `${tableColumnWidths.geneId}px` }} />
                  <col style={{ width: `${tableColumnWidths.geneSymbol}px` }} />
                  <col style={{ width: `${tableColumnWidths.pattern}px` }} />
                </colgroup>
                <thead>{tableHeaderRow}</thead>
              </table>
            </div>
            <div className="absolute top-0 overflow-hidden border-r border-b border-slate-200 bg-slate-50 shadow-sm" style={{ left: `${Math.min(fixedHeaderWidth, overlayHeader.width)}px`, width: `${Math.max(0, overlayHeader.width - Math.min(fixedHeaderWidth, overlayHeader.width))}px` }}>
              <div style={{ width: `${Math.max(0, overlayHeader.tableWidth - fixedHeaderWidth)}px`, transform: `translateX(-${overlayHeader.scrollLeft}px)` }}>
                <table className="data-table" style={{ width: `${Math.max(0, overlayHeader.tableWidth - fixedHeaderWidth)}px`, tableLayout: 'fixed' }}>
                  <colgroup>
                    <col style={{ width: `${tableColumnWidths.membership}px` }} />
                    {samples.map(sample => <col key={sample} style={{ width: `${tableColumnWidths.sample}px` }} />)}
                  </colgroup>
                  <thead>
                    <tr>
                      <th className="px-3 py-2 text-left text-xs font-bold text-slate-600 uppercase tracking-wider" style={{ width: `${tableColumnWidths.membership}px`, minWidth: `${tableColumnWidths.membership}px` }}>Module Membership</th>
                      {samples.map(sample => (
                        <th key={sample} className="px-2 py-2 text-left text-xs font-bold text-slate-600 uppercase tracking-wider" style={{ width: `${tableColumnWidths.sample}px`, minWidth: `${tableColumnWidths.sample}px` }}>
                          {sample}
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

      {/* Loading Overlay */}
      {loading && (
        <div className="absolute inset-0 bg-white bg-opacity-75 flex items-center justify-center z-40">
          <div className="text-center">
            <div className="animate-spin rounded-full h-12 w-12 border-b-4 border-blue-600 mx-auto mb-4"></div>
            <p className="text-slate-600">Loading results...</p>
          </div>
        </div>
      )}

      {/* No Results Message */}
      {!loading && genes.length === 0 && (
        <div className="text-center py-12">
          <div className="text-slate-400 mb-4">
            <svg className="w-16 h-16 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
          </div>
          <h4 className="text-lg font-medium text-slate-900 mb-2">No genes found</h4>
          <p className="text-slate-500">
            {activeSearch
              ? `No genes match your search criteria "${activeSearch}"`
              : 'No genes available in this module'}
          </p>
        </div>
      )}

      {/* GO Analysis Modal */}
      <GOAnalysisModal
        isOpen={analysisGOModalOpen}
        onClose={closeAnalysisGO}
        result={analysisGOResult}
        isLoading={analysisGOLoading}
        workbenchId={workbenchId}
        comparisonName={`WGCNA Module ${moduleId}`}
        toolName="WGCNA"
      />

      {/* Heatmap Analysis Modal */}
      <HeatmapAnalysisModal
        isOpen={analysisHeatmapOpen}
        onClose={closeAnalysisHeatmap}
        workbenchId={workbenchId}
        selectedGenes={Array.from(selectedGenes)}
        comparisonName={`WGCNA Module ${moduleId}`}
        toolName="WGCNA"
      />

      {/* KEGG Pathway Modal */}
      <KEGGPathwayModal
        isOpen={analysisKEGGOpen}
        onClose={closeAnalysisKEGG}
        workbenchId={workbenchId}
        selectedGenes={Array.from(selectedGenes)}
        comparisonName={`WGCNA Module ${moduleId}`}
        toolName="WGCNA"
      />
    </div>
  );
};

export default WgcnaModuleGeneTable;
