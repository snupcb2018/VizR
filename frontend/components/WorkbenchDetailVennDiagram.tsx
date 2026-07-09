import React, { useState, useRef, useCallback, useMemo, useEffect } from 'react';
import { createPortal } from 'react-dom';
import Highcharts from 'highcharts';
import HighchartsReact from 'highcharts-react-official';
import HighchartsVenn from 'highcharts/modules/venn';
import HighchartsExporting from 'highcharts/modules/exporting';
import HighchartsExportData from 'highcharts/modules/export-data';
import MiniHeatmap from './MiniHeatmap';
import GOAnalysisModal from './GOAnalysisModal';
import GOProviderSubmenu from './GOProviderSubmenu';
import CopyGeneListMenuItem from './CopyGeneListMenuItem';
import HeatmapAnalysisModal from './HeatmapAnalysisModal';
import KEGGPathwayModal from './KEGGPathwayModal';
import { apiService } from '../services/api';
import SelectableGeneTableShell from './SelectableGeneTableShell';
import { useGeneAnalysisActions } from '../hooks/useGeneAnalysisActions';
import { useOverlayStickyTable } from '../hooks/useOverlayStickyTable';

if (typeof HighchartsVenn === 'function') HighchartsVenn(Highcharts);
if (typeof HighchartsExporting === 'function') HighchartsExporting(Highcharts);
if (typeof HighchartsExportData === 'function') HighchartsExportData(Highcharts);

interface WorkbenchDetailVennDiagramProps {
  workbenchId: number;
  hasTPMMatrix?: boolean;
  geneSets: GeneSet[];
  geneInputs: { [key: string]: string };
  onGeneSetsChange: (sets: GeneSet[]) => void;
  onGeneInputsChange: (inputs: { [key: string]: string }) => void;
  onReset: () => void;
}

interface GeneSet {
  id: string;
  name: string;
  genes: string[];
}

interface VennIntersection {
  key: string;
  label: string;
  genes: string[];
}

interface RegionDefinition extends VennIntersection {
  mask: number;
  sets: string[];
}

interface NormalizedGeneSet extends GeneSet {
  letter: string;
  displayName: string;
  normalizedGenes: string[];
}

interface GeneExpressionData {
  gene_id: string;
  gene_symbol: string;
  gene_description: string;
  [sample: string]: number | string;
}

interface CountResultsResponse {
  matrix: GeneExpressionData[];
  samples: string[];
  groups?: string[];
  total_genes?: number;
  showing_genes?: number;
  current_page?: number;
  total_pages?: number;
  page_size?: number;
  matched_gene_ids?: string[];
  status?: string;
}

interface VennOverlayItem {
  key: string;
  path: string;
  transform: string;
  overlapPaths: Array<{ d: string; transform: string }>;
}

interface VennOverlayState {
  width: number;
  height: number;
  items: VennOverlayItem[];
}

type MatrixType = 'TMM' | 'TPM' | 'Raw';
type VisualizationMode = 'venn' | 'upset';
type UpsetSort = 'count_desc' | 'count_asc' | 'key_asc';

const SET_LETTERS = ['A', 'B', 'C', 'D'] as const;
const UPSET_TOP_N_OPTIONS = [10, 20, 30, 50, 100] as const;

const normalizeGenes = (genes: string[]): string[] => Array.from(new Set(genes.map(g => g.trim()).filter(Boolean)));
const fallbackSetName = (index: number) => `Set ${SET_LETTERS[index] || String(index + 1)}`;
const displayName = (name: string) => (name || '').trim();
const sortKey = (sets: string[]) => [...sets].sort().join('');

const keyToMask = (key: string, setCount: number): number => {
  const indexMap = new Map<string, number>();
  for (let i = 0; i < setCount; i += 1) indexMap.set(SET_LETTERS[i], i);
  return key.split('').reduce((mask, letter) => {
    const idx = indexMap.get(letter);
    return idx === undefined ? mask : (mask | (1 << idx));
  }, 0);
};

const WorkbenchDetailVennDiagram: React.FC<WorkbenchDetailVennDiagramProps> = ({
  workbenchId,
  hasTPMMatrix = true,
  geneSets,
  geneInputs,
  onGeneSetsChange,
  onGeneInputsChange,
  onReset
}) => {
  const chartComponentRef = useRef<HighchartsReact.RefObject>(null);
  const actionMenuRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLTextAreaElement>(null);
  const previousSetCountRef = useRef<number>(geneSets.length);

  const [selectedRegionKeys, setSelectedRegionKeys] = useState<Set<string>>(new Set());
  const [selectedIntersection, setSelectedIntersection] = useState<VennIntersection | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(500);
  const [isSetsPanelCollapsed, setIsSetsPanelCollapsed] = useState(false);
  const [geneExpressionData, setGeneExpressionData] = useState<CountResultsResponse | null>(null);
  const [loadingExpression, setLoadingExpression] = useState(false);
  const [selectedMatrixType, setSelectedMatrixType] = useState<MatrixType>('TMM');
  const [selectedGenes, setSelectedGenes] = useState<Set<string>>(new Set());
  const [isActionMenuOpen, setActionMenuOpen] = useState(false);
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
    description: `Venn diagram selected genes from ${selectedMatrixType} count matrix`,
  });
  const [activeSearch, setActiveSearch] = useState('');
  const [selectAllState, setSelectAllState] = useState<0 | 1 | 2>(0);
  const [visualizationMode, setVisualizationMode] = useState<VisualizationMode>('venn');
  const [upsetSort, setUpsetSort] = useState<UpsetSort>('count_desc');
  const [upsetTopN, setUpsetTopN] = useState<number | 'all'>(30);
  const [upsetMinCount, setUpsetMinCount] = useState(1);
  const [upsetHideZero, setUpsetHideZero] = useState(true);
  const [vennOverlayState, setVennOverlayState] = useState<VennOverlayState | null>(null);
  const vennOverlayStateRef = useRef<VennOverlayState | null>(null);
  const exportScaleRef = useRef(2);
  const tableColumnWidths = {
    select: 48,
    rowNo: 56,
    geneId: 150,
    geneSymbol: 120,
    pattern: 240,
    sample: 96
  } as const;
  const tableStickyOffsets = {
    geneId: tableColumnWidths.select + tableColumnWidths.rowNo,
    geneSymbol: tableColumnWidths.select + tableColumnWidths.rowNo + tableColumnWidths.geneId,
    pattern: tableColumnWidths.select + tableColumnWidths.rowNo + tableColumnWidths.geneId + tableColumnWidths.geneSymbol
  } as const;
  const fixedHeaderWidth =
    tableColumnWidths.select +
    tableColumnWidths.geneId +
    tableColumnWidths.geneSymbol +
    tableColumnWidths.pattern;
  const logVennDebug = useCallback((tag: string, payload: Record<string, unknown>) => {
    if (typeof window === 'undefined') return;
    if ((window as any).__VIZR_VENN_DEBUG__ !== true) return;
    console.info(tag, payload);
  }, []);

  useEffect(() => {
    vennOverlayStateRef.current = vennOverlayState;
  }, [vennOverlayState]);

  useEffect(() => {
    if (!hasTPMMatrix && selectedMatrixType === 'TPM') {
      setSelectedMatrixType('TMM');
    }
  }, [hasTPMMatrix, selectedMatrixType]);

  const buildVennSvgWithOverlay = useCallback((chart: Highcharts.Chart): { svg: string; width: number; height: number } => {
    const liveSvg = chart.container.querySelector('svg');
    if (!liveSvg) {
      const fallbackSvg = chart.getSVG();
      return {
        svg: fallbackSvg,
        width: chart.chartWidth,
        height: chart.chartHeight
      };
    }

    const clone = liveSvg.cloneNode(true) as SVGSVGElement;
    clone.querySelectorAll('.highcharts-contextbutton, .highcharts-button, .highcharts-credits').forEach(node => node.remove());

    const overlayState = vennOverlayStateRef.current;
    if (overlayState?.items?.length) {
      const ns = 'http://www.w3.org/2000/svg';
      const overlayGroup = document.createElementNS(ns, 'g');
      overlayGroup.setAttribute('class', 'venn-overlay-export');

      overlayState.items.forEach((item) => {
        const path = document.createElementNS(ns, 'path');
        if (item.key.length === 1) {
          const onlyPathD = [
            item.path,
            ...item.overlapPaths
              .filter(overlap => overlap.transform === item.transform)
              .map(overlap => overlap.d)
          ].join(' ');
          path.setAttribute('d', onlyPathD);
          path.setAttribute('fill-rule', 'evenodd');
          path.setAttribute('clip-rule', 'evenodd');
        } else {
          path.setAttribute('d', item.path);
        }
        path.setAttribute('transform', item.transform);
        path.setAttribute('fill', 'rgba(59,130,246,0.15)');
        path.setAttribute('stroke', '#1d4ed8');
        path.setAttribute('stroke-width', '2');
        path.setAttribute('vector-effect', 'non-scaling-stroke');
        overlayGroup.appendChild(path);
      });

      clone.appendChild(overlayGroup);
    }

    const bbox = liveSvg.getBBox();
    const padding = 16;
    const exportWidth = Math.max(1, Math.ceil(bbox.width + padding * 2));
    const exportHeight = Math.max(1, Math.ceil(bbox.height + padding * 2));
    clone.setAttribute('viewBox', `${bbox.x - padding} ${bbox.y - padding} ${exportWidth} ${exportHeight}`);
    clone.setAttribute('width', String(exportWidth));
    clone.setAttribute('height', String(exportHeight));
    clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');

    return {
      svg: new XMLSerializer().serializeToString(clone),
      width: exportWidth,
      height: exportHeight
    };
  }, []);

  const triggerBlobDownload = useCallback((blob: Blob, filename: string) => {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }, []);

  const exportVennWithOverlay = useCallback(async (chart: Highcharts.Chart, format: 'png' | 'jpeg' | 'svg') => {
    const filenameBase = ((chart.options.exporting as any)?.filename || 'venn-diagram') as string;
    const mimeType = format === 'svg'
      ? 'image/svg+xml'
      : (format === 'jpeg' ? 'image/jpeg' : 'image/png');
    const extension = format === 'jpeg' ? 'jpg' : format;

    try {
      const { svg, width, height } = buildVennSvgWithOverlay(chart);
      if (format === 'svg') {
        const svgBlob = new Blob([svg], { type: 'image/svg+xml;charset=utf-8' });
        triggerBlobDownload(svgBlob, `${filenameBase}.${extension}`);
        return;
      }

      const svgBlob = new Blob([svg], { type: 'image/svg+xml;charset=utf-8' });
      const svgUrl = URL.createObjectURL(svgBlob);

      await new Promise<void>((resolve, reject) => {
        const img = new Image();
        img.onload = () => {
          const scale = exportScaleRef.current;
          const canvas = document.createElement('canvas');
          canvas.width = Math.max(1, Math.round(width * scale));
          canvas.height = Math.max(1, Math.round(height * scale));
          const ctx = canvas.getContext('2d');
          if (!ctx) {
            URL.revokeObjectURL(svgUrl);
            reject(new Error('Canvas context unavailable'));
            return;
          }

          if (format === 'jpeg') {
            ctx.fillStyle = '#ffffff';
            ctx.fillRect(0, 0, canvas.width, canvas.height);
          }
          ctx.scale(scale, scale);
          ctx.drawImage(img, 0, 0);
          URL.revokeObjectURL(svgUrl);

          canvas.toBlob((blob) => {
            if (!blob) {
              reject(new Error('Raster export failed'));
              return;
            }
            triggerBlobDownload(blob, `${filenameBase}.${extension}`);
            resolve();
          }, mimeType, 0.95);
        };
        img.onerror = () => {
          URL.revokeObjectURL(svgUrl);
          reject(new Error('Failed to load SVG for raster export'));
        };
        img.src = svgUrl;
      });
    } catch (error) {
      console.error('[VENN-EXPORT] Overlay export failed, fallback to default export:', error);
      chart.exportChart({ type: mimeType });
    }
  }, [buildVennSvgWithOverlay, triggerBlobDownload]);

  const normalizedGeneSets = useMemo<NormalizedGeneSet[]>(() => {
    return geneSets.slice(0, 4).map((set, index) => ({
      ...set,
      letter: SET_LETTERS[index],
      displayName: displayName(set.name),
      normalizedGenes: normalizeGenes(set.genes || [])
    }));
  }, [geneSets]);

  const normalizedSetMap = useMemo(() => new Map(normalizedGeneSets.map(s => [s.letter, s])), [normalizedGeneSets]);

  const intersections = useMemo<RegionDefinition[]>(() => {
    if (normalizedGeneSets.length < 2) return [];

    const geneMaskMap = new Map<string, number>();
    normalizedGeneSets.forEach((set, setIndex) => {
      const bit = 1 << setIndex;
      set.normalizedGenes.forEach(gene => geneMaskMap.set(gene, (geneMaskMap.get(gene) || 0) | bit));
    });

    const genesByMask = new Map<number, string[]>();
    for (const [gene, mask] of geneMaskMap.entries()) {
      const list = genesByMask.get(mask) || [];
      list.push(gene);
      genesByMask.set(mask, list);
    }

    const maxMask = (1 << normalizedGeneSets.length) - 1;
    const regions: RegionDefinition[] = [];
    for (let mask = 1; mask <= maxMask; mask += 1) {
      const indices: number[] = [];
      for (let i = 0; i < normalizedGeneSets.length; i += 1) {
        if ((mask & (1 << i)) !== 0) indices.push(i);
      }
      const sets = indices.map(idx => normalizedGeneSets[idx].letter);
      const regionLabel = indices.length === 1
        ? `Only ${normalizedGeneSets[indices[0]].displayName}`
        : indices.map(idx => normalizedGeneSets[idx].displayName).join(' & ');
      regions.push({
        key: sets.join(''),
        mask,
        sets,
        label: regionLabel,
        genes: [...(genesByMask.get(mask) || [])].sort()
      });
    }
    return regions.sort((a, b) => a.sets.length - b.sets.length || a.key.localeCompare(b.key));
  }, [normalizedGeneSets]);

  const intersectionMap = useMemo(() => new Map(intersections.map(r => [r.key, r])), [intersections]);
  const hasEnoughSets = normalizedGeneSets.length >= 2;
  const allSetsHaveGenes = normalizedGeneSets.length > 0 && normalizedGeneSets.every(s => s.normalizedGenes.length > 0);
  const canRenderComparison = hasEnoughSets && allSetsHaveGenes;
  const vennAvailable = normalizedGeneSets.length >= 2 && normalizedGeneSets.length <= 3;

  useEffect(() => {
    const currentSetCount = normalizedGeneSets.length;
    const previousSetCount = previousSetCountRef.current;
    if (currentSetCount >= 4) setVisualizationMode('upset');
    else if (previousSetCount >= 4 && currentSetCount <= 3) setVisualizationMode('venn');
    previousSetCountRef.current = currentSetCount;
  }, [normalizedGeneSets.length]);

  useEffect(() => {
    setSelectedRegionKeys(prev => {
      const next = new Set<string>();
      let changed = false;
      prev.forEach(key => {
        if (intersectionMap.has(key)) next.add(key);
        else changed = true;
      });
      if (!changed && next.size === prev.size) return prev;
      return next;
    });
  }, [intersectionMap]);

  useEffect(() => {
    if (selectedRegionKeys.size === 0) {
      setSelectedIntersection(null);
      return;
    }
    const selectedRegions = Array.from(selectedRegionKeys)
      .map(key => intersectionMap.get(key))
      .filter((region): region is RegionDefinition => Boolean(region));
    if (selectedRegions.length === 0) {
      setSelectedIntersection(null);
      return;
    }

    const dedup = new Set<string>();
    const mergedGenes: string[] = [];
    selectedRegions.forEach(region => {
      region.genes.forEach(gene => {
        if (!dedup.has(gene)) {
          dedup.add(gene);
          mergedGenes.push(gene);
        }
      });
    });

    setSelectedIntersection({
      key: selectedRegions.map(region => region.key).join('+'),
      label: selectedRegions.length === 1
        ? selectedRegions[0].label
        : selectedRegions.map(region => region.label).join(' + '),
      genes: mergedGenes
    });
  }, [selectedRegionKeys, intersectionMap]);

  const totalCountByMask = useMemo(() => {
    const totals = new Map<number, number>();
    const maxMask = (1 << normalizedGeneSets.length) - 1;
    for (let targetMask = 1; targetMask <= maxMask; targetMask += 1) {
      let sum = 0;
      intersections.forEach(region => {
        if ((region.mask & targetMask) === targetMask) sum += region.genes.length;
      });
      totals.set(targetMask, sum);
    }
    return totals;
  }, [intersections, normalizedGeneSets.length]);

  const applyRegionSelection = useCallback((regionKey: string, toggle: boolean) => {
    if (!intersectionMap.has(regionKey)) return;
    setSelectedRegionKeys(prev => {
      if (!toggle) return new Set([regionKey]);
      const next = new Set(prev);
      if (next.has(regionKey)) next.delete(regionKey);
      else next.add(regionKey);
      return next;
    });
    if (searchInputRef.current) searchInputRef.current.value = '';
    setActiveSearch('');
    setCurrentPage(1);
    setSelectedGenes(new Set());
    setSelectAllState(0);
  }, [intersectionMap]);

  const handleVennClick = useCallback((event: any) => {
    const point = event?.point;
    if (!point) {
      logVennDebug('[VENN-CLICK]', { hasPoint: false });
      return;
    }
    const directKey = point?.custom?.regionKey as string | undefined;
    const fallbackKey = Array.isArray(point.sets) ? sortKey(point.sets) : '';
    const regionKey = directKey || fallbackKey;
    const toggle = Boolean(
      event?.originalEvent?.ctrlKey || event?.originalEvent?.metaKey ||
      event?.browserEvent?.ctrlKey || event?.browserEvent?.metaKey ||
      event?.pointerEvent?.ctrlKey || event?.pointerEvent?.metaKey ||
      event?.ctrlKey || event?.metaKey
    );

    logVennDebug('[VENN-CLICK]', {
      hasPoint: true,
      directKey,
      fallbackKey,
      regionKey,
      toggle,
      ctrlSources: {
        originalEvent: { ctrlKey: event?.originalEvent?.ctrlKey, metaKey: event?.originalEvent?.metaKey },
        browserEvent: { ctrlKey: event?.browserEvent?.ctrlKey, metaKey: event?.browserEvent?.metaKey },
        pointerEvent: { ctrlKey: event?.pointerEvent?.ctrlKey, metaKey: event?.pointerEvent?.metaKey },
        eventSelf: { ctrlKey: event?.ctrlKey, metaKey: event?.metaKey }
      },
      intersectionExists: Boolean(regionKey && intersectionMap.has(regionKey)),
      sets: point?.sets || []
    });
    if (!regionKey || !intersectionMap.has(regionKey)) return;
    applyRegionSelection(regionKey, toggle);
  }, [applyRegionSelection, intersectionMap, logVennDebug]);

  const chartOptions = useMemo<Highcharts.Options>(() => {
    if (!canRenderComparison || !vennAvailable) {
      return {
        chart: { type: 'venn', height: 500 },
        title: { text: 'Add at least 2 sets with genes to view overlap' },
        accessibility: { enabled: false },
        series: [{ type: 'venn', name: 'Gene Sets', data: [] }]
      };
    }

    const keys = normalizedGeneSets.length === 2
      ? ['A', 'B', 'AB']
      : ['A', 'B', 'C', 'AB', 'AC', 'BC', 'ABC'];
    const data = keys.map(regionKey => {
      const sets = regionKey.split('');
      const setDisplayNames = sets
        .map(letter => normalizedSetMap.get(letter)?.displayName ?? '')
        .filter(Boolean);
      const labelText = setDisplayNames.join(' & ');
      const mask = keyToMask(regionKey, normalizedGeneSets.length);
      const totalCount = totalCountByMask.get(mask) || 0;
      const exclusiveCount = intersectionMap.get(regionKey)?.genes.length || 0;
      return {
        name: labelText,
        sets,
        value: totalCount,
        color: 'rgba(0,0,0,0)',
        borderColor: '#334155',
        borderWidth: 1,
        custom: { regionKey, exclusiveCount, totalCount, labelText }
      };
    });

    return {
      chart: { type: 'venn', height: 500 },
      title: { text: 'Gene Set Overlap Analysis' },
      subtitle: { text: 'Click: single select, Ctrl/Cmd+Click: add/remove' },
      accessibility: { enabled: false },
      exporting: {
        enabled: true,
        menuItemDefinitions: {
          downloadPNGWithOverlay: {
            text: 'Download PNG',
            onclick: function(this: Highcharts.Chart) {
              void exportVennWithOverlay(this, 'png');
            }
          },
          downloadJPEGWithOverlay: {
            text: 'Download JPEG',
            onclick: function(this: Highcharts.Chart) {
              void exportVennWithOverlay(this, 'jpeg');
            }
          },
          downloadSVGWithOverlay: {
            text: 'Download SVG',
            onclick: function(this: Highcharts.Chart) {
              void exportVennWithOverlay(this, 'svg');
            }
          }
        } as any,
        buttons: {
          contextButton: {
            menuItems: ['downloadPNGWithOverlay', 'downloadJPEGWithOverlay', 'downloadSVGWithOverlay', 'separator', 'downloadPDF']
          }
        },
        filename: 'venn-diagram'
      },
      tooltip: {
        headerFormat: '',
        formatter: function() {
          const point: any = this.point;
          const sets: string[] = point?.sets || [];
          const setLabel = sets
            .map(letter => normalizedSetMap.get(letter)?.displayName ?? '')
            .filter(Boolean)
            .join(' & ');
          const exclusiveCount: number = point?.custom?.exclusiveCount || 0;
          const totalCount: number = point?.custom?.totalCount || point?.value || 0;
          if (sets.length === 1) {
            const onlyTitle = setLabel ? `Only ${setLabel}` : 'Only';
            return `<b>${onlyTitle} (n=${exclusiveCount})</b><br/>Set total: ${totalCount} genes`;
          }
          const overlapTitle = setLabel || 'Intersection';
          return `<b>${overlapTitle}</b><br/>Exclusive: ${exclusiveCount} genes<br/>Total overlap: ${totalCount} genes`;
        }
      },
      plotOptions: {
        venn: {
          opacity: 0.85,
          states: { hover: { enabled: false }, inactive: { opacity: 1 } },
          dataLabels: {
            enabled: true,
            formatter: function() {
              const labelText = (this.point as any)?.custom?.labelText;
              return typeof labelText === 'string' ? labelText : '';
            }
          },
          point: { events: { click: handleVennClick } }
        }
      },
      series: [{ type: 'venn', name: 'Gene Sets', data }]
    };
  }, [
    canRenderComparison,
    vennAvailable,
    normalizedGeneSets.length,
    totalCountByMask,
    intersectionMap,
    normalizedSetMap,
    handleVennClick,
    exportVennWithOverlay
  ]);

  const upsetRows = useMemo(() => {
    let rows = intersections.map(region => ({ ...region, count: region.genes.length }));
    if (upsetHideZero) rows = rows.filter(row => row.count > 0);
    rows = rows.filter(row => row.count >= upsetMinCount);

    if (upsetSort === 'count_desc') rows.sort((a, b) => b.count - a.count || a.key.localeCompare(b.key));
    else if (upsetSort === 'count_asc') rows.sort((a, b) => a.count - b.count || a.key.localeCompare(b.key));
    else rows.sort((a, b) => a.key.localeCompare(b.key));

    if (upsetTopN !== 'all') rows = rows.slice(0, upsetTopN);
    return rows;
  }, [intersections, upsetHideZero, upsetMinCount, upsetSort, upsetTopN]);

  const maxUpsetCount = useMemo(() => Math.max(1, ...upsetRows.map(row => row.count), 1), [upsetRows]);

  const geneExpressionMap = useMemo(() => {
    const map = new Map<string, GeneExpressionData>();
    geneExpressionData?.matrix?.forEach(item => map.set(item.gene_id, item));
    return map;
  }, [geneExpressionData]);

  const matchedGeneIds = useMemo(() => geneExpressionData?.matched_gene_ids || [], [geneExpressionData]);

  const paginatedGenes = useMemo(
    () => geneExpressionData?.matrix?.map(item => item.gene_id) || [],
    [geneExpressionData]
  );

  const totalPages = geneExpressionData?.total_pages || 0;
  const totalMatchedGenes = geneExpressionData?.total_genes || 0;
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
    enabled: Boolean(selectedIntersection) && paginatedGenes.length > 0,
    dependencyKey: [
      selectedIntersection?.key ?? 'none',
      selectedMatrixType,
      currentPage,
      pageSize,
      paginatedGenes.length,
      geneExpressionData?.samples?.length ?? 0,
      loadingExpression ? 'loading' : 'idle'
    ].join('|')
  });

  const handleSetNameChange = (id: string, newName: string) => {
    onGeneSetsChange(geneSets.map(set => set.id === id ? { ...set, name: newName } : set));
  };

  const handleClearSet = (id: string) => {
    onGeneSetsChange(geneSets.map(set => set.id === id ? { ...set, genes: [] } : set));
    onGeneInputsChange({ ...geneInputs, [id]: '' });
  };

  const handleDeleteSet = (id: string) => {
    if (geneSets.length < 2) {
      alert('Minimum 2 sets required');
      return;
    }
    onGeneSetsChange(geneSets.filter(set => set.id !== id));
    const newInputs = { ...geneInputs };
    delete newInputs[id];
    onGeneInputsChange(newInputs);
  };

  const handleAddSet = () => {
    if (geneSets.length >= 4) {
      alert('Maximum 4 sets allowed');
      return;
    }
    const newId = `set${Date.now()}`;
    const setLetter = SET_LETTERS[geneSets.length] || String(geneSets.length + 1);
    onGeneSetsChange([...geneSets, { id: newId, name: `Set ${setLetter}`, genes: [] }]);
  };

  const handleGeneInputChange = (id: string, value: string) => {
    onGeneInputsChange({ ...geneInputs, [id]: value });
    const newGenes = normalizeGenes(value.split(/[\n,;]+/));
    onGeneSetsChange(geneSets.map(set => set.id === id ? { ...set, genes: newGenes } : set));
  };

  const handlePageSizeChange = (newSize: number) => {
    setPageSize(newSize);
    setCurrentPage(1);
  };

  const handleSearch = useCallback(() => {
    setActiveSearch(searchInputRef.current?.value.trim() || '');
    setCurrentPage(1);
    setSelectedGenes(new Set());
    setSelectAllState(0);
  }, []);

  const handleClearSearch = useCallback(() => {
    if (searchInputRef.current) searchInputRef.current.value = '';
    setActiveSearch('');
    setCurrentPage(1);
    setSelectedGenes(new Set());
    setSelectAllState(0);
  }, []);

  const handleSelectAllCycle = useCallback(() => {
    if (selectAllState === 0) {
      const next = new Set(selectedGenes);
      paginatedGenes.forEach(geneId => next.add(geneId));
      setSelectedGenes(next);
      setSelectAllState(1);
    } else if (selectAllState === 1) {
      setSelectedGenes(new Set(matchedGeneIds));
      setSelectAllState(2);
    } else {
      setSelectedGenes(new Set());
      setSelectAllState(0);
    }
  }, [selectAllState, selectedGenes, paginatedGenes, matchedGeneIds]);

  const handleSelectOne = (geneId: string) => {
    const next = new Set(selectedGenes);
    if (next.has(geneId)) next.delete(geneId);
    else next.add(geneId);
    setSelectedGenes(next);
    setSelectAllState(0);
  };

  const vennTableColGroup = (
    <colgroup>
      <col style={{ width: `${tableColumnWidths.select}px` }} />
      <col style={{ width: `${tableColumnWidths.rowNo}px` }} />
      <col style={{ width: `${tableColumnWidths.geneId}px` }} />
      <col style={{ width: `${tableColumnWidths.geneSymbol}px` }} />
      <col style={{ width: `${tableColumnWidths.pattern}px` }} />
      {(geneExpressionData?.samples || []).map(sample => (
        <col key={sample} style={{ width: `${tableColumnWidths.sample}px` }} />
      ))}
    </colgroup>
  );

  const vennHeaderRow = (
    <tr>
      <th className="px-3 py-2 text-left text-xs font-bold text-slate-600 uppercase" style={{ width: `${tableColumnWidths.select}px`, backgroundColor: 'rgb(248 250 252)', position: 'sticky', left: 0, zIndex: 20 }}>
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
      <th className="px-3 py-2 text-left text-xs font-bold text-slate-600 uppercase" style={{ width: `${tableColumnWidths.rowNo}px`, backgroundColor: 'rgb(248 250 252)' }}>#</th>
      <th className="px-3 py-2 text-left text-xs font-bold text-slate-600 uppercase" style={{ width: `${tableColumnWidths.geneId}px`, minWidth: `${tableColumnWidths.geneId}px`, backgroundColor: 'rgb(248 250 252)', position: 'sticky', left: `${tableStickyOffsets.geneId}px`, zIndex: 20 }}>Gene ID</th>
      <th className="px-3 py-2 text-left text-xs font-bold text-slate-600 uppercase" style={{ width: `${tableColumnWidths.geneSymbol}px`, minWidth: `${tableColumnWidths.geneSymbol}px`, backgroundColor: 'rgb(248 250 252)', position: 'sticky', left: `${tableStickyOffsets.geneSymbol}px`, zIndex: 20 }}>Symbol</th>
      <th className="px-3 py-2 text-left text-xs font-bold text-slate-600 uppercase" style={{ width: `${tableColumnWidths.pattern}px`, minWidth: `${tableColumnWidths.pattern}px`, backgroundColor: 'rgb(248 250 252)', position: 'sticky', left: `${tableStickyOffsets.pattern}px`, zIndex: 20 }}>Pattern</th>
      {(geneExpressionData?.samples || []).map(sample => (
        <th key={sample} className="px-3 py-2 text-left text-xs font-bold text-slate-600 uppercase" style={{ width: `${tableColumnWidths.sample}px`, minWidth: `${tableColumnWidths.sample}px`, backgroundColor: 'rgb(248 250 252)' }}>
          {sample}
        </th>
      ))}
    </tr>
  );

  const fetchGeneExpressionData = async (genes: string[], searchQuery: string, page: number, limit: number) => {
    if (genes.length === 0) {
      setGeneExpressionData(null);
      return;
    }
    setLoadingExpression(true);
    try {
      const data = await apiService.fetchSelectedCountResults(workbenchId, {
        matrix_type: selectedMatrixType === 'Raw' ? 'RAW' : selectedMatrixType,
        selected_genes: genes,
        search: searchQuery,
        page,
        limit
      });
      setGeneExpressionData({
        matrix: data.matrix || [],
        samples: data.samples || [],
        groups: data.groups || [],
        total_genes: data.total_genes || 0,
        showing_genes: data.showing_genes || 0,
        current_page: data.current_page || page,
        total_pages: data.total_pages || 0,
        page_size: data.page_size || limit,
        matched_gene_ids: data.matched_gene_ids || [],
        status: data.status || 'available'
      });
    } catch (error) {
      console.error('Error fetching gene expression data:', error);
      setGeneExpressionData(null);
    } finally {
      setLoadingExpression(false);
    }
  };

  useEffect(() => {
    if (selectedIntersection) fetchGeneExpressionData(selectedIntersection.genes, activeSearch, currentPage, pageSize);
    else setGeneExpressionData(null);
  }, [selectedIntersection, selectedMatrixType, activeSearch, currentPage, pageSize]);

  useEffect(() => {
    setSelectedGenes(new Set());
    setSelectAllState(0);
  }, [currentPage, pageSize, selectedIntersection, activeSearch, selectedMatrixType]);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (actionMenuRef.current && !actionMenuRef.current.contains(event.target as Node)) {
        setActionMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleDownload = () => {
    if (!selectedIntersection) return;
    const downloadSelectedGenes = async () => {
      try {
        const response = await fetch(`/api/workbenches/${workbenchId}/count-results/download`, {
          method: 'POST',
          credentials: 'include',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            matrix_type: selectedMatrixType === 'Raw' ? 'RAW' : selectedMatrixType,
            selected_genes: matchedGeneIds.length > 0 ? matchedGeneIds : selectedIntersection.genes
          })
        });

        if (!response.ok) {
          throw new Error('Failed to download selected genes');
        }

        const blob = await response.blob();
        const downloadUrl = window.URL.createObjectURL(blob);
        const contentDisposition = response.headers.get('Content-Disposition');
        const filenameMatch = contentDisposition?.match(/filename=\"?([^"]+)\"?/);
        const filename = filenameMatch?.[1] || `counts_${selectedMatrixType.toLowerCase()}_selected_genes.csv`;

        const a = document.createElement('a');
        a.href = downloadUrl;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(downloadUrl);
      } catch (error) {
        console.error('Failed to download selected genes:', error);
        alert('Failed to download selected genes. Please try again.');
      }
    };

    void downloadSelectedGenes();
  };

  const handleGOAnalysis = async (provider: 'david' | 'gprofiler') => {
    const genes = Array.from(selectedGenes);
    setGOLoading(true);
    setGOModalOpen(true);
    try {
      const result = await apiService.runGOEnrichment(workbenchId, {
        genes,
        databases: ['GO_BP', 'GO_MF', 'GO_CC'],
        p_value_cutoff: 0.05,
        description: `Venn diagram selected genes from ${selectedMatrixType} count matrix`,
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

  const syncVennOverlay = useCallback(() => {
    if (!canRenderComparison || !vennAvailable || visualizationMode !== 'venn') {
      setVennOverlayState(null);
      logVennDebug('[VENN-OVERLAY-SKIP]', { reason: 'mode_or_data_not_ready' });
      return;
    }

    const chart = chartComponentRef.current?.chart as any;
    if (!chart || !chart.series?.[0]) {
      setVennOverlayState(null);
      logVennDebug('[VENN-OVERLAY-SKIP]', { reason: 'chart_or_series_missing' });
      return;
    }

    const selectedKeys = Array.from(selectedRegionKeys).filter(Boolean);
    if (selectedKeys.length === 0) {
      setVennOverlayState(null);
      logVennDebug('[VENN-OVERLAY-SKIP]', {
        reason: 'selected_keys_missing',
        selectedRegionKeys: selectedKeys
      });
      return;
    }

    const points = chart.series[0].points || [];
    const toPathData = (element: SVGGraphicsElement | null | undefined): string | null => {
      if (!element) return null;
      const tag = element.tagName?.toLowerCase?.();
      if (tag === 'path') return element.getAttribute('d');

      if (tag === 'circle') {
        const cx = Number(element.getAttribute('cx') || 0);
        const cy = Number(element.getAttribute('cy') || 0);
        const r = Number(element.getAttribute('r') || 0);
        if (!Number.isFinite(cx) || !Number.isFinite(cy) || !Number.isFinite(r) || r <= 0) return null;
        return `M ${cx - r} ${cy} A ${r} ${r} 0 1 0 ${cx + r} ${cy} A ${r} ${r} 0 1 0 ${cx - r} ${cy} Z`;
      }

      if (tag === 'ellipse') {
        const cx = Number(element.getAttribute('cx') || 0);
        const cy = Number(element.getAttribute('cy') || 0);
        const rx = Number(element.getAttribute('rx') || 0);
        const ry = Number(element.getAttribute('ry') || 0);
        if (!Number.isFinite(cx) || !Number.isFinite(cy) || !Number.isFinite(rx) || !Number.isFinite(ry) || rx <= 0 || ry <= 0) return null;
        return `M ${cx - rx} ${cy} A ${rx} ${ry} 0 1 0 ${cx + rx} ${cy} A ${rx} ${ry} 0 1 0 ${cx - rx} ${cy} Z`;
      }

      return null;
    };

    const matrixToTransform = (matrix: DOMMatrix | SVGMatrix | null | undefined) => {
      if (!matrix) return null;
      const fmt = (value: number) => (Number.isFinite(value) ? value.toFixed(4) : '0');
      return `matrix(${fmt(matrix.a)} ${fmt(matrix.b)} ${fmt(matrix.c)} ${fmt(matrix.d)} ${fmt(matrix.e)} ${fmt(matrix.f)})`;
    };

    const fallbackTransform = `translate(${chart.plotLeft || 0} ${chart.plotTop || 0})`;
    const items: VennOverlayItem[] = selectedKeys
      .map((selectedKey) => {
        const selectedPoint = points.find((point: any) => point?.custom?.regionKey === selectedKey);
        const selectedElement = selectedPoint?.graphic?.element as SVGGraphicsElement | undefined;
        const selectedPathElement = selectedElement?.tagName?.toLowerCase?.() === 'path'
          ? selectedElement
          : (selectedElement?.querySelector?.('path') as SVGGraphicsElement | null) || selectedElement;
        const selectedPath = toPathData(selectedPathElement);
        if (!selectedPath) {
          logVennDebug('[VENN-OVERLAY-SKIP]', {
            reason: 'selected_path_missing',
            selectedKey,
            hasSelectedPoint: Boolean(selectedPoint),
            selectedTag: selectedElement?.tagName,
            points: points.map((point: any) => point?.custom?.regionKey || sortKey(point?.sets || []))
          });
          return null;
        }

        const selectedTransform = matrixToTransform(selectedPathElement?.getCTM?.()) || fallbackTransform;
        const overlapPaths: Array<{ d: string; transform: string }> = points
          .filter((point: any) => {
            const key = point?.custom?.regionKey;
            return (
              typeof key === 'string' &&
              key.length > 1 &&
              selectedKey.length === 1 &&
              key.includes(selectedKey)
            );
          })
          .map((point: any) => {
            const element = point?.graphic?.element as SVGGraphicsElement | undefined;
            const pathElement = element?.tagName?.toLowerCase?.() === 'path'
              ? element
              : (element?.querySelector?.('path') as SVGGraphicsElement | null) || element;
            const path = toPathData(pathElement);
            if (!path) return null;
            const transform = matrixToTransform(pathElement?.getCTM?.()) || fallbackTransform;
            return { d: path, transform };
          })
          .filter((item): item is { d: string; transform: string } => Boolean(item));

        return {
          key: selectedKey,
          path: selectedPath,
          transform: selectedTransform,
          overlapPaths
        };
      })
      .filter((item): item is VennOverlayItem => Boolean(item));

    if (items.length === 0) {
      setVennOverlayState(null);
      logVennDebug('[VENN-OVERLAY-SKIP]', {
        reason: 'no_renderable_items',
        selectedRegionKeys: selectedKeys
      });
      return;
    }

    setVennOverlayState({
      width: chart.chartWidth,
      height: chart.chartHeight,
      items
    });

    logVennDebug('[VENN-OVERLAY]', {
      selectedKeys,
      renderedItems: items.map(item => ({
        key: item.key,
        transform: item.transform,
        pathLength: item.path.length,
        overlapCount: item.overlapPaths.length
      }))
    });
  }, [canRenderComparison, vennAvailable, visualizationMode, selectedRegionKeys, logVennDebug]);

  useEffect(() => {
    if (visualizationMode !== 'venn' || !canRenderComparison || !vennAvailable) {
      setVennOverlayState(null);
      return;
    }

    const chart = chartComponentRef.current?.chart as any;
    if (!chart) return;

    syncVennOverlay();

    const offRender = Highcharts.addEvent(chart, 'render', syncVennOverlay);
    const offRedraw = Highcharts.addEvent(chart, 'redraw', syncVennOverlay);
    const onResize = () => syncVennOverlay();
    window.addEventListener('resize', onResize);

    return () => {
      if (typeof offRender === 'function') offRender();
      if (typeof offRedraw === 'function') offRedraw();
      window.removeEventListener('resize', onResize);
    };
  }, [syncVennOverlay, visualizationMode, canRenderComparison, vennAvailable]);

  return (
    <div className="flex h-full overflow-hidden relative">
      {isSetsPanelCollapsed ? (
        <div className="bg-slate-50 border-r border-slate-200 flex-shrink-0">
          <button
            onClick={() => setIsSetsPanelCollapsed(false)}
            className="h-full px-2 text-xs text-slate-600 hover:bg-slate-100"
            title="Expand gene sets panel"
          >
            Gene Sets
          </button>
        </div>
      ) : (
        <div className="flex flex-shrink-0 overflow-hidden">
          <div className="w-56 bg-slate-50 border-r border-slate-200 overflow-y-auto p-4 space-y-4">
            <button
              onClick={onReset}
              disabled={geneSets.length === 0}
              className="w-full py-2 px-4 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:bg-slate-300 disabled:cursor-not-allowed text-sm font-semibold"
            >
              Reset All Sets
            </button>
            {geneSets.map((set, index) => (
              <div key={set.id} className="bg-white rounded-lg border border-slate-200">
                <div className="flex items-center gap-2 p-2 border-b border-slate-200">
                  <input
                    type="text"
                    value={set.name}
                    placeholder={fallbackSetName(index)}
                    onChange={(e) => handleSetNameChange(set.id, e.target.value)}
                    className="text-sm font-semibold border border-slate-200 rounded px-2 py-1 w-full"
                  />
                </div>
                <div className="p-2 space-y-2">
                  <textarea
                    value={geneInputs[set.id] || ''}
                    onChange={(e) => handleGeneInputChange(set.id, e.target.value)}
                    placeholder="Enter gene IDs"
                    className="w-full h-36 text-xs font-mono border border-slate-300 rounded px-2 py-1.5"
                  />
                  <div className="flex items-center justify-between text-xs text-slate-500">
                    <span>{normalizeGenes(set.genes || []).length} genes</span>
                    <div className="space-x-2">
                      <button onClick={() => handleClearSet(set.id)} className="hover:text-orange-600">clear</button>
                      <button onClick={() => handleDeleteSet(set.id)} className="hover:text-red-600">delete</button>
                    </div>
                  </div>
                </div>
              </div>
            ))}
            {geneSets.length < 4 && (
              <button
                onClick={handleAddSet}
                className="w-full py-3 border-2 border-dashed border-slate-300 rounded-lg text-sm text-slate-500 hover:border-blue-500 hover:text-blue-600"
              >
                + Add Set
              </button>
            )}
          </div>
          <button
            onClick={() => setIsSetsPanelCollapsed(true)}
            className="w-8 bg-slate-50 hover:bg-slate-100 border-r border-slate-200 text-slate-500"
            title="Collapse gene sets panel"
          >
            {'<'}
          </button>
        </div>
      )}

      <div className="w-[560px] flex-shrink-0 bg-white border-r border-slate-200 p-4 overflow-y-auto">
        <div className="space-y-3">
          {hasEnoughSets && (
            <div className="flex items-center justify-between gap-2">
              <div className="text-xs text-slate-500">Click: single select, Ctrl/Cmd+Click: add/remove</div>
              <div className="inline-flex rounded border border-slate-300 overflow-hidden">
                <button
                  onClick={() => setVisualizationMode('venn')}
                  disabled={!vennAvailable}
                  className={`px-3 py-1 text-xs ${visualizationMode === 'venn' ? 'bg-blue-600 text-white' : 'bg-white text-slate-700'} ${!vennAvailable ? 'opacity-40 cursor-not-allowed' : ''}`}
                >
                  Venn
                </button>
                <button
                  onClick={() => setVisualizationMode('upset')}
                  disabled={!hasEnoughSets}
                  className={`px-3 py-1 text-xs ${visualizationMode === 'upset' ? 'bg-blue-600 text-white' : 'bg-white text-slate-700'}`}
                >
                  UpSet
                </button>
              </div>
            </div>
          )}

          {normalizedGeneSets.length >= 4 && (
            <p className="text-xs text-slate-500">4 sets detected. UpSet is used to avoid Venn distortion.</p>
          )}

          {canRenderComparison ? (
            visualizationMode === 'venn' && vennAvailable ? (
              <div className="relative">
                <HighchartsReact highcharts={Highcharts} options={chartOptions} ref={chartComponentRef} immutable={true} />
                {vennOverlayState && (() => {
                  if (!vennOverlayState.items || vennOverlayState.items.length === 0) return null;

                  return (
                    <svg
                      className="absolute inset-0"
                      width={vennOverlayState.width}
                      height={vennOverlayState.height}
                      viewBox={`0 0 ${vennOverlayState.width} ${vennOverlayState.height}`}
                      preserveAspectRatio="none"
                      style={{ pointerEvents: 'none' }}
                    >
                      {vennOverlayState.items.map((item) => {
                        const isOnlySelection = item.key.length === 1;
                        if (isOnlySelection) {
                          const onlyPathD = [
                            item.path,
                            ...item.overlapPaths
                              .filter(path => path.transform === item.transform)
                              .map(path => path.d)
                          ].join(' ');
                          return (
                            <path
                              key={`overlay-${item.key}`}
                              d={onlyPathD}
                              transform={item.transform}
                              fillRule="evenodd"
                              clipRule="evenodd"
                              fill="rgba(59,130,246,0.15)"
                              stroke="#1d4ed8"
                              strokeWidth={2}
                              vectorEffect="non-scaling-stroke"
                            />
                          );
                        }

                        return (
                          <path
                            key={`overlay-${item.key}`}
                            d={item.path}
                            transform={item.transform}
                            fill="rgba(59,130,246,0.15)"
                            stroke="#1d4ed8"
                            strokeWidth={2}
                            vectorEffect="non-scaling-stroke"
                          />
                        );
                      })}
                    </svg>
                  );
                })()}
              </div>
            ) : (
              <div className="space-y-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs text-slate-600">Sort:</span>
                  <select value={upsetSort} onChange={(e) => setUpsetSort(e.target.value as UpsetSort)} className="text-xs border border-slate-300 rounded px-2 py-1">
                    <option value="count_desc">Count desc</option>
                    <option value="count_asc">Count asc</option>
                    <option value="key_asc">Combination key</option>
                  </select>
                  <span className="text-xs text-slate-600">Top N:</span>
                  <select
                    value={String(upsetTopN)}
                    onChange={(e) => setUpsetTopN(e.target.value === 'all' ? 'all' : Number(e.target.value))}
                    className="text-xs border border-slate-300 rounded px-2 py-1"
                  >
                    {UPSET_TOP_N_OPTIONS.map(option => <option key={option} value={option}>{option}</option>)}
                    <option value="all">All</option>
                  </select>
                  <span className="text-xs text-slate-600">Min count:</span>
                  <input
                    type="number"
                    min={0}
                    value={upsetMinCount}
                    onChange={(e) => setUpsetMinCount(Math.max(0, Number(e.target.value) || 0))}
                    className="w-20 text-xs border border-slate-300 rounded px-2 py-1"
                  />
                  <label className="inline-flex items-center gap-1 text-xs text-slate-600">
                    <input type="checkbox" checked={upsetHideZero} onChange={(e) => setUpsetHideZero(e.target.checked)} />
                    Hide zero-count
                  </label>
                </div>
                <div className="overflow-auto max-h-[560px] border border-slate-200 rounded-lg bg-white">
                  {upsetRows.length === 0 ? (
                    <div className="p-6 text-sm text-slate-400 text-center">No intersections match current filter.</div>
                  ) : (
                    <table className="min-w-full text-sm">
                      <thead className="bg-slate-50 sticky top-0">
                        <tr>
                          <th className="px-2 py-2 text-left text-xs">#</th>
                          <th className="px-2 py-2 text-left text-xs">Combination</th>
                          <th className="px-2 py-2 text-left text-xs">Count</th>
                          {normalizedGeneSets.map(set => (
                            <th key={set.id} className="px-2 py-2 text-center text-xs">{set.displayName}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {upsetRows.map((row, idx) => {
                          const isSelected = selectedRegionKeys.has(row.key);
                          const barWidth = `${Math.max(3, (row.count / maxUpsetCount) * 100)}%`;
                          return (
                            <tr
                              key={row.key}
                              onClick={(e) => applyRegionSelection(row.key, e.ctrlKey || e.metaKey)}
                              className={`cursor-pointer ${isSelected ? 'bg-blue-50' : 'hover:bg-slate-50'}`}
                            >
                              <td className="px-2 py-2 text-xs text-slate-500">{idx + 1}</td>
                              <td className="px-2 py-2">
                                <div className="text-sm text-slate-800">{row.label}</div>
                                <div className="text-xs text-slate-500">{row.key}</div>
                              </td>
                              <td className="px-2 py-2">
                                <div className="flex items-center gap-2">
                                  <span className="text-xs">{row.count}</span>
                                  <div className="h-2 w-24 bg-slate-100 rounded-full overflow-hidden">
                                    <div className={`h-full ${isSelected ? 'bg-blue-600' : 'bg-slate-400'}`} style={{ width: barWidth }} />
                                  </div>
                                </div>
                              </td>
                              {normalizedGeneSets.map(set => (
                                <td key={set.id} className="px-2 py-2 text-center">
                                  <span className={`inline-block w-3 h-3 rounded-full border ${row.sets.includes(set.letter) ? 'bg-slate-700 border-slate-800' : 'bg-white border-slate-300'}`} />
                                </td>
                              ))}
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  )}
                </div>
              </div>
            )
          ) : (
            <div className="text-center text-slate-400 py-20 text-sm">
              {normalizedGeneSets.length < 2 ? 'Add at least 2 sets to start' : 'Add genes to all active sets to visualize overlap'}
            </div>
          )}
        </div>
      </div>

      <div ref={tableSectionRef} className="flex-1 flex flex-col bg-white overflow-visible relative">
        {selectedIntersection ? (
          <>
            <div className="p-4 border-b border-slate-200 space-y-3">
              <div>
                <h3 className="text-lg font-semibold text-slate-800 break-words">{selectedIntersection.label}</h3>
                <p className="text-sm text-slate-500">
                  {activeSearch ? `${totalMatchedGenes} / ${selectedIntersection.genes.length} genes (filtered)` : `${selectedIntersection.genes.length} genes total`}
                </p>
              </div>

              <div className="flex flex-wrap items-center gap-4">
                <textarea
                  ref={searchInputRef}
                  rows={1}
                  placeholder="Search Gene IDs or Symbols..."
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && e.ctrlKey) handleSearch();
                  }}
                  className="px-3 py-2 border border-slate-300 rounded-lg w-64 min-h-[40px] max-h-[180px] resize-vertical"
                />
                <button onClick={handleSearch} className="px-3 py-2 bg-blue-600 text-white rounded-lg text-sm">Search</button>
                {activeSearch && <button onClick={handleClearSearch} className="px-3 py-2 bg-slate-200 text-slate-700 rounded-lg text-sm">Clear</button>}

                <SelectableGeneTableShell
                  selectedGenes={Array.from(selectedGenes)}
                  onHeatmap={openHeatmap}
                  onGOAnalysis={(provider) => { void runGOAnalysis(provider); }}
                  onKEGG={openKEGG}
                  afterAnalyzeControls={(
                    <button onClick={handleDownload} disabled={loadingExpression} className="px-3 py-2 bg-green-600 text-white rounded-lg text-sm disabled:opacity-50">
                      Download
                    </button>
                  )}
                  analyzeButtonClassName="px-3 py-2 text-sm font-semibold bg-blue-600 text-white rounded-lg disabled:bg-slate-300"
                  toolbarClassName="contents"
                  leftGroupClassName="contents"
                  rightGroupClassName="contents"
                />

                <div className="ml-auto flex items-center gap-1">
                  {(['Raw', 'TPM', 'TMM'] as const).map(type => (
                    <button
                      key={type}
                      onClick={() => {
                        if (type === 'TPM' && !hasTPMMatrix) return;
                        setSelectedMatrixType(type);
                      }}
                      disabled={loadingExpression || (type === 'TPM' && !hasTPMMatrix)}
                      title={type === 'TPM' && !hasTPMMatrix ? 'TPM matrix is unavailable for this workbench' : undefined}
                      className={`px-2 py-1 rounded border text-sm ${selectedMatrixType === type ? 'bg-blue-600 text-white border-blue-600' : 'bg-white text-slate-700 border-slate-300'} ${(type === 'TPM' && !hasTPMMatrix) ? 'opacity-50 cursor-not-allowed' : ''}`}
                    >
                      {type === 'Raw' ? 'Gene Count' : (type === 'TPM' && !hasTPMMatrix ? 'TPM (Unavailable)' : type)}
                    </button>
                  ))}
                </div>
              </div>

              {totalPages > 0 && (
                <div className="flex items-center gap-3 text-sm text-slate-600">
                  <span>Rows per page:</span>
                  <select value={pageSize} onChange={(e) => handlePageSizeChange(Number(e.target.value))} className="border border-slate-300 rounded px-2 py-1">
                    {[100, 500, 1000, 2000, 5000].map(size => <option key={size} value={size}>{size}</option>)}
                  </select>
                  <span>
                    {totalMatchedGenes === 0 ? 0 : ((currentPage - 1) * pageSize + 1)}
                    -
                    {Math.min(currentPage * pageSize, totalMatchedGenes)}
                    {' '}of {totalMatchedGenes.toLocaleString()}
                  </span>
                  <button onClick={() => setCurrentPage(Math.max(1, currentPage - 1))} disabled={currentPage === 1} className="px-2 py-1 border border-slate-300 rounded disabled:opacity-50">Previous</button>
                  <button onClick={() => setCurrentPage(Math.min(totalPages, currentPage + 1))} disabled={currentPage === totalPages} className="px-2 py-1 border border-slate-300 rounded disabled:opacity-50">Next</button>
                </div>
              )}
            </div>

            <div className="flex-1 overflow-visible">
              {loadingExpression ? (
                <div className="flex items-center justify-center h-64">
                  <div className="animate-spin rounded-full h-10 w-10 border-b-4 border-blue-600" />
                </div>
              ) : (
                <div className="border border-slate-200 rounded-lg overflow-visible bg-white">
                  <div ref={topScrollbarRef} className="overflow-x-auto overflow-y-hidden border-b border-slate-200 bg-slate-50">
                    <div style={{ width: `${topScrollbarWidth}px`, height: '16px' }} />
                  </div>
                  <div ref={tableWrapperRef} className="relative" style={{ overflowX: 'auto', overflowY: 'visible' }}>
                    <table ref={tableRef} className="min-w-full divide-y divide-slate-200" style={{ tableLayout: 'fixed' }}>
                      {vennTableColGroup}
                      <thead ref={tableTheadRef} className="bg-slate-50">
                        {vennHeaderRow}
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {paginatedGenes.map((geneId, idx) => {
                          const rowNo = (currentPage - 1) * pageSize + idx + 1;
                          const geneData = geneExpressionMap.get(geneId);
                          const samples = geneExpressionData?.samples || [];
                          const values = samples.map(sample => {
                            const value = geneData?.[sample];
                            return typeof value === 'number' ? value : parseFloat(value as string) || 0;
                          });
                          return (
                            <tr key={geneId} className="hover:bg-slate-50">
                              <td className="px-3 py-2" style={{ position: 'sticky', left: 0, zIndex: 20, backgroundColor: 'white' }}>
                                <input type="checkbox" checked={selectedGenes.has(geneId)} onChange={() => handleSelectOne(geneId)} />
                              </td>
                              <td className="px-3 py-2 text-sm text-slate-500">{rowNo}</td>
                              <td className="px-3 py-2 text-sm font-medium text-slate-900" style={{ position: 'sticky', left: `${tableStickyOffsets.geneId}px`, zIndex: 20, backgroundColor: 'white', minWidth: `${tableColumnWidths.geneId}px` }} title={geneData?.gene_description || 'No description available'}>
                                {geneId}
                              </td>
                              <td className="px-3 py-2 text-sm text-slate-700" style={{ position: 'sticky', left: `${tableStickyOffsets.geneSymbol}px`, zIndex: 20, backgroundColor: 'white', minWidth: `${tableColumnWidths.geneSymbol}px` }}>{geneData?.gene_symbol || '-'}</td>
                              <td className="px-3 py-2" style={{ position: 'sticky', left: `${tableStickyOffsets.pattern}px`, zIndex: 20, backgroundColor: 'white', minWidth: `${tableColumnWidths.pattern}px` }}>
                                {samples.length > 0 ? <MiniHeatmap values={values} samples={samples} width={Math.min(samples.length * 16, 240)} height={20} /> : <span className="text-xs text-slate-400">N/A</span>}
                              </td>
                              {samples.map(sample => (
                                <td key={sample} className="px-3 py-2 text-sm text-slate-600">{geneData?.[sample] ?? '-'}</td>
                              ))}
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          </>
        ) : (
          <div className="flex items-center justify-center h-full text-slate-400">
            <div className="text-center">
              <div className="text-3xl mb-4 text-slate-300">Select</div>
              <p className="text-sm">Click a Venn/UpSet region to view genes</p>
            </div>
          </div>
        )}
      </div>

      {overlayHeader.visible && typeof document !== 'undefined' && createPortal(
        <div className="fixed z-[120] pointer-events-none" style={{ top: overlayHeader.top, left: overlayHeader.left, width: overlayHeader.width }}>
          <div ref={floatingTopScrollbarRef} className="overflow-x-auto overflow-y-hidden bg-slate-50 border border-slate-200 border-b-0 rounded-t-lg pointer-events-auto" style={{ width: `${overlayHeader.width}px` }}>
            <div style={{ width: `${overlayHeader.tableWidth}px`, height: '16px' }} />
          </div>
          <div className="relative" style={{ width: `${overlayHeader.width}px`, height: `${overlayHeader.height || 57}px` }}>
            <div className="absolute top-0 left-0 overflow-hidden border-x border-b border-slate-200 bg-slate-50 shadow-sm" style={{ width: `${Math.min(fixedHeaderWidth, overlayHeader.width)}px` }}>
              <table className="min-w-full divide-y divide-slate-200" style={{ width: `${Math.min(fixedHeaderWidth, overlayHeader.width)}px`, tableLayout: 'fixed' }}>
                <colgroup>
                  <col style={{ width: `${tableColumnWidths.select}px` }} />
                  <col style={{ width: `${tableColumnWidths.rowNo}px` }} />
                  <col style={{ width: `${tableColumnWidths.geneId}px` }} />
                  <col style={{ width: `${tableColumnWidths.geneSymbol}px` }} />
                  <col style={{ width: `${tableColumnWidths.pattern}px` }} />
                </colgroup>
                <thead className="bg-slate-50">{vennHeaderRow}</thead>
              </table>
            </div>
            <div className="absolute top-0 overflow-hidden border-r border-b border-slate-200 bg-slate-50 shadow-sm" style={{ left: `${Math.min(fixedHeaderWidth, overlayHeader.width)}px`, width: `${Math.max(0, overlayHeader.width - Math.min(fixedHeaderWidth, overlayHeader.width))}px` }}>
              <div style={{ width: `${Math.max(0, overlayHeader.tableWidth - fixedHeaderWidth)}px`, transform: `translateX(-${overlayHeader.scrollLeft}px)` }}>
                <table className="min-w-full divide-y divide-slate-200" style={{ width: `${Math.max(0, overlayHeader.tableWidth - fixedHeaderWidth)}px`, tableLayout: 'fixed' }}>
                  <colgroup>
                    <col style={{ width: `${tableColumnWidths.rowNo}px` }} />
                    {(geneExpressionData?.samples || []).map(sample => <col key={sample} style={{ width: `${tableColumnWidths.sample}px` }} />)}
                  </colgroup>
                  <thead className="bg-slate-50">
                    <tr>
                      <th className="px-3 py-2 text-left text-xs font-bold text-slate-600 uppercase" style={{ width: `${tableColumnWidths.rowNo}px`, minWidth: `${tableColumnWidths.rowNo}px` }}>#</th>
                      {(geneExpressionData?.samples || []).map(sample => (
                        <th key={sample} className="px-3 py-2 text-left text-xs font-bold text-slate-600 uppercase" style={{ width: `${tableColumnWidths.sample}px`, minWidth: `${tableColumnWidths.sample}px` }}>
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

      <GOAnalysisModal
        isOpen={analysisGOModalOpen}
        onClose={closeAnalysisGO}
        result={analysisGOResult}
        isLoading={analysisGOLoading}
        workbenchId={workbenchId}
        comparisonName=""
        toolName="Venn Diagram"
      />
      <HeatmapAnalysisModal
        isOpen={analysisHeatmapOpen}
        onClose={closeAnalysisHeatmap}
        workbenchId={workbenchId}
        selectedGenes={Array.from(selectedGenes)}
        comparisonName=""
        toolName="Venn Diagram"
      />
      <KEGGPathwayModal
        isOpen={analysisKEGGOpen}
        onClose={closeAnalysisKEGG}
        workbenchId={workbenchId}
        selectedGenes={Array.from(selectedGenes)}
        comparisonName=""
        toolName="Venn Diagram"
      />
    </div>
  );
};

export default WorkbenchDetailVennDiagram;
