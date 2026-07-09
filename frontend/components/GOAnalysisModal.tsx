import React, { useState, useMemo, useRef, useEffect } from 'react';
import { ScatterChart, Scatter, XAxis, YAxis, ZAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import Plot from 'react-plotly.js';
import { apiService } from '../services/api';

interface GOTerm {
    Rank: number;
    Term: string;
    'Term ID': string;
    'Term Name': string;
    'P-value': number;
    'Adjusted P-value': number;
    Genes: string;
    GeneSymbols?: string;  // Optional: Gene symbols corresponding to Genes
    'Gene Count': number;
    'Term Size': number;
    'Query Size': number;
    'Intersection Size': number;
}

interface GOAnalysisResult {
    success: boolean;
    provider?: 'david' | 'gprofiler';
    gene_count: number;
    databases: string[];
    total_terms: number;
    results: {
        [database: string]: GOTerm[];
    };
}

interface GOAnalysisModalProps {
    isOpen: boolean;
    onClose: () => void;
    result: GOAnalysisResult | null;
    isLoading: boolean;
    workbenchId: number;
    comparisonName: string;
    toolName: string;
}

const GOAnalysisModal: React.FC<GOAnalysisModalProps> = ({
    isOpen,
    onClose,
    result,
    isLoading,
    workbenchId,
    comparisonName,
    toolName
}) => {
    type FontSizeMode = 'auto' | '10' | '12' | '14' | '16' | '18' | '20' | '22' | '24';
    const providerLabel = result?.provider === 'david' ? 'DAVID' : 'g:Profiler';

    const [activeTab, setActiveTab] = useState<string>('GO_BP');
    const [searchTerm, setSearchTerm] = useState('');
    const [sortConfig, setSortConfig] = useState<{ key: keyof GOTerm; direction: 'asc' | 'desc' } | null>(null);
    const [maxTerms, setMaxTerms] = useState<number | 'all'>(20);
    const [fontSizeMode, setFontSizeMode] = useState<FontSizeMode>('auto');
    const [yLabelTilt, setYLabelTilt] = useState<number>(0);
    const [tiltInput, setTiltInput] = useState<string>('0');
    const [yAxisLabelWidth, setYAxisLabelWidth] = useState(300);
    const [manualChartHeight, setManualChartHeight] = useState<number | null>(null);
    const [termSelection, setTermSelection] = useState<Record<string, boolean>>({});
    const [selectedTerm, setSelectedTerm] = useState<GOTerm | null>(null);
    const [heatmapData, setHeatmapData] = useState<any>(null);
    const [isLoadingHeatmap, setIsLoadingHeatmap] = useState(false);
    const chartRef = useRef<HTMLDivElement>(null);
    const chartAreaRef = useRef<HTMLDivElement>(null);
    const selectAllRef = useRef<HTMLInputElement>(null);

    // Load heatmap data when term is selected
    useEffect(() => {
        if (selectedTerm && workbenchId) {
            loadHeatmapData();
        }
    }, [selectedTerm, workbenchId]);

    const loadHeatmapData = async () => {
        if (!selectedTerm) return;

        setIsLoadingHeatmap(true);
        try {
            const genes = selectedTerm.Genes.split(';');
            const response = await apiService.generateHeatmap(workbenchId, {
                genes,
                comparison: comparisonName,
                tool: toolName,
                clustering_method: 'ward',
                normalize: 'zscore'
            });

            if (response.z && response.x && response.y) {
                // Create Gene ID to Symbol mapping
                const geneIds = selectedTerm.Genes.split(';');
                const geneSymbols = selectedTerm.GeneSymbols?.split(';') || [];
                const geneMap = new Map<string, string>();
                geneIds.forEach((geneId, idx) => {
                    const symbol = geneSymbols[idx];
                    geneMap.set(geneId, symbol || geneId);
                });

                // Replace Gene IDs with Gene Symbols in y-axis
                const yLabels = response.y.map((geneId: string) => geneMap.get(geneId) || geneId);

                setHeatmapData({
                    ...response,
                    y: yLabels
                });
            } else {
                console.error('Invalid heatmap data received');
                setHeatmapData(null);
            }
        } catch (error) {
            console.error('Failed to load heatmap:', error);
            setHeatmapData(null);
        } finally {
            setIsLoadingHeatmap(false);
        }
    };

    const handleSort = (key: keyof GOTerm) => {
        setSortConfig(prev => {
            if (prev?.key === key) {
                return { key, direction: prev.direction === 'asc' ? 'desc' : 'asc' };
            }
            return { key, direction: 'desc' };
        });
    };

    const getTermKey = (term: GOTerm): string => {
        return term['Term ID'] || term.Term || `${term.Rank}_${term['Term Name']}`;
    };

    const activeData = useMemo(() => {
        if (!result?.results[activeTab]) return [];

        let data = [...result.results[activeTab]];

        // Apply search filter
        if (searchTerm.trim()) {
            const lineTerms = searchTerm
                .toLowerCase()
                .split(/\r?\n/)
                .map(line =>
                    line
                        .split(/[\s,;\t,]+/)
                        .map(term => term.trim())
                        .filter(Boolean)
                )
                .filter(terms => terms.length > 0);

            data = data.filter(term =>
                lineTerms.some(terms =>
                    terms.every(query =>
                        term['Term Name'].toLowerCase().includes(query) ||
                        term['Term ID'].toLowerCase().includes(query) ||
                        term.Genes.toLowerCase().includes(query) ||
                        (term.GeneSymbols || '').toLowerCase().includes(query)
                    )
                )
            );
        }

        // Apply sorting
        if (sortConfig) {
            data.sort((a, b) => {
                const aVal = a[sortConfig.key];
                const bVal = b[sortConfig.key];

                if (typeof aVal === 'number' && typeof bVal === 'number') {
                    return sortConfig.direction === 'asc' ? aVal - bVal : bVal - aVal;
                }

                return sortConfig.direction === 'asc'
                    ? String(aVal).localeCompare(String(bVal))
                    : String(bVal).localeCompare(String(aVal));
            });
        }

        if (maxTerms === 'all') {
            return data;
        }

        return data.slice(0, maxTerms);
    }, [result, activeTab, searchTerm, sortConfig, maxTerms]);

    // Reset selection to "all selected" whenever tab changes.
    useEffect(() => {
        if (!isOpen) return;

        const nextSelection: Record<string, boolean> = {};
        activeData.forEach(term => {
            nextSelection[getTermKey(term)] = true;
        });
        setTermSelection(nextSelection);
    }, [activeTab, isOpen, result]);

    // Keep newly visible terms selected by default.
    useEffect(() => {
        if (!isOpen || activeData.length === 0) return;

        setTermSelection(prev => {
            let changed = false;
            const next = { ...prev };

            activeData.forEach(term => {
                const key = getTermKey(term);
                if (typeof next[key] === 'undefined') {
                    next[key] = true;
                    changed = true;
                }
            });

            return changed ? next : prev;
        });
    }, [activeData, isOpen]);

    const selectedActiveData = useMemo(() => {
        return activeData.filter(term => termSelection[getTermKey(term)] !== false);
    }, [activeData, termSelection]);

    const selectedCount = selectedActiveData.length;
    const allActiveSelected = activeData.length > 0 && selectedCount === activeData.length;
    const someActiveSelected = selectedCount > 0 && selectedCount < activeData.length;

    useEffect(() => {
        if (selectAllRef.current) {
            selectAllRef.current.indeterminate = someActiveSelected;
        }
    }, [someActiveSelected, activeData.length]);

    const handleToggleTermSelection = (term: GOTerm, checked: boolean) => {
        const key = getTermKey(term);
        setTermSelection(prev => ({
            ...prev,
            [key]: checked
        }));
    };

    const handleToggleAllTerms = (checked: boolean) => {
        setTermSelection(prev => {
            const next = { ...prev };
            activeData.forEach(term => {
                next[getTermKey(term)] = checked;
            });
            return next;
        });
    };

    const handleClearSearch = () => {
        setSearchTerm('');
    };

    const clampTilt = (value: number): number => {
        return Math.max(-45, Math.min(45, Math.round(value)));
    };

    const applyTiltInput = (rawValue: string) => {
        const trimmed = rawValue.trim();
        if (!trimmed) {
            setTiltInput(String(yLabelTilt));
            return;
        }

        const parsed = Number(trimmed);
        if (Number.isNaN(parsed)) {
            setTiltInput(String(yLabelTilt));
            return;
        }

        const clamped = clampTilt(parsed);
        setYLabelTilt(clamped);
        setTiltInput(String(clamped));
    };

    const changeTiltBy = (delta: number) => {
        const next = clampTilt(yLabelTilt + delta);
        setYLabelTilt(next);
        setTiltInput(String(next));
    };

    useEffect(() => {
        setTiltInput(String(yLabelTilt));
    }, [yLabelTilt]);

    const effectiveAxisFontSize = useMemo(() => {
        if (fontSizeMode !== 'auto') return Number(fontSizeMode);

        const termCount = selectedActiveData.length;
        if (termCount <= 8) return 16;
        if (termCount <= 15) return 14;
        if (termCount <= 30) return 12;
        if (termCount <= 60) return 10;
        return 9;
    }, [fontSizeMode, selectedActiveData.length]);

    const textMeasureContext = useMemo(() => {
        if (typeof document === 'undefined') return null;
        const canvas = document.createElement('canvas');
        const ctx = canvas.getContext('2d');
        if (!ctx) return null;
        ctx.font = `${effectiveAxisFontSize}px sans-serif`;
        return ctx;
    }, [effectiveAxisFontSize]);

    const estimateTextWidth = (text: string): number => {
        if (!textMeasureContext) return text.length * effectiveAxisFontSize * 0.6;
        return textMeasureContext.measureText(text).width;
    };

    const fitTextWithEllipsis = (text: string, maxWidth: number): string => {
        if (estimateTextWidth(text) <= maxWidth) return text;
        const ellipsis = '...';
        if (estimateTextWidth(ellipsis) >= maxWidth) return ellipsis;

        let result = '';
        for (let i = 0; i < text.length; i += 1) {
            const candidate = `${result}${text[i]}`;
            if (estimateTextWidth(`${candidate}${ellipsis}`) > maxWidth) break;
            result = candidate;
        }
        return `${result}${ellipsis}`;
    };

    const formatTermForYAxis = (rawTerm: string): string => {
        const normalized = rawTerm.replace(/\s+/g, ' ').trim();
        const maxLineWidth = Math.max(80, yAxisLabelWidth - 16);

        if (!normalized) return '';
        if (estimateTextWidth(normalized) <= maxLineWidth) return normalized;

        const words = normalized.split(' ');
        if (words.length === 1) {
            return fitTextWithEllipsis(normalized, maxLineWidth);
        }

        let line1 = '';
        let splitIndex = 0;
        while (splitIndex < words.length) {
            const candidate = line1 ? `${line1} ${words[splitIndex]}` : words[splitIndex];
            if (estimateTextWidth(candidate) <= maxLineWidth || !line1) {
                line1 = candidate;
                splitIndex += 1;
            } else {
                break;
            }
        }

        const remaining = words.slice(splitIndex).join(' ');
        if (!remaining) return line1;

        const line2 = estimateTextWidth(remaining) <= maxLineWidth
            ? remaining
            : fitTextWithEllipsis(remaining, maxLineWidth);

        return `${line1}\n${line2}`;
    };

    const bubbleData = useMemo(() => {
        return selectedActiveData.map(term => ({
            x: -Math.log10(term['P-value']),
            y: formatTermForYAxis(term['Term Name']),
            z: term['Gene Count'],
            pValue: term['Adjusted P-value'],
            fullTerm: term.Term,
            genes: term.Genes,
            geneCount: term['Gene Count'],
            termData: term  // Store original term data for click handler
        }));
    }, [selectedActiveData, yAxisLabelWidth, effectiveAxisFontSize]);

    // Dynamic auto chart height based on number of terms
    const autoChartHeight = useMemo(() => {
        const termCount = bubbleData.length;
        // 28px per term, minimum 500px, maximum 1200px
        return Math.max(500, Math.min(1200, termCount * 18));
    }, [bubbleData.length]);

    const chartHeight = manualChartHeight ?? autoChartHeight;

    const handleYAxisResizeStart = (event: React.MouseEvent<HTMLDivElement>) => {
        event.preventDefault();

        const startX = event.clientX;
        const startWidth = yAxisLabelWidth;
        const containerWidth = chartAreaRef.current?.clientWidth ?? 1200;
        const minWidth = 220;
        const maxWidth = Math.max(260, containerWidth - 140);

        const onMouseMove = (moveEvent: MouseEvent) => {
            const nextWidth = Math.max(minWidth, Math.min(maxWidth, startWidth + (moveEvent.clientX - startX)));
            setYAxisLabelWidth(nextWidth);
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
        const minHeight = 220;
        const maxHeight = 1800;

        const onMouseMove = (moveEvent: MouseEvent) => {
            const deltaY = moveEvent.clientY - startY;
            const nextHeight = Math.max(minHeight, Math.min(maxHeight, startHeight + deltaY));
            setManualChartHeight(nextHeight);
        };

        const onMouseUp = () => {
            window.removeEventListener('mousemove', onMouseMove);
            window.removeEventListener('mouseup', onMouseUp);
        };

        window.addEventListener('mousemove', onMouseMove);
        window.addEventListener('mouseup', onMouseUp);
    };

    const renderYAxisTick = (props: any) => {
        const { x = 0, y = 0, payload } = props;
        const value = String(payload?.value ?? '');
        const lines = value.split('\n');
        const lineGap = 2;
        const totalHeight = lines.length * effectiveAxisFontSize + (lines.length - 1) * lineGap;
        const firstDy = (-totalHeight / 2) + (effectiveAxisFontSize * 0.85);

        return (
            <g transform={`translate(${x},${y})`}>
                <text
                    x={0}
                    y={0}
                    textAnchor="end"
                    fill="#475569"
                    fontSize={effectiveAxisFontSize}
                    fontWeight={500}
                    transform={yLabelTilt !== 0 ? `rotate(${yLabelTilt} 0 0)` : undefined}
                >
                    {lines.map((line, index) => (
                        <tspan
                            key={`${line}-${index}`}
                            x={0}
                            dy={index === 0 ? firstDy : effectiveAxisFontSize + lineGap}
                        >
                            {line}
                        </tspan>
                    ))}
                </text>
            </g>
        );
    };

    const getColorByPValue = (pValue: number) => {
        if (pValue < 0.001) return '#dc2626'; // red-600
        if (pValue < 0.01) return '#ea580c'; // orange-600
        if (pValue < 0.05) return '#f59e0b'; // amber-500
        return '#94a3b8'; // slate-400
    };

    const handleDownloadCSV = () => {
        if (!selectedActiveData.length) return;

        const headers = ['Rank', 'Term ID', 'Term Name', 'P-value', 'Adjusted P-value', 'Gene Count', 'Term Size', 'Genes'];
        const rows = selectedActiveData.map(term => [
            term.Rank,
            term['Term ID'],
            term['Term Name'],
            term['P-value'],
            term['Adjusted P-value'],
            term['Gene Count'],
            term['Term Size'],
            term.Genes
        ]);

        const csvContent = [
            headers.join(','),
            ...rows.map(row => row.map(cell => `"${cell}"`).join(','))
        ].join('\n');

        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        const link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = `go_enrichment_${activeTab}.csv`;
        link.click();
    };

    const handleDownloadChart = async () => {
        if (!chartRef.current) return;

        try {
            // Use html-to-image for better CSS rendering
            const { toPng } = await import('html-to-image');

            const dataUrl = await toPng(chartRef.current, {
                quality: 1.0,
                pixelRatio: 2, // Higher resolution
                backgroundColor: '#ffffff',
                // Exclude UI-only controls from exported figure
                filter: (node: HTMLElement) => !node.classList?.contains('no-export')
            });

            const cropWhitespace = async (srcDataUrl: string, padding = 16): Promise<string> => {
                const image = new Image();
                image.src = srcDataUrl;

                await new Promise<void>((resolve, reject) => {
                    image.onload = () => resolve();
                    image.onerror = () => reject(new Error('Failed to load chart image for cropping'));
                });

                const sourceCanvas = document.createElement('canvas');
                sourceCanvas.width = image.width;
                sourceCanvas.height = image.height;
                const sourceCtx = sourceCanvas.getContext('2d');
                if (!sourceCtx) return srcDataUrl;

                sourceCtx.drawImage(image, 0, 0);
                const { data, width, height } = sourceCtx.getImageData(0, 0, sourceCanvas.width, sourceCanvas.height);

                let minX = width;
                let minY = height;
                let maxX = -1;
                let maxY = -1;

                // Treat near-white background as empty space and crop it out.
                for (let y = 0; y < height; y += 1) {
                    for (let x = 0; x < width; x += 1) {
                        const idx = (y * width + x) * 4;
                        const r = data[idx];
                        const g = data[idx + 1];
                        const b = data[idx + 2];
                        const a = data[idx + 3];
                        const isBlank = a === 0 || (r >= 245 && g >= 245 && b >= 245);
                        if (isBlank) continue;

                        if (x < minX) minX = x;
                        if (y < minY) minY = y;
                        if (x > maxX) maxX = x;
                        if (y > maxY) maxY = y;
                    }
                }

                if (maxX < minX || maxY < minY) return srcDataUrl;

                const cropX = Math.max(0, minX - padding);
                const cropY = Math.max(0, minY - padding);
                const cropW = Math.min(width - cropX, (maxX - minX + 1) + (padding * 2));
                const cropH = Math.min(height - cropY, (maxY - minY + 1) + (padding * 2));

                const targetCanvas = document.createElement('canvas');
                targetCanvas.width = cropW;
                targetCanvas.height = cropH;
                const targetCtx = targetCanvas.getContext('2d');
                if (!targetCtx) return srcDataUrl;

                targetCtx.drawImage(sourceCanvas, cropX, cropY, cropW, cropH, 0, 0, cropW, cropH);
                return targetCanvas.toDataURL('image/png');
            };

            const croppedDataUrl = await cropWhitespace(dataUrl);

            const link = document.createElement('a');
            link.href = croppedDataUrl;
            link.download = `go_enrichment_bubble_plot_${activeTab}.png`;
            link.click();
        } catch (error) {
            console.error('Failed to download chart:', error);
            alert('Failed to download chart image. Please try again.');
        }
    };

    const CustomTooltip = ({ active, payload }: any) => {
        if (active && payload && payload.length) {
            const data = payload[0].payload;
            return (
                <div className="bg-white p-4 border-2 border-slate-300 rounded-lg shadow-xl text-sm">
                    <p className="font-bold mb-2 text-slate-800">{data.fullTerm}</p>
                    <div className="space-y-1 text-slate-600">
                        <p>-log10(P-value): <span className="font-semibold text-slate-800">{data.x.toFixed(2)}</span></p>
                        <p>Adj. P-value: <span className="font-semibold text-slate-800">{data.pValue.toExponential(2)}</span></p>
                        <p>Gene Count: <span className="font-semibold text-slate-800">{data.geneCount}</span></p>
                    </div>
                </div>
            );
        }
        return null;
    };

    // Early return after all Hooks are called (React Hooks rules)
    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
            <div className="bg-white rounded-lg shadow-xl w-full max-w-7xl h-[90vh] flex flex-col">
                {/* Header */}
                <div className="flex justify-between items-center p-6 border-b border-slate-200">
                    <div>
                        <div className="flex items-center gap-3">
                            <h2 className="text-2xl font-bold text-slate-800">GO Enrichment Analysis</h2>
                            {result?.provider && (
                                <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-slate-700">
                                    {providerLabel}
                                </span>
                            )}
                        </div>
                        {result && (
                            <p className="text-sm text-slate-600 mt-1">
                                {result.gene_count} genes analyzed • {result.total_terms} enriched terms found
                            </p>
                        )}
                    </div>
                    <button
                        onClick={onClose}
                        className="text-slate-400 hover:text-slate-600 transition-colors"
                    >
                        <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                    </button>
                </div>

                {/* Loading State */}
                {isLoading && (
                    <div className="flex-1 flex items-center justify-center bg-gradient-to-br from-blue-50 to-slate-50">
                        <div className="text-center">
                            <div className="relative mb-6">
                                {/* Outer spinning ring */}
                                <div className="animate-spin rounded-full h-20 w-20 border-4 border-slate-200 border-t-primary mx-auto"></div>
                                {/* Inner pulsing circle */}
                                <div className="absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2">
                                    <div className="animate-pulse rounded-full h-12 w-12 bg-primary/20"></div>
                                </div>
                            </div>
                            <h3 className="text-lg font-semibold text-slate-800 mb-2">Running GO Enrichment Analysis</h3>
                            <p className="text-sm text-slate-600 mb-4">Analyzing gene functional enrichment...</p>
                            <div className="flex items-center justify-center space-x-2 text-xs text-slate-500">
                                <div className="animate-pulse">⚡</div>
                                <span>Querying g:Profiler database</span>
                                <div className="animate-pulse">⚡</div>
                            </div>
                        </div>
                    </div>
                )}

                {/* No Results State */}
                {!isLoading && result && (!result.databases || result.databases.length === 0 || result.total_terms === 0) && (
                    <div className="flex-1 flex items-center justify-center p-8">
                        <div className="text-center max-w-md">
                            <svg className="mx-auto h-16 w-16 text-slate-400 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                            </svg>
                            <h3 className="text-lg font-semibold text-slate-800 mb-2">No Significant Enrichment Found</h3>
                            <p className="text-sm text-slate-600 mb-4">
                                No GO terms were significantly enriched (p-value &lt; 0.05) for the selected {result.gene_count} genes.
                            </p>
                            <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 text-left">
                                <p className="text-sm text-blue-900 font-medium mb-2">Possible reasons:</p>
                                <ul className="text-sm text-blue-800 space-y-1 list-disc list-inside">
                                    <li>The selected genes may have diverse functions</li>
                                    <li>Sample size might be too small (try selecting more genes)</li>
                                    <li>The genes might not be well-annotated in the database</li>
                                </ul>
                            </div>
                        </div>
                    </div>
                )}

                {/* Results */}
                {!isLoading && result && result.databases && result.databases.length > 0 && result.total_terms > 0 && (
                    <div className="flex-1 overflow-hidden flex flex-col">
                        {/* Tabs */}
                        <div className="flex border-b border-slate-200 px-6 space-x-1">
                            {result.databases.map(db => (
                                <button
                                    key={db}
                                    onClick={() => setActiveTab(db)}
                                    className={`px-4 py-2 text-sm font-medium transition-colors ${
                                        activeTab === db
                                            ? 'border-b-2 border-primary text-primary'
                                            : 'text-slate-600 hover:text-slate-800'
                                    }`}
                                >
                                    {db.replace(/_/g, ' ')}
                                    <span className="ml-2 text-xs bg-slate-100 px-2 py-0.5 rounded">
                                        {result.results[db]?.length || 0}
                                    </span>
                                </button>
                            ))}
                        </div>

                        {/* Controls */}
                        <div className="flex items-center justify-between p-4 bg-slate-50 border-b border-slate-200">
                            <div className="flex items-center space-x-4">
                                <div className="relative">
                                    <textarea
                                        rows={2}
                                        placeholder="Search terms or genes (comma, space, tab, or newline separated)..."
                                        value={searchTerm}
                                        onChange={(e) => setSearchTerm(e.target.value)}
                                        className="pl-9 pr-12 py-2 border border-slate-300 rounded-lg text-sm focus:ring-primary focus:border-primary min-w-[320px] min-h-[56px] resize-y"
                                    />
                                    {searchTerm && (
                                        <button
                                            type="button"
                                            onClick={handleClearSearch}
                                            className="absolute right-2 top-2 inline-flex h-7 w-7 items-center justify-center rounded-md text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600"
                                            aria-label="Clear GO search"
                                            title="Clear"
                                        >
                                            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                                            </svg>
                                        </button>
                                    )}
                                    <svg className="absolute left-3 top-3 h-4 w-4 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                                    </svg>
                                </div>
                                <div className="flex items-center space-x-2">
                                    <label className="text-sm text-slate-600">Show top:</label>
                                    <select
                                        value={String(maxTerms)}
                                        onChange={(e) => setMaxTerms(e.target.value === 'all' ? 'all' : Number(e.target.value))}
                                        className="border border-slate-300 rounded px-2 py-1 text-sm focus:ring-primary focus:border-primary"
                                    >
                                        <option value={10}>10</option>
                                        <option value={20}>20</option>
                                        <option value={50}>50</option>
                                        <option value={100}>100</option>
                                        <option value="all">All</option>
                                    </select>
                                </div>
                            </div>
                            <div className="flex items-center space-x-3">
                                <span className="text-sm text-slate-600">
                                    {selectedCount} selected / {activeData.length} shown
                                </span>
                                <button
                                    onClick={handleDownloadChart}
                                    className="flex items-center space-x-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm"
                                >
                                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                                    </svg>
                                    <span>Download Chart</span>
                                </button>
                                <button
                                    onClick={handleDownloadCSV}
                                    className="flex items-center space-x-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors text-sm"
                                >
                                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                                    </svg>
                                    <span>Download CSV</span>
                                </button>
                            </div>
                        </div>

                        {/* Content */}
                        <div className="flex-1 overflow-auto p-6">
                            {activeData.length === 0 ? (
                                <div className="text-center py-12 text-slate-500">
                                    No enriched terms found
                                </div>
                            ) : (
                                <div className="space-y-6">
                                    {/* Bubble Plot - Enhanced Recharts */}
                                    <div ref={chartRef} className="bg-gradient-to-br from-slate-50 to-white border-2 border-slate-200 rounded-xl p-6 shadow-sm">
                                        <div className="grid grid-cols-3 items-center mb-6">
                                            <div />
                                            <h3 className="text-xl font-bold text-slate-800 text-center">
                                                GO Enrichment
                                            </h3>
                                            <div className="justify-self-end flex items-center gap-2 no-export">
                                                <label className="text-xs text-slate-600">Font size:</label>
                                                <select
                                                    value={fontSizeMode}
                                                    onChange={(e) => setFontSizeMode(e.target.value as FontSizeMode)}
                                                    className="border border-slate-300 rounded px-2 py-1 text-xs focus:ring-primary focus:border-primary bg-white"
                                                >
                                                    <option value="auto">Auto</option>
                                                    <option value="10">10</option>
                                                    <option value="12">12</option>
                                                    <option value="14">14</option>
                                                    <option value="16">16</option>
                                                    <option value="18">18</option>
                                                    <option value="20">20</option>
                                                    <option value="22">22</option>
                                                    <option value="24">24</option>
                                                </select>
                                                <label className="text-xs text-slate-600 ml-2">Tilt:</label>
                                                <div className="flex items-center gap-1">
                                                    <button
                                                        type="button"
                                                        onClick={() => changeTiltBy(-2)}
                                                        className="border border-slate-300 rounded px-2 py-1 text-xs text-slate-700 hover:bg-slate-100"
                                                        aria-label="Decrease tilt"
                                                    >
                                                        -
                                                    </button>
                                                    <input
                                                        type="text"
                                                        inputMode="numeric"
                                                        value={tiltInput}
                                                        onChange={(e) => setTiltInput(e.target.value)}
                                                        onBlur={() => applyTiltInput(tiltInput)}
                                                        onKeyDown={(e) => {
                                                            if (e.key === 'Enter') {
                                                                applyTiltInput(tiltInput);
                                                            }
                                                        }}
                                                        className="w-14 border border-slate-300 rounded px-2 py-1 text-xs text-center focus:ring-primary focus:border-primary bg-white"
                                                        aria-label="Tilt value"
                                                        title="Range: -45 to 45"
                                                    />
                                                    <button
                                                        type="button"
                                                        onClick={() => changeTiltBy(2)}
                                                        className="border border-slate-300 rounded px-2 py-1 text-xs text-slate-700 hover:bg-slate-100"
                                                        aria-label="Increase tilt"
                                                    >
                                                        +
                                                    </button>
                                                </div>
                                            </div>
                                        </div>
                                        {bubbleData.length === 0 ? (
                                            <div className="flex items-center justify-center h-64 text-slate-500 text-sm">
                                                No selected GO terms to display. Check terms in the table to show them on the chart.
                                            </div>
                                        ) : (
                                            <div ref={chartAreaRef} className="relative">
                                                <div
                                                    className="absolute left-0 top-0 no-export z-20"
                                                    style={{
                                                        width: `${yAxisLabelWidth}px`,
                                                        height: `${chartHeight}px`,
                                                        cursor: 'col-resize',
                                                        pointerEvents: 'auto'
                                                    }}
                                                    onMouseDown={handleYAxisResizeStart}
                                                    title="Drag to resize Y-axis label width"
                                                />
                                                <div
                                                    className="absolute top-0 bottom-0 no-export z-30 flex items-center"
                                                    style={{ left: `${yAxisLabelWidth}px`, cursor: 'col-resize', pointerEvents: 'auto' }}
                                                    onMouseDown={handleYAxisResizeStart}
                                                >
                                                    <div className="h-full border-l border-dashed border-slate-300" />
                                                    <div className="ml-1 rounded bg-white/80 px-1 text-[10px] text-slate-500 select-none">
                                                        ||
                                                    </div>
                                                </div>
                                                <div
                                                    className="absolute left-1/2 no-export z-30 rounded border border-slate-300 bg-white/90 px-1.5 py-0.5 text-[10px] text-slate-600 select-none"
                                                    style={{ transform: 'translateX(-50%)', bottom: '10px', cursor: 'ns-resize', pointerEvents: 'auto' }}
                                                    onMouseDown={handleXAxisHeightResizeStart}
                                                    title="Drag up/down to resize Y-axis length"
                                                >
                                                    =
                                                </div>
                                                <ResponsiveContainer width="100%" height={chartHeight}>
                                                    <ScatterChart margin={{ top: 20, right: 30, bottom: 40, left: 5 }}>
                                                        <CartesianGrid
                                                            strokeDasharray="3 3"
                                                            stroke="#e2e8f0"
                                                            strokeWidth={1}
                                                            vertical={true}
                                                            horizontal={true}
                                                        />
                                                        <XAxis
                                                            type="number"
                                                            dataKey="x"
                                                            name="-log10(P-value)"
                                                            tick={{ fill: '#475569', fontSize: effectiveAxisFontSize, fontWeight: 500 }}
                                                            label={{
                                                                value: '-log10(P-value)',
                                                                position: 'insideBottom',
                                                                offset: -15,
                                                                style: { fill: '#1e293b', fontSize: 14, fontWeight: 600 }
                                                            }}
                                                            stroke="#94a3b8"
                                                            strokeWidth={2}
                                                        />
                                                        <YAxis
                                                            type="category"
                                                            dataKey="y"
                                                            name="GO Term"
                                                            width={yAxisLabelWidth}
                                                            tick={renderYAxisTick}
                                                            stroke="#94a3b8"
                                                            strokeWidth={2}
                                                            interval={0}
                                                        />
                                                        <ZAxis
                                                            type="number"
                                                            dataKey="z"
                                                            range={[80, 600]}
                                                            name="Gene Count"
                                                        />
                                                        <Tooltip
                                                            content={<CustomTooltip />}
                                                            cursor={{ strokeDasharray: '3 3', stroke: '#94a3b8', strokeWidth: 1.5 }}
                                                        />
                                                        <Scatter
                                                            name="GO Terms"
                                                            data={bubbleData}
                                                            fill="#8884d8"
                                                            shape="circle"
                                                            fillOpacity={0.8}
                                                            strokeWidth={2}
                                                            stroke="#fff"
                                                            onClick={(data) => {
                                                                if (data && data.termData) {
                                                                    setSelectedTerm(data.termData);
                                                                }
                                                            }}
                                                        >
                                                            {bubbleData.map((entry, index) => (
                                                                <Cell
                                                                    key={`cell-${index}`}
                                                                    fill={getColorByPValue(entry.pValue)}
                                                                    style={{ cursor: 'pointer' }}
                                                                />
                                                            ))}
                                                        </Scatter>
                                                    </ScatterChart>
                                                </ResponsiveContainer>
                                            </div>
                                        )}
                                        <div className="text-center mt-3 text-sm font-medium" style={{ lineHeight: '24px' }}>
                                            {/* Color Legend */}
                                            <span className="text-slate-500 font-semibold" style={{ display: 'inline-block', verticalAlign: 'middle' }}>Color:</span>
                                            {' '}
                                            <span className="inline-block w-4 h-4 bg-red-600 rounded-full shadow-sm" style={{ transform: 'translateY(3px)' }}></span>
                                            {' '}
                                            <span className="text-slate-700" style={{ display: 'inline-block', verticalAlign: 'middle' }}>p &lt; 0.001</span>
                                            {'  '}
                                            <span className="inline-block w-4 h-4 bg-orange-600 rounded-full shadow-sm" style={{ transform: 'translateY(3px)' }}></span>
                                            {' '}
                                            <span className="text-slate-700" style={{ display: 'inline-block', verticalAlign: 'middle' }}>p &lt; 0.01</span>
                                            {'  '}
                                            <span className="inline-block w-4 h-4 bg-amber-500 rounded-full shadow-sm" style={{ transform: 'translateY(3px)' }}></span>
                                            {' '}
                                            <span className="text-slate-700" style={{ display: 'inline-block', verticalAlign: 'middle' }}>p &lt; 0.05</span>
                                            {/* Size Legend */}
                                            <span className="text-slate-500 font-semibold ml-12" style={{ display: 'inline-block', verticalAlign: 'middle' }}>Bubble Size:</span>
                                            {' '}
                                            <span className="inline-block w-2 h-2 bg-slate-400 rounded-full" style={{ transform: 'translateY(2px)' }}></span>
                                            {' '}
                                            <span className="text-slate-700" style={{ display: 'inline-block', verticalAlign: 'middle' }}>Small</span>
                                            {' '}
                                            <svg width="20" height="12" className="inline-block mx-1" style={{ transform: 'translateY(2px)' }}>
                                                <line x1="0" y1="6" x2="20" y2="6" stroke="#94a3b8" strokeWidth="1"/>
                                            </svg>
                                            {' '}
                                            <span className="inline-block w-5 h-5 bg-slate-400 rounded-full" style={{ transform: 'translateY(3px)' }}></span>
                                            {' '}
                                            <span className="text-slate-700" style={{ display: 'inline-block', verticalAlign: 'middle' }}>Large</span>
                                            {' '}
                                            <span className="text-slate-500 text-xs" style={{ display: 'inline-block', verticalAlign: 'middle' }}>(Gene Count)</span>
                                        </div>
                                    </div>

                                    {/* Results Table */}
                                    <div className="bg-white border border-slate-200 rounded-lg overflow-hidden">
                                        <div className="overflow-x-auto">
                                            <table className="w-full text-sm">
                                                <thead className="bg-slate-50 border-b border-slate-200">
                                                    <tr>
                                                        <th className="px-3 py-3 text-left font-semibold text-slate-700 w-12">
                                                            <input
                                                                ref={selectAllRef}
                                                                type="checkbox"
                                                                className="h-4 w-4 rounded border-slate-300 text-primary focus:ring-primary"
                                                                checked={allActiveSelected}
                                                                onChange={(e) => handleToggleAllTerms(e.target.checked)}
                                                                aria-label="Select all GO terms"
                                                            />
                                                        </th>
                                                        <th className="px-4 py-3 text-left font-semibold text-slate-700 cursor-pointer hover:bg-slate-100" onClick={() => handleSort('Rank')}>
                                                            Rank {sortConfig?.key === 'Rank' && (sortConfig.direction === 'asc' ? '↑' : '↓')}
                                                        </th>
                                                        <th className="px-4 py-3 text-left font-semibold text-slate-700 cursor-pointer hover:bg-slate-100" onClick={() => handleSort('Term')}>
                                                            GO Term {sortConfig?.key === 'Term' && (sortConfig.direction === 'asc' ? '↑' : '↓')}
                                                        </th>
                                                        <th className="px-4 py-3 text-left font-semibold text-slate-700 cursor-pointer hover:bg-slate-100" onClick={() => handleSort('P-value')}>
                                                            P-value {sortConfig?.key === 'P-value' && (sortConfig.direction === 'asc' ? '↑' : '↓')}
                                                        </th>
                                                        <th className="px-4 py-3 text-left font-semibold text-slate-700 cursor-pointer hover:bg-slate-100" onClick={() => handleSort('Adjusted P-value')}>
                                                            Adj. P-value {sortConfig?.key === 'Adjusted P-value' && (sortConfig.direction === 'asc' ? '↑' : '↓')}
                                                        </th>
                                                        <th className="px-4 py-3 text-left font-semibold text-slate-700 cursor-pointer hover:bg-slate-100" onClick={() => handleSort('Gene Count')}>
                                                            Genes {sortConfig?.key === 'Gene Count' && (sortConfig.direction === 'asc' ? '↑' : '↓')}
                                                        </th>
                                                        <th className="px-4 py-3 text-left font-semibold text-slate-700 cursor-pointer hover:bg-slate-100" onClick={() => handleSort('Term Size')}>
                                                            Term Size {sortConfig?.key === 'Term Size' && (sortConfig.direction === 'asc' ? '↑' : '↓')}
                                                        </th>
                                                        <th className="px-4 py-3 text-left font-semibold text-slate-700">
                                                            Actions
                                                        </th>
                                                    </tr>
                                                </thead>
                                                <tbody className="divide-y divide-slate-200">
                                                    {activeData.map((term) => {
                                                        const termKey = getTermKey(term);
                                                        const isChecked = termSelection[termKey] !== false;

                                                        return (
                                                        <tr key={termKey} className="hover:bg-slate-50">
                                                            <td className="px-3 py-3">
                                                                <input
                                                                    type="checkbox"
                                                                    className="h-4 w-4 rounded border-slate-300 text-primary focus:ring-primary"
                                                                    checked={isChecked}
                                                                    onChange={(e) => handleToggleTermSelection(term, e.target.checked)}
                                                                    aria-label={`Select ${term.Term}`}
                                                                />
                                                            </td>
                                                            <td className="px-4 py-3">{term.Rank}</td>
                                                            <td className="px-4 py-3 max-w-md">
                                                                <div className="truncate" title={term.Term}>
                                                                    {term.Term}
                                                                </div>
                                                            </td>
                                                            <td className="px-4 py-3">{term['P-value'].toExponential(2)}</td>
                                                            <td className="px-4 py-3">
                                                                <span className={`px-2 py-1 rounded text-xs font-medium ${
                                                                    term['Adjusted P-value'] < 0.001 ? 'bg-red-100 text-red-800' :
                                                                    term['Adjusted P-value'] < 0.01 ? 'bg-orange-100 text-orange-800' :
                                                                    term['Adjusted P-value'] < 0.05 ? 'bg-amber-100 text-amber-800' :
                                                                    'bg-slate-100 text-slate-800'
                                                                }`}>
                                                                    {term['Adjusted P-value'].toExponential(2)}
                                                                </span>
                                                            </td>
                                                            <td className="px-4 py-3">
                                                                <span className="bg-primary/10 text-primary px-2 py-1 rounded text-xs font-medium">
                                                                    {term['Gene Count']}
                                                                </span>
                                                            </td>
                                                            <td className="px-4 py-3 text-slate-600">{term['Term Size']}</td>
                                                            <td className="px-4 py-3">
                                                                <button
                                                                    onClick={() => setSelectedTerm(term)}
                                                                    className="text-primary hover:text-primary-dark text-xs font-medium"
                                                                >
                                                                    View Genes
                                                                </button>
                                                            </td>
                                                        </tr>
                                                    )})}
                                                </tbody>
                                            </table>
                                        </div>
                                    </div>
                                </div>
                            )}
                        </div>
                    </div>
                )}

                {/* Gene List Modal with Heatmap */}
                {selectedTerm && (
                    <div className="absolute inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4">
                        <div className="bg-white rounded-lg shadow-xl max-w-6xl w-full max-h-[90vh] overflow-hidden flex flex-col">
                            <div className="flex justify-between items-center p-4 border-b border-slate-200">
                                <div>
                                    <h3 className="text-lg font-semibold">Genes in Term</h3>
                                    <p className="text-xs text-slate-600 mt-1">
                                        {selectedTerm.Term} • P-value: {selectedTerm['Adjusted P-value'].toExponential(2)} • {selectedTerm['Gene Count']} genes
                                    </p>
                                </div>
                                <button
                                    onClick={() => {
                                        setSelectedTerm(null);
                                        setHeatmapData(null);
                                    }}
                                    className="text-slate-400 hover:text-slate-600"
                                >
                                    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                                    </svg>
                                </button>
                            </div>

                            <div className="flex-1 overflow-auto p-4">
                                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                                    {/* Gene List */}
                                    <div>
                                        <h4 className="text-sm font-semibold text-slate-700 mb-3">Gene List ({selectedTerm['Gene Count']})</h4>
                                        <div className="flex flex-wrap gap-2">
                                            {(() => {
                                                const geneIds = selectedTerm.Genes.split(';');
                                                const geneSymbols = selectedTerm.GeneSymbols?.split(';') || [];

                                                return geneIds.map((geneId, idx) => {
                                                    const symbol = geneSymbols[idx] || geneId;
                                                    const displayText = symbol !== geneId ? `${symbol}` : geneId;

                                                    return (
                                                        <span
                                                            key={idx}
                                                            className="px-3 py-1 bg-primary/10 text-primary rounded-full text-sm font-medium"
                                                            title={symbol !== geneId ? `Gene ID: ${geneId}\nGene Symbol: ${symbol}` : geneId}
                                                        >
                                                            {displayText}
                                                        </span>
                                                    );
                                                });
                                            })()}
                                        </div>
                                    </div>

                                    {/* Heatmap */}
                                    <div>
                                        <h4 className="text-sm font-semibold text-slate-700 mb-3">Expression Heatmap</h4>
                                        {isLoadingHeatmap ? (
                                            <div className="flex items-center justify-center h-64 bg-slate-50 rounded-lg">
                                                <div className="text-center">
                                                    <div className="animate-spin rounded-full h-12 w-12 border-4 border-slate-200 border-t-primary mx-auto mb-2"></div>
                                                    <p className="text-sm text-slate-600">Loading heatmap...</p>
                                                </div>
                                            </div>
                                        ) : heatmapData ? (
                                            <div className="border border-slate-200 rounded-lg overflow-hidden">
                                                <Plot
                                                    data={[
                                                        {
                                                            z: heatmapData.z,
                                                            x: heatmapData.x,
                                                            y: heatmapData.y,
                                                            type: 'heatmap',
                                                            colorscale: 'RdBu',
                                                            reversescale: false,
                                                            zmid: 0,
                                                            zmin: -3,
                                                            zmax: 3,
                                                            colorbar: {
                                                                title: 'Z-score',
                                                                thickness: 15,
                                                                len: 0.7
                                                            },
                                                            hovertemplate: 'Gene: %{y}<br>Sample: %{x}<br>Z-score: %{z:.2f}<extra></extra>'
                                                        }
                                                    ]}
                                                    layout={{
                                                        autosize: true,
                                                        margin: { l: 100, r: 50, t: 50, b: 80 },
                                                        xaxis: {
                                                            tickangle: -45,
                                                            tickfont: { size: 10 }
                                                        },
                                                        yaxis: {
                                                            tickfont: { size: 9 }
                                                        },
                                                        plot_bgcolor: '#ffffff',
                                                        paper_bgcolor: '#ffffff'
                                                    }}
                                                    config={{
                                                        responsive: true,
                                                        displayModeBar: true,
                                                        displaylogo: false,
                                                        toImageButtonOptions: {
                                                            format: 'png',
                                                            filename: `go_term_heatmap_${selectedTerm['Term ID']}`,
                                                            height: 600,
                                                            width: 800,
                                                            scale: 2
                                                        }
                                                    }}
                                                    style={{ width: '100%', height: '500px' }}
                                                />
                                            </div>
                                        ) : (
                                            <div className="flex items-center justify-center h-64 bg-slate-50 rounded-lg">
                                                <p className="text-sm text-slate-500">Failed to load heatmap data</p>
                                            </div>
                                        )}
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
};

export default GOAnalysisModal;
