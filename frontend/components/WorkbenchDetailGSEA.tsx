import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { Workbench } from '../types';
import { apiService } from '../services/api';
import SelectableGeneTableShell from './SelectableGeneTableShell';
import VennSetMenu, { VennSetSummary } from './VennSetMenu';
import MiniHeatmap from './MiniHeatmap';
import ColumnFilterPopup, { ColumnFilter } from './ColumnFilterPopup';
import { useGeneAnalysisActions } from '../hooks/useGeneAnalysisActions';
import GOAnalysisModal from './GOAnalysisModal';
import HeatmapAnalysisModal from './HeatmapAnalysisModal';
import KEGGPathwayModal from './KEGGPathwayModal';

interface GSEAResultRow {
  gene_set: string;
  gene_set_id?: string;
  description: string;
  gene_set_size: number;
  overlap_size: number;
  es: number;
  nes: number;
  p_value: number;
  fdr: number;
  leading_edge_size: number;
}

interface BuiltInDatabase {
  key: string;
  label: string;
  description: string;
  species: string;
  id_namespace: string;
  generation_date: string;
  source?: string;
  status?: string;
  usage_note?: string;
  origin_url?: string;
  provisioned_at?: string;
}

interface ValidationSummary {
  ranked_gene_count: number;
  tested_gene_sets: number;
  min_overlap: number;
  permutations: number;
}

interface GSEAResponse {
  comparison_name: string;
  deg_tool: string;
  gene_set_db: string;
  gene_set_db_label: string;
  database_metadata?: BuiltInDatabase;
  ranking_metric: string;
  zero_cross_index: number | null;
  validation: ValidationSummary;
  rows: GSEAResultRow[];
}

interface GSEAGeneSetDetail {
  comparison_name: string;
  deg_tool: string;
  gene_set_db: string;
  gene_set: string;
  ranking_metric: string;
  ranking_profile: Array<{
    index: number;
    value: number;
  }>;
  zero_cross_index: number | null;
  description: string;
  gene_set_size: number;
  overlap_size: number;
  es: number;
  nes: number;
  p_value: number;
  fdr: number;
  leading_edge_genes: string[];
  leading_edge_size: number;
  hit_genes: string[];
  hit_indices: number[];
  hit_scores: number[];
  running_scores: number[];
  peak_index: number;
}

type GSEAResultState = 'idle' | 'ready' | 'pending' | 'failed';

interface LeadingEdgeGeneRow {
  GeneID: string;
  GeneSymbol?: string;
  GeneDescription?: string;
  logFC?: number;
  logCPM?: number;
  PValue?: number;
  FDR?: number;
}

type LeadingEdgeFilterConfig = Record<string, ColumnFilter>;

interface WorkbenchDetailGSEAProps {
  workbench: Workbench;
  workbenchId: number;
  comparisonName?: string | null;
  toolName?: string | null;
  selectedGenes: Set<string>;
  onSelectionChange: (genes: Set<string>) => void;
  onAnalysisRequest: (type: string) => void;
  showComingSoon: () => void;
  onNavigateToVennDiagram: (genes: string[], targetSetIndex?: number) => void;
  vennSetSummaries?: VennSetSummary[];
}

const getGSEADatabaseStorageKey = (workbenchId: number) => `vizr:gsea:last-db:${workbenchId}`;

const formatComparisonSegment = (value: string) => value.replace(/_/g, ' ').trim();
const formatComparisonLabel = (value?: string | null) => {
  if (!value) return 'Not selected';
  const [left, right] = value.split('_vs_');
  if (!right) {
    return formatComparisonSegment(value);
  }
  return `${formatComparisonSegment(left)} vs ${formatComparisonSegment(right)}`;
};

const stripStarterPhrase = (value?: string | null) => {
  if (!value) return '';
  return value
    .replace(/^Curated starter set for\s*/i, '')
    .replace(/^Curated starter\s*/i, '')
    .replace(/\s+/g, ' ')
    .trim();
};

const formatGeneSetLabel = (value?: string | null) => {
  if (!value) return '';
  return value
    .replace(/_/g, ' ')
    .toLowerCase();
};

const RESULT_TABLE_COLGROUP = (
  <colgroup>
    <col className="w-[42%]" />
    <col className="w-[10%]" />
    <col className="w-[12%]" />
    <col className="w-[14%]" />
    <col className="w-[14%]" />
    <col className="w-[8%]" />
  </colgroup>
);

const formatNumber = (value: number) => {
  if (!Number.isFinite(value)) return 'NA';
  if (Math.abs(value) >= 1000 || (Math.abs(value) > 0 && Math.abs(value) < 0.001)) {
    return value.toExponential(2);
  }
  return value.toFixed(3);
};

const getDirectionLabel = (nes: number) => (nes >= 0 ? 'Positive' : 'Negative');
const getDirectionToken = (nes: number) => (nes >= 0 ? 'UP' : 'DOWN');

const toCsv = (rows: string[][]) =>
  rows.map((row) => row.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(',')).join('\n');

const downloadText = (filename: string, content: string, mimeType: string) => {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
};

const sanitizeFilename = (value: string) =>
  value.replace(/[^a-zA-Z0-9._-]+/g, '_').replace(/^_+|_+$/g, '') || 'gsea_plot';

const escapeXml = (value: string) =>
  value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');

const clamp = (value: number, min: number, max: number) => Math.min(Math.max(value, min), max);

const buildEnrichmentPlotData = (runningScores: number[]) => {
  if (!runningScores.length) {
    return [];
  }

  return runningScores.map((score, idx) => ({
    index: idx + 1,
    score: Number(score.toFixed(6)),
  }));
};

const WorkbenchDetailGSEA: React.FC<WorkbenchDetailGSEAProps> = ({
  workbench,
  workbenchId,
  comparisonName,
  toolName,
  selectedGenes,
  onSelectionChange,
  onAnalysisRequest,
  showComingSoon,
  onNavigateToVennDiagram,
  vennSetSummaries,
}) => {
  const [isWideLayout, setIsWideLayout] = useState(() =>
    typeof window !== 'undefined' ? window.matchMedia('(min-width: 1280px)').matches : false
  );
  const [availableDatabases, setAvailableDatabases] = useState<BuiltInDatabase[]>([]);
  const [selectedDatabaseKey, setSelectedDatabaseKey] = useState('');
  const [isLoadingDatabases, setIsLoadingDatabases] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [validationSummary, setValidationSummary] = useState<ValidationSummary | null>(null);
  const [resultRows, setResultRows] = useState<GSEAResultRow[]>([]);
  const [selectedGeneSetName, setSelectedGeneSetName] = useState<string | null>(null);
  const [selectedGeneSetDetail, setSelectedGeneSetDetail] = useState<GSEAGeneSetDetail | null>(null);
  const [isLoadingGeneSetDetail, setIsLoadingGeneSetDetail] = useState(false);
  const [geneSetDetailError, setGeneSetDetailError] = useState<string | null>(null);
  const [rankingMetric, setRankingMetric] = useState('logFC');
  const [rankingProfile, setRankingProfile] = useState<Array<{ index: number; value: number }>>([]);
  const [zeroCrossIndex, setZeroCrossIndex] = useState<number | null>(null);
  const [resultsSplitRatio, setResultsSplitRatio] = useState(68);
  const [isResizingSplit, setIsResizingSplit] = useState(false);
  const [plotSectionHeight, setPlotSectionHeight] = useState(610);
  const [isResizingPlotSection, setIsResizingPlotSection] = useState(false);
  const [isDatabaseDetailsOpen, setIsDatabaseDetailsOpen] = useState(false);
  const [directionFilter, setDirectionFilter] = useState<'all' | 'up' | 'down'>('all');
  const [resultSearchInput, setResultSearchInput] = useState('');
  const [resultSearchQuery, setResultSearchQuery] = useState('');
  const [resultState, setResultState] = useState<GSEAResultState>('idle');
  const [runningMode, setRunningMode] = useState<'precomputed' | 'fallback' | null>(null);
  const [leadingEdgeSourceRows, setLeadingEdgeSourceRows] = useState<LeadingEdgeGeneRow[]>([]);
  const [leadingEdgeLoading, setLeadingEdgeLoading] = useState(false);
  const [leadingEdgeSearch, setLeadingEdgeSearch] = useState('');
  const [leadingEdgePage, setLeadingEdgePage] = useState(1);
  const [leadingEdgePageSize, setLeadingEdgePageSize] = useState(100);
  const [leadingEdgeFilters, setLeadingEdgeFilters] = useState<LeadingEdgeFilterConfig>({});
  const [leadingEdgeSortBy, setLeadingEdgeSortBy] = useState<string | null>(null);
  const [leadingEdgeSortOrder, setLeadingEdgeSortOrder] = useState<'asc' | 'desc'>('asc');
  const [activeLeadingEdgeFilterColumn, setActiveLeadingEdgeFilterColumn] = useState<string | null>(null);
  const [leadingEdgeTmmData, setLeadingEdgeTmmData] = useState<Record<string, number[]> | null>(null);
  const [leadingEdgeSampleNames, setLeadingEdgeSampleNames] = useState<string[]>([]);
  const [isDownloadingValidationInputs, setIsDownloadingValidationInputs] = useState(false);
  const responseCacheRef = useRef<Map<string, GSEAResponse>>(new Map());
  const plotDetailCacheRef = useRef<Map<string, GSEAGeneSetDetail>>(new Map());
  const degResultCacheRef = useRef<Map<string, LeadingEdgeGeneRow[]>>(new Map());
  const inFlightRequestKeyRef = useRef<string | null>(null);
  const inFlightDetailKeyRef = useRef<string | null>(null);
  const splitContainerRef = useRef<HTMLDivElement | null>(null);
  const plotSplitContainerRef = useRef<HTMLDivElement | null>(null);
  const mainScrollContainerRef = useRef<HTMLDivElement | null>(null);
  const scrollTargetRef = useRef<HTMLElement | Window | null>(null);
  const leadingEdgeSectionRef = useRef<HTMLElement | null>(null);
  const leadingEdgeTableWrapperRef = useRef<HTMLDivElement | null>(null);
  const leadingEdgeTableRef = useRef<HTMLTableElement | null>(null);
  const leadingEdgeTheadRef = useRef<HTMLTableSectionElement | null>(null);
  const searchInputRef = useRef<HTMLTextAreaElement | null>(null);
  const resultSearchInputRef = useRef<HTMLTextAreaElement | null>(null);
  const [showScrollToTopButton, setShowScrollToTopButton] = useState(false);
  const [leadingEdgeOverlayHeader, setLeadingEdgeOverlayHeader] = useState<{
    visible: boolean;
    top: number;
    left: number;
    width: number;
  }>({
    visible: false,
    top: 0,
    left: 0,
    width: 0,
  });

  useEffect(() => {
    const mediaQuery = window.matchMedia('(min-width: 1280px)');
    const updateLayout = () => setIsWideLayout(mediaQuery.matches);

    updateLayout();
    mediaQuery.addEventListener('change', updateLayout);
    return () => mediaQuery.removeEventListener('change', updateLayout);
  }, []);

  useEffect(() => {
    let isMounted = true;

    const loadDatabases = async () => {
      try {
        setIsLoadingDatabases(true);
        setError(null);
        const response = await apiService.fetchBuiltInGSEADatabases(workbenchId);
        if (!isMounted) return;

        setAvailableDatabases(response.databases);
        setSelectedDatabaseKey((current) => {
          if (current && response.databases.some((database) => database.key === current)) {
            return current;
          }

          const savedDatabaseKey = window.sessionStorage.getItem(getGSEADatabaseStorageKey(workbenchId));
          if (
            savedDatabaseKey &&
            response.databases.some((database) => database.key === savedDatabaseKey)
          ) {
            return savedDatabaseKey;
          }

          return response.databases[0]?.key || '';
        });
      } catch (loadError: any) {
        if (!isMounted) return;
        setAvailableDatabases([]);
        setSelectedDatabaseKey('');
        setError(loadError?.message || 'Failed to load built-in GSEA databases');
      } finally {
        if (isMounted) {
          setIsLoadingDatabases(false);
        }
      }
    };

    loadDatabases();
    return () => {
      isMounted = false;
    };
  }, [workbench?.name, workbench?.species, workbenchId]);

  useEffect(() => {
    if (!selectedDatabaseKey) {
      return;
    }

    window.sessionStorage.setItem(getGSEADatabaseStorageKey(workbenchId), selectedDatabaseKey);
  }, [selectedDatabaseKey, workbenchId]);

  useEffect(() => {
    setLeadingEdgeSearch('');
    setLeadingEdgePage(1);
  }, [selectedGeneSetName, comparisonName, toolName]);

  const selectedDatabase = useMemo(
    () => availableDatabases.find((database) => database.key === selectedDatabaseKey) || null,
    [availableDatabases, selectedDatabaseKey]
  );
  const rankedGeneDisplayValue = validationSummary
    ? validationSummary.ranked_gene_count.toLocaleString()
    : '—';
  const testedGeneDisplayValue = validationSummary
    ? validationSummary.tested_gene_sets.toLocaleString()
    : '—';
  const testedSetCaption = validationSummary
    ? 'in current species snapshot'
    : resultState === 'failed'
      ? 'unavailable for failed result'
      : resultState === 'pending' || isRunning
        ? 'waiting for precomputed result'
        : 'not loaded yet';
  const permutationDisplayValue = validationSummary
    ? validationSummary.permutations.toLocaleString()
    : '—';
  const {
    isGOModalOpen,
    goAnalysisResult,
    isGOLoading,
    closeGOModal,
    runGOAnalysis,
    isHeatmapModalOpen,
    openHeatmap,
    closeHeatmap,
    isKEGGModalOpen,
    openKEGG,
    closeKEGG,
  } = useGeneAnalysisActions({
    workbenchId,
    selectedGenes: Array.from(selectedGenes),
    description: `GSEA leading-edge genes (${comparisonName || 'comparison'})`,
  });

  useEffect(() => {
    if (!comparisonName) {
      setLeadingEdgeSourceRows([]);
      return;
    }

    const degCacheKey = `${comparisonName}::${toolName || 'edgeR'}`;
    if (degResultCacheRef.current.has(degCacheKey)) {
      setLeadingEdgeSourceRows(degResultCacheRef.current.get(degCacheKey) || []);
      return;
    }

    let isMounted = true;

    const loadLeadingEdgeSourceRows = async () => {
      try {
        setLeadingEdgeLoading(true);
        const params = new URLSearchParams({
          tool_name: toolName || 'edgeR',
          page: '1',
          limit: '50000',
          filter_type: 'all',
          data_type: 'matrix',
        });
        const response = await fetch(
          `/api/workbenches/${workbenchId}/deg/results/${comparisonName}?${params.toString()}`,
          { credentials: 'include' }
        );
        if (!response.ok) {
          throw new Error('Failed to load DEG results for leading-edge genes');
        }

        const payload = await response.json();
        if (!isMounted) return;

        const rows = Array.isArray(payload?.data) ? payload.data : [];
        degResultCacheRef.current.set(degCacheKey, rows);
        setLeadingEdgeSourceRows(rows);
      } catch {
        if (!isMounted) return;
        setLeadingEdgeSourceRows([]);
      } finally {
        if (isMounted) {
          setLeadingEdgeLoading(false);
        }
      }
    };

    loadLeadingEdgeSourceRows();
    return () => {
      isMounted = false;
    };
  }, [comparisonName, toolName, workbenchId]);

  const requestKey = useMemo(() => {
    if (!comparisonName || !selectedDatabaseKey) return '';
    return `${comparisonName}::${toolName || 'edgeR'}::${selectedDatabaseKey}`;
  }, [comparisonName, selectedDatabaseKey, toolName]);

  const applyReadyResponse = (response: GSEAResponse) => {
    setValidationSummary(response.validation);
    setResultRows(response.rows);
    setSelectedGeneSetName(response.rows[0]?.gene_set || null);
    setSelectedGeneSetDetail(null);
    setGeneSetDetailError(null);
    setRankingMetric(response.ranking_metric);
    setZeroCrossIndex(response.zero_cross_index);
    setRankingProfile([]);
    setResultState('ready');
    setError(null);
  };

  useEffect(() => {
    if (!comparisonName || !selectedDatabaseKey) {
      setValidationSummary(null);
      setResultRows([]);
      setSelectedGeneSetName(null);
      setSelectedGeneSetDetail(null);
      setGeneSetDetailError(null);
      setRankingProfile([]);
      setZeroCrossIndex(null);
      setResultState('idle');
      setRunningMode(null);
      return;
    }

    if (responseCacheRef.current.has(requestKey)) {
      const cached = responseCacheRef.current.get(requestKey)!;
      applyReadyResponse(cached);
      return;
    }

    if (inFlightRequestKeyRef.current === requestKey) {
      return;
    }

    let isMounted = true;

    const runAutomaticGSEA = async () => {
      try {
        inFlightRequestKeyRef.current = requestKey;
        setIsRunning(true);
        setRunningMode('precomputed');
        setError(null);
        setResultState('idle');
        setValidationSummary(null);
        setResultRows([]);
        setSelectedGeneSetName(null);
        setSelectedGeneSetDetail(null);
        setGeneSetDetailError(null);
        setRankingProfile([]);
        setZeroCrossIndex(null);

        const response = await apiService.fetchPrecomputedGSEAResult(workbenchId, {
          comparison_name: comparisonName,
          deg_tool: toolName || 'edgeR',
          gene_set_db: selectedDatabaseKey,
        });

        if (!isMounted) return;

        if (response.state === 'ready' && response.rows && response.validation) {
          const readyResponse = response as GSEAResponse;
          responseCacheRef.current.set(requestKey, readyResponse);
          applyReadyResponse(readyResponse);
          return;
        }

        if (response.state === 'pending') {
          setResultState('pending');
          setError(null);
          return;
        }

        if (response.state === 'failed') {
          setResultState('failed');
          setError(response.error_message || 'Precomputed GSEA generation failed');
          return;
        }

        setRunningMode('fallback');
        const fallbackResponse = await apiService.runComparisonGSEA(workbenchId, {
          comparison_name: comparisonName,
          deg_tool: toolName || 'edgeR',
          gene_set_db: selectedDatabaseKey,
        });

        if (!isMounted) return;

        responseCacheRef.current.set(requestKey, fallbackResponse);
        applyReadyResponse(fallbackResponse);
      } catch (runError: any) {
        if (!isMounted) return;
        setValidationSummary(null);
        setResultRows([]);
        setSelectedGeneSetName(null);
        setSelectedGeneSetDetail(null);
        setGeneSetDetailError(null);
        setRankingProfile([]);
        setZeroCrossIndex(null);
        setResultState('failed');
        setError(runError?.message || 'Failed to run GSEA');
      } finally {
        if (isMounted) {
          setIsRunning(false);
          setRunningMode(null);
        }
        if (inFlightRequestKeyRef.current === requestKey) {
          inFlightRequestKeyRef.current = null;
        }
      }
    };

    runAutomaticGSEA();
    return () => {
      isMounted = false;
    };
  }, [availableDatabases.length, comparisonName, requestKey, selectedDatabaseKey, toolName, workbenchId]);

  useEffect(() => {
    if (!isResizingSplit) {
      document.body.style.removeProperty('cursor');
      document.body.style.removeProperty('user-select');
      return;
    }

    const handlePointerMove = (event: MouseEvent) => {
      if (!splitContainerRef.current) return;

      const rect = splitContainerRef.current.getBoundingClientRect();
      if (rect.width <= 0) return;

      const minLeftPx = 560;
      const minRightPx = 360;
      const maxLeft = Math.max(minLeftPx, rect.width - minRightPx);
      const fallbackLeft = rect.width * 0.68;
      const clampedLeft = Math.min(Math.max(event.clientX - rect.left, minLeftPx), maxLeft > minLeftPx ? maxLeft : fallbackLeft);
      const nextRatio = (clampedLeft / rect.width) * 100;
      setResultsSplitRatio(Math.min(80, Math.max(45, nextRatio)));
    };

    const handlePointerUp = () => setIsResizingSplit(false);

    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    window.addEventListener('mousemove', handlePointerMove);
    window.addEventListener('mouseup', handlePointerUp);

    return () => {
      document.body.style.removeProperty('cursor');
      document.body.style.removeProperty('user-select');
      window.removeEventListener('mousemove', handlePointerMove);
      window.removeEventListener('mouseup', handlePointerUp);
    };
  }, [isResizingSplit]);

  useEffect(() => {
    if (!isResizingPlotSection) {
      document.body.style.removeProperty('cursor');
      document.body.style.removeProperty('user-select');
      return;
    }

    const handlePointerMove = (event: MouseEvent) => {
      if (!plotSplitContainerRef.current) return;

      const rect = plotSplitContainerRef.current.getBoundingClientRect();
      if (rect.height <= 0) return;

      const minTop = 480;
      const minBottom = 220;
      const maxTop = Math.max(minTop, rect.height - minBottom);
      const fallbackTop = 610;
      const clampedTop = Math.min(
        Math.max(event.clientY - rect.top, minTop),
        maxTop > minTop ? maxTop : fallbackTop
      );
      setPlotSectionHeight(clampedTop);
    };

    const handlePointerUp = () => setIsResizingPlotSection(false);

    document.body.style.cursor = 'row-resize';
    document.body.style.userSelect = 'none';
    window.addEventListener('mousemove', handlePointerMove);
    window.addEventListener('mouseup', handlePointerUp);

    return () => {
      document.body.style.removeProperty('cursor');
      document.body.style.removeProperty('user-select');
      window.removeEventListener('mousemove', handlePointerMove);
      window.removeEventListener('mouseup', handlePointerUp);
    };
  }, [isResizingPlotSection]);

  useEffect(() => {
    const container = mainScrollContainerRef.current;
    if (!container) {
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

    const scrollTarget = findScrollParent(container) ?? window;
    scrollTargetRef.current = scrollTarget;

    const readMetrics = () => {
      if (scrollTarget === window) {
        const doc = document.documentElement;
        const body = document.body;
        const scrollTop = window.scrollY || doc.scrollTop || body.scrollTop || 0;
        const clientHeight = window.innerHeight || doc.clientHeight || 0;
        const scrollHeight = Math.max(
          body.scrollHeight,
          doc.scrollHeight,
          body.offsetHeight,
          doc.offsetHeight,
          body.clientHeight,
          doc.clientHeight
        );
        return { scrollTop, clientHeight, scrollHeight, targetType: 'window' as const };
      }

      return {
        scrollTop: scrollTarget.scrollTop,
        clientHeight: scrollTarget.clientHeight,
        scrollHeight: scrollTarget.scrollHeight,
        targetType: 'element' as const,
      };
    };

    const updateVisibility = () => {
      const { scrollTop, clientHeight } = readMetrics();
      const threshold = Math.max(1800, Math.min(3600, clientHeight * 1.8));
      const nextVisible = scrollTop > threshold;
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
  }, [comparisonName, selectedDatabaseKey, resultRows.length, selectedGeneSetName]);

  useEffect(() => {
    const section = leadingEdgeSectionRef.current;
    const table = leadingEdgeTableRef.current;
    const thead = leadingEdgeTheadRef.current;

    if (!section || !table || !thead || !selectedGeneSetDetail?.leading_edge_genes?.length) {
      setLeadingEdgeOverlayHeader((current) => (current.visible ? { visible: false, top: 0, left: 0, width: 0 } : current));
      return;
    }

    const findActualScrollParent = (node: HTMLElement | null): HTMLElement | Window => {
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

    const scrollParent = findActualScrollParent(section);

    const updateOverlay = () => {
      const sectionRect = section.getBoundingClientRect();
      const tableRect = table.getBoundingClientRect();
      const theadRect = thead.getBoundingClientRect();
      const headerHeight = theadRect.height || 40;
      const containerTop = scrollParent === window
        ? 0
        : (scrollParent as HTMLElement).getBoundingClientRect().top;
      const containerBottom = scrollParent === window
        ? window.innerHeight
        : (scrollParent as HTMLElement).getBoundingClientRect().bottom;
      const shouldShow =
        tableRect.top <= containerTop &&
        sectionRect.bottom > containerTop + headerHeight + 8 &&
        tableRect.bottom > containerTop + headerHeight + 8;

      setLeadingEdgeOverlayHeader({
        visible: shouldShow,
        top: containerTop,
        left: tableRect.left,
        width: tableRect.width,
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
  }, [comparisonName, selectedDatabaseKey, selectedGeneSetDetail, leadingEdgePage, leadingEdgePageSize]);

  const filteredRows = useMemo(() => {
    const lineTerms = resultSearchQuery
      .toLowerCase()
      .split(/\r?\n/)
      .map((line) =>
        line
          .split(/[\s,\t,]+/)
          .map((term) => term.trim())
          .filter(Boolean)
      )
      .filter((terms) => terms.length > 0);

    const directionFiltered = (() => {
      if (directionFilter === 'up') {
        return resultRows.filter((row) => row.nes >= 0);
      }
      if (directionFilter === 'down') {
        return resultRows.filter((row) => row.nes < 0);
      }
      return resultRows;
    })();

    if (!lineTerms.length) {
      return directionFiltered;
    }

    return directionFiltered.filter((row) => {
      const geneSet = row.gene_set.toLowerCase();
      const description = (row.description || '').toLowerCase();
      const geneSetId = (row.gene_set_id || '').toLowerCase();
      return lineTerms.some((terms) =>
        terms.every((term) =>
          geneSet.includes(term) ||
          description.includes(term) ||
          geneSetId.includes(term)
        )
      );
    });
  }, [directionFilter, resultRows, resultSearchQuery]);

  useEffect(() => {
    if (filteredRows.length > 0 && !selectedGeneSetName) {
      setSelectedGeneSetName(filteredRows[0].gene_set);
      return;
    }
    if (selectedGeneSetName && !filteredRows.some((row) => row.gene_set === selectedGeneSetName)) {
      setSelectedGeneSetName(filteredRows[0]?.gene_set || null);
    }
  }, [filteredRows, selectedGeneSetName]);

  const selectedRow = useMemo(
    () => filteredRows.find((row) => row.gene_set === selectedGeneSetName) || filteredRows[0] || null,
    [filteredRows, selectedGeneSetName]
  );

  const selectedDetailRequestKey = useMemo(() => {
    if (!requestKey || !selectedRow?.gene_set) {
      return '';
    }
    return `${requestKey}::${selectedRow.gene_set}`;
  }, [requestKey, selectedRow]);

  useEffect(() => {
    if (!comparisonName || !selectedDatabaseKey || !selectedRow?.gene_set) {
      setIsLoadingGeneSetDetail(false);
      setSelectedGeneSetDetail(null);
      setGeneSetDetailError(null);
      setRankingProfile([]);
      return;
    }

    if (plotDetailCacheRef.current.has(selectedDetailRequestKey)) {
      const cachedDetail = plotDetailCacheRef.current.get(selectedDetailRequestKey)!;
      setIsLoadingGeneSetDetail(false);
      setSelectedGeneSetDetail(cachedDetail);
      setRankingMetric(cachedDetail.ranking_metric);
      setRankingProfile(cachedDetail.ranking_profile);
      setZeroCrossIndex(cachedDetail.zero_cross_index);
      setGeneSetDetailError(null);
      return;
    }

    let isMounted = true;
    const abortController = new AbortController();

    const loadGeneSetDetail = async () => {
      try {
        inFlightDetailKeyRef.current = selectedDetailRequestKey;
        setIsLoadingGeneSetDetail(true);
        setSelectedGeneSetDetail(null);
        setGeneSetDetailError(null);
        const detail = await apiService.fetchGSEAPlotDetail(workbenchId, {
          comparison_name: comparisonName,
          deg_tool: toolName || 'edgeR',
          gene_set_db: selectedDatabaseKey,
          gene_set: selectedRow.gene_set,
        }, abortController.signal);
        if (!isMounted || inFlightDetailKeyRef.current !== selectedDetailRequestKey) {
          return;
        }
        plotDetailCacheRef.current.set(selectedDetailRequestKey, detail);
        setSelectedGeneSetDetail(detail);
        setRankingMetric(detail.ranking_metric);
        setRankingProfile(detail.ranking_profile);
        setZeroCrossIndex(detail.zero_cross_index);
      } catch (detailError: any) {
        if (!isMounted || abortController.signal.aborted) {
          return;
        }
        setSelectedGeneSetDetail(null);
        setRankingProfile([]);
        setGeneSetDetailError(detailError?.message || 'Failed to load enrichment plot details');
      } finally {
        if (isMounted && inFlightDetailKeyRef.current === selectedDetailRequestKey) {
          setIsLoadingGeneSetDetail(false);
        }
      }
    };

    loadGeneSetDetail();
    return () => {
      isMounted = false;
      abortController.abort();
      if (inFlightDetailKeyRef.current === selectedDetailRequestKey) {
        inFlightDetailKeyRef.current = null;
      }
    };
  }, [comparisonName, selectedDatabaseKey, selectedDetailRequestKey, selectedRow, toolName, workbenchId]);

  const leadingEdgeRows = useMemo(() => {
    if (!selectedGeneSetDetail?.leading_edge_genes?.length) {
      return [];
    }

    const leadingEdgeSet = new Set(selectedGeneSetDetail.leading_edge_genes);
    return leadingEdgeSourceRows.filter((row) => leadingEdgeSet.has(row.GeneID));
  }, [leadingEdgeSourceRows, selectedGeneSetDetail]);

  const searchedLeadingEdgeRows = useMemo(() => {
    const query = leadingEdgeSearch.trim().toLowerCase();
    if (!query) {
      return leadingEdgeRows;
    }

    const terms = query
      .split(/[\s,\t\r\n]+/)
      .map((term) => term.trim())
      .filter(Boolean);

    return leadingEdgeRows.filter((row) => {
      const geneId = row.GeneID?.toLowerCase() || '';
      const geneSymbol = row.GeneSymbol?.toLowerCase() || '';
      return terms.some((term) => geneId.includes(term) || geneSymbol.includes(term));
    });
  }, [leadingEdgeRows, leadingEdgeSearch]);

  const filteredLeadingEdgeRows = useMemo(() => {
    const passesFilter = (value: number | undefined, filter?: ColumnFilter) => {
      if (!filter) {
        return true;
      }

      if (value === undefined || value === null || !Number.isFinite(value)) {
        return false;
      }

      const filterValue = Number(filter.value);
      if (!Number.isFinite(filterValue)) {
        return true;
      }

      switch (filter.operator) {
        case 'gt':
          return value > filterValue;
        case 'gte':
          return value >= filterValue;
        case 'lt':
          return value < filterValue;
        case 'lte':
          return value <= filterValue;
        case 'eq':
          return value === filterValue;
        default:
          return true;
      }
    };

    const nextRows = searchedLeadingEdgeRows.filter((row) =>
      passesFilter(row.logFC, leadingEdgeFilters.logFC) &&
      passesFilter(row.logCPM, leadingEdgeFilters.logCPM) &&
      passesFilter(row.PValue, leadingEdgeFilters.PValue) &&
      passesFilter(row.FDR, leadingEdgeFilters.FDR)
    );

    if (!leadingEdgeSortBy) {
      return nextRows;
    }

    return [...nextRows].sort((left, right) => {
      const leftValue = Number(left[leadingEdgeSortBy as keyof LeadingEdgeGeneRow] ?? Number.NaN);
      const rightValue = Number(right[leadingEdgeSortBy as keyof LeadingEdgeGeneRow] ?? Number.NaN);

      if (!Number.isFinite(leftValue) && !Number.isFinite(rightValue)) {
        return 0;
      }
      if (!Number.isFinite(leftValue)) {
        return 1;
      }
      if (!Number.isFinite(rightValue)) {
        return -1;
      }

      return leadingEdgeSortOrder === 'asc' ? leftValue - rightValue : rightValue - leftValue;
    });
  }, [leadingEdgeFilters, leadingEdgeSortBy, leadingEdgeSortOrder, searchedLeadingEdgeRows]);

  const leadingEdgeTotalPages = Math.max(1, Math.ceil(filteredLeadingEdgeRows.length / leadingEdgePageSize));
  const pagedLeadingEdgeRows = useMemo(() => {
    const safePage = Math.min(leadingEdgePage, leadingEdgeTotalPages);
    const start = (safePage - 1) * leadingEdgePageSize;
    return filteredLeadingEdgeRows.slice(start, start + leadingEdgePageSize);
  }, [filteredLeadingEdgeRows, leadingEdgePage, leadingEdgePageSize, leadingEdgeTotalPages]);

  const leadingEdgePaginationItems = useMemo(() => {
    const totalPages = leadingEdgeTotalPages;
    const currentPage = leadingEdgePage;
    const pages: (number | string)[] = [];

    if (totalPages <= 3) {
      for (let page = 1; page <= totalPages; page += 1) {
        pages.push(page);
      }
      return pages;
    }

    if (currentPage <= 2) {
      for (let page = 1; page <= Math.min(3, totalPages); page += 1) {
        pages.push(page);
      }
      pages.push('...');
      pages.push(totalPages);
      return pages;
    }

    if (currentPage >= totalPages - 1) {
      pages.push(1);
      pages.push('...');
      for (let page = Math.max(totalPages - 2, 2); page <= totalPages; page += 1) {
        pages.push(page);
      }
      return pages;
    }

    pages.push(1);
    pages.push('...');
    pages.push(currentPage - 1);
    pages.push(currentPage);
    pages.push(currentPage + 1);
    pages.push('...');
    pages.push(totalPages);
    return pages;
  }, [leadingEdgePage, leadingEdgeTotalPages]);

  useEffect(() => {
    if (!comparisonName || !toolName || leadingEdgeRows.length === 0) {
      setLeadingEdgeTmmData(null);
      setLeadingEdgeSampleNames([]);
      return;
    }

    let isMounted = true;
    const geneIds = leadingEdgeRows.map((row) => row.GeneID);

    const loadLeadingEdgeTmm = async () => {
      try {
        const response = await apiService.fetchTMMCountsByGenes(
          workbenchId,
          geneIds,
          comparisonName,
          toolName
        );
        if (!isMounted || !response.success) {
          return;
        }
        setLeadingEdgeTmmData(response.data || null);
        setLeadingEdgeSampleNames(response.sample_names || []);
      } catch {
        if (isMounted) {
          setLeadingEdgeTmmData(null);
          setLeadingEdgeSampleNames([]);
        }
      }
    };

    loadLeadingEdgeTmm();
    return () => {
      isMounted = false;
    };
  }, [comparisonName, leadingEdgeRows, toolName, workbenchId]);

  const plotData = useMemo(
    () => (selectedGeneSetDetail ? buildEnrichmentPlotData(selectedGeneSetDetail.running_scores) : []),
    [selectedGeneSetDetail]
  );

  useEffect(() => {
    if (leadingEdgePage > leadingEdgeTotalPages) {
      setLeadingEdgePage(leadingEdgeTotalPages);
    }
  }, [leadingEdgePage, leadingEdgeTotalPages]);

  const hitRugData = useMemo(
    () => selectedGeneSetDetail?.hit_indices.map((index) => ({ index: index + 1 })) || [],
    [selectedGeneSetDetail]
  );
  const comparisonDisplayLabel = formatComparisonLabel(comparisonName);
  const [positiveLabelRaw, negativeLabelRaw] = comparisonName ? comparisonName.split('_vs_') : ['', ''];
  const positivelyCorrelatedLabel = positiveLabelRaw ? formatComparisonSegment(positiveLabelRaw) : 'Positive';
  const negativelyCorrelatedLabel = negativeLabelRaw ? formatComparisonSegment(negativeLabelRaw) : 'Negative';

  const hasComparisonContext = Boolean(comparisonName);
  const runningLabel =
    runningMode === 'fallback'
      ? `Generating the missing GSEA result for ${comparisonDisplayLabel} using ${selectedDatabase?.label || selectedDatabaseKey || 'the selected database'}...`
      : `Loading precomputed GSEA result for ${comparisonDisplayLabel} using ${selectedDatabase?.label || selectedDatabaseKey || 'the selected database'}...`;
  const noResultsMessage = !hasComparisonContext
    ? 'Select a DEG comparison to populate GSEA results.'
    : resultState === 'pending'
      ? 'GSEA precomputation is still in progress for the current comparison and database.'
      : resultState === 'failed'
        ? 'The stored GSEA result could not be loaded for the current selection.'
        : `No ${directionFilter === 'all' ? '' : directionFilter === 'up' ? 'positive ' : 'negative '}GSEA results are available for the current selection.`;
  const plotPlaceholderMessage = !hasComparisonContext
    ? 'Select a DEG comparison to view the enrichment plot.'
    : resultState === 'pending'
      ? 'The enrichment plot will appear automatically once precomputation finishes.'
      : resultState === 'failed'
        ? 'The enrichment plot is unavailable because the stored GSEA result failed.'
        : 'No enrichment plot available.';
  const leadingEdgePlaceholderMessage = !hasComparisonContext
    ? 'Select a DEG comparison to inspect leading-edge genes.'
    : resultState === 'pending'
      ? 'Leading-edge genes will appear automatically once precomputed results are ready.'
      : resultState === 'failed'
        ? 'Leading-edge genes are unavailable because the stored GSEA result failed.'
        : 'No leading-edge genes available.';
  const topSectionHeight = Math.max(520, plotSectionHeight);
  const plotChartHeight = Math.max(300, topSectionHeight - 190);
  const resultsTableHeight = Math.max(280, topSectionHeight - 138);
  const resultsPaneStyle = isWideLayout
    ? ({
        width: `${resultsSplitRatio}%`,
        flexBasis: `${resultsSplitRatio}%`,
        flexShrink: 0,
      } as React.CSSProperties)
    : undefined;

  const handleDownloadResults = () => {
    const metadataRows = [
      ['Metadata', 'Value'],
      ['Workbench', workbench?.name || String(workbenchId)],
      ['Comparison', comparisonName || ''],
      ['DEG Tool', toolName || 'edgeR'],
      ['Ranking Metric', rankingMetric],
      ['Gene Set DB', selectedDatabase?.label || selectedDatabaseKey],
      ['', ''],
    ];
    const dataRows = [
      ['Gene Set', 'Description', 'Size', 'NES', 'Nominal p-value', 'FDR q-value', 'Direction', 'Leading-edge count'],
      ...resultRows.map((row) => [
        row.gene_set,
        row.description,
        String(row.gene_set_size),
        String(row.nes),
        String(row.p_value),
        String(row.fdr),
        getDirectionLabel(row.nes),
        String(row.leading_edge_size),
      ]),
    ];
    downloadText(
      `gsea_results_${comparisonName || 'comparison'}_${selectedDatabaseKey || 'db'}.csv`,
      toCsv([...metadataRows, ...dataRows]),
      'text/csv;charset=utf-8;'
    );
  };

  const handleDownloadLeadingEdgeTable = () => {
    if (!leadingEdgeRows.length) {
      return;
    }

    const rows = [
      ['Gene ID', 'Gene Symbol', 'logFC', 'logCPM', 'PValue', 'FDR'],
      ...leadingEdgeRows.map((row) => [
        row.GeneID,
        row.GeneSymbol || '',
        row.logFC ?? '',
        row.logCPM ?? '',
        row.PValue ?? '',
        row.FDR ?? '',
      ]),
    ];

    downloadText(
      `leading_edge_genes_${sanitizeFilename(selectedRow?.gene_set || 'gene_set')}_${sanitizeFilename(comparisonName || 'comparison')}.csv`,
      toCsv(rows),
      'text/csv;charset=utf-8'
    );
  };

  const handleLeadingEdgeSearch = () => {
    setLeadingEdgePage(1);
  };

  const handleLeadingEdgeFilterApply = (
    columnName: string,
    filter: ColumnFilter | null,
    sort: 'asc' | 'desc' | null
  ) => {
    setLeadingEdgeFilters((current) => {
      const next = { ...current };
      if (filter) {
        next[columnName] = filter;
      } else {
        delete next[columnName];
      }
      return next;
    });

    if (sort) {
      setLeadingEdgeSortBy(columnName);
      setLeadingEdgeSortOrder(sort);
    } else if (leadingEdgeSortBy === columnName) {
      setLeadingEdgeSortBy(null);
      setLeadingEdgeSortOrder('asc');
    }

    setActiveLeadingEdgeFilterColumn(null);
    setLeadingEdgePage(1);
  };

  const handleResultSearch = () => {
    setResultSearchQuery(resultSearchInput);
    resultSearchInputRef.current?.blur();
  };

  const handleClearResultSearch = () => {
    setResultSearchInput('');
    setResultSearchQuery('');
    resultSearchInputRef.current?.focus();
  };

  const handleLeadingEdgeClearSearch = () => {
    setLeadingEdgeSearch('');
    setLeadingEdgePage(1);
  };

  const handleScrollToTop = () => {
    const target = scrollTargetRef.current;
    if (target && target !== window) {
      target.scrollTo({ top: 0, behavior: 'smooth' });
      return;
    }

    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleSelectLeadingEdgeGene = (geneId: string) => {
    const next = new Set(selectedGenes);
    if (next.has(geneId)) {
      next.delete(geneId);
    } else {
      next.add(geneId);
    }
    onSelectionChange(next);
  };

  const leadingEdgePageGeneIds = useMemo(
    () => pagedLeadingEdgeRows.map((row) => row.GeneID),
    [pagedLeadingEdgeRows]
  );

  const selectedOnPageCount = useMemo(
    () => leadingEdgePageGeneIds.filter((geneId) => selectedGenes.has(geneId)).length,
    [leadingEdgePageGeneIds, selectedGenes]
  );

  const selectedInSearchCount = useMemo(
    () => filteredLeadingEdgeRows.filter((row) => selectedGenes.has(row.GeneID)).length,
    [filteredLeadingEdgeRows, selectedGenes]
  );

  const leadingEdgeSelectAllState: 0 | 1 | 2 =
    selectedOnPageCount === 0
      ? 0
      : selectedInSearchCount === filteredLeadingEdgeRows.length && filteredLeadingEdgeRows.length > 0
        ? 2
        : 1;

  const handleLeadingEdgeSelectAllCycle = () => {
    if (!filteredLeadingEdgeRows.length) {
      return;
    }

    const next = new Set(selectedGenes);
    if (leadingEdgeSelectAllState === 0) {
      leadingEdgePageGeneIds.forEach((geneId) => next.add(geneId));
    } else if (leadingEdgeSelectAllState === 1) {
      filteredLeadingEdgeRows.forEach((row) => next.add(row.GeneID));
    } else {
      filteredLeadingEdgeRows.forEach((row) => next.delete(row.GeneID));
    }
    onSelectionChange(next);
  };

  const leadingEdgeColumnWidths = {
    select: 44,
    geneId: 132,
    geneSymbol: 132,
    pattern: 180,
    metric: 112,
  } as const;

  const leadingEdgeStickyOffsets = {
    geneId: leadingEdgeColumnWidths.select,
    geneSymbol: leadingEdgeColumnWidths.select + leadingEdgeColumnWidths.geneId,
  } as const;

  const leadingEdgeColGroup = (
    <colgroup>
      <col style={{ width: `${leadingEdgeColumnWidths.select}px` }} />
      <col style={{ width: `${leadingEdgeColumnWidths.geneId}px` }} />
      <col style={{ width: `${leadingEdgeColumnWidths.geneSymbol}px` }} />
      <col style={{ width: `${leadingEdgeColumnWidths.pattern}px` }} />
      <col style={{ width: `${leadingEdgeColumnWidths.metric}px` }} />
      <col style={{ width: `${leadingEdgeColumnWidths.metric}px` }} />
      <col style={{ width: `${leadingEdgeColumnWidths.metric}px` }} />
      <col style={{ width: `${leadingEdgeColumnWidths.metric}px` }} />
    </colgroup>
  );

  const leadingEdgeHeaderRow = (
    <tr>
      <th
        className="p-2 text-left text-xs font-bold uppercase tracking-wider text-slate-600"
        style={{
          width: leadingEdgeColumnWidths.select,
          backgroundColor: 'rgb(248 250 252)',
          boxShadow: '2px 0 4px rgba(0,0,0,0.05)'
        }}
      >
        <button
          type="button"
          onClick={handleLeadingEdgeSelectAllCycle}
          className="flex h-5 w-5 items-center justify-center rounded focus:outline-none focus:ring-2 focus:ring-blue-400"
          title={
            leadingEdgeSelectAllState === 0
              ? `Select current page (${pagedLeadingEdgeRows.length} genes)`
              : leadingEdgeSelectAllState === 1
                ? `Select all ${filteredLeadingEdgeRows.length.toLocaleString()} searched genes`
                : `Deselect ${filteredLeadingEdgeRows.length.toLocaleString()} searched genes`
          }
        >
          {leadingEdgeSelectAllState === 0 && (
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <rect x="1" y="1" width="14" height="14" rx="2" stroke="#9CA3AF" strokeWidth="1.5" />
            </svg>
          )}
          {leadingEdgeSelectAllState === 1 && (
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <rect x="1" y="1" width="14" height="14" rx="2" stroke="#3B82F6" strokeWidth="1.5" />
              <path d="M4 8.5l2.5 2.5 5-5.5" stroke="#3B82F6" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          )}
          {leadingEdgeSelectAllState === 2 && (
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <rect x="1" y="1" width="14" height="14" rx="2" fill="#1D4ED8" stroke="#1D4ED8" strokeWidth="1.5" />
              <path d="M4 8.5l2.5 2.5 5-5.5" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          )}
        </button>
      </th>
      <th className="px-3 py-2 text-left text-xs font-bold uppercase tracking-wider text-slate-600" style={{ width: `${leadingEdgeColumnWidths.geneId}px`, minWidth: `${leadingEdgeColumnWidths.geneId}px`, backgroundColor: 'rgb(248 250 252)' }}>
        Gene ID
      </th>
      <th className="px-3 py-2 text-left text-xs font-bold uppercase tracking-wider text-slate-600" style={{ width: `${leadingEdgeColumnWidths.geneSymbol}px`, minWidth: `${leadingEdgeColumnWidths.geneSymbol}px`, backgroundColor: 'rgb(248 250 252)' }}>
        Gene Symbol
      </th>
      <th className="px-3 py-2 text-left text-xs font-bold uppercase tracking-wider text-slate-600" style={{ width: `${leadingEdgeColumnWidths.pattern}px`, minWidth: `${leadingEdgeColumnWidths.pattern}px`, backgroundColor: 'rgb(248 250 252)' }}>
        Expression Pattern
      </th>
      {['logFC', 'logCPM', 'PValue', 'FDR'].map((column) => {
        const hasFilter = !!leadingEdgeFilters[column];
        const hasSort = leadingEdgeSortBy === column;
        const isActive = hasFilter || hasSort;

        return (
          <th
            key={column}
            className="px-3 py-2 text-right text-xs font-bold uppercase tracking-wider text-slate-600"
            style={{ width: `${leadingEdgeColumnWidths.metric}px`, minWidth: `${leadingEdgeColumnWidths.metric}px`, backgroundColor: 'rgb(248 250 252)' }}
          >
            <div className="relative flex items-center justify-end gap-1">
              <span>{column}</span>
              {hasSort && (
                <span className="font-bold text-blue-600">
                  {leadingEdgeSortOrder === 'asc' ? '↑' : '↓'}
                </span>
              )}
              <div className="relative">
                <button
                  type="button"
                  onClick={() => setActiveLeadingEdgeFilterColumn(column)}
                  className={`rounded p-1 transition-colors ${
                    isActive ? 'bg-blue-50 text-blue-600' : 'text-slate-400 hover:bg-slate-100'
                  }`}
                  title={`Filter ${column}`}
                >
                  <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.5 6h9.75M10.5 6a1.5 1.5 0 11-3 0m3 0a1.5 1.5 0 10-3 0M3.75 6H7.5m3 12h9.75m-9.75 0a1.5 1.5 0 01-3 0m3 0a1.5 1.5 0 00-3 0m-3.75 0H7.5m9-6h3.75m-3.75 0a1.5 1.5 0 01-3 0m3 0a1.5 1.5 0 00-3 0m-9.75 0h9.75" />
                  </svg>
                </button>
                {hasFilter && (
                  <span className="absolute -right-1 -top-1 flex h-2 w-2">
                    <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-blue-400 opacity-75"></span>
                    <span className="relative inline-flex h-2 w-2 rounded-full bg-blue-500"></span>
                  </span>
                )}
                {activeLeadingEdgeFilterColumn === column && (
                  <ColumnFilterPopup
                    isOpen={true}
                    onClose={() => setActiveLeadingEdgeFilterColumn(null)}
                    columnName={column}
                    currentFilter={leadingEdgeFilters[column]}
                    currentSort={leadingEdgeSortBy === column ? leadingEdgeSortOrder : undefined}
                    onApply={(filter, sort) => handleLeadingEdgeFilterApply(column, filter, sort)}
                  />
                )}
              </div>
            </div>
          </th>
        );
      })}
    </tr>
  );

  const handleSelectGeneSet = (geneSetName: string) => {
    setSelectedGeneSetName(geneSetName);
    if (selectedGenes.size > 0) {
      onSelectionChange(new Set());
    }
  };

  const handleDownloadLeadingEdge = () => {
    if (!selectedRow || !selectedGeneSetDetail?.leading_edge_genes?.length) {
      return;
    }
    const metadataRows = [
      ['Metadata', 'Value'],
      ['Workbench', workbench?.name || String(workbenchId)],
      ['Comparison', comparisonName || ''],
      ['DEG Tool', toolName || 'edgeR'],
      ['Ranking Metric', rankingMetric],
      ['Gene Set DB', selectedDatabase?.label || selectedDatabaseKey],
      ['', ''],
    ];
    const dataRows = [
      ['Gene Set', 'Leading-edge genes'],
      [selectedRow.gene_set, selectedGeneSetDetail.leading_edge_genes.join(';')],
    ];
    downloadText(
      `gsea_leading_edge_${sanitizeFilename(selectedRow.gene_set)}_${comparisonName || 'comparison'}_${selectedDatabaseKey || 'db'}.csv`,
      toCsv([...metadataRows, ...dataRows]),
      'text/csv;charset=utf-8;'
    );
  };

  const handleDownloadValidationInputs = async () => {
    if (!comparisonName || !selectedDatabaseKey) {
      return;
    }

    try {
      setIsDownloadingValidationInputs(true);
      const payload = await apiService.fetchGSEAValidationInputs(workbenchId, {
        comparison_name: comparisonName,
        deg_tool: toolName || 'edgeR',
        gene_set_db: selectedDatabaseKey,
      });

      downloadText(payload.ranked_filename, payload.ranked_list_text, 'text/plain;charset=utf-8');
      downloadText(payload.gmt_filename, payload.gmt_text, 'text/plain;charset=utf-8');
      downloadText(payload.readme_filename, payload.readme_text, 'text/plain;charset=utf-8');
    } catch (downloadError: any) {
      alert(downloadError?.message || 'Failed to download GSEA validation inputs');
    } finally {
      setIsDownloadingValidationInputs(false);
    }
  };

  const handleDownloadPlot = () => {
    if (!selectedRow || !selectedGeneSetDetail || plotData.length === 0 || rankingProfile.length === 0) {
      return;
    }

    const width = 1400;
    const height = 1040;
    const margin = { top: 36, right: 34, bottom: 96, left: 110 };
    const plotWidth = width - margin.left - margin.right;
    const topHeight = 360;
    const hitsHeight = 120;
    const bottomHeight = 250;
    const legendY = height - 34;
    const topY = margin.top;
    const hitsY = topY + topHeight + 16;
    const bottomY = hitsY + hitsHeight + 24;
    const maxRank = Math.max(rankingProfile.length, 1);
    const xScale = (index: number) => margin.left + ((index - 1) / Math.max(maxRank - 1, 1)) * plotWidth;

    const topScores = plotData.map((point) => point.score);
    const topMin = Math.min(...topScores, 0);
    const topMax = Math.max(...topScores, 0);
    const topRange = topMax - topMin || 1;
    const yScaleTop = (value: number) => topY + topHeight - ((value - topMin) / topRange) * topHeight;
    const topTicks = Array.from({ length: 6 }, (_, idx) => topMin + (topRange / 5) * idx);

    const bottomValues = rankingProfile.map((point) => point.value);
    const bottomAbsMax = Math.max(...bottomValues.map((value) => Math.abs(value)), 1);
    const yScaleBottom = (value: number) =>
      bottomY + bottomHeight / 2 - (value / (bottomAbsMax || 1)) * ((bottomHeight / 2) * 0.88);
    const zeroY = yScaleBottom(0);

    const linePath = plotData
      .map((point, index) => `${index === 0 ? 'M' : 'L'} ${xScale(point.index).toFixed(2)} ${yScaleTop(point.score).toFixed(2)}`)
      .join(' ');

    const areaPathPoints = rankingProfile
      .map((point, index) => `${index === 0 ? 'M' : 'L'} ${xScale(point.index).toFixed(2)} ${yScaleBottom(point.value).toFixed(2)}`)
      .join(' ');
    const areaPath = `${areaPathPoints} L ${xScale(rankingProfile[rankingProfile.length - 1].index).toFixed(2)} ${zeroY.toFixed(2)} L ${xScale(rankingProfile[0].index).toFixed(2)} ${zeroY.toFixed(2)} Z`;

    const topGrid = topTicks
      .map((tick) => {
        const y = yScaleTop(tick);
        return `
          <line x1="${margin.left}" y1="${y.toFixed(2)}" x2="${width - margin.right}" y2="${y.toFixed(2)}" stroke="#94a3b8" stroke-width="1" stroke-dasharray="3 8" opacity="0.65" />
          <text x="${margin.left - 12}" y="${(y + 4).toFixed(2)}" text-anchor="end" font-size="12" fill="#64748b">${tick.toFixed(2)}</text>
        `;
      })
      .join('');

    const xTicks = [1, 5000, 10000, 15000, maxRank]
      .filter((tick, idx, arr) => tick <= maxRank && arr.indexOf(tick) === idx)
      .map((tick) => {
        const x = xScale(tick);
        return `
          <line x1="${x.toFixed(2)}" y1="${topY}" x2="${x.toFixed(2)}" y2="${bottomY + bottomHeight}" stroke="#94a3b8" stroke-width="1" stroke-dasharray="3 8" opacity="0.45" />
          <text x="${x.toFixed(2)}" y="${(bottomY + bottomHeight + 22).toFixed(2)}" text-anchor="middle" font-size="12" fill="#64748b">${tick}</text>
        `;
      })
      .join('');

    const hitLines = hitRugData
      .map((point) => {
        const x = xScale(point.index);
        return `<line x1="${x.toFixed(2)}" y1="${(hitsY + 8).toFixed(2)}" x2="${x.toFixed(2)}" y2="${(hitsY + 68).toFixed(2)}" stroke="#111827" stroke-width="1.4" />`;
      })
      .join('');

    const zeroCrossLine =
      zeroCrossIndex && zeroCrossIndex > 0
        ? `
          <line x1="${xScale(clamp(zeroCrossIndex, 1, maxRank)).toFixed(2)}" y1="${bottomY}" x2="${xScale(clamp(zeroCrossIndex, 1, maxRank)).toFixed(2)}" y2="${(bottomY + bottomHeight).toFixed(2)}" stroke="#111827" stroke-width="1.5" stroke-dasharray="6 6" />
          <text x="${(xScale(clamp(zeroCrossIndex, 1, maxRank)) + 8).toFixed(2)}" y="${(zeroY - 8).toFixed(2)}" font-size="12" fill="#475569">Zero cross at ${zeroCrossIndex}</text>
        `
        : '';

    const svg = `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
  <defs>
    <linearGradient id="gseaHitsGradient" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#f87171" />
      <stop offset="50%" stop-color="#fce7f3" />
      <stop offset="100%" stop-color="#4338ca" />
    </linearGradient>
  </defs>
  <rect x="0" y="0" width="${width}" height="${height}" fill="#ffffff" />
  <text x="${width / 2}" y="28" text-anchor="middle" font-size="22" font-weight="700" fill="#0f172a">Enrichment plot: ${escapeXml(selectedRow.gene_set)}</text>

  ${xTicks}
  ${topGrid}
  <line x1="${margin.left}" y1="${yScaleTop(0).toFixed(2)}" x2="${width - margin.right}" y2="${yScaleTop(0).toFixed(2)}" stroke="#111827" stroke-width="1.4" />
  <path d="${linePath}" fill="none" stroke="#39d353" stroke-width="5" stroke-linecap="round" stroke-linejoin="round" />
  <text x="30" y="${topY + topHeight / 2}" text-anchor="middle" transform="rotate(-90 30 ${topY + topHeight / 2})" font-size="15" font-weight="700" fill="#111827">Enrichment score (ES)</text>

  <rect x="${margin.left}" y="${hitsY}" width="${plotWidth}" height="${hitsHeight}" fill="#ffffff" stroke="#cbd5e1" stroke-width="1" />
  <rect x="${margin.left}" y="${hitsY + 74}" width="${plotWidth}" height="26" fill="url(#gseaHitsGradient)" />
  ${hitLines}
  <text x="${margin.left + 12}" y="${hitsY + 92}" font-size="12" font-weight="600" fill="#b91c1c">'${escapeXml(positivelyCorrelatedLabel)}' (positively correlated)</text>
  <text x="${width - margin.right - 12}" y="${hitsY + 92}" text-anchor="end" font-size="12" font-weight="600" fill="#4338ca">'${escapeXml(negativelyCorrelatedLabel)}' (negatively correlated)</text>
  <text x="30" y="${hitsY + hitsHeight / 2}" text-anchor="middle" transform="rotate(-90 30 ${hitsY + hitsHeight / 2})" font-size="15" font-weight="700" fill="#111827">Hits</text>

  <rect x="${margin.left}" y="${bottomY}" width="${plotWidth}" height="${bottomHeight}" fill="#ffffff" />
  <line x1="${margin.left}" y1="${zeroY.toFixed(2)}" x2="${width - margin.right}" y2="${zeroY.toFixed(2)}" stroke="#94a3b8" stroke-width="1.5" stroke-dasharray="4 6" />
  ${zeroCrossLine}
  <path d="${areaPath}" fill="#cbd5e1" stroke="#cbd5e1" stroke-width="1.2" opacity="1" />
  <text x="30" y="${bottomY + bottomHeight / 2}" text-anchor="middle" transform="rotate(-90 30 ${bottomY + bottomHeight / 2})" font-size="15" font-weight="700" fill="#111827">Ranked list metric (${escapeXml(rankingMetric)})</text>
  <text x="${width / 2}" y="${bottomY + bottomHeight + 48}" text-anchor="middle" font-size="15" fill="#111827">Rank in ordered dataset</text>

  <line x1="${margin.left}" y1="${legendY}" x2="${margin.left + 26}" y2="${legendY}" stroke="#39d353" stroke-width="3" />
  <text x="${margin.left + 38}" y="${legendY + 4}" font-size="13" fill="#475569">Enrichment profile</text>
  <line x1="${margin.left + 228}" y1="${legendY - 10}" x2="${margin.left + 228}" y2="${legendY + 10}" stroke="#111827" stroke-width="1.4" />
  <text x="${margin.left + 242}" y="${legendY + 4}" font-size="13" fill="#475569">Hits</text>
  <rect x="${margin.left + 330}" y="${legendY - 9}" width="24" height="18" fill="#cbd5e1" />
  <text x="${margin.left + 366}" y="${legendY + 4}" font-size="13" fill="#475569">Ranking metric scores</text>
</svg>`;

    downloadText(
      `${sanitizeFilename(selectedRow.gene_set)}_${sanitizeFilename(comparisonName || 'comparison')}_gsea_plot.svg`,
      svg,
      'image/svg+xml;charset=utf-8;'
    );
  };

  return (
    <div className="min-h-full bg-slate-50 font-sans text-slate-900">
      <div className="flex h-full min-h-[760px] flex-col overflow-hidden rounded-lg border border-slate-200 bg-slate-50 shadow-sm">
        <header className="z-10 flex flex-shrink-0 items-center justify-between border-b border-slate-200 bg-white px-6 py-4 shadow-sm">
          <div>
            <div className="flex items-center space-x-3">
              <div className="rounded-lg bg-indigo-100 p-2">
                <svg className="h-5 w-5 text-indigo-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13h4l3-8 4 14 3-6h2" />
                </svg>
              </div>
              <h1 className="text-xl font-bold tracking-tight text-slate-800">Gene Set Enrichment Analysis (GSEA)</h1>
            </div>
            <p className="ml-11 mt-1 text-sm text-slate-500">
              Automated preranked GSEA based on the current DEG comparison. Interpreting pathway-level biological programs.
            </p>
          </div>
        </header>

          <main className="flex flex-1 overflow-hidden">
            <section className="relative flex min-w-0 flex-1 flex-col bg-slate-50/50">
            <div ref={mainScrollContainerRef} className="flex-1 p-6">
              <div className="grid gap-8">
                <div className="grid gap-6 border-b border-slate-200 bg-white px-6 py-6">
                  <div>
                    <h2 className="mb-2 flex items-center text-sm font-bold uppercase tracking-wider text-slate-800">
                      <svg className="mr-2 h-4 w-4 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11.25 3.75h1.5m-7.5 4.5h13.5M6.75 8.25v10.5m10.5-10.5v10.5M9.75 12h4.5m-4.5 3h4.5" />
                      </svg>
                      Analysis Setup
                    </h2>
                    <p className="max-w-3xl text-sm text-slate-500">
                      GSEA runs automatically on the selected DEG comparison. No manual ranked list upload is required.
                    </p>
                  </div>

                  <div className="grid gap-8 xl:grid-cols-[380px_minmax(0,1fr)] xl:items-start">
                    <div className="space-y-5 xl:pr-6 xl:border-r xl:border-slate-200">
                    <section>
                      <label className="mb-2 block text-sm font-semibold text-slate-700">Gene Set Database</label>
                      <div className="relative">
                        <select
                          value={selectedDatabaseKey}
                          onChange={(event) => setSelectedDatabaseKey(event.target.value)}
                          disabled={isLoadingDatabases || availableDatabases.length === 0}
                          className="w-full appearance-none rounded-lg border border-slate-300 bg-white py-2.5 pl-4 pr-10 text-sm font-medium text-slate-700 shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:cursor-not-allowed disabled:bg-slate-50 disabled:text-slate-400"
                        >
                          {availableDatabases.length === 0 ? (
                            <option value="">No built-in database available</option>
                          ) : (
                            availableDatabases.map((database) => (
                              <option key={database.key} value={database.key}>
                                {database.label}
                              </option>
                            ))
                          )}
                        </select>
                        <svg className="pointer-events-none absolute right-3 top-3 h-4 w-4 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                        </svg>
                      </div>
                    </section>

                    {selectedDatabase && (
                      <section className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                        <div className="mb-2 flex items-start">
                          <svg className="mr-2 mt-0.5 h-4 w-4 text-indigo-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7a2 2 0 012-2h12a2 2 0 012 2M4 7v10a2 2 0 002 2h12a2 2 0 002-2V7M4 7l8 5 8-5" />
                          </svg>
                          <h3 className="text-sm font-bold text-slate-800">{selectedDatabase.label}</h3>
                        </div>
                        <p className="mb-3 text-xs leading-relaxed text-slate-600">{stripStarterPhrase(selectedDatabase.description)}</p>
                        <div className="flex items-center justify-between text-xs">
                          <span className="text-slate-500">ID Namespace:</span>
                          <span className="rounded bg-slate-200 px-2 py-0.5 font-mono font-medium text-slate-700">
                            {selectedDatabase.id_namespace}
                          </span>
                        </div>
                        <button
                          type="button"
                          onClick={() => setIsDatabaseDetailsOpen((current) => !current)}
                          className="mt-3 inline-flex items-center text-xs font-medium text-indigo-600 hover:text-indigo-700"
                        >
                          <svg className="mr-1.5 h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M12 21a9 9 0 100-18 9 9 0 000 18z" />
                          </svg>
                          {isDatabaseDetailsOpen ? 'Hide database details' : 'View database details'}
                        </button>
                        {isDatabaseDetailsOpen && (
                          <div className="mt-3 rounded-lg border border-slate-200 bg-white p-3 text-xs text-slate-600">
                            <div className="grid gap-2">
                              <div className="grid grid-cols-[96px_minmax(0,1fr)] gap-2">
                                <span className="font-semibold text-slate-500">Source</span>
                                <span>{selectedDatabase.source || 'Built-in VizR GSEA snapshot'}</span>
                              </div>
                              <div className="grid grid-cols-[96px_minmax(0,1fr)] gap-2">
                                <span className="font-semibold text-slate-500">Species</span>
                                <span>{selectedDatabase.species}</span>
                              </div>
                              <div className="grid grid-cols-[96px_minmax(0,1fr)] gap-2">
                                <span className="font-semibold text-slate-500">Generated</span>
                                <span>{selectedDatabase.generation_date}</span>
                              </div>
                              <div className="grid grid-cols-[96px_minmax(0,1fr)] gap-2">
                                <span className="font-semibold text-slate-500">ID namespace</span>
                                <span>{selectedDatabase.id_namespace}</span>
                              </div>
                              <div className="grid grid-cols-[96px_minmax(0,1fr)] gap-2">
                                <span className="font-semibold text-slate-500">Usage note</span>
                                <span>Species-specific built-in snapshot used for automatic GSEA in VizR.</span>
                              </div>
                            </div>
                          </div>
                        )}
                      </section>
                    )}
                  </div>

                  <div className="xl:px-2 xl:pt-1">
                    <div>
                      <h3 className="mb-4 text-sm font-bold uppercase tracking-wider text-slate-500">Automatic Source</h3>
                      <div className="grid gap-3 text-sm">
                        <div className="grid grid-cols-[140px_minmax(0,1fr)] items-start gap-3">
                          <span className="text-slate-500">Comparison</span>
                          <span className="break-all font-medium text-slate-800">{comparisonDisplayLabel}</span>
                        </div>
                        <div className="grid grid-cols-[140px_minmax(0,1fr)] items-start gap-3">
                          <span className="text-slate-500">DEG Tool</span>
                          <span className="font-medium text-slate-800">{toolName || 'edgeR'}</span>
                        </div>
                        <div className="grid grid-cols-[140px_minmax(0,1fr)] items-start gap-3">
                          <span className="text-slate-500">Ranking Metric</span>
                          <span className="font-medium text-slate-800">{rankingMetric}</span>
                        </div>
                        <div className="grid grid-cols-[140px_minmax(0,1fr)] items-start gap-3">
                          <span className="text-slate-500">Permutations</span>
                          <span className="font-medium text-slate-800">{permutationDisplayValue}</span>
                        </div>
                      </div>
                    </div>

                      <div className="grid grid-cols-2 gap-3">
                      <div className="rounded-lg border border-slate-200 bg-white p-3 text-center shadow-sm">
                        <p className="mb-1 text-2xl font-bold text-indigo-600">
                          {rankedGeneDisplayValue}
                        </p>
                        <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Ranked Genes</p>
                      </div>
                      <div
                        className="rounded-lg border border-slate-200 bg-white p-3 text-center shadow-sm"
                        title="Gene sets with sufficient overlap under the current built-in species snapshot"
                      >
                        <p className="mb-1 text-2xl font-bold text-emerald-600">
                          {testedGeneDisplayValue}
                        </p>
                        <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Tested Sets</p>
                        <p className="mt-1 text-[10px] text-slate-400">{testedSetCaption}</p>
                      </div>
                    </div>
                  </div>

                    {!hasComparisonContext && (
                      <div className="xl:col-span-2 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
                        Select a DEG comparison from the left panel to run GSEA.
                      </div>
                    )}

                    {error && (
                      <div className="xl:col-span-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                        {error}
                      </div>
                    )}
                  </div>
                </div>

                <div ref={plotSplitContainerRef} className="flex flex-col">
                  <div
                    ref={splitContainerRef}
                    className="flex min-h-[620px] flex-col gap-6 xl:flex-row xl:gap-0"
                  >
                  <div className="flex min-w-0 flex-col" style={{ ...resultsPaneStyle, ...(isWideLayout ? { height: `${topSectionHeight}px` } : {}) }}>
                    <div className="mb-5 flex items-start justify-between">
                      <div>
                        <h2 className="flex items-center text-lg font-bold text-slate-800">
                          <svg className="mr-2 h-5 w-5 text-indigo-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                          </svg>
                          Enrichment Results
                        </h2>
                        <p className="mt-1 max-w-2xl text-sm text-slate-500">
                          Review Normalized Enrichment Score (NES), nominal p-value, and FDR q-value. Select a row to view the enrichment plot and leading-edge genes.
                        </p>
                        {isRunning && (
                          <div className="mt-3 inline-flex items-center rounded-full border border-indigo-200 bg-indigo-50 px-3 py-1.5 text-sm font-medium text-indigo-700">
                            <span className="mr-2 inline-block h-4 w-4 animate-spin rounded-full border-2 border-indigo-300 border-t-indigo-600" />
                            GSEA is running
                          </div>
                        )}
                        {!isRunning && resultState === 'pending' && (
                          <div className="mt-3 inline-flex items-center rounded-full border border-amber-200 bg-amber-50 px-3 py-1.5 text-sm font-medium text-amber-700">
                            <span className="mr-2 inline-block h-2.5 w-2.5 rounded-full bg-amber-500" />
                            Waiting for precomputed GSEA results
                          </div>
                        )}
                        {!isRunning && resultState === 'failed' && (
                          <div className="mt-3 inline-flex items-center rounded-full border border-rose-200 bg-rose-50 px-3 py-1.5 text-sm font-medium text-rose-700">
                            <span className="mr-2 inline-block h-2.5 w-2.5 rounded-full bg-rose-500" />
                            Stored GSEA result failed
                          </div>
                        )}
                        {!isRunning && resultRows.length > 0 && (
                          <div className="mt-3 inline-flex rounded-full border border-slate-200 bg-white p-1 text-xs font-medium text-slate-600">
                            {(['all', 'up', 'down'] as const).map((filter) => (
                              <button
                                key={filter}
                                type="button"
                                onClick={() => setDirectionFilter(filter)}
                                className={`rounded-full px-3 py-1 transition-colors ${
                                  directionFilter === filter
                                    ? 'bg-indigo-600 text-white shadow-sm'
                                    : 'text-slate-600 hover:bg-slate-100'
                                }`}
                              >
                                {filter === 'all' ? 'All' : filter === 'up' ? 'Up' : 'Down'}
                              </button>
                            ))}
                          </div>
                        )}
                        {!isRunning && resultRows.length > 0 && (
                          <div className="mt-4 flex flex-wrap items-center gap-3">
                            <div className="relative">
                              <textarea
                                ref={resultSearchInputRef}
                                value={resultSearchInput}
                                onChange={(event) => setResultSearchInput(event.target.value)}
                                onKeyDown={(event) => {
                                  if (event.key === 'Enter' && event.ctrlKey) {
                                    handleResultSearch();
                                  }
                                }}
                                placeholder="Search gene sets, descriptions, or GO IDs (comma, space, tab, or newline separated)..."
                                className="min-h-[40px] max-h-[180px] w-[360px] resize-y rounded-lg border border-slate-300 py-2 pl-10 pr-4 text-sm text-slate-700 placeholder:text-slate-400 focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-100"
                                rows={1}
                              />
                              {resultSearchInput && (
                                <button
                                  type="button"
                                  onClick={handleClearResultSearch}
                                  className="absolute right-2 top-2 inline-flex h-7 w-7 items-center justify-center rounded-md text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600"
                                  aria-label="Clear result search"
                                  title="Clear"
                                >
                                  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
                                  </svg>
                                </button>
                              )}
                              <div className="pointer-events-none absolute left-0 top-2.5 flex items-center pl-3">
                                <svg className="h-5 w-5 text-slate-400" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                                </svg>
                              </div>
                            </div>
                            <button
                              type="button"
                              onClick={handleResultSearch}
                              className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
                            >
                              Search
                            </button>
                          </div>
                        )}
                      </div>
                      <div className="flex flex-wrap gap-3">
                        <button
                          type="button"
                          onClick={handleDownloadValidationInputs}
                          disabled={!comparisonName || !selectedDatabaseKey || isDownloadingValidationInputs}
                          className="flex items-center rounded-lg border border-amber-300 bg-amber-50 px-4 py-2 text-sm font-medium text-amber-700 shadow-sm transition-colors hover:bg-amber-100 disabled:cursor-not-allowed disabled:opacity-50"
                          title="Temporary helper: download the exact ranked list and GMT used by VizR for external validation"
                        >
                          <svg className="mr-2 h-4 w-4 text-amber-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v12m0 0l-4-4m4 4l4-4M4 20h16" />
                          </svg>
                          {isDownloadingValidationInputs ? 'Preparing Inputs...' : 'Validation Inputs'}
                        </button>
                        <button
                          type="button"
                          onClick={handleDownloadResults}
                          disabled={resultRows.length === 0}
                          className="flex items-center rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 shadow-sm transition-colors hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          <svg className="mr-2 h-4 w-4 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a2 2 0 002 2h12a2 2 0 002-2v-1M12 4v12m0 0l-4-4m4 4l4-4" />
                          </svg>
                          Results
                        </button>
                        <button
                          type="button"
                          onClick={handleDownloadLeadingEdge}
                          disabled={!selectedGeneSetDetail?.leading_edge_genes?.length}
                          className="flex items-center rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 shadow-sm transition-colors hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          <svg className="mr-2 h-4 w-4 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a2 2 0 002 2h12a2 2 0 002-2v-1M12 4v12m0 0l-4-4m4 4l4-4" />
                          </svg>
                          Leading Edge
                        </button>
                      </div>
                    </div>

                  <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
                  <table className="w-full table-fixed text-left text-sm">
                    {RESULT_TABLE_COLGROUP}
                    <thead className="sticky top-0 z-10 border-b border-slate-200 bg-slate-50 text-slate-600">
                      <tr>
                        <th className="px-5 py-3.5 font-semibold">Gene Set</th>
                        <th className="px-5 py-3.5 text-right font-semibold">Size</th>
                        <th className="px-5 py-3.5 text-right font-semibold">NES</th>
                        <th className="px-5 py-3.5 text-right font-semibold">NOM p-val</th>
                        <th className="px-5 py-3.5 text-right font-semibold">FDR q-val</th>
                        <th className="px-5 py-3.5 text-center font-semibold">Direction</th>
                      </tr>
                    </thead>
                  </table>
                  <div className="overflow-auto" style={{ maxHeight: `${resultsTableHeight}px` }}>
                    <table className="w-full table-fixed text-left text-sm">
                      {RESULT_TABLE_COLGROUP}
                      <tbody className="divide-y divide-slate-100">
                        {isRunning ? (
                          <tr>
                            <td colSpan={6} className="px-5 py-14">
                              <div className="flex flex-col items-center justify-center text-center">
                                <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-indigo-50">
                                  <span className="inline-block h-8 w-8 animate-spin rounded-full border-[3px] border-indigo-200 border-t-indigo-600" />
                                </div>
                                <p className="text-base font-semibold text-slate-700">Running GSEA analysis</p>
                                <p className="mt-2 max-w-lg text-sm leading-relaxed text-slate-500">
                                  {runningLabel}
                                </p>
                                <p className="mt-1 text-xs uppercase tracking-wider text-slate-400">
                                  Preparing ranked genes, testing gene sets, and computing enrichment scores
                                </p>
                              </div>
                            </td>
                          </tr>
                        ) : filteredRows.length === 0 ? (
                          <tr>
                            <td colSpan={6} className="px-5 py-8 text-center text-slate-500">
                              {noResultsMessage}
                            </td>
                          </tr>
                        ) : (
                          filteredRows.map((row) => {
                            const isSelected = selectedRow?.gene_set === row.gene_set;
                            const isUp = row.nes >= 0;
                            const formattedGeneSet = formatGeneSetLabel(row.gene_set);
                            const normalizedDescription = stripStarterPhrase(row.description || '').trim();
                            const showRawGeneSet = Boolean(row.gene_set) && formattedGeneSet !== normalizedDescription.toLowerCase();
                            const normalizedGeneSetId = (row.gene_set_id || '').trim().toLowerCase();
                            const normalizedGeneSetName = (row.gene_set || '').trim().toLowerCase();
                            const showGeneSetId = Boolean(row.gene_set_id) && normalizedGeneSetId !== normalizedGeneSetName;

                            return (
                              <tr
                                key={row.gene_set}
                                onClick={() => handleSelectGeneSet(row.gene_set)}
                                className={`group cursor-pointer border-l-4 transition-colors ${
                                  isSelected
                                    ? 'border-l-indigo-500 bg-indigo-50/60'
                                    : 'border-l-transparent hover:bg-slate-50'
                                }`}
                              >
                                <td className="px-5 py-4 align-top">
                                  <div
                                    className={`whitespace-normal break-words font-bold ${isSelected ? 'text-indigo-700' : 'text-slate-800 group-hover:text-indigo-600'}`}
                                    title={row.description || row.gene_set}
                                  >
                                    {stripStarterPhrase(row.description) || 'No description'}
                                  </div>
                                  {showRawGeneSet && (
                                    <div className="mt-1 whitespace-normal break-words text-xs text-slate-500 line-clamp-2" title={row.gene_set}>
                                      {row.gene_set}
                                    </div>
                                  )}
                                  {showGeneSetId && (
                                    <div className="mt-1 font-mono text-[11px] text-slate-400">
                                      {row.gene_set_id}
                                    </div>
                                  )}
                                </td>
                                <td className="px-5 py-4 text-right align-top font-medium text-slate-600">{row.gene_set_size}</td>
                                <td className="px-5 py-4 text-right align-top font-mono font-medium text-slate-800">{formatNumber(row.nes)}</td>
                                <td className="px-5 py-4 text-right align-top font-mono text-slate-600">{formatNumber(row.p_value)}</td>
                                <td className="px-5 py-4 text-right align-top font-mono font-semibold text-slate-800">{formatNumber(row.fdr)}</td>
                                <td className="px-5 py-4 text-center align-top">
                                  <span className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-bold ${
                                    isUp ? 'bg-emerald-100 text-emerald-700' : 'bg-rose-100 text-rose-700'
                                  }`}>
                                    <svg className="mr-1 h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                      {isUp ? (
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 17L17 7m0 0H9m8 0v8" />
                                      ) : (
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 7l10 10m0 0H9m8 0V9" />
                                      )}
                                    </svg>
                                    {getDirectionToken(row.nes)}
                                  </span>
                                </td>
                              </tr>
                            );
                          })
                        )}
                      </tbody>
                    </table>
                  </div>
                  </div>
                </div>

                  <div
                    role="separator"
                    aria-orientation="vertical"
                    aria-label="Resize GSEA results and plot panels"
                    onMouseDown={() => isWideLayout && setIsResizingSplit(true)}
                    className={`relative hidden xl:flex xl:w-5 xl:flex-shrink-0 xl:cursor-col-resize xl:items-stretch xl:justify-center ${
                      isResizingSplit ? 'bg-indigo-50' : ''
                    }`}
                  >
                    <div className="absolute inset-y-0 w-px bg-slate-200 transition-colors hover:bg-indigo-300" />
                    <div className="absolute inset-y-0 flex w-5 items-center justify-center">
                      <div className="flex h-10 w-2 flex-col items-center justify-center gap-1 rounded-full border border-slate-200 bg-white shadow-sm">
                        <span className="h-1 w-1 rounded-full bg-slate-400" />
                        <span className="h-1 w-1 rounded-full bg-slate-400" />
                        <span className="h-1 w-1 rounded-full bg-slate-400" />
                      </div>
                    </div>
                  </div>

                  <aside
                    className="flex min-w-0 flex-1 flex-col border-t border-slate-200 bg-white xl:border-l xl:border-t-0"
                    style={isWideLayout ? { height: `${topSectionHeight}px` } : undefined}
                  >
                  <div
                    className="flex h-full flex-col p-6"
                  >
                    <div className="mb-4 flex items-start justify-between gap-4">
                      <h2 className="flex items-center text-sm font-bold uppercase tracking-wider text-slate-800">
                        <svg className="mr-2 h-4 w-4 text-indigo-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 3v18h18M7 14l3-3 3 2 4-6" />
                        </svg>
                        Enrichment Plot
                      </h2>
                        <button
                          type="button"
                          onClick={handleDownloadPlot}
                          disabled={!selectedRow || !selectedGeneSetDetail || plotData.length === 0 || rankingProfile.length === 0}
                        className="inline-flex flex-shrink-0 items-center rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 shadow-sm transition-colors hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        <svg className="mr-1.5 h-4 w-4 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a2 2 0 002 2h12a2 2 0 002-2v-1M12 4v12m0 0l-4-4m4 4l4-4" />
                        </svg>
                        Download Plot
                      </button>
                    </div>

                    <div className="mb-4">
                      <h3 className="break-words text-base font-bold leading-tight text-slate-800">
                        {selectedRow ? formatGeneSetLabel(selectedRow.gene_set) : 'Select a gene set'}
                      </h3>
                      {selectedRow ? (
                        <div className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-5">
                          <div className="flex flex-col">
                            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">NES</span>
                            <span className="font-mono font-bold text-slate-800">{formatNumber(selectedRow.nes)}</span>
                          </div>
                          <div className="flex flex-col">
                            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">FDR</span>
                            <span className="font-mono font-bold text-slate-800">{formatNumber(selectedRow.fdr)}</span>
                          </div>
                          <div className="flex flex-col">
                            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Direction</span>
                            <span className={`text-sm font-bold ${selectedRow.nes >= 0 ? 'text-emerald-600' : 'text-rose-600'}`}>
                              {getDirectionToken(selectedRow.nes)}
                            </span>
                          </div>
                          <div className="flex flex-col">
                            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Size</span>
                            <span className="font-mono font-bold text-slate-800">{selectedRow.gene_set_size}</span>
                          </div>
                          <div className="flex flex-col">
                            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Leading Edge</span>
                            <span className="font-mono font-bold text-slate-800">{selectedRow.leading_edge_size}</span>
                          </div>
                        </div>
                      ) : (
                        <div className="mt-2 text-xs text-slate-500">Select a gene set to inspect enrichment details.</div>
                      )}
                    </div>

                    <div
                      className="w-full rounded-xl border border-slate-200 bg-white p-4"
                      style={{ height: `${plotChartHeight}px` }}
                    >
                      {isRunning || isLoadingGeneSetDetail ? (
                        <div className="flex h-full flex-col items-center justify-center text-center">
                          <span className="mb-4 inline-block h-8 w-8 animate-spin rounded-full border-[3px] border-indigo-200 border-t-indigo-600" />
                          <p className="text-sm font-medium text-slate-700">
                            {isRunning ? 'Generating enrichment plot' : 'Loading enrichment plot'}
                          </p>
                          <p className="mt-1 max-w-xs text-xs leading-relaxed text-slate-500">
                            {isRunning
                              ? 'The selected comparison is being analyzed. The enrichment curve will appear as soon as the top result is ready.'
                              : 'The selected gene set detail is being loaded. The enrichment curve will appear automatically.'}
                          </p>
                        </div>
                      ) : geneSetDetailError ? (
                        <div className="flex h-full items-center justify-center text-sm text-rose-600">
                          {geneSetDetailError}
                        </div>
                      ) : plotData.length > 0 && rankingProfile.length > 0 ? (
                        <div className="flex h-full flex-col">
                          <div className="grid h-[44%] grid-cols-[36px_minmax(0,1fr)]">
                            <div className="flex items-center justify-center">
                              <span className="-rotate-90 whitespace-nowrap text-xs font-semibold text-slate-700">
                                Enrichment score (ES)
                              </span>
                            </div>
                            <ResponsiveContainer width="100%" height="100%">
                              <LineChart data={plotData} margin={{ top: 6, right: 10, left: -12, bottom: 2 }}>
                                <CartesianGrid strokeDasharray="2 6" stroke="#94a3b8" strokeOpacity={0.55} />
                                <XAxis
                                  dataKey="index"
                                  type="number"
                                  hide
                                  domain={[1, rankingProfile.length]}
                                />
                                <YAxis
                                  tick={{ fontSize: 10, fill: '#64748b' }}
                                  axisLine={{ stroke: '#cbd5e1' }}
                                  tickLine={false}
                                  width={34}
                                />
                                <Tooltip
                                  contentStyle={{ borderRadius: '8px', border: '1px solid #e2e8f0', fontSize: '12px', fontWeight: 'bold' }}
                                  labelFormatter={(value) => `Rank position ${value}`}
                                  formatter={(value: number) => [formatNumber(value), 'Enrichment Score']}
                                />
                                <ReferenceLine y={0} stroke="#111827" strokeWidth={1} />
                                <Line
                                  type="monotone"
                                  dataKey="score"
                                  stroke="#39d353"
                                  strokeWidth={4}
                                  dot={false}
                                  activeDot={{
                                    r: 5,
                                    fill: '#39d353',
                                    stroke: '#fff',
                                    strokeWidth: 2,
                                  }}
                                  isAnimationActive={false}
                                />
                              </LineChart>
                            </ResponsiveContainer>
                          </div>

                          <div className="grid h-[18%] grid-cols-[36px_minmax(0,1fr)] border-y border-slate-300">
                            <div className="flex items-center justify-center border-r border-slate-300 bg-white">
                              <span className="-rotate-90 whitespace-nowrap text-xs font-semibold text-slate-700">Hits</span>
                            </div>
                            <div className="relative flex flex-col bg-white">
                              <div className="relative h-10">
                                {hitRugData.map((point) => (
                                  <span
                                    key={point.index}
                                    className="absolute bottom-0 top-0 w-px bg-slate-900"
                                    style={{ left: `${((point.index - 1) / Math.max(rankingProfile.length - 1, 1)) * 100}%` }}
                                  />
                                ))}
                              </div>
                              <div className="relative h-5 border-t border-slate-300 bg-gradient-to-r from-red-400 via-pink-100 via-50% to-indigo-700">
                                <span className="absolute left-2 top-0.5 text-[10px] font-semibold text-red-700">
                                  '{positivelyCorrelatedLabel}' (positively correlated)
                                </span>
                                <span className="absolute right-2 top-0.5 text-[10px] font-semibold text-indigo-700">
                                  '{negativelyCorrelatedLabel}' (negatively correlated)
                                </span>
                              </div>
                            </div>
                          </div>

                          <div className="grid h-[38%] grid-cols-[36px_minmax(0,1fr)]">
                            <div className="flex items-center justify-center">
                              <span className="-rotate-90 whitespace-nowrap text-xs font-semibold text-slate-700">
                                Ranked list metric ({rankingMetric})
                              </span>
                            </div>
                            <ResponsiveContainer width="100%" height="100%">
                              <AreaChart data={rankingProfile} margin={{ top: 8, right: 10, left: -12, bottom: 6 }}>
                                <CartesianGrid strokeDasharray="2 6" stroke="#94a3b8" strokeOpacity={0.55} />
                                <XAxis
                                  dataKey="index"
                                  type="number"
                                  domain={[1, rankingProfile.length]}
                                  tick={{ fontSize: 10, fill: '#64748b' }}
                                  axisLine={{ stroke: '#cbd5e1' }}
                                  tickLine={false}
                                  label={{
                                    value: 'Rank in ordered dataset',
                                    position: 'insideBottom',
                                    offset: -2,
                                    fill: '#334155',
                                    fontSize: 11,
                                  }}
                                />
                                <YAxis
                                  tick={{ fontSize: 10, fill: '#64748b' }}
                                  axisLine={{ stroke: '#cbd5e1' }}
                                  tickLine={false}
                                  width={34}
                                />
                                <Tooltip
                                  contentStyle={{ borderRadius: '8px', border: '1px solid #e2e8f0', fontSize: '12px', fontWeight: 'bold' }}
                                  labelFormatter={(value) => `Rank position ${value}`}
                                  formatter={(value: number) => [formatNumber(value), rankingMetric]}
                                />
                                <ReferenceLine y={0} stroke="#94a3b8" strokeDasharray="3 3" />
                                {zeroCrossIndex ? (
                                  <ReferenceLine
                                    x={zeroCrossIndex}
                                    stroke="#111827"
                                    strokeDasharray="5 5"
                                    strokeWidth={1.5}
                                    label={{
                                      value: `Zero cross at ${zeroCrossIndex}`,
                                      fill: '#64748b',
                                      fontSize: 10,
                                      position: 'insideTop',
                                    }}
                                  />
                                ) : null}
                                <Area
                                  type="monotone"
                                  dataKey="value"
                                  stroke="#d1d5db"
                                  fill="#d1d5db"
                                  fillOpacity={1}
                                  isAnimationActive={false}
                                />
                              </AreaChart>
                            </ResponsiveContainer>
                          </div>
                        </div>
                      ) : (
                        <div className="flex h-full items-center justify-center text-sm text-slate-500">
                          {plotPlaceholderMessage}
                        </div>
                      )}
                    </div>
                    <div className="mt-3 flex items-center justify-center gap-6 text-[11px] text-slate-600">
                      <span className="flex items-center gap-2">
                        <span className="h-0.5 w-6 bg-[#39d353]" />
                        Enrichment profile
                      </span>
                      <span className="flex items-center gap-2">
                        <span className="h-4 w-px bg-slate-900" />
                        Hits
                      </span>
                      <span className="flex items-center gap-2">
                        <span className="h-3 w-6 bg-slate-300" />
                        Ranking metric scores
                      </span>
                    </div>
                  </div>
                  </aside>
                </div>

                <div
                  role="separator"
                  aria-orientation="horizontal"
                  aria-label="Resize GSEA top panels and leading-edge panel"
                  onMouseDown={() => setIsResizingPlotSection(true)}
                  className={`relative mt-5 hidden h-5 flex-shrink-0 cursor-row-resize items-center justify-center xl:flex ${
                    isResizingPlotSection ? 'bg-indigo-50' : ''
                  }`}
                >
                  <div className="absolute inset-x-0 h-px bg-slate-200 transition-colors hover:bg-indigo-300" />
                  <div className="absolute inset-x-0 flex items-center justify-center">
                    <div className="flex h-2 w-10 items-center justify-center gap-1 rounded-full border border-slate-200 bg-white shadow-sm">
                      <span className="h-1 w-1 rounded-full bg-slate-400" />
                      <span className="h-1 w-1 rounded-full bg-slate-400" />
                      <span className="h-1 w-1 rounded-full bg-slate-400" />
                    </div>
                  </div>
                </div>

                <section ref={leadingEdgeSectionRef} className="mt-5 bg-slate-50/30 p-6">
                    <div className="mb-4 flex items-center justify-between">
                      <h2 className="flex items-center text-sm font-bold uppercase tracking-wider text-slate-800">
                        <svg className="mr-2 h-4 w-4 text-indigo-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6M7 4h10a2 2 0 012 2v12a2 2 0 01-2 2H7a2 2 0 01-2-2V6a2 2 0 012-2z" />
                        </svg>
                        Leading-Edge Genes
                      </h2>
                      <span className="rounded-full bg-slate-200 px-2 py-0.5 text-xs font-bold text-slate-500">
                        {selectedGeneSetDetail?.leading_edge_genes?.length || 0} Genes
                      </span>
                    </div>

                    <p className="mb-4 text-xs leading-relaxed text-slate-600">
                      The core subset of genes that accounts for the enrichment signal. These are the primary candidates for downstream biological interpretation.
                    </p>

                    {isRunning || isLoadingGeneSetDetail ? (
                      <div className="flex h-32 flex-col items-center justify-center rounded-xl border border-slate-200 bg-white/80 text-center">
                        <span className="mb-3 inline-block h-7 w-7 animate-spin rounded-full border-[3px] border-indigo-200 border-t-indigo-600" />
                        <p className="text-sm font-medium text-slate-700">
                          {isRunning ? 'Collecting leading-edge genes' : 'Loading leading-edge genes'}
                        </p>
                        <p className="mt-1 max-w-xs text-xs text-slate-500">
                          {isRunning
                            ? 'Leading-edge genes will be shown automatically once the enrichment results are available.'
                            : 'Leading-edge genes will be shown automatically once the selected gene set detail is ready.'}
                        </p>
                      </div>
                    ) : geneSetDetailError ? (
                      <div className="text-sm text-rose-600">{geneSetDetailError}</div>
                    ) : selectedGeneSetDetail?.leading_edge_genes?.length ? (
                      <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
                        <div className="flex flex-wrap items-center gap-4 border-b border-slate-200 bg-white px-4 py-3">
                            <div className="relative">
                              <textarea
                                ref={searchInputRef}
                                value={leadingEdgeSearch}
                                onChange={(event) => setLeadingEdgeSearch(event.target.value)}
                                onKeyDown={(event) => {
                                  if (event.key === 'Enter' && event.ctrlKey) {
                                    handleLeadingEdgeSearch();
                                  }
                                }}
                                placeholder="Search Gene IDs or Symbols (comma, space, tab, or newline separated)..."
                                className="min-h-[40px] max-h-[180px] w-64 resize-y rounded-lg border border-slate-300 py-2 pl-10 pr-4 text-sm text-slate-700 placeholder:text-slate-400 focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-100"
                                rows={1}
                              />
                              <div className="pointer-events-none absolute left-0 top-2.5 flex items-center pl-3">
                                <svg className="h-5 w-5 text-slate-400" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                                </svg>
                              </div>
                            </div>
                            <button
                              type="button"
                              onClick={handleLeadingEdgeSearch}
                              className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
                            >
                              Search
                            </button>
                              {leadingEdgeSearch && (
                                <button
                                  type="button"
                                  onClick={handleLeadingEdgeClearSearch}
                                className="rounded-lg bg-slate-200 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-300"
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
                              analyzeButtonClassName="px-4 py-2 text-sm font-semibold bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-slate-300 disabled:cursor-not-allowed flex items-center"
                              toolbarClassName="contents"
                              leftGroupClassName="contents"
                              rightGroupClassName="contents"
                            />
                            <button
                              type="button"
                              onClick={handleDownloadLeadingEdgeTable}
                              className="inline-flex items-center rounded-lg bg-emerald-500 px-4 py-2 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-emerald-600"
                            >
                              <svg className="mr-2 h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a2 2 0 002 2h12a2 2 0 002-2v-1M12 4v12m0 0l-4-4m4 4l4-4" />
                              </svg>
                              Download
                            </button>
                            <div className="ml-auto flex items-center gap-2 text-sm text-slate-600">
                              <span>Rows per page:</span>
                              <select
                                value={leadingEdgePageSize}
                                onChange={(event) => {
                                  setLeadingEdgePageSize(Number(event.target.value));
                                  setLeadingEdgePage(1);
                                }}
                                className="rounded-lg border border-slate-300 px-2 py-1.5 text-sm focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-100"
                              >
                                {[100, 500, 1000, 2000, 5000].map((size) => (
                                  <option key={size} value={size}>
                                    {size}
                                  </option>
                                ))}
                              </select>
                            </div>
                            <div className="text-sm text-slate-600">
                              {filteredLeadingEdgeRows.length === 0
                                ? '0-0'
                                : `${(leadingEdgePage - 1) * leadingEdgePageSize + 1}-${Math.min(
                                    leadingEdgePage * leadingEdgePageSize,
                                    filteredLeadingEdgeRows.length
                                  )}`}{' '}
                              of {filteredLeadingEdgeRows.length.toLocaleString()}
                            </div>
                            <div className="flex items-center gap-2">
                              <button
                                type="button"
                                onClick={() => setLeadingEdgePage((page) => Math.max(1, page - 1))}
                                disabled={leadingEdgePage === 1}
                                className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm disabled:cursor-not-allowed disabled:opacity-50 hover:bg-slate-50"
                              >
                                Previous
                              </button>
                              {leadingEdgePaginationItems.map((page, index) => (
                                typeof page === 'number' ? (
                                  <button
                                    key={`${page}-${index}`}
                                    type="button"
                                    onClick={() => setLeadingEdgePage(page)}
                                    className={`rounded-lg px-3 py-1.5 text-sm transition-colors ${
                                      page === leadingEdgePage
                                        ? 'border border-blue-600 bg-blue-600 text-white'
                                        : 'border border-slate-300 hover:bg-slate-50'
                                    }`}
                                  >
                                    {page}
                                  </button>
                                ) : (
                                  <span key={`ellipsis-${index}`} className="px-2 text-slate-400">
                                    {page}
                                  </span>
                                )
                              ))}
                              <button
                                type="button"
                                onClick={() => setLeadingEdgePage((page) => Math.min(leadingEdgeTotalPages, page + 1))}
                                disabled={leadingEdgePage >= leadingEdgeTotalPages}
                                className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm disabled:cursor-not-allowed disabled:opacity-50 hover:bg-slate-50"
                              >
                                Next
                              </button>
                            </div>
                        </div>

                        <div
                          ref={leadingEdgeTableWrapperRef}
                          className="relative"
                          style={{ height: 'auto', minHeight: 0, maxHeight: 'none', overflow: 'visible', position: 'relative' }}
                        >
                          <table ref={leadingEdgeTableRef} className="data-table" style={{ position: 'relative', width: '100%', tableLayout: 'fixed' }}>
                            {leadingEdgeColGroup}
                            <thead
                              ref={leadingEdgeTheadRef}
                              className="sticky top-0 z-40"
                              style={{
                                position: 'sticky',
                                top: 0,
                                zIndex: 40,
                                backgroundColor: 'rgb(248 250 252)',
                                boxShadow: '0 1px 0 rgba(226,232,240,0.9)'
                              }}
                            >
                              {leadingEdgeHeaderRow}
                            </thead>
                            <tbody className="divide-y divide-slate-100">
                              {leadingEdgeLoading ? (
                                <tr>
                                  <td colSpan={8} className="px-5 py-10 text-center text-slate-500">
                                    Loading DEG metadata for leading-edge genes...
                                  </td>
                                </tr>
                              ) : pagedLeadingEdgeRows.length === 0 ? (
                                <tr>
                                  <td colSpan={8} className="px-5 py-10 text-center text-slate-500">
                                    No leading-edge genes matched the current search.
                                  </td>
                                </tr>
                              ) : (
                                pagedLeadingEdgeRows.map((row) => (
                                  <tr key={row.GeneID} className="hover:bg-slate-50">
                                    <td
                                      className="px-3 py-2"
                                      style={{
                                        position: 'sticky',
                                        left: 0,
                                        zIndex: 20,
                                        width: leadingEdgeColumnWidths.select,
                                        backgroundColor: 'white',
                                        boxShadow: '2px 0 4px rgba(0,0,0,0.05)'
                                      }}
                                    >
                                      <input
                                        type="checkbox"
                                        className="h-4 w-4 rounded border-slate-300 text-primary focus:ring-primary"
                                        checked={selectedGenes.has(row.GeneID)}
                                        onChange={() => handleSelectLeadingEdgeGene(row.GeneID)}
                                      />
                                    </td>
                                    <td
                                      className="cursor-help px-3 py-2 text-sm font-medium text-slate-900"
                                      style={{
                                        position: 'sticky',
                                        left: leadingEdgeStickyOffsets.geneId,
                                        zIndex: 20,
                                        width: `${leadingEdgeColumnWidths.geneId}px`,
                                        minWidth: `${leadingEdgeColumnWidths.geneId}px`,
                                        backgroundColor: 'white',
                                        boxShadow: '2px 0 4px rgba(0,0,0,0.05)'
                                      }}
                                      title={row.GeneDescription || 'No description available'}
                                    >
                                      {row.GeneID}
                                    </td>
                                    <td
                                      className="px-3 py-2 text-sm text-slate-700"
                                      style={{
                                        position: 'sticky',
                                        left: leadingEdgeStickyOffsets.geneSymbol,
                                        zIndex: 20,
                                        width: `${leadingEdgeColumnWidths.geneSymbol}px`,
                                        minWidth: `${leadingEdgeColumnWidths.geneSymbol}px`,
                                        backgroundColor: 'white',
                                        boxShadow: '2px 0 4px rgba(0,0,0,0.05)'
                                      }}
                                    >
                                      {row.GeneSymbol || '-'}
                                    </td>
                                    <td className="px-3 py-2" style={{ width: `${leadingEdgeColumnWidths.pattern}px` }}>
                                      {leadingEdgeTmmData?.[row.GeneID] && leadingEdgeSampleNames.length > 0 ? (
                                        <MiniHeatmap
                                          values={leadingEdgeTmmData[row.GeneID]}
                                          samples={leadingEdgeSampleNames}
                                          logFC={row.logFC}
                                          width={132}
                                          height={20}
                                        />
                                      ) : (
                                        <span className="text-xs text-slate-400">Not available</span>
                                      )}
                                    </td>
                                    <td className="px-3 py-2 text-right font-mono text-sm text-slate-700" style={{ width: `${leadingEdgeColumnWidths.metric}px` }}>
                                      {row.logFC !== undefined ? formatNumber(row.logFC) : 'NA'}
                                    </td>
                                    <td className="px-3 py-2 text-right font-mono text-sm text-slate-700" style={{ width: `${leadingEdgeColumnWidths.metric}px` }}>
                                      {row.logCPM !== undefined ? formatNumber(row.logCPM) : 'NA'}
                                    </td>
                                    <td className="px-3 py-2 text-right font-mono text-sm text-slate-700" style={{ width: `${leadingEdgeColumnWidths.metric}px` }}>
                                      {row.PValue !== undefined ? formatNumber(row.PValue) : 'NA'}
                                    </td>
                                    <td className="px-3 py-2 text-right font-mono text-sm font-semibold text-slate-800" style={{ width: `${leadingEdgeColumnWidths.metric}px` }}>
                                      {row.FDR !== undefined ? formatNumber(row.FDR) : 'NA'}
                                    </td>
                                  </tr>
                                ))
                              )}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    ) : (
                      <div className="text-sm text-slate-500">{leadingEdgePlaceholderMessage}</div>
                    )}
                </section>
              </div>
            </div>
            </div>
          </section>

          {leadingEdgeOverlayHeader.visible && typeof document !== 'undefined' && createPortal(
            <div
              className="fixed z-[9998]"
              style={{
                top: leadingEdgeOverlayHeader.top,
                left: leadingEdgeOverlayHeader.left,
                width: leadingEdgeOverlayHeader.width,
              }}
            >
              <div className="overflow-hidden rounded-t-xl border border-slate-200 bg-slate-50 shadow-sm">
                <table className="data-table" style={{ width: '100%', tableLayout: 'fixed' }}>
                  {leadingEdgeColGroup}
                  <thead>{leadingEdgeHeaderRow}</thead>
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

          <GOAnalysisModal
            isOpen={isGOModalOpen}
            onClose={closeGOModal}
            result={goAnalysisResult}
            isLoading={isGOLoading}
            workbenchId={workbenchId}
            comparisonName={comparisonName || undefined}
            toolName={toolName || 'edgeR'}
          />

          <HeatmapAnalysisModal
            isOpen={isHeatmapModalOpen}
            onClose={closeHeatmap}
            workbenchId={workbenchId}
            selectedGenes={Array.from(selectedGenes)}
            comparisonName={comparisonName || undefined}
            toolName={toolName || 'edgeR'}
          />

          <KEGGPathwayModal
            isOpen={isKEGGModalOpen}
            onClose={closeKEGG}
            workbenchId={workbenchId}
            selectedGenes={Array.from(selectedGenes)}
            comparisonName={comparisonName || undefined}
            toolName={toolName || 'edgeR'}
          />
        </main>
      </div>
    </div>
  );
};

export default WorkbenchDetailGSEA;
