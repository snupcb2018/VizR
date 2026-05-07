import React, { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import { createPortal } from 'react-dom';
import useWebSocket from '../src/hooks/useWebSocket';
import { Workbench, StepDetail } from '../types';
import { apiService } from '../services/api';
import PatternSelectionPanel from './PatternSelectionPanel';
import GOAnalysisModal from './GOAnalysisModal';
import GOProviderSubmenu from './GOProviderSubmenu';
import CopyGeneListMenuItem from './CopyGeneListMenuItem';
import HeatmapAnalysisModal from './HeatmapAnalysisModal';
import KEGGPathwayModal from './KEGGPathwayModal';
import MiniHeatmap from './MiniHeatmap';
import SelectableGeneTableShell from './SelectableGeneTableShell';
import VennSetMenu, { VennSetSummary } from './VennSetMenu';
import { useGeneAnalysisActions } from '../hooks/useGeneAnalysisActions';
import { useOverlayStickyTable } from '../hooks/useOverlayStickyTable';

// ========================================
// Type Definitions
// ========================================

interface CountsProgressData {
    completed_files: number;
    total_files: number;
    progress_percent: number;
    tool_name?: string;
}

interface ToolProgressResponse {
    workbench_id: number;
    status: 'not_started' | 'pending' | 'running' | 'completed' | 'failed';
    progress_data: CountsProgressData | null;
    last_updated: string | null;
}

interface CountResultsResponse {
    workbench_id: number;
    matrix_type: string;
    matrix: Array<{
        gene_id: string;
        gene_symbol: string;
        gene_description: string;
        [sample: string]: number | string;
    }>;
    samples: string[];
    groups?: string[];  // Sample groups from pipeline configuration
    total_genes: number;
    showing_genes: number;
    current_page: number;
    total_pages: number;
    page_size: number;
    matrix_file: string | null;
    status: 'available' | 'not_available';
    // 검색 관련 필드 추가
    search_query?: string;
    is_search_result?: boolean;
}

type MatrixType = 'TMM' | 'TPM' | 'Raw';

interface WorkbenchDetailCountsProps {
    workbench: Workbench;
    pipelineStepsData: StepDetail[];
    selectedGenes: Set<string>;
    onSelectionChange: (genes: Set<string>) => void;
    onAnalysisRequest: (type: string) => void;
    showComingSoon: () => void;
    onNavigateToVennDiagram: (genes: string[], targetSetIndex?: number) => void;
    vennSetSummaries?: VennSetSummary[];
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

const ProgressBar = ({ progress }: { progress: CountsProgressData | null }) => {
    if (!progress) {
        return (
            <div className="w-full bg-slate-200 rounded-full h-2">
                <div className="bg-slate-400 h-2 rounded-full w-0"></div>
            </div>
        );
    }

    const percentage = Math.min(100, Math.max(0, progress.progress_percent || 0));

    return (
        <div className="w-full">
            <div className="flex justify-between text-sm text-slate-600 mb-2">
                <span>Count Quantification Progress</span>
                <span>{progress.completed_files}/{progress.total_files} files ({percentage.toFixed(1)}%)</span>
            </div>
            <div className="w-full bg-slate-200 rounded-full h-2">
                <div
                    className="bg-purple-600 h-2 rounded-full transition-all duration-300 ease-out"
                    style={{ width: `${percentage}%` }}
                ></div>
            </div>
        </div>
    );
};

const StatusBadge = ({ status }: { status: string }) => {
    const statusConfig = {
        'not_started': { color: 'bg-slate-100 text-slate-600', text: 'Not Started' },
        'pending': { color: 'bg-yellow-100 text-yellow-700', text: 'Pending' },
        'running': { color: 'bg-purple-100 text-purple-700', text: 'Running' },
        'completed': { color: 'bg-green-100 text-green-700', text: 'Completed' },
        'failed': { color: 'bg-red-100 text-red-700', text: 'Failed' }
    };

    const config = statusConfig[status as keyof typeof statusConfig] || statusConfig.not_started;

    return (
        <span className={`px-2 py-1 rounded-full text-xs font-medium ${config.color}`}>
            {config.text}
        </span>
    );
};

// Loading Modal Component
const LoadingModal = ({
    isOpen,
    matrixType,
    mode = 'loading'
}: {
    isOpen: boolean;
    matrixType: MatrixType;
    mode?: 'loading' | 'pattern_analysis';
}) => {
    if (!isOpen) return null;

    const messages = {
        loading: {
            title: `Loading ${matrixType} matrix data...`,
            description: 'Please wait while we fetch the count quantification results.'
        },
        pattern_analysis: {
            title: 'Analyzing Pattern...',
            description: 'Searching for genes matching the specified expression pattern. This may take a moment.'
        }
    };

    const message = messages[mode];

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50">
            <div className="bg-white rounded-lg shadow-xl p-8 max-w-md w-full mx-4">
                <div className="flex flex-col items-center space-y-4">
                    {/* Spinner */}
                    <div className="animate-spin rounded-full h-16 w-16 border-b-4 border-blue-600"></div>

                    {/* Loading Text */}
                    <div className="text-center">
                        <h3 className="text-lg font-semibold text-slate-900 mb-2">
                            {message.title}
                        </h3>
                        <p className="text-sm text-slate-500">
                            {message.description}
                        </p>
                    </div>
                </div>
            </div>
        </div>
    );
};

// Pattern Analysis Result Modal Component
const PatternResultModal = ({
    isOpen,
    onClose,
    type,
    geneCount,
    errorMessage
}: {
    isOpen: boolean;
    onClose: () => void;
    type: 'success' | 'no_results' | 'error';
    geneCount?: number;
    errorMessage?: string;
}) => {
    if (!isOpen) return null;

    const configs = {
        success: {
            icon: '✅',
            iconColor: 'text-green-600',
            title: 'Pattern analysis complete!',
            message: `Found ${geneCount} genes matching the pattern.`,
            buttonText: 'OK',
            buttonColor: 'bg-green-600 hover:bg-green-700'
        },
        no_results: {
            icon: '⚠️',
            iconColor: 'text-yellow-600',
            title: 'No genes found matching the specified pattern.',
            message: (
                <div className="text-sm text-slate-600 space-y-2">
                    <p>Try adjusting the thresholds:</p>
                    <ul className="list-disc list-inside space-y-1 text-left">
                        <li>Lower Min Spearman Correlation</li>
                        <li>Lower Min Log2 Fold Change</li>
                        <li>Increase tolerance values</li>
                    </ul>
                </div>
            ),
            buttonText: 'OK',
            buttonColor: 'bg-yellow-600 hover:bg-yellow-700'
        },
        error: {
            icon: '❌',
            iconColor: 'text-red-600',
            title: 'Pattern analysis failed',
            message: errorMessage || 'An error occurred. Please try again.',
            buttonText: 'OK',
            buttonColor: 'bg-red-600 hover:bg-red-700'
        }
    };

    const config = configs[type];

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50">
            <div className="bg-white rounded-lg shadow-xl p-8 max-w-md w-full mx-4">
                <div className="flex flex-col items-center space-y-4">
                    {/* Icon */}
                    <div className={`text-5xl ${config.iconColor}`}>
                        {config.icon}
                    </div>

                    {/* Title */}
                    <h3 className="text-lg font-semibold text-slate-900 text-center">
                        {config.title}
                    </h3>

                    {/* Message */}
                    <div className="text-center">
                        {typeof config.message === 'string' ? (
                            <p className="text-sm text-slate-600">{config.message}</p>
                        ) : (
                            config.message
                        )}
                    </div>

                    {/* Close Button */}
                    <button
                        onClick={onClose}
                        className={`px-6 py-2 text-white rounded-lg transition-colors ${config.buttonColor}`}
                    >
                        {config.buttonText}
                    </button>
                </div>
            </div>
        </div>
    );
};

// Matrix Type Selector Component
const MatrixTypeSelector = ({
    selectedType,
    onTypeChange,
    disabled,
    hasTPMMatrix = true
}: {
    selectedType: MatrixType;
    onTypeChange: (type: MatrixType) => void;
    disabled: boolean;
    hasTPMMatrix?: boolean;
}) => {
    const matrixTypes: Array<{ value: MatrixType; label: string; description: string }> = [
        { value: 'Raw', label: 'Gene Count', description: 'Gene-level raw read counts' },
        { value: 'TPM', label: 'TPM', description: 'Transcripts Per Million normalized' },
        { value: 'TMM', label: 'TMM', description: 'Trimmed Mean of M-values normalized' }
    ];

    return (
        <div className="flex space-x-2 mb-4">
            {matrixTypes.map(type => (
                <button
                    key={type.value}
                    onClick={() => onTypeChange(type.value)}
                    disabled={disabled || (type.value === 'TPM' && !hasTPMMatrix)}
                    className={`px-4 py-2 rounded-lg border transition-colors ${
                        selectedType === type.value
                            ? 'bg-blue-600 text-white border-blue-600'
                            : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'
                    } ${(disabled || (type.value === 'TPM' && !hasTPMMatrix)) ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
                    title={type.value === 'TPM' && !hasTPMMatrix ? 'TPM matrix is unavailable for this workbench' : type.description}
                >
                    {type.value === 'TPM' && !hasTPMMatrix ? 'TPM (Unavailable)' : type.label}
                </button>
            ))}
        </div>
    );
};

// Pagination Component
interface PaginationProps {
    currentPage: number;
    totalPages: number;
    onPageChange: (page: number) => void;
    pageSize: number;
    onPageSizeChange: (size: number) => void;
    totalCount: number;
}

const Pagination: React.FC<PaginationProps> = ({
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
            // 7페이지 이하: 모두 표시
            for (let i = 1; i <= totalPages; i++) {
                pages.push(i);
            }
        } else {
            // 7페이지 초과: 축약 표시
            if (currentPage <= 4) {
                // 앞쪽: 1 2 3 4 5 ... 마지막
                for (let i = 1; i <= 5; i++) pages.push(i);
                pages.push('...');
                pages.push(totalPages);
            } else if (currentPage >= totalPages - 3) {
                // 뒷쪽: 1 ... 마지막-4 마지막-3 마지막-2 마지막-1 마지막
                pages.push(1);
                pages.push('...');
                for (let i = totalPages - 4; i <= totalPages; i++) pages.push(i);
            } else {
                // 중간: 1 ... 현재-1 현재 현재+1 ... 마지막
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
                {/* Previous Button */}
                <button
                    onClick={() => onPageChange(currentPage - 1)}
                    disabled={currentPage === 1}
                    className="px-3 py-1 rounded border border-slate-300 text-sm disabled:opacity-50 disabled:cursor-not-allowed hover:bg-slate-50"
                >
                    Previous
                </button>

                {/* Page Numbers */}
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

                {/* Next Button */}
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

const WorkbenchDetailCounts: React.FC<WorkbenchDetailCountsProps> = ({
    workbench,
    pipelineStepsData,
    selectedGenes,
    onSelectionChange,
    onAnalysisRequest,
    showComingSoon,
    onNavigateToVennDiagram,
    vennSetSummaries
}) => {
    const [progressData, setProgressData] = useState<ToolProgressResponse | null>(null);
    const [countsResults, setCountsResults] = useState<CountResultsResponse | null>(null);
    const [loading, setLoading] = useState(false);
    const searchInputRef = useRef<HTMLTextAreaElement>(null);  // 검색 입력 참조
    const [activeSearch, setActiveSearch] = useState('');  // 서버 검색용
    const [isActionMenuOpen, setActionMenuOpen] = useState(false);
    const [selectedMatrixType, setSelectedMatrixType] = useState<MatrixType>('TMM');
    const [currentPage, setCurrentPage] = useState(1);
    const [pageSize, setPageSize] = useState(500);
    const [loadingResults, setLoadingResults] = useState(false);
    const [analyzingPattern, setAnalyzingPattern] = useState(false);
    const [selectedColumns, setSelectedColumns] = useState<Set<string>>(new Set());
    const actionMenuRef = useRef(null);

    // Pattern selection state
    const [isPatternPanelExpanded, setPatternPanelExpanded] = useState(false);
    const [patternFullResults, setPatternFullResults] = useState<any>(null); // Store full pattern results for filtering
    const [initialSampleGroups, setInitialSampleGroups] = useState<string[]>([]);
    const [isPatternAnalysisActive, setPatternAnalysisActive] = useState(false); // Track if pattern analysis is active
    const [patternResultModal, setPatternResultModal] = useState<{
        isOpen: boolean;
        type: 'success' | 'no_results' | 'error';
        geneCount?: number;
        errorMessage?: string;
    }>({
        isOpen: false,
        type: 'success'
    });

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
        workbenchId: workbench.id,
        selectedGenes: Array.from(selectedGenes),
        description: `Selected genes from ${selectedMatrixType} count matrix`,
    });

    const [selectAllState, setSelectAllState] = useState<0 | 1 | 2>(0);
    const hasTPMMatrix = workbench.has_tpm_matrix !== false;

    // Extract count tool name from pipeline steps data or progress data
    const countStep = pipelineStepsData?.find(step =>
        step.step_name === 'count' ||
        step.step_name === 'quantification' ||
        step.tool_name?.toLowerCase().includes('stringtie') ||
        step.tool_name?.toLowerCase().includes('htseq') ||
        step.tool_name?.toLowerCase().includes('featurecounts')
    );

    // Priority: API progress data tool_name > pipeline steps tool_name > fallback
    const toolName = progressData?.progress_data?.tool_name ||
                     countStep?.tool_name ||
                     'Unknown';
    const status = progressData?.status || 'not_started';

    // WebSocket connection for real-time progress updates (only when not completed)
    const {
        isConnected: wsIsConnected,
        connectionId: wsConnectionId,
        lastError: wsLastError,
        progressData: wsProgressData,
        disconnect: wsDisconnect,
        reconnect: wsReconnect
    } = useWebSocket({
        workbenchId: workbench.id,
        taskType: 'stringtie',
        enabled: progressData?.status !== 'completed', // Only connect if not completed
        onProgressUpdate: (data) => {
            // Update progress data when WebSocket receives updates
            if (data && typeof data === 'object') {
                // Extract progress data from nested structure
                const progressInfo = data.data || data;

                setProgressData(prev => {
                    const progressPercent = progressInfo.progress_percent || 0;
                    const isCompleted = progressPercent >= 100;
                    const newStatus = isCompleted ? 'completed' : 'running';

                    return {
                        ...prev,
                        workbench_id: workbench.id,
                        status: newStatus,
                        progress_data: {
                            completed_files: progressInfo.completed_files || 0,
                            total_files: progressInfo.total_files || 0,
                            progress_percent: progressPercent
                        },
                        last_updated: new Date().toISOString()
                    };
                });
            }
        },
        onConnect: () => {},
        onDisconnect: () => {},
        onError: () => {}
    });

    useEffect(() => {
        const handleClickOutside = (event: MouseEvent) => {
            if (actionMenuRef.current && !actionMenuRef.current.contains(event.target as Node)) {
                setActionMenuOpen(false);
            }
        };
        document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, []);

    /**
     * Fetch Count progress from API
     */
    const fetchProgress = async () => {
        if (loading) return;
        setLoading(true);

        try {
            const response = await fetch(`/api/workbenches/${workbench.id}/count-progress`, {
                credentials: 'include'
            });

            if (response.ok) {
                const data: ToolProgressResponse = await response.json();
                setProgressData(data);
            }
        } catch (error) {
            console.error('Error fetching count progress:', error);
        } finally {
            setLoading(false);
        }
    };

    /**
     * Fetch Count results from API
     */
    const fetchCountResults = async (matrixType: MatrixType, page: number = 1, search: string = '', limit: number = 1000) => {
        setLoadingResults(true);
        setSelectedColumns(new Set()); // Reset column selection

        try {
            // Build URL with search parameter
            let url = `/api/workbenches/${workbench.id}/count-results?matrix_type=${matrixType}&page=${page}&limit=${limit}`;
            if (search) {
                url += `&search=${encodeURIComponent(search)}`;
            }

            const response = await fetch(url, { credentials: 'include' });

            if (response.ok) {
                const data: CountResultsResponse = await response.json();

                setCountsResults(data);

                // Store initial sample groups when first loading full results (not search or pattern results)
                if (!search && !isPatternAnalysisActive && data.groups && data.groups.length > 0) {
                    setInitialSampleGroups(data.groups);
                }
            } else {
                console.error('Failed to fetch count results:', response.status, response.statusText);
            }
        } catch (error) {
            console.error('Error fetching count results:', error);
        } finally {
            setLoadingResults(false);
        }
    };

    /**
     * Filter pattern analysis results by search query
     */
    const filterPatternResults = (searchQuery: string) => {
        if (!patternFullResults || !patternFullResults.matrix) {
            return;
        }

        const searchTerms = searchQuery
            .split(/[\s,\t\n]+/)
            .map(term => term.trim().toUpperCase())
            .filter(term => term.length > 0);

        // Filter matrix by gene IDs or symbols
        const filteredMatrix = patternFullResults.matrix.filter((gene: any) => {
            const geneId = gene.gene_id.toUpperCase();
            const geneSymbol = gene.gene_symbol.toUpperCase();

            return searchTerms.some(term =>
                geneId.includes(term) || geneSymbol.includes(term)
            );
        });

        // Update results with filtered data
        setCountsResults({
            ...patternFullResults,
            matrix: filteredMatrix,
            total_genes: filteredMatrix.length,
            showing_genes: filteredMatrix.length,
            current_page: 1,
            total_pages: 1,
            page_size: filteredMatrix.length,
            is_search_result: true,
            search_query: `Pattern Analysis (${filteredMatrix.length} genes) - Filtered: "${searchQuery}"`
        });
    };

    /**
     * Handle search
     */
    const handleSearch = () => {
        const searchValue = searchInputRef.current?.value.trim() || '';
        if (searchValue) {
            setActiveSearch(searchValue);
            setCurrentPage(1);  // Reset to page 1 when searching
            setSelectAllState(0);

            // If pattern analysis is active, filter within pattern results
            if (isPatternAnalysisActive && patternFullResults) {
                filterPatternResults(searchValue);
            } else {
                // Regular search in full dataset
                fetchCountResults(selectedMatrixType, 1, searchValue, pageSize);
            }
        }
    };

    const handleClearSearch = () => {
        if (searchInputRef.current) {
            searchInputRef.current.value = '';
        }
        setActiveSearch('');
        setCurrentPage(1);
        setSelectAllState(0);

        // If pattern analysis is active, restore full pattern results
        if (isPatternAnalysisActive && patternFullResults) {
            setCountsResults(patternFullResults);
        } else {
            // Clear pattern analysis state and fetch full dataset
            setPatternAnalysisActive(false);
            fetchCountResults(selectedMatrixType, 1, '', pageSize);
        }
    };

    /**
     * Handle matrix type change
     */
    const handleMatrixTypeChange = (newType: MatrixType) => {
        if (newType === 'TPM' && !hasTPMMatrix) {
            return;
        }
        setSelectedMatrixType(newType);
        setCurrentPage(1);  // Reset to page 1 when changing matrix type
        setActiveSearch('');  // Clear search when changing matrix type
        setPatternAnalysisActive(false); // Reset pattern analysis state
        setPatternFullResults(null); // Clear pattern results
        setSelectAllState(0);
        if (searchInputRef.current) {
            searchInputRef.current.value = '';
        }
        if (progressData?.status === 'completed') {
            fetchCountResults(newType, 1, '', pageSize);
        }
    };

    /**
     * Handle page change
     */
    const handlePageChange = (newPage: number) => {
        const maxPage = isPatternAnalysisActive
            ? Math.max(1, Math.ceil(filteredData.length / pageSize))
            : (countsResults?.total_pages || 1);
        const safePage = Math.min(Math.max(newPage, 1), maxPage);
        setCurrentPage(safePage);

        // Pattern analysis pagination is handled on the client side.
        if (!isPatternAnalysisActive) {
            fetchCountResults(selectedMatrixType, safePage, activeSearch, pageSize);
        }

        // Scroll to top of table
        window.scrollTo({ top: 0, behavior: 'smooth' });
    };

    /**
     * Handle page size change
     */
    const handlePageSizeChange = (newSize: number) => {
        setPageSize(newSize);
        setCurrentPage(1); // Reset to first page when changing page size

        // Pattern analysis pagination is handled on the client side.
        if (!isPatternAnalysisActive) {
            fetchCountResults(selectedMatrixType, 1, activeSearch, newSize);
        }
    };

    useEffect(() => {
        if (!hasTPMMatrix && selectedMatrixType === 'TPM') {
            setSelectedMatrixType('TMM');
        }
    }, [hasTPMMatrix, selectedMatrixType]);

    // Initialize component when mounted
    useEffect(() => {
        fetchProgress();
    }, []);

    // 페이지 변경 시 선택 초기화
    useEffect(() => {
        onSelectionChange(new Set());
        setSelectAllState(0);
    }, [currentPage, pageSize]);

    // Fetch results when count is completed (실시간 자동 호출)
    useEffect(() => {
        if (progressData?.status === 'completed') {
            fetchCountResults(selectedMatrixType, currentPage, activeSearch, pageSize);
            // WebSocket은 enabled 조건에 의해 자동으로 disconnect됨
        }
    }, [progressData?.status, selectedMatrixType]);

    const filteredData = useMemo(() => {
        if (!countsResults?.matrix || countsResults.matrix.length === 0) {
            return [];
        }

        // 서버에서 이미 필터링된 데이터를 그대로 사용
        // 단순히 형태만 변환
        const baseData = countsResults.matrix.map(gene => {
            const row: any = {
                gene: gene.gene_id,
                gene_symbol: gene.gene_symbol,
                gene_description: gene.gene_description
            };
            countsResults.samples.forEach(sample => {
                row[sample] = gene[sample];
            });
            return row;
        });

        return baseData;
    }, [countsResults]);

    // Pattern analysis returns full matrix data, so paginate that result on client side.
    const displayedData = useMemo(() => {
        if (!isPatternAnalysisActive) {
            return filteredData;
        }
        const start = (currentPage - 1) * pageSize;
        return filteredData.slice(start, start + pageSize);
    }, [isPatternAnalysisActive, filteredData, currentPage, pageSize]);

    const effectiveTotalCount = isPatternAnalysisActive
        ? filteredData.length
        : (countsResults?.total_genes || 0);
    const effectiveTotalPages = isPatternAnalysisActive
        ? Math.max(1, Math.ceil(effectiveTotalCount / pageSize))
        : (countsResults?.total_pages || 1);
    const effectiveCurrentPage = isPatternAnalysisActive
        ? currentPage
        : (countsResults?.current_page || 1);

    const tableColumnWidths = {
        select: 48,
        geneId: 150,
        geneSymbol: 120,
        pattern: 240,
        sample: 124
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
        enabled: status === 'completed' && displayedData.length > 0,
        dependencyKey: [
            status,
            effectiveCurrentPage,
            pageSize,
            displayedData.length,
            countsResults?.samples?.length ?? 0,
            countsResults?.total_genes ?? 0,
            selectedMatrixType,
            loadingResults ? 'loading' : 'idle',
            isPatternAnalysisActive ? 'pattern' : 'regular'
        ].join('|')
    });

    const tableColGroup = (
        <colgroup>
            <col style={{ width: `${tableColumnWidths.select}px` }} />
            <col style={{ width: `${tableColumnWidths.geneId}px` }} />
            <col style={{ width: `${tableColumnWidths.geneSymbol}px` }} />
            <col style={{ width: `${tableColumnWidths.pattern}px` }} />
            {(countsResults?.samples || []).map(sample => (
                <col key={sample} style={{ width: `${tableColumnWidths.sample}px` }} />
            ))}
        </colgroup>
    );

    const formatMatrixValue = useCallback((value: unknown) => {
        if (typeof value === 'number' && Number.isFinite(value)) {
            if (selectedMatrixType === 'Raw') {
                return value.toLocaleString();
            }
            return value.toFixed(3);
        }

        if (typeof value === 'string') {
            const parsed = Number(value);
            if (Number.isFinite(parsed)) {
                if (selectedMatrixType === 'Raw') {
                    return parsed.toLocaleString();
                }
                return parsed.toFixed(3);
            }
        }

        return value ?? '';
    }, [selectedMatrixType]);

    const fetchAllGeneIds = useCallback(async (): Promise<string[]> => {
        if (isPatternAnalysisActive && patternFullResults) {
            // Pattern analysis: all results are already in patternFullResults
            return (patternFullResults.matrix || []).map((gene: any) => gene.gene_id as string);
        } else {
            const total = countsResults?.total_genes || 0;
            let url = `/api/workbenches/${workbench.id}/count-results?matrix_type=${selectedMatrixType}&page=1&limit=${total}`;
            if (activeSearch) {
                url += `&search=${encodeURIComponent(activeSearch)}`;
            }
            try {
                const response = await fetch(url, { credentials: 'include' });
                if (response.ok) {
                    const data: CountResultsResponse = await response.json();
                    return (data.matrix || []).map(gene => gene.gene_id);
                }
            } catch (error) {
                console.error('Failed to fetch all gene IDs:', error);
            }
            return [];
        }
    }, [workbench.id, isPatternAnalysisActive, patternFullResults, countsResults?.total_genes, selectedMatrixType, activeSearch]);

    const handleSelectAllCycle = useCallback(async () => {
        if (selectAllState === 0) {
            const newSelected = new Set(selectedGenes);
            displayedData.forEach(item => newSelected.add(item.gene as string));
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
    }, [selectAllState, displayedData, selectedGenes, onSelectionChange, fetchAllGeneIds]);

    const handleSelectOne = (gene: string) => {
        const newSelectedGenes = new Set(selectedGenes);
        if (newSelectedGenes.has(gene)) {
            newSelectedGenes.delete(gene);
        } else {
            newSelectedGenes.add(gene);
        }
        onSelectionChange(newSelectedGenes);
        setSelectAllState(0);
    };

    const handleColumnClick = (columnName: string) => {
        const newSelectedColumns = new Set(selectedColumns);
        if (newSelectedColumns.has(columnName)) {
            newSelectedColumns.delete(columnName);
        } else {
            newSelectedColumns.add(columnName);
        }
        setSelectedColumns(newSelectedColumns);
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
            {(countsResults?.samples || []).map(name => {
                const isSelected = selectedColumns.has(name);
                return (
                    <th
                        key={name}
                        className="px-3 py-3 text-left text-xs font-bold uppercase tracking-wider cursor-pointer hover:bg-blue-50 transition-colors"
                        style={{
                            width: `${tableColumnWidths.sample}px`,
                            minWidth: `${tableColumnWidths.sample}px`,
                            backgroundColor: isSelected ? 'rgb(219 234 254)' : 'rgb(248 250 252)',
                            color: isSelected ? 'rgb(30 64 175)' : 'rgb(71 85 105)'
                        }}
                        onClick={() => handleColumnClick(name)}
                        title={`Click to ${isSelected ? 'deselect' : 'select'} ${name} column`}
                    >
                        {name}
                    </th>
                );
            })}
        </tr>
    );

    const handleDownload = async () => {
        // 선택 유전자가 있으면 POST로 선택 목록만 다운로드
        if (selectedGenes.size > 0) {
            try {
                const response = await fetch(`/api/workbenches/${workbench.id}/count-results/download`, {
                    method: 'POST',
                    credentials: 'include',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        matrix_type: selectedMatrixType,
                        search: activeSearch,
                        selected_genes: Array.from(selectedGenes)
                    })
                });

                if (!response.ok) {
                    throw new Error('Failed to download selected genes');
                }

                const blob = await response.blob();
                const blobUrl = window.URL.createObjectURL(blob);

                const contentDisposition = response.headers.get('Content-Disposition') || '';
                const filenameMatch = contentDisposition.match(/filename="?([^"]+)"?/i);
                const fallbackName = `counts_${selectedMatrixType}_${workbench.name}_selected_${selectedGenes.size}_genes.csv`;
                const filename = filenameMatch?.[1] || fallbackName;

                const link = document.createElement('a');
                link.href = blobUrl;
                link.download = filename;
                link.click();

                window.URL.revokeObjectURL(blobUrl);
            } catch (error) {
                console.error('Failed to download selected genes:', error);
                alert('Failed to download selected genes. Please try again.');
            }
            return;
        }

        // 선택 유전자가 없으면 기존 동작(전체/검색 결과 전체 다운로드)
        let url = `/api/workbenches/${workbench.id}/count-results/download?matrix_type=${selectedMatrixType}`;
        if (activeSearch) {
            url += `&search=${encodeURIComponent(activeSearch)}`;
        }
        window.location.href = url;
    };

    // Extract sample groups from API response (or fallback to parsing from samples)
    const sampleGroups = useMemo(() => {
        // Backend always provides groups array (empty array if extraction fails)
        const groups = countsResults?.groups || [];

        return groups;
    }, [countsResults?.groups]);

    // Handle pattern analysis
    const handlePatternAnalysis = async (config: any) => {
        setAnalyzingPattern(true);
        setSelectedColumns(new Set()); // Reset column selection
        try {
            const response = await fetch(`/api/workbenches/${workbench.id}/pattern-analysis`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                credentials: 'include',
                body: JSON.stringify({
                    matrix_type: selectedMatrixType,
                    page: 1,
                    limit: pageSize,
                    ...config
                })
            });

            if (response.ok) {
                const results = await response.json();

                // Backend returns same format as count results
                if (results.total_genes > 0) {
                    // Mark that pattern analysis is active
                    setPatternAnalysisActive(true);

                    // Store full pattern results for filtering
                    setPatternFullResults(results);

                    // Directly use the response from backend
                    setCountsResults(results);
                    setCurrentPage(1); // Reset to page 1
                    setSelectAllState(0);

                    // Show success modal
                    setPatternResultModal({
                        isOpen: true,
                        type: 'success',
                        geneCount: results.total_genes
                    });

                    // Close pattern panel after successful analysis
                    setPatternPanelExpanded(false);
                } else {
                    // Show no results modal
                    setPatternResultModal({
                        isOpen: true,
                        type: 'no_results'
                    });
                }
            } else {
                const error = await response.text();
                console.error('Pattern analysis failed:', error);

                // Show error modal
                setPatternResultModal({
                    isOpen: true,
                    type: 'error',
                    errorMessage: error
                });
            }
        } catch (error) {
            console.error('Error during pattern analysis:', error);

            // Show error modal
            setPatternResultModal({
                isOpen: true,
                type: 'error',
                errorMessage: 'Pattern analysis error. Please try again.'
            });
        } finally {
            setAnalyzingPattern(false);
        }
    };

    // Handle GO Analysis
    const handleGOAnalysis = async (provider: 'david' | 'gprofiler') => {
        const genes = Array.from(selectedGenes);

        setGOLoading(true);
        setGOModalOpen(true);

        try {
            const result = await apiService.runGOEnrichment(workbench.id, {
                genes: genes,
                databases: ['GO_BP', 'GO_MF', 'GO_CC'],
                p_value_cutoff: 0.05,
                description: `Selected genes from ${selectedMatrixType} count matrix`,
                organism: 'arabidopsis',
                provider
            });
            setGOAnalysisResult(result);
        } catch (error) {
            console.error('GO Analysis failed:', error);
        } finally {
            setGOLoading(false);
            setActionMenuOpen(false);
        }
    };

    return (
        <>
            {/* Loading Modals */}
            <LoadingModal
                isOpen={loadingResults}
                matrixType={selectedMatrixType}
                mode={isPatternAnalysisActive ? "pattern_analysis" : "loading"}
            />
            <LoadingModal isOpen={analyzingPattern} matrixType={selectedMatrixType} mode="pattern_analysis" />

            {/* Pattern Result Modal */}
            <PatternResultModal
                isOpen={patternResultModal.isOpen}
                onClose={() => setPatternResultModal({ ...patternResultModal, isOpen: false })}
                type={patternResultModal.type}
                geneCount={patternResultModal.geneCount}
                errorMessage={patternResultModal.errorMessage}
            />

            <div className="h-full p-6">
                <div className="bg-white rounded-lg shadow-sm border border-slate-200">
                    <div className="p-6">
                        <div className="flex items-center justify-between mb-6">
                            <div className="flex items-center space-x-4">
                                <h3 className="text-lg font-semibold text-slate-900">Gene Expression Counts</h3>
                            {toolName && toolName !== 'Unknown' && (
                                <span className="px-3 py-1 bg-purple-100 text-purple-700 rounded-full text-sm font-medium">
                                    {toolName.toUpperCase()}
                                </span>
                            )}
                            {/* WebSocket Connection Indicator - Only show when not completed */}
                            {status !== 'completed' && (
                                <div className="flex items-center space-x-2">
                                    <div className={`w-2 h-2 rounded-full ${
                                        wsIsConnected ? 'bg-green-500' : 'bg-red-500'
                                    }`} />
                                    <span className="text-xs text-slate-500">
                                        {wsIsConnected ? 'Live' : 'Offline'}
                                    </span>
                                    {!wsIsConnected && (
                                        <button
                                            onClick={wsReconnect}
                                            className="text-xs text-blue-600 hover:text-blue-800 underline"
                                        >
                                            Reconnect
                                        </button>
                                    )}
                                </div>
                            )}
                        </div>
                        <StatusBadge status={status} />
                    </div>

                    {/* Progress Section - Only show when not completed */}
                    {status !== 'completed' && (
                        <div className="mb-6">
                            <ProgressBar progress={progressData?.progress_data || null} />

                            <div className="mt-2 flex items-center justify-between text-sm text-slate-500">
                                <div className="flex items-center space-x-4">
                                    {loading && (
                                        <span className="animate-pulse">Loading progress...</span>
                                    )}
                                </div>

                                {progressData?.last_updated && (
                                    <span className="text-xs">
                                        Updated: {new Date(progressData.last_updated).toLocaleTimeString()}
                                    </span>
                                )}
                            </div>
                        </div>
                    )}

                    {/* Count Data Section */}
                    {status === 'completed' ? (
                        <div ref={tableSectionRef} className="relative">
                            {/* Pattern Selection Panel - Always show if initial groups are available */}
                            {initialSampleGroups.length > 0 && (
                                <PatternSelectionPanel
                                    groups={initialSampleGroups}
                                    isExpanded={isPatternPanelExpanded}
                                    onToggle={() => setPatternPanelExpanded(!isPatternPanelExpanded)}
                                    onAnalyze={handlePatternAnalysis}
                                />
                            )}

                            {/* Controls */}
                            <div className="mb-4 flex items-center justify-between">
                                <div className="flex flex-wrap items-center gap-5">
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
                                        disabled={loadingResults}
                                        className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed font-medium text-sm"
                                    >
                                        Search
                                    </button>
                                    {activeSearch && (
                                        <button
                                            onClick={handleClearSearch}
                                            disabled={loadingResults}
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
                                        disabled={loadingResults || !countsResults}
                                        className="flex items-center gap-2 rounded-lg bg-green-600 px-4 py-2 text-white transition-colors hover:bg-green-700 disabled:cursor-not-allowed disabled:opacity-50"
                                        title={
                                            selectedGenes.size > 0
                                                ? `Download selected genes (${selectedGenes.size})`
                                                : (activeSearch ? 'Download filtered results' : `Download ${selectedMatrixType} results`)
                                        }
                                    >
                                        <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                                        </svg>
                                        <span>Download {selectedGenes.size > 0 ? `(${selectedGenes.size})` : ''}</span>
                                        {selectedGenes.size === 0 && activeSearch && <span className="text-xs opacity-80">(Filtered)</span>}
                                    </button>
                                </div>
                                <div className="flex items-center space-x-4">
                                    <MatrixTypeSelector
                                        selectedType={selectedMatrixType}
                                        onTypeChange={handleMatrixTypeChange}
                                        disabled={loadingResults}
                                        hasTPMMatrix={hasTPMMatrix}
                                    />
                                </div>
                            </div>

                            {/* Search Results Info */}
                            {countsResults?.is_search_result && (
                                <div className="mb-4 p-3 bg-blue-50 border border-blue-200 rounded-lg">
                                    <div className="flex items-center justify-between">
                                        <span className="text-sm text-blue-800">
                                            🔍 {countsResults.search_query}: {countsResults.total_genes.toLocaleString()} gene{countsResults.total_genes !== 1 ? 's' : ''} found
                                        </span>
                                        <div className="flex items-center gap-2">
                                            {activeSearch && (
                                                <button
                                                    onClick={handleClearSearch}
                                                    className="text-xs text-blue-600 hover:text-blue-800 underline"
                                                >
                                                    Clear filter
                                                </button>
                                            )}
                                            {isPatternAnalysisActive && (
                                                <button
                                                    onClick={() => {
                                                        setPatternAnalysisActive(false);
                                                        setPatternFullResults(null);
                                                        setActiveSearch('');
                                                        setSelectAllState(0);
                                                        if (searchInputRef.current) {
                                                            searchInputRef.current.value = '';
                                                        }
                                                        fetchCountResults(selectedMatrixType, 1, '', pageSize);
                                                    }}
                                                    className="text-xs text-red-600 hover:text-red-800 underline font-medium"
                                                >
                                                    Reset to all genes
                                                </button>
                                            )}
                                        </div>
                                    </div>
                                </div>
                            )}

                            {/* Pagination - Top */}
                            {countsResults && countsResults.total_pages > 0 && (
                                <Pagination
                                    currentPage={effectiveCurrentPage}
                                    totalPages={effectiveTotalPages}
                                    onPageChange={handlePageChange}
                                    pageSize={pageSize}
                                    onPageSizeChange={handlePageSizeChange}
                                    totalCount={effectiveTotalCount}
                                />
                            )}

                            {/* Data Table or No Results Message */}
                            {countsResults?.is_search_result && countsResults.total_genes === 0 ? (
                                <div className="text-center py-12">
                                    <div className="text-slate-400 mb-4">
                                        <svg className="w-16 h-16 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                                        </svg>
                                    </div>
                                    <h4 className="text-lg font-medium text-slate-900 mb-2">No genes found</h4>
                                    <p className="text-slate-500 mb-4">No genes match your search criteria "{countsResults.search_query}"</p>
                                    <button
                                        onClick={handleClearSearch}
                                        className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                                    >
                                        Clear Search
                                    </button>
                                </div>
                            ) : (
                            <div className="border border-slate-200 rounded-lg overflow-visible bg-white">
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
                                            {displayedData.map((item) => (
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
                                                            const samples = countsResults?.samples || [];
                                                            const values = samples.map(sample => {
                                                                const value = item[sample];
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
                                                            }
                                                            return <span className="text-xs text-slate-400">N/A</span>;
                                                        })()}
                                                    </td>
                                                    {(countsResults?.samples || []).map(sample => {
                                                        const isColumnSelected = selectedColumns.has(sample);
                                                        return (
                                                            <td
                                                                key={sample}
                                                                className="px-3 py-3 whitespace-nowrap text-sm transition-colors"
                                                                style={{
                                                                    backgroundColor: isColumnSelected ? 'rgb(219 234 254)' : 'transparent',
                                                                    color: isColumnSelected ? 'rgb(30 64 175)' : 'rgb(100 116 139)'
                                                                }}
                                                            >
                                                                {formatMatrixValue(item[sample])}
                                                            </td>
                                                        );
                                                    })}
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                            )}
                        </div>
                    ) : (
                        <div className="text-center py-12">
                            <div className="text-slate-400 mb-4">
                                <svg className="w-16 h-16 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                                </svg>
                            </div>
                            <h4 className="text-lg font-medium text-slate-900 mb-2">
                                {status === 'running' ? 'Quantifying Gene Expression...' : 'Waiting for Count Quantification'}
                            </h4>
                            <p className="text-slate-500">
                                {status === 'running'
                                    ? `${toolName !== 'Unknown' ? toolName.toUpperCase() : 'Count tool'} is currently quantifying gene expression from aligned reads`
                                    : 'Gene expression quantification will begin after read alignment completes'
                                }
                            </p>
                        </div>
                    )}
                </div>
            </div>

            {overlayHeader.visible && typeof document !== 'undefined' && createPortal(
                <div
                    className="fixed z-[120] pointer-events-none"
                    style={{ top: overlayHeader.top, left: overlayHeader.left, width: overlayHeader.width }}
                >
                    <div
                        ref={floatingTopScrollbarRef}
                        className="overflow-x-auto overflow-y-hidden bg-slate-50 border border-slate-200 border-b-0 rounded-t-lg pointer-events-auto"
                        style={{ width: `${overlayHeader.width}px` }}
                    >
                        <div style={{ width: `${overlayHeader.tableWidth}px`, height: '16px' }} />
                    </div>
                    <div className="relative" style={{ width: `${overlayHeader.width}px`, height: `${overlayHeader.height || 57}px` }}>
                        <div
                            className="absolute top-0 left-0 overflow-hidden border-x border-b border-slate-200 bg-slate-50 shadow-sm"
                            style={{ width: `${Math.min(fixedHeaderWidth, overlayHeader.width)}px` }}
                        >
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
                        <div
                            className="absolute top-0 overflow-hidden border-r border-b border-slate-200 bg-slate-50 shadow-sm"
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
                                        {(countsResults?.samples || []).map(sample => (
                                            <col key={sample} style={{ width: `${tableColumnWidths.sample}px` }} />
                                        ))}
                                    </colgroup>
                                    <thead>
                                        <tr>
                                            {(countsResults?.samples || []).map(name => {
                                                const isSelected = selectedColumns.has(name);
                                                return (
                                                    <th
                                                        key={name}
                                                        className="px-3 py-3 text-left text-xs font-bold uppercase tracking-wider"
                                                        style={{
                                                            width: `${tableColumnWidths.sample}px`,
                                                            minWidth: `${tableColumnWidths.sample}px`,
                                                            backgroundColor: isSelected ? 'rgb(219 234 254)' : 'rgb(248 250 252)',
                                                            color: isSelected ? 'rgb(30 64 175)' : 'rgb(71 85 105)'
                                                        }}
                                                    >
                                                        {name}
                                                    </th>
                                                );
                                            })}
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
                workbenchId={workbench.id}
                comparisonName=""
                toolName={toolName}
            />

            {/* Heatmap Analysis Modal */}
            <HeatmapAnalysisModal
                isOpen={analysisHeatmapOpen}
                onClose={closeAnalysisHeatmap}
                workbenchId={workbench.id}
                selectedGenes={Array.from(selectedGenes)}
                comparisonName=""
                toolName={toolName}
            />

            {/* KEGG Pathway Modal */}
            <KEGGPathwayModal
                isOpen={analysisKEGGOpen}
                onClose={closeAnalysisKEGG}
                workbenchId={workbench.id}
                selectedGenes={Array.from(selectedGenes)}
                comparisonName=""
                toolName={toolName}
            />
        </div>
        </>
    );
};

export default WorkbenchDetailCounts;
