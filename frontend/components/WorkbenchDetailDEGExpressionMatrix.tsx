import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { createPortal } from 'react-dom';
import MiniHeatmap from './MiniHeatmap';
import GOAnalysisModal from './GOAnalysisModal';
import GOProviderSubmenu from './GOProviderSubmenu';
import CopyGeneListMenuItem from './CopyGeneListMenuItem';
import HeatmapAnalysisModal from './HeatmapAnalysisModal';
import KEGGPathwayModal from './KEGGPathwayModal';
import VennSetMenu, { VennSetSummary } from './VennSetMenu';
import SelectableGeneTableShell from './SelectableGeneTableShell';
import { apiService } from '../services/api';
import { useGeneAnalysisActions } from '../hooks/useGeneAnalysisActions';

// ========================================
// Type Definitions
// ========================================

interface WorkbenchDetailDEGExpressionMatrixProps {
    workbenchId: number;
    selectedGenes: Set<string>;
    onSelectionChange: (genes: Set<string>) => void;
    onAnalysisRequest: (type: string) => void;
    showComingSoon: () => void;
    onNavigateToVennDiagram: (genes: string[], targetSetIndex?: number) => void;
    vennSetSummaries?: VennSetSummary[];
}

interface ExpressionMatrixResponse {
    data: Array<{
        GeneID: string;
        GeneSymbol: string;
        GeneDescription?: string;
        [sample: string]: number | string;
    }>;
    samples: string[];
    total: number;
    page: number;
    limit: number;
    p_value: number;
    fold_change: number;
    file_generated: boolean;
}

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
            const toolbarHeight = 180; // 입력 필드 영역 포함

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
    const pageSizeOptions = [100, 500, 1000];

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

const WorkbenchDetailDEGExpressionMatrix: React.FC<WorkbenchDetailDEGExpressionMatrixProps> = ({
    workbenchId,
    selectedGenes,
    onSelectionChange,
    onAnalysisRequest,
    showComingSoon,
    onNavigateToVennDiagram,
    vennSetSummaries
}) => {
    const [matrixData, setMatrixData] = useState<ExpressionMatrixResponse | null>(null);
    const [isLoading, setIsLoading] = useState(false);
    const [isGenerating, setIsGenerating] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // 파라미터 상태
    const [pValue, setPValue] = useState('0.01');
    const [foldChange, setFoldChange] = useState('2');

    // 검색 상태
    const [searchInput, setSearchInput] = useState('');
    const [activeSearch, setActiveSearch] = useState('');

    // 페이지네이션 상태
    const [currentPage, setCurrentPage] = useState(1);
    const [pageSize, setPageSize] = useState(500);

    // Analysis 메뉴 상태
    const [isActionMenuOpen, setActionMenuOpen] = useState(false);
    const actionMenuRef = useRef<HTMLDivElement>(null);

    // GO Analysis 모달 상태
    const [isGOModalOpen, setGOModalOpen] = useState(false);
    const [goAnalysisResult, setGOAnalysisResult] = useState<any>(null);
    const [isGOLoading, setGOLoading] = useState(false);

    // Heatmap Analysis 모달 상태
    const [isHeatmapModalOpen, setHeatmapModalOpen] = useState(false);

    // KEGG Pathway 모달 상태
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
        description: `Expression Matrix (P=${pValue}, C=${foldChange})`,
    });

    const [selectAllState, setSelectAllState] = useState<0 | 1 | 2>(0);
    const [showScrollToTopButton, setShowScrollToTopButton] = useState(false);
    const [overlayHeader, setOverlayHeader] = useState<{ visible: boolean; top: number; left: number; width: number; tableWidth: number; scrollLeft: number; height: number }>({
        visible: false,
        top: 0,
        left: 0,
        width: 0,
        tableWidth: 0,
        scrollLeft: 0,
        height: 0
    });
    const [topScrollbarWidth, setTopScrollbarWidth] = useState(0);
    const scrollTargetRef = useRef<HTMLElement | Window | null>(null);
    const tableSectionRef = useRef<HTMLDivElement | null>(null);
    const topScrollbarRef = useRef<HTMLDivElement | null>(null);
    const floatingTopScrollbarRef = useRef<HTMLDivElement | null>(null);
    const tableWrapperRef = useRef<HTMLDivElement | null>(null);
    const tableRef = useRef<HTMLTableElement | null>(null);
    const tableTheadRef = useRef<HTMLTableSectionElement | null>(null);

    // Expression Matrix 데이터 로드
    const loadExpressionMatrix = useCallback(async (page: number = 1, limit: number = 500, search: string = '') => {
        try {
            setIsLoading(true);
            setError(null);

            const params = new URLSearchParams({
                p_value: pValue,
                fold_change: foldChange,
                page: page.toString(),
                limit: limit.toString()
            });

            if (search) {
                params.append('search', search);
            }

            const response = await fetch(
                `/api/workbenches/${workbenchId}/deg/expression-matrix?${params}`,
                { credentials: 'include' }
            );

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || 'Failed to load expression matrix');
            }

            const data: ExpressionMatrixResponse = await response.json();
            setMatrixData(data);
        } catch (err) {
            console.error('Failed to load expression matrix:', err);
            setError(err instanceof Error ? err.message : 'Failed to load expression matrix');
        } finally {
            setIsLoading(false);
            setIsGenerating(false); // 항상 생성 상태 해제
        }
    }, [workbenchId, pValue, foldChange]);

    // 초기 로드 시 자동으로 디폴트 값으로 API 호출
    useEffect(() => {
        loadExpressionMatrix(1, pageSize);
    }, [workbenchId]); // workbenchId 변경 시에만 재실행

    // 외부 클릭 감지 (Analysis 메뉴)
    useEffect(() => {
        const handleClickOutside = (event: MouseEvent) => {
            if (actionMenuRef.current && !actionMenuRef.current.contains(event.target as Node)) {
                setActionMenuOpen(false);
            }
        };
        document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, []);

    // Generate 버튼 클릭
    const handleGenerate = useCallback(() => {
        setIsGenerating(true);
        setCurrentPage(1);
        setSearchInput(''); // 검색 입력 초기화
        setActiveSearch(''); // 검색 상태 초기화
        setSelectAllState(0);
        onSelectionChange(new Set()); // 선택 초기화
        loadExpressionMatrix(1, pageSize, '');
    }, [loadExpressionMatrix, pageSize, onSelectionChange]);

    // 검색 핸들러
    const handleSearch = () => {
        const searchValue = searchInput.trim();
        if (searchValue) {
            setActiveSearch(searchValue);
            setCurrentPage(1);
            setSelectAllState(0);
            onSelectionChange(new Set()); // 선택 초기화
            loadExpressionMatrix(1, pageSize, searchValue);
        }
    };

    const handleClearSearch = () => {
        setSearchInput('');
        setActiveSearch('');
        setCurrentPage(1);
        setSelectAllState(0);
        onSelectionChange(new Set()); // 선택 초기화
        loadExpressionMatrix(1, pageSize, '');
    };

    // 페이지 변경
    const handlePageChange = useCallback((newPage: number) => {
        setCurrentPage(newPage);
        setSelectAllState(0);
        loadExpressionMatrix(newPage, pageSize, activeSearch);
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }, [loadExpressionMatrix, pageSize, activeSearch]);

    // 페이지 크기 변경
    const handlePageSizeChange = useCallback((newSize: number) => {
        setPageSize(newSize);
        setCurrentPage(1);
        setSelectAllState(0);
        onSelectionChange(new Set()); // 선택 초기화
        loadExpressionMatrix(1, newSize, activeSearch);
    }, [loadExpressionMatrix, activeSearch, onSelectionChange]);

    // 테이블 데이터 메모이제이션 (핸들러보다 먼저 정의)
    const filteredData = useMemo(() => {
        if (!matrixData?.data || matrixData.data.length === 0) {
            return [];
        }

        return matrixData.data.map(gene => {
            const row: any = {
                gene: gene.GeneID,
                gene_symbol: gene.GeneSymbol,
                gene_description: gene.GeneDescription || 'No description available'
            };
            matrixData.samples.forEach(sample => {
                row[sample] = gene[sample];
            });
            return row;
        });
    }, [matrixData]);

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

    const tableColGroup = (
        <colgroup>
            <col style={{ width: `${tableColumnWidths.select}px` }} />
            <col style={{ width: `${tableColumnWidths.geneId}px` }} />
            <col style={{ width: `${tableColumnWidths.geneSymbol}px` }} />
            <col style={{ width: `${tableColumnWidths.pattern}px` }} />
            {(matrixData?.samples || []).map(sample => (
                <col key={sample} style={{ width: `${tableColumnWidths.sample}px` }} />
            ))}
        </colgroup>
    );

    // Fetch all gene IDs across all pages
    const fetchAllGeneIds = useCallback(async (): Promise<string[]> => {
        const total = matrixData?.total || 0;
        const params = new URLSearchParams({
            p_value: pValue,
            fold_change: foldChange,
            page: '1',
            limit: total.toString()
        });
        if (activeSearch) params.append('search', activeSearch);
        try {
            const response = await fetch(
                `/api/workbenches/${workbenchId}/deg/expression-matrix?${params}`,
                { credentials: 'include' }
            );
            if (response.ok) {
                const data = await response.json();
                return (data.data || []).map((g: any) => g.GeneID);
            }
        } catch (error) {
            console.error('Failed to fetch all gene IDs:', error);
        }
        return [];
    }, [workbenchId, pValue, foldChange, matrixData?.total, activeSearch]);

    // 3-state Select All cycle handler
    const handleSelectAllCycle = useCallback(async () => {
        if (selectAllState === 0) {
            // State 0 → 1: Select current page
            const newSelected = new Set(selectedGenes);
            filteredData.forEach(item => newSelected.add(item.gene as string));
            onSelectionChange(newSelected);
            setSelectAllState(1);
        } else if (selectAllState === 1) {
            // State 1 → 2: Select all pages via API
            setIsLoading(true);
            const allIds = await fetchAllGeneIds();
            onSelectionChange(new Set<string>(allIds));
            setSelectAllState(2);
            setIsLoading(false);
        } else {
            // State 2 → 0: Deselect all
            onSelectionChange(new Set());
            setSelectAllState(0);
        }
    }, [selectAllState, filteredData, selectedGenes, onSelectionChange, fetchAllGeneIds]);

    // 유전자 선택 핸들러
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

    const handleScrollToTop = () => {
        const target = scrollTargetRef.current;
        if (target && target !== window) {
            target.scrollTo({ top: 0, behavior: 'smooth' });
            return;
        }
        window.scrollTo({ top: 0, behavior: 'smooth' });
    };

    const tableHeaderRow = (
        <tr>
            <th
                className="p-4 text-left text-xs font-bold text-slate-600 uppercase tracking-wider w-12"
                style={{
                    width: `${tableColumnWidths.select}px`,
                    backgroundColor: 'rgb(248 250 252)',
                    position: 'sticky',
                    left: 0,
                    zIndex: 20,
                    boxShadow: '2px 0 4px rgba(0,0,0,0.05)'
                }}
            >
                <button
                    onClick={handleSelectAllCycle}
                    className="flex items-center justify-center w-5 h-5 hover:opacity-75 transition-opacity"
                    title={
                        selectAllState === 0 ? 'Select current page' :
                        selectAllState === 1 ? 'Select all pages' :
                        'Deselect all'
                    }
                >
                    <svg viewBox="0 0 16 16" className="w-4 h-4" fill="none" xmlns="http://www.w3.org/2000/svg">
                        {selectAllState === 0 && (
                            <rect x="1" y="1" width="14" height="14" rx="2" stroke="#9CA3AF" strokeWidth="1.5"/>
                        )}
                        {selectAllState === 1 && (
                            <>
                                <rect x="1" y="1" width="14" height="14" rx="2" stroke="#3B82F6" strokeWidth="1.5"/>
                                <path d="M4 8.5l2.5 2.5 5-5.5" stroke="#3B82F6" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                            </>
                        )}
                        {selectAllState === 2 && (
                            <>
                                <rect x="1" y="1" width="14" height="14" rx="2" fill="#1D4ED8" stroke="#1D4ED8" strokeWidth="1.5"/>
                                <path d="M4 8.5l2.5 2.5 5-5.5" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                            </>
                        )}
                    </svg>
                </button>
            </th>
            <th
                className="px-3 py-3 text-left text-xs font-bold text-slate-600 uppercase tracking-wider"
                style={{
                    width: `${tableColumnWidths.geneId}px`,
                    minWidth: `${tableColumnWidths.geneId}px`,
                    backgroundColor: 'rgb(248 250 252)',
                    position: 'sticky',
                    left: `${tableStickyOffsets.geneId}px`,
                    zIndex: 20,
                    boxShadow: '2px 0 4px rgba(0,0,0,0.05)'
                }}
            >
                Gene ID
            </th>
            <th
                className="px-3 py-3 text-left text-xs font-bold text-slate-600 uppercase tracking-wider"
                style={{
                    width: `${tableColumnWidths.geneSymbol}px`,
                    minWidth: `${tableColumnWidths.geneSymbol}px`,
                    backgroundColor: 'rgb(248 250 252)',
                    position: 'sticky',
                    left: `${tableStickyOffsets.geneSymbol}px`,
                    zIndex: 20,
                    boxShadow: '2px 0 4px rgba(0,0,0,0.05)'
                }}
            >
                Gene Symbol
            </th>
            <th
                className="px-3 py-3 text-center text-xs font-bold text-slate-600 uppercase tracking-wider"
                style={{
                    width: `${tableColumnWidths.pattern}px`,
                    minWidth: `${tableColumnWidths.pattern}px`,
                    backgroundColor: 'rgb(248 250 252)',
                    position: 'sticky',
                    left: `${tableStickyOffsets.pattern}px`,
                    zIndex: 20,
                    boxShadow: '2px 0 4px rgba(0,0,0,0.05)'
                }}
            >
                Expression Pattern
            </th>
            {(matrixData?.samples || []).map(name => (
                <th
                    key={name}
                    className="px-3 py-3 text-left text-xs font-bold text-slate-600 uppercase tracking-wider"
                    style={{ width: `${tableColumnWidths.sample}px`, minWidth: `${tableColumnWidths.sample}px`, backgroundColor: 'rgb(248 250 252)' }}
                >
                    {name}
                </th>
            ))}
        </tr>
    );

    useEffect(() => {
        const section = tableSectionRef.current;
        if (!section) return;

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
            setShowScrollToTopButton(scrollTop > 320);
        };

        updateVisibility();
        scrollTarget.addEventListener('scroll', updateVisibility, { passive: true });
        return () => {
            scrollTarget.removeEventListener('scroll', updateVisibility);
            if (scrollTargetRef.current === scrollTarget) {
                scrollTargetRef.current = null;
            }
        };
    }, [currentPage, pageSize, filteredData.length, matrixData?.samples?.length, Boolean(matrixData), matrixData?.total, isLoading, isGenerating, error]);

    useEffect(() => {
        const topScrollbar = topScrollbarRef.current;
        const floatingScrollbar = floatingTopScrollbarRef.current;
        const tableWrapper = tableWrapperRef.current;
        const table = tableRef.current;

        if (!topScrollbar || !tableWrapper || !table) {
            setTopScrollbarWidth(0);
            return;
        }

        let syncingFromTop = false;
        let syncingFromFloating = false;
        let syncingFromTable = false;

        const syncMetrics = () => {
            setTopScrollbarWidth(table.scrollWidth);
        };

        const handleTopScroll = () => {
            if (syncingFromTable || syncingFromFloating) return;
            syncingFromTop = true;
            tableWrapper.scrollLeft = topScrollbar.scrollLeft;
            if (floatingScrollbar) {
                floatingScrollbar.scrollLeft = topScrollbar.scrollLeft;
            }
            requestAnimationFrame(() => {
                syncingFromTop = false;
            });
        };

        const handleFloatingScroll = () => {
            if (!floatingScrollbar || syncingFromTable || syncingFromTop) return;
            syncingFromFloating = true;
            tableWrapper.scrollLeft = floatingScrollbar.scrollLeft;
            topScrollbar.scrollLeft = floatingScrollbar.scrollLeft;
            requestAnimationFrame(() => {
                syncingFromFloating = false;
            });
        };

        const handleTableScroll = () => {
            if (syncingFromTop || syncingFromFloating) return;
            syncingFromTable = true;
            topScrollbar.scrollLeft = tableWrapper.scrollLeft;
            if (floatingScrollbar) {
                floatingScrollbar.scrollLeft = tableWrapper.scrollLeft;
            }
            requestAnimationFrame(() => {
                syncingFromTable = false;
            });
        };

        syncMetrics();
        topScrollbar.scrollLeft = tableWrapper.scrollLeft;
        if (floatingScrollbar) {
            floatingScrollbar.scrollLeft = tableWrapper.scrollLeft;
        }

        topScrollbar.addEventListener('scroll', handleTopScroll, { passive: true });
        floatingScrollbar?.addEventListener('scroll', handleFloatingScroll, { passive: true });
        tableWrapper.addEventListener('scroll', handleTableScroll, { passive: true });
        window.addEventListener('resize', syncMetrics);

        return () => {
            topScrollbar.removeEventListener('scroll', handleTopScroll);
            floatingScrollbar?.removeEventListener('scroll', handleFloatingScroll);
            tableWrapper.removeEventListener('scroll', handleTableScroll);
            window.removeEventListener('resize', syncMetrics);
        };
    }, [currentPage, pageSize, filteredData.length, matrixData?.samples?.length, Boolean(matrixData), matrixData?.total, isLoading, isGenerating, error, overlayHeader.visible]);

    useEffect(() => {
        const section = tableSectionRef.current;
        const table = tableRef.current;
        const thead = tableTheadRef.current;

        if (!section || !table || !thead || filteredData.length === 0) {
            setOverlayHeader(current => current.visible ? { visible: false, top: 0, left: 0, width: 0, tableWidth: 0, scrollLeft: 0, height: 0 } : current);
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
        const horizontalScrollTarget = tableWrapperRef.current;
        const updateOverlay = () => {
            const tableRect = table.getBoundingClientRect();
            const wrapperRect = (horizontalScrollTarget ?? table).getBoundingClientRect();
            const theadRect = thead.getBoundingClientRect();
            const headerHeight = theadRect.height || 40;
            const containerTop = scrollParent === window ? 0 : (scrollParent as HTMLElement).getBoundingClientRect().top;
            const shouldShow =
                tableRect.top <= containerTop &&
                tableRect.bottom > containerTop + headerHeight + 8;

            setOverlayHeader({
                visible: shouldShow,
                top: containerTop,
                left: wrapperRect.left,
                width: wrapperRect.width,
                tableWidth: tableRect.width,
                scrollLeft: horizontalScrollTarget?.scrollLeft ?? 0,
                height: headerHeight
            });
        };

        updateOverlay();
        const handleScrollOrResize = () => updateOverlay();

        if (scrollParent === window) {
            window.addEventListener('scroll', handleScrollOrResize, { passive: true });
        } else {
            scrollParent.addEventListener('scroll', handleScrollOrResize, { passive: true });
        }
        horizontalScrollTarget?.addEventListener('scroll', handleScrollOrResize, { passive: true });
        window.addEventListener('resize', handleScrollOrResize);

        return () => {
            if (scrollParent === window) {
                window.removeEventListener('scroll', handleScrollOrResize);
            } else {
                scrollParent.removeEventListener('scroll', handleScrollOrResize);
            }
            horizontalScrollTarget?.removeEventListener('scroll', handleScrollOrResize);
            window.removeEventListener('resize', handleScrollOrResize);
        };
    }, [currentPage, pageSize, filteredData.length, matrixData?.samples?.length, Boolean(matrixData), matrixData?.total, isLoading, isGenerating, error]);

    // GO Analysis 핸들러
    const handleGOAnalysis = useCallback(async (provider: 'david' | 'gprofiler') => {
        const genes = Array.from(selectedGenes);

        setGOLoading(true);
        setGOModalOpen(true);

        try {
            const result = await apiService.runGOEnrichment(workbenchId, {
                genes: genes,
                databases: ['GO_BP', 'GO_MF', 'GO_CC'],
                p_value_cutoff: 0.05,
                description: `Expression Matrix (P=${pValue}, C=${foldChange})`,
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
    }, [selectedGenes, workbenchId, pValue, foldChange]);

    // 다운로드 핸들러
    const handleDownload = useCallback(async () => {
        if (!matrixData) return;

        try {
            // 선택된 유전자 목록 준비
            const selected_genes = selectedGenes.size > 0 ? Array.from(selectedGenes) : [];

            // POST 요청으로 전체 또는 선택된 유전자만 다운로드
            const response = await fetch(
                `/api/workbenches/${workbenchId}/deg/expression-matrix/download`,
                {
                    method: 'POST',
                    credentials: 'include',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        p_value: matrixData.p_value,
                        fold_change: matrixData.fold_change,
                        selected_genes: selected_genes
                    })
                }
            );

            if (!response.ok) {
                throw new Error('Failed to download expression matrix');
            }

            // Blob으로 변환
            const blob = await response.blob();
            const url = URL.createObjectURL(blob);

            // 파일명 생성
            const p_str = String(matrixData.p_value).replace('.', '');
            const c_str = String(matrixData.fold_change).replace('.', '');

            let filename;
            if (selected_genes.length > 0) {
                filename = `diffExpr.P${p_str}_C${c_str}.selected_${selected_genes.length}_genes.csv`;
            } else {
                filename = `diffExpr.P${p_str}_C${c_str}.matrix.log2.centered.csv`;
            }

            // 다운로드 트리거
            const link = document.createElement('a');
            link.href = url;
            link.download = filename;
            link.click();

            URL.revokeObjectURL(url);

            // 다운로드 완료 메시지
            console.log(`✅ Downloaded: ${filename} (${selected_genes.length > 0 ? selected_genes.length : 'all'} genes)`);
        } catch (error) {
            console.error('Failed to download expression matrix:', error);
            alert('Failed to download expression matrix. Please try again.');
        }
    }, [workbenchId, matrixData, selectedGenes]);

    // 총 페이지 수 계산
    const totalPages = matrixData ? Math.ceil(matrixData.total / pageSize) : 0;

    return (
        <div ref={tableSectionRef} className="h-full flex flex-col p-6 relative">
            {/* 파라미터 입력 영역 */}
            <div className="bg-slate-50 p-4 rounded-lg border border-slate-200 mb-4">
                {/* 첫 번째 행: 필터 + 생성 버튼 */}
                <div className="flex items-end space-x-4">
                    <div className="flex-1">
                        <label className="block text-sm font-medium text-slate-700 mb-2">
                            P-value Cutoff
                        </label>
                        <input
                            type="number"
                            step="0.01"
                            min="0"
                            max="1"
                            value={pValue}
                            onChange={(e) => setPValue(e.target.value)}
                            className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-1 focus:ring-primary focus:border-primary"
                            placeholder="0.01"
                        />
                    </div>
                    <div className="flex-1">
                        <label className="block text-sm font-medium text-slate-700 mb-2">
                            Fold-change Cutoff (log2)
                        </label>
                        <input
                            type="number"
                            step="1"
                            min="0"
                            value={foldChange}
                            onChange={(e) => setFoldChange(e.target.value)}
                            className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-1 focus:ring-primary focus:border-primary"
                            placeholder="2"
                        />
                    </div>
                    <button
                        onClick={handleGenerate}
                        disabled={isLoading || isGenerating || !pValue || !foldChange}
                        className="px-6 py-2 bg-primary text-white rounded-lg hover:bg-primary-dark disabled:opacity-50 disabled:cursor-not-allowed transition-colors font-medium"
                    >
                        {isGenerating ? 'Generating...' : 'Generate Matrix'}
                    </button>
                </div>


                {matrixData && (
                    <div className="mt-3 text-sm text-slate-600">
                        <span className="font-medium">
                            Current Matrix: P={matrixData.p_value}, C={matrixData.fold_change}
                        </span>
                        {matrixData.file_generated && (
                            <span className="ml-2 text-green-600">✓ Newly generated</span>
                        )}
                    </div>
                )}
            </div>

            {/* 에러 메시지 */}
            {error && (
                <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
                    {error}
                </div>
            )}

            {/* 로딩 상태 */}
            {(isLoading || isGenerating) && (
                <div className="flex items-center justify-center h-96">
                    <div className="text-center">
                        <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-blue-100 mb-4">
                            <svg className="animate-spin h-8 w-8 text-primary" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                            </svg>
                        </div>
                        <h3 className="text-lg font-semibold text-slate-900 mb-2">
                            {isGenerating ? 'Generating Expression Matrix...' : 'Loading...'}
                        </h3>
                        <p className="text-sm text-slate-600 max-w-md">
                            {isGenerating
                                ? 'Running analyze_diff_expr.pl to generate matrix file. This may take a moment...'
                                : 'Fetching expression matrix data...'
                            }
                        </p>
                    </div>
                </div>
            )}

            {/* Toolbar with Search, Analysis, Download, and Pagination */}
            {!isLoading && !isGenerating && matrixData && (
                <div className="flex items-center gap-4 mb-4">
                        {/* Search Bar */}
                        <div className="relative">
                            <textarea
                                value={searchInput}
                                onChange={(e) => setSearchInput(e.target.value)}
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
                            disabled={isLoading}
                            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed font-medium text-sm"
                        >
                            Search
                        </button>
                        {activeSearch && (
                            <button
                                onClick={handleClearSearch}
                                disabled={isLoading}
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
                            disabled={!matrixData}
                            className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed font-medium text-sm flex items-center"
                        >
                            <svg className="h-4 w-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                            </svg>
                            Download {selectedGenes.size > 0 ? `(${selectedGenes.size})` : ''}
                        </button>
                        <div className="flex-1"></div>
                        {/* Pagination - Inline */}
                        {matrixData && matrixData.total > 0 && (
                            <div className="flex items-center space-x-4">
                                <div className="flex items-center space-x-2">
                                    <span className="text-sm text-slate-600">Rows per page:</span>
                                    <select
                                        value={pageSize}
                                        onChange={(e) => handlePageSizeChange(Number(e.target.value))}
                                        className="text-sm border border-slate-300 rounded px-2 py-1 focus:ring-1 focus:ring-primary focus:border-primary"
                                    >
                                        {[100, 500, 1000].map(size => (
                                            <option key={size} value={size}>{size}</option>
                                        ))}
                                    </select>
                                </div>
                                <div className="text-sm text-slate-600">
                                    {((currentPage - 1) * pageSize + 1)}-{Math.min(currentPage * pageSize, matrixData.total)} of {matrixData.total.toLocaleString()}
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
                                        disabled={currentPage === totalPages}
                                        className="px-3 py-1 rounded border border-slate-300 text-sm disabled:opacity-50 disabled:cursor-not-allowed hover:bg-slate-50"
                                    >
                                        Next
                                    </button>
                                </div>
                            </div>
                        )}
                </div>
            )}

            {/* 데이터 테이블 */}
            {!isLoading && !isGenerating && matrixData && (
                <div className="border border-slate-200 rounded-lg overflow-visible">
                    <div
                        ref={topScrollbarRef}
                        className="overflow-x-auto overflow-y-hidden border-b border-slate-200 bg-slate-50"
                    >
                        <div style={{ width: `${topScrollbarWidth}px`, height: '16px' }} />
                    </div>
                    <div ref={tableWrapperRef} className="relative" style={{ overflowX: 'auto', overflowY: 'visible' }}>
                        <table ref={tableRef} className="data-table" style={{ position: 'relative', width: '100%', tableLayout: 'fixed' }}>
                            {tableColGroup}
                            <thead ref={tableTheadRef}>
                                {tableHeaderRow}
                            </thead>
                            <tbody className="divide-y divide-slate-200">
                                {filteredData.length > 0 ? (
                                    filteredData.map((item) => (
                                    <tr key={item.gene as string} className="table-row">
                                        <td
                                            className="p-4"
                                            style={{
                                                position: 'sticky',
                                                left: 0,
                                                zIndex: 20,
                                                backgroundColor: 'white',
                                                boxShadow: '2px 0 4px rgba(0,0,0,0.05)'
                                            }}
                                        >
                                            <input
                                                type="checkbox"
                                                className="h-4 w-4 rounded border-slate-300 text-primary focus:ring-primary"
                                                checked={selectedGenes.has(item.gene as string)}
                                                onChange={() => handleSelectOne(item.gene as string)}
                                            />
                                        </td>
                                        <td
                                            className="px-3 py-3 whitespace-nowrap text-sm font-medium text-slate-900 cursor-help"
                                            style={{
                                                position: 'sticky',
                                                left: `${tableStickyOffsets.geneId}px`,
                                                zIndex: 20,
                                                backgroundColor: 'white',
                                                boxShadow: '2px 0 4px rgba(0,0,0,0.05)',
                                                minWidth: `${tableColumnWidths.geneId}px`
                                            }}
                                            title={item.gene_description as string || 'No description available'}
                                        >
                                            {item.gene}
                                        </td>
                                        <td
                                            className="px-3 py-3 whitespace-nowrap text-sm text-slate-700"
                                            style={{
                                                position: 'sticky',
                                                left: `${tableStickyOffsets.geneSymbol}px`,
                                                zIndex: 20,
                                                backgroundColor: 'white',
                                                boxShadow: '2px 0 4px rgba(0,0,0,0.05)',
                                                minWidth: `${tableColumnWidths.geneSymbol}px`
                                            }}
                                        >
                                            {item.gene_symbol && item.gene_symbol !== item.gene ? (
                                                <span className="italic">{item.gene_symbol}</span>
                                            ) : (
                                                <span className="text-slate-500">{item.gene}</span>
                                            )}
                                        </td>
                                        <td
                                            className="px-3 py-3"
                                            style={{
                                                position: 'sticky',
                                                left: `${tableStickyOffsets.pattern}px`,
                                                zIndex: 20,
                                                backgroundColor: 'white',
                                                boxShadow: '2px 0 4px rgba(0,0,0,0.05)',
                                                minWidth: `${tableColumnWidths.pattern}px`
                                            }}
                                        >
                                            {(() => {
                                                const samples = matrixData?.samples || [];
                                                const values = samples.map(sample => {
                                                    const value = item[sample];
                                                    return typeof value === 'number' ? value : parseFloat(value as string) || 0;
                                                });

                                                if (values.length > 0 && samples.length > 0) {
                                                    return (
                                                        <MiniHeatmap
                                                            values={values}
                                                            samples={samples}
                                                            width={Math.min(samples.length * 12, tableColumnWidths.pattern)}
                                                            height={20}
                                                        />
                                                    );
                                                } else {
                                                    return <span className="text-xs text-slate-400">N/A</span>;
                                                }
                                            })()}
                                        </td>
                                        {(matrixData?.samples || []).map(sample => (
                                            <td
                                                key={sample}
                                                className="px-3 py-3 whitespace-nowrap text-sm text-slate-600"
                                            >
                                                {typeof item[sample] === 'number'
                                                    ? item[sample].toFixed(2)
                                                    : item[sample]
                                                }
                                            </td>
                                        ))}
                                    </tr>
                                ))
                                ) : (
                                    <tr>
                                        <td colSpan={4 + (matrixData?.samples?.length || 0)} className="px-3 py-12 text-center">
                                            <div className="text-slate-400 mb-4">
                                                <svg className="w-16 h-16 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                                                </svg>
                                            </div>
                                            <h4 className="text-lg font-medium text-slate-900 mb-2">No genes found</h4>
                                            <p className="text-slate-500">
                                                {activeSearch
                                                    ? `No genes match your search criteria "${activeSearch}"`
                                                    : 'No data available for the current parameters'}
                                            </p>
                                        </td>
                                    </tr>
                                )}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

            {/* 데이터 없음 메시지 */}
            {!isLoading && !isGenerating && !matrixData && (
                <div className="flex items-center justify-center h-96">
                    <div className="text-center">
                        <div className="text-slate-400 mb-4">
                            <svg className="w-16 h-16 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                            </svg>
                        </div>
                        <h4 className="text-lg font-medium text-slate-900 mb-2">No Expression Matrix Loaded</h4>
                        <p className="text-slate-500 mb-4">Enter P-value and Fold-change parameters and click "Generate Matrix"</p>
                    </div>
                </div>
            )}

            {overlayHeader.visible && typeof document !== 'undefined' && createPortal(
                <div
                    className="fixed z-[9998]"
                    style={{ top: overlayHeader.top, left: overlayHeader.left, width: overlayHeader.width }}
                >
                    <div
                        ref={floatingTopScrollbarRef}
                        className="overflow-x-auto overflow-y-hidden rounded-t-xl border border-b-0 border-slate-200 bg-slate-50"
                        style={{ width: `${overlayHeader.width}px` }}
                    >
                        <div style={{ width: `${overlayHeader.tableWidth}px`, height: '16px' }} />
                    </div>
                    <div className="overflow-hidden rounded-t-xl border border-slate-200 bg-slate-50 shadow-sm">
                        <div className="relative" style={{ width: `${overlayHeader.width}px`, height: `${overlayHeader.height || 57}px` }}>
                            <div
                                className="absolute left-0 top-0 z-10 overflow-hidden border-r border-slate-200 bg-slate-50"
                                style={{ width: `${Math.min(fixedHeaderWidth, overlayHeader.width)}px` }}
                            >
                                <table className="data-table" style={{ width: `${fixedHeaderWidth}px`, tableLayout: 'fixed' }}>
                                    <colgroup>
                                        <col style={{ width: `${tableColumnWidths.select}px` }} />
                                        <col style={{ width: `${tableColumnWidths.geneId}px` }} />
                                        <col style={{ width: `${tableColumnWidths.geneSymbol}px` }} />
                                        <col style={{ width: `${tableColumnWidths.pattern}px` }} />
                                    </colgroup>
                                    <thead>
                                        <tr>
                                            <th
                                                className="p-4 text-left text-xs font-bold text-slate-600 uppercase tracking-wider w-12"
                                                style={{ width: `${tableColumnWidths.select}px`, backgroundColor: 'rgb(248 250 252)' }}
                                            >
                                                <button
                                                    onClick={handleSelectAllCycle}
                                                    className="flex items-center justify-center w-5 h-5 hover:opacity-75 transition-opacity"
                                                    title={
                                                        selectAllState === 0 ? 'Select current page' :
                                                        selectAllState === 1 ? 'Select all pages' :
                                                        'Deselect all'
                                                    }
                                                >
                                                    <svg viewBox="0 0 16 16" className="w-4 h-4" fill="none" xmlns="http://www.w3.org/2000/svg">
                                                        {selectAllState === 0 && (
                                                            <rect x="1" y="1" width="14" height="14" rx="2" stroke="#9CA3AF" strokeWidth="1.5"/>
                                                        )}
                                                        {selectAllState === 1 && (
                                                            <>
                                                                <rect x="1" y="1" width="14" height="14" rx="2" stroke="#3B82F6" strokeWidth="1.5"/>
                                                                <path d="M4 8.5l2.5 2.5 5-5.5" stroke="#3B82F6" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                                                            </>
                                                        )}
                                                        {selectAllState === 2 && (
                                                            <>
                                                                <rect x="1" y="1" width="14" height="14" rx="2" fill="#1D4ED8" stroke="#1D4ED8" strokeWidth="1.5"/>
                                                                <path d="M4 8.5l2.5 2.5 5-5.5" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                                                            </>
                                                        )}
                                                    </svg>
                                                </button>
                                            </th>
                                            <th className="px-3 py-3 text-left text-xs font-bold text-slate-600 uppercase tracking-wider" style={{ width: `${tableColumnWidths.geneId}px`, minWidth: `${tableColumnWidths.geneId}px`, backgroundColor: 'rgb(248 250 252)' }}>
                                                Gene ID
                                            </th>
                                            <th className="px-3 py-3 text-left text-xs font-bold text-slate-600 uppercase tracking-wider" style={{ width: `${tableColumnWidths.geneSymbol}px`, minWidth: `${tableColumnWidths.geneSymbol}px`, backgroundColor: 'rgb(248 250 252)' }}>
                                                Gene Symbol
                                            </th>
                                            <th className="px-3 py-3 text-center text-xs font-bold text-slate-600 uppercase tracking-wider" style={{ width: `${tableColumnWidths.pattern}px`, minWidth: `${tableColumnWidths.pattern}px`, backgroundColor: 'rgb(248 250 252)' }}>
                                                Expression Pattern
                                            </th>
                                        </tr>
                                    </thead>
                                </table>
                            </div>
                            <div
                                className="absolute top-0 overflow-hidden"
                                style={{
                                    left: `${Math.min(fixedHeaderWidth, overlayHeader.width)}px`,
                                    width: `${Math.max(0, overlayHeader.width - Math.min(fixedHeaderWidth, overlayHeader.width))}px`
                                }}
                            >
                                <div
                                    style={{
                                        width: `${Math.max(0, overlayHeader.tableWidth - fixedHeaderWidth)}px`,
                                        transform: `translateX(-${overlayHeader.scrollLeft}px)`
                                    }}
                                >
                                    <table className="data-table" style={{ width: `${Math.max(0, overlayHeader.tableWidth - fixedHeaderWidth)}px`, tableLayout: 'fixed' }}>
                                        <colgroup>
                                            {(matrixData?.samples || []).map(sample => (
                                                <col key={sample} style={{ width: `${tableColumnWidths.sample}px` }} />
                                            ))}
                                        </colgroup>
                                        <thead>
                                            <tr>
                                                {(matrixData?.samples || []).map(name => (
                                                    <th
                                                        key={name}
                                                        className="px-3 py-3 text-left text-xs font-bold text-slate-600 uppercase tracking-wider"
                                                        style={{ width: `${tableColumnWidths.sample}px`, minWidth: `${tableColumnWidths.sample}px`, backgroundColor: 'rgb(248 250 252)' }}
                                                    >
                                                        {name}
                                                    </th>
                                                ))}
                                            </tr>
                                        </thead>
                                    </table>
                                </div>
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
                comparisonName={`Expression_Matrix_P${pValue}_C${foldChange}`}
                toolName="Expression Matrix"
            />

            {/* Heatmap Analysis Modal */}
            <HeatmapAnalysisModal
                isOpen={analysisHeatmapOpen}
                onClose={closeAnalysisHeatmap}
                workbenchId={workbenchId}
                selectedGenes={Array.from(selectedGenes)}
                comparisonName={`Expression_Matrix_P${pValue}_C${foldChange}`}
                toolName="Expression Matrix"
            />

            {/* KEGG Pathway Modal */}
            <KEGGPathwayModal
                isOpen={analysisKEGGOpen}
                onClose={closeAnalysisKEGG}
                workbenchId={workbenchId}
                selectedGenes={Array.from(selectedGenes)}
                comparisonName={`Expression_Matrix_P${pValue}_C${foldChange}`}
                toolName="Expression Matrix"
            />
        </div>
    );
};

export default WorkbenchDetailDEGExpressionMatrix;
