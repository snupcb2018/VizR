import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { createPortal } from 'react-dom';
import ColumnFilterPopup, { ColumnFilter } from './ColumnFilterPopup';
import GOAnalysisModal from './GOAnalysisModal';
import GOProviderSubmenu from './GOProviderSubmenu';
import CopyGeneListMenuItem from './CopyGeneListMenuItem';
import HeatmapAnalysisModal from './HeatmapAnalysisModal';
import KEGGPathwayModal from './KEGGPathwayModal';
import VennSetMenu, { VennSetSummary } from './VennSetMenu';
import MiniHeatmap from './MiniHeatmap';
import SelectableGeneTableShell from './SelectableGeneTableShell';
import { apiService } from '../services/api';
import useWebSocket from '../src/hooks/useWebSocket';
import { useGeneAnalysisActions } from '../hooks/useGeneAnalysisActions';

// ========================================
// Type Definitions
// ========================================

interface WorkbenchDetailDEGMatrixUpProps {
    workbenchId: number;
    comparisonName: string;
    toolName: string;
    selectedGenes: Set<string>;
    onSelectionChange: (genes: Set<string>) => void;
    onAnalysisRequest: (type: string) => void;
    showComingSoon: () => void;
    onNavigateToVennDiagram: (genes: string[], targetSetIndex?: number) => void;
    vennSetSummaries?: VennSetSummary[];
}

interface FilterConfig {
    [columnName: string]: ColumnFilter;
}

interface DEGResultsResponse {
    comparison: string;
    tool_name: string;
    data: Array<{
        GeneID: string;
        GeneSymbol: string;
        GeneDescription: string;
        logFC: number;
        logCPM: number;
        PValue: number;
        FDR: number;
        [sample: string]: number | string;
    }>;
    total: number;
    page: number;
    limit: number;
    columns: string[];
    samples?: string[];
    filter_type: string;
    low_expression_filter?: {
        enabled: boolean;
        min_tmm: number;
        min_sample_pct: number;
    };
}

type LowExpressionPreset = 'relaxed' | 'standard' | 'strict' | 'custom';

interface LowExpressionFilterState {
    enabled: boolean;
    preset: LowExpressionPreset;
    minTmm: string;
    minSamplePct: string;
}

interface LowExpressionProgressState {
    status: 'preparing' | 'running' | 'finalizing' | 'completed' | 'failed';
    stage: string;
    message: string;
    comparison_name: string;
    tool_name: string;
    total_contrasts: number;
    completed_contrasts: number;
    current_contrast: number;
    progress_percent: number;
}

const DEFAULT_LOW_EXPRESSION_FILTER: LowExpressionFilterState = {
    enabled: false,
    preset: 'standard',
    minTmm: '1',
    minSamplePct: '25'
};

const LOW_EXPRESSION_PRESETS: Record<Exclude<LowExpressionPreset, 'custom'>, { minTmm: number; minSamplePct: number }> = {
    relaxed: { minTmm: 1, minSamplePct: 10 },
    standard: { minTmm: 1, minSamplePct: 25 },
    strict: { minTmm: 1, minSamplePct: 50 }
};

const resolveLowExpressionFilter = (filterState: LowExpressionFilterState) => {
    if (filterState.preset === 'custom') {
        return {
            minTmm: Math.max(0, Number(filterState.minTmm) || 0),
            minSamplePct: Math.min(100, Math.max(0, Number(filterState.minSamplePct) || 0))
        };
    }

    return LOW_EXPRESSION_PRESETS[filterState.preset];
};

const appendLowExpressionParams = (
    params: URLSearchParams,
    filterState: LowExpressionFilterState
) => {
    if (!filterState.enabled) {
        return;
    }

    const resolved = resolveLowExpressionFilter(filterState);
    params.append('low_expr_enabled', 'true');
    params.append('low_expr_min_tmm', resolved.minTmm.toString());
    params.append('low_expr_min_sample_pct', resolved.minSamplePct.toString());
};

const isSameLowExpressionFilter = (
    left: LowExpressionFilterState,
    right: LowExpressionFilterState
) => (
    left.enabled === right.enabled &&
    left.preset === right.preset &&
    left.minTmm === right.minTmm &&
    left.minSamplePct === right.minSamplePct
);

const getLowExpressionFilterStorageKey = (workbenchId: number) =>
    `vizr:deg:low-expression-filter:${workbenchId}`;

const loadStoredLowExpressionFilter = (workbenchId: number): LowExpressionFilterState => {
    if (typeof window === 'undefined') {
        return DEFAULT_LOW_EXPRESSION_FILTER;
    }

    try {
        const raw = window.sessionStorage.getItem(getLowExpressionFilterStorageKey(workbenchId));
        if (!raw) {
            return DEFAULT_LOW_EXPRESSION_FILTER;
        }

        const parsed = JSON.parse(raw);
        return {
            enabled: Boolean(parsed.enabled),
            preset: ['relaxed', 'standard', 'strict', 'custom'].includes(parsed.preset)
                ? parsed.preset
                : DEFAULT_LOW_EXPRESSION_FILTER.preset,
            minTmm: String(parsed.minTmm ?? DEFAULT_LOW_EXPRESSION_FILTER.minTmm),
            minSamplePct: String(parsed.minSamplePct ?? DEFAULT_LOW_EXPRESSION_FILTER.minSamplePct)
        };
    } catch {
        return DEFAULT_LOW_EXPRESSION_FILTER;
    }
};

// ========================================
// Utility Hooks
// ========================================

const useTableHeight = () => {
    const [tableHeight, setTableHeight] = useState('60vh');

    useEffect(() => {
        const calculateHeight = () => {
            const viewportHeight = window.innerHeight;
            const headerHeight = 120;
            const tabsHeight = 60;
            const paddingHeight = 100;
            const toolbarHeight = 80;

            const availableHeight = viewportHeight - headerHeight - tabsHeight - paddingHeight - toolbarHeight;
            const minHeight = Math.max(300, availableHeight);
            const maxHeight = Math.min(viewportHeight * 0.8, minHeight);

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
    const pageSizeOptions = [100, 500, 1000, 2000, 5000];

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

const WorkbenchDetailDEGMatrixUp: React.FC<WorkbenchDetailDEGMatrixUpProps> = ({
    workbenchId,
    comparisonName,
    toolName,
    selectedGenes,
    onSelectionChange,
    onAnalysisRequest,
    showComingSoon,
    onNavigateToVennDiagram,
    vennSetSummaries
}) => {
    const [degResults, setDegResults] = useState<DEGResultsResponse | null>(null);
    const [loading, setLoading] = useState(false);
    const [showLowExpressionLoadingHint, setShowLowExpressionLoadingHint] = useState(false);
    const [lowExprProgress, setLowExprProgress] = useState<LowExpressionProgressState | null>(null);
    const [isLowExprRecalculationRunning, setIsLowExprRecalculationRunning] = useState(false);
    const searchInputRef = useRef<HTMLTextAreaElement>(null);  // 검색 입력 참조
    const [activeSearch, setActiveSearch] = useState('');
    const [currentPage, setCurrentPage] = useState(1);
    const [pageSize, setPageSize] = useState(500);
    const [filters, setFilters] = useState<FilterConfig>({});
    const [sortBy, setSortBy] = useState<string | null>(null);
    const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('asc');
    const [activeFilterColumn, setActiveFilterColumn] = useState<string | null>(null);
    const [selectAllState, setSelectAllState] = useState<0 | 1 | 2>(0);
    const [showScrollToTopButton, setShowScrollToTopButton] = useState(false);
    const [overlayHeader, setOverlayHeader] = useState<{ visible: boolean; top: number; left: number; width: number }>({
        visible: false,
        top: 0,
        left: 0,
        width: 0
    });
    const scrollTargetRef = useRef<HTMLElement | Window | null>(null);
    const matrixSectionRef = useRef<HTMLDivElement | null>(null);
    const matrixTableWrapperRef = useRef<HTMLDivElement | null>(null);
    const matrixTableRef = useRef<HTMLTableElement | null>(null);
    const matrixTheadRef = useRef<HTMLTableSectionElement | null>(null);

    // Analysis menu states
    const [isActionMenuOpen, setActionMenuOpen] = useState(false);
    const actionMenuRef = useRef<HTMLDivElement>(null);

    // GO Analysis modal states
    const [isGOModalOpen, setGOModalOpen] = useState(false);
    const [goAnalysisResult, setGOAnalysisResult] = useState<any>(null);
    const [isGOLoading, setGOLoading] = useState(false);

    // Heatmap Analysis modal state
    const [isHeatmapModalOpen, setHeatmapModalOpen] = useState(false);

    // KEGG Pathway modal state
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
        description: `Significant up-regulated genes from ${comparisonName}`,
    });

    // TMM counts data for mini heatmap
    const [tmmData, setTmmData] = useState<{ [geneId: string]: number[] } | null>(null);
    const [sampleNames, setSampleNames] = useState<string[]>([]);
    const [lowExpressionFilterDraft, setLowExpressionFilterDraft] = useState<LowExpressionFilterState>(() => loadStoredLowExpressionFilter(workbenchId));
    const [appliedLowExpressionFilter, setAppliedLowExpressionFilter] = useState<LowExpressionFilterState>(() => loadStoredLowExpressionFilter(workbenchId));
    const resolvedAppliedLowExpressionFilter = useMemo(
        () => resolveLowExpressionFilter(appliedLowExpressionFilter),
        [appliedLowExpressionFilter]
    );
    const resolvedDraftLowExpressionFilter = useMemo(
        () => resolveLowExpressionFilter(lowExpressionFilterDraft),
        [lowExpressionFilterDraft]
    );
    const hasPendingLowExpressionChanges = !isSameLowExpressionFilter(lowExpressionFilterDraft, appliedLowExpressionFilter);
    const progressPercent = Math.min(100, Math.max(0, lowExprProgress?.progress_percent || 5));

    useEffect(() => {
        if (typeof window === 'undefined') {
            return;
        }

        window.sessionStorage.setItem(
            getLowExpressionFilterStorageKey(workbenchId),
            JSON.stringify(appliedLowExpressionFilter)
        );
    }, [workbenchId, appliedLowExpressionFilter]);

    useWebSocket({
        workbenchId,
        taskType: 'deg_lowexpr',
        enabled: true,
        onProgressUpdate: (data) => {
            const progressInfo = data.data || data;
            const normalizedExpectedTool = (toolName || '').toLowerCase();
            const normalizedActualTool = (progressInfo?.tool_name || '').toLowerCase();
            if (!progressInfo || progressInfo.comparison_name !== comparisonName) {
                return;
            }
            if (progressInfo.tool_name && normalizedActualTool !== normalizedExpectedTool) {
                return;
            }

            setLowExprProgress({
                status: progressInfo.status || 'running',
                stage: progressInfo.stage || 'contrasts',
                message: progressInfo.message || 'Recalculating DEG results...',
                comparison_name: progressInfo.comparison_name,
                tool_name: progressInfo.tool_name || toolName,
                total_contrasts: progressInfo.total_contrasts || 0,
                completed_contrasts: progressInfo.completed_contrasts || 0,
                current_contrast: progressInfo.current_contrast || 0,
                progress_percent: progressInfo.progress_percent || 0
            });

            const running = !['completed', 'failed'].includes(progressInfo.status || '');
            setIsLowExprRecalculationRunning(running);
            if (running) {
                setShowLowExpressionLoadingHint(true);
            }
        }
    });

    // Fetch DEG results from API
    const fetchDEGResults = useCallback(async (
        page: number = 1,
        search: string = '',
        columnFilters: FilterConfig = {},
        sortColumn: string | null = null,
        sortDirection: 'asc' | 'desc' = 'asc',
        customPageSize?: number,  // 선택적 pageSize 매개변수 추가
        lowExpressionFilterOverride?: LowExpressionFilterState,
        showLongRunningHint: boolean = false
    ) => {
        setShowLowExpressionLoadingHint(showLongRunningHint);
        if (showLongRunningHint) {
            setIsLowExprRecalculationRunning(true);
            setLowExprProgress({
                status: 'preparing',
                stage: 'preparing',
                message: 'Preparing low-expression DEG recalculation...',
                comparison_name: comparisonName,
                tool_name: toolName,
                total_contrasts: 0,
                completed_contrasts: 0,
                current_contrast: 0,
                progress_percent: 5
            });
        }
        setLoading(true);
        try {
            const effectivePageSize = customPageSize || pageSize;  // 전달된 값 또는 현재 상태 사용
            const params = new URLSearchParams({
                tool_name: toolName,
                page: page.toString(),
                limit: effectivePageSize.toString(),
                filter_type: 'up',
                data_type: 'matrix'
            });

            appendLowExpressionParams(params, lowExpressionFilterOverride || appliedLowExpressionFilter);

            if (search) {
                params.append('search', search);
            }

            if (Object.keys(columnFilters).length > 0) {
                params.append('filters', JSON.stringify(columnFilters));
            }

            if (sortColumn) {
                params.append('sort_by', sortColumn);
                params.append('sort_order', sortDirection);
            }

            const response = await fetch(
                `/api/workbenches/${workbenchId}/deg/results/${comparisonName}?${params}`,
                { credentials: 'include' }
            );

            if (response.ok) {
                const data = await response.json();
                setDegResults(data);

                // Fetch TMM counts for mini heatmap
                if (data.data && data.data.length > 0) {
                    const geneIds = data.data.map((gene: any) => gene.GeneID);
                    try {
                        const tmmResponse = await apiService.fetchTMMCountsByGenes(
                            workbenchId,
                            geneIds,
                            comparisonName,
                            toolName
                        );
                        if (tmmResponse.success) {
                            setTmmData(tmmResponse.data);
                            setSampleNames(tmmResponse.sample_names);
                        }
                    } catch {
                        // Ignore mini-heatmap fetch failures and keep the table visible.
                    }
                }
            }
        } catch {
            // Ignore DEG fetch errors here; empty state remains visible.
        } finally {
            setShowLowExpressionLoadingHint(false);
            if (showLongRunningHint) {
                setIsLowExprRecalculationRunning(false);
                setLowExprProgress(null);
            }
            setLoading(false);
        }
    }, [workbenchId, comparisonName, toolName, pageSize, appliedLowExpressionFilter]);

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

    // Initial load and reload when comparison or tool changes.
    // Low-expression filter state is preserved across comparison/tool changes within the same workbench.
    useEffect(() => {
        // Reset table/search/sort/selection states when comparison or tool changes
        setCurrentPage(1);
        setActiveSearch('');
        setFilters({});
        setSortBy(null);
        setSortOrder('asc');
        onSelectionChange(new Set());
        setSelectAllState(0);
        if (searchInputRef.current) {
            searchInputRef.current.value = '';
        }
        setLowExprProgress(null);
        setIsLowExprRecalculationRunning(false);

        // Fetch new data
        fetchDEGResults(1, '', {}, null, 'asc', undefined, undefined, appliedLowExpressionFilter.enabled);
    }, [comparisonName, toolName]);

    // Filter data using useMemo for performance
    const filteredData = useMemo(() => {
        if (!degResults?.data || degResults.data.length === 0) {
            return [];
        }

        return degResults.data.map(gene => ({
            gene: gene.GeneID,
            gene_symbol: gene.GeneSymbol,
            gene_description: gene.GeneDescription,
            logFC: gene.logFC,
            logCPM: gene.logCPM,
            PValue: gene.PValue,
            FDR: gene.FDR
        }));
    }, [degResults]);

    const matrixColumnWidths = {
        select: 48,
        geneId: 120,
        geneSymbol: 120,
        pattern: 240,
        metric: 100
    } as const;

    const matrixStickyOffsets = {
        geneId: matrixColumnWidths.select,
        geneSymbol: matrixColumnWidths.select + matrixColumnWidths.geneId
    } as const;

    const matrixColGroup = (
        <colgroup>
            <col style={{ width: `${matrixColumnWidths.select}px` }} />
            <col style={{ width: `${matrixColumnWidths.geneId}px` }} />
            <col style={{ width: `${matrixColumnWidths.geneSymbol}px` }} />
            <col style={{ width: `${matrixColumnWidths.pattern}px` }} />
            <col style={{ width: `${matrixColumnWidths.metric}px` }} />
            <col style={{ width: `${matrixColumnWidths.metric}px` }} />
            <col style={{ width: `${matrixColumnWidths.metric}px` }} />
            <col style={{ width: `${matrixColumnWidths.metric}px` }} />
        </colgroup>
    );

    // Fetch all gene IDs across all pages (for state 2 select all)
    const fetchAllGeneIds = useCallback(async (): Promise<string[]> => {
        try {
            const total = degResults?.total || 0;
            if (total === 0) return [];
            const params = new URLSearchParams({
                tool_name: toolName,
                page: '1',
                limit: total.toString(),
                filter_type: 'up',
                data_type: 'matrix'
            });
            appendLowExpressionParams(params, appliedLowExpressionFilter);
            if (activeSearch) params.append('search', activeSearch);
            if (Object.keys(filters).length > 0) params.append('filters', JSON.stringify(filters));
            const response = await fetch(
                `/api/workbenches/${workbenchId}/deg/results/${comparisonName}?${params}`,
                { credentials: 'include' }
            );
            if (response.ok) {
                const data = await response.json();
                return data.data.map((gene: any) => gene.GeneID as string);
            }
            return [];
        } catch {
            return [];
        }
    }, [workbenchId, comparisonName, toolName, degResults?.total, activeSearch, filters, appliedLowExpressionFilter]);

    // 3-state select all cycle: none → current page → all pages → none
    const handleSelectAllCycle = useCallback(async () => {
        if (selectAllState === 0) {
            // → State 1: select current page
            const newSelected = new Set(selectedGenes);
            filteredData.forEach(item => newSelected.add(item.gene));
            onSelectionChange(newSelected);
            setSelectAllState(1);
        } else if (selectAllState === 1) {
            // → State 2: select all pages (API call)
            setLoading(true);
            const allIds = await fetchAllGeneIds();
            onSelectionChange(new Set<string>(allIds));
            setSelectAllState(2);
            setLoading(false);
        } else {
            // → State 0: deselect all
            onSelectionChange(new Set());
            setSelectAllState(0);
        }
    }, [selectAllState, filteredData, selectedGenes, onSelectionChange, fetchAllGeneIds]);

    // Selection handlers
    const handleSelectOne = useCallback((gene: string) => {
        const newSelectedGenes = new Set(selectedGenes);
        if (newSelectedGenes.has(gene)) {
            newSelectedGenes.delete(gene);
        } else {
            newSelectedGenes.add(gene);
        }
        onSelectionChange(newSelectedGenes);
        setSelectAllState(0);
    }, [selectedGenes, onSelectionChange]);

    // Search handlers
    const handleSearch = () => {
        const searchValue = searchInputRef.current?.value.trim() || '';
        if (searchValue) {
            setActiveSearch(searchValue);
            setCurrentPage(1);
            onSelectionChange(new Set()); // Reset selection
            fetchDEGResults(1, searchValue, filters, sortBy, sortOrder);
        }
    };

    const handleClearSearch = () => {
        if (searchInputRef.current) {
            searchInputRef.current.value = '';
        }
        setActiveSearch('');
        setCurrentPage(1);
        onSelectionChange(new Set()); // Reset selection
        fetchDEGResults(1, '', filters, sortBy, sortOrder);
    };

    const handleLowExpressionToggle = (enabled: boolean) => {
        setLowExpressionFilterDraft(prev => ({ ...prev, enabled }));
    };

    const handleLowExpressionPresetChange = (preset: LowExpressionPreset) => {
        setLowExpressionFilterDraft(prev => {
            if (preset === 'custom') {
                return { ...prev, preset };
            }

            const presetConfig = LOW_EXPRESSION_PRESETS[preset];
            return {
                ...prev,
                preset,
                minTmm: presetConfig.minTmm.toString(),
                minSamplePct: presetConfig.minSamplePct.toString()
            };
        });
    };

    const handleApplyLowExpressionFilter = () => {
        setAppliedLowExpressionFilter(lowExpressionFilterDraft);
        setCurrentPage(1);
        onSelectionChange(new Set());
        setSelectAllState(0);
        fetchDEGResults(1, activeSearch, filters, sortBy, sortOrder, undefined, lowExpressionFilterDraft, lowExpressionFilterDraft.enabled);
    };

    // Pagination handlers
    const handlePageChange = (newPage: number) => {
        setCurrentPage(newPage);
        onSelectionChange(new Set()); // Reset selection
        fetchDEGResults(newPage, activeSearch, filters, sortBy, sortOrder);
        window.scrollTo({ top: 0, behavior: 'smooth' });
    };

    const handlePageSizeChange = (newSize: number) => {
        setPageSize(newSize);
        setCurrentPage(1);
        onSelectionChange(new Set()); // Reset selection
        // pageSize 매개변수를 직접 전달하여 즉시 반영되도록 수정
        fetchDEGResults(1, activeSearch, filters, sortBy, sortOrder, newSize);
    };

    // Filter handler
    const handleFilterApply = useCallback((
        columnName: string,
        filter: ColumnFilter | null,
        sort: 'asc' | 'desc' | null
    ) => {
        const newFilters = { ...filters };

        if (filter) {
            newFilters[columnName] = filter;
        } else {
            delete newFilters[columnName];
        }

        setFilters(newFilters);

        let newSortBy = sortBy;
        let newSortOrder = sortOrder;

        if (sort) {
            newSortBy = columnName;
            newSortOrder = sort;
            setSortBy(columnName);
            setSortOrder(sort);
        } else if (sortBy === columnName) {
            newSortBy = null;
            setSortBy(null);
        }

        setCurrentPage(1);
        setActiveFilterColumn(null);
        onSelectionChange(new Set()); // Reset selection
        fetchDEGResults(1, activeSearch, newFilters, newSortBy, newSortOrder);
    }, [filters, sortBy, sortOrder, activeSearch, fetchDEGResults, onSelectionChange]);

    const handleScrollToTop = () => {
        const target = scrollTargetRef.current;
        if (target && target !== window) {
            target.scrollTo({ top: 0, behavior: 'smooth' });
            return;
        }
        window.scrollTo({ top: 0, behavior: 'smooth' });
    };

    const matrixHeaderRow = (
        <tr>
            <th
                className="p-2 text-left text-xs font-bold text-slate-600 uppercase tracking-wider"
                style={{
                    width: `${matrixColumnWidths.select}px`,
                    backgroundColor: 'rgb(248 250 252)',
                    boxShadow: '2px 0 4px rgba(0,0,0,0.05)'
                }}
            >
                <button
                    onClick={handleSelectAllCycle}
                    title={
                        selectAllState === 0
                            ? `Select current page (${filteredData.length} genes)`
                            : selectAllState === 1
                            ? `Select all ${degResults?.total?.toLocaleString()} genes`
                            : 'Deselect all'
                    }
                    className="flex items-center justify-center w-5 h-5 cursor-pointer rounded focus:outline-none focus:ring-2 focus:ring-blue-400"
                >
                    {selectAllState === 0 && (
                        <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                            <rect x="1" y="1" width="14" height="14" rx="2" stroke="#9CA3AF" strokeWidth="1.5"/>
                        </svg>
                    )}
                    {selectAllState === 1 && (
                        <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                            <rect x="1" y="1" width="14" height="14" rx="2" stroke="#3B82F6" strokeWidth="1.5"/>
                            <path d="M4 8.5l2.5 2.5 5-5.5" stroke="#3B82F6" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                        </svg>
                    )}
                    {selectAllState === 2 && (
                        <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                            <rect x="1" y="1" width="14" height="14" rx="2" fill="#1D4ED8" stroke="#1D4ED8" strokeWidth="1.5"/>
                            <path d="M4 8.5l2.5 2.5 5-5.5" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                        </svg>
                    )}
                </button>
            </th>
            <th className="px-2 py-2 text-left text-xs font-bold text-slate-600 uppercase tracking-wider" style={{ width: `${matrixColumnWidths.geneId}px`, minWidth: `${matrixColumnWidths.geneId}px`, backgroundColor: 'rgb(248 250 252)' }}>
                Gene ID
            </th>
            <th className="px-2 py-2 text-left text-xs font-bold text-slate-600 uppercase tracking-wider" style={{ width: `${matrixColumnWidths.geneSymbol}px`, minWidth: `${matrixColumnWidths.geneSymbol}px`, backgroundColor: 'rgb(248 250 252)' }}>
                Gene Symbol
            </th>
            <th className="px-2 py-2 text-left text-xs font-bold text-slate-600 uppercase tracking-wider" style={{ width: `${matrixColumnWidths.pattern}px`, minWidth: `${matrixColumnWidths.pattern}px`, backgroundColor: 'rgb(248 250 252)' }}>
                Expression Pattern
            </th>
            {['logFC', 'logCPM', 'PValue', 'FDR'].map(column => {
                const hasFilter = !!filters[column];
                const hasSort = sortBy === column;
                const isActive = hasFilter || hasSort;

                return (
                    <th
                        key={column}
                        className="px-2 py-2 text-left text-xs font-bold text-slate-600 uppercase tracking-wider"
                        style={{ width: `${matrixColumnWidths.metric}px`, minWidth: `${matrixColumnWidths.metric}px`, backgroundColor: 'rgb(248 250 252)' }}
                    >
                        <div className="flex items-center relative">
                            <span>{column}</span>
                            {hasSort && (
                                <span className="ml-1 text-blue-600 font-bold text-base">
                                    {sortOrder === 'asc' ? '↑' : '↓'}
                                </span>
                            )}
                            <div className="relative">
                                <button
                                    onClick={() => setActiveFilterColumn(column)}
                                    className={`ml-1 p-1 rounded transition-colors ${
                                        isActive ? 'text-blue-600 bg-blue-50' : 'text-slate-400 hover:bg-slate-100'
                                    }`}
                                    title={`Filter ${column}`}
                                >
                                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.5 6h9.75M10.5 6a1.5 1.5 0 11-3 0m3 0a1.5 1.5 0 10-3 0M3.75 6H7.5m3 12h9.75m-9.75 0a1.5 1.5 0 01-3 0m3 0a1.5 1.5 0 00-3 0m-3.75 0H7.5m9-6h3.75m-3.75 0a1.5 1.5 0 01-3 0m3 0a1.5 1.5 0 00-3 0m-9.75 0h9.75" />
                                    </svg>
                                </button>
                                {hasFilter && (
                                    <span className="absolute -top-1 -right-1 flex h-2 w-2">
                                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
                                        <span className="relative inline-flex rounded-full h-2 w-2 bg-blue-500"></span>
                                    </span>
                                )}
                            </div>

                            {activeFilterColumn === column && (
                                <ColumnFilterPopup
                                    isOpen={true}
                                    onClose={() => setActiveFilterColumn(null)}
                                    columnName={column}
                                    currentFilter={filters[column]}
                                    currentSort={sortBy === column ? sortOrder : undefined}
                                    onApply={(filter, sort) => handleFilterApply(column, filter, sort)}
                                />
                            )}
                        </div>
                    </th>
                );
            })}
        </tr>
    );

    useEffect(() => {
        const section = matrixSectionRef.current;
        if (!section) {
            return;
        }

        const findScrollParent = (node: HTMLElement | null): HTMLElement | null => {
            let current = node?.parentElement ?? null;
            while (current) {
                const styles = window.getComputedStyle(current);
                const overflowY = styles.overflowY;
                const isScrollable = (overflowY === 'auto' || overflowY === 'scroll' || overflowY === 'overlay')
                    && current.scrollHeight > current.clientHeight + 4;
                if (isScrollable) {
                    return current;
                }
                current = current.parentElement;
            }
            return null;
        };

        const scrollTarget = findScrollParent(section) ?? window;
        scrollTargetRef.current = scrollTarget;
        const updateVisibility = () => {
            const scrollTop = scrollTarget === window
                ? (window.scrollY || document.documentElement.scrollTop || document.body.scrollTop || 0)
                : scrollTarget.scrollTop;
            const nextVisible = scrollTop > 320;
            setShowScrollToTopButton(nextVisible);
        };

        updateVisibility();
        scrollTarget.addEventListener('scroll', updateVisibility, { passive: true });
        return () => {
            scrollTarget.removeEventListener('scroll', updateVisibility);
            if (scrollTargetRef.current === scrollTarget) {
                scrollTargetRef.current = null;
            }
        };
    }, [comparisonName, currentPage, pageSize, filteredData.length]);

    useEffect(() => {
        const section = matrixSectionRef.current;
        const table = matrixTableRef.current;
        const thead = matrixTheadRef.current;

        if (!section || !table || !thead || filteredData.length === 0) {
            setOverlayHeader(current => current.visible ? { visible: false, top: 0, left: 0, width: 0 } : current);
            return;
        }

        const findScrollParent = (node: HTMLElement | null): HTMLElement | Window => {
            let current = node?.parentElement ?? null;
            while (current) {
                const styles = window.getComputedStyle(current);
                const overflowY = styles.overflowY;
                const isScrollable = (overflowY === 'auto' || overflowY === 'scroll' || overflowY === 'overlay')
                    && current.scrollHeight > current.clientHeight + 4;
                if (isScrollable) {
                    return current;
                }
                current = current.parentElement;
            }
            return window;
        };

        const scrollParent = findScrollParent(section);
        const updateOverlay = () => {
            const tableRect = table.getBoundingClientRect();
            const theadRect = thead.getBoundingClientRect();
            const headerHeight = theadRect.height || 40;
            const containerTop = scrollParent === window ? 0 : (scrollParent as HTMLElement).getBoundingClientRect().top;
            const shouldShow =
                tableRect.top <= containerTop &&
                tableRect.bottom > containerTop + headerHeight + 8;

            setOverlayHeader({
                visible: shouldShow,
                top: containerTop,
                left: tableRect.left,
                width: tableRect.width
            });
        };

        updateOverlay();
        const handleScrollOrResize = () => updateOverlay();

        if (scrollParent === window) {
            window.addEventListener('scroll', handleScrollOrResize, { passive: true });
        } else {
            scrollParent.addEventListener('scroll', handleScrollOrResize, { passive: true });
        }
        window.addEventListener('resize', handleScrollOrResize);

        return () => {
            if (scrollParent === window) {
                window.removeEventListener('scroll', handleScrollOrResize);
            } else {
                scrollParent.removeEventListener('scroll', handleScrollOrResize);
            }
            window.removeEventListener('resize', handleScrollOrResize);
        };
    }, [comparisonName, currentPage, pageSize, filteredData.length]);

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
                description: `Up-regulated genes from ${comparisonName}`,
                organism: 'arabidopsis',
                provider
            });
            setGOAnalysisResult(result);
        } catch {
            // GO analysis modal stays open and reflects the failed state from the API layer.
        } finally {
            setGOLoading(false);
            setActionMenuOpen(false);
        }
    };

    // Handle Download
    const handleDownload = useCallback(() => {
        if (!degResults?.data) return;

        // 선택된 유전자가 있으면 선택된 것만, 없으면 현재 페이지 전체
        const dataToDownload = selectedGenes.size > 0
            ? degResults.data.filter(gene => selectedGenes.has(gene.GeneID))
            : degResults.data;

        if (dataToDownload.length === 0) {
            alert('No data to download');
            return;
        }

        // TSV 형식으로 데이터 생성
        const headers = ['GeneID', 'GeneSymbol', 'logFC', 'logCPM', 'PValue', 'FDR'];
        const rows = [headers.join('\t')];

        dataToDownload.forEach(gene => {
            const row = [
                gene.GeneID,
                gene.GeneSymbol,
                gene.logFC?.toFixed(3) || '',
                gene.logCPM?.toFixed(3) || '',
                gene.PValue?.toExponential(2) || '',
                gene.FDR?.toExponential(2) || ''
            ];
            rows.push(row.join('\t'));
        });

        const tsvContent = rows.join('\n');
        const blob = new Blob([tsvContent], { type: 'text/tab-separated-values;charset=utf-8;' });
        const url = URL.createObjectURL(blob);

        // 파일명 생성
        const timestamp = new Date().toISOString().slice(0, 10);
        const selectionType = selectedGenes.size > 0 ? `selected_${selectedGenes.size}` : 'page';
        const filename = `${comparisonName}_up_regulated_${selectionType}_${timestamp}.tsv`;

        // 다운로드 트리거
        const link = document.createElement('a');
        link.href = url;
        link.download = filename;
        link.click();

        URL.revokeObjectURL(url);
    }, [degResults, selectedGenes, comparisonName]);

    return (
        <div ref={matrixSectionRef} className="h-full">
            <div className="mb-3 flex flex-wrap items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                <label className="flex items-center gap-2 text-sm font-medium text-slate-700">
                    <input
                        type="checkbox"
                        checked={lowExpressionFilterDraft.enabled}
                        onChange={(e) => handleLowExpressionToggle(e.target.checked)}
                        className="h-4 w-4 rounded border-slate-300 text-primary focus:ring-primary"
                    />
                    Low expression filter
                </label>
                <select
                    value={lowExpressionFilterDraft.preset}
                    onChange={(e) => handleLowExpressionPresetChange(e.target.value as LowExpressionPreset)}
                    disabled={!lowExpressionFilterDraft.enabled}
                    className="rounded border border-slate-300 bg-white px-2 py-1 text-sm focus:border-primary focus:ring-primary disabled:cursor-not-allowed disabled:bg-slate-100"
                >
                    <option value="relaxed">Relaxed</option>
                    <option value="standard">Standard</option>
                    <option value="strict">Strict</option>
                    <option value="custom">Custom</option>
                </select>
                {lowExpressionFilterDraft.preset === 'custom' && (
                    <>
                        <label className="flex items-center gap-1 text-sm text-slate-600">
                            TMM
                            <input
                                type="number"
                                min="0"
                                step="0.1"
                                value={lowExpressionFilterDraft.minTmm}
                                onChange={(e) => setLowExpressionFilterDraft(prev => ({ ...prev, minTmm: e.target.value }))}
                                disabled={!lowExpressionFilterDraft.enabled}
                                className="w-20 rounded border border-slate-300 px-2 py-1 text-sm focus:border-primary focus:ring-primary disabled:cursor-not-allowed disabled:bg-slate-100"
                            />
                        </label>
                        <label className="flex items-center gap-1 text-sm text-slate-600">
                            Samples %
                            <input
                                type="number"
                                min="0"
                                max="100"
                                step="1"
                                value={lowExpressionFilterDraft.minSamplePct}
                                onChange={(e) => setLowExpressionFilterDraft(prev => ({ ...prev, minSamplePct: e.target.value }))}
                                disabled={!lowExpressionFilterDraft.enabled}
                                className="w-20 rounded border border-slate-300 px-2 py-1 text-sm focus:border-primary focus:ring-primary disabled:cursor-not-allowed disabled:bg-slate-100"
                            />
                        </label>
                    </>
                )}
                {lowExpressionFilterDraft.enabled && (
                    <span className="rounded-full bg-white px-2 py-1 text-xs text-slate-600 border border-slate-200">
                        TMM ≥ {resolvedDraftLowExpressionFilter.minTmm} in ≥ {resolvedDraftLowExpressionFilter.minSamplePct}% samples
                    </span>
                )}
                <button
                    type="button"
                    onClick={handleApplyLowExpressionFilter}
                    disabled={loading || !hasPendingLowExpressionChanges}
                    className="rounded bg-primary px-3 py-1 text-sm font-medium text-white hover:bg-primary-dark disabled:cursor-not-allowed disabled:bg-slate-300"
                >
                    Apply
                </button>
            </div>

            {/* Search Bar */}
            <div className="flex flex-wrap items-center gap-4 mb-4">
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
                    disabled={loading}
                    className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed font-medium text-sm"
                >
                    Search
                </button>
                {activeSearch && (
                    <button
                        onClick={handleClearSearch}
                        disabled={loading}
                        className="px-4 py-2 bg-slate-200 text-slate-700 rounded-lg hover:bg-slate-300 disabled:opacity-50 disabled:cursor-not-allowed font-medium text-sm"
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
                        analyzeButtonClassName="px-4 py-2 text-sm font-semibold bg-primary text-white rounded-lg hover:bg-primary-dark disabled:bg-slate-300 disabled:cursor-not-allowed flex items-center"
                        toolbarClassName="contents"
                        leftGroupClassName="contents"
                        rightGroupClassName="contents"
                    />
                <button
                    onClick={handleDownload}
                    disabled={!degResults?.data || degResults.data.length === 0}
                    className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed font-medium text-sm flex items-center"
                >
                    <svg className="h-4 w-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                    </svg>
                    Download {selectedGenes.size > 0 ? `(${selectedGenes.size})` : ''}
                </button>
                <div className="flex-1"></div>
                {/* Pagination - Inline */}
                {degResults && degResults.total > 0 && (
                    <div className="flex items-center space-x-4">
                        <div className="flex items-center space-x-2">
                            <span className="text-sm text-slate-600">Rows per page:</span>
                            <select
                                value={pageSize}
                                onChange={(e) => handlePageSizeChange(Number(e.target.value))}
                                className="text-sm border border-slate-300 rounded px-2 py-1 focus:ring-1 focus:ring-primary focus:border-primary"
                            >
                                {[100, 500, 1000, 2000, 5000].map(size => (
                                    <option key={size} value={size}>{size}</option>
                                ))}
                            </select>
                        </div>
                        <div className="text-sm text-slate-600">
                            {((currentPage - 1) * pageSize + 1)}-{Math.min(currentPage * pageSize, degResults.total)} of {degResults.total.toLocaleString()}
                        </div>
                        <div className="flex items-center space-x-2">
                            <button
                                onClick={() => handlePageChange(currentPage - 1)}
                                disabled={currentPage === 1}
                                className="px-3 py-1 rounded border border-slate-300 text-sm disabled:opacity-50 disabled:cursor-not-allowed hover:bg-slate-50"
                            >
                                Previous
                            </button>

                            {/* Page Numbers with Ellipsis (starting from 3 pages) */}
                            {(() => {
                                const totalPages = Math.ceil(degResults.total / pageSize);
                                const pages: (number | string)[] = [];
                                const showEllipsis = totalPages > 3;

                                if (!showEllipsis) {
                                    // Show all pages if 3 or fewer
                                    for (let i = 1; i <= totalPages; i++) {
                                        pages.push(i);
                                    }
                                } else {
                                    // Show with ellipsis for 4+ pages
                                    if (currentPage <= 2) {
                                        for (let i = 1; i <= Math.min(3, totalPages); i++) pages.push(i);
                                        if (totalPages > 3) {
                                            pages.push('...');
                                            pages.push(totalPages);
                                        }
                                    } else if (currentPage >= totalPages - 1) {
                                        pages.push(1);
                                        pages.push('...');
                                        for (let i = Math.max(totalPages - 2, 2); i <= totalPages; i++) pages.push(i);
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

                                return pages.map((page, idx) => (
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
                                ));
                            })()}

                            <button
                                onClick={() => handlePageChange(currentPage + 1)}
                                disabled={currentPage === Math.ceil(degResults.total / pageSize)}
                                className="px-3 py-1 rounded border border-slate-300 text-sm disabled:opacity-50 disabled:cursor-not-allowed hover:bg-slate-50"
                            >
                                Next
                            </button>
                        </div>
                    </div>
                )}
            </div>

            {/* Table */}
            <div ref={matrixTableWrapperRef} className="relative" style={{ overflowX: 'auto', overflowY: 'visible' }}>
                <table ref={matrixTableRef} className="data-table" style={{ position: 'relative', width: '100%', tableLayout: 'fixed' }}>
                    {matrixColGroup}
                    <thead ref={matrixTheadRef}>
                        {matrixHeaderRow}
                    </thead>
                    <tbody className="divide-y divide-slate-200">
                        {filteredData.map((item) => (
                            <tr key={item.gene} className="table-row">
                                <td
                                    className="p-2"
                                    style={{
                                        position: 'sticky',
                                        left: 0,
                                        zIndex: 20,
                                        width: `${matrixColumnWidths.select}px`,
                                        backgroundColor: 'white',
                                        boxShadow: '2px 0 4px rgba(0,0,0,0.05)'
                                    }}
                                >
                                    <input
                                        type="checkbox"
                                        className="h-4 w-4 rounded border-slate-300 text-primary focus:ring-primary"
                                        checked={selectedGenes.has(item.gene)}
                                        onChange={() => handleSelectOne(item.gene)}
                                    />
                                </td>
                                <td
                                    className="px-2 py-2 whitespace-nowrap text-sm font-medium text-slate-900 cursor-help"
                                    style={{
                                        position: 'sticky',
                                        left: `${matrixStickyOffsets.geneId}px`,
                                        zIndex: 20,
                                        backgroundColor: 'white',
                                        boxShadow: '2px 0 4px rgba(0,0,0,0.05)',
                                        minWidth: `${matrixColumnWidths.geneId}px`
                                    }}
                                    title={item.gene_description as string || 'No description available'}
                                >
                                    {item.gene}
                                </td>
                                <td
                                    className="px-2 py-2 whitespace-nowrap text-sm text-slate-700"
                                    style={{
                                        position: 'sticky',
                                        left: `${matrixStickyOffsets.geneSymbol}px`,
                                        zIndex: 20,
                                        backgroundColor: 'white',
                                        boxShadow: '2px 0 4px rgba(0,0,0,0.05)',
                                        minWidth: `${matrixColumnWidths.geneSymbol}px`
                                    }}
                                >
                                    {item.gene_symbol && item.gene_symbol !== item.gene ? (
                                        <span className="italic">{item.gene_symbol}</span>
                                    ) : (
                                        <span className="text-slate-500">{item.gene}</span>
                                    )}
                                </td>
                                <td className="px-2 py-2">
                                    {(() => {
                                        if (tmmData && sampleNames.length > 0 && tmmData[item.gene]) {
                                            const values = tmmData[item.gene];
                                            return (
                                                <MiniHeatmap
                                                    values={values}
                                                    samples={sampleNames}
                                                    width={Math.min(sampleNames.length * 12, matrixColumnWidths.pattern)}
                                                    height={20}
                                                />
                                            );
                                        }
                                        return <span className="text-xs text-slate-400">N/A</span>;
                                    })()}
                                </td>
                                <td className="px-2 py-2 whitespace-nowrap text-sm text-slate-600">
                                    {item.logFC?.toFixed(3)}
                                </td>
                                <td className="px-2 py-2 whitespace-nowrap text-sm text-slate-600">
                                    {item.logCPM?.toFixed(3)}
                                </td>
                                <td className="px-2 py-2 whitespace-nowrap text-sm text-slate-600">
                                    {item.PValue?.toExponential(2)}
                                </td>
                                <td className="px-2 py-2 whitespace-nowrap text-sm text-slate-600">
                                    {item.FDR?.toExponential(2)}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>

            {/* No Results Message */}
            {!loading && filteredData.length === 0 && (
                <div className="text-center py-12">
                    <div className="text-slate-400 mb-4">
                        <svg className="w-16 h-16 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                        </svg>
                    </div>
                    <h4 className="text-lg font-medium text-slate-900 mb-2">No up-regulated genes found</h4>
                    <p className="text-slate-500">
                        {activeSearch
                            ? `No genes match your search criteria "${activeSearch}"`
                            : 'Try adjusting your filters or search criteria'}
                    </p>
                </div>
            )}

            {/* Loading Overlay */}
            {loading && (
                <div className="absolute inset-0 bg-white bg-opacity-75 flex items-center justify-center z-40">
                    <div className="text-center">
                        {showLowExpressionLoadingHint ? (
                            <div className="w-[360px] max-w-full rounded-lg border border-slate-200 bg-white px-5 py-4 shadow-sm">
                                <p className="text-slate-700 font-medium">
                                    Applying low-expression filter and recalculating DEG results...
                                </p>
                                <p className="mt-2 text-sm text-slate-500">
                                    This may take several minutes depending on sample count.
                                </p>
                                <div className="mt-4">
                                    <div className="flex items-center justify-between text-sm text-slate-600 mb-2">
                                        <span>{lowExprProgress?.message || 'Preparing analysis...'}</span>
                                        <span>{progressPercent}%</span>
                                    </div>
                                    <div className="w-full bg-slate-200 rounded-full h-2 overflow-hidden">
                                        <div
                                            className="bg-blue-600 h-2 rounded-full transition-all duration-300 ease-out"
                                            style={{ width: `${progressPercent}%` }}
                                        />
                                    </div>
                                </div>
                                <div className="mt-3 text-sm text-slate-600">
                                    {lowExprProgress?.total_contrasts && lowExprProgress.total_contrasts > 0 ? (
                                        <span>
                                            Running DEG contrasts ({Math.min(lowExprProgress.current_contrast || 0, lowExprProgress.total_contrasts)}/{lowExprProgress.total_contrasts})
                                        </span>
                                    ) : (
                                        <span>Preparing analysis inputs...</span>
                                    )}
                                </div>
                                <p className="mt-1 text-xs text-slate-500">
                                    Estimated progress based on completed contrasts.
                                </p>
                                {!isLowExprRecalculationRunning && (
                                    <p className="mt-2 text-xs text-slate-400">
                                        Finalizing response...
                                    </p>
                                )}
                            </div>
                        ) : (
                            <>
                                <div className="animate-spin rounded-full h-12 w-12 border-b-4 border-blue-600 mx-auto mb-4"></div>
                                <p className="text-slate-600">Loading results...</p>
                            </>
                        )}
                    </div>
                </div>
            )}

            {overlayHeader.visible && typeof document !== 'undefined' && createPortal(
                <div
                    className="fixed z-[9998]"
                    style={{ top: overlayHeader.top, left: overlayHeader.left, width: overlayHeader.width }}
                >
                    <div className="overflow-hidden rounded-t-xl border border-slate-200 bg-slate-50 shadow-sm">
                        <table className="data-table" style={{ width: '100%', tableLayout: 'fixed' }}>
                            {matrixColGroup}
                            <thead>{matrixHeaderRow}</thead>
                        </table>
                    </div>
                </div>,
                document.body
            )}

            {showScrollToTopButton && typeof document !== 'undefined' && createPortal(
                <button
                    type="button"
                    onClick={handleScrollToTop}
                    className="scroll-to-top-button fixed bottom-6 right-6 z-[9999] inline-flex h-12 w-12 items-center justify-center rounded-full transition-transform hover:scale-105"
                    title="Scroll to top"
                    aria-label="Scroll to top"
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
                comparisonName={comparisonName}
                toolName={toolName}
            />

            {/* Heatmap Analysis Modal */}
            <HeatmapAnalysisModal
                isOpen={analysisHeatmapOpen}
                onClose={closeAnalysisHeatmap}
                workbenchId={workbenchId}
                selectedGenes={Array.from(selectedGenes)}
                comparisonName={comparisonName}
                toolName={toolName}
            />

            {/* KEGG Pathway Modal */}
            <KEGGPathwayModal
                isOpen={analysisKEGGOpen}
                onClose={closeAnalysisKEGG}
                workbenchId={workbenchId}
                selectedGenes={Array.from(selectedGenes)}
                comparisonName={comparisonName}
                toolName={toolName}
            />
        </div>
    );
};

export default WorkbenchDetailDEGMatrixUp;
