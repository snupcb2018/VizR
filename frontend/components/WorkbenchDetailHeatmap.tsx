import React, { useState, useEffect, useMemo, useRef } from 'react';
import Plot from 'react-plotly.js';
import Plotly from 'plotly.js/dist/plotly';
import { apiService } from '../services/api';
import InterestingGenesSidebar from './InterestingGenesSidebar';
import { useHeatmapColors } from '../contexts/UserSettingsContext';

interface WorkbenchDetailHeatmapProps {
    workbenchId: number;
}

const HEATMAP_SELECTION_LOG_PREFIX = '[HEATMAP-GENE-SELECTION]';

type HeatmapModifierKeys = {
    shiftKey: boolean;
    ctrlKey: boolean;
    metaKey: boolean;
    altKey: boolean;
};

type HeatmapLogLevel = 'debug' | 'info' | 'warn' | 'error';

type HeatmapClickedGene = {
    gene: string;
    rowIndex: number;
};

type HeatmapDisplayRow = {
    fullRowIndex: number;
    geneId: string;
    label: string;
    defaultLabel: string;
    zRow: number[];
};

type HeatmapLabelEditorState = {
    geneId: string;
    fullRowIndex: number;
    currentLabel: string;
    defaultLabel: string;
} | null;

const clamp = (value: number, minimum: number, maximum: number) =>
    Math.min(maximum, Math.max(minimum, value));

const zoomAxisRange = (
    range: unknown,
    pointerFraction: number,
    zoomFactor: number,
    itemCount: number
): [number, number] | null => {
    if (!Array.isArray(range) || range.length < 2 || itemCount <= 0) return null;

    const start = Number(range[0]);
    const end = Number(range[1]);
    if (!Number.isFinite(start) || !Number.isFinite(end) || start === end) return null;

    const dataMinimum = -0.5;
    const dataMaximum = itemCount - 0.5;
    const fullSpan = dataMaximum - dataMinimum;
    const direction = end > start ? 1 : -1;
    const center = start + (end - start) * clamp(pointerFraction, 0, 1);
    const currentSpan = Math.abs(end - start);
    const nextSpan = clamp(currentSpan * zoomFactor, Math.min(0.5, fullSpan), fullSpan);

    if (nextSpan >= fullSpan) {
        return direction > 0
            ? [dataMinimum, dataMaximum]
            : [dataMaximum, dataMinimum];
    }

    const centerFromStart = Math.abs(center - start) / currentSpan;
    let nextMinimum = center - nextSpan * centerFromStart;
    let nextMaximum = nextMinimum + nextSpan;

    if (nextMinimum < dataMinimum) {
        nextMaximum += dataMinimum - nextMinimum;
        nextMinimum = dataMinimum;
    }
    if (nextMaximum > dataMaximum) {
        nextMinimum -= nextMaximum - dataMaximum;
        nextMaximum = dataMaximum;
    }

    return direction > 0
        ? [nextMinimum, nextMaximum]
        : [nextMaximum, nextMinimum];
};

const summarizePlotPoint = (point: any) => {
    if (!point) return null;
    return {
        x: point.x,
        y: point.y,
        customdata: point.customdata,
        pointIndex: point.pointIndex,
        pointNumber: point.pointNumber,
        curveNumber: point.curveNumber,
    };
};

const emitHeatmapSelectionLog = (level: HeatmapLogLevel, event: string, payload: Record<string, unknown> = {}) => {
    const message = `${HEATMAP_SELECTION_LOG_PREFIX} ${event}`;
    const consoleMethod = level === 'warn' ? 'warn' : level;

    console[consoleMethod](message, payload);

    fetch('/api/client-logs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
            level,
            source: 'WorkbenchDetailHeatmap',
            event,
            payload,
            timestamp: new Date().toISOString(),
        }),
    }).catch((error) => {
        console.debug(`${HEATMAP_SELECTION_LOG_PREFIX} failed to send client log`, error);
    });
};

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
    const [selectedHeatmapRowIndexes, setSelectedHeatmapRowIndexes] = useState<number[]>([]);
    const [lastClickedHeatmapGene, setLastClickedHeatmapGene] = useState<string | null>(null);
    const [lastClickedHeatmapRowIndex, setLastClickedHeatmapRowIndex] = useState<number | null>(null);
    const [copyStatus, setCopyStatus] = useState<'idle' | 'copied' | 'failed'>('idle');
    const [visibleHeatmapRowIndexes, setVisibleHeatmapRowIndexes] = useState<number[] | null>(null);
    const [customHeatmapLabels, setCustomHeatmapLabels] = useState<Record<string, string>>({});
    const [labelEditor, setLabelEditor] = useState<HeatmapLabelEditorState>(null);
    const [labelEditorValue, setLabelEditorValue] = useState('');
    const lastClickedHeatmapGeneRef = useRef<string | null>(null);
    const lastClickedHeatmapRowIndexRef = useRef<number | null>(null);
    const heatmapGeneOrderRef = useRef<string[]>([]);
    const displayHeatmapRowsRef = useRef<HeatmapDisplayRow[]>([]);
    const plotContainerRef = useRef<HTMLDivElement | null>(null);
    const modifierKeysRef = useRef<HeatmapModifierKeys>({
        shiftKey: false,
        ctrlKey: false,
        metaKey: false,
        altKey: false,
    });

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
        const syncModifierKeys = (event: KeyboardEvent, source: 'keydown' | 'keyup') => {
            modifierKeysRef.current = {
                shiftKey: event.shiftKey,
                ctrlKey: event.ctrlKey,
                metaKey: event.metaKey,
                altKey: event.altKey,
            };

            if (event.key === 'Shift' || event.key === 'Control' || event.key === 'Meta' || event.key === 'Alt') {
                emitHeatmapSelectionLog('info', `modifier-${source}`, {
                    key: event.key,
                    modifiers: modifierKeysRef.current,
                });
            }
        };

        const handleKeyDown = (event: KeyboardEvent) => syncModifierKeys(event, 'keydown');
        const handleKeyUp = (event: KeyboardEvent) => syncModifierKeys(event, 'keyup');
        const handleBlur = () => {
            modifierKeysRef.current = {
                shiftKey: false,
                ctrlKey: false,
                metaKey: false,
                altKey: false,
            };
            emitHeatmapSelectionLog('info', 'modifier-reset-window-blur');
        };

        window.addEventListener('keydown', handleKeyDown);
        window.addEventListener('keyup', handleKeyUp);
        window.addEventListener('blur', handleBlur);

        return () => {
            window.removeEventListener('keydown', handleKeyDown);
            window.removeEventListener('keyup', handleKeyUp);
            window.removeEventListener('blur', handleBlur);
        };
    }, []);

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
            setSelectedHeatmapRowIndexes([]);
            setLastClickedHeatmapGene(null);
            setLastClickedHeatmapRowIndex(null);
            lastClickedHeatmapGeneRef.current = null;
            lastClickedHeatmapRowIndexRef.current = null;
            setCopyStatus('idle');
            setVisibleHeatmapRowIndexes(null);
            setCustomHeatmapLabels({});
            setLabelEditor(null);
        }
    }, [heatmapData]);

    const heatmapGeneOrder = useMemo(() => {
        if (!heatmapData?.y) return [];
        return heatmapData.y.map((gene: unknown) => String(gene));
    }, [heatmapData]);

    const heatmapGeneLabels = useMemo(() => {
        if (!heatmapData?.y) return [];
        const labels = Array.isArray(heatmapData.gene_symbols) ? heatmapData.gene_symbols : [];
        return heatmapData.y.map((gene: unknown, rowIndex: number) => {
            const geneId = String(gene);
            if (customHeatmapLabels[geneId]) {
                return customHeatmapLabels[geneId];
            }
            const label = labels[rowIndex];
            return label ? String(label) : geneId;
        });
    }, [customHeatmapLabels, heatmapData]);

    const heatmapDefaultGeneLabels = useMemo(() => {
        if (!heatmapData?.y) return [];
        const labels = Array.isArray(heatmapData.gene_symbols) ? heatmapData.gene_symbols : [];
        return heatmapData.y.map((gene: unknown, rowIndex: number) => {
            const label = labels[rowIndex];
            return label ? String(label) : String(gene);
        });
    }, [heatmapData]);

    const displayHeatmapRows = useMemo<HeatmapDisplayRow[]>(() => {
        if (!heatmapData?.y || !Array.isArray(heatmapData.z)) return [];

        const visibleRowSet = visibleHeatmapRowIndexes ? new Set(visibleHeatmapRowIndexes) : null;
        return heatmapData.y
            .map((gene: unknown, fullRowIndex: number) => ({
                fullRowIndex,
                geneId: String(gene),
                label: heatmapGeneLabels[fullRowIndex] || String(gene),
                defaultLabel: heatmapDefaultGeneLabels[fullRowIndex] || String(gene),
                zRow: heatmapData.z[fullRowIndex] || [],
            }))
            .filter((row: HeatmapDisplayRow) => !visibleRowSet || visibleRowSet.has(row.fullRowIndex));
    }, [heatmapData, heatmapDefaultGeneLabels, heatmapGeneLabels, visibleHeatmapRowIndexes]);

    const selectedHeatmapGenes = useMemo(() => {
        return selectedHeatmapRowIndexes
            .map((rowIndex) => heatmapGeneOrder[rowIndex])
            .filter((gene): gene is string => Boolean(gene));
    }, [selectedHeatmapRowIndexes, heatmapGeneOrder]);

    const selectedHeatmapGenesInDisplayOrder = useMemo(() => {
        return [...selectedHeatmapRowIndexes]
            .sort((a, b) => b - a)
            .map((rowIndex) => heatmapGeneOrder[rowIndex])
            .filter((gene): gene is string => Boolean(gene));
    }, [selectedHeatmapRowIndexes, heatmapGeneOrder]);

    useEffect(() => {
        heatmapGeneOrderRef.current = heatmapGeneOrder;
    }, [heatmapGeneOrder]);

    useEffect(() => {
        displayHeatmapRowsRef.current = displayHeatmapRows;
    }, [displayHeatmapRows]);

    const heatmapViewportRevision = useMemo(() => JSON.stringify({
        workbenchId,
        samples: heatmapData?.x || [],
        genes: displayHeatmapRows.map((row) => row.geneId),
        clusteringMethod,
        normalizationMethod,
        referenceSample: normalizationMethod === 'log2fc_reference' ? referenceSample : '',
    }), [
        workbenchId,
        heatmapData,
        displayHeatmapRows,
        clusteringMethod,
        normalizationMethod,
        referenceSample,
    ]);

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

            // 캐시에 저장
            heatmapCache.set(cacheKey, response);

            setHeatmapData(response);
        } catch (error) {
            console.error('Failed to load heatmap data:', error);
            alert('Failed to generate heatmap. Please check the console for details.');
            setHeatmapData(null);
        } finally {
            setIsLoading(false);
        }
    };

    const plotConfig = useMemo(() => {
        if (!heatmapData || displayHeatmapRows.length === 0) return null;

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
            const totalGeneCount = heatmapData?.y?.length || selectedGenes.length;
            const visibleGeneCount = displayHeatmapRows.length;
            const geneCount = visibleHeatmapRowIndexes
                ? ` (${visibleGeneCount}/${totalGeneCount} genes, ${normText})`
                : ` (${totalGeneCount} genes, ${normText})`;

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
        const exportHeight = clamp(
            displayHeatmapRows.length * 15 + topMargin + 120,
            800,
            2400
        );

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

        const selectedHeatmapRowSet = new Set(selectedHeatmapRowIndexes);
        const yAxisTickText = displayHeatmapRows.map((row) =>
            selectedHeatmapRowSet.has(row.fullRowIndex) ? `● ${row.label}` : row.label
        );
        const yAxisTickfont = {
            size: yAxisFontSize,
            color: displayHeatmapRows.map((row) =>
                selectedHeatmapRowSet.has(row.fullRowIndex) ? '#0f172a' : '#000000'
            )
        };
        const selectedRowOverlay = displayHeatmapRows.map((row) =>
            selectedHeatmapRowSet.has(row.fullRowIndex)
                ? heatmapData.x.map(() => 1)
                : heatmapData.x.map(() => null)
        );
        const yAxisRowValues = displayHeatmapRows.map((_row, displayRowIndex) => displayRowIndex);
        const hoverGeneData = displayHeatmapRows.map((row) => {
            const displayText = row.label === row.geneId ? row.geneId : `${row.label} (${row.geneId})`;
            return heatmapData.x.map(() => [displayText, row.fullRowIndex, row.geneId]);
        });

        return {
            data: [{
                type: 'heatmap',
                z: displayHeatmapRows.map((row) => row.zRow),
                x: heatmapData.x,
                y: yAxisRowValues,
                customdata: hoverGeneData,
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
                hovertemplate: `Gene: %{customdata[0]}<br>Sample: %{x}<br>${hoverValue}: %{z:.2f}<extra>Click row to select gene</extra>`,
                xgap: 0.5,
                ygap: 0.5
            }, {
                type: 'heatmap',
                z: selectedRowOverlay,
                x: heatmapData.x,
                y: yAxisRowValues,
                colorscale: [[0, 'rgba(250, 204, 21, 0.34)'], [1, 'rgba(250, 204, 21, 0.34)']],
                showscale: false,
                hoverinfo: 'skip',
                xgap: 0.5,
                ygap: 0.5,
                zmin: 0,
                zmax: 1
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
                dragmode: 'pan',
                xaxis: {
                    title: 'Samples',
                    side: 'bottom',
                    tickangle: -45,
                    tickfont: xAxisTickfont,
                    fixedrange: true
                },
                yaxis: {
                    title: `Genes (${displayHeatmapRows.length})`,
                    tickmode: 'array',
                    tickvals: yAxisRowValues,
                    ticktext: yAxisTickText,
                    tickfont: yAxisTickfont,
                    showticklabels: true,
                    fixedrange: false
                },
                paper_bgcolor: 'white',
                plot_bgcolor: 'white',
                autosize: true,
                uirevision: heatmapViewportRevision
            },
            config: {
                toImageButtonOptions: {
                    format: 'png',
                    filename: `heatmap_${new Date().toISOString().split('T')[0]}`,
                    height: exportHeight,
                    width: 900,
                    scale: 10
                },
                displaylogo: false,
                responsive: true
            }
        };
    }, [heatmapData, displayHeatmapRows, zscoreClip, yAxisFontSize, normalizationMethod, selectedGenes.length, selectedFileNames, referenceSample, colors, selectedHeatmapRowIndexes, visibleHeatmapRowIndexes, heatmapViewportRevision]);

    useEffect(() => {
        const container = plotContainerRef.current;
        if (!container || !plotConfig) return;

        const handleWheelZoom = (event: WheelEvent) => {
            const wheelDelta = event.deltaY !== 0 ? event.deltaY : event.deltaX;
            if (wheelDelta === 0) return;

            const plotElement = container.querySelector('.js-plotly-plot') as any;
            const plotArea = container.querySelector('.nsewdrag') as SVGRectElement | null;
            const yRange = plotElement?._fullLayout?.yaxis?.range;

            if (!plotElement || !plotArea || !yRange) return;

            const plotRect = plotArea.getBoundingClientRect();
            if (
                plotRect.width <= 0 ||
                plotRect.height <= 0 ||
                event.clientX < plotRect.left ||
                event.clientX > plotRect.right ||
                event.clientY < plotRect.top ||
                event.clientY > plotRect.bottom
            ) {
                return;
            }

            event.preventDefault();
            event.stopPropagation();

            const yFraction = 1 - (event.clientY - plotRect.top) / plotRect.height;
            const normalizedDelta = clamp(wheelDelta, -100, 100);
            const zoomFactor = Math.exp(normalizedDelta * 0.0025);

            const nextYRange = zoomAxisRange(
                yRange,
                yFraction,
                zoomFactor,
                displayHeatmapRowsRef.current.length
            );
            if (!nextYRange) return;

            void Plotly.relayout(plotElement, {
                'yaxis.range': nextYRange,
            });
        };

        container.addEventListener('wheel', handleWheelZoom, { passive: false });
        return () => {
            container.removeEventListener('wheel', handleWheelZoom);
        };
    }, [plotConfig, heatmapData]);

    const copyTextToClipboard = async (text: string) => {
        if (navigator.clipboard?.writeText) {
            await navigator.clipboard.writeText(text);
            return;
        }

        const textarea = document.createElement('textarea');
        textarea.value = text;
        textarea.setAttribute('readonly', 'true');
        textarea.style.position = 'absolute';
        textarea.style.left = '-9999px';
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);
    };

    const handleCopySelectedHeatmapGenes = async () => {
        if (selectedHeatmapGenes.length === 0) return;

        const genesForCopy = selectedHeatmapGenesInDisplayOrder;

        try {
            await copyTextToClipboard(genesForCopy.join('\n'));
            emitHeatmapSelectionLog('info', 'copied-genes', {
                count: genesForCopy.length,
                genes: genesForCopy,
                selectionOrderGenes: selectedHeatmapGenes,
            });
            setCopyStatus('copied');
            window.setTimeout(() => setCopyStatus('idle'), 1600);
        } catch (error) {
            console.error('Failed to copy heatmap genes:', error);
            emitHeatmapSelectionLog('error', 'copy-failed', {
                error: error instanceof Error ? error.message : String(error),
            });
            setCopyStatus('failed');
            window.setTimeout(() => setCopyStatus('idle'), 2200);
        }
    };

    const getPointRowIndex = (point: any, currentGeneOrder: string[]): number | null => {
        if (Array.isArray(point?.customdata)) {
            const fullRowIndex = Number(point.customdata[1]);
            if (Number.isInteger(fullRowIndex) && currentGeneOrder[fullRowIndex]) {
                return fullRowIndex;
            }
        }

        const currentDisplayRows = displayHeatmapRowsRef.current;
        const pointIndex = Array.isArray(point?.pointIndex) ? point.pointIndex : point?.pointNumber;
        if (Array.isArray(pointIndex)) {
            const displayRowIndex = Number(pointIndex[0]);
            const displayRow = currentDisplayRows[displayRowIndex];
            if (Number.isInteger(displayRowIndex) && displayRow && currentGeneOrder[displayRow.fullRowIndex]) {
                return displayRow.fullRowIndex;
            }
        }

        if (typeof point?.y === 'number') {
            const displayRow = currentDisplayRows[point.y];
            if (displayRow && currentGeneOrder[displayRow.fullRowIndex]) {
                return displayRow.fullRowIndex;
            }

            if (currentGeneOrder[point.y]) {
                return point.y;
            }
        }

        if (typeof point?.y === 'string') {
            const rowIndex = currentGeneOrder.indexOf(point.y);
            return rowIndex >= 0 ? rowIndex : null;
        }

        return null;
    };

    const resolveClickedGene = (point: any): HeatmapClickedGene | null => {
        if (!point) {
            emitHeatmapSelectionLog('warn', 'resolve-no-point');
            return null;
        }

        const currentGeneOrder = heatmapGeneOrderRef.current;
        const rowIndex = getPointRowIndex(point, currentGeneOrder);

        if (rowIndex !== null) {
            const gene = currentGeneOrder[rowIndex];
            emitHeatmapSelectionLog('info', 'resolved-gene-from-row-index', {
                rowIndex,
                gene,
                point: summarizePlotPoint(point),
            });
            return { gene, rowIndex };
        }

        emitHeatmapSelectionLog('warn', 'resolve-failed', {
            point: summarizePlotPoint(point),
            heatmapGeneCount: currentGeneOrder.length,
            firstGenes: currentGeneOrder.slice(0, 5),
        });
        return null;
    };

    const getModifierState = (nativeEvent?: MouseEvent): HeatmapModifierKeys => {
        return {
            shiftKey: Boolean(nativeEvent?.shiftKey || modifierKeysRef.current.shiftKey),
            ctrlKey: Boolean(nativeEvent?.ctrlKey || modifierKeysRef.current.ctrlKey),
            metaKey: Boolean(nativeEvent?.metaKey || modifierKeysRef.current.metaKey),
            altKey: Boolean(nativeEvent?.altKey || modifierKeysRef.current.altKey),
        };
    };

    const updateSelectedHeatmapGenes = (clicked: HeatmapClickedGene, modifiers: HeatmapModifierKeys) => {
        const clickedGene = clicked.gene;
        const clickedRowIndex = clicked.rowIndex;
        const rangeAnchorGene = lastClickedHeatmapGeneRef.current;
        const rangeAnchorRowIndex = lastClickedHeatmapRowIndexRef.current;
        const currentGeneOrder = heatmapGeneOrderRef.current;
        const isRangeSelection = Boolean(modifiers.shiftKey && rangeAnchorRowIndex !== null);
        const isToggleSelection = Boolean(modifiers.ctrlKey || modifiers.metaKey);

        setSelectedHeatmapRowIndexes((prev) => {
            let nextSelection: number[];

            if (isRangeSelection && rangeAnchorRowIndex !== null) {
                const start = rangeAnchorRowIndex;
                const end = clickedRowIndex;

                if (start >= 0 && end >= 0) {
                    const currentDisplayRows = displayHeatmapRowsRef.current;
                    const displayStart = currentDisplayRows.findIndex((row) => row.fullRowIndex === start);
                    const displayEnd = currentDisplayRows.findIndex((row) => row.fullRowIndex === end);
                    const useDisplayRange = displayStart >= 0 && displayEnd >= 0;
                    const [from, to] = useDisplayRange
                        ? (displayStart < displayEnd ? [displayStart, displayEnd] : [displayEnd, displayStart])
                        : (start < end ? [start, end] : [end, start]);
                    const rangeRowIndexes = useDisplayRange
                        ? currentDisplayRows.slice(from, to + 1).map((row) => row.fullRowIndex)
                        : Array.from({ length: to - from + 1 }, (_, index) => from + index);
                    const rangeGenes = rangeRowIndexes.map((rowIndex) => currentGeneOrder[rowIndex]);

                    nextSelection = Array.from(new Set([...prev, ...rangeRowIndexes]));

                    emitHeatmapSelectionLog('info', 'range-selected', {
                        clickedGene,
                        clickedRowIndex,
                        rangeAnchorGene,
                        rangeAnchorRowIndex,
                        selectionMode: 'append-range',
                        rangeBasis: useDisplayRange ? 'visible-rows' : 'full-rows',
                        from,
                        to,
                        rangeCount: rangeGenes.length,
                        previousCount: prev.length,
                        nextCount: nextSelection.length,
                        modifiers: {
                            shiftKey: modifiers.shiftKey,
                            ctrlKey: modifiers.ctrlKey,
                            metaKey: modifiers.metaKey,
                        },
                        selectedRowIndexes: nextSelection,
                        selectedGenes: nextSelection.map((rowIndex) => currentGeneOrder[rowIndex]),
                    });
                    return nextSelection;
                }

                emitHeatmapSelectionLog('warn', 'range-indices-not-found', {
                    clickedGene,
                    clickedRowIndex,
                    rangeAnchorGene,
                    rangeAnchorRowIndex,
                    start,
                    end,
                    heatmapGeneCount: currentGeneOrder.length,
                });
            }

            if (isToggleSelection) {
                nextSelection = prev.includes(clickedRowIndex)
                    ? prev.filter((rowIndex) => rowIndex !== clickedRowIndex)
                    : [...prev, clickedRowIndex];

                emitHeatmapSelectionLog('info', 'toggled-gene', {
                    clickedGene,
                    clickedRowIndex,
                    wasSelected: prev.includes(clickedRowIndex),
                    previousCount: prev.length,
                    nextCount: nextSelection.length,
                    selectedRowIndexes: nextSelection,
                    selectedGenes: nextSelection.map((rowIndex) => currentGeneOrder[rowIndex]),
                });
                return nextSelection;
            }

            if (prev.includes(clickedRowIndex)) {
                nextSelection = prev.filter((rowIndex) => rowIndex !== clickedRowIndex);
                emitHeatmapSelectionLog('info', 'deselected-gene', {
                    clickedGene,
                    clickedRowIndex,
                    previousCount: prev.length,
                    nextCount: nextSelection.length,
                    selectedRowIndexes: nextSelection,
                    selectedGenes: nextSelection.map((rowIndex) => currentGeneOrder[rowIndex]),
                });
                return nextSelection;
            }

            nextSelection = [clickedRowIndex];
            emitHeatmapSelectionLog('info', 'selected-single-gene', {
                clickedGene,
                clickedRowIndex,
                rangeAnchorGene,
                rangeAnchorRowIndex,
                modifiers,
                previousCount: prev.length,
                nextCount: nextSelection.length,
                selectedRowIndexes: nextSelection,
                selectedGenes: nextSelection.map((rowIndex) => currentGeneOrder[rowIndex]),
            });
            return nextSelection;
        });

        lastClickedHeatmapGeneRef.current = clickedGene;
        lastClickedHeatmapRowIndexRef.current = clickedRowIndex;
        setLastClickedHeatmapGene(clickedGene);
        setLastClickedHeatmapRowIndex(clickedRowIndex);
        setCopyStatus('idle');
    };

    // 히트맵 클릭 시 gene row 선택. log2fc_reference에서는 Alt+Click으로 기준 샘플 변경.
    const handlePlotClick = (event: any) => {
        if (!event.points || event.points.length === 0) {
            emitHeatmapSelectionLog('warn', 'plot-click-without-points', {
                hasEvent: Boolean(event),
                eventKeys: event ? Object.keys(event) : [],
            });
            return;
        }

        const nativeEvent = event.event as MouseEvent | undefined;
        const point = event.points[0];
        const clickedSample = point.x;
        const modifiers = getModifierState(nativeEvent);

        emitHeatmapSelectionLog('info', 'plot-click', {
            pointsLength: event.points.length,
            point: summarizePlotPoint(point),
            modifiers,
            nativeModifiers: {
                shiftKey: Boolean(nativeEvent?.shiftKey),
                ctrlKey: Boolean(nativeEvent?.ctrlKey),
                metaKey: Boolean(nativeEvent?.metaKey),
                altKey: Boolean(nativeEvent?.altKey),
            },
            trackedModifiers: modifierKeysRef.current,
            normalizationMethod,
            currentReferenceSample: referenceSample,
            lastClickedHeatmapGene,
            lastClickedHeatmapGeneRef: lastClickedHeatmapGeneRef.current,
            lastClickedHeatmapRowIndex,
            lastClickedHeatmapRowIndexRef: lastClickedHeatmapRowIndexRef.current,
            heatmapGeneCount: heatmapGeneOrderRef.current.length,
        });

        if (normalizationMethod === 'log2fc_reference' && modifiers.altKey && clickedSample && typeof clickedSample === 'string') {
            emitHeatmapSelectionLog('info', 'reference-sample-changed-by-alt-click', {
                previousReferenceSample: referenceSample,
                nextReferenceSample: clickedSample,
            });
            setReferenceSample(clickedSample);
        }

        const clickedGene = resolveClickedGene(point);
        if (clickedGene) {
            updateSelectedHeatmapGenes(clickedGene, modifiers);
        } else {
            emitHeatmapSelectionLog('warn', 'click-ignored-no-gene', {
                point: summarizePlotPoint(point),
            });
        }
    };

    const resetHeatmapSelection = () => {
        setSelectedHeatmapRowIndexes([]);
        setLastClickedHeatmapGene(null);
        setLastClickedHeatmapRowIndex(null);
        lastClickedHeatmapGeneRef.current = null;
        lastClickedHeatmapRowIndexRef.current = null;
        setCopyStatus('idle');
    };

    const handleShowSelectedOnly = () => {
        if (selectedHeatmapRowIndexes.length === 0) return;

        const nextVisibleRows = [...selectedHeatmapRowIndexes]
            .sort((a, b) => a - b)
            .filter((rowIndex, index, rows) => rows.indexOf(rowIndex) === index);

        setVisibleHeatmapRowIndexes(nextVisibleRows);
        resetHeatmapSelection();

        emitHeatmapSelectionLog('info', 'selected-only-applied', {
            visibleRowIndexes: nextVisibleRows,
            visibleGenes: nextVisibleRows.map((rowIndex) => heatmapGeneOrderRef.current[rowIndex]),
        });
    };

    const openLabelEditor = (row: HeatmapDisplayRow) => {
        setLabelEditor({
            geneId: row.geneId,
            fullRowIndex: row.fullRowIndex,
            currentLabel: row.label,
            defaultLabel: row.defaultLabel,
        });
        setLabelEditorValue(customHeatmapLabels[row.geneId] || row.label);
        emitHeatmapSelectionLog('info', 'label-edit-open', {
            geneId: row.geneId,
            fullRowIndex: row.fullRowIndex,
            currentLabel: row.label,
            defaultLabel: row.defaultLabel,
        });
    };

    const summarizeElement = (element: Element | null) => {
        if (!element) return null;
        const className = typeof element.className === 'string'
            ? element.className
            : String((element as HTMLElement).getAttribute('class') || '');
        return {
            tagName: element.tagName,
            className,
            id: (element as HTMLElement).id || '',
            text: (element.textContent || '').trim().slice(0, 80),
        };
    };

    const handlePlotDoubleClick = (event: React.MouseEvent<HTMLDivElement>) => {
        const target = event.target as Element | null;
        const plotContainer = plotContainerRef.current;

        if (!plotContainer) return;

        const yTickGroups = Array.from(
            plotContainer.querySelectorAll('.yaxislayer-above .ytick, .yaxislayer-below .ytick')
        );
        const tickEntries = yTickGroups
            .map((candidate) => {
                const textElement = candidate.querySelector('text');
                const rect = candidate.getBoundingClientRect();
                const textRect = textElement?.getBoundingClientRect() || rect;
                const text = (textElement?.textContent || candidate.textContent || '').trim();
                return {
                    candidate,
                    text,
                    centerY: textRect.top + textRect.height / 2,
                    textRect,
                    isVisible: textRect.width > 0 && textRect.height > 0,
                };
            })
            .filter((entry) => entry.isVisible)
            .sort((a, b) => a.centerY - b.centerY);
        const targetTickGroup = target?.closest('.ytick') as Element | null;
        let tickEntry = targetTickGroup && plotContainer.contains(targetTickGroup)
            ? tickEntries.find((entry) => entry.candidate === targetTickGroup) || null
            : null;

        if (!tickEntry) {
            const nearbyTick = tickEntries
                .map((entry) => {
                    const yDistance = Math.abs(event.clientY - entry.centerY);
                    const xNearLabel = event.clientX >= entry.textRect.left - 24 && event.clientX <= entry.textRect.right + 24;
                    return { entry, yDistance, xNearLabel };
                })
                .filter((item) => item.xNearLabel && item.yDistance <= 14)
                .sort((a, b) => a.yDistance - b.yDistance)[0];

            tickEntry = nearbyTick?.entry || null;

            if (!tickEntry) {
                emitHeatmapSelectionLog('warn', 'label-edit-dblclick-no-ytick', {
                    target: summarizeElement(target),
                    parent: summarizeElement(target?.parentElement || null),
                    clientX: event.clientX,
                    clientY: event.clientY,
                    tickCount: yTickGroups.length,
                    visibleTickCount: tickEntries.length,
                    tickPreview: tickEntries.slice(0, 5).map((entry, index) => ({
                        index,
                        text: entry.text,
                        centerY: Math.round(entry.centerY),
                    })),
                });
                return;
            }
        }

        event.preventDefault();
        event.stopPropagation();

        const screenIndex = tickEntries.findIndex((entry) => entry.candidate === tickEntry.candidate);
        const screenRows = displayHeatmapRowsRef.current;
        const plotElement = plotContainer.querySelector('.js-plotly-plot') as any;
        const yAxisRange = plotElement?._fullLayout?.yaxis?.range;
        const topMapsToFirstRow = Array.isArray(yAxisRange)
            ? Number(yAxisRange[0]) > Number(yAxisRange[1])
            : false;
        const geneOrderTopToBottom = screenRows.map((_row, visualIndex) => {
            const rowIndex = topMapsToFirstRow
                ? visualIndex
                : screenRows.length - 1 - visualIndex;
            const row = screenRows[rowIndex];
            return {
                visualIndex,
                displayRowIndex: rowIndex,
                fullRowIndex: row?.fullRowIndex,
                geneId: row?.geneId,
                label: row?.label,
            };
        });
        const displayRowIndex = topMapsToFirstRow
            ? screenIndex
            : screenRows.length - 1 - screenIndex;
        const targetRow = screenRows[displayRowIndex];

        if (!targetRow) {
            emitHeatmapSelectionLog('warn', 'label-edit-target-not-found', {
                screenIndex,
                displayRowIndex,
                tickCount: yTickGroups.length,
                visibleTickCount: tickEntries.length,
                displayRowCount: screenRows.length,
                tickText: tickEntry.text,
                yAxisRange,
                geneOrderTopToBottom,
            });
            return;
        }

        emitHeatmapSelectionLog('info', 'label-edit-target-resolved', {
            screenIndex,
            displayRowIndex,
            tickText: tickEntry.text,
            geneId: targetRow.geneId,
            label: targetRow.label,
            fullRowIndex: targetRow.fullRowIndex,
            tickCount: yTickGroups.length,
            visibleTickCount: tickEntries.length,
            yAxisRange,
            topMapsToFirstRow,
            geneOrderTopToBottom,
        });

        openLabelEditor(targetRow);
    };

    const closeLabelEditor = () => {
        if (labelEditor) {
            emitHeatmapSelectionLog('info', 'label-edit-cancel', {
                geneId: labelEditor.geneId,
                fullRowIndex: labelEditor.fullRowIndex,
            });
        }
        setLabelEditor(null);
        setLabelEditorValue('');
    };

    const saveLabelEditor = () => {
        if (!labelEditor) return;

        const nextLabel = labelEditorValue.trim();
        setCustomHeatmapLabels((prev) => {
            const next = { ...prev };
            if (nextLabel) {
                next[labelEditor.geneId] = nextLabel;
            } else {
                delete next[labelEditor.geneId];
            }
            return next;
        });

        emitHeatmapSelectionLog('info', nextLabel ? 'label-edit-save' : 'label-edit-clear', {
            geneId: labelEditor.geneId,
            fullRowIndex: labelEditor.fullRowIndex,
            previousLabel: labelEditor.currentLabel,
            nextLabel: nextLabel || labelEditor.defaultLabel,
            clearedToDefault: !nextLabel,
        });

        setLabelEditor(null);
        setLabelEditorValue('');
    };

    // 줌 시 Y축 폰트 크기 동적 조정
    const handleRelayout = (event: any) => {
        if (!heatmapData) return;

        if (event['yaxis.range[0]'] !== undefined && event['yaxis.range[1]'] !== undefined) {
            const yStart = Number(event['yaxis.range[0]']);
            const yEnd = Number(event['yaxis.range[1]']);
            const visibleGenes = Math.abs(yEnd - yStart);

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
            const totalGenes = displayHeatmapRowsRef.current.length || heatmapData.y.length;
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
            <div className="flex min-h-0 min-w-0 flex-1 flex-col bg-slate-50">
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
                <div className={`min-h-0 flex-1 p-6 ${!isLoading && selectedGenes.length > 0 && plotConfig ? 'overflow-hidden' : 'overflow-auto'}`}>
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
                        <div className="flex h-full min-h-0 flex-col gap-3">
                            <div className="shrink-0 rounded-lg border border-slate-200 bg-white px-4 py-3">
                                <div className="flex items-center justify-between gap-3">
                                    <div className="min-w-0">
                                        <div className="text-sm font-medium text-slate-700">
                                            {selectedHeatmapGenes.length} heatmap gene{selectedHeatmapGenes.length === 1 ? '' : 's'} selected
                                        </div>
                                        {selectedHeatmapGenes.length > 0 && (
                                            <div className="mt-1 truncate text-xs text-slate-500">
                                                {selectedHeatmapGenesInDisplayOrder.slice(0, 12).join(', ')}
                                                {selectedHeatmapGenesInDisplayOrder.length > 12 ? `, +${selectedHeatmapGenesInDisplayOrder.length - 12} more` : ''}
                                            </div>
                                        )}
                                    </div>
                                    <div className="flex shrink-0 items-center gap-2">
                                        <button
                                            type="button"
                                            onClick={handleShowSelectedOnly}
                                            disabled={selectedHeatmapGenes.length === 0}
                                            className="rounded border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                                        >
                                            Show selected only
                                        </button>
                                        <button
                                            type="button"
                                            onClick={() => {
                                                setVisibleHeatmapRowIndexes(null);
                                                resetHeatmapSelection();
                                                emitHeatmapSelectionLog('info', 'view-reset-to-all');
                                            }}
                                            disabled={!visibleHeatmapRowIndexes}
                                            className="rounded border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                                        >
                                            Reset view
                                        </button>
                                        <button
                                            type="button"
                                            onClick={() => {
                                                resetHeatmapSelection();
                                                emitHeatmapSelectionLog('info', 'selection-cleared', {
                                                    visibleRowIndexes: visibleHeatmapRowIndexes,
                                                });
                                            }}
                                            disabled={selectedHeatmapGenes.length === 0}
                                            className="rounded border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                                        >
                                            Clear
                                        </button>
                                        <button
                                            type="button"
                                            onClick={() => {
                                                void handleCopySelectedHeatmapGenes();
                                            }}
                                            disabled={selectedHeatmapGenes.length === 0}
                                            className="rounded bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-300"
                                        >
                                            {copyStatus === 'copied' ? 'Copied' : copyStatus === 'failed' ? 'Copy failed' : 'Copy selected genes'}
                                        </button>
                                    </div>
                                </div>
                            </div>
                            <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg border border-slate-200 bg-white p-4">
                                <div ref={plotContainerRef} onDoubleClickCapture={handlePlotDoubleClick} className="min-h-0 flex-1">
                                    <Plot
                                        {...plotConfig}
                                        onClick={handlePlotClick}
                                        onRelayout={handleRelayout}
                                        useResizeHandler
                                        style={{ width: '100%', height: '100%' }}
                                    />
                                </div>
                                <div className="mt-4 shrink-0 text-xs text-slate-500 text-center">
                                    Tip: Click to select/unselect, Ctrl/Cmd-click to add a new block anchor, Shift-click to append a range | Wheel to zoom genes, drag vertically to pan, double-click to reset | Use the camera toolbar button to download a high-resolution PNG
                                    {normalizationMethod === 'log2fc_reference' && <span> | Alt-click a cell to change reference sample</span>}
                                </div>
                            </div>
                            {labelEditor && (
                                <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/30 px-4">
                                    <div className="w-full max-w-md rounded-lg border border-slate-200 bg-white p-5 shadow-xl">
                                        <div className="mb-4">
                                            <h3 className="text-base font-semibold text-slate-900">Edit gene label</h3>
                                            <p className="mt-1 text-xs text-slate-500">
                                                {labelEditor.geneId}
                                            </p>
                                        </div>
                                        <input
                                            autoFocus
                                            value={labelEditorValue}
                                            onChange={(event) => setLabelEditorValue(event.target.value)}
                                            onKeyDown={(event) => {
                                                if (event.key === 'Enter') {
                                                    event.preventDefault();
                                                    saveLabelEditor();
                                                }
                                                if (event.key === 'Escape') {
                                                    event.preventDefault();
                                                    closeLabelEditor();
                                                }
                                            }}
                                            className="w-full rounded border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
                                            placeholder={labelEditor.defaultLabel}
                                        />
                                        <div className="mt-4 flex items-center justify-end gap-2">
                                            <button
                                                type="button"
                                                onClick={closeLabelEditor}
                                                className="rounded border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50"
                                            >
                                                Cancel
                                            </button>
                                            <button
                                                type="button"
                                                onClick={() => {
                                                    setLabelEditorValue('');
                                                }}
                                                className="rounded border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50"
                                            >
                                                Use default
                                            </button>
                                            <button
                                                type="button"
                                                onClick={saveLabelEditor}
                                                className="rounded bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-800"
                                            >
                                                Save
                                            </button>
                                        </div>
                                    </div>
                                </div>
                            )}
                        </div>
                    ) : null}
                </div>
            </div>
        </div>
    );
};

export default WorkbenchDetailHeatmap;
