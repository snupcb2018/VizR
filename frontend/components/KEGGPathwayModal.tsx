import React, { useState, useEffect, useMemo, useRef } from 'react';
import { ScatterChart, Scatter, XAxis, YAxis, ZAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import Plot from 'react-plotly.js';
import { apiService } from '../services/api';

interface KEGGPathwayModalProps {
    isOpen: boolean;
    onClose: () => void;
    workbenchId: number;
    selectedGenes: string[];
    comparisonName: string;
    toolName: string;
}

interface PathwayResult {
    Rank: number;
    'Term ID': string;
    'Term Name': string;
    'P-value': number;
    'Adjusted P-value': number;
    Genes: string;
    'Gene Count': number;
    'Term Size': number;
    kegg_url?: string;
    GeneSymbols?: string;
}

const KEGGPathwayModal: React.FC<KEGGPathwayModalProps> = ({
    isOpen,
    onClose,
    workbenchId,
    selectedGenes,
    comparisonName,
    toolName
}) => {
    const [pathwayResults, setPathwayResults] = useState<PathwayResult[]>([]);
    const [isLoading, setIsLoading] = useState(false);
    const [pValueCutoff, setPValueCutoff] = useState(0.05);
    const [selectedPathway, setSelectedPathway] = useState<PathwayResult | null>(null);
    const [heatmapData, setHeatmapData] = useState<any>(null);
    const [isLoadingHeatmap, setIsLoadingHeatmap] = useState(false);
    const [maxTerms, setMaxTerms] = useState(20);
    const [searchTerm, setSearchTerm] = useState('');
    const chartRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        if (isOpen && selectedGenes.length > 0) {
            loadPathwayData();
        }
    }, [isOpen, selectedGenes, pValueCutoff]);

    // Load heatmap data when pathway is selected
    useEffect(() => {
        if (selectedPathway && workbenchId) {
            loadHeatmapData();
        }
    }, [selectedPathway, workbenchId]);

    const loadHeatmapData = async () => {
        if (!selectedPathway) return;

        setIsLoadingHeatmap(true);
        try {
            const genes = selectedPathway.Genes.split(';');
            const response = await apiService.generateHeatmap(workbenchId, {
                genes,
                comparison: comparisonName,
                tool: toolName,
                clustering_method: 'ward',
                normalize: 'zscore'
            });

            if (response.z && response.x && response.y) {
                // Create Gene ID to Symbol mapping
                const geneIds = selectedPathway.Genes.split(';');
                const geneSymbols = selectedPathway.GeneSymbols?.split(';') || [];
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

    const loadPathwayData = async () => {
        setIsLoading(true);
        try {
            const response = await apiService.runKEGGPathway(workbenchId, {
                genes: selectedGenes,
                p_value_cutoff: pValueCutoff,
                organism: 'arabidopsis'
            });

            if (response.success && response.pathways) {
                setPathwayResults(response.pathways);
            } else {
                setPathwayResults([]);
            }
        } catch (error) {
            console.error('Failed to load KEGG pathway data:', error);
            alert('Failed to run KEGG pathway analysis. Please check the console for details.');
            setPathwayResults([]);
        } finally {
            setIsLoading(false);
        }
    };

    const openKEGGWebsite = (url: string) => {
        window.open(url, '_blank', 'noopener,noreferrer');
    };

    // Filter and sort pathways
    const filteredPathways = useMemo(() => {
        let data = [...pathwayResults];

        // Apply search filter
        if (searchTerm) {
            data = data.filter(pathway =>
                pathway['Term Name'].toLowerCase().includes(searchTerm.toLowerCase()) ||
                pathway['Term ID'].toLowerCase().includes(searchTerm.toLowerCase()) ||
                pathway.Genes.toLowerCase().includes(searchTerm.toLowerCase()) ||
                (pathway.GeneSymbols && pathway.GeneSymbols.toLowerCase().includes(searchTerm.toLowerCase()))
            );
        }

        return data.slice(0, maxTerms);
    }, [pathwayResults, searchTerm, maxTerms]);

    // Bubble plot data
    const bubbleData = useMemo(() => {
        return filteredPathways.map(pathway => ({
            x: -Math.log10(pathway['P-value']),
            y: pathway['Term Name'].length > 50 ? pathway['Term Name'].substring(0, 50) + '...' : pathway['Term Name'],
            z: pathway['Gene Count'],
            pValue: pathway['Adjusted P-value'],
            fullTerm: pathway['Term Name'],
            termId: pathway['Term ID'],
            genes: pathway.Genes,
            geneCount: pathway['Gene Count'],
            pathwayData: pathway  // Store original pathway data for click handler
        }));
    }, [filteredPathways]);

    // Dynamic chart height based on number of terms
    const chartHeight = useMemo(() => {
        const termCount = bubbleData.length;
        // 28px per term, minimum 500px, maximum 1200px
        return Math.max(500, Math.min(1200, termCount * 18));
    }, [bubbleData.length]);

    const getColorByPValue = (pValue: number) => {
        if (pValue < 0.001) return '#dc2626'; // red-600
        if (pValue < 0.01) return '#ea580c'; // orange-600
        if (pValue < 0.05) return '#f59e0b'; // amber-500
        return '#94a3b8'; // slate-400
    };

    const handleDownloadChart = async () => {
        if (!chartRef.current) return;

        try {
            // Use html-to-image for better CSS rendering
            const { toPng } = await import('html-to-image');

            const dataUrl = await toPng(chartRef.current, {
                quality: 1.0,
                pixelRatio: 2, // Higher resolution
                backgroundColor: '#ffffff'
            });

            const link = document.createElement('a');
            link.href = dataUrl;
            link.download = `kegg_pathway_bubble_plot.png`;
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
                    <p className="text-xs text-slate-500 mb-2">{data.termId}</p>
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

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex items-center justify-center p-4">
            <div className="bg-white rounded-lg shadow-xl max-w-6xl w-full max-h-[90vh] flex flex-col">
                {/* Header */}
                <div className="px-6 py-4 border-b border-slate-200 flex justify-between items-center">
                    <h2 className="text-xl font-bold text-slate-800">
                        KEGG Pathway Analysis ({selectedGenes.length} genes)
                    </h2>
                    <button
                        onClick={onClose}
                        className="text-slate-400 hover:text-slate-600 transition-colors"
                    >
                        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                    </button>
                </div>

                {/* Controls */}
                <div className="px-6 py-3 border-b border-slate-200 bg-slate-50">
                    <div className="flex items-center justify-between gap-4">
                        <div className="flex items-center gap-4">
                            <div>
                                <label className="text-sm font-medium text-slate-700 mr-2">P-value cutoff:</label>
                                <input
                                    type="number"
                                    value={pValueCutoff}
                                    onChange={(e) => setPValueCutoff(Number(e.target.value))}
                                    min="0.001"
                                    max="0.1"
                                    step="0.001"
                                    className="text-sm border border-slate-300 rounded px-2 py-1 w-20"
                                />
                            </div>
                            <div className="relative">
                                <input
                                    type="text"
                                    placeholder="Search pathways..."
                                    value={searchTerm}
                                    onChange={(e) => setSearchTerm(e.target.value)}
                                    className="pl-9 pr-4 py-2 border border-slate-300 rounded-lg text-sm focus:ring-primary focus:border-primary"
                                />
                                <svg className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                                </svg>
                            </div>
                            <div className="flex items-center space-x-2">
                                <label className="text-sm text-slate-600">Show top:</label>
                                <select
                                    value={maxTerms}
                                    onChange={(e) => setMaxTerms(Number(e.target.value))}
                                    className="border border-slate-300 rounded px-2 py-1 text-sm focus:ring-primary focus:border-primary"
                                >
                                    <option value={10}>10</option>
                                    <option value={20}>20</option>
                                    <option value={50}>50</option>
                                    <option value={100}>100</option>
                                </select>
                            </div>
                        </div>
                        <div className="flex items-center gap-3">
                            <div className="text-sm text-slate-600">
                                {filteredPathways.length} of {pathwayResults.length} pathways
                            </div>
                            <button
                                onClick={handleDownloadChart}
                                className="flex items-center space-x-2 px-3 py-1.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm"
                            >
                                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                                </svg>
                                <span>Download Chart</span>
                            </button>
                        </div>
                    </div>
                </div>

                {/* Content */}
                <div className="flex-1 overflow-auto p-6">
                    {isLoading ? (
                        <div className="flex items-center justify-center h-96">
                            <div className="text-center">
                                <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-blue-100 mb-4">
                                    <svg className="animate-spin h-8 w-8 text-blue-600" fill="none" viewBox="0 0 24 24">
                                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                                    </svg>
                                </div>
                                <p className="text-sm text-slate-600">Running KEGG pathway analysis...</p>
                            </div>
                        </div>
                    ) : filteredPathways.length > 0 ? (
                        <div className="space-y-6">
                            {/* Bubble Plot */}
                            <div ref={chartRef} className="bg-gradient-to-br from-slate-50 to-white border-2 border-slate-200 rounded-xl p-6 shadow-sm">
                                <h3 className="text-xl font-bold mb-6 text-slate-800 text-center">
                                    KEGG Pathway Enrichment
                                </h3>
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
                                            tick={{ fill: '#475569', fontSize: 12, fontWeight: 500 }}
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
                                            name="KEGG Pathway"
                                            width={300}
                                            tick={{ fill: '#475569', fontSize: 10, fontWeight: 500 }}
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
                                            name="KEGG Pathways"
                                            data={bubbleData}
                                            fill="#8884d8"
                                            shape="circle"
                                            fillOpacity={0.8}
                                            strokeWidth={2}
                                            stroke="#fff"
                                            onClick={(data) => {
                                                if (data && data.pathwayData) {
                                                    setSelectedPathway(data.pathwayData);
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

                            {/* Pathway List */}
                            <div className="space-y-2">
                                {filteredPathways.map((pathway) => {
                                const enrichmentRatio = ((pathway['Gene Count'] / pathway['Term Size']) * 100).toFixed(1);

                                return (
                                    <div key={pathway['Term ID']} className="border border-slate-200 rounded-lg overflow-hidden">
                                        {/* Pathway Header */}
                                        <div className="bg-white p-4 flex items-center justify-between hover:bg-slate-50 transition-colors">
                                            <div className="flex-1">
                                                <div className="flex items-center gap-3">
                                                    <div>
                                                        <div className="flex items-center gap-2">
                                                            <span className="inline-flex items-center justify-center w-6 h-6 text-xs font-bold text-white bg-blue-600 rounded-full">
                                                                {pathway.Rank}
                                                            </span>
                                                            <span className="font-medium text-slate-800">
                                                                {pathway['Term Name']}
                                                            </span>
                                                        </div>
                                                        <div className="text-sm text-slate-500 mt-1">
                                                            {pathway['Term ID']} • {pathway['Gene Count']}/{pathway['Term Size']} genes ({enrichmentRatio}%)
                                                        </div>
                                                    </div>
                                                </div>
                                            </div>
                                            <div className="flex items-center gap-4">
                                                <div className="text-right">
                                                    <div className="text-sm text-slate-600">Adj. P-value</div>
                                                    <div className="font-mono text-sm font-medium text-slate-800">
                                                        {pathway['Adjusted P-value'].toExponential(2)}
                                                    </div>
                                                </div>
                                                <button
                                                    onClick={() => setSelectedPathway(pathway)}
                                                    className="px-3 py-1.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm font-semibold"
                                                >
                                                    View Genes
                                                </button>
                                                {pathway.kegg_url && (
                                                    <button
                                                        onClick={() => openKEGGWebsite(pathway.kegg_url!)}
                                                        className="px-3 py-1.5 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors text-sm font-semibold flex items-center gap-1"
                                                    >
                                                        View in KEGG
                                                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                                                        </svg>
                                                    </button>
                                                )}
                                            </div>
                                        </div>
                                    </div>
                                );
                            })}
                            </div>
                        </div>
                    ) : (
                        <div className="flex items-center justify-center h-96">
                            <div className="text-center text-slate-500">
                                <svg className="w-16 h-16 mx-auto mb-4 text-slate-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                                </svg>
                                <p className="text-sm">No KEGG pathways found</p>
                                <p className="text-xs mt-1">Try adjusting the P-value cutoff</p>
                            </div>
                        </div>
                    )}
                </div>

                {/* Footer */}
                <div className="px-6 py-4 border-t border-slate-200 flex justify-between items-center bg-slate-50">
                    <div className="text-sm text-slate-600">
                        Tip: Click bubbles or "View Genes" to see gene list and heatmap | Use "View in KEGG" to see pathway diagram
                    </div>
                    <div className="flex gap-2">
                        <button
                            onClick={onClose}
                            className="px-4 py-2 bg-slate-200 text-slate-700 rounded-lg hover:bg-slate-300 transition-colors text-sm font-semibold"
                        >
                            Close
                        </button>
                    </div>
                </div>

                {/* Gene List Modal with Heatmap */}
                {selectedPathway && (
                    <div className="absolute inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4">
                        <div className="bg-white rounded-lg shadow-xl max-w-6xl w-full max-h-[90vh] overflow-hidden flex flex-col">
                            <div className="flex justify-between items-center p-4 border-b border-slate-200">
                                <div>
                                    <h3 className="text-lg font-semibold">Genes in Pathway</h3>
                                    <p className="text-xs text-slate-600 mt-1">
                                        {selectedPathway['Term Name']} • P-value: {selectedPathway['Adjusted P-value'].toExponential(2)} • {selectedPathway['Gene Count']} genes
                                    </p>
                                </div>
                                <button
                                    onClick={() => {
                                        setSelectedPathway(null);
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
                                        <h4 className="text-sm font-semibold text-slate-700 mb-3">Gene List ({selectedPathway['Gene Count']})</h4>
                                        <div className="flex flex-wrap gap-2">
                                            {(() => {
                                                const geneIds = selectedPathway.Genes.split(';');
                                                const geneSymbols = selectedPathway.GeneSymbols?.split(';') || [];

                                                return geneIds.map((geneId, idx) => {
                                                    const symbol = geneSymbols[idx] || geneId;
                                                    const displayText = symbol !== geneId ? `${symbol}` : geneId;

                                                    return (
                                                        <span
                                                            key={idx}
                                                            className="px-3 py-1 bg-blue-100 text-blue-800 rounded-full text-sm font-medium"
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
                                                    <div className="animate-spin rounded-full h-12 w-12 border-4 border-slate-200 border-t-blue-600 mx-auto mb-2"></div>
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
                                                            filename: `kegg_pathway_heatmap_${selectedPathway['Term ID']}`,
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

export default KEGGPathwayModal;
