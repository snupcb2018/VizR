import React, { useState, useEffect, useMemo } from 'react';
import Plot from 'react-plotly.js';
import { apiService } from '../services/api';
import { useHeatmapColors } from '../contexts/UserSettingsContext';

interface HeatmapAnalysisModalProps {
    isOpen: boolean;
    onClose: () => void;
    workbenchId: number;
    selectedGenes: string[];
    comparisonName: string;
    toolName: string;
}

const HeatmapAnalysisModal: React.FC<HeatmapAnalysisModalProps> = ({
    isOpen,
    onClose,
    workbenchId,
    selectedGenes,
    comparisonName,
    toolName
}) => {
    const { colors } = useHeatmapColors();
    const [heatmapData, setHeatmapData] = useState<any>(null);
    const [isLoading, setIsLoading] = useState(false);
    const [clusteringMethod, setClusteringMethod] = useState<'ward' | 'average' | 'complete'>('ward');
    const [normalizationMethod, setNormalizationMethod] = useState<'zscore' | 'log2_centered' | 'log2fc_reference'>('zscore');
    const [referenceSample, setReferenceSample] = useState<string>('');
    const [yAxisFontSize, setYAxisFontSize] = useState(10); // 동적 Y축 폰트 크기

    // 자동 Z-score Clip 계산 (데이터 기반)
    const zscoreClip = useMemo(() => {
        if (!heatmapData || !heatmapData.z) return 3;

        const allValues = heatmapData.z.flat().filter((v: number) => !isNaN(v) && isFinite(v));
        if (allValues.length === 0) return 3;

        const absValues = allValues.map((v: number) => Math.abs(v));
        const sorted = absValues.sort((a: number, b: number) => a - b);
        const p99 = sorted[Math.floor(sorted.length * 0.99)];

        // 최소 2, 최대 5로 제한
        return Math.min(5, Math.max(2, Math.ceil(p99 * 10) / 10));
    }, [heatmapData]);

    // 높이 계산 로직
    const calculateDimensions = useMemo(() => {
        const geneCount = selectedGenes.length;
        const MIN_HEIGHT = 300;    // 최소 전체 높이 (범례가 잘 보이도록)
        const MAX_HEIGHT = 1200;   // 최대 높이
        const MIN_ROW_HEIGHT = 2;  // 최소 행 높이
        const MAX_ROW_HEIGHT = 15; // 최대 행 높이
        const PADDING = 100;       // 상하 여백

        // 행 높이 계산 (최소 2px, 최대 15px)
        let rowHeight = Math.min(MAX_ROW_HEIGHT, Math.max(MIN_ROW_HEIGHT, 15));

        // 전체 높이 = 유전자 수 × 행 높이 + 여백
        let totalHeight = geneCount * rowHeight + PADDING;

        // 최소/최대 높이 제한
        totalHeight = Math.max(MIN_HEIGHT, totalHeight);
        totalHeight = Math.min(MAX_HEIGHT, totalHeight);

        // 최대 높이 도달 시 행 높이 재조정
        if (totalHeight === MAX_HEIGHT && geneCount > 0) {
            rowHeight = Math.floor((MAX_HEIGHT - PADDING) / geneCount);
        }

        return {
            height: totalHeight,
            rowHeight: rowHeight,
            needsScroll: totalHeight === MAX_HEIGHT
        };
    }, [selectedGenes.length]);

    // normalizationMethod가 log2fc_reference로 변경될 때 기준 샘플 자동 설정
    useEffect(() => {
        if (normalizationMethod === 'log2fc_reference' && !referenceSample) {
            // 기존 heatmapData가 있으면 첫 번째 샘플을 기준으로 설정
            if (heatmapData && heatmapData.x && heatmapData.x.length > 0) {
                setReferenceSample(heatmapData.x[0]);
            }
        }
    }, [normalizationMethod]);

    useEffect(() => {
        if (isOpen && selectedGenes.length > 0) {
            loadHeatmapData();
        }
    }, [isOpen, selectedGenes, clusteringMethod, normalizationMethod, referenceSample]);

    // 히트맵 데이터 로드 시 초기 폰트 크기 설정
    useEffect(() => {
        if (heatmapData && heatmapData.y) {
            const totalGenes = heatmapData.y.length;
            const initialFontSize = totalGenes <= 50 ? 10 : totalGenes <= 100 ? 8 : 6;
            setYAxisFontSize(initialFontSize);
        }
    }, [heatmapData]);

    const loadHeatmapData = async () => {
        setIsLoading(true);
        try {
            // 실제 API 호출 (백엔드에서 TMM counts 로드 + 정규화 + 클러스터링)
            const requestBody: any = {
                genes: selectedGenes,
                comparison: comparisonName,
                tool: toolName,
                clustering_method: clusteringMethod,
                normalize: normalizationMethod
            };

            // log2fc_reference 모드일 때만 reference_sample 추가
            if (normalizationMethod === 'log2fc_reference' && referenceSample) {
                requestBody.reference_sample = referenceSample;
            }

            const response = await apiService.generateHeatmap(workbenchId, requestBody);

            // Gene symbols가 있으면 y축에 사용
            if (response.gene_symbols && response.gene_symbols.length > 0) {
                setHeatmapData({
                    ...response,
                    y: response.gene_symbols
                });
            } else {
                setHeatmapData(response);
            }
        } catch (error) {
            console.error('Failed to load heatmap data:', error);
            alert('Failed to generate heatmap. Please check the console for details.');
        } finally {
            setIsLoading(false);
        }
    };

    const plotConfig = useMemo(() => {
        if (!heatmapData) return null;

        const { height, rowHeight, needsScroll } = calculateDimensions;

        // Colorbar title과 hover value 설정
        let colorbarTitle = 'Z-score';
        let hoverValue = 'Z-score';
        if (normalizationMethod === 'log2_centered') {
            colorbarTitle = 'log2(centered)';
            hoverValue = 'log2';
        } else if (normalizationMethod === 'log2fc_reference') {
            colorbarTitle = 'Log2FC';
            hoverValue = 'Log2FC';
        }

        // 범위 설정: z-score는 클리핑, 나머지는 자동 범위
        const zRange = normalizationMethod === 'zscore'
            ? { zmin: -zscoreClip, zmax: zscoreClip }
            : {};

        // X축 tickfont 설정 (기준 샘플 하이라이트)
        const xAxisTickfont = normalizationMethod === 'log2fc_reference' && referenceSample
            ? {
                size: 10,
                color: heatmapData.x.map((sample: string) =>
                    sample === referenceSample ? '#2563eb' : '#000000'  // 기준 샘플은 파란색
                )
            }
            : { size: 10 };

        // Generate custom colorscale from user settings
        const customColorscale = [
            [0, colors.low],      // Lowest value
            [0.5, colors.middle], // Middle value
            [1, colors.high]      // Highest value
        ];

        return {
            data: [{
                type: 'heatmap',
                z: heatmapData.z,
                x: heatmapData.x,
                y: heatmapData.y,
                colorscale: customColorscale,
                zmid: 0,
                ...zRange,
                colorbar: {
                    title: colorbarTitle,
                    titleside: 'right',
                    thickness: 15,
                    len: 0.7,
                    x: 1.02,
                    titlefont: { size: 12, color: '#000000' },
                    tickfont: { size: 10, color: '#000000' },
                    outlinewidth: 0,
                    borderwidth: 0
                },
                hovertemplate: `Gene: %{y}<br>Sample: %{x}<br>${hoverValue}: %{z:.2f}<extra></extra>`,
                xgap: 0.5,
                ygap: 0.5
            }],
            layout: {
                title: {
                    text: `Expression Heatmap - ${comparisonName}`,
                    font: { size: 16, family: 'Arial, sans-serif' }
                },
                dragmode: 'zoom',  // 명시적으로 줌 모드 설정
                xaxis: {
                    title: 'Samples',
                    side: 'bottom',
                    tickangle: -45,
                    tickfont: xAxisTickfont,
                    fixedrange: false  // 줌 활성화
                },
                yaxis: {
                    title: `Genes (${heatmapData.y.length})`,
                    tickmode: 'array',
                    tickvals: Array.from({ length: heatmapData.y.length }, (_, i) => i),
                    ticktext: heatmapData.y,
                    tickfont: { size: yAxisFontSize },
                    showticklabels: true,
                    fixedrange: false  // 줌 활성화
                },
                width: 900,
                height: height + 100, // 여백 추가
                margin: { l: 100, r: 100, t: 80, b: 100 },
                paper_bgcolor: 'white',
                plot_bgcolor: 'white'
            },
            config: {
                toImageButtonOptions: {
                    format: 'png',
                    filename: `heatmap_${comparisonName}_${new Date().toISOString().split('T')[0]}`,
                    height: height + 100,
                    width: 900,
                    scale: 10
                },
                displaylogo: false,
                responsive: true
            }
        };
    }, [heatmapData, zscoreClip, calculateDimensions, comparisonName, yAxisFontSize, normalizationMethod, referenceSample, colors]);

    // 줌 시 Y축 폰트 크기 동적 조정
    const handleRelayout = (event: any) => {
        if (!heatmapData) return;

        // Y축 범위 변경 감지
        if (event['yaxis.range[0]'] !== undefined && event['yaxis.range[1]'] !== undefined) {
            const yMin = Math.floor(event['yaxis.range[0]']);
            const yMax = Math.ceil(event['yaxis.range[1]']);
            const visibleGenes = yMax - yMin;

            // 보이는 유전자 수에 따라 폰트 크기 계산
            // 10-30개: 12px, 30-50개: 10px, 50+개: 8px
            let newFontSize = 10;
            if (visibleGenes <= 10) {
                newFontSize = 14;
            } else if (visibleGenes <= 20) {
                newFontSize = 12;
            } else if (visibleGenes <= 50) {
                newFontSize = 10;
            } else if (visibleGenes <= 100) {
                newFontSize = 8;
            } else {
                newFontSize = 6;
            }

            setYAxisFontSize(newFontSize);
        }

        // 리셋 감지 (더블클릭)
        if (event['yaxis.autorange'] === true) {
            // 전체 유전자 수로 초기 폰트 크기 계산
            const totalGenes = heatmapData.y.length;
            const initialFontSize = totalGenes <= 50 ? 10 : totalGenes <= 100 ? 8 : 6;
            setYAxisFontSize(initialFontSize);
        }
    };

    // 히트맵 클릭 시 기준 샘플 변경 (log2fc_reference 모드일 때만)
    const handlePlotClick = (event: any) => {
        if (normalizationMethod !== 'log2fc_reference') return;
        if (!event.points || event.points.length === 0) return;

        const clickedSample = event.points[0].x;
        if (clickedSample && typeof clickedSample === 'string') {
            setReferenceSample(clickedSample);
        }
    };

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex items-center justify-center p-4">
            <div className="bg-white rounded-lg shadow-xl max-w-6xl w-full max-h-[90vh] flex flex-col">
                {/* Header */}
                <div className="px-6 py-4 border-b border-slate-200 flex justify-between items-center">
                    <h2 className="text-xl font-bold text-slate-800">
                        Heatmap Analysis ({selectedGenes.length} genes)
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
                    <div className="flex items-center gap-6">
                        <div>
                            <label className="text-sm font-medium text-slate-700 mr-2">Normalization:</label>
                            <select
                                value={normalizationMethod}
                                onChange={(e) => setNormalizationMethod(e.target.value as any)}
                                className="text-sm border border-slate-300 rounded px-2 py-1"
                                disabled={isLoading}
                            >
                                <option value="zscore">Z-score</option>
                                <option value="log2_centered">log2(centered)</option>
                                <option value="log2fc_reference">Log2FC vs Reference</option>
                            </select>
                        </div>

                        {/* Reference Sample 선택 (log2fc_reference 모드일 때만 표시) */}
                        {normalizationMethod === 'log2fc_reference' && heatmapData && heatmapData.x && (
                            <div>
                                <label className="text-sm font-medium text-slate-700 mr-2">Reference Sample:</label>
                                <select
                                    value={referenceSample}
                                    onChange={(e) => setReferenceSample(e.target.value)}
                                    className="text-sm border border-slate-300 rounded px-2 py-1"
                                    disabled={isLoading}
                                >
                                    {heatmapData.x.map((sample: string) => (
                                        <option key={sample} value={sample}>{sample}</option>
                                    ))}
                                </select>
                                <span className="text-xs text-slate-500 ml-2">
                                    (or click sample in heatmap)
                                </span>
                            </div>
                        )}

                        <div>
                            <label className="text-sm font-medium text-slate-700 mr-2">Clustering:</label>
                            <select
                                value={clusteringMethod}
                                onChange={(e) => setClusteringMethod(e.target.value as any)}
                                className="text-sm border border-slate-300 rounded px-2 py-1"
                            >
                                <option value="ward">Ward</option>
                                <option value="average">Average</option>
                                <option value="complete">Complete</option>
                            </select>
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
                                <p className="text-sm text-slate-600">Generating heatmap...</p>
                            </div>
                        </div>
                    ) : plotConfig ? (
                        <div className={calculateDimensions.needsScroll ? 'overflow-y-auto' : ''}>
                            <Plot {...plotConfig} onClick={handlePlotClick} onRelayout={handleRelayout} />
                        </div>
                    ) : null}
                </div>

                {/* Footer */}
                <div className="px-6 py-4 border-t border-slate-200 flex justify-between items-center bg-slate-50">
                    <div className="text-sm text-slate-600">
                        Tip: Drag to zoom, double-click to reset | Use camera icon (📷) in toolbar to download high-resolution PNG
                        {normalizationMethod === 'log2fc_reference' && <span> | Click sample name to change reference</span>}
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
            </div>
        </div>
    );
};

export default HeatmapAnalysisModal;
