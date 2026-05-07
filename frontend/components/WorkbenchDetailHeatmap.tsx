import React, { useState, useEffect, useMemo } from 'react';
import Plot from 'react-plotly.js';
import { apiService } from '../services/api';
import InterestingGenesSidebar from './InterestingGenesSidebar';
import { useHeatmapColors } from '../contexts/UserSettingsContext';

interface WorkbenchDetailHeatmapProps {
    workbenchId: number;
}

const WorkbenchDetailHeatmap: React.FC<WorkbenchDetailHeatmapProps> = ({ workbenchId }) => {
    const { colors } = useHeatmapColors();
    const [selectedGenes, setSelectedGenes] = useState<string[]>([]);
    const [selectedFileNames, setSelectedFileNames] = useState<string[]>([]);
    const [heatmapData, setHeatmapData] = useState<any>(null);
    const [isLoading, setIsLoading] = useState(false);
    const [clusteringMethod, setClusteringMethod] = useState<'ward' | 'average' | 'complete'>('ward');
    const [normalizationMethod, setNormalizationMethod] = useState<'zscore' | 'log2_centered' | 'log2fc_reference'>('zscore');
    const [referenceSample, setReferenceSample] = useState<string>('');
    const [yAxisFontSize, setYAxisFontSize] = useState(10);

    // Heatmap cache: Map<cacheKey, heatmapData>
    const [heatmapCache] = useState<Map<string, any>>(new Map());

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
        const MIN_HEIGHT = 300;
        const MAX_HEIGHT = 1200;
        const MIN_ROW_HEIGHT = 2;
        const MAX_ROW_HEIGHT = 15;
        const PADDING = 100;

        let rowHeight = Math.min(MAX_ROW_HEIGHT, Math.max(MIN_ROW_HEIGHT, 15));
        let totalHeight = geneCount * rowHeight + PADDING;

        totalHeight = Math.max(MIN_HEIGHT, totalHeight);
        totalHeight = Math.min(MAX_HEIGHT, totalHeight);

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

    // 유전자 선택 시 히트맵 로드
    useEffect(() => {
        if (selectedGenes.length > 0) {
            loadHeatmapData();
        } else {
            setHeatmapData(null);
        }
    }, [selectedGenes, clusteringMethod, normalizationMethod, referenceSample]);

    // 히트맵 데이터 로드 시 초기 폰트 크기 설정
    useEffect(() => {
        if (heatmapData && heatmapData.y) {
            const totalGenes = heatmapData.y.length;
            const initialFontSize = totalGenes <= 50 ? 10 : totalGenes <= 100 ? 8 : 6;
            setYAxisFontSize(initialFontSize);
        }
    }, [heatmapData]);

    // 캐시 키 생성 함수
    const generateCacheKey = (genes: string[], clustering: string, normalize: string, refSample: string): string => {
        // 유전자 목록을 정렬하여 순서에 무관하게 동일한 키 생성
        const sortedGenes = [...genes].sort();
        return `genes:${JSON.stringify(sortedGenes)}|clustering:${clustering}|normalize:${normalize}|ref:${refSample}`;
    };

    const loadHeatmapData = async () => {
        // 캐시 키 생성
        const cacheKey = generateCacheKey(selectedGenes, clusteringMethod, normalizationMethod, referenceSample);

        // 캐시에서 확인
        if (heatmapCache.has(cacheKey)) {
            const cachedData = heatmapCache.get(cacheKey);
            setHeatmapData(cachedData);
            return;
        }

        setIsLoading(true);
        try {
            // TMM counts 기반 히트맵 생성 (comparison/tool 없이)
            const requestBody: any = {
                genes: selectedGenes,
                comparison: '',  // 빈 문자열
                tool: '',  // 빈 문자열
                clustering_method: clusteringMethod,
                normalize: normalizationMethod
            };

            // log2fc_reference 모드일 때만 reference_sample 추가
            if (normalizationMethod === 'log2fc_reference' && referenceSample) {
                requestBody.reference_sample = referenceSample;
            }

            const response = await apiService.generateHeatmap(workbenchId, requestBody);

            // Gene symbols가 있으면 y축에 사용
            const processedData = response.gene_symbols && response.gene_symbols.length > 0
                ? { ...response, y: response.gene_symbols }
                : response;

            // 캐시에 저장
            heatmapCache.set(cacheKey, processedData);

            setHeatmapData(processedData);
        } catch (error) {
            console.error('Failed to load heatmap data:', error);
            alert('Failed to generate heatmap. Please check the console for details.');
            setHeatmapData(null);
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

        // Normalization 방법 표시 텍스트
        const getNormalizationText = () => {
            if (normalizationMethod === 'zscore') return 'Z-score';
            if (normalizationMethod === 'log2_centered') return 'log2(centered)';
            if (normalizationMethod === 'log2fc_reference') {
                return referenceSample ? `Log2FC (vs ${referenceSample})` : 'Log2FC';
            }
            return '';
        };

        // 제목 생성 (멀티라인 지원)
        const generateTitleInfo = () => {
            const normText = getNormalizationText();
            const geneCount = ` (${selectedGenes.length} genes, ${normText})`;

            if (selectedFileNames.length === 0) {
                return { text: `Expression Heatmap${geneCount}`, lineCount: 1 };
            }

            const maxLineLength = 120; // 한 줄 최대 글자 수
            const fileNamesText = selectedFileNames.join(', ');

            // 파일 이름이 짧으면 한 줄로
            if (fileNamesText.length + geneCount.length <= maxLineLength) {
                return { text: fileNamesText + geneCount, lineCount: 1 };
            }

            // 긴 경우 적절한 위치에서 줄바꿈
            const words = selectedFileNames;
            const lines: string[] = [];
            let currentLine = '';

            for (let i = 0; i < words.length; i++) {
                const word = words[i];
                const separator = i === 0 ? '' : ', ';
                const testLine = currentLine + separator + word;

                if (testLine.length > maxLineLength && currentLine !== '') {
                    lines.push(currentLine);
                    currentLine = word;
                } else {
                    currentLine = testLine;
                }
            }

            if (currentLine !== '') {
                lines.push(currentLine);
            }

            // 마지막 줄에 gene count와 normalization 추가
            if (lines.length > 0) {
                lines[lines.length - 1] += geneCount;
            }

            return { text: lines.join('<br>'), lineCount: lines.length };
        };

        const titleInfo = generateTitleInfo();

        // 제목 줄 수에 따라 상단 마진 동적 조정 (각 줄당 약 30px, 기본 80px)
        const topMargin = 80 + (titleInfo.lineCount - 1) * 30;

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
                    text: titleInfo.text,
                    font: { size: 16, family: 'Arial, sans-serif' },
                    xanchor: 'center',
                    yanchor: 'top',
                    x: 0.5
                },
                margin: {
                    t: topMargin,
                    b: 100,
                    l: 150,
                    r: 50
                },
                dragmode: 'zoom',
                xaxis: {
                    title: 'Samples',
                    side: 'bottom',
                    tickangle: -45,
                    tickfont: xAxisTickfont,
                    fixedrange: false
                },
                yaxis: {
                    title: `Genes (${heatmapData.y.length})`,
                    tickmode: 'array',
                    tickvals: Array.from({ length: heatmapData.y.length }, (_, i) => i),
                    ticktext: heatmapData.y,
                    tickfont: { size: yAxisFontSize },
                    showticklabels: true,
                    fixedrange: false
                },
                width: undefined,  // Auto-width
                height: height + 100,
                paper_bgcolor: 'white',
                plot_bgcolor: 'white',
                autosize: true
            },
            config: {
                toImageButtonOptions: {
                    format: 'png',
                    filename: `heatmap_${new Date().toISOString().split('T')[0]}`,
                    height: height + 100,
                    width: 900,
                    scale: 10
                },
                displaylogo: false,
                responsive: true
            }
        };
    }, [heatmapData, zscoreClip, calculateDimensions, yAxisFontSize, normalizationMethod, selectedGenes.length, selectedFileNames, referenceSample, colors]);

    // 히트맵 클릭 시 기준 샘플 변경 (log2fc_reference 모드일 때만)
    const handlePlotClick = (event: any) => {
        if (normalizationMethod !== 'log2fc_reference') return;
        if (!event.points || event.points.length === 0) return;

        const clickedSample = event.points[0].x;
        if (clickedSample && typeof clickedSample === 'string') {
            setReferenceSample(clickedSample);
        }
    };

    // 줌 시 Y축 폰트 크기 동적 조정
    const handleRelayout = (event: any) => {
        if (!heatmapData) return;

        if (event['yaxis.range[0]'] !== undefined && event['yaxis.range[1]'] !== undefined) {
            const yMin = Math.floor(event['yaxis.range[0]']);
            const yMax = Math.ceil(event['yaxis.range[1]']);
            const visibleGenes = yMax - yMin;

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

        if (event['yaxis.autorange'] === true) {
            const totalGenes = heatmapData.y.length;
            const initialFontSize = totalGenes <= 50 ? 10 : totalGenes <= 100 ? 8 : 6;
            setYAxisFontSize(initialFontSize);
        }
    };

    return (
        <div className="h-full flex">
            {/* Sidebar */}
            <InterestingGenesSidebar
                workbenchId={workbenchId}
                onGenesSelected={(genes, fileNames) => {
                    setSelectedGenes(genes);
                    setSelectedFileNames(fileNames);
                }}
            />

            {/* Main content */}
            <div className="flex-1 flex flex-col bg-slate-50">
                {/* Controls */}
                <div className="px-6 py-4 border-b border-slate-200 bg-white">
                    <div className="flex items-center gap-6 flex-wrap">
                        <div>
                            <label className="text-sm font-medium text-slate-700 mr-2">Normalization:</label>
                            <select
                                value={normalizationMethod}
                                onChange={(e) => setNormalizationMethod(e.target.value as any)}
                                className="text-sm border border-slate-300 rounded px-3 py-1.5"
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
                                    className="text-sm border border-slate-300 rounded px-3 py-1.5"
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
                                className="text-sm border border-slate-300 rounded px-3 py-1.5"
                                disabled={isLoading}
                            >
                                <option value="ward">Ward</option>
                                <option value="average">Average</option>
                                <option value="complete">Complete</option>
                            </select>
                        </div>
                        {selectedGenes.length > 0 && (
                            <div className="ml-auto">
                                <span className="text-sm text-slate-600">
                                    {selectedGenes.length} gene{selectedGenes.length > 1 ? 's' : ''} selected
                                </span>
                            </div>
                        )}
                    </div>
                </div>

                {/* Content */}
                <div className="flex-1 overflow-auto p-6">
                    {isLoading ? (
                        <div className="flex items-center justify-center h-full">
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
                    ) : selectedGenes.length === 0 ? (
                        <div className="flex items-center justify-center h-full">
                            <div className="text-center max-w-md">
                                <svg className="w-16 h-16 text-slate-300 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                                </svg>
                                <h3 className="text-lg font-semibold text-slate-700 mb-2">No genes selected</h3>
                                <p className="text-sm text-slate-500">
                                    Select gene sets from the sidebar to generate a heatmap.
                                    Use Ctrl+Click to select multiple sets.
                                </p>
                            </div>
                        </div>
                    ) : plotConfig ? (
                        <div className="bg-white rounded-lg border border-slate-200 p-4">
                            <Plot {...plotConfig} onClick={handlePlotClick} onRelayout={handleRelayout} style={{ width: '100%', height: 'auto' }} />
                            <div className="mt-4 text-xs text-slate-500 text-center">
                                Tip: Drag to zoom, double-click to reset | Use camera icon (📷) in toolbar to download high-resolution PNG
                                {normalizationMethod === 'log2fc_reference' && <span> | Click sample name to change reference</span>}
                            </div>
                        </div>
                    ) : null}
                </div>
            </div>
        </div>
    );
};

export default WorkbenchDetailHeatmap;
