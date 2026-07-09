import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { createPortal } from 'react-dom';
import { ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, ZAxis, ReferenceLine, Label } from 'recharts';
import { apiService } from '../services/api';
import MiniHeatmap from './MiniHeatmap';
import ColumnFilterPopup, { ColumnFilter } from './ColumnFilterPopup';
import GOAnalysisModal from './GOAnalysisModal';
import GOProviderSubmenu from './GOProviderSubmenu';
import CopyGeneListMenuItem from './CopyGeneListMenuItem';
import HeatmapAnalysisModal from './HeatmapAnalysisModal';
import KEGGPathwayModal from './KEGGPathwayModal';
import ChartExportModal, { ChartExportOptions } from './ChartExportModal';
import SelectableGeneTableShell from './SelectableGeneTableShell';
import { useGeneAnalysisActions } from '../hooks/useGeneAnalysisActions';

interface WorkbenchDetailDEGVolcanoProps {
    workbenchId: number;
    comparisonName: string;
    toolName: string;
    selectedGenes: Set<string>;
    onSelectionChange: (genes: Set<string>) => void;
    onAnalysisRequest: (type: string) => void;
    showComingSoon: () => void;
}

interface FilterConfig {
    [columnName: string]: ColumnFilter;
}

interface VolcanoPlotDataPoint {
    gene_id: string;
    gene_symbol: string;
    logFC: number;
    neg_log10_pval: number;
    fdr: number;
    significant: boolean;
}

interface SignificantGene {
    GeneID: string;
    GeneSymbol: string;
    GeneDescription: string;
    logFC: number;
    logCPM: number;
    PValue: number;
    FDR: number;
}

interface SignificantGenesResponse {
    comparison: string;
    tool_name: string;
    data: SignificantGene[];
    total: number;
    page: number;
    limit: number;
    columns: string[];
    samples?: string[];
    filter_type: string;
}

type VolcanoDotSizePreset = 'tiny' | 'small' | 'medium' | 'large' | 'xlarge';
type VolcanoColorTarget = 'upregulated' | 'downregulated' | 'significant' | 'background';

const VOLCANO_DOT_SIZE_OPTIONS: Array<{
    value: VolcanoDotSizePreset;
    label: string;
    majorRadius: number;
    neutralRadius: number;
    backgroundRadius: number;
}> = [
    { value: 'tiny', label: 'Tiny', majorRadius: 3, neutralRadius: 2.3, backgroundRadius: 1.5 },
    { value: 'small', label: 'Small', majorRadius: 4, neutralRadius: 3, backgroundRadius: 2 },
    { value: 'medium', label: 'Medium', majorRadius: 5.5, neutralRadius: 4, backgroundRadius: 2.5 },
    { value: 'large', label: 'Large', majorRadius: 7, neutralRadius: 5.2, backgroundRadius: 3.5 },
    { value: 'xlarge', label: 'XL', majorRadius: 8.5, neutralRadius: 6.5, backgroundRadius: 4.5 }
];

const COLOR_COLUMNS = ['A', 'B', 'C', 'D', 'E', 'F', 'G'];
const COLOR_PALETTE: string[][] = [
    ['#ffffff', '#e0e0e0', '#c0c0c0', '#a0a0a0', '#808080', '#404040', '#000000'],
    ['#f5f5dc', '#e6ccb2', '#b28d66', '#cc9966', '#cc6600', '#996633', '#666633'],
    ['#ffe6e6', '#ffcccc', '#ff9999', '#ff6666', '#ff0000', '#cc0000', '#990000'],
    ['#fff0e6', '#ffe0cc', '#ffb380', '#ff8833', '#ff6600', '#cc5200', '#993d00'],
    ['#ffffe6', '#ffffcc', '#ffff80', '#ffff33', '#ffff00', '#cccc00', '#999900'],
    ['#e6ffe6', '#ccffcc', '#80ff80', '#33ff33', '#00ff00', '#00cc00', '#009900'],
    ['#e6f9e6', '#cceecc', '#80cc80', '#33b333', '#008000', '#006600', '#004d00'],
    ['#e6ffff', '#ccffff', '#80ffff', '#33ffff', '#00ffff', '#00cccc', '#009999'],
    ['#e6f2ff', '#cce0ff', '#80bfff', '#3399ff', '#0073e6', '#0059b3', '#004080'],
    ['#e6e6ff', '#ccccff', '#8080ff', '#3333ff', '#0000ff', '#0000cc', '#000099'],
    ['#f2e6ff', '#e0ccff', '#bf80ff', '#9933ff', '#7300e6', '#5900b3', '#400080'],
    ['#ffe6ff', '#ffccff', '#ff80ff', '#ff33ff', '#ff00ff', '#cc00cc', '#990099']
];

// Pagination Component
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

const WorkbenchDetailDEGVolcano: React.FC<WorkbenchDetailDEGVolcanoProps> = ({
    workbenchId,
    comparisonName,
    toolName,
    selectedGenes,
    onSelectionChange,
    onAnalysisRequest,
    showComingSoon
}) => {
    // Volcano Plot data states
    const [plotData, setPlotData] = useState<VolcanoPlotDataPoint[]>([]);
    const [isPlotLoading, setIsPlotLoading] = useState(true);
    const [isPlotRendering, setIsPlotRendering] = useState(false);
    const [plotError, setPlotError] = useState<string | null>(null);
    const [loadingStatus, setLoadingStatus] = useState<string>('Preparing...');

    // Chart display limit control
    const [chartDisplayLimit, setChartDisplayLimit] = useState<number | 'all'>(100);
    const [chartHeight, setChartHeight] = useState<number>(500);
    const [yAxisWidth, setYAxisWidth] = useState<number>(72);
    const [dotSizePreset, setDotSizePreset] = useState<VolcanoDotSizePreset>('medium');
    const [upDotColor, setUpDotColor] = useState<string>('#dc2626');
    const [downDotColor, setDownDotColor] = useState<string>('#2563eb');
    const [significantDotColor, setSignificantDotColor] = useState<string>('#f59e0b');
    const [backgroundDotColor, setBackgroundDotColor] = useState<string>('#94a3b8');
    const [activeColorTarget, setActiveColorTarget] = useState<VolcanoColorTarget>('upregulated');
    const [isColorPaletteOpen, setIsColorPaletteOpen] = useState(false);
    const [isDotSizeMenuOpen, setIsDotSizeMenuOpen] = useState(false);
    const [isExportModalOpen, setIsExportModalOpen] = useState(false);
    const [isExportingFigure, setIsExportingFigure] = useState(false);
    const chartAreaRef = useRef<HTMLDivElement>(null);
    const paletteRef = useRef<HTMLDivElement>(null);
    const dotSizeMenuRef = useRef<HTMLDivElement>(null);

    // Significant genes table states
    const [significantGenes, setSignificantGenes] = useState<SignificantGenesResponse | null>(null);
    const [isTableLoading, setIsTableLoading] = useState(false);
    const searchInputRef = useRef<HTMLTextAreaElement>(null);
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
    const tableSectionRef = useRef<HTMLDivElement | null>(null);
    const tableWrapperRef = useRef<HTMLDivElement | null>(null);
    const tableRef = useRef<HTMLTableElement | null>(null);
    const tableTheadRef = useRef<HTMLTableSectionElement | null>(null);

    // TMM counts for mini heatmap
    const [tmmCounts, setTmmCounts] = useState<Map<string, number[]>>(new Map());
    const [tmmSampleNames, setTmmSampleNames] = useState<string[]>([]);

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
        description: `Significant genes from ${comparisonName}`,
    });

    // Fetch Volcano Plot data for chart
    const fetchVolcanoPlotData = useCallback(async () => {
        try {
            setIsPlotLoading(true);
            setIsPlotRendering(false);
            setPlotError(null);
            setLoadingStatus('Fetching expression data...');

            const response = await apiService.fetchDEGResults(workbenchId, comparisonName, {
                tool_name: toolName,
                data_type: 'volcano_plot'
            });

            const dataCount = response.returned || response.data?.length || 0;
            setLoadingStatus(`Processing ${dataCount.toLocaleString()} genes...`);
            setPlotData(response.data || []);

            setIsPlotLoading(false);
            setIsPlotRendering(true);
            setLoadingStatus('Rendering chart...');

            // Wait for chart rendering
            setTimeout(() => {
                setIsPlotRendering(false);
            }, 800);
        } catch (err) {
            console.error('Failed to fetch volcano plot data:', err);
            setPlotError('Failed to load volcano plot data');
            setPlotData([]);
            setIsPlotLoading(false);
            setIsPlotRendering(false);
        }
    }, [workbenchId, comparisonName, toolName]);

    // Fetch significant genes table data
    const fetchSignificantGenes = useCallback(async (
        page: number = 1,
        search: string = '',
        columnFilters: FilterConfig = {},
        sortColumn: string | null = null,
        sortDirection: 'asc' | 'desc' = 'asc',
        customPageSize?: number
    ) => {
        setIsTableLoading(true);
        try {
            const effectivePageSize = customPageSize || pageSize;
            const params = new URLSearchParams({
                tool_name: toolName,
                page: page.toString(),
                limit: effectivePageSize.toString(),
                filter_type: 'significant',
                data_type: 'matrix'
            });

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
                setSignificantGenes(data);

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
                            const tmmMap = new Map<string, number[]>();
                            Object.entries(tmmResponse.data).forEach(([geneId, values]) => {
                                tmmMap.set(geneId, values as number[]);
                            });
                            setTmmCounts(tmmMap);
                            setTmmSampleNames(tmmResponse.sample_names);
                        }
                    } catch (tmmError) {
                        console.error('Failed to fetch TMM counts:', tmmError);
                    }
                }
            }
        } catch (error) {
            console.error('Failed to fetch significant genes:', error);
        } finally {
            setIsTableLoading(false);
        }
    }, [workbenchId, comparisonName, toolName, pageSize]);

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

    useEffect(() => {
        const handleClickOutside = (event: MouseEvent) => {
            if (paletteRef.current && !paletteRef.current.contains(event.target as Node)) {
                setIsColorPaletteOpen(false);
            }
            if (dotSizeMenuRef.current && !dotSizeMenuRef.current.contains(event.target as Node)) {
                setIsDotSizeMenuOpen(false);
            }
        };
        document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, []);

    // Initial load
    useEffect(() => {
        // Reset states
        setCurrentPage(1);
        setActiveSearch('');
        setFilters({});
        setSortBy(null);
        setSortOrder('asc');
        setSelectAllState(0);
        onSelectionChange(new Set());
        if (searchInputRef.current) {
            searchInputRef.current.value = '';
        }

        // Fetch data
        fetchVolcanoPlotData();
        fetchSignificantGenes(1, '', {}, null, 'asc');
    }, [comparisonName, toolName]);

    // Statistics
    const significantData = plotData.filter(d => d.significant);
    const upregulatedData = significantData.filter(d => d.logFC > 1);
    const downregulatedData = significantData.filter(d => d.logFC < -1);
    const dotSizeConfig = useMemo(
        () => VOLCANO_DOT_SIZE_OPTIONS.find((option) => option.value === dotSizePreset) ?? VOLCANO_DOT_SIZE_OPTIONS[2],
        [dotSizePreset]
    );
    const legendItems = useMemo(() => ([
        { key: 'up', label: 'Upregulated (logFC > 1)', color: upDotColor },
        { key: 'down', label: 'Downregulated (logFC < -1)', color: downDotColor },
        { key: 'sig', label: 'Significant (|logFC| <= 1)', color: significantDotColor },
        { key: 'bg', label: 'Background (not significant)', color: backgroundDotColor }
    ]), [upDotColor, downDotColor, significantDotColor, backgroundDotColor]);

    // Volcano Plot chart data: Show only top N significant genes (by FDR)
    const chartSignificantData = useMemo(() => {
        const sorted = [...significantData].sort((a, b) => a.fdr - b.fdr);
        return chartDisplayLimit === 'all' ? sorted : sorted.slice(0, chartDisplayLimit);
    }, [significantData, chartDisplayLimit]);

    // Enriched data for chart
    const enrichedData = useMemo(() => {
        return [
            // Non-significant first (background)
            ...plotData.filter(d => !d.significant).map(d => ({
                ...d,
                fill: backgroundDotColor,
                size: dotSizeConfig.backgroundRadius
            })),
            // Significant (limited) on top
            ...chartSignificantData.map(d => {
                let pointColor = significantDotColor;
                let pointSize = dotSizeConfig.neutralRadius;

                if (d.logFC > 1) {
                    pointColor = upDotColor;
                    pointSize = dotSizeConfig.majorRadius;
                } else if (d.logFC < -1) {
                    pointColor = downDotColor;
                    pointSize = dotSizeConfig.majorRadius;
                } else {
                    pointColor = significantDotColor;
                    pointSize = dotSizeConfig.neutralRadius;
                }

                return {
                    ...d,
                    fill: pointColor,
                    size: pointSize
                };
            })
        ];
    }, [plotData, chartSignificantData, dotSizeConfig, upDotColor, downDotColor, significantDotColor, backgroundDotColor]);

    const applySelectedColor = (color: string) => {
        if (activeColorTarget === 'upregulated') {
            setUpDotColor(color);
        } else if (activeColorTarget === 'downregulated') {
            setDownDotColor(color);
        } else if (activeColorTarget === 'significant') {
            setSignificantDotColor(color);
        } else {
            setBackgroundDotColor(color);
        }
        setIsColorPaletteOpen(false);
    };

    const handleYAxisResizeStart = (event: React.MouseEvent<HTMLDivElement>) => {
        event.preventDefault();

        const startX = event.clientX;
        const startWidth = yAxisWidth;
        const containerWidth = chartAreaRef.current?.clientWidth ?? 1200;
        const minWidth = 56;
        const maxWidth = Math.max(70, containerWidth - 180);

        const onMouseMove = (moveEvent: MouseEvent) => {
            const nextWidth = Math.max(minWidth, Math.min(maxWidth, startWidth + (moveEvent.clientX - startX)));
            setYAxisWidth(nextWidth);
        };

        const onMouseUp = () => {
            window.removeEventListener('mousemove', onMouseMove);
            window.removeEventListener('mouseup', onMouseUp);
        };

        window.addEventListener('mousemove', onMouseMove);
        window.addEventListener('mouseup', onMouseUp);
    };

    const handleXAxisHeightResizeStart = (event: React.MouseEvent<HTMLDivElement>) => {
        event.preventDefault();
        event.stopPropagation();

        const startY = event.clientY;
        const startHeight = chartHeight;
        const minHeight = 280;
        const maxHeight = 1400;

        const onMouseMove = (moveEvent: MouseEvent) => {
            const deltaY = moveEvent.clientY - startY;
            const nextHeight = Math.max(minHeight, Math.min(maxHeight, startHeight + deltaY));
            setChartHeight(nextHeight);
        };

        const onMouseUp = () => {
            window.removeEventListener('mousemove', onMouseMove);
            window.removeEventListener('mouseup', onMouseUp);
        };

        window.addEventListener('mousemove', onMouseMove);
        window.addEventListener('mouseup', onMouseUp);
    };

    const handleExportFigure = useCallback(async (options: ChartExportOptions) => {
        if (!chartAreaRef.current) return;

        setIsExportingFigure(true);
        try {
            const { toPng, toSvg } = await import('html-to-image');
            const filter = (node: HTMLElement) => !node.classList?.contains('no-export');
            const backgroundColor = options.background === 'transparent' ? 'transparent' : '#ffffff';
            const sourceWidth = Math.max(1, Math.round(chartAreaRef.current.clientWidth));
            const sourceHeight = Math.max(1, Math.round(chartAreaRef.current.clientHeight));
            const exportBlob = await (options.format === 'svg'
                ? (() => {
                    const svgDataUrlPromise = toSvg(chartAreaRef.current as HTMLElement, {
                        cacheBust: true,
                        backgroundColor,
                        filter
                    });
                    return svgDataUrlPromise.then((dataUrl) => {
                        const commaIndex = dataUrl.indexOf(',');
                        const header = dataUrl.slice(0, commaIndex);
                        const payload = dataUrl.slice(commaIndex + 1);
                        const rawSvgText = header.includes(';base64')
                            ? atob(payload)
                            : decodeURIComponent(payload);

                        const patchedSvgText = rawSvgText.replace(/<svg\b([^>]*)>/i, (_match, attrs) => {
                            let nextAttrs = attrs;
                            if (/width="[^"]*"/i.test(nextAttrs)) {
                                nextAttrs = nextAttrs.replace(/width="[^"]*"/i, `width="${options.widthPx}"`);
                            } else {
                                nextAttrs += ` width="${options.widthPx}"`;
                            }
                            if (/height="[^"]*"/i.test(nextAttrs)) {
                                nextAttrs = nextAttrs.replace(/height="[^"]*"/i, `height="${options.heightPx}"`);
                            } else {
                                nextAttrs += ` height="${options.heightPx}"`;
                            }
                            if (!/viewBox="[^"]*"/i.test(nextAttrs)) {
                                nextAttrs += ` viewBox="0 0 ${sourceWidth} ${sourceHeight}"`;
                            }
                            if (/preserveAspectRatio="[^"]*"/i.test(nextAttrs)) {
                                nextAttrs = nextAttrs.replace(/preserveAspectRatio="[^"]*"/i, 'preserveAspectRatio="none"');
                            } else {
                                nextAttrs += ' preserveAspectRatio="none"';
                            }
                            return `<svg${nextAttrs}>`;
                        });

                        return new Blob([patchedSvgText], { type: 'image/svg+xml;charset=utf-8' });
                    });
                })()
                : (async () => {
                    const basePngDataUrl = await toPng(chartAreaRef.current as HTMLElement, {
                        cacheBust: true,
                        backgroundColor,
                        pixelRatio: 1,
                        filter
                    });

                    const image = new Image();
                    image.src = basePngDataUrl;
                    await new Promise<void>((resolve, reject) => {
                        image.onload = () => resolve();
                        image.onerror = () => reject(new Error('Failed to load base PNG for resize'));
                    });

                    const dpiScale = Math.max(1, options.dpi / 96);
                    const targetWidth = Math.max(1, Math.round(options.widthPx * dpiScale));
                    const targetHeight = Math.max(1, Math.round(options.heightPx * dpiScale));
                    const canvas = document.createElement('canvas');
                    canvas.width = targetWidth;
                    canvas.height = targetHeight;
                    const ctx = canvas.getContext('2d');
                    if (!ctx) throw new Error('Failed to create export canvas');

                    if (options.background !== 'transparent') {
                        ctx.fillStyle = '#ffffff';
                        ctx.fillRect(0, 0, targetWidth, targetHeight);
                    } else {
                        ctx.clearRect(0, 0, targetWidth, targetHeight);
                    }

                    ctx.drawImage(image, 0, 0, targetWidth, targetHeight);
                    const pngBlob = await new Promise<Blob>((resolve, reject) => {
                        canvas.toBlob((blob) => {
                            if (blob) resolve(blob);
                            else reject(new Error('Failed to encode PNG blob'));
                        }, 'image/png');
                    });

                    return pngBlob;
                })());

            const objectUrl = URL.createObjectURL(exportBlob);
            const link = document.createElement('a');
            link.href = objectUrl;
            link.download = `${options.filename}.${options.format}`;
            link.click();
            window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
            setIsExportModalOpen(false);
        } catch (error) {
            console.error('Failed to export volcano plot figure:', error);
            alert('Failed to export volcano plot figure. Please try again.');
        } finally {
            setIsExportingFigure(false);
        }
    }, []);

    const renderYAxisLabel = (props: any) => {
        const viewBox = props?.viewBox;
        if (!viewBox) return null;

        const axisX = (viewBox.x ?? 0) + (viewBox.width ?? 0) - 8;
        const labelX = axisX - 36;
        const centerY = (viewBox.y ?? 0) + ((viewBox.height ?? 0) / 2);

        return (
            <text
                x={labelX}
                y={centerY}
                transform={`rotate(-90 ${labelX} ${centerY})`}
                textAnchor="middle"
                fill="#475569"
                fontSize={14}
            >
                -log10(p-value)
            </text>
        );
    };

    // Table data
    const tableData = useMemo(() => {
        if (!significantGenes?.data || significantGenes.data.length === 0) {
            return [];
        }

        return significantGenes.data.map(gene => ({
            gene: gene.GeneID,
            gene_symbol: gene.GeneSymbol,
            gene_description: gene.GeneDescription,
            logFC: gene.logFC,
            logCPM: gene.logCPM,
            PValue: gene.PValue,
            FDR: gene.FDR
        }));
    }, [significantGenes]);

    const tableColumnWidths = {
        select: 48,
        geneId: 180,
        geneSymbol: 180,
        pattern: 260,
        metric: 110,
        regulation: 120
    } as const;

    const tableColGroup = (
        <colgroup>
            <col style={{ width: `${tableColumnWidths.select}px` }} />
            <col style={{ width: `${tableColumnWidths.geneId}px` }} />
            <col style={{ width: `${tableColumnWidths.geneSymbol}px` }} />
            <col style={{ width: `${tableColumnWidths.pattern}px` }} />
            <col style={{ width: `${tableColumnWidths.metric}px` }} />
            <col style={{ width: `${tableColumnWidths.metric}px` }} />
            <col style={{ width: `${tableColumnWidths.metric}px` }} />
            <col style={{ width: `${tableColumnWidths.metric}px` }} />
            <col style={{ width: `${tableColumnWidths.regulation}px` }} />
        </colgroup>
    );

    // Fetch all gene IDs across all pages
    const fetchAllGeneIds = useCallback(async (): Promise<string[]> => {
        const total = significantGenes?.total || 0;
        const params = new URLSearchParams({
            tool_name: toolName,
            page: '1',
            limit: total.toString(),
            filter_type: 'significant',
            data_type: 'matrix'
        });
        if (activeSearch) params.append('search', activeSearch);
        if (Object.keys(filters).length > 0) params.append('filters', JSON.stringify(filters));
        if (sortBy) {
            params.append('sort_by', sortBy);
            params.append('sort_order', sortOrder);
        }
        try {
            const response = await fetch(
                `/api/workbenches/${workbenchId}/deg/results/${comparisonName}?${params}`,
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
    }, [workbenchId, comparisonName, toolName, significantGenes?.total, activeSearch, filters, sortBy, sortOrder]);

    // 3-state Select All cycle handler
    const handleSelectAllCycle = useCallback(async () => {
        if (selectAllState === 0) {
            // State 0 ??1: Select current page
            const newSelected = new Set(selectedGenes);
            tableData.forEach(item => newSelected.add(item.gene));
            onSelectionChange(newSelected);
            setSelectAllState(1);
        } else if (selectAllState === 1) {
            // State 1 ??2: Select all pages via API
            setIsTableLoading(true);
            const allIds = await fetchAllGeneIds();
            onSelectionChange(new Set<string>(allIds));
            setSelectAllState(2);
            setIsTableLoading(false);
        } else {
            // State 2 ??0: Deselect all
            onSelectionChange(new Set());
            setSelectAllState(0);
        }
    }, [selectAllState, tableData, selectedGenes, onSelectionChange, fetchAllGeneIds]);

    // Selection handler
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
            onSelectionChange(new Set());
            fetchSignificantGenes(1, searchValue, filters, sortBy, sortOrder);
        }
    };

    const handleClearSearch = () => {
        if (searchInputRef.current) {
            searchInputRef.current.value = '';
        }
        setActiveSearch('');
        setCurrentPage(1);
        onSelectionChange(new Set());
        fetchSignificantGenes(1, '', filters, sortBy, sortOrder);
    };

    // Pagination handlers
    const handlePageChange = (newPage: number) => {
        setCurrentPage(newPage);
        onSelectionChange(new Set());
        fetchSignificantGenes(newPage, activeSearch, filters, sortBy, sortOrder);
        window.scrollTo({ top: 0, behavior: 'smooth' });
    };

    const handlePageSizeChange = (newSize: number) => {
        setPageSize(newSize);
        setCurrentPage(1);
        onSelectionChange(new Set());
        fetchSignificantGenes(1, activeSearch, filters, sortBy, sortOrder, newSize);
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
        onSelectionChange(new Set());
        fetchSignificantGenes(1, activeSearch, newFilters, newSortBy, newSortOrder);
    }, [filters, sortBy, sortOrder, activeSearch, fetchSignificantGenes, onSelectionChange]);

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
            <th className="px-4 py-3 text-left text-xs font-semibold text-slate-700 uppercase tracking-wider" style={{ width: `${tableColumnWidths.select}px`, backgroundColor: 'rgb(248 250 252)' }}>
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
            <th className="px-4 py-3 text-left text-xs font-semibold text-slate-700 uppercase tracking-wider" style={{ width: `${tableColumnWidths.geneId}px`, minWidth: `${tableColumnWidths.geneId}px`, backgroundColor: 'rgb(248 250 252)' }}>
                Gene ID
            </th>
            <th className="px-4 py-3 text-left text-xs font-semibold text-slate-700 uppercase tracking-wider" style={{ width: `${tableColumnWidths.geneSymbol}px`, minWidth: `${tableColumnWidths.geneSymbol}px`, backgroundColor: 'rgb(248 250 252)' }}>
                Gene Symbol
            </th>
            <th className="px-4 py-3 text-left text-xs font-semibold text-slate-700 uppercase tracking-wider" style={{ width: `${tableColumnWidths.pattern}px`, minWidth: `${tableColumnWidths.pattern}px`, backgroundColor: 'rgb(248 250 252)' }}>
                Expression Pattern
            </th>
            {['logFC', 'logCPM', 'PValue', 'FDR'].map(column => {
                const hasFilter = !!filters[column];
                const hasSort = sortBy === column;
                const isActive = hasFilter || hasSort;

                return (
                    <th
                        key={column}
                        className="px-4 py-3 text-left text-xs font-semibold text-slate-700 uppercase tracking-wider"
                        style={{ width: `${tableColumnWidths.metric}px`, minWidth: `${tableColumnWidths.metric}px`, backgroundColor: 'rgb(248 250 252)' }}
                    >
                        <div className="flex items-center relative">
                            <span>{column}</span>
                            {hasSort && (
                                <span className="ml-1 text-blue-600 font-bold text-base">
                                    {sortOrder === 'asc' ? '^' : 'v'}
                                </span>
                            )}
                            <div className="relative">
                                <button
                                    onClick={() => setActiveFilterColumn(column)}
                                    className={`ml-1 p-1 rounded transition-colors ${
                                        isActive
                                            ? 'text-blue-600 bg-blue-50'
                                            : 'text-slate-400 hover:bg-slate-100'
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
            <th className="px-4 py-3 text-left text-xs font-semibold text-slate-700 uppercase tracking-wider" style={{ width: `${tableColumnWidths.regulation}px`, minWidth: `${tableColumnWidths.regulation}px`, backgroundColor: 'rgb(248 250 252)' }}>
                Regulation
            </th>
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

        const readMetrics = () => {
            if (scrollTarget === window) {
                return {
                    target: 'window',
                    scrollTop: window.scrollY || document.documentElement.scrollTop || document.body.scrollTop || 0,
                    clientHeight: window.innerHeight,
                    scrollHeight: Math.max(document.documentElement.scrollHeight, document.body.scrollHeight)
                };
            }

            return {
                target: 'element',
                scrollTop: scrollTarget.scrollTop,
                clientHeight: scrollTarget.clientHeight,
                scrollHeight: scrollTarget.scrollHeight
            };
        };

        const updateVisibility = () => {
            const metrics = readMetrics();
            setShowScrollToTopButton(metrics.scrollTop > 320);
        };

        updateVisibility();
        scrollTarget.addEventListener('scroll', updateVisibility, { passive: true });
        return () => {
            scrollTarget.removeEventListener('scroll', updateVisibility);
            if (scrollTargetRef.current === scrollTarget) {
                scrollTargetRef.current = null;
            }
        };
    }, [comparisonName, currentPage, pageSize, tableData.length, isPlotLoading, isPlotRendering, plotError, plotData.length]);

    useEffect(() => {
        const section = tableSectionRef.current;
        const table = tableRef.current;
        const thead = tableTheadRef.current;

        if (!section || !table || !thead || tableData.length === 0) {
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
    }, [comparisonName, currentPage, pageSize, tableData.length, isPlotLoading, isPlotRendering, plotError, plotData.length]);

    // GO Analysis
    const handleGOAnalysis = async (provider: 'david' | 'gprofiler') => {
        const genes = Array.from(selectedGenes);

        setGOLoading(true);
        setGOModalOpen(true);

        try {
            const result = await apiService.runGOEnrichment(workbenchId, {
                genes: genes,
                databases: ['GO_BP', 'GO_MF', 'GO_CC'],
                p_value_cutoff: 0.05,
                description: `Significant genes from ${comparisonName}`,
                organism: 'arabidopsis',
                provider
            });
            setGOAnalysisResult(result);
        } catch (error) {
            console.error('??[GO-ANALYSIS] Failed:', error);
        } finally {
            setGOLoading(false);
            setActionMenuOpen(false);
        }
    };

    // Download handler
    const handleDownload = useCallback(() => {
        if (!significantGenes?.data) return;

        const dataToDownload = selectedGenes.size > 0
            ? significantGenes.data.filter(gene => selectedGenes.has(gene.GeneID))
            : significantGenes.data;

        if (dataToDownload.length === 0) {
            alert('No data to download');
            return;
        }

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

        const timestamp = new Date().toISOString().slice(0, 10);
        const selectionType = selectedGenes.size > 0 ? `selected_${selectedGenes.size}` : 'all';
        const filename = `${comparisonName}_significant_genes_${selectionType}_${timestamp}.tsv`;

        const link = document.createElement('a');
        link.href = url;
        link.download = filename;
        link.click();

        URL.revokeObjectURL(url);
    }, [significantGenes, selectedGenes, comparisonName]);

    const getRegulationStatus = (d: { logFC: number }) => {
        if (d.logFC > 1) return { text: 'Upregulated', color: 'text-red-600' };
        if (d.logFC < -1) return { text: 'Downregulated', color: 'text-blue-600' };
        return { text: 'Significant', color: 'text-orange-600' };
    };

    // Threshold values
    const logFCThreshold = 1;
    const pvalThreshold = -Math.log10(0.05); // ??1.3

    // Custom tooltip
    const CustomTooltip = ({ active, payload }: any) => {
        if (active && payload && payload.length > 0) {
            const data = payload[0].payload;
            const geneValues = tmmCounts.get(data.gene_id);
            const showHeatmap = data.significant && geneValues && tmmSampleNames.length > 0;

            return (
                <div className="bg-white p-3 border border-slate-200 rounded-lg shadow-lg">
                    <div className="mb-2">
                        {data.gene_symbol && data.gene_symbol !== data.gene_id ? (
                            <>
                                <p className="font-semibold text-slate-800 italic">{data.gene_symbol}</p>
                                <p className="text-sm text-slate-500">{data.gene_id}</p>
                            </>
                        ) : (
                            <p className="font-semibold text-slate-800">{data.gene_id}</p>
                        )}
                    </div>
                    <p className="text-sm text-slate-600">
                        <span className="font-medium">logFC:</span> {data.logFC.toFixed(2)}
                    </p>
                    <p className="text-sm text-slate-600">
                        <span className="font-medium">-log10(p-value):</span> {data.neg_log10_pval.toFixed(2)}
                    </p>
                    <p className="text-sm text-slate-600">
                        <span className="font-medium">FDR:</span> {data.fdr.toExponential(2)}
                    </p>
                    {data.significant ? (
                        <p className="text-xs mt-2 text-green-600">
                            {data.logFC > 1 ? '??Upregulated (FDR < 0.05)' :
                             data.logFC < -1 ? '??Downregulated (FDR < 0.05)' :
                             '??Significant (FDR < 0.05)'}
                        </p>
                    ) : (
                        <p className="text-xs mt-2 text-slate-400">??Not significant</p>
                    )}

                    {/* Mini Heatmap for significant genes */}
                    {showHeatmap && (
                        <div className="mt-3 pt-3 border-t border-slate-200">
                            <p className="text-xs text-slate-600 mb-2">Expression Pattern:</p>
                            <MiniHeatmap
                                values={geneValues}
                                samples={tmmSampleNames}
                                width={Math.min(tmmSampleNames.length * 16, 240)}
                                height={20}
                            />
                        </div>
                    )}
                </div>
            );
        }
        return null;
    };

    if (isPlotLoading) {
        return (
            <div className="h-full flex items-center justify-center">
                <div className="text-center">
                    <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-blue-100 mb-4">
                        <svg className="animate-spin h-8 w-8 text-primary" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                        </svg>
                    </div>
                    <h3 className="text-lg font-semibold text-slate-900 mb-2">Loading Volcano Plot</h3>
                    <p className="text-sm text-slate-600">{loadingStatus}</p>
                    <p className="text-xs text-slate-500 mt-2">{comparisonName.replace(/_/g, ' ')}</p>
                </div>
            </div>
        );
    }

    if (plotError) {
        return (
            <div className="h-full flex items-center justify-center">
                <div className="text-center">
                    <svg className="mx-auto h-16 w-16 text-red-300 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    <h3 className="text-lg font-semibold text-slate-700 mb-2">Failed to Load Data</h3>
                    <p className="text-sm text-slate-500">{plotError}</p>
                </div>
            </div>
        );
    }

    if (plotData.length === 0) {
        return (
            <div className="h-full flex items-center justify-center">
                <div className="text-center">
                    <svg className="mx-auto h-16 w-16 text-slate-300 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z" />
                    </svg>
                    <h3 className="text-lg font-semibold text-slate-700 mb-2">No Data Available</h3>
                    <p className="text-sm text-slate-500">No volcano plot data found for {comparisonName}</p>
                </div>
            </div>
        );
    }

    return (
        <div ref={tableSectionRef} className="h-full flex flex-col p-6 relative">
            {/* Rendering overlay */}
            {isPlotRendering && (
                <div className="absolute inset-0 bg-white/80 backdrop-blur-sm z-50 flex items-center justify-center">
                    <div className="text-center">
                        <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-blue-100 mb-3">
                            <svg className="animate-spin h-6 w-6 text-primary" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                            </svg>
                        </div>
                        <p className="text-sm font-medium text-slate-700">{loadingStatus}</p>
                    </div>
                </div>
            )}

            <div className="mb-6">
                <div className="flex items-center justify-between mb-2">
                    <h3 className="text-lg font-semibold text-slate-900">Volcano Plot: {comparisonName.replace(/_/g, ' ')}</h3>

                    {/* Chart Controls */}
                    <div className="flex items-center gap-3 flex-wrap justify-end">
                        <div className="flex items-center space-x-2">
                            <span className="text-sm text-slate-600">Chart significant genes:</span>
                            <select
                                value={chartDisplayLimit}
                                onChange={(e) => setChartDisplayLimit(e.target.value === 'all' ? 'all' : Number(e.target.value))}
                                className="text-sm border border-slate-300 rounded px-3 py-1 focus:ring-1 focus:ring-primary focus:border-primary"
                            >
                                <option value={100}>Top 100</option>
                                <option value={300}>Top 300</option>
                                <option value={500}>Top 500</option>
                                <option value={1000}>Top 1,000</option>
                                <option value={2000}>Top 2,000</option>
                                <option value="all">All ({significantData.length.toLocaleString()})</option>
                            </select>
                        </div>
                        <div className="flex items-center space-x-2">
                            <span className="text-sm text-slate-600">Dot size:</span>
                            <div className="relative" ref={dotSizeMenuRef}>
                                <button
                                    type="button"
                                    onClick={() => {
                                        setIsDotSizeMenuOpen((open) => !open);
                                        setIsColorPaletteOpen(false);
                                    }}
                                    className="group flex items-center gap-2 text-sm border border-slate-300 rounded bg-white hover:bg-slate-50 min-w-[132px] h-[34px] overflow-hidden"
                                    title="Select dot size"
                                >
                                    <span className="inline-flex items-center justify-center w-6 h-5 ml-2">
                                        <span
                                            className="rounded-full border border-slate-400"
                                            style={{
                                                width: `${dotSizeConfig.majorRadius * 2}px`,
                                                height: `${dotSizeConfig.majorRadius * 2}px`,
                                                backgroundColor: upDotColor
                                            }}
                                        />
                                    </span>
                                    <span>{dotSizeConfig.label}</span>
                                    <span className="ml-auto h-full px-2.5 border-l border-slate-200 bg-slate-50 text-slate-500 group-hover:bg-slate-100 flex items-center">
                                        <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7" />
                                        </svg>
                                    </span>
                                </button>
                                {isDotSizeMenuOpen && (
                                    <div className="absolute right-0 top-full mt-2 z-40 min-w-[180px] rounded border border-slate-300 bg-white p-1 shadow-xl">
                                        {VOLCANO_DOT_SIZE_OPTIONS.map((option) => (
                                            <button
                                                key={option.value}
                                                type="button"
                                                onClick={() => {
                                                    setDotSizePreset(option.value);
                                                    setIsDotSizeMenuOpen(false);
                                                }}
                                                className={`w-full flex items-center gap-2 rounded px-2 py-1.5 text-left hover:bg-slate-100 ${
                                                    option.value === dotSizePreset ? 'bg-blue-50 text-blue-700' : 'text-slate-700'
                                                }`}
                                            >
                                                <span className="inline-flex items-center justify-center w-7 h-5">
                                                    <span
                                                        className="rounded-full border border-slate-400"
                                                        style={{
                                                            width: `${option.majorRadius * 2}px`,
                                                            height: `${option.majorRadius * 2}px`,
                                                            backgroundColor: upDotColor
                                                        }}
                                                    />
                                                </span>
                                                <span className="text-sm">{option.label}</span>
                                            </button>
                                        ))}
                                    </div>
                                )}
                            </div>
                        </div>
                        <div className="flex items-center space-x-2">
                            <span className="text-sm text-slate-600">Color target:</span>
                            <select
                                value={activeColorTarget}
                                onChange={(e) => setActiveColorTarget(e.target.value as VolcanoColorTarget)}
                                className="text-sm border border-slate-300 rounded px-2 py-1 focus:ring-1 focus:ring-primary focus:border-primary bg-white"
                            >
                                <option value="upregulated">Upregulated</option>
                                <option value="downregulated">Downregulated</option>
                                <option value="significant">Significant (|logFC| &le; 1)</option>
                                <option value="background">Background</option>
                            </select>
                        </div>
                        <div className="relative" ref={paletteRef}>
                            <button
                                type="button"
                                onClick={() => {
                                    setIsColorPaletteOpen((open) => !open);
                                    setIsDotSizeMenuOpen(false);
                                }}
                                className="flex items-center gap-2 text-sm border border-slate-300 rounded px-2 py-1 bg-white hover:bg-slate-50"
                                title="Select dot color"
                            >
                                <span
                                    className="inline-block h-4 w-4 rounded border border-slate-300"
                                    style={{
                                        backgroundColor: activeColorTarget === 'upregulated'
                                            ? upDotColor
                                            : activeColorTarget === 'downregulated'
                                                ? downDotColor
                                                : activeColorTarget === 'significant'
                                                    ? significantDotColor
                                                    : backgroundDotColor
                                    }}
                                />
                                <span>Palette</span>
                            </button>
                            {isColorPaletteOpen && (
                                <div className="absolute right-0 top-full mt-2 z-40 w-[270px] rounded border border-slate-300 bg-white p-2 shadow-xl">
                                    <div className="mb-1 grid grid-cols-7 gap-1 px-1 text-[10px] text-slate-500">
                                        {COLOR_COLUMNS.map((column) => (
                                            <span key={column} className="text-center">{column}</span>
                                        ))}
                                    </div>
                                    <div className="grid grid-cols-7 gap-1">
                                        {COLOR_PALETTE.flatMap((row, rowIndex) =>
                                            row.map((color, columnIndex) => (
                                                <button
                                                    key={`${rowIndex}-${columnIndex}-${color}`}
                                                    type="button"
                                                    className="h-7 w-7 border border-slate-300 hover:scale-105 transition-transform"
                                                    style={{ backgroundColor: color }}
                                                    onClick={() => applySelectedColor(color)}
                                                    aria-label={`Select color ${color}`}
                                                />
                                            ))
                                        )}
                                    </div>
                                </div>
                            )}
                        </div>
                        <button
                            type="button"
                            onClick={() => setIsExportModalOpen(true)}
                            className="flex items-center gap-2 text-sm border border-slate-300 rounded px-3 py-1.5 bg-white hover:bg-slate-50"
                        >
                            <svg className="w-4 h-4 text-slate-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                            </svg>
                            <span>Download Figure</span>
                        </button>
                    </div>
                </div>
                <p className="text-sm text-slate-600">
                    Log fold change vs statistical significance ??Tool: {toolName} ??
                    Total genes: {plotData.length.toLocaleString()} ??
                    Upregulated: <span className="font-semibold text-red-600">{upregulatedData.length.toLocaleString()}</span> ??
                    Downregulated: <span className="font-semibold text-blue-600">{downregulatedData.length.toLocaleString()}</span>
                </p>
            </div>

            <div className="w-full bg-white">
                <div
                    ref={chartAreaRef}
                    className="relative"
                    style={{ height: `${chartHeight}px`, minHeight: '280px' }}
                >
                    <div
                        className="absolute left-0 top-0 z-20 no-export"
                        style={{ width: `${yAxisWidth}px`, height: `${chartHeight}px`, cursor: 'col-resize' }}
                        onMouseDown={handleYAxisResizeStart}
                        title="Drag to resize Y-axis label width"
                    />
                    <div
                        className="absolute top-0 bottom-0 z-30 flex items-center no-export"
                        style={{ left: `${yAxisWidth}px`, cursor: 'col-resize' }}
                        onMouseDown={handleYAxisResizeStart}
                    >
                        <div className="h-full border-l border-dashed border-slate-300" />
                        <div className="ml-1 rounded bg-white/80 px-1 text-[10px] text-slate-500 select-none">||</div>
                    </div>
                    <div
                        className="absolute left-1/2 z-30 rounded border border-slate-300 bg-white/90 px-1.5 py-0.5 text-[10px] text-slate-600 select-none no-export"
                        style={{ transform: 'translateX(-50%)', bottom: '10px', cursor: 'ns-resize' }}
                        onMouseDown={handleXAxisHeightResizeStart}
                        title="Drag up/down to resize Y-axis length"
                    >
                        =
                    </div>
                    <ResponsiveContainer width="100%" height="100%">
                        <ScatterChart
                            key={`volcano-plot-${comparisonName}-${plotData.length}-${chartDisplayLimit}-${dotSizePreset}`}
                            margin={{ top: 20, right: 30, bottom: 60, left: 5 }}
                        >
                            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                            <XAxis
                                type="number"
                                dataKey="logFC"
                                name="logFC"
                                label={{ value: 'Log Fold Change (logFC)', position: 'insideBottom', offset: -10, style: { fontSize: 14, fill: '#475569' } }}
                                stroke="#64748b"
                                tick={{ fontSize: 12 }}
                            />
                            <YAxis
                                type="number"
                                dataKey="neg_log10_pval"
                                name="-log10(p-value)"
                                width={yAxisWidth}
                                label={<Label content={renderYAxisLabel} />}
                                stroke="#64748b"
                                tick={{ fontSize: 12 }}
                            />
                            <ZAxis dataKey="size" range={[2, 9]} />
                            <Tooltip content={<CustomTooltip />} cursor={{ strokeDasharray: '3 3' }} />
                            <Legend
                                verticalAlign="top"
                                height={52}
                                content={() => (
                                    <div className="flex items-center justify-center gap-4 text-xs text-slate-700 flex-wrap pt-1">
                                        {legendItems.map((item) => (
                                            <div key={item.key} className="flex items-center gap-1.5">
                                                <span
                                                    className="inline-block w-2.5 h-2.5 rounded-full border border-slate-300"
                                                    style={{ backgroundColor: item.color }}
                                                />
                                                <span>{item.label}</span>
                                            </div>
                                        ))}
                                    </div>
                                )}
                            />

                            {/* Threshold lines */}
                            <ReferenceLine
                                x={logFCThreshold}
                                stroke="#94a3b8"
                                strokeDasharray="5 5"
                                strokeWidth={1}
                                label={{ value: 'FC > 2', position: 'top', fill: '#64748b', fontSize: 11 }}
                            />
                            <ReferenceLine
                                x={-logFCThreshold}
                                stroke="#94a3b8"
                                strokeDasharray="5 5"
                                strokeWidth={1}
                                label={{ value: 'FC < 0.5', position: 'top', fill: '#64748b', fontSize: 11 }}
                            />
                            <ReferenceLine
                                y={pvalThreshold}
                                stroke="#94a3b8"
                                strokeDasharray="5 5"
                                strokeWidth={1}
                                label={{ value: 'p = 0.05', position: 'insideRight', fill: '#64748b', fontSize: 11 }}
                            />

                            <Scatter
                                key={`volcano-scatter-${plotData.length}-${chartDisplayLimit}-${dotSizePreset}`}
                                name="All Genes"
                                data={enrichedData}
                                shape={(props: any) => {
                                    const { cx, cy, fill, payload } = props;
                                    return (
                                        <circle
                                            cx={cx}
                                            cy={cy}
                                            r={payload.size}
                                            fill={fill}
                                            fillOpacity={payload.significant ? 0.82 : 0.4}
                                            stroke={payload.significant ? fill : 'none'}
                                            strokeWidth={payload.significant ? 1 : 0}
                                        />
                                    );
                                }}
                            />
                        </ScatterChart>
                    </ResponsiveContainer>
                </div>
            </div>

            {/* Interpretation */}
            <div className="mt-4 p-4 bg-slate-50 rounded-lg border border-slate-200">
                <div className="flex items-start justify-between mb-2">
                    <p className="text-xs text-slate-600 flex-1">
                        <strong>Interpretation:</strong> Points in the upper corners show genes with both large fold changes and high statistical significance.
                        Point colors follow the legend and current palette settings.
                        Dashed lines indicate thresholds: |logFC| &gt; 1 (2-fold change) and p-value &lt; 0.05.
                        {chartDisplayLimit !== 'all' && significantData.length > chartDisplayLimit && (
                            <span className="ml-2 text-amber-700">
                                <strong>Note:</strong> Chart displays top {chartDisplayLimit.toLocaleString()} significant genes (by FDR). All {significantData.length.toLocaleString()} significant genes are available in the table below.
                            </span>
                        )}
                    </p>
                    <div className="flex items-center space-x-2 ml-4">
                        <span className="text-xs font-semibold text-slate-700">
                            Significant: {significantData.length.toLocaleString()}
                        </span>
                        <span className="px-2 py-1 bg-red-50 text-red-700 rounded text-xs font-medium">
                            Up: {upregulatedData.length.toLocaleString()}
                        </span>
                        <span className="px-2 py-1 bg-blue-50 text-blue-700 rounded text-xs font-medium">
                            Down: {downregulatedData.length.toLocaleString()}
                        </span>
                    </div>
                </div>
            </div>

            {/* Significant Genes Table */}
            <div className="mt-6">
                {/* Search Bar and Actions */}
                <div className="mb-4 flex flex-wrap items-center gap-5">
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
                        disabled={isTableLoading}
                        className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed font-medium text-sm"
                    >
                        Search
                    </button>
                    {activeSearch && (
                        <button
                            onClick={handleClearSearch}
                            disabled={isTableLoading}
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
                        analyzeButtonClassName="px-4 py-2 text-sm font-semibold bg-primary text-white rounded-lg hover:bg-primary-dark disabled:bg-slate-300 disabled:cursor-not-allowed flex items-center"
                        toolbarClassName="contents"
                        leftGroupClassName="contents"
                        rightGroupClassName="contents"
                    />
                    <button
                        onClick={handleDownload}
                        disabled={!significantGenes?.data || significantGenes.data.length === 0}
                        className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed font-medium text-sm flex items-center"
                    >
                        <svg className="h-4 w-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                        </svg>
                        Download {selectedGenes.size > 0 ? `(${selectedGenes.size})` : ''}
                    </button>
                    <div className="flex-1"></div>
                    {/* Pagination - Inline */}
                    {significantGenes && significantGenes.total > 0 && (
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
                                {((currentPage - 1) * pageSize + 1)}-{Math.min(currentPage * pageSize, significantGenes.total)} of {significantGenes.total.toLocaleString()}
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
                                    const totalPages = Math.ceil(significantGenes.total / pageSize);
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
                                    disabled={currentPage === Math.ceil(significantGenes.total / pageSize)}
                                    className="px-3 py-1 rounded border border-slate-300 text-sm disabled:opacity-50 disabled:cursor-not-allowed hover:bg-slate-50"
                                >
                                    Next
                                </button>
                            </div>
                        </div>
                    )}
                </div>

                <div className="mb-4">
                    <h4 className="text-md font-semibold text-slate-900">
                        Significant Genes Table
                    </h4>
                </div>

                {/* Table */}
                {significantGenes && significantGenes.total > 0 ? (
                    <div className="border border-slate-200 rounded-lg overflow-visible">
                        <div ref={tableWrapperRef} className="relative" style={{ overflowX: 'auto', overflowY: 'visible' }}>
                            <table ref={tableRef} className="min-w-full divide-y divide-slate-200" style={{ tableLayout: 'fixed' }}>
                                {tableColGroup}
                                <thead ref={tableTheadRef}>
                                    {tableHeaderRow}
                                </thead>
                                <tbody className="bg-white divide-y divide-slate-200">
                                    {tableData.map((gene, idx) => {
                                        const regulation = getRegulationStatus(gene);
                                        return (
                                            <tr key={`${gene.gene}-${idx}`} className="hover:bg-slate-50 transition-colors">
                                                <td className="px-4 py-3">
                                                    <input
                                                        type="checkbox"
                                                        className="h-4 w-4 rounded border-slate-300 text-primary focus:ring-primary"
                                                        checked={selectedGenes.has(gene.gene)}
                                                        onChange={() => handleSelectOne(gene.gene)}
                                                    />
                                                </td>
                                                <td className="px-4 py-3 whitespace-nowrap text-sm font-medium text-slate-900 cursor-help" title={gene.gene_description as string || 'No description available'}>
                                                    {gene.gene}
                                                </td>
                                                <td className="px-4 py-3 whitespace-nowrap text-sm text-slate-700">
                                                    {gene.gene_symbol && gene.gene_symbol !== gene.gene ? (
                                                        <span className="italic">{gene.gene_symbol}</span>
                                                    ) : (
                                                        <span className="text-slate-500">{gene.gene}</span>
                                                    )}
                                                </td>
                                                <td className="px-4 py-3">
                                                    {(() => {
                                                        if (tmmCounts && tmmSampleNames.length > 0 && tmmCounts.has(gene.gene)) {
                                                            const values = tmmCounts.get(gene.gene)!;
                                                            return (
                                                                <MiniHeatmap
                                                                    values={values}
                                                                    samples={tmmSampleNames}
                                                                    width={Math.min(tmmSampleNames.length * 16, 240)}
                                                                    height={20}
                                                                />
                                                            );
                                                        }
                                                        return <span className="text-xs text-slate-400">N/A</span>;
                                                    })()}
                                                </td>
                                                <td className={`px-4 py-3 whitespace-nowrap text-sm font-mono ${regulation.color}`}>
                                                    {gene.logFC?.toFixed(3)}
                                                </td>
                                                <td className="px-4 py-3 whitespace-nowrap text-sm font-mono text-slate-600">
                                                    {gene.logCPM?.toFixed(3)}
                                                </td>
                                                <td className="px-4 py-3 whitespace-nowrap text-sm font-mono text-slate-600">
                                                    {gene.PValue?.toExponential(2)}
                                                </td>
                                                <td className="px-4 py-3 whitespace-nowrap text-sm font-mono text-slate-600">
                                                    {gene.FDR?.toExponential(2)}
                                                </td>
                                                <td className={`px-4 py-3 whitespace-nowrap text-sm font-semibold ${regulation.color}`}>
                                                    {regulation.text}
                                                </td>
                                            </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                        </div>
                    </div>
                ) : (
                    <div className="text-center py-8 text-slate-500">
                        <p>No significant genes found (FDR &lt; 0.05)</p>
                    </div>
                )}

                {/* Loading Overlay */}
                {isTableLoading && (
                    <div className="absolute inset-0 bg-white bg-opacity-75 flex items-center justify-center z-40">
                        <div className="text-center">
                            <div className="animate-spin rounded-full h-12 w-12 border-b-4 border-blue-600 mx-auto mb-4"></div>
                            <p className="text-slate-600">Loading results...</p>
                        </div>
                    </div>
                )}

                {overlayHeader.visible && typeof document !== 'undefined' && createPortal(
                    <div
                        className="fixed z-[9998]"
                        style={{ top: overlayHeader.top, left: overlayHeader.left, width: overlayHeader.width }}
                    >
                        <div className="overflow-hidden rounded-t-xl border border-slate-200 bg-slate-50 shadow-sm">
                            <table className="min-w-full divide-y divide-slate-200" style={{ width: '100%', tableLayout: 'fixed' }}>
                                {tableColGroup}
                                <thead>{tableHeaderRow}</thead>
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
            </div>

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
            <ChartExportModal
                isOpen={isExportModalOpen}
                onClose={() => !isExportingFigure && setIsExportModalOpen(false)}
                onExport={handleExportFigure}
                isExporting={isExportingFigure}
                defaultFilename={`${comparisonName.replace(/\s+/g, '_')}_Volcano_plot`}
                currentWidth={Math.max(800, Math.round(chartAreaRef.current?.clientWidth || 1200))}
                currentHeight={chartHeight}
            />
        </div>
    );
};

export default WorkbenchDetailDEGVolcano;
