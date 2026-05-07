import React, { useState, useCallback, useEffect, useLayoutEffect, useRef } from 'react';
import Modal from './Modal';
import FileUpload, { FileUploadRef } from './FileUpload';
import { apiService } from '../services/api';

interface UploadedFile {
  id: number;
  name: string;
  size: number;
  tempFilename: string;
  uploadProgress: number;
  uploadStatus: 'uploading' | 'completed' | 'failed' | 'cancelled';
  error?: string;
}

interface FileMapping {
  uiId: string;
  groupName: string;
  sampleName: string;
  file1: string;
  file2?: string; // For paired-end only
  sourceColumnName?: string;
  sourceWorkbenchId?: number;
  sourceWorkbenchName?: string;
  sourceGroupName?: string;
  sourceSampleName?: string;
  sourceCountTool?: string;
  sourceReferenceSet?: string | null;
  sourceHasTpmMatrix?: boolean;
}

interface NCBIFile {
  run: string;
  library_layout: string;
  sample_name: string;
  size_mb: string;
  bases: string;
  spots: string;
  scientific_name: string;
  platform: string;
  model: string;
}

interface MacrogenFile {
  name: string;
  sample_name: string;
  size_bytes: number;
  size_mb: string;
  md5: string;
  url: string;
  read_num: number;
}

interface ImportWorkbenchSource {
  workbench_id: number;
  workbench_name: string;
  species: string;
  count_tool: string;
  has_tpm_matrix: boolean;
  reference_set: string | null;
  samples: Array<{
    sample_name: string;
    group_name: string;
  }>;
}

interface MatrixValidationResult {
  valid: boolean;
  errors: string[];
  warnings: string[];
  sample_columns: string[];
  sample_count: number;
  gene_count: number;
  has_tpm_matrix: boolean;
}

interface PipelineStep {
  id: string;
  name: string;
  description: string;
  selectedTool: string;
  availableTools: {
    id: string;
    name: string;
    description: string;
    parameters: {
      name: string;
      type: 'text' | 'number' | 'boolean' | 'select';
      default: any;
      options?: string[];
      description: string;
    }[];
  }[];
  toolParameters: { [key: string]: any };
}

const GSEA_DATABASE_OPTIONS = [
  { key: 'go_bp', label: 'GO gene sets' },
  { key: 'kegg', label: 'KEGG gene sets' },
  { key: 'gene_family', label: 'Gene Family based gene sets' },
  { key: 'plantcyc', label: 'PlantCyc gene sets' },
  { key: 'po', label: 'PO gene sets' },
  { key: 'tf', label: 'TFT gene sets' },
  { key: 'mir', label: 'MIR gene sets' },
] as const;

const DEFAULT_GSEA_DATABASES = ['go_bp', 'kegg'];
const VALID_GSEA_DATABASE_KEYS = new Set(GSEA_DATABASE_OPTIONS.map(option => option.key));

function normalizeGSEADatabases(value: unknown): string[] {
  if (!Array.isArray(value)) return [...DEFAULT_GSEA_DATABASES];
  const normalized = value
    .map(item => String(item).trim())
    .filter(item => VALID_GSEA_DATABASE_KEYS.has(item as typeof GSEA_DATABASE_OPTIONS[number]['key']));
  return normalized.length > 0 ? normalized : [...DEFAULT_GSEA_DATABASES];
}

function normalizeGSEAEnabled(value: unknown): boolean {
  return typeof value === 'boolean' ? value : true;
}




interface CreateWorkbenchModalProps {
  isOpen: boolean;
  onClose: () => void;
  showComingSoon: () => void;
  onWorkbenchCreated?: (workbenchId: number) => void;
}

export default function CreateWorkbenchModal({ isOpen, onClose, showComingSoon, onWorkbenchCreated }: CreateWorkbenchModalProps): React.ReactNode {
  const mappingIdRef = useRef(0);
  const createFileMapping = useCallback((partial?: Partial<Omit<FileMapping, 'uiId'>>): FileMapping => {
    mappingIdRef.current += 1;
    return {
      uiId: `mapping-${mappingIdRef.current}`,
      groupName: '',
      sampleName: '',
      file1: '',
      file2: undefined,
      ...partial
    };
  }, []);

  const [currentStep, setCurrentStep] = useState(1);
  const [formData, setFormData] = useState({
    workbenchName: '',
    dataInputMethod: 'local',
    bioprojectId: '',
    species: 'Arabidopsis thaliana',
    referenceGenome: null as File | null,
    referenceSet: 'TAIR10',  // Reference set ?醫뤾문 ?곕떽?
    layout: 'se' as 'se' | 'pe',
    trimmomaticAdapter: 'TruSeq3',
    illuminaclipSeedMismatches: 2,
    illuminaclipPalindromeClip: 30,
    illuminaclipSimpleClip: 10,
    uploadedFiles: [] as UploadedFile[],
    serverFilePaths: ''
  });
  const [matrixCountsFile, setMatrixCountsFile] = useState<UploadedFile | null>(null);
  const [matrixTpmFile, setMatrixTpmFile] = useState<UploadedFile | null>(null);
  const [matrixValidation, setMatrixValidation] = useState<MatrixValidationResult | null>(null);
  const [matrixValidationLoading, setMatrixValidationLoading] = useState(false);
  const [matrixDragTarget, setMatrixDragTarget] = useState<'counts' | 'tpm' | null>(null);

  // Real-time validation states
  const [nameValidation, setNameValidation] = useState<{
    available: boolean;
    message: string;
    checking: boolean;
  }>({ available: true, message: '', checking: false });
  const [invalidNameHint, setInvalidNameHint] = useState('');

  const nameValidationTimeout = useRef<NodeJS.Timeout | null>(null);
  const invalidNameHintTimeout = useRef<NodeJS.Timeout | null>(null);
  const fileUploadRef = useRef<FileUploadRef>(null);

  // Step 1 validation errors
  const [step1Errors, setStep1Errors] = useState<string[]>([]);
  
  // Drag and drop state
  const [draggedFile, setDraggedFile] = useState<string | null>(null);
  const [availableFiles, setAvailableFiles] = useState<string[]>([]);
  const [draggedMappingIndex, setDraggedMappingIndex] = useState<number | null>(null);
  const [dragOverMappingIndex, setDragOverMappingIndex] = useState<number | null>(null);
  const [recentlyMovedMappingId, setRecentlyMovedMappingId] = useState<string | null>(null);
  const mappingContainerRef = useRef<HTMLDivElement | null>(null);
  const mappingRowRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const orderButtonRefs = useRef<Record<string, { up: HTMLButtonElement | null; down: HTMLButtonElement | null }>>({});
  const flipPositionsRef = useRef<Record<string, number> | null>(null);
  const autoScrollFrameRef = useRef<number | null>(null);
  const autoScrollVelocityRef = useRef(0);
  const moveHighlightTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const pendingButtonFollowRef = useRef<{ mappingId: string; button: 'up' | 'down'; previousTop: number } | null>(null);
  
  // Confirmation modal state
  const [showConfirmModal, setShowConfirmModal] = useState(false);
  const [pendingLayout, setPendingLayout] = useState<'se' | 'pe' | null>(null);

  // Upload cancel confirmation modal state
  const [showUploadCancelModal, setShowUploadCancelModal] = useState(false);

  // Alert modal state
  const [showAlertModal, setShowAlertModal] = useState(false);
  const [alertMessage, setAlertMessage] = useState('');
  const [alertTitle, setAlertTitle] = useState('Alert');

  // Long-read validation modal state
  const [showLongReadModal, setShowLongReadModal] = useState(false);
  const [longReadValidation, setLongReadValidation] = useState<{
    files: Array<{
      run: string;
      platform: string;
      model: string;
      avg_length: number;
      read_class: string;
    }>;
    validation: any;
  } | null>(null);

  // NCBI search states
  const [isSearching, setIsSearching] = useState(false);
  const [ncbiFiles, setNcbiFiles] = useState<NCBIFile[]>([]);
  const [ncbiSelectedRuns, setNcbiSelectedRuns] = useState<string[]>([]);
  const [macrogenSelectedFiles, setMacrogenSelectedFiles] = useState<string[]>([]);
  const [layoutError, setLayoutError] = useState('');
  const [importWorkbenchSources, setImportWorkbenchSources] = useState<ImportWorkbenchSource[]>([]);
  const [selectedImportedSamples, setSelectedImportedSamples] = useState<string[]>([]);
  const [expandedImportWorkbenchIds, setExpandedImportWorkbenchIds] = useState<number[]>([]);
  const [isLoadingImportSources, setIsLoadingImportSources] = useState(false);
  const [importSourcesError, setImportSourcesError] = useState<string | null>(null);

  // NCBI Sample Mapping state (used for 1/3 step only, converted to fileMappings in 2/3 step)
  const [ncbiSampleMappings, setNcbiSampleMappings] = useState<Record<string, string>>({});

  // Macrogen states
  const [macrogenUrl, setMacrogenUrl] = useState('');
  const [macrogenFiles, setMacrogenFiles] = useState<MacrogenFile[]>([]);
  const [isFetchingMacrogen, setIsFetchingMacrogen] = useState(false);
  const [macrogenError, setMacrogenError] = useState<string | null>(null);
  const [macrogenLayout, setMacrogenLayout] = useState<'single' | 'paired'>('paired');

  // Loading state for workbench creation
  const [isCreating, setIsCreating] = useState(false);

  // Reference Set list state
  const [availableReferenceSets, setAvailableReferenceSets] = useState<Array<{
    name: string;
    species: string;
  }>>([]);
  const [isLoadingReferences, setIsLoadingReferences] = useState(false);

  // Pipeline configuration state
  const [pipelineSteps, setPipelineSteps] = useState<PipelineStep[]>([
    {
      id: 'download',
      name: 'Data Download',
      description: 'Download or copy data files from specified source',
      selectedTool: 'data_downloader',
      availableTools: [
        {
          id: 'data_downloader',
          name: 'Data Downloader',
          description: 'Download data from server, upload, or NCBI sources',
          parameters: [
            { name: 'dataInputMethod', type: 'text', default: 'server', description: 'Data input method (server, upload, ncbi)' },
            { name: 'serverFilePaths', type: 'text', default: '', description: 'Server file paths (newline separated)' }
          ]
        }
      ],
      toolParameters: { dataInputMethod: 'server', serverFilePaths: '' }
    },
    {
      id: 'qc',
      name: 'Quality Control',
      description: 'Assess read quality and generate reports',
      selectedTool: 'fastqc',
      availableTools: [
        {
          id: 'fastqc',
          name: 'FastQC',
          description: 'Popular quality control tool for high throughput sequence data',
          parameters: [
            { name: 'threads', type: 'number', default: 4, description: 'Number of processing threads' }
          ]
        },
        {
          id: 'none',
          name: 'Skip QC',
          description: 'Skip quality control step',
          parameters: []
        }
      ],
      toolParameters: { threads: 4 }
    },
    {
      id: 'clean',
      name: 'Sequence Cleaning',
      description: 'Remove low quality reads and contamination (sequential processing supported)',
      selectedTool: 'prinseq_only',
      availableTools: [
        {
          id: 'none',
          name: 'Skip Cleaning',
          description: 'Use raw data without cleaning',
          parameters: []
        },
        {
          id: 'trimmomatic_only',
          name: 'Trimmomatic Only',
          description: 'Flexible read trimming tool for Illumina NGS data',
          parameters: [
            { name: 'leading', type: 'number', default: 3, description: 'Leading quality threshold' },
            { name: 'trailing', type: 'number', default: 3, description: 'Trailing quality threshold' },
            { name: 'slidingwindow', type: 'text', default: '4:15', description: 'Sliding window trimming (window_size:required_quality)' },
            { name: 'minlen', type: 'number', default: 36, description: 'Minimum length threshold' }
          ]
        },
        {
          id: 'prinseq_only',
          name: 'PRINSEQ Only',
          description: 'Preprocessing and information of sequence data',
          parameters: [
            { name: 'min_len', type: 'number', default: 50, description: 'Minimum sequence length' },
            { name: 'min_qual_mean', type: 'number', default: 20, description: 'Minimum mean quality score' },
            { name: 'trim_qual_left', type: 'number', default: 20, description: 'Trim sequences from 5\' end based on quality' },
            { name: 'trim_qual_right', type: 'number', default: 20, description: 'Trim sequences from 3\' end based on quality' }
          ]
        },
        {
          id: 'trimmomatic_prinseq',
          name: 'Trimmomatic ??PRINSEQ',
          description: 'Sequential processing: First Trimmomatic trimming, then PRINSEQ filtering',
          parameters: [
            { name: 'trimmomatic_leading', type: 'number', default: 3, description: '[Step 1] Trimmomatic: Leading quality threshold' },
            { name: 'trimmomatic_trailing', type: 'number', default: 3, description: '[Step 1] Trimmomatic: Trailing quality threshold' },
            { name: 'trimmomatic_slidingwindow', type: 'text', default: '4:15', description: '[Step 1] Trimmomatic: Sliding window (window_size:quality)' },
            { name: 'trimmomatic_minlen', type: 'number', default: 36, description: '[Step 1] Trimmomatic: Minimum length threshold' },
            { name: 'prinseq_min_len', type: 'number', default: 50, description: '[Step 2] PRINSEQ: Minimum sequence length' },
            { name: 'prinseq_min_qual_mean', type: 'number', default: 20, description: '[Step 2] PRINSEQ: Minimum mean quality score' },
            { name: 'prinseq_trim_qual_left', type: 'number', default: 20, description: '[Step 2] PRINSEQ: Trim from 5\' end based on quality' },
            { name: 'prinseq_trim_qual_right', type: 'number', default: 20, description: '[Step 2] PRINSEQ: Trim from 3\' end based on quality' }
          ]
        }
      ],
      toolParameters: { min_len: 50, min_qual_mean: 20, trim_qual_left: 20, trim_qual_right: 20 }
    },
    {
      id: 'quantification',
      name: 'Quantification',
      description: 'Align reads and quantify gene expression',
      selectedTool: 'hisat2_stringtie',
      availableTools: [
        {
          id: 'bowtie_rsem',
          name: 'Bowtie + RSEM',
          description: 'Ultrafast alignment with integrated RSEM quantification',
          parameters: [
            { name: 'threads', type: 'number', default: 4, description: 'Number of threads' },
            { name: 'max_mismatches', type: 'number', default: 2, description: 'Maximum number of mismatches in alignment' }
          ]
        },
        {
          id: 'bowtie2_rsem',
          name: 'Bowtie2 + RSEM',
          description: 'Fast and sensitive alignment with integrated RSEM quantification',
          parameters: [
            { name: 'threads', type: 'number', default: 4, description: 'Number of threads' },
            { name: 'preset', type: 'select', default: 'sensitive', options: ['very-fast', 'fast', 'sensitive', 'very-sensitive'], description: 'Alignment preset' }
          ]
        },
        {
          id: 'hisat2_stringtie',
          name: 'HISAT2 + StringTie',
          description: 'Graph-based alignment with transcriptome assembly and quantification',
          parameters: [
            { name: 'threads', type: 'number', default: 8, description: 'Number of threads' },
            { name: 'max_intronlen', type: 'number', default: 500000, description: 'Maximum intron length for HISAT2' },
            { name: 'min_coverage', type: 'number', default: 2.5, description: 'Minimum coverage for StringTie transcripts' },
            { name: 'min_transcript_len', type: 'number', default: 200, description: 'Minimum transcript length for StringTie' }
          ]
        }
      ],
      toolParameters: { threads: 8, max_intronlen: 500000, min_coverage: 2.5, min_transcript_len: 200 }
    },
    {
      id: 'deg',
      name: 'Differential Expression',
      description: 'Identify differentially expressed genes',
      selectedTool: 'edger',
      availableTools: [
        {
          id: 'edger',
          name: 'edgeR',
          description: 'Empirical analysis of digital gene expression data',
          parameters: [
            { name: 'fdr', type: 'number', default: 0.05, description: 'False discovery rate' },
            { name: 'logfc', type: 'number', default: 1, description: 'Log fold change threshold' }
          ]
        }
      ],
      toolParameters: {
        fdr: 0.05,
        logfc: 1,
        gsea_enabled: true,
        gsea_databases: DEFAULT_GSEA_DATABASES,
      }
    }
  ]);

  const [fileMappings, setFileMappings] = useState<FileMapping[]>(() => [
    createFileMapping({ groupName: 'Control', sampleName: 'Rep1' }),
    createFileMapping({ groupName: 'Treatment', sampleName: 'Rep1' })
  ]);

  const getSelectedImportedSampleDetails = useCallback(() => {
    const selectedKeys = new Set(selectedImportedSamples);
    return importWorkbenchSources.flatMap(source =>
      source.samples
        .filter(sample => selectedKeys.has(`${source.workbench_id}::${sample.group_name}::${sample.sample_name}`))
        .map(sample => ({
          sourceWorkbenchId: source.workbench_id,
          sourceWorkbenchName: source.workbench_name,
          sourceGroupName: sample.group_name,
          sourceSampleName: sample.sample_name,
          sourceCountTool: source.count_tool,
          sourceReferenceSet: source.reference_set,
          sourceHasTpmMatrix: source.has_tpm_matrix
        }))
    );
  }, [importWorkbenchSources, selectedImportedSamples]);

  useEffect(() => {
    return () => {
      if (autoScrollFrameRef.current !== null) {
        cancelAnimationFrame(autoScrollFrameRef.current);
      }
      autoScrollVelocityRef.current = 0;
      if (moveHighlightTimeoutRef.current) {
        clearTimeout(moveHighlightTimeoutRef.current);
      }
    };
  }, []);

  useLayoutEffect(() => {
    const previousPositions = flipPositionsRef.current;
    const pendingButtonFollow = pendingButtonFollowRef.current;
    if (!previousPositions) return;

    if (!pendingButtonFollow) {
      fileMappings.forEach(mapping => {
        const node = mappingRowRefs.current[mapping.uiId];
        if (!node) return;

        const previousTop = previousPositions[mapping.uiId];
        if (previousTop === undefined) return;

        const currentTop = node.getBoundingClientRect().top;
        const deltaY = previousTop - currentTop;

        if (Math.abs(deltaY) > 1) {
          node.style.transition = 'none';
          node.style.transform = `translateY(${deltaY}px)`;
          node.style.willChange = 'transform';

          requestAnimationFrame(() => {
            node.style.transition = 'transform 180ms ease, background-color 180ms ease, box-shadow 180ms ease, opacity 180ms ease';
            node.style.transform = 'translateY(0)';
            window.setTimeout(() => {
              if (mappingRowRefs.current[mapping.uiId] === node) {
                node.style.transition = '';
                node.style.willChange = '';
              }
            }, 220);
          });
        }
      });
    }

    if (pendingButtonFollow) {
      const container = mappingContainerRef.current;
      const button = orderButtonRefs.current[pendingButtonFollow.mappingId]?.[pendingButtonFollow.button];
      if (container && button) {
        const nextTop = button.getBoundingClientRect().top;
        const deltaY = nextTop - pendingButtonFollow.previousTop;
        if (Math.abs(deltaY) > 1) {
          container.scrollTop += deltaY;
        }
        button.focus({ preventScroll: true });
      }
      pendingButtonFollowRef.current = null;
    }

    flipPositionsRef.current = null;
  }, [fileMappings]);

  // Load available Reference Sets when modal opens
  useEffect(() => {
    // Only load when modal is actually open
    if (!isOpen) {
      return;
    }

    // Skip if already loaded
    if (availableReferenceSets.length > 0) {
      return;
    }

    const loadReferenceSets = async () => {
      setIsLoadingReferences(true);
      try {
        const response = await apiService.getReferences();

        const mappedRefs = response.references.map(ref => ({
          name: ref.name,
          species: ref.species
        }));

        setAvailableReferenceSets(mappedRefs);
      } catch (error) {
        console.error('Failed to load reference sets:', error);
        // Fallback to default TAIR10 if API fails
        setAvailableReferenceSets([
          { name: 'TAIR10', species: 'arabidopsis' }
        ]);
      } finally {
        setIsLoadingReferences(false);
      }
    };

    loadReferenceSets();
  }, [isOpen, availableReferenceSets.length]);

  // Auto-select first available Reference Set when species changes
  useEffect(() => {
    if (isLoadingReferences || availableReferenceSets.length === 0) return;

    const speciesMap: Record<string, string> = {
      'Arabidopsis thaliana': 'arabidopsis',
      'Lemna gibba (Duckweed)': 'lemna_gibba',
      'Lemna minor (Duckweed)': 'lemna_minor'
    };

    const currentSpecies = speciesMap[formData.species] || 'arabidopsis';

    const filteredReferences = availableReferenceSets.filter(
      ref => ref.species === currentSpecies
    );

    // If current referenceSet is not available for the new species, select the first one
    const currentRefAvailable = filteredReferences.some(ref => ref.name === formData.referenceSet);

    if (!currentRefAvailable && filteredReferences.length > 0) {
      setFormData(prev => ({ ...prev, referenceSet: filteredReferences[0].name }));
    } else if (filteredReferences.length === 0) {
      console.warn(`No references available for species: ${currentSpecies}`);
    }
  }, [formData.species, availableReferenceSets, isLoadingReferences, formData.referenceSet]);

  useEffect(() => {
    if (!isOpen || formData.dataInputMethod !== 'existing_workbench') {
      return;
    }

    const loadImportSources = async () => {
      setIsLoadingImportSources(true);
      setImportSourcesError(null);
      try {
        const response = await apiService.getImportWorkbenchSources(formData.species);
        const sources = response.sources || [];
        setImportWorkbenchSources(sources);
        setExpandedImportWorkbenchIds([]);
      } catch (error: any) {
        setImportSourcesError(error.message || 'Failed to load importable workbenches');
      } finally {
        setIsLoadingImportSources(false);
      }
    };

    loadImportSources();
  }, [isOpen, formData.dataInputMethod, formData.species]);

  const validateUploadedMatrixFiles = useCallback(async (countsTempFilename: string, tpmTempFilename?: string | null) => {
    if (!countsTempFilename) {
      setMatrixValidation(null);
      return null;
    }

    setMatrixValidationLoading(true);
    try {
      const result = await apiService.validateMatrixFiles({
        counts_temp_file: countsTempFilename,
        tpm_temp_file: tpmTempFilename || null
      });
      setMatrixValidation(result);
      return result;
    } catch (error: any) {
      const fallback = {
        valid: false,
        errors: [error.message || 'Failed to validate matrix files'],
        warnings: [],
        sample_columns: [],
        sample_count: 0,
        gene_count: 0,
        has_tpm_matrix: false
      };
      setMatrixValidation(fallback);
      return fallback;
    } finally {
      setMatrixValidationLoading(false);
    }
  }, []);

  const handleInputChange = useCallback((field: string, value: any) => {
    setFormData(prev => ({
      ...prev,
      [field]: value
    }));
    if (field === 'dataInputMethod' && value !== 'matrix_files') {
      setMatrixValidation(null);
    }
  }, []);

  const handleMatrixFileUpload = useCallback(async (kind: 'counts' | 'tpm', file: File | null) => {
    if (!file) return;
    const previousFile = kind === 'counts' ? matrixCountsFile : matrixTpmFile;
    if (previousFile) {
      try {
        await apiService.deleteTempFile(previousFile.tempFilename);
      } catch (error) {
        console.error(`Failed to replace matrix temp file ${previousFile.name}:`, error);
      }
    }
    const uploaded = await apiService.uploadTempMatrixFile(file);
    const uploadedFile: UploadedFile = {
      id: uploaded.temp_upload_id,
      name: uploaded.original_filename,
      size: uploaded.file_size,
      tempFilename: uploaded.temp_filename,
      uploadProgress: 100,
      uploadStatus: 'completed'
    };

    if (kind === 'counts') {
      setMatrixCountsFile(uploadedFile);
      await validateUploadedMatrixFiles(uploaded.temp_filename, matrixTpmFile?.tempFilename || null);
    } else {
      setMatrixTpmFile(uploadedFile);
      if (matrixCountsFile?.tempFilename) {
        await validateUploadedMatrixFiles(matrixCountsFile.tempFilename, uploaded.temp_filename);
      }
    }
  }, [matrixCountsFile?.tempFilename, matrixTpmFile?.tempFilename, validateUploadedMatrixFiles]);

  const handleMatrixFileRemove = useCallback(async (kind: 'counts' | 'tpm') => {
    const target = kind === 'counts' ? matrixCountsFile : matrixTpmFile;
    if (!target) return;
    try {
      await apiService.deleteTempFile(target.tempFilename);
    } catch (error) {
      console.error(`Failed to delete matrix temp file ${target.name}:`, error);
    }
    if (kind === 'counts') {
      setMatrixCountsFile(null);
      setMatrixValidation(null);
    } else {
      setMatrixTpmFile(null);
      if (matrixCountsFile?.tempFilename) {
        await validateUploadedMatrixFiles(matrixCountsFile.tempFilename, null);
      } else {
        setMatrixValidation(null);
      }
    }
  }, [matrixCountsFile, matrixTpmFile, validateUploadedMatrixFiles]);

  const handleMatrixDragOver = useCallback((e: React.DragEvent, kind: 'counts' | 'tpm') => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'copy';
    if (matrixDragTarget !== kind) {
      setMatrixDragTarget(kind);
    }
  }, [matrixDragTarget]);

  const handleMatrixDragLeave = useCallback((e: React.DragEvent, kind: 'counts' | 'tpm') => {
    const nextTarget = e.relatedTarget as Node | null;
    if (nextTarget && (e.currentTarget as HTMLElement).contains(nextTarget)) {
      return;
    }
    if (matrixDragTarget === kind) {
      setMatrixDragTarget(null);
    }
  }, [matrixDragTarget]);

  const handleMatrixDrop = useCallback(async (e: React.DragEvent, kind: 'counts' | 'tpm') => {
    e.preventDefault();
    setMatrixDragTarget(null);
    const fileItem = e.dataTransfer.files?.[0] || null;
    if (fileItem) {
      await handleMatrixFileUpload(kind, fileItem);
    }
  }, [handleMatrixFileUpload]);

  const toggleImportedWorkbenchExpanded = useCallback((workbenchId: number) => {
    setExpandedImportWorkbenchIds(prev =>
      prev.includes(workbenchId)
        ? prev.filter(id => id !== workbenchId)
        : [...prev, workbenchId]
    );
  }, []);

  const toggleImportedWorkbenchSamples = useCallback((source: ImportWorkbenchSource, checked: boolean) => {
    const workbenchSampleKeys = source.samples.map(
      sample => `${source.workbench_id}::${sample.group_name}::${sample.sample_name}`
    );

    setSelectedImportedSamples(prev => {
      if (checked) {
        return Array.from(new Set([...prev, ...workbenchSampleKeys]));
      }
      return prev.filter(key => !workbenchSampleKeys.includes(key));
    });
  }, []);

  // NCBI search handler
  const handleNcbiSearch = useCallback(async () => {
    if (!formData.bioprojectId.trim()) {
      return;
    }

    setIsSearching(true);
    setLayoutError('');

    try {
      const result = await apiService.searchNCBIBioproject(formData.bioprojectId.trim());

      // Use backend validation results
      const validation = result.validation;

      // Filter out long-read files completely
      let compatibleFiles = result.files;

      // Check for long-read data
      if (validation.has_long_reads) {
        const longReadFiles = result.files.filter(f => f.read_class === 'LONG');
        const shortReadFiles = result.files.filter(f => f.read_class === 'SHORT');

        setLongReadValidation({
          files: longReadFiles,
          validation: validation
        });
        setShowLongReadModal(true);

        // If there are short-read files, allow user to proceed with them
        if (shortReadFiles.length > 0) {
          // Use only short-read files
          compatibleFiles = shortReadFiles;
        } else {
          // No short-read files - block completely
          setNcbiFiles([]);
          return;
        }
      }

      // Check for borderline data (warning, but allow)
      if (validation.has_borderline) {
        const borderlineFiles = compatibleFiles.filter(f => f.read_class === 'BORDERLINE');
        const borderlineInfo = borderlineFiles.map(f =>
          `${f.run}: ${f.avg_length}bp avg`
        );

        const warningMessage =
          `?醫묓닔 Warning: Borderline read length detected\n\n` +
          `${validation.borderline_count} file(s) have average read length between 600-1000bp:\n` +
          `${borderlineInfo.slice(0, 3).map(p => `??${p}`).join('\n')}` +
          `${borderlineInfo.length > 3 ? `\n... and ${borderlineInfo.length - 3} more` : ''}\n\n` +
          `These files may be compatible, but upload validation will perform final verification.\n` +
          `You can proceed, but some files may be rejected during upload.`;

        // Show warning but don't block (optional: you can show a dismissible alert)
      }

      // Set only compatible files (SHORT or BORDERLINE, no LONG)
      setNcbiFiles(compatibleFiles);

      // Check if all files have the same layout
      const layouts = [...new Set(compatibleFiles.map(f => f.library_layout))];

      if (layouts.length === 1) {
        // All files have same layout - select all by default
        const selectedRuns = compatibleFiles.map(f => f.run);
        setNcbiSelectedRuns(selectedRuns);
        setLayoutError('');

        // Initialize sample mappings with default group names
        const initialMappings: Record<string, string> = {};
        compatibleFiles.forEach(file => {
          initialMappings[file.sample_name] = file.sample_name; // Default group name = sample name
        });
        setNcbiSampleMappings(initialMappings);

        // Auto-detect layout
        const detectedLayout = layouts[0] === 'PAIRED' ? 'pe' : 'se';
        handleInputChange('layout', detectedLayout);
      } else {
        // Mixed layouts - don't select any by default and show warning
        setNcbiSelectedRuns([]);
        setLayoutError("?醫묓닔 This BioProject contains both SE and PE files. Please select files with the same layout only.");
      }
    } catch (error) {
      setAlertTitle('NCBI Search Failed');
      setAlertMessage(`NCBI search failed: ${error instanceof Error ? error.message : 'Unknown error'}`);
      setShowAlertModal(true);
      setNcbiFiles([]);
    } finally {
      setIsSearching(false);
    }
  }, [formData.bioprojectId, handleInputChange]);

  // File selection handlers
  const handleSelectAll = useCallback(() => {
    if (ncbiSelectedRuns.length === ncbiFiles.length) {
      // Unselect all
      setNcbiSelectedRuns([]);
      setLayoutError('');
      handleInputChange('layout', 'se'); // Reset to default
    } else {
      // Select all - but check for layout consistency first
      const layouts = [...new Set(ncbiFiles.map(f => f.library_layout))];
      if (layouts.length > 1) {
        setLayoutError("?醫묓닔 SE and PE files cannot be mixed in the same analysis. Please select files with the same layout.");
        return;
      }

      setLayoutError('');
      const selectedRuns = ncbiFiles.map(f => f.run);
      setNcbiSelectedRuns(selectedRuns);

      // Initialize sample mappings with default group names for all selected files
      const initialMappings: Record<string, string> = {};
      ncbiFiles.forEach(file => {
        initialMappings[file.sample_name] = file.sample_name; // Default group name = sample name
      });
      setNcbiSampleMappings(initialMappings);

      // Auto-detect layout
      const detectedLayout = layouts[0] === 'PAIRED' ? 'pe' : 'se';
      handleInputChange('layout', detectedLayout);
    }
  }, [ncbiSelectedRuns.length, ncbiFiles, handleInputChange]);

  const handleSelectByLayout = useCallback((layout: 'SINGLE' | 'PAIRED') => {
    const filesWithLayout = ncbiFiles.filter(f => f.library_layout === layout);
    const selectedRuns = filesWithLayout.map(f => f.run);

    // Check if already all selected
    const allSelected = filesWithLayout.every(f => ncbiSelectedRuns.includes(f.run));

    if (allSelected) {
      // Unselect all files with this layout
      setNcbiSelectedRuns(prev => prev.filter(run => !selectedRuns.includes(run)));

      // If no files selected after unselecting, clear layout error
      const remainingFiles = ncbiSelectedRuns.filter(run => !selectedRuns.includes(run));
      if (remainingFiles.length === 0) {
        setLayoutError('');
        handleInputChange('layout', 'se'); // Reset to default
      }
    } else {
      // Select all files with this layout
      setLayoutError('');
      setNcbiSelectedRuns(selectedRuns);

      // Initialize sample mappings
      const initialMappings: Record<string, string> = {};
      filesWithLayout.forEach(file => {
        initialMappings[file.sample_name] = file.sample_name;
      });
      setNcbiSampleMappings(initialMappings);

      // Auto-detect layout
      const detectedLayout = layout === 'PAIRED' ? 'pe' : 'se';
      handleInputChange('layout', detectedLayout);
    }
  }, [ncbiFiles, ncbiSelectedRuns, handleInputChange]);

  const handleFileToggle = useCallback((runId: string) => {
    const file = ncbiFiles.find(f => f.run === runId);
    if (!file) return;

    const newSelectedRuns = ncbiSelectedRuns.includes(runId)
      ? ncbiSelectedRuns.filter(id => id !== runId)
      : [...ncbiSelectedRuns, runId];

    // Check layout consistency
    const selectedFileObjects = ncbiFiles.filter(f => newSelectedRuns.includes(f.run));
    const layouts = [...new Set(selectedFileObjects.map(f => f.library_layout))];

    if (layouts.length > 1) {
      setLayoutError("?醫묓닔 SE and PE files cannot be mixed in the same analysis. Please select files with the same layout.");
      return;
    }

    setLayoutError('');
    setNcbiSelectedRuns(newSelectedRuns);

    // Update sample mappings for currently selected files
    const newMappings: Record<string, string> = {};
    selectedFileObjects.forEach(file => {
      newMappings[file.sample_name] = ncbiSampleMappings[file.sample_name] || file.sample_name;
    });
    setNcbiSampleMappings(newMappings);

    // Auto-detect layout
    if (layouts.length === 1) {
      const detectedLayout = layouts[0] === 'PAIRED' ? 'pe' : 'se';
      handleInputChange('layout', detectedLayout);
    } else if (newSelectedRuns.length === 0) {
      handleInputChange('layout', 'se'); // Reset to default when no files selected
    }
  }, [ncbiSelectedRuns, ncbiFiles, ncbiSampleMappings, handleInputChange]);

  // Handle local file uploads
  const handleUploadedFilesChange = useCallback((files: UploadedFile[]) => {
    setFormData(prev => ({
      ...prev,
      uploadedFiles: files
    }));
  }, []);

  // Handle progress updates for specific file
  const handleFileProgressUpdate = useCallback((tempId: number, progress: number) => {
    setFormData(prev => {
      const updatedFiles = prev.uploadedFiles.map(f => 
        f.id === tempId 
          ? { ...f, uploadProgress: progress }
          : f
      );
      return {
        ...prev,
        uploadedFiles: updatedFiles
      };
    });
  }, []);

  // Handle upload completion for specific file
  const handleFileUploadComplete = useCallback((tempId: number, uploadResult: any) => {
    setFormData(prev => {
      const completedFiles = prev.uploadedFiles.map(f =>
        f.id === tempId
          ? {
              ...f,
              id: uploadResult.temp_upload_id,
              tempFilename: uploadResult.temp_filename,
              uploadProgress: 100,
              uploadStatus: 'completed'
            }
          : f
      );

      return {
        ...prev,
        uploadedFiles: completedFiles
      };
    });
  }, []);

  // Handle upload failure for specific file
  const handleFileUploadError = useCallback((tempId: number, error: string) => {
    setFormData(prev => ({
      ...prev,
      uploadedFiles: prev.uploadedFiles.map(f =>
        f.id === tempId
          ? { ...f, uploadStatus: 'failed', error: error }
          : f
      )
    }));
  }, []);

  // Helper functions to check if tabs have data
  const hasLocalFiles = Array.isArray(formData.uploadedFiles) ? formData.uploadedFiles.filter(f => f.uploadStatus === 'completed').length > 0 : false;
  const hasNcbiData = formData.bioprojectId.trim().length > 0 && ncbiFiles.length > 0 && ncbiSelectedRuns.length > 0;
  const hasServerPaths = formData.serverFilePaths.split('\n').filter(path => path.trim()).length > 0;
  const hasMatrixCounts = Boolean(matrixCountsFile);
  const hasMatrixTpm = Boolean(matrixTpmFile);
  const hasMacrogenData = macrogenUrl.trim().length > 0 && macrogenFiles.length > 0 && macrogenSelectedFiles.length > 0;

  // Real-time workbench name validation
  const validateWorkbenchName = useCallback(async (name: string) => {
    if (!name.trim()) {
      setNameValidation({ available: true, message: '', checking: false });
      return;
    }

    setNameValidation(prev => ({ ...prev, checking: true }));

    try {
      const response = await fetch('/api/workbenches/validate-name', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ name: name.trim() })
      });

      if (response.ok) {
        const data = await response.json();
        setNameValidation({
          available: data.available,
          message: data.message,
          checking: false
        });
      } else {
        setNameValidation({
          available: false,
          message: 'Validation failed',
          checking: false
        });
      }
    } catch (error) {
      setNameValidation({
        available: false,
        message: 'Validation failed',
        checking: false
      });
    }
  }, []);

  const handleNameChange = useCallback((name: string) => {
    // Filter out invalid characters (allow only alphanumeric, underscore, and hyphen)
    // Remove spaces, Korean characters, and special characters that are not allowed in folder names
    const filteredName = name.replace(/[^a-zA-Z0-9_\-]/g, '');
    const hasInvalidCharacters = name !== filteredName;

    handleInputChange('workbenchName', filteredName);

    if (invalidNameHintTimeout.current) {
      clearTimeout(invalidNameHintTimeout.current);
    }

    if (hasInvalidCharacters) {
      setInvalidNameHint('Only English letters, numbers, underscores (_), and hyphens (-) can be used.');
      invalidNameHintTimeout.current = setTimeout(() => {
        setInvalidNameHint('');
      }, 2800);
    } else {
      setInvalidNameHint('');
    }

    // Debounce validation
    if (nameValidationTimeout.current) {
      clearTimeout(nameValidationTimeout.current);
    }

    nameValidationTimeout.current = setTimeout(() => {
      validateWorkbenchName(filteredName);
    }, 500);
  }, [handleInputChange, validateWorkbenchName]);


  const handleNext = async () => {
    if (currentStep === 1) {
      // Step 1 validation before proceeding
      const validationErrors = [];
      
      // Check workbench name
      if (!formData.workbenchName.trim()) {
        validationErrors.push('Workbench name is required');
      } else if (!nameValidation.available) {
        validationErrors.push('Workbench name is not available');
      }
      
      // Check data source and files (only validate active tab)
      if (formData.dataInputMethod === 'local') {
        if (!hasLocalFiles) {
          validationErrors.push('Please select at least one file for Local Upload');
        }
      } else if (formData.dataInputMethod === 'ncbi') {
        if (!hasNcbiData) {
          if (formData.bioprojectId.trim().length === 0) {
            validationErrors.push('NCBI BioProject ID is required');
          } else if (ncbiFiles.length === 0) {
            validationErrors.push('Please search for valid NCBI data first');
          } else if (ncbiSelectedRuns.length === 0) {
            validationErrors.push('Please select at least one file from the search results');
          }
        }
      } else if (formData.dataInputMethod === 'macrogen') {
        if (macrogenUrl.trim().length === 0) {
          validationErrors.push('Macrogen report URL is required');
        } else if (macrogenFiles.length === 0) {
          validationErrors.push('Please fetch the file list from the Macrogen report first');
        } else if (macrogenSelectedFiles.length === 0) {
          validationErrors.push('Please select at least one file from the Macrogen report');
        }
      } else if (formData.dataInputMethod === 'server') {
        if (!hasServerPaths) {
          validationErrors.push('Please enter at least one server file path');
        } else {
          // Validate server file paths
          try {
            const filePaths = formData.serverFilePaths
              .split('\n')
              .filter(path => path.trim())
              .map(path => path.trim());

            const validationResult = await apiService.validateServerFiles(filePaths);

            if (validationResult.invalid_files.length > 0) {
              // Show validation errors
              const errorMessages = validationResult.invalid_files.map(
                f => `${f.filename}: ${f.error}`
              ).join('\n');

              setAlertTitle('Server File Validation Failed');
              setAlertMessage(`The following files are invalid:\n\n${errorMessages}`);
              setShowAlertModal(true);
              return;
            }

            // Check for long-read files
            const longReadFiles = validationResult.valid_files.filter(
              f => f.read_type === 'long'
            );

            if (longReadFiles.length > 0) {
              const longReadNames = longReadFiles.map(f => f.filename).join(', ');
              setAlertTitle('Long-read Data Detected');
              setAlertMessage(
                `The following files contain long-read data: ${longReadNames}\n\n` +
                `VizR currently supports only short-read (Illumina) data. ` +
                `Please use files with short reads only.`
              );
              setShowAlertModal(true);
              return;
            }

          } catch (error: any) {
            console.error('Server file validation error:', error);
            setAlertTitle('Validation Error');
            setAlertMessage(`Failed to validate server files: ${error.message || 'Unknown error'}`);
            setShowAlertModal(true);
            return;
          }
        }
      } else if (formData.dataInputMethod === 'existing_workbench') {
        if (selectedImportedSamples.length === 0) {
          validationErrors.push('Please select at least one sample from existing workbenches');
        }
      } else if (formData.dataInputMethod === 'matrix_files') {
        if (!matrixCountsFile) {
          validationErrors.push('Counts matrix is required');
        } else if (matrixValidationLoading) {
          validationErrors.push('Matrix file validation is still running');
        } else if (!matrixValidation) {
          validationErrors.push('Please validate the uploaded matrix files first');
        } else if (!matrixValidation.valid) {
          validationErrors.push(...matrixValidation.errors);
        }
      }
      
      // Show validation errors
      if (validationErrors.length > 0) {
        setStep1Errors(validationErrors);
        return;
      }
      
      // Clear errors if validation passes
      setStep1Errors([]);
      
      // If validation passes, proceed to step 2
      // Initialize available files based on current data source
      let fileNames: string[] = [];
      if (formData.dataInputMethod === 'local') {
        fileNames = Array.isArray(formData.uploadedFiles)
          ? formData.uploadedFiles
              .filter(file => file.uploadStatus === 'completed')
              .map(file => file.name)
          : [];
      } else if (formData.dataInputMethod === 'server') {
        fileNames = formData.serverFilePaths
          .split('\n')
          .filter(path => path.trim())
          .map(path => path.split(/[/\\]/).pop() || path.trim());
      } else if (formData.dataInputMethod === 'ncbi') {
        // For NCBI, files are pre-allocated, so Available Files should be empty
        fileNames = [];
      } else if (formData.dataInputMethod === 'macrogen') {
        // For Macrogen, files are pre-allocated, so Available Files should be empty
        fileNames = [];
      } else if (formData.dataInputMethod === 'existing_workbench') {
        fileNames = [];
      } else if (formData.dataInputMethod === 'matrix_files') {
        fileNames = [];
      }
      setAvailableFiles(fileNames);

      // Generate initial file mappings
      const initialMappings: FileMapping[] = [];
      
      if (formData.dataInputMethod === 'ncbi') {
        // For NCBI: Convert NCBI data to fileMappings format
        const selectedFileObjects = ncbiFiles.filter(f => ncbiSelectedRuns.includes(f.run));

        // Sort by sample_name for better grouping
        selectedFileObjects.sort((a, b) => a.sample_name.localeCompare(b.sample_name));

        // Group files by sample_name and generate unique sample names
        const sampleGroups: Record<string, typeof selectedFileObjects> = {};
        selectedFileObjects.forEach(file => {
          if (!sampleGroups[file.sample_name]) {
            sampleGroups[file.sample_name] = [];
          }
          sampleGroups[file.sample_name].push(file);
        });

        // Generate unique sample names for each file
        Object.entries(sampleGroups).forEach(([baseSampleName, files]) => {
          files.forEach((file, index) => {
            const uniqueSampleName = files.length > 1
              ? `${baseSampleName}-Rep${index + 1}`
              : baseSampleName;
              
            initialMappings.push(createFileMapping({
              groupName: '', // Leave Group Name empty for user input
              sampleName: uniqueSampleName,
              file1: formData.layout === 'pe' ? `${file.run}_1.fastq.gz` : `${file.run}.fastq.gz`,
              file2: formData.layout === 'pe' ? `${file.run}_2.fastq.gz` : undefined
            }));
          });
        });

        // Update layout field to match the detected layout
        handleInputChange('layout', formData.layout);
      } else if (formData.dataInputMethod === 'macrogen') {
        // For Macrogen: Convert macrogenFiles to fileMappings format
        const selectedFileObjs = macrogenFiles.filter(f => macrogenSelectedFiles.includes(f.name));

        if (macrogenLayout === 'paired') {
          // PAIRED: group _1 and _2 files by sample_name
          const r1Files = selectedFileObjs.filter(f => f.read_num === 1);
          r1Files.sort((a, b) => a.sample_name.localeCompare(b.sample_name));

          r1Files.forEach(file => {
            const r2File = macrogenFiles.find(
              f => f.sample_name === file.sample_name && f.read_num === 2
            );
            initialMappings.push(createFileMapping({
              groupName: '',
              sampleName: file.sample_name,
              file1: file.name,
              file2: r2File?.name
            }));
          });
          handleInputChange('layout', 'pe');
        } else {
          // SINGLE
          selectedFileObjs.sort((a, b) => a.sample_name.localeCompare(b.sample_name));
          selectedFileObjs.forEach(file => {
            initialMappings.push(createFileMapping({
              groupName: '',
              sampleName: file.sample_name,
              file1: file.name,
              file2: undefined
            }));
          });
          handleInputChange('layout', 'se');
        }
      } else if (formData.dataInputMethod === 'existing_workbench') {
        const importedSamples = getSelectedImportedSampleDetails();
        importedSamples.forEach(sample => {
          initialMappings.push(createFileMapping({
            groupName: sample.sourceGroupName,
            sampleName: sample.sourceSampleName,
            file1: '',
            file2: undefined,
            sourceWorkbenchId: sample.sourceWorkbenchId,
            sourceWorkbenchName: sample.sourceWorkbenchName,
            sourceGroupName: sample.sourceGroupName,
            sourceSampleName: sample.sourceSampleName,
            sourceCountTool: sample.sourceCountTool,
            sourceReferenceSet: sample.sourceReferenceSet
          }));
        });
      } else if (formData.dataInputMethod === 'matrix_files') {
        const columns = matrixValidation?.sample_columns || [];
        columns.forEach(columnName => {
          initialMappings.push(createFileMapping({
            groupName: '',
            sampleName: columnName,
            file1: '',
            file2: undefined,
            sourceColumnName: columnName,
            sourceSampleName: columnName
          }));
        });
      } else {
        // For Local/Server: Original logic
        const fileCount = fileNames.length;
        let mappingRowCount: number;
        
        if (formData.layout === 'se') {
          // Single-End: each file = one sample
          mappingRowCount = fileCount;
        } else {
          // Paired-End: two files = one sample (forward + reverse)
          mappingRowCount = Math.ceil(fileCount / 2);
        }

        for (let i = 0; i < mappingRowCount; i++) {
          const groupType = i < Math.ceil(mappingRowCount / 2) ? 'Control' : 'Treatment';
          const replicateNum = i < Math.ceil(mappingRowCount / 2) ? i + 1 : i - Math.floor(mappingRowCount / 2) + 1;
          
          initialMappings.push(createFileMapping({
            groupName: groupType,
            sampleName: `Rep${replicateNum}`,
            file2: formData.layout === 'pe' ? '' : undefined
          }));
        }
        
        // Update layout field to match the detected layout
        handleInputChange('layout', formData.layout);
      }
      
      setFileMappings(initialMappings);
      setCurrentStep(2);
    } else if (currentStep === 2) {
      // Step 2 validation - ensure all files are mapped
      const unmappedFiles = availableFiles.length;
      if (unmappedFiles > 0) {
        setAlertTitle('File Mapping Required');
        setAlertMessage(`${unmappedFiles} file(s) are not yet mapped. Please map all files before proceeding.`);
        setShowAlertModal(true);
        return;
      }

      // Step 2 validation - Check for duplicate sample names
      const sampleNames = fileMappings.map(mapping => mapping.sampleName).filter(name => name.trim());
      const duplicates = sampleNames.filter((name, index) => sampleNames.indexOf(name) !== index);

      if (duplicates.length > 0) {
        const uniqueDuplicates = [...new Set(duplicates)];
        setAlertTitle('Duplicate Sample Names');
        setAlertMessage(`Duplicate sample names detected: ${uniqueDuplicates.join(', ')}. Each sample must have a unique name.`);
        setShowAlertModal(true);
        return;
      }

      // Check for empty sample names
      const emptySamples = fileMappings.filter(mapping => !mapping.sampleName.trim());

      if (emptySamples.length > 0) {
        setAlertTitle('Empty Sample Names');
        setAlertMessage(`${emptySamples.length} mapping(s) are missing sample names. Please provide sample names for all mappings.`);
        setShowAlertModal(true);
        return;
      }

      // Check for empty group names
      const emptyGroups = fileMappings.filter(mapping => !mapping.groupName.trim());

      if (emptyGroups.length > 0) {
        setAlertTitle('Empty Group Names');
        setAlertMessage(`${emptyGroups.length} mapping(s) are missing group names. Please provide group names for all mappings.`);
        setShowAlertModal(true);
        return;
      }

      // Proceed to Step 3 - Pipeline Configuration
      setCurrentStep(3);
    } else {
      // Final step - Create workbench (validation already done in Step 2)
      await createWorkbench();
    }
  };

  const handleBack = () => {
    if (currentStep > 1) {
      setCurrentStep(currentStep - 1);
    }
  };

  const handleClose = () => {
    // Check if there are any uploaded files (completed or uploading)
    const uploadedFiles = Array.isArray(formData.uploadedFiles)
      ? formData.uploadedFiles.filter(f => f.uploadStatus === 'completed' || f.uploadStatus === 'uploading')
      : [];

    if (uploadedFiles.length > 0) {
      // Show confirmation modal if there are any uploaded files
      setShowUploadCancelModal(true);
      return;
    }

    // If no uploaded files, close immediately
    performClose();
  };

  const performClose = (deleteTempFiles: boolean = true) => {
    // Immediately cancel all uploads via FileUpload ref
    if (fileUploadRef.current) {
      fileUploadRef.current.cancelAllUploads();
    }

    // Cancel all uploading files before closing
    const uploadingFiles = Array.isArray(formData.uploadedFiles)
      ? formData.uploadedFiles.filter(f => f.uploadStatus === 'uploading')
      : [];

    uploadingFiles.forEach((file) => {
      if (file.abortController) {
        file.abortController.abort();
      }
    });

    // Delete all completed uploaded files from server temp folder (only if deleteTempFiles is true)
    if (deleteTempFiles) {
      const completedFiles = Array.isArray(formData.uploadedFiles)
        ? formData.uploadedFiles.filter(f => f.uploadStatus === 'completed')
        : [];

      completedFiles.forEach(async (file) => {
        try {
          await apiService.deleteTempFile(file.id);
        } catch (error) {
          console.error(`Failed to delete temp file ${file.name}:`, error);
          // Continue closing modal even if deletion fails
        }
      });

      [matrixCountsFile, matrixTpmFile].filter(Boolean).forEach(async (file) => {
        try {
          await apiService.deleteTempFile((file as UploadedFile).tempFilename);
        } catch (error) {
          console.error(`Failed to delete matrix temp file ${(file as UploadedFile).name}:`, error);
        }
      });
    }

    setCurrentStep(1);
    setFormData({
      workbenchName: '',
      dataInputMethod: 'local',
      bioprojectId: '',
      species: 'Arabidopsis thaliana',
      referenceGenome: null,
      referenceSet: 'TAIR10',
      layout: 'se',
      trimmomaticAdapter: 'TruSeq3',
      illuminaclipSeedMismatches: 2,
      illuminaclipPalindromeClip: 30,
      illuminaclipSimpleClip: 10,
      uploadedFiles: [],
      serverFilePaths: ''
    });
    setNameValidation({ available: true, message: '', checking: false });
    setInvalidNameHint('');
    setStep1Errors([]); // Clear validation errors
    setAvailableFiles([]); // Clear available files
    setDraggedFile(null); // Clear drag state
    setDraggedMappingIndex(null);
    setDragOverMappingIndex(null);
    setRecentlyMovedMappingId(null);
    setFileMappings([
      createFileMapping({ groupName: 'Control', sampleName: 'Rep1' }),
      createFileMapping({ groupName: 'Treatment', sampleName: 'Rep1' })
    ]); // Reset file mappings

    // Clear NCBI-related states
    setIsSearching(false);
    setNcbiFiles([]);
    setNcbiSelectedRuns([]);
    setLayoutError('');
    setNcbiSampleMappings({});

    // Clear Macrogen-related states
    setMacrogenUrl('');
    setMacrogenFiles([]);
    setMacrogenSelectedFiles([]);
    setIsFetchingMacrogen(false);
    setMacrogenError(null);
    setMacrogenLayout('paired');
    setImportWorkbenchSources([]);
    setSelectedImportedSamples([]);
    setExpandedImportWorkbenchIds([]);
    setImportSourcesError(null);
    setIsLoadingImportSources(false);
    setMatrixCountsFile(null);
    setMatrixTpmFile(null);
    setMatrixValidation(null);
    setMatrixValidationLoading(false);

    // Clear validation timeout
    if (nameValidationTimeout.current) {
      clearTimeout(nameValidationTimeout.current);
    }
    if (invalidNameHintTimeout.current) {
      clearTimeout(invalidNameHintTimeout.current);
    }

    onClose();
  };

  const addFileMapping = () => {
    const newMapping = createFileMapping({
      file2: formData.layout === 'pe' ? '' : undefined
    });
    setFileMappings(prev => [...prev, newMapping]);
  };

  const removeFileMapping = (index: number) => {
    setFileMappings(prev => prev.filter((_, i) => i !== index));
  };

  const updateFileMapping = (index: number, field: keyof FileMapping, value: string) => {
    setFileMappings(prev => prev.map((mapping, i) => 
      i === index ? { ...mapping, [field]: value } : mapping
    ));
  };

  const stopAutoScroll = useCallback(() => {
    autoScrollVelocityRef.current = 0;
    if (autoScrollFrameRef.current !== null) {
      cancelAnimationFrame(autoScrollFrameRef.current);
      autoScrollFrameRef.current = null;
    }
  }, []);

  const runAutoScroll = useCallback(() => {
    const container = mappingContainerRef.current;
    if (!container || autoScrollVelocityRef.current === 0) {
      autoScrollFrameRef.current = null;
      return;
    }

    container.scrollTop += autoScrollVelocityRef.current;
    autoScrollFrameRef.current = requestAnimationFrame(runAutoScroll);
  }, []);

  const startAutoScroll = useCallback((clientY: number) => {
    const container = mappingContainerRef.current;
    if (!container) return;

    const rect = container.getBoundingClientRect();
    const threshold = 72;
    const maxSpeed = 14;
    let nextVelocity = 0;

    if (clientY <= rect.top + threshold) {
      const depth = Math.max(0, rect.top + threshold - clientY);
      const ratio = Math.min(depth / threshold, 1);
      nextVelocity = -Math.max(2, maxSpeed * ratio * ratio);
    } else if (clientY >= rect.bottom - threshold) {
      const depth = Math.max(0, clientY - (rect.bottom - threshold));
      const ratio = Math.min(depth / threshold, 1);
      nextVelocity = Math.max(2, maxSpeed * ratio * ratio);
    }

    if (nextVelocity === 0) {
      stopAutoScroll();
      return;
    }

    autoScrollVelocityRef.current = nextVelocity;
    if (autoScrollFrameRef.current === null) {
      autoScrollFrameRef.current = requestAnimationFrame(runAutoScroll);
    }
  }, [runAutoScroll, stopAutoScroll]);

  const captureMappingPositions = useCallback(() => {
    const positions: Record<string, number> = {};
    fileMappings.forEach(mapping => {
      const node = mappingRowRefs.current[mapping.uiId];
      if (node) {
        positions[mapping.uiId] = node.getBoundingClientRect().top;
      }
    });
    flipPositionsRef.current = positions;
  }, [fileMappings]);

  const flashMovedMapping = useCallback((mappingId: string) => {
    setRecentlyMovedMappingId(mappingId);
    if (moveHighlightTimeoutRef.current) {
      clearTimeout(moveHighlightTimeoutRef.current);
    }
    moveHighlightTimeoutRef.current = setTimeout(() => {
      setRecentlyMovedMappingId(current => current === mappingId ? null : current);
    }, 700);
  }, []);

  const prepareButtonFollow = useCallback((mappingId: string, button: 'up' | 'down') => {
    const targetButton = orderButtonRefs.current[mappingId]?.[button];
    if (!targetButton) {
      pendingButtonFollowRef.current = null;
      return;
    }

    pendingButtonFollowRef.current = {
      mappingId,
      button,
      previousTop: targetButton.getBoundingClientRect().top
    };
  }, []);

  const moveFileMapping = useCallback((fromIndex: number, toIndex: number) => {
    if (
      fromIndex === toIndex ||
      fromIndex < 0 ||
      toIndex < 0 ||
      fromIndex >= fileMappings.length ||
      toIndex >= fileMappings.length
    ) {
      return;
    }

    captureMappingPositions();
    setFileMappings(prev => {
      const reordered = [...prev];
      const [moved] = reordered.splice(fromIndex, 1);
      reordered.splice(toIndex, 0, moved);
      return reordered;
    });
    flashMovedMapping(fileMappings[fromIndex].uiId);
  }, [captureMappingPositions, fileMappings, flashMovedMapping]);

  const moveFileMappingUp = useCallback((index: number) => {
    prepareButtonFollow(fileMappings[index].uiId, 'up');
    moveFileMapping(index, index - 1);
  }, [fileMappings, moveFileMapping, prepareButtonFollow]);

  const moveFileMappingDown = useCallback((index: number) => {
    prepareButtonFollow(fileMappings[index].uiId, 'down');
    moveFileMapping(index, index + 1);
  }, [fileMappings, moveFileMapping, prepareButtonFollow]);

  // Handle layout change and update file mappings accordingly
  const handleLayoutChange = (newLayout: 'se' | 'pe') => {
    // Check if any files are currently assigned
    const hasAssignedFiles = fileMappings.some(mapping => 
      mapping.file1.trim() !== '' || (mapping.file2 && mapping.file2.trim() !== '')
    );

    // If files are assigned, show confirmation modal
    if (hasAssignedFiles) {
      setPendingLayout(newLayout);
      setShowConfirmModal(true);
      return;
    }

    // If no files assigned, proceed directly
    performLayoutChange(newLayout);
  };

  // Actually perform the layout change
  const performLayoutChange = (newLayout: 'se' | 'pe') => {
    // Update layout
    handleInputChange('layout', newLayout);

    // Collect all assigned files and return them to available list
    const assignedFiles: string[] = [];
    fileMappings.forEach(mapping => {
      if (mapping.file1.trim()) assignedFiles.push(mapping.file1);
      if (mapping.file2 && mapping.file2.trim()) assignedFiles.push(mapping.file2);
    });

    // Add assigned files back to available list
    const updatedAvailableFiles = [...availableFiles, ...assignedFiles].sort();
    setAvailableFiles(updatedAvailableFiles);

    // Calculate new mapping row count based on total file count
    const totalFileCount = updatedAvailableFiles.length;
    let mappingRowCount: number;
    
    if (newLayout === 'se') {
      // Single-End: each file = one sample
      mappingRowCount = totalFileCount;
    } else {
      // Paired-End: two files = one sample (forward + reverse)
      mappingRowCount = Math.ceil(totalFileCount / 2);
    }

    // Generate fresh mappings for the new layout
    const freshMappings: FileMapping[] = [];
    for (let i = 0; i < mappingRowCount; i++) {
      const groupType = i < Math.ceil(mappingRowCount / 2) ? 'Control' : 'Treatment';
      const replicateNum = i < Math.ceil(mappingRowCount / 2) ? i + 1 : i - Math.floor(mappingRowCount / 2) + 1;
      
        freshMappings.push(createFileMapping({
          groupName: groupType,
          sampleName: `Rep${replicateNum}`,
          file2: newLayout === 'pe' ? '' : undefined
        }));
      }

    setFileMappings(freshMappings);
  };

  // Handle confirmation modal
  const handleConfirmLayoutChange = () => {
    if (pendingLayout) {
      performLayoutChange(pendingLayout);
    }
    setShowConfirmModal(false);
    setPendingLayout(null);
  };

  const handleCancelLayoutChange = () => {
    setShowConfirmModal(false);
    setPendingLayout(null);
  };

  // Drag and drop handlers
  const handleDragStart = (e: React.DragEvent, fileName: string) => {
    setDraggedFile(fileName);
    e.dataTransfer.setData('text/plain', fileName);
  };

  const handleDragEnd = () => {
    setDraggedFile(null);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
  };

  const handleDrop = (e: React.DragEvent, mappingIndex: number, fileField: 'file1' | 'file2') => {
    e.preventDefault();
    const fileName = e.dataTransfer.getData('text/plain');
    
    if (!fileName || !availableFiles.includes(fileName)) return;

    // Check if file is already assigned elsewhere
    const isAssigned = fileMappings.some((mapping, index) => 
      (mapping.file1 === fileName) || (mapping.file2 === fileName)
    );

    if (isAssigned) return;

    // Assign file to the mapping
    updateFileMapping(mappingIndex, fileField, fileName);
    
    // Remove file from available list
    setAvailableFiles(prev => prev.filter(file => file !== fileName));
    setDraggedFile(null);
  };

  const handleRemoveFile = (mappingIndex: number, fileField: 'file1' | 'file2') => {
    const mapping = fileMappings[mappingIndex];
    const fileName = mapping[fileField];
    
    if (fileName) {
      // Add file back to available list
      setAvailableFiles(prev => [...prev, fileName].sort());
      // Clear the file from mapping
      updateFileMapping(mappingIndex, fileField, '');
    }
  };

  const handleMappingDragStart = (e: React.DragEvent, index: number) => {
    captureMappingPositions();
    setDraggedMappingIndex(index);
    setDragOverMappingIndex(index);
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/mapping-index', String(index));
  };

  const handleMappingDragOver = (e: React.DragEvent, index: number) => {
    if (draggedMappingIndex === null) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';

    if (dragOverMappingIndex !== index) {
      setDragOverMappingIndex(index);
    }

    startAutoScroll(e.clientY);
  };

  const handleMappingDrop = (e: React.DragEvent, dropIndex: number) => {
    if (draggedMappingIndex === null) return;
    e.preventDefault();
    stopAutoScroll();
    moveFileMapping(draggedMappingIndex, dropIndex);
    setDraggedMappingIndex(null);
    setDragOverMappingIndex(null);
  };

  const handleMappingDragEnd = () => {
    stopAutoScroll();
    setDraggedMappingIndex(null);
    setDragOverMappingIndex(null);
  };

  // Create workbench function
  const createWorkbench = async () => {
    if (isCreating) return;
    
    setIsCreating(true);
    
    try {
      const importedSamplePayload = fileMappings.map(mapping => ({
        source_workbench_id: mapping.sourceWorkbenchId,
        source_workbench_name: mapping.sourceWorkbenchName,
        source_group_name: mapping.sourceGroupName,
        source_sample_name: mapping.sourceSampleName,
        source_column_name: mapping.sourceColumnName,
        target_group_name: mapping.groupName,
        target_sample_name: mapping.sampleName,
        source_count_tool: mapping.sourceCountTool,
        source_reference_set: mapping.sourceReferenceSet,
        source_has_tpm_matrix: mapping.sourceHasTpmMatrix
      }));
      const importedHasTpmMatrix =
        formData.dataInputMethod === 'existing_workbench'
          ? importedSamplePayload.length > 0 && importedSamplePayload.every(sample => Boolean(sample.source_has_tpm_matrix))
          : Boolean(matrixValidation?.has_tpm_matrix);

      const importedPipelineSteps = ['existing_workbench', 'matrix_files'].includes(formData.dataInputMethod)
        ? [
            {
              step: 'download',
              tool: 'none',
              description: 'Skipped for imported-count workbench',
              parameters: { disabled: true, locked_reason: 'Managed by imported count matrices' }
            },
            {
              step: 'qc',
              tool: 'none',
              description: 'Skipped for imported-count workbench',
              parameters: { disabled: true, locked_reason: 'Managed by imported count matrices' }
            },
            {
              step: 'clean',
              tool: 'none',
              description: 'Skipped for imported-count workbench',
              parameters: { disabled: true, locked_reason: 'Managed by imported count matrices' }
            },
            {
              step: 'alignment',
              tool: 'none',
              description: 'Skipped for imported-count workbench',
              parameters: { disabled: true, locked_reason: 'Managed by imported count matrices' }
            },
            {
              step: 'count',
              tool: formData.dataInputMethod === 'existing_workbench' ? 'imported_counts' : 'imported_matrix_files',
              description: formData.dataInputMethod === 'existing_workbench'
                ? 'Merge count matrices from existing workbenches'
                : 'Prepare imported count matrices from uploaded files',
              parameters: formData.dataInputMethod === 'existing_workbench'
                ? {
                    species: formData.species,
                    reference_set: importedSamplePayload[0]?.source_reference_set || formData.referenceSet,
                    has_tpm_matrix: importedHasTpmMatrix,
                    source_workbench_data: {
                      workbench_ids: [...new Set(importedSamplePayload.map(sample => sample.source_workbench_id).filter(Boolean))],
                      selected_samples: importedSamplePayload,
                      has_tpm_matrix: importedHasTpmMatrix
                    }
                  }
                : {
                    species: formData.species,
                    reference_set: formData.referenceSet,
                    has_tpm_matrix: importedHasTpmMatrix,
                    matrix_file_data: {
                      counts_temp_file: matrixCountsFile?.tempFilename,
                      tpm_temp_file: matrixTpmFile?.tempFilename || null,
                      has_tpm_matrix: importedHasTpmMatrix,
                      validated_sample_columns: matrixValidation?.sample_columns || [],
                      selected_samples: importedSamplePayload
                    }
                  }
            },
            ...pipelineSteps
              .filter(step => step.id === 'deg' && step.selectedTool !== 'none')
              .map(step => ({
                step: step.id,
                tool: step.selectedTool,
                description: step.description,
                parameters: step.toolParameters
              }))
          ]
        : null;

      // Prepare data payload
      const payload = {
        name: formData.workbenchName,
        description: '',
        species: formData.species,
        bioprojectId: formData.bioprojectId,
        dataInputMethod: formData.dataInputMethod, // Add data source information
        pipelineSteps: importedPipelineSteps || pipelineSteps
          .filter(step => {
            if (step.selectedTool === 'none') return false; // Exclude steps with tool='none'
            return true;
          })
          .flatMap(step => {
          // Handle quantification step - split into alignment + count
          if (step.id === 'quantification') {
            const tool = step.selectedTool;
            const params = step.toolParameters;

            // Parse tool combination
            let alignmentTool: string;
            let countTool: string;
            let alignmentParams: any = {};
            let countParams: any = {};

            if (tool === 'hisat2_stringtie') {
              alignmentTool = 'hisat2';
              countTool = 'stringtie';
              alignmentParams = {
                threads: params.threads || 8,
                max_intronlen: params.max_intronlen || 500000
              };
              countParams = {
                threads: params.threads || 8,
                min_coverage: params.min_coverage || 2.5,
                min_transcript_len: params.min_transcript_len || 200
              };
            } else if (tool === 'bowtie_rsem') {
              alignmentTool = 'bowtie';
              countTool = 'rsem';
              alignmentParams = {
                threads: params.threads || 4,
                max_mismatches: params.max_mismatches || 2,
                tool_name: 'bowtie'
              };
              countParams = {
                threads: params.threads || 4
              };
            } else if (tool === 'bowtie2_rsem') {
              alignmentTool = 'bowtie2';
              countTool = 'rsem';
              alignmentParams = {
                threads: params.threads || 4,
                preset: params.preset || 'sensitive',
                tool_name: 'bowtie2'
              };
              countParams = {
                threads: params.threads || 4
              };
            } else {
              // Fallback - shouldn't happen
              alignmentTool = 'hisat2';
              countTool = 'stringtie';
              alignmentParams = { threads: 8, max_intronlen: 500000 };
              countParams = { threads: 8, min_coverage: 2.5, min_transcript_len: 200 };
            }

            // Add reference information to both steps
            const referenceInfo = {
              referenceGenome: formData.referenceGenome,
              reference_set: formData.referenceSet,
              species: formData.species === 'Arabidopsis thaliana' ? 'arabidopsis' :
                       formData.species === 'Lemna gibba' ? 'lemna_gibba' : 'lemna_minor'
            };

            // Return both alignment and count steps
            return [
              {
                step: 'alignment',
                tool: alignmentTool,
                description: `Read alignment with ${alignmentTool.toUpperCase()}`,
                parameters: { ...alignmentParams, ...referenceInfo }
              },
              {
                step: 'count',
                tool: countTool,
                description: `Quantification with ${countTool.toUpperCase()}`,
                parameters: { ...countParams, ...referenceInfo }
              }
            ];
          }

          // Handle other steps normally (return as array for flatMap)
          return [(() => {
          // Add dataInputMethod and source-specific parameters to Download step
          if (step.id === 'download') {
            const baseParams = {
              ...step.toolParameters,
              dataInputMethod: formData.dataInputMethod
            };
            
            // Add different parameters for each data source
            if (formData.dataInputMethod === 'ncbi') {
              // NCBI: Derive SRR runs from fileMappings (Step 2), not ncbiSelectedRuns (Step 1).
              // The user may have deleted rows in Step 2, so fileMappings reflects the actual intended set.
              const srrRuns = fileMappings.map(mapping =>
                formData.layout === 'pe'
                  ? mapping.file1.replace('_1.fastq.gz', '')
                  : mapping.file1.replace('.fastq.gz', '')
              );
              const selectedFileObjects = ncbiFiles.filter(f => srrRuns.includes(f.run));

              // ???Create SRR size mapping (convert MB to bytes)
              const srrSizes: Record<string, number> = {};
              selectedFileObjects.forEach(file => {
                const sizeMB = parseFloat(file.size_mb) || 0;
                srrSizes[file.run] = Math.round(sizeMB * 1024 * 1024); // MB to bytes
              });

              baseParams.bioprojectId = formData.bioprojectId;
              baseParams.SRR_Runs = srrRuns;
              baseParams.SRR_Sizes = srrSizes;  // ??Add size information
            } else if (formData.dataInputMethod === 'macrogen') {
              // Macrogen: report URL and selected files with metadata
              baseParams.report_url = macrogenUrl;
              baseParams.macrogen_files = macrogenFiles.filter(f => macrogenSelectedFiles.includes(f.name));
            } else if (formData.dataInputMethod === 'server') {
              // Server: File paths
              baseParams.serverFilePaths = formData.serverFilePaths;
            }
            // No additional parameters for local (uses uploaded files)
            
            return {
              step: step.id,
              tool: step.selectedTool,
              description: step.description,
              parameters: baseParams
            };
          }
          // Add clean_tools array and Trimmomatic adapter settings to Clean step
          if (step.id === 'clean') {
            // Create clean_tools array from tool names
            const clean_tools: string[] = [];
            if (step.selectedTool.includes('trimmomatic')) {
              clean_tools.push('trimmomatic');
            }
            if (step.selectedTool.includes('prinseq')) {
              clean_tools.push('prinseq');
            }

            return {
              step: step.id,
              tool: step.selectedTool,
              description: step.description,
              parameters: {
                ...step.toolParameters,
                // Add clean_tools array (used by backend to determine input directory)
                clean_tools: clean_tools,
                // Add Trimmomatic adapter-related settings
                trimmomaticAdapter: formData.trimmomaticAdapter,
                illuminaclipSeedMismatches: formData.illuminaclipSeedMismatches,
                illuminaclipPalindromeClip: formData.illuminaclipPalindromeClip,
                illuminaclipSimpleClip: formData.illuminaclipSimpleClip
              }
            };
          }
          // Keep existing structure for other steps (step, tool, description, parameters)
          return {
            step: step.id,
            tool: step.selectedTool,
            description: step.description,
            parameters: step.toolParameters
          };
          })()];
        }),
        fileMappings: {
          layout: ['existing_workbench', 'matrix_files'].includes(formData.dataInputMethod) ? 'derived' : formData.layout,
          samples: fileMappings.map(({ uiId, ...mapping }) => mapping)
        },
        uploadedFiles: Array.isArray(formData.uploadedFiles)
          ? formData.uploadedFiles
              .filter(file => file.uploadStatus === 'completed')
              .map(file => ({
                temp_upload_id: file.id,
                name: file.name,
                size: file.size,
                temp_filename: file.tempFilename
              }))
          : [],
        // Add NCBI related data
        ncbiData: formData.dataInputMethod === 'ncbi' ? {
          selectedFiles: ncbiSelectedRuns,
          ncbiFiles: ncbiFiles.filter(f => ncbiSelectedRuns.includes(f.run)),
          readLayout: formData.layout
        } : null,
        sourceWorkbenchData: formData.dataInputMethod === 'existing_workbench' ? {
          workbench_ids: [...new Set(importedSamplePayload.map(sample => sample.source_workbench_id).filter(Boolean))],
          selected_samples: importedSamplePayload,
          has_tpm_matrix: importedHasTpmMatrix
        } : null,
        matrixFileData: formData.dataInputMethod === 'matrix_files' ? {
          counts_temp_file: matrixCountsFile?.tempFilename,
          tpm_temp_file: matrixTpmFile?.tempFilename || null,
          has_tpm_matrix: importedHasTpmMatrix
        } : null
      };

      const response = await fetch('/api/workbenches/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify(payload)
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || 'Failed to create workbench');
      }

      const result = await response.json();
      const workbenchId = result.workbench_id;

      // Close modal directly without confirmation (workbench creation succeeded)
      // DO NOT delete temp files - they will be moved to raw directory during "Start Analysis"
      performClose(false);

      // Call the callback to navigate to the new workbench
      if (onWorkbenchCreated) {
        onWorkbenchCreated(workbenchId);
      }

    } catch (error) {
      console.error('Error creating workbench:', error);
      setAlertTitle('Workbench Creation Failed');
      setAlertMessage(`Failed to create workbench: ${error instanceof Error ? error.message : 'Unknown error'}`);
      setShowAlertModal(true);
    } finally {
      setIsCreating(false);
    }
  };

  // Pipeline configuration handlers
  const updatePipelineStep = (stepId: string, toolId: string) => {
    setPipelineSteps(prev => prev.map(step => {
      if (step.id === stepId) {
        const selectedTool = step.availableTools.find(tool => tool.id === toolId);
        const defaultParams: { [key: string]: any } = {};
        
        if (selectedTool) {
          selectedTool.parameters.forEach(param => {
            defaultParams[param.name] = param.default;
          });
        }

        if (stepId === 'deg') {
          defaultParams.gsea_enabled = normalizeGSEAEnabled(step.toolParameters.gsea_enabled);
          defaultParams.gsea_databases = normalizeGSEADatabases(step.toolParameters.gsea_databases);
        }
        
        return {
          ...step,
          selectedTool: toolId,
          toolParameters: defaultParams
        };
      }
      return step;
    }));
  };

  const updateToolParameter = (stepId: string, paramName: string, value: any) => {
    setPipelineSteps(prev => prev.map(step => {
      if (step.id === stepId) {
        return {
          ...step,
          toolParameters: {
            ...step.toolParameters,
            [paramName]: value
          }
        };
      }
      return step;
    }));
  };

  const renderGSEASetup = () => {
    const degStep = pipelineSteps.find(step => step.id === 'deg');
    if (!degStep || degStep.selectedTool === 'none') return null;

    const gseaEnabled = normalizeGSEAEnabled(degStep.toolParameters.gsea_enabled);
    const selectedDatabases = normalizeGSEADatabases(degStep.toolParameters.gsea_databases);

    const toggleGSEADatabase = (databaseKey: string) => {
      const nextSelection = selectedDatabases.includes(databaseKey)
        ? selectedDatabases.filter((key: string) => key !== databaseKey)
        : [...selectedDatabases, databaseKey];

      updateToolParameter('deg', 'gsea_databases', nextSelection);
    };

    return (
      <div className="border border-slate-200 rounded-xl overflow-hidden">
        <div className="bg-gradient-to-r from-emerald-50 to-teal-50 px-6 py-4 border-b border-slate-200">
          <div className="flex items-center space-x-4">
            <div className="flex-shrink-0 w-10 h-10 bg-white rounded-lg flex items-center justify-center shadow-sm">
              <DocumentIcon className="w-6 h-6 text-emerald-600" />
            </div>
            <div className="flex-1">
              <h4 className="text-base font-semibold text-slate-800">5. GSEA</h4>
              <p className="text-sm text-slate-500">
                Select built-in gene set databases to prepare during the final GSEA pipeline step.
              </p>
            </div>
          </div>
        </div>

        <div className="px-6 py-5 bg-white space-y-4">
          <label className="flex items-center justify-between gap-4 rounded-lg border border-emerald-200 bg-emerald-50/70 px-4 py-3">
            <div>
              <p className="text-sm font-semibold text-slate-800">Enable GSEA</p>
              <p className="mt-1 text-xs text-slate-500">
                When disabled, VizR skips the automatic GSEA step and the DEG GSEA tab stays unavailable until prior GSEA results exist.
              </p>
            </div>
            <input
              type="checkbox"
              className="h-4 w-4 rounded border-slate-300 text-emerald-600 focus:ring-emerald-500"
              checked={gseaEnabled}
              onChange={(event) => updateToolParameter('deg', 'gsea_enabled', event.target.checked)}
            />
          </label>

          <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
            <p className="text-sm text-slate-700">
              Only selected databases will be downloaded, provisioned, and precomputed.
            </p>
            <p className="mt-1 text-xs text-slate-500">
              Default selections include databases already bundled with VizR snapshots.
            </p>
          </div>

          <div className={`grid grid-cols-1 gap-3 md:grid-cols-2 ${gseaEnabled ? '' : 'opacity-50 pointer-events-none'}`}>
            {GSEA_DATABASE_OPTIONS.map(option => {
              const checked = selectedDatabases.includes(option.key);
              return (
                <label
                  key={option.key}
                  className={`flex items-start gap-3 rounded-lg border px-4 py-3 transition-colors ${
                    checked
                      ? 'border-emerald-300 bg-emerald-50'
                      : 'border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50'
                  }`}
                >
                  <input
                    type="checkbox"
                    className="mt-0.5 h-4 w-4 rounded border-slate-300 text-emerald-600 focus:ring-emerald-500"
                    checked={checked}
                    onChange={() => toggleGSEADatabase(option.key)}
                  />
                  <span className="text-sm font-medium text-slate-800">{option.label}</span>
                </label>
              );
            })}
          </div>
        </div>
      </div>
    );
  };

  const renderStep1 = () => (
    <div className="space-y-6">
      {/* Validation Errors */}
      {step1Errors.length > 0 && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <div className="flex items-start">
            <div className="flex-shrink-0">
              <svg className="h-5 w-5 text-red-400" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
              </svg>
            </div>
            <div className="ml-3">
              <h3 className="text-sm font-medium text-red-800">
                Please fix the following issues:
              </h3>
              <div className="mt-2 text-sm text-red-700">
                <ul className="list-disc space-y-1 pl-5">
                  {step1Errors.map((error, index) => (
                    <li key={index}>{error}</li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        </div>
      )}
      <div>
        <label htmlFor="workbenchName" className="block text-sm font-medium text-slate-700 mb-1">
          Workbench Name
        </label>
        <div className="relative">
          {invalidNameHint && (
            <div className="absolute -top-[58px] left-0 right-0 z-30">
              <div
                className="relative rounded-lg border-2 border-red-400 bg-white px-3 py-2 text-sm text-red-700 shadow-sm"
                style={{ animation: 'invalid-name-hint-blink 0.62s ease-in-out 5' }}
              >
                {invalidNameHint}
                <div className="absolute left-6 top-full h-3 w-3 -translate-y-1/2 rotate-45 border-b-2 border-r-2 border-red-400 bg-white" />
              </div>
            </div>
          )}
          <input
            type="text"
            id="workbenchName"
            value={formData.workbenchName}
            onChange={(e) => handleNameChange(e.target.value)}
            placeholder="e.g., Cold_Stress_Experiment"
            className={`w-full px-3 py-2 border rounded-lg focus:ring-primary focus:border-primary pr-10 ${
              !nameValidation.available && formData.workbenchName.trim()
                ? 'border-red-300 focus:border-red-500 focus:ring-red-500'
                : 'border-slate-300'
            }`}
          />
          {nameValidation.checking && (
            <div className="absolute right-3 top-1/2 transform -translate-y-1/2">
              <div className="animate-spin w-4 h-4 border-2 border-slate-300 border-t-primary rounded-full"></div>
            </div>
          )}
          {!nameValidation.checking && formData.workbenchName.trim() && (
            <div className="absolute right-3 top-1/2 transform -translate-y-1/2">
              {nameValidation.available ? (
                <CheckIcon className="w-4 h-4 text-green-500" />
              ) : (
                <XIcon className="w-4 h-4 text-red-500" />
              )}
            </div>
          )}
        </div>
        {!nameValidation.available && nameValidation.message && (
          <p className="mt-1 text-sm text-red-600">{nameValidation.message}</p>
        )}
        <p className="mt-1 text-xs text-slate-500">
          Only alphanumeric characters (A-Z, a-z, 0-9), underscores (_), and hyphens (-) are allowed. Spaces and other characters will be automatically removed.
        </p>
      </div>
      
      <div>
        <label className="block text-sm font-medium text-slate-700 mb-2">Data Source</label>
        <div className="grid grid-cols-6 gap-2 rounded-lg bg-slate-100 p-1">
          <button
            onClick={() => handleInputChange('dataInputMethod', 'local')}
            className={`px-3 py-2 text-sm font-semibold rounded-md relative ${formData.dataInputMethod === 'local' ? 'bg-white shadow text-primary' : 'text-slate-600'}`}
          >
            <span>Local Upload</span>
            {hasLocalFiles && (
              <span className="absolute -top-1 -right-1 flex h-4 w-4 items-center justify-center">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500"></span>
              </span>
            )}
          </button>
          <button
            onClick={() => handleInputChange('dataInputMethod', 'ncbi')}
            className={`px-3 py-2 text-sm font-semibold rounded-md relative ${formData.dataInputMethod === 'ncbi' ? 'bg-white shadow text-primary' : 'text-slate-600'}`}
          >
            <span>NCBI BioProject</span>
            {hasNcbiData && (
              <span className="absolute -top-1 -right-1 flex h-4 w-4 items-center justify-center">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500"></span>
              </span>
            )}
          </button>
          <button
            onClick={() => { handleInputChange('dataInputMethod', 'macrogen'); setMacrogenSelectedFiles(macrogenFiles.map(f => f.name)); }}
            className={`px-3 py-2 text-sm font-semibold rounded-md relative ${formData.dataInputMethod === 'macrogen' ? 'bg-white shadow text-primary' : 'text-slate-600'}`}
          >
            <span>Macrogen</span>
            {hasMacrogenData && (
              <span className="absolute -top-1 -right-1 flex h-4 w-4 items-center justify-center">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500"></span>
              </span>
            )}
          </button>
          <button
            onClick={() => handleInputChange('dataInputMethod', 'server')}
            className={`px-3 py-2 text-sm font-semibold rounded-md relative ${formData.dataInputMethod === 'server' ? 'bg-white shadow text-primary' : 'text-slate-600'}`}
          >
            <span>From Server</span>
            {hasServerPaths && (
              <span className="absolute -top-1 -right-1 flex h-4 w-4 items-center justify-center">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500"></span>
              </span>
            )}
          </button>
          <button
            onClick={() => handleInputChange('dataInputMethod', 'existing_workbench')}
            className={`px-3 py-2 text-sm font-semibold rounded-md relative ${formData.dataInputMethod === 'existing_workbench' ? 'bg-white shadow text-primary' : 'text-slate-600'}`}
          >
            <span>Existing Workbenches</span>
            {selectedImportedSamples.length > 0 && (
              <span className="absolute -top-1 -right-1 flex h-4 w-4 items-center justify-center">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500"></span>
              </span>
            )}
          </button>
          <button
            onClick={() => handleInputChange('dataInputMethod', 'matrix_files')}
            className={`px-3 py-2 text-sm font-semibold rounded-md relative ${formData.dataInputMethod === 'matrix_files' ? 'bg-white shadow text-primary' : 'text-slate-600'}`}
          >
            <span>Matrix Files</span>
            {hasMatrixCounts && (
              <span className="absolute -top-1 -right-1 flex h-4 w-4 items-center justify-center">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500"></span>
              </span>
            )}
          </button>
        </div>
        
        {/* Active tab data info */}
        <div className="mt-2 text-xs text-slate-500 bg-blue-50 border border-blue-200 rounded-lg p-2">
          <div className="flex items-center space-x-1">
            <svg className="w-3 h-3 text-blue-500" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
            </svg>
            <span>
              Only data from the selected <strong>{
                formData.dataInputMethod === 'local' ? 'Local Upload' :
                formData.dataInputMethod === 'ncbi' ? 'NCBI BioProject' :
                formData.dataInputMethod === 'macrogen' ? 'Macrogen' :
                formData.dataInputMethod === 'server' ? 'From Server' :
                formData.dataInputMethod === 'existing_workbench' ? 'Existing Workbenches' : 'Matrix Files'
              }</strong> tab will be used for this workbench.
            </span>
          </div>
          
          {/* Show data from other tabs if they exist */}
          {(hasLocalFiles || hasNcbiData || hasMacrogenData || hasServerPaths) && (
            <div className="mt-2 pt-2 border-t border-blue-200">
              <div className="text-slate-600 font-medium mb-1">Data available in other tabs:</div>
              <div className="space-y-1">
                {hasLocalFiles && formData.dataInputMethod !== 'local' && (
                  <div className="flex items-center space-x-1">
                    <span className="w-2 h-2 bg-green-500 rounded-full"></span>
                    <span>Local Upload: {Array.isArray(formData.uploadedFiles) ? formData.uploadedFiles.filter(f => f.uploadStatus === 'completed').length : 0} file(s)</span>
                  </div>
                )}
                {hasNcbiData && formData.dataInputMethod !== 'ncbi' && (
                  <div className="flex items-center space-x-1">
                    <span className="w-2 h-2 bg-green-500 rounded-full"></span>
                    <span>NCBI BioProject: {formData.bioprojectId}</span>
                  </div>
                )}
                {hasMacrogenData && formData.dataInputMethod !== 'macrogen' && (
                  <div className="flex items-center space-x-1">
                    <span className="w-2 h-2 bg-green-500 rounded-full"></span>
                    <span>Macrogen: {macrogenSelectedFiles.length} file(s)</span>
                  </div>
                )}
                {hasServerPaths && formData.dataInputMethod !== 'server' && (
                  <div className="flex items-center space-x-1">
                    <span className="w-2 h-2 bg-green-500 rounded-full"></span>
                    <span>From Server: {formData.serverFilePaths.split('\n').filter(path => path.trim()).length} path(s)</span>
                  </div>
                )}
                {selectedImportedSamples.length > 0 && formData.dataInputMethod !== 'existing_workbench' && (
                  <div className="flex items-center space-x-1">
                    <span className="w-2 h-2 bg-green-500 rounded-full"></span>
                    <span>Existing Workbenches: {selectedImportedSamples.length} sample(s)</span>
                  </div>
                )}
                {hasMatrixCounts && formData.dataInputMethod !== 'matrix_files' && (
                  <div className="flex items-center space-x-1">
                    <span className="w-2 h-2 bg-green-500 rounded-full"></span>
                    <span>Matrix Files: counts{hasMatrixTpm ? ' + TPM' : ' only'}</span>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>


      {formData.dataInputMethod === 'local' && (
        <div className="space-y-4">
          {/* Upload Time Warning */}
          <div className="bg-amber-50 border border-amber-200 rounded-lg p-4">
            <div className="flex items-start">
              <div className="flex-shrink-0">
                <svg className="h-5 w-5 text-amber-400 mt-0.5" viewBox="0 0 20 20" fill="currentColor">
                  <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                </svg>
              </div>
              <div className="ml-3">
                <h3 className="text-sm font-medium text-amber-800">
                  Upload Time Notice
                </h3>
                <div className="mt-2 text-sm text-amber-700">
                  <p>
                    RNA-seq files are typically 1GB+ in size and may take considerable time to upload.
                    Please do not close your browser during workbench creation and wait until the upload is complete.
                  </p>
                </div>
              </div>
            </div>
          </div>
          
          <FileUpload
            ref={fileUploadRef}
            files={Array.isArray(formData.uploadedFiles) ? formData.uploadedFiles : []}
            onFilesChange={handleUploadedFilesChange}
            onProgressUpdate={handleFileProgressUpdate}
            onUploadComplete={handleFileUploadComplete}
            onUploadError={handleFileUploadError}
            accept=".fastq,.fq,.fasta,.fa,.gz,.fastq.gz,.fq.gz,.fasta.gz,.fa.gz"
            multiple={true}
            maxConcurrentUploads={1}
          />
        </div>
      )}
      
      {formData.dataInputMethod === 'ncbi' && (
        <div className="space-y-4">
          <div>
            <label htmlFor="bioproject" className="block text-sm font-medium text-slate-700 mb-1">NCBI BioProject Number</label>
            <div className="flex space-x-2">
              <input 
                type="text" 
                id="bioproject" 
                value={formData.bioprojectId}
                onChange={(e) => handleInputChange('bioprojectId', e.target.value)}
                placeholder="e.g., PRJNA252931" 
                className="flex-1 px-3 py-2 border border-slate-300 rounded-lg focus:ring-primary focus:border-primary" 
              />
              <button 
                onClick={handleNcbiSearch}
                disabled={isSearching || !formData.bioprojectId}
                className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed flex items-center space-x-2"
              >
                {isSearching ? (
                  <>
                    <div className="animate-spin w-4 h-4 border-2 border-white/30 border-t-white rounded-full" />
                    <span>Searching...</span>
                  </>
                ) : (
                  <>
                    <div>+</div>
                    <span>Search</span>
                  </>
                )}
              </button>
            </div>
          </div>

          {/* 野꺜??餓??袁㏓┛?癒?┛??嚥≪뮆逾??醫딅빍筌롫뗄???*/}
          {isSearching && (
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
              <div className="flex items-center space-x-3">
                <div className="flex space-x-1">
                  <div className="w-2 h-2 bg-blue-400 rounded-full animate-bounce"></div>
                  <div className="w-2 h-2 bg-blue-400 rounded-full animate-bounce" style={{animationDelay: '0.1s'}}></div>
                  <div className="w-2 h-2 bg-blue-400 rounded-full animate-bounce" style={{animationDelay: '0.2s'}}></div>
                </div>
                <span className="text-blue-600 font-medium">
                  ???Fetching metadata from NCBI...
                </span>
              </div>
            </div>
          )}

          {/* NCBI 野꺜??野껉퀗?????뵬 ?醫뤾문 ???뵠??*/}
          {ncbiFiles.length > 0 && (
            <div className="bg-green-50 border border-green-200 rounded-lg p-4">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center space-x-2">
                  <svg className="w-4 h-4 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" /></svg>
                  <span className="font-medium text-green-700">
                    Found {ncbiFiles.length} files
                  </span>
                </div>
                <div className="flex items-center space-x-3">
                  <div className="text-sm text-green-600">
                    Selected: {ncbiSelectedRuns.length}
                  </div>
                  {(() => {
                    const seCount = ncbiFiles.filter(f => f.library_layout === 'SINGLE').length;
                    const peCount = ncbiFiles.filter(f => f.library_layout === 'PAIRED').length;
                    const seSelected = ncbiFiles.filter(f => f.library_layout === 'SINGLE' && ncbiSelectedRuns.includes(f.run)).length;
                    const peSelected = ncbiFiles.filter(f => f.library_layout === 'PAIRED' && ncbiSelectedRuns.includes(f.run)).length;

                    return (seCount > 0 && peCount > 0) && (
                      <div className="flex items-center space-x-2">
                        <button
                          type="button"
                          onClick={() => handleSelectByLayout('SINGLE')}
                          className={`px-2 py-1 text-xs font-medium rounded border transition-colors ${
                            seSelected === seCount && seCount > 0
                              ? 'bg-blue-500 text-white border-blue-500'
                              : 'bg-white text-blue-600 border-blue-300 hover:bg-blue-50'
                          }`}
                        >
                          SE ({seCount})
                        </button>
                        <button
                          type="button"
                          onClick={() => handleSelectByLayout('PAIRED')}
                          className={`px-2 py-1 text-xs font-medium rounded border transition-colors ${
                            peSelected === peCount && peCount > 0
                              ? 'bg-purple-500 text-white border-purple-500'
                              : 'bg-white text-purple-600 border-purple-300 hover:bg-purple-50'
                          }`}
                        >
                          PE ({peCount})
                        </button>
                      </div>
                    );
                  })()}
                </div>
              </div>
              
              <div className="max-h-60 overflow-y-auto bg-white rounded border">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50 sticky top-0">
                    <tr>
                      <th className="px-3 py-2 text-left">
                        <input 
                          type="checkbox"
                          onChange={handleSelectAll}
                          checked={ncbiSelectedRuns.length === ncbiFiles.length && ncbiFiles.length > 0}
                          className="rounded"
                        />
                      </th>
                      <th className="px-3 py-2 text-left font-medium">FileName</th>
                      <th className="px-3 py-2 text-left font-medium">SampleName</th>
                      <th className="px-3 py-2 text-left font-medium">Layout</th>
                      <th className="px-3 py-2 text-left font-medium">Size</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ncbiFiles.map((file, index) => (
                      <tr key={file.run} className={index % 2 === 0 ? 'bg-white' : 'bg-gray-50'}>
                        <td className="px-3 py-2">
                          <input 
                            type="checkbox"
                            checked={ncbiSelectedRuns.includes(file.run)}
                            onChange={() => handleFileToggle(file.run)}
                            className="rounded"
                          />
                        </td>
                        <td className="px-3 py-2 font-mono text-xs">{file.run}</td>
                        <td className="px-3 py-2">{file.sample_name}</td>
                        <td className="px-3 py-2">
                          <span className={`px-2 py-1 rounded text-xs font-medium ${
                            file.library_layout === 'PAIRED' 
                              ? 'bg-blue-100 text-blue-800' 
                              : 'bg-gray-100 text-gray-800'
                          }`}>
                            {file.library_layout === 'PAIRED' ? 'PE' : 'SE'}
                          </span>
                        </td>
                        <td className="px-3 py-2 text-xs text-gray-500">
                          {file.size_mb} MB
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* SE/PE ??노? 獄쎻뫗? 野껋럡??筌롫뗄?놅쭪? */}
              {layoutError && (
                <div className="mt-3 bg-red-50 border border-red-200 rounded-lg p-3">
                  <div className="text-red-600 text-sm">{layoutError}</div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
      
      {formData.dataInputMethod === 'macrogen' && (
        <div className="space-y-4">
          <div>
            <label htmlFor="macrogenUrl" className="block text-sm font-medium text-slate-700 mb-1">Macrogen Report URL</label>
            <div className="flex space-x-2">
              <input
                type="text"
                id="macrogenUrl"
                value={macrogenUrl}
                onChange={(e) => setMacrogenUrl(e.target.value)}
                placeholder="https://data.macrogen.com/.../YYYYMMDD_XXXXXXXX_TRR_Report.zip"
                className="flex-1 px-3 py-2 border border-slate-300 rounded-lg focus:ring-primary focus:border-primary text-sm"
              />
              <button
                onClick={async () => {
                  if (!macrogenUrl.trim()) return;
                  setIsFetchingMacrogen(true);
                  setMacrogenError(null);
                  setMacrogenFiles([]);
                  setMacrogenSelectedFiles([]);
                  try {
                    const result = await apiService.fetchMacrogenFileList(macrogenUrl.trim());
                    setMacrogenFiles(result.files);
                    setMacrogenLayout(result.layout);
                    setMacrogenSelectedFiles(result.files.map(f => f.name));
                  } catch (e: any) {
                    setMacrogenError(e.message || 'Failed to fetch file list from Macrogen report');
                  } finally {
                    setIsFetchingMacrogen(false);
                  }
                }}
                disabled={isFetchingMacrogen || !macrogenUrl.trim()}
                className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed flex items-center space-x-2"
              >
                {isFetchingMacrogen ? (
                  <>
                    <div className="animate-spin w-4 h-4 border-2 border-white/30 border-t-white rounded-full" />
                    <span>Fetching...</span>
                  </>
                ) : (
                  <>
                    <div>+</div>
                    <span>Fetch File List</span>
                  </>
                )}
              </button>
            </div>
          </div>

          {/* 嚥≪뮆逾??醫딅빍筌롫뗄???*/}
          {isFetchingMacrogen && (
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
              <div className="flex items-center space-x-3">
                <div className="flex space-x-1">
                  <div className="w-2 h-2 bg-blue-400 rounded-full animate-bounce"></div>
                  <div className="w-2 h-2 bg-blue-400 rounded-full animate-bounce" style={{animationDelay: '0.1s'}}></div>
                  <div className="w-2 h-2 bg-blue-400 rounded-full animate-bounce" style={{animationDelay: '0.2s'}}></div>
                </div>
                <span className="text-blue-600 font-medium">
                  ?踰 Downloading and parsing Macrogen report...
                </span>
              </div>
            </div>
          )}

          {/* ?癒?쑎 筌롫뗄?놅쭪? */}
          {macrogenError && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-3">
              <div className="text-red-600 text-sm">{macrogenError}</div>
            </div>
          )}

          {/* ???뵬 筌뤴뫖以????뵠??*/}
          {macrogenFiles.length > 0 && (
            <div className="bg-green-50 border border-green-200 rounded-lg p-4">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center space-x-2">
                  <svg className="w-4 h-4 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" /></svg>
                  <span className="font-medium text-green-700">
                    Found {macrogenFiles.length} files ({macrogenLayout === 'paired' ? 'PAIRED' : 'SINGLE'})
                  </span>
                </div>
                <div className="text-sm text-green-600">
                  Selected: {macrogenSelectedFiles.length}
                </div>
              </div>

              <div className="max-h-60 overflow-y-auto bg-white rounded border">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50 sticky top-0">
                    <tr>
                      <th className="px-3 py-2 text-left">
                        <input
                          type="checkbox"
                          onChange={(e) => {
                            if (e.target.checked) {
                              setMacrogenSelectedFiles(macrogenFiles.map(f => f.name));
                            } else {
                              setMacrogenSelectedFiles([]);
                            }
                          }}
                          checked={macrogenSelectedFiles.length === macrogenFiles.length && macrogenFiles.length > 0}
                          className="rounded"
                        />
                      </th>
                      <th className="px-3 py-2 text-left font-medium">File Name</th>
                      <th className="px-3 py-2 text-left font-medium">Sample</th>
                      <th className="px-3 py-2 text-left font-medium">R#</th>
                      <th className="px-3 py-2 text-left font-medium">Size</th>
                    </tr>
                  </thead>
                  <tbody>
                    {macrogenFiles.map((file, index) => (
                      <tr key={file.name} className={index % 2 === 0 ? 'bg-white' : 'bg-gray-50'}>
                        <td className="px-3 py-2">
                          <input
                            type="checkbox"
                            checked={macrogenSelectedFiles.includes(file.name)}
                            onChange={() => {
                              const pairFiles = macrogenLayout === 'paired'
                                ? macrogenFiles.filter(f => f.sample_name === file.sample_name)
                                : [file];
                              const pairNames = pairFiles.map(f => f.name);
                              setMacrogenSelectedFiles(prev => {
                                const isSelected = prev.includes(file.name);
                                if (isSelected) {
                                  return prev.filter(f => !pairNames.includes(f));
                                } else {
                                  const existing = prev.filter(f => !pairNames.includes(f));
                                  return [...existing, ...pairNames];
                                }
                              });
                            }}
                            className="rounded"
                          />
                        </td>
                        <td className="px-3 py-2 font-mono text-xs">{file.name}</td>
                        <td className="px-3 py-2 text-xs">{file.sample_name}</td>
                        <td className="px-3 py-2">
                          {file.read_num > 0 && (
                            <span className={`px-2 py-1 rounded text-xs font-medium ${
                              file.read_num === 1 ? 'bg-blue-100 text-blue-800' : 'bg-purple-100 text-purple-800'
                            }`}>
                              R{file.read_num}
                            </span>
                          )}
                        </td>
                        <td className="px-3 py-2 text-xs text-gray-500">
                          {file.size_mb} MB
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {formData.dataInputMethod === 'server' && (
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-2">
              Server File Paths
            </label>
            <p className="text-xs text-slate-500 mb-3">
              Enter full server paths to your FASTQ/FASTA files, one path per line. 
              Use <code className="bg-slate-100 px-1 rounded text-xs">pwd</code> in terminal to get current directory, then add filename.
            </p>
            <textarea
              value={formData.serverFilePaths || ''}
              onChange={(e) => handleInputChange('serverFilePaths', e.target.value)}
              placeholder={`Example:
/home/user/data/sample1.fastq.gz
/home/user/data/sample2.fastq.gz
Y:\\11.Material\\PublicDATA\\file1.fq.gz
C:\\Users\\data\\file2.fasta.gz`}
              className="w-full h-40 px-3 py-2 border border-slate-300 rounded-lg focus:ring-primary focus:border-primary font-mono text-sm resize-vertical"
              rows={8}
            />
            <div className="flex items-center justify-between mt-2">
              {formData.serverFilePaths && (
                <p className="text-xs text-slate-500">
                  {formData.serverFilePaths.split('\n').filter(line => line.trim()).length} file path(s) entered
                </p>
              )}
              <button
                type="button"
                onClick={() => handleInputChange('serverFilePaths', '')}
                className="text-xs text-slate-500 hover:text-red-600 transition-colors"
              >
                Clear all
              </button>
            </div>
          </div>
        </div>
      )}

      {formData.dataInputMethod === 'existing_workbench' && (
        <div className="space-y-4">
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
            <h4 className="text-sm font-semibold text-slate-800">Import Counts From Existing Workbenches</h4>
            <p className="mt-1 text-sm text-slate-500">
              Select completed workbenches and choose the samples you want to reuse. The new workbench will merge counts and TPM matrices, regenerate TMM, and start downstream analysis from the count step.
            </p>
          </div>

          {importSourcesError && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              {importSourcesError}
            </div>
          )}

          {isLoadingImportSources ? (
            <div className="rounded-lg border border-slate-200 bg-white px-4 py-8 text-center text-slate-500">
              Loading compatible workbenches...
            </div>
          ) : importWorkbenchSources.length === 0 ? (
            <div className="rounded-lg border border-slate-200 bg-white px-4 py-8 text-center text-slate-500">
              No completed workbenches with reusable count matrices were found for the selected species.
            </div>
          ) : (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <p className="text-xs text-slate-500">
                  Expand a workbench to review its samples, then check only the samples you want to import.
                </p>
                <div className="flex items-center gap-3 text-xs">
                  <button
                    type="button"
                    onClick={() => setExpandedImportWorkbenchIds(importWorkbenchSources.map(source => source.workbench_id))}
                    className="text-slate-500 hover:text-primary transition-colors"
                  >
                    Expand all
                  </button>
                  <button
                    type="button"
                    onClick={() => setExpandedImportWorkbenchIds([])}
                    className="text-slate-500 hover:text-primary transition-colors"
                  >
                    Collapse all
                  </button>
                </div>
              </div>

              <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm text-sm overflow-auto max-h-[420px]">
                <div className="flex items-center text-slate-800 mb-2 relative z-20">
                  <button
                    type="button"
                    className="mr-2 bg-white text-slate-500 hover:text-primary transition-colors"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                    </svg>
                  </button>
                  <span className="font-bold text-base">Workbenches</span>
                </div>

                <div className="relative ml-2">
                  <div className="absolute top-0 bottom-0 left-0 w-px bg-slate-300 z-10" />

                  {importWorkbenchSources.map((source, sourceIdx) => {
                    const workbenchSampleKeys = source.samples.map(
                      sample => `${source.workbench_id}::${sample.group_name}::${sample.sample_name}`
                    );
                    const selectedCount = workbenchSampleKeys.filter(key => selectedImportedSamples.includes(key)).length;
                    const isExpanded = expandedImportWorkbenchIds.includes(source.workbench_id);
                    const isAllSelected = source.samples.length > 0 && selectedCount === source.samples.length;
                    const isPartiallySelected = selectedCount > 0 && selectedCount < source.samples.length;
                    const isLastWorkbench = sourceIdx === importWorkbenchSources.length - 1;

                    return (
                      <div key={source.workbench_id} className="relative">
                        <div className="absolute top-[16px] left-0 w-6 h-px bg-slate-300 z-10" />
                        {isLastWorkbench && (
                          <div className="absolute top-[17px] bottom-0 left-[-1px] w-[3px] bg-white z-10" />
                        )}

                        <div className="flex items-start py-1.5 pl-6 relative z-20">
                          <button
                            type="button"
                            onClick={() => toggleImportedWorkbenchExpanded(source.workbench_id)}
                            className="mr-2 mt-0.5 bg-white text-slate-500 hover:text-primary transition-colors"
                            title={isExpanded ? 'Collapse samples' : 'Expand samples'}
                          >
                            <svg
                              className={`w-4 h-4 transition-transform ${isExpanded ? 'rotate-90' : ''}`}
                              fill="none"
                              stroke="currentColor"
                              viewBox="0 0 24 24"
                            >
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                            </svg>
                          </button>
                          <input
                            type="checkbox"
                            checked={isAllSelected}
                            ref={(node) => {
                              if (node) node.indeterminate = isPartiallySelected;
                            }}
                            onChange={(e) => toggleImportedWorkbenchSamples(source, e.target.checked)}
                            className="mr-3 mt-1 rounded border-slate-300 bg-white"
                          />
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-2 flex-wrap">
                              <span
                                className="font-semibold text-slate-800 cursor-pointer hover:text-primary transition-colors"
                                onClick={() => toggleImportedWorkbenchExpanded(source.workbench_id)}
                              >
                                {source.workbench_name}
                              </span>
                              <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
                                {selectedCount}/{source.samples.length} selected
                              </span>
                              <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600">
                                #{source.workbench_id}
                              </span>
                            </div>
                            <p className="mt-1 text-xs text-slate-500">
                              {source.species} · {source.count_tool.toUpperCase()} · {source.reference_set || 'Unknown reference'}
                            </p>
                          </div>
                        </div>

                        {isExpanded && (
                          <div className="relative ml-8">
                            <div className="absolute top-0 bottom-0 left-0 w-px bg-slate-300 z-10" />
                            <div>
                              {source.samples.map((sample, sampleIdx) => {
                                const sampleKey = `${source.workbench_id}::${sample.group_name}::${sample.sample_name}`;
                                const isChecked = selectedImportedSamples.includes(sampleKey);
                                const isLastSample = sampleIdx === source.samples.length - 1;

                                return (
                                  <div key={sampleKey} className="relative">
                                    <div className="absolute top-[16px] left-0 w-6 h-px bg-slate-300 z-10" />
                                    {isLastSample && (
                                      <div className="absolute top-[17px] bottom-0 left-[-1px] w-[3px] bg-white z-10" />
                                    )}
                                    <label className="flex items-center py-1.5 pl-6 relative z-20 cursor-pointer">
                                      <input
                                        type="checkbox"
                                        checked={isChecked}
                                        onChange={() => {
                                          setSelectedImportedSamples(prev =>
                                            prev.includes(sampleKey)
                                              ? prev.filter(key => key !== sampleKey)
                                              : [...prev, sampleKey]
                                          );
                                        }}
                                        className="mr-3 rounded border-slate-300 bg-white"
                                      />
                                      <div className="min-w-0">
                                        <div className={`transition-colors ${isChecked ? 'text-primary font-semibold' : 'text-slate-700 hover:text-primary'}`}>
                                          {sample.sample_name}
                                        </div>
                                        <div className="truncate text-xs text-slate-500">{sample.group_name || 'Ungrouped'}</div>
                                      </div>
                                    </label>
                                  </div>
                                );
                              })}
                            </div>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {formData.dataInputMethod === 'matrix_files' && (
        <div className="space-y-4">
          <div className="rounded-lg border border-blue-200 bg-blue-50 p-4 text-sm text-blue-800">
            Counts matrix is required and used as the primary input for downstream analysis. TPM matrix is optional. If TPM is provided, VizR uses the uploaded TPM values together with counts to generate the normalized expression matrix. If TPM is omitted, VizR applies edgeR TMM normalization to raw counts and generates a TMM-adjusted CPM matrix for downstream visualization and exploratory analysis.
          </div>
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
            <div className="mb-1 text-sm font-semibold text-slate-800">Expected counts matrix format</div>
            <div className="mb-3 text-xs text-slate-600">
              Upload a tab-delimited gene-level matrix where the first column is <code className="rounded bg-slate-100 px-1 py-0.5">gene_id</code> and the remaining columns are sample names.
            </div>
            <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
              <table className="min-w-full text-left text-xs text-slate-600">
                <thead className="bg-slate-100 text-slate-700">
                  <tr>
                    <th className="border-b border-slate-200 px-3 py-2 font-semibold">gene_id</th>
                    <th className="border-b border-slate-200 px-3 py-2 font-semibold">WT_0h_rep1</th>
                    <th className="border-b border-slate-200 px-3 py-2 font-semibold">WT_0h_rep2</th>
                    <th className="border-b border-slate-200 px-3 py-2 font-semibold">WT_1h_rep1</th>
                    <th className="border-b border-slate-200 px-3 py-2 font-semibold">WT_1h_rep2</th>
                  </tr>
                </thead>
                <tbody>
                  {[
                    ['AT1G01010', '726', '584', '2279', '2974'],
                    ['AT1G01020', '507', '453', '677', '807'],
                    ['AT1G01030', '113', '87', '4149', '5318']
                  ].map((row) => (
                    <tr key={row[0]} className="odd:bg-white even:bg-slate-50/60">
                      {row.map((cell) => (
                        <td key={`${row[0]}-${cell}`} className="border-b border-slate-100 px-3 py-2">
                          {cell}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            {([
              { kind: 'counts', label: 'Counts Matrix', optional: false, file: matrixCountsFile },
              { kind: 'tpm', label: 'TPM Matrix (Optional)', optional: true, file: matrixTpmFile }
            ] as const).map(({ kind, label, file }) => (
              <div key={kind} className="rounded-lg border border-slate-200 bg-white p-4">
                <div className="mb-2 text-sm font-semibold text-slate-800">{label}</div>
                {file ? (
                  <div className="flex items-center justify-between rounded-lg border border-green-200 bg-green-50 px-3 py-2">
                    <div className="min-w-0">
                      <div className="truncate text-sm font-medium text-green-800">{file.name}</div>
                      <div className="text-xs text-green-700">{(file.size / 1024 / 1024).toFixed(2)} MB</div>
                    </div>
                    <button
                      type="button"
                      onClick={() => void handleMatrixFileRemove(kind)}
                      className="text-sm text-red-600 hover:text-red-700"
                    >
                      Remove
                    </button>
                  </div>
                ) : (
                  <label
                    onDragOver={(e) => handleMatrixDragOver(e, kind)}
                    onDragLeave={(e) => handleMatrixDragLeave(e, kind)}
                    onDrop={(e) => void handleMatrixDrop(e, kind)}
                    className={`flex cursor-pointer items-center justify-center rounded-lg border-2 border-dashed px-4 py-6 text-sm transition-colors ${
                      matrixDragTarget === kind
                        ? 'border-primary bg-primary/10 text-primary'
                        : 'border-slate-300 text-slate-500 hover:border-primary hover:bg-primary/5'
                    }`}
                  >
                    <input
                      type="file"
                      accept=".tsv,.txt,.matrix"
                      className="hidden"
                      onChange={(e) => {
                        const fileItem = e.target.files?.[0] || null;
                        if (fileItem) {
                          void handleMatrixFileUpload(kind, fileItem);
                        }
                        e.currentTarget.value = '';
                      }}
                    />
                    <div className="flex flex-col items-center gap-1 text-center">
                      <span>Select file</span>
                      <span className="text-xs text-slate-400">or drag and drop a matrix file here</span>
                    </div>
                  </label>
                )}
              </div>
            ))}
          </div>

          {(matrixValidationLoading || matrixValidation) && (
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
              <div className="text-sm font-semibold text-slate-800">Validation Preview</div>
              {matrixValidationLoading ? (
                <div className="mt-3 text-sm text-slate-600">Validating uploaded matrix files...</div>
              ) : matrixValidation && (
                <div className="mt-3 space-y-2 text-sm">
                  <div className="flex gap-4 text-slate-700">
                    <span>Samples: <strong>{matrixValidation.sample_count}</strong></span>
                    <span>Genes: <strong>{matrixValidation.gene_count}</strong></span>
                    <span>TPM: <strong>{matrixValidation.has_tpm_matrix ? 'Provided' : 'Not provided'}</strong></span>
                  </div>
                  {matrixValidation.errors.length > 0 && (
                    <div className="rounded border border-red-200 bg-red-50 p-3 text-red-700">
                      {matrixValidation.errors.map(error => <div key={error}>{error}</div>)}
                    </div>
                  )}
                  {matrixValidation.warnings.length > 0 && (
                    <div className="rounded border border-amber-200 bg-amber-50 p-3 text-amber-700">
                      {matrixValidation.warnings.map(warning => <div key={warning}>{warning}</div>)}
                    </div>
                  )}
                  {matrixValidation.sample_columns.length > 0 && (
                    <div className="rounded border border-slate-200 bg-white p-3">
                      <div className="mb-2 text-xs font-semibold uppercase text-slate-500">Detected sample columns</div>
                      <div className="flex flex-wrap gap-2">
                        {matrixValidation.sample_columns.map(column => (
                          <span key={column} className="rounded-full bg-slate-100 px-2 py-1 text-xs text-slate-700">{column}</span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      <div>
        <label htmlFor="species" className="block text-sm font-medium text-slate-700 mb-1">Analysis Species</label>
        <select
          id="species"
          value={formData.species}
          onChange={(e) => handleInputChange('species', e.target.value)}
          className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-primary focus:border-primary bg-white"
        >
          <option>Arabidopsis thaliana</option>
          <option disabled className="text-slate-400">Lemna</option>
          <option disabled className="text-slate-400">Spirodela</option>
          <option disabled className="text-slate-400">Wolffia</option>
        </select>
      </div>

      {/* Reference Genome - Hidden for future implementation */}
      {false && (
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Reference Genome (Optional)</label>
          <div className="space-y-2">
            <input
              type="file"
              accept=".fasta,.fa,.fasta.gz,.fa.gz"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) {
                  handleInputChange('referenceGenome', file);
                }
              }}
              className="hidden"
              id="referenceGenome"
            />
            <button
              onClick={() => document.getElementById('referenceGenome')?.click()}
              className="w-full text-sm border border-slate-300 rounded-lg py-2 hover:bg-slate-50 flex items-center justify-center space-x-2"
            >
              <UploadIcon className="w-4 h-4" />
              <span>Upload Reference File</span>
            </button>
            {formData.referenceGenome && (
              <div className="flex items-center justify-between p-2 bg-green-50 border border-green-200 rounded text-sm">
                <div className="flex items-center space-x-2">
                  <CheckIcon className="w-4 h-4 text-green-500" />
                  <span className="text-green-700">{formData.referenceGenome.name}</span>
                </div>
                <button
                  onClick={() => handleInputChange('referenceGenome', null)}
                  className="text-red-500 hover:text-red-700"
                >
                  <XIcon className="w-4 h-4" />
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );

  const renderStep2 = () => (
    ['existing_workbench', 'matrix_files'].includes(formData.dataInputMethod) ? (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-slate-800">Configure Imported Samples</h3>
        <p className="text-sm text-slate-500 mt-1">
          Review imported samples, update the final group/sample labels if needed, and reorder them to define the final samples.txt order.
        </p>
      </div>

      <div className="flex items-start justify-between">
        <div>
          <h4 className="text-base font-semibold text-slate-800">Imported Sample Mapping</h4>
          <p className="text-sm text-slate-500 mt-1">
            {fileMappings.length} selected samples from {formData.dataInputMethod === 'existing_workbench' ? 'existing workbenches' : 'uploaded matrix columns'}
          </p>
          <p className="text-xs text-slate-400 mt-1">
            Drag the handle or use the arrows to change row order. Downstream analysis will follow this order.
          </p>
        </div>
      </div>

      <div className="border border-slate-200 rounded-lg overflow-hidden">
        <div className="bg-slate-50 px-4 py-3 border-b border-slate-200">
          <div className="grid gap-4 text-sm font-semibold text-slate-700 grid-cols-[88px_minmax(220px,1.1fr)_minmax(180px,1fr)_minmax(180px,1fr)]">
            <div>Order</div>
            <div>{formData.dataInputMethod === 'existing_workbench' ? 'Source Workbench' : 'Source Column'}</div>
            <div>Group</div>
            <div>Sample</div>
          </div>
        </div>
        <div ref={mappingContainerRef} className="max-h-96 overflow-y-auto">
          {fileMappings.map((mapping, index) => (
            <div
              key={mapping.uiId}
              ref={(node) => { mappingRowRefs.current[mapping.uiId] = node; }}
              onDragOver={(e) => handleMappingDragOver(e, index)}
              onDrop={(e) => handleMappingDrop(e, index)}
              className={`px-4 py-3 border-b border-slate-100 grid gap-4 items-center transition-all duration-200 grid-cols-[88px_minmax(220px,1.1fr)_minmax(180px,1fr)_minmax(180px,1fr)] ${draggedMappingIndex === index ? 'opacity-80 scale-[0.99] shadow-md z-10 bg-primary/5' : 'bg-white'} ${dragOverMappingIndex === index && draggedMappingIndex !== null && draggedMappingIndex !== index ? 'bg-primary/5 border-primary/40' : ''} ${recentlyMovedMappingId === mapping.uiId ? 'ring-1 ring-primary/30 bg-primary/5' : ''}`}
            >
              <div className="flex items-center justify-center gap-1">
                <button
                  type="button"
                  draggable
                  onDragStart={(e) => handleMappingDragStart(e, index)}
                  onDragEnd={handleMappingDragEnd}
                  className="p-2 rounded-md text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors cursor-grab active:cursor-grabbing"
                  title="Drag to reorder"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 6h.01M8 12h.01M8 18h.01M16 6h.01M16 12h.01M16 18h.01" />
                  </svg>
                </button>
                <div className="flex flex-col">
                  <button
                    type="button"
                    ref={(node) => {
                      orderButtonRefs.current[mapping.uiId] = {
                        up: node,
                        down: orderButtonRefs.current[mapping.uiId]?.down ?? null
                      };
                    }}
                    onClick={() => moveFileMappingUp(index)}
                    disabled={index === 0}
                    className="p-0.5 rounded text-slate-400 hover:text-slate-700 disabled:text-slate-200 disabled:cursor-not-allowed transition-colors"
                    title="Move up"
                  >
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" />
                    </svg>
                  </button>
                  <button
                    type="button"
                    ref={(node) => {
                      orderButtonRefs.current[mapping.uiId] = {
                        up: orderButtonRefs.current[mapping.uiId]?.up ?? null,
                        down: node
                      };
                    }}
                    onClick={() => moveFileMappingDown(index)}
                    disabled={index === fileMappings.length - 1}
                    className="p-0.5 rounded text-slate-400 hover:text-slate-700 disabled:text-slate-200 disabled:cursor-not-allowed transition-colors"
                    title="Move down"
                  >
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                    </svg>
                  </button>
                </div>
              </div>
              <div className="text-sm text-slate-700 truncate" title={formData.dataInputMethod === 'existing_workbench' ? (mapping.sourceWorkbenchName || '-') : (mapping.sourceColumnName || '-')}>
                {formData.dataInputMethod === 'existing_workbench' ? (mapping.sourceWorkbenchName || '-') : (mapping.sourceColumnName || '-')}
              </div>
              <input
                type="text"
                value={mapping.groupName}
                onChange={(e) => updateFileMapping(index, 'groupName', e.target.value)}
                placeholder={mapping.sourceGroupName || "Control, Treatment, etc."}
                className="px-2 py-1 text-sm border border-slate-300 rounded focus:ring-primary focus:border-primary"
              />
              <input
                type="text"
                value={mapping.sampleName}
                onChange={(e) => updateFileMapping(index, 'sampleName', e.target.value)}
                placeholder={(mapping.sourceColumnName || mapping.sourceSampleName) || "Rep1, Rep2, etc."}
                className="px-2 py-1 text-sm border border-slate-300 rounded focus:ring-primary focus:border-primary"
              />
            </div>
          ))}
        </div>
      </div>
    </div>
    ) : (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-slate-800">Configure Sample Mapping</h3>
        <p className="text-sm text-slate-500 mt-1">
          Assign files to samples, then reorder the sample rows to match your preferred sample order
        </p>
      </div>

      {/* Data Layout Selection */}
      <div>
        <label className="block text-sm font-medium text-slate-700 mb-2">Data Layout</label>
        <div className="grid grid-cols-2 gap-2 rounded-lg bg-slate-100 p-1">
          <button 
            onClick={() => handleLayoutChange('se')} 
            className={`px-3 py-2 text-sm font-semibold rounded-md ${formData.layout === 'se' ? 'bg-white shadow text-primary' : 'text-slate-600'}`}
          >
            Single-End (SE)
          </button>
          <button 
            onClick={() => handleLayoutChange('pe')} 
            className={`px-3 py-2 text-sm font-semibold rounded-md ${formData.layout === 'pe' ? 'bg-white shadow text-primary' : 'text-slate-600'}`}
          >
            Paired-End (PE)
          </button>
        </div>
        <p className="text-xs text-slate-500 mt-2">
          {formData.layout === 'se' 
            ? 'Single-End: Each sample requires one FASTQ file' 
            : 'Paired-End: Each sample requires two FASTQ files (forward and reverse reads)'}
        </p>
      </div>

      {/* Available Files Panel */}
      <div>
        <h4 className="text-base font-semibold text-slate-800 mb-3">Available Files</h4>
        <div className="border border-slate-200 rounded-lg bg-slate-50 p-4 min-h-[120px]">
          {availableFiles.length > 0 ? (
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2">
              {availableFiles.map((fileName, index) => (
                <div
                  key={index}
                  draggable
                  onDragStart={(e) => handleDragStart(e, fileName)}
                  onDragEnd={handleDragEnd}
                  className={`
                    flex items-center space-x-2 p-2 bg-white border border-slate-200 rounded-lg cursor-move
                    hover:border-primary hover:shadow-sm transition-all duration-200
                    ${draggedFile === fileName ? 'opacity-50 scale-95' : ''}
                  `}
                  title={`Drag to assign: ${fileName}`}
                >
                  <DocumentIcon className="w-4 h-4 text-slate-400 flex-shrink-0" />
                  <span className="text-xs text-slate-700 truncate">{fileName}</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center text-slate-500 py-8">
              <DocumentIcon className="w-8 h-8 mx-auto mb-2 text-slate-300" />
              <p className="text-sm">All files have been assigned</p>
            </div>
          )}
        </div>
      </div>

      {/* File Mapping Section */}
      <div className="flex items-start justify-between">
        <div>
          <h4 className="text-base font-semibold text-slate-800">Sample Mapping</h4>
          <p className="text-sm text-slate-500 mt-1">
            {formData.layout === 'se' 
              ? `${availableFiles.length} files ??${fileMappings.length} samples (1 file per sample)`
              : `${availableFiles.length} files ??${fileMappings.length} samples (2 files per sample)`
            }
          </p>
          <p className="text-xs text-slate-400 mt-1">
            Drag the handle or use the arrows to change row order. The final samples.txt file will follow this order.
          </p>
        </div>
      </div>

      <div className="border border-slate-200 rounded-lg overflow-hidden">
        <div className="bg-slate-50 px-4 py-3 border-b border-slate-200">
          <div className={`grid gap-4 text-sm font-semibold text-slate-700 ${formData.layout === 'se' ? 'grid-cols-[88px_minmax(160px,1fr)_minmax(160px,1fr)_minmax(220px,1.2fr)]' : 'grid-cols-[88px_minmax(150px,0.95fr)_minmax(150px,0.95fr)_minmax(190px,1.15fr)_minmax(190px,1.15fr)]'}`}>
            <div>Order</div>
            <div>Group Name</div>
            <div>Replicate</div>
            <div>{formData.layout === 'se' ? 'FASTQ File' : 'Forward Read'}</div>
            {formData.layout === 'pe' && <div>Reverse Read</div>}
          </div>
        </div>
        
        <div ref={mappingContainerRef} className="max-h-96 overflow-y-auto">
          {fileMappings.map((mapping, index) => (
            <div
              key={mapping.uiId}
              ref={(node) => { mappingRowRefs.current[mapping.uiId] = node; }}
              onDragOver={(e) => handleMappingDragOver(e, index)}
              onDrop={(e) => handleMappingDrop(e, index)}
              className={`
                px-4 py-3 border-b border-slate-100 grid gap-4 items-center transition-all duration-200
                ${formData.layout === 'se' ? 'grid-cols-[88px_minmax(160px,1fr)_minmax(160px,1fr)_minmax(220px,1.2fr)]' : 'grid-cols-[88px_minmax(150px,0.95fr)_minmax(150px,0.95fr)_minmax(190px,1.15fr)_minmax(190px,1.15fr)]'}
                ${draggedMappingIndex === index ? 'opacity-80 scale-[0.99] shadow-md z-10 bg-primary/5' : 'bg-white'}
                ${dragOverMappingIndex === index && draggedMappingIndex !== null && draggedMappingIndex !== index ? 'bg-primary/5 border-primary/40' : ''}
                ${recentlyMovedMappingId === mapping.uiId ? 'ring-1 ring-primary/30 bg-primary/5' : ''}
              `}
            >
              <div className="flex items-center justify-center gap-1">
                <button
                  type="button"
                  draggable
                  onDragStart={(e) => handleMappingDragStart(e, index)}
                  onDragEnd={handleMappingDragEnd}
                  className="p-2 rounded-md text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors cursor-grab active:cursor-grabbing"
                  title="Drag to reorder"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 6h.01M8 12h.01M8 18h.01M16 6h.01M16 12h.01M16 18h.01" />
                  </svg>
                </button>
                <div className="flex flex-col">
                  <button
                    type="button"
                    ref={(node) => {
                      orderButtonRefs.current[mapping.uiId] = {
                        up: node,
                        down: orderButtonRefs.current[mapping.uiId]?.down ?? null
                      };
                    }}
                    onClick={() => moveFileMappingUp(index)}
                    disabled={index === 0}
                    className="p-0.5 rounded text-slate-400 hover:text-slate-700 disabled:text-slate-200 disabled:cursor-not-allowed transition-colors"
                    title="Move up"
                  >
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" />
                    </svg>
                  </button>
                  <button
                    type="button"
                    ref={(node) => {
                      orderButtonRefs.current[mapping.uiId] = {
                        up: orderButtonRefs.current[mapping.uiId]?.up ?? null,
                        down: node
                      };
                    }}
                    onClick={() => moveFileMappingDown(index)}
                    disabled={index === fileMappings.length - 1}
                    className="p-0.5 rounded text-slate-400 hover:text-slate-700 disabled:text-slate-200 disabled:cursor-not-allowed transition-colors"
                    title="Move down"
                  >
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                    </svg>
                  </button>
                </div>
              </div>
              <input
                type="text"
                value={mapping.groupName}
                onChange={(e) => updateFileMapping(index, 'groupName', e.target.value)}
                placeholder="Control, Treatment, etc."
                className="px-2 py-1 text-sm border border-slate-300 rounded focus:ring-primary focus:border-primary"
              />
              <input
                type="text"
                value={mapping.sampleName}
                onChange={(e) => updateFileMapping(index, 'sampleName', e.target.value)}
                placeholder="Rep1, Rep2, Rep3, etc."
                className="px-2 py-1 text-sm border border-slate-300 rounded focus:ring-primary focus:border-primary"
              />
              
              {/* Forward Read Drop Zone */}
              <div
                onDragOver={handleDragOver}
                onDrop={(e) => handleDrop(e, index, 'file1')}
                className={`
                  relative min-h-[32px] min-w-0 border-2 border-dashed rounded-lg flex items-center justify-center
                  ${mapping.file1 
                    ? 'border-green-300 bg-green-50' 
                    : 'border-slate-300 hover:border-primary hover:bg-primary/5'
                  }
                  transition-all duration-200
                `}
              >
                {mapping.file1 ? (
                  <div className="flex items-center space-x-2 px-2 py-1 min-w-0">
                    <DocumentIcon className="w-4 h-4 text-green-600" />
                    <span className="text-xs text-green-800 truncate min-w-0 flex-1" title={mapping.file1}>
                      {mapping.file1}
                    </span>
                    <button
                      onClick={() => handleRemoveFile(index, 'file1')}
                      className="text-red-500 hover:text-red-700"
                      title="Remove file"
                    >
                      <XIcon className="w-3 h-3" />
                    </button>
                  </div>
                ) : (
                  <span className="text-xs text-slate-500 px-2">Drop file here</span>
                )}
              </div>

              {/* Reverse Read Drop Zone (for PE only) */}
              {formData.layout === 'pe' && (
                <div
                  onDragOver={handleDragOver}
                  onDrop={(e) => handleDrop(e, index, 'file2')}
                  className={`
                    relative min-h-[32px] min-w-0 border-2 border-dashed rounded-lg flex items-center justify-center
                    ${mapping.file2 
                      ? 'border-green-300 bg-green-50' 
                      : 'border-slate-300 hover:border-primary hover:bg-primary/5'
                    }
                    transition-all duration-200
                  `}
                >
                  {mapping.file2 ? (
                    <div className="flex items-center space-x-2 px-2 py-1 min-w-0">
                      <DocumentIcon className="w-4 h-4 text-green-600" />
                      <span className="text-xs text-green-800 truncate min-w-0 flex-1" title={mapping.file2}>
                        {mapping.file2}
                      </span>
                      <button
                        onClick={() => handleRemoveFile(index, 'file2')}
                        className="text-red-500 hover:text-red-700"
                        title="Remove file"
                      >
                        <XIcon className="w-3 h-3" />
                      </button>
                    </div>
                  ) : (
                    <span className="text-xs text-slate-500 px-2">Drop file here</span>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
    )
  );

  const renderStep3 = () => {
    // Check if Bowtie/Bowtie2 is selected (RSEM integrated)
    const alignmentStep = pipelineSteps.find(s => s.id === 'alignment');
    const isBowtieSelected = alignmentStep && (alignmentStep.selectedTool === 'bowtie' || alignmentStep.selectedTool === 'bowtie2');

    return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-slate-800">Pipeline Configuration</h3>
        <p className="text-sm text-slate-500 mt-1">
          Configure tools and parameters for each step of the RNA-seq analysis pipeline
        </p>
      </div>

      {['existing_workbench', 'matrix_files'].includes(formData.dataInputMethod) && (
        <div className="rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-800">
          This workbench will start from imported matrices. QC, cleaning, and alignment settings are shown for reference only and will be skipped when jobs are generated.
        </div>
      )}

      {/* Reference Set Selection - Global configuration for Alignment and Count steps */}
      <div className="border border-blue-200 rounded-lg p-4 bg-blue-50/30">
        <div className="flex items-center space-x-3 mb-3">
          <svg className="w-5 h-5 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
          <h4 className="text-sm font-semibold text-blue-900">
            {formData.dataInputMethod === 'existing_workbench' ? 'Imported Reference Context' : 'Reference Genome Settings'}
          </h4>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-medium text-slate-700 mb-2">
              Reference Set
              {formData.dataInputMethod !== 'existing_workbench' && <span className="text-red-500 ml-1">*</span>}
            </label>
            <select
              value={formData.referenceSet}
              onChange={(e) => handleInputChange('referenceSet', e.target.value)}
              disabled={isLoadingReferences || formData.dataInputMethod === 'existing_workbench'}
              className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-primary focus:border-primary disabled:bg-slate-100 disabled:cursor-not-allowed"
            >
              {isLoadingReferences ? (
                <option>Loading reference sets...</option>
              ) : (() => {
                // Map species display name to internal species name
                const speciesMap: Record<string, string> = {
                  'Arabidopsis thaliana': 'arabidopsis',
                  'Lemna gibba (Duckweed)': 'lemna_gibba',
                  'Lemna minor (Duckweed)': 'lemna_minor'
                };

                const currentSpecies = speciesMap[formData.species] || 'arabidopsis';

                // Filter reference sets by current species
                const filteredReferences = availableReferenceSets.filter(
                  ref => ref.species === currentSpecies
                );

                if (filteredReferences.length === 0) {
                  return <option value="">No reference sets available for {formData.species}</option>;
                }

                return filteredReferences.map(ref => (
                  <option key={ref.name} value={ref.name}>
                    {ref.name}
                  </option>
                ));
              })()}
            </select>
            <p className="text-xs text-slate-500 mt-1">
              {formData.dataInputMethod === 'existing_workbench'
                ? 'Inherited from the selected source workbenches and shown as read-only context.'
                : 'Reference genome version for alignment and quantification.'}
              {formData.dataInputMethod !== 'existing_workbench' && !isLoadingReferences && availableReferenceSets.filter(ref => {
                const speciesMap: Record<string, string> = {
                  'Arabidopsis thaliana': 'arabidopsis',
                  'Lemna gibba (Duckweed)': 'lemna_gibba',
                  'Lemna minor (Duckweed)': 'lemna_minor'
                };
                return ref.species === (speciesMap[formData.species] || 'arabidopsis');
              }).length === 0 && (
                <span className="text-red-500 ml-1">
                  Please upload a reference set for this species in Settings.
                </span>
              )}
            </p>
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-700 mb-2">
              Species
            </label>
            <input
              type="text"
              value={formData.species}
              readOnly
              className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm bg-slate-50 text-slate-600"
            />
            <p className="text-xs text-slate-500 mt-1">
              Automatically determined from Step 1
            </p>
          </div>
        </div>
      </div>

      <div className="space-y-6">
        {pipelineSteps.filter(step => step.id !== 'download').map((step, index) => {
          const selectedTool = step.availableTools.find(tool => tool.id === step.selectedTool);
          const isCountStepDisabled = step.id === 'count' && isBowtieSelected;
          const isImportedLocked = ['existing_workbench', 'matrix_files'].includes(formData.dataInputMethod) && ['download', 'qc', 'clean', 'quantification'].includes(step.id);

          return (
            <div key={step.id} className={`border border-slate-200 rounded-xl overflow-hidden ${(isCountStepDisabled || isImportedLocked) ? 'opacity-60' : ''}`}>
              {/* Step Header */}
              <div className="bg-gradient-to-r from-blue-50 to-indigo-50 px-6 py-4 border-b border-slate-200">
                <div className="flex items-center space-x-4">
                  <div className="flex-shrink-0 w-10 h-10 bg-white rounded-lg flex items-center justify-center shadow-sm">
                    {getPipelineStepIcon(step.id)}
                  </div>
                  <div className="flex-1">
                    <h4 className="text-base font-semibold text-slate-800">
                      {index + 1}. {step.name}
                    </h4>
                    <p className="text-sm text-slate-500">{step.description}</p>
                    {(isCountStepDisabled || isImportedLocked) && (
                      <p className="text-xs text-blue-600 mt-1 flex items-center">
                        <svg className="w-4 h-4 mr-1" fill="currentColor" viewBox="0 0 20 20">
                          <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
                        </svg>
                        {isImportedLocked
                          ? 'Managed by imported count matrices'
                          : 'Quantification is already included in Bowtie + RSEM alignment step'}
                      </p>
                    )}
                  </div>
                </div>
              </div>

              {/* Tool Selection */}
              <div className={`px-6 py-4 bg-white ${(isCountStepDisabled || isImportedLocked) ? 'pointer-events-none' : ''}`}>
                <div className={`grid gap-3 ${step.id === 'clean' ? 'grid-cols-1 md:grid-cols-2' : 'grid-cols-1 md:grid-cols-3'}`}>
                  {step.availableTools.map(tool => (
                    <button
                      key={tool.id}
                      onClick={() => updatePipelineStep(step.id, tool.id)}
                      className={`
                        p-4 text-left border-2 rounded-lg transition-all duration-200
                        ${step.selectedTool === tool.id
                          ? 'border-primary bg-primary/5 shadow-sm'
                          : 'border-slate-200 hover:border-slate-300 hover:bg-slate-50'
                        }
                        ${tool.id === 'trimmomatic_prinseq' ? 'md:col-span-2' : ''}
                      `}
                    >
                      <div className="font-medium text-sm text-slate-800">
                        {tool.name}
                        {tool.id === 'trimmomatic_prinseq' && (
                          <span className="ml-2 text-xs bg-blue-100 text-blue-700 px-2 py-1 rounded-full">Sequential</span>
                        )}
                      </div>
                      <div className="text-xs text-slate-500 mt-1 line-clamp-2">{tool.description}</div>
                      
                      {/* Sequential Processing Visual for Trimmomatic ??PRINSEQ */}
                      {tool.id === 'trimmomatic_prinseq' && (
                        <div className="mt-3 flex items-center space-x-2 text-xs">
                          <div className="flex items-center space-x-2 bg-orange-50 px-2 py-1 rounded">
                            <CleanIcon className="w-3 h-3 text-orange-600" />
                            <span className="text-orange-700 font-medium">Trimmomatic</span>
                          </div>
                          <ArrowRightIcon className="w-3 h-3 text-slate-400" />
                          <div className="flex items-center space-x-2 bg-green-50 px-2 py-1 rounded">
                            <CleanIcon className="w-3 h-3 text-green-600" />
                            <span className="text-green-700 font-medium">PRINSEQ</span>
                          </div>
                        </div>
                      )}
                    </button>
                  ))}
                </div>

                {/* Tool Parameters */}
                {selectedTool && selectedTool.parameters.length > 0 && (
                  <div className="mt-6 p-4 bg-slate-50 rounded-lg">
                    <h5 className="text-sm font-medium text-slate-700 mb-3">
                      {selectedTool.name} Parameters
                    </h5>
                    
                    {/* Sequential Processing Parameters Layout */}
                    {selectedTool.id === 'trimmomatic_prinseq' ? (
                      <div className="space-y-6">
                        {/* Step 1: Trimmomatic Parameters */}
                        <div className="border border-orange-200 rounded-lg p-4 bg-orange-50/30">
                          <div className="flex items-center space-x-2 mb-3">
                            <div className="w-6 h-6 bg-orange-100 rounded-full flex items-center justify-center">
                              <span className="text-xs font-bold text-orange-700">1</span>
                            </div>
                            <h6 className="text-sm font-semibold text-orange-800">Trimmomatic Parameters</h6>
                          </div>
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            {selectedTool.parameters.filter(param => param.name.startsWith('trimmomatic_') && param.name !== 'trimmomatic_illuminaclip_params').map(param => (
                              <div key={param.name}>
                                <label className="block text-xs font-medium text-slate-600 mb-1">
                                  {param.name.replace('trimmomatic_', '')}
                                </label>
                                {param.type === 'text' && (
                                  <input
                                    type="text"
                                    value={step.toolParameters[param.name] || param.default}
                                    onChange={(e) => updateToolParameter(step.id, param.name, e.target.value)}
                                    className="w-full px-2 py-1 text-sm border border-slate-300 rounded focus:ring-primary focus:border-primary"
                                  />
                                )}
                                {param.type === 'number' && (
                                  <input
                                    type="number"
                                    value={step.toolParameters[param.name] || param.default}
                                    onChange={(e) => updateToolParameter(step.id, param.name, parseFloat(e.target.value) || param.default)}
                                    className="w-full px-2 py-1 text-sm border border-slate-300 rounded focus:ring-primary focus:border-primary"
                                  />
                                )}
                                <p className="text-xs text-slate-500 mt-1">{param.description}</p>
                              </div>
                            ))}
                            
                            {/* Adapter Selection - 筌???살쨮 ??猷?*/}
                            <div className="md:col-span-2">
                              <label className="block text-xs font-medium text-slate-600 mb-2">
                                ???ILLUMINACLIP Configuration
                              </label>
                              
                              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                {/* Adapter File Selection */}
                                <div>
                                  <label className="block text-xs font-medium text-slate-500 mb-1">
                                    Adapter
                                  </label>
                                  <select
                                    value={formData.trimmomaticAdapter || 'TruSeq3'}
                                    onChange={(e) => {
                                      console.log('Adapter selection changed:', e.target.value);
                                      setFormData(prev => ({ ...prev, trimmomaticAdapter: e.target.value }));
                                    }}
                                    className="w-full px-2 py-1 text-sm border border-slate-300 rounded focus:ring-primary focus:border-primary"
                                  >
                                    <option value="TruSeq3">TruSeq v3</option>
                                    <option value="TruSeq2">TruSeq v2</option>
                                    <option value="NexteraPE">Nextera (only PE)</option>
                                    <option value="none">None</option>
                                  </select>
                                </div>
                                
                                {/* ILLUMINACLIP Parameters */}
                                <div>
                                  <label className="block text-xs font-medium text-slate-500 mb-1">
                                    Parameters
                                  </label>
                                  <div className="grid grid-cols-3 gap-1">
                                    <input
                                      type="number"
                                      placeholder="2"
                                      value={formData.illuminaclipSeedMismatches}
                                      onChange={(e) => setFormData(prev => ({ 
                                        ...prev, 
                                        illuminaclipSeedMismatches: parseInt(e.target.value) || 2 
                                      }))}
                                      className="px-2 py-1 text-xs border border-slate-300 rounded focus:ring-primary focus:border-primary text-center"
                                      title="Seed mismatches"
                                    />
                                    <input
                                      type="number"
                                      placeholder="30"
                                      value={formData.illuminaclipPalindromeClip}
                                      onChange={(e) => setFormData(prev => ({ 
                                        ...prev, 
                                        illuminaclipPalindromeClip: parseInt(e.target.value) || 30 
                                      }))}
                                      className="px-2 py-1 text-xs border border-slate-300 rounded focus:ring-primary focus:border-primary text-center"
                                      title="Palindrome clip threshold"
                                    />
                                    <input
                                      type="number"
                                      placeholder="10"
                                      value={formData.illuminaclipSimpleClip}
                                      onChange={(e) => setFormData(prev => ({ 
                                        ...prev, 
                                        illuminaclipSimpleClip: parseInt(e.target.value) || 10 
                                      }))}
                                      className="px-2 py-1 text-xs border border-slate-300 rounded focus:ring-primary focus:border-primary text-center"
                                      title="Simple clip threshold"
                                    />
                                  </div>
                                  <div className="grid grid-cols-3 gap-1 mt-1">
                                    <span className="text-xs text-slate-400 text-center">seed</span>
                                    <span className="text-xs text-slate-400 text-center">palindrome</span>
                                    <span className="text-xs text-slate-400 text-center">simple</span>
                                  </div>
                                </div>
                              </div>
                              
                              <p className="text-xs text-slate-500 mt-2">
                                Format: {formData.illuminaclipSeedMismatches}:{formData.illuminaclipPalindromeClip}:{formData.illuminaclipSimpleClip} 
                                - Configure adapter trimming parameters for contamination removal
                              </p>
                            </div>
                          </div>
                        </div>
                        
                        {/* Arrow between steps */}
                        <div className="flex justify-center">
                          <div className="flex flex-col items-center space-y-1 bg-white px-4 py-3 rounded-full border border-slate-200">
                            <ArrowDownIcon className="w-4 h-4 text-slate-400" />
                            <span className="text-xs text-slate-500 font-medium">Then process with</span>
                            <ArrowDownIcon className="w-4 h-4 text-slate-400" />
                          </div>
                        </div>
                        
                        {/* Step 2: PRINSEQ Parameters */}
                        <div className="border border-green-200 rounded-lg p-4 bg-green-50/30">
                          <div className="flex items-center space-x-2 mb-3">
                            <div className="w-6 h-6 bg-green-100 rounded-full flex items-center justify-center">
                              <span className="text-xs font-bold text-green-700">2</span>
                            </div>
                            <h6 className="text-sm font-semibold text-green-800">PRINSEQ Parameters</h6>
                          </div>
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            {selectedTool.parameters.filter(param => param.name.startsWith('prinseq_')).map(param => (
                              <div key={param.name}>
                                <label className="block text-xs font-medium text-slate-600 mb-1">
                                  {param.name.replace('prinseq_', '')}
                                </label>
                                {param.type === 'text' && (
                                  <input
                                    type="text"
                                    value={step.toolParameters[param.name] || param.default}
                                    onChange={(e) => updateToolParameter(step.id, param.name, e.target.value)}
                                    className="w-full px-2 py-1 text-sm border border-slate-300 rounded focus:ring-primary focus:border-primary"
                                  />
                                )}
                                {param.type === 'number' && (
                                  <input
                                    type="number"
                                    value={step.toolParameters[param.name] || param.default}
                                    onChange={(e) => updateToolParameter(step.id, param.name, parseFloat(e.target.value) || param.default)}
                                    className="w-full px-2 py-1 text-sm border border-slate-300 rounded focus:ring-primary focus:border-primary"
                                  />
                                )}
                                <p className="text-xs text-slate-500 mt-1">{param.description}</p>
                              </div>
                            ))}
                          </div>
                        </div>
                      </div>
                    ) : (
                      /* Regular Parameters Layout */
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        {selectedTool.parameters.map(param => (
                          <div key={param.name}>
                            <label className="block text-xs font-medium text-slate-600 mb-1">
                              {param.name}
                            </label>
                            {param.type === 'text' && (
                              <input
                                type="text"
                                value={step.toolParameters[param.name] || param.default}
                                onChange={(e) => updateToolParameter(step.id, param.name, e.target.value)}
                                className="w-full px-2 py-1 text-sm border border-slate-300 rounded focus:ring-primary focus:border-primary"
                              />
                            )}
                            {param.type === 'number' && (
                              <input
                                type="number"
                                value={step.toolParameters[param.name] || param.default}
                                onChange={(e) => updateToolParameter(step.id, param.name, parseFloat(e.target.value) || param.default)}
                                className="w-full px-2 py-1 text-sm border border-slate-300 rounded focus:ring-primary focus:border-primary"
                              />
                            )}
                            {param.type === 'boolean' && (
                              <input
                                type="checkbox"
                                checked={step.toolParameters[param.name] !== undefined ? step.toolParameters[param.name] : param.default}
                                onChange={(e) => updateToolParameter(step.id, param.name, e.target.checked)}
                                className="w-4 h-4 text-primary focus:ring-primary border-slate-300 rounded"
                              />
                            )}
                            {param.type === 'select' && param.options && (
                              <select
                                value={step.toolParameters[param.name] || param.default}
                                onChange={(e) => updateToolParameter(step.id, param.name, e.target.value)}
                                className="w-full px-2 py-1 text-sm border border-slate-300 rounded focus:ring-primary focus:border-primary"
                              >
                                {param.options.map(option => (
                                  <option key={option} value={option}>
                                    {option}
                                  </option>
                                ))}
                              </select>
                            )}
                            <p className="text-xs text-slate-500 mt-1">{param.description}</p>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          );
        })}
        {renderGSEASetup()}
      </div>
    </div>
    );
  };

  // Helper function to get pipeline step icons
  const getPipelineStepIcon = (stepId: string) => {
    switch (stepId) {
      case 'qc':
        return <QCIcon className="w-6 h-6 text-blue-600" />;
      case 'clean':
        return <CleanIcon className="w-6 h-6 text-green-600" />;
      case 'alignment':
        return <AlignmentIcon className="w-6 h-6 text-purple-600" />;
      case 'count':
        return <CountIcon className="w-6 h-6 text-amber-600" />;
      case 'deg':
        return <DEGIcon className="w-6 h-6 text-red-600" />;
      default:
        return <DocumentIcon className="w-6 h-6 text-slate-600" />;
    }
  };

  return (
    <>
      <style>{`
        @keyframes invalid-name-hint-blink {
          0%, 100% { opacity: 1; transform: translateY(0); }
          50% { opacity: 0.35; transform: translateY(-1px); }
        }
      `}</style>
      {/* Main Modal */}
      <Modal 
        isOpen={isOpen} 
        onClose={handleClose} 
        title={`Create New Workbench - Step ${currentStep} of 3`}
        size="lg"
        allowBackgroundClose={false}
      >
        <div className={currentStep === 1 ? 'min-h-[680px]' : ''}>
          {currentStep === 1 ? renderStep1() : currentStep === 2 ? renderStep2() : renderStep3()}
        </div>
        
        <div className="mt-8 flex justify-between">
          <div>
            {currentStep > 1 && (
              <button 
                onClick={handleBack}
                className="px-4 py-2 text-sm font-semibold bg-slate-200 text-slate-700 rounded-lg hover:bg-slate-300"
              >
                Back
              </button>
            )}
          </div>
          <div className="flex space-x-3">
            <button
              onClick={handleClose}
              className="px-4 py-2 text-sm font-semibold bg-slate-200 text-slate-700 rounded-lg hover:bg-slate-300"
            >
              Cancel
            </button>
            {(() => {
              const hasUploadingFiles = Array.isArray(formData.uploadedFiles) &&
                formData.uploadedFiles.some(f => f.uploadStatus === 'uploading');
              const isDisabled = isCreating || hasUploadingFiles;

              return (
                <div className="relative group">
                  <button
                    onClick={handleNext}
                    disabled={isDisabled}
                    className="px-4 py-2 text-sm font-semibold bg-primary text-white rounded-lg hover:bg-primary-dark disabled:opacity-50 disabled:cursor-not-allowed flex items-center space-x-2"
                  >
                    {isCreating && (
                      <div className="animate-spin w-4 h-4 border-2 border-white border-t-transparent rounded-full"></div>
                    )}
                    <span>
                      {currentStep === 1 ? 'Next' : currentStep === 2 ? 'Next' : isCreating ? 'Creating...' : 'Create Workbench'}
                    </span>
                  </button>
                  {hasUploadingFiles && !isCreating && (
                    <div className="absolute bottom-full right-0 mb-2 px-3 py-2 bg-slate-800 text-white text-xs rounded-lg whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none">
                      Waiting for file upload to complete...
                      <div className="absolute top-full right-4 -mt-1 border-4 border-transparent border-t-slate-800"></div>
                    </div>
                  )}
                </div>
              );
            })()}
          </div>
        </div>
      </Modal>

      {/* Confirmation Modal for Layout Change */}
      <ConfirmationModal
        isOpen={showConfirmModal}
        onConfirm={handleConfirmLayoutChange}
        onCancel={handleCancelLayoutChange}
        title="Change Layout?"
        message={`Switching to ${pendingLayout === 'se' ? 'Single-End' : 'Paired-End'} will reset the current file mappings. Do you want to continue?`}
        confirmText="Change Layout"
        cancelText="Cancel"
      />

      {/* Upload Cancel Confirmation Modal */}
      <ConfirmationModal
        isOpen={showUploadCancelModal}
        onConfirm={() => {
          setShowUploadCancelModal(false);
          performClose();
        }}
        onCancel={() => setShowUploadCancelModal(false)}
        title="Cancel Workbench Creation?"
        message={(() => {
          const uploadingCount = formData.uploadedFiles?.filter(f => f.uploadStatus === 'uploading').length || 0;
          const completedCount = formData.uploadedFiles?.filter(f => f.uploadStatus === 'completed').length || 0;
          const totalCount = uploadingCount + completedCount;

          if (uploadingCount > 0 && completedCount > 0) {
            return `You have ${uploadingCount} file(s) uploading and ${completedCount} file(s) already uploaded. If you cancel now, all uploads will be stopped and files will be removed.`;
          } else if (uploadingCount > 0) {
            return `Currently ${uploadingCount} file(s) are being uploaded. If you cancel now, all uploads will be stopped and files will be removed.`;
          } else {
            return `You have ${completedCount} file(s) uploaded. If you cancel now, all uploaded files will be removed.`;
          }
        })()}
        confirmText="Yes"
        cancelText="No"
      />

      {/* Long-read Validation Modal */}
      <LongReadValidationModal
        isOpen={showLongReadModal}
        onClose={() => {
          setShowLongReadModal(false);
          setLongReadValidation(null);
        }}
        data={longReadValidation}
      />

      {/* Alert Modal */}
      <AlertModal
        isOpen={showAlertModal}
        onClose={() => setShowAlertModal(false)}
        title={alertTitle}
        message={alertMessage}
      />
    </>
  );
}

const PlusIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
  </svg>
);

const TrashIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
  </svg>
);

const CheckIcon = ({ className = "w-4 h-4" }: { className?: string }) => (
  <svg xmlns="http://www.w3.org/2000/svg" className={className} viewBox="0 0 20 20" fill="currentColor">
    <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
  </svg>
);

const XIcon = ({ className = "w-4 h-4" }: { className?: string }) => (
  <svg xmlns="http://www.w3.org/2000/svg" className={className} viewBox="0 0 20 20" fill="currentColor">
    <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
  </svg>
);

const UploadIcon = ({ className = "w-4 h-4" }: { className?: string }) => (
  <svg xmlns="http://www.w3.org/2000/svg" className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
  </svg>
);

const DocumentIcon = ({ className = "w-4 h-4" }: { className?: string }) => (
  <svg xmlns="http://www.w3.org/2000/svg" className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
  </svg>
);

// Confirmation Modal Component
interface ConfirmationModalProps {
  isOpen: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  title: string;
  message: string;
  confirmText: string;
  cancelText: string;
}

const ConfirmationModal = ({ 
  isOpen, 
  onConfirm, 
  onCancel, 
  title, 
  message, 
  confirmText, 
  cancelText 
}: ConfirmationModalProps) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-60 z-[60] flex justify-center items-center animate-in fade-in duration-200">
      <div 
        className={`
          bg-white rounded-2xl shadow-2xl w-full max-w-md mx-4 
          transform transition-all duration-300 ease-out
          animate-in zoom-in-75 slide-in-from-bottom-4
          ${isOpen ? 'scale-100 opacity-100' : 'scale-75 opacity-0'}
        `}
      >
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-200">
          <div className="flex items-center space-x-3">
            <div className="flex-shrink-0 w-8 h-8 bg-amber-100 rounded-full flex items-center justify-center">
              <WarningIcon className="w-5 h-5 text-amber-600" />
            </div>
            <h3 className="text-lg font-semibold text-slate-800">{title}</h3>
          </div>
        </div>
        
        {/* Content */}
        <div className="px-6 py-4">
          <p className="text-sm text-slate-600 leading-relaxed">
            {message}
          </p>
        </div>
        
        {/* Actions */}
        <div className="px-6 py-4 bg-slate-50 rounded-b-2xl flex justify-end space-x-3">
          <button
            onClick={onCancel}
            className="px-4 py-2 text-sm font-medium text-slate-700 bg-white border border-slate-300 rounded-lg hover:bg-slate-50 transition-colors"
          >
            {cancelText}
          </button>
          <button
            onClick={onConfirm}
            className="px-4 py-2 text-sm font-medium text-white bg-amber-600 rounded-lg hover:bg-amber-700 transition-colors"
          >
            {confirmText}
          </button>
        </div>
      </div>
    </div>
  );
};

// Long-read Validation Modal Component
interface LongReadValidationModalProps {
  isOpen: boolean;
  onClose: () => void;
  data: {
    files: Array<{
      run: string;
      platform: string;
      model: string;
      avg_length: number;
      read_class: string;
    }>;
    validation: any;
  } | null;
}

const LongReadValidationModal = ({ isOpen, onClose, data }: LongReadValidationModalProps) => {
  if (!isOpen || !data) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-60 z-[60] flex justify-center items-center animate-in fade-in duration-200">
      <div
        className={`
          bg-white rounded-2xl shadow-2xl w-full max-w-4xl mx-4 max-h-[90vh] overflow-hidden
          transform transition-all duration-300 ease-out
          animate-in zoom-in-75 slide-in-from-bottom-4
          ${isOpen ? 'scale-100 opacity-100' : 'scale-75 opacity-0'}
        `}
      >
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-200 bg-red-50">
          <div className="flex items-center space-x-3">
            <div className="flex-shrink-0 w-10 h-10 bg-red-100 rounded-full flex items-center justify-center">
              <svg className="w-6 h-6 text-red-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
            </div>
            <div>
              <h3 className="text-lg font-semibold text-red-800">Long-read Data Detected</h3>
              <p className="text-sm text-red-600">VizR currently supports only short-read data (Illumina, typically &lt;600bp)</p>
            </div>
          </div>
        </div>

        {/* Summary Stats */}
        <div className="px-6 py-4 bg-slate-50 border-b border-slate-200">
          <div className="grid grid-cols-3 gap-4">
            <div className="text-center">
              <div className="text-2xl font-bold text-slate-800">{data.validation.total_files}</div>
              <div className="text-xs text-slate-600">Total Files</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-red-600">{data.validation.long_read_count}</div>
              <div className="text-xs text-slate-600">Long-read Files</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-green-600">{data.validation.short_read_count}</div>
              <div className="text-xs text-slate-600">Short-read Files</div>
            </div>
          </div>
        </div>

        {/* Table Content */}
        <div className="px-6 py-4 max-h-96 overflow-y-auto">
          <h4 className="text-sm font-semibold text-slate-700 mb-3">Detected Long-read Files:</h4>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-100 sticky top-0">
                <tr>
                  <th className="px-3 py-2 text-left text-xs font-semibold text-slate-700 border-b">#</th>
                  <th className="px-3 py-2 text-left text-xs font-semibold text-slate-700 border-b">Run ID</th>
                  <th className="px-3 py-2 text-left text-xs font-semibold text-slate-700 border-b">Platform</th>
                  <th className="px-3 py-2 text-left text-xs font-semibold text-slate-700 border-b">Model</th>
                  <th className="px-3 py-2 text-right text-xs font-semibold text-slate-700 border-b">Avg Length</th>
                  <th className="px-3 py-2 text-center text-xs font-semibold text-slate-700 border-b">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200">
                {data.files.map((file, index) => (
                  <tr key={file.run} className="hover:bg-slate-50">
                    <td className="px-3 py-2 text-slate-600">{index + 1}</td>
                    <td className="px-3 py-2 font-mono text-xs text-slate-800">{file.run}</td>
                    <td className="px-3 py-2 text-slate-700">{file.platform}</td>
                    <td className="px-3 py-2 text-slate-600 text-xs">{file.model}</td>
                    <td className="px-3 py-2 text-right">
                      <span className="inline-flex items-center px-2 py-1 rounded text-xs font-medium bg-red-100 text-red-700">
                        {file.avg_length}bp
                      </span>
                    </td>
                    <td className="px-3 py-2 text-center">
                      <span className="inline-flex items-center px-2 py-1 rounded text-xs font-medium bg-red-100 text-red-700">
                        LONG
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Footer Message */}
        <div className={`px-6 py-3 border-t ${
          data.validation.short_read_count > 0
            ? 'bg-green-50 border-green-200'
            : 'bg-amber-50 border-amber-200'
        }`}>
          {data.validation.short_read_count > 0 ? (
            <div className="flex items-start space-x-2">
              <svg className="w-5 h-5 text-green-600 flex-shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <div>
                <p className="text-sm text-green-800 font-medium">
                  Good news! {data.validation.short_read_count} compatible short-read file(s) found.
                </p>
                <p className="text-xs text-green-700 mt-1">
                  Long-read files have been automatically excluded. You can proceed with the {data.validation.short_read_count} short-read file(s).
                </p>
              </div>
            </div>
          ) : (
            <p className="text-sm text-amber-800">
              <strong>Note:</strong> This BioProject contains only long-read data. Please use a different BioProject with Illumina short-read data.
            </p>
          )}
        </div>

        {/* Actions */}
        <div className="px-6 py-4 bg-slate-50 rounded-b-2xl flex justify-end border-t border-slate-200">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 transition-colors"
          >
            {data.validation.short_read_count > 0 ? 'Continue with Short-read Files' : 'Close'}
          </button>
        </div>
      </div>
    </div>
  );
};

// Alert Modal Component
interface AlertModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  message: string;
}

const AlertModal = ({ isOpen, onClose, title, message }: AlertModalProps) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-60 z-[60] flex justify-center items-center animate-in fade-in duration-200">
      <div 
        className={`
          bg-white rounded-2xl shadow-2xl w-full max-w-md mx-4 
          transform transition-all duration-300 ease-out
          animate-in zoom-in-75 slide-in-from-bottom-4
          ${isOpen ? 'scale-100 opacity-100' : 'scale-75 opacity-0'}
        `}
      >
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-200">
          <div className="flex items-center space-x-3">
            <div className="flex-shrink-0 w-8 h-8 bg-blue-100 rounded-full flex items-center justify-center">
              <InfoIcon className="w-5 h-5 text-blue-600" />
            </div>
            <h3 className="text-lg font-semibold text-slate-800">{title}</h3>
          </div>
        </div>
        
        {/* Content */}
        <div className="px-6 py-4">
          <p className="text-sm text-slate-600 leading-relaxed">
            {message}
          </p>
        </div>
        
        {/* Actions */}
        <div className="px-6 py-4 bg-slate-50 rounded-b-2xl flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 transition-colors"
          >
            OK
          </button>
        </div>
      </div>
    </div>
  );
};

const InfoIcon = ({ className = "w-5 h-5" }: { className?: string }) => (
  <svg xmlns="http://www.w3.org/2000/svg" className={className} viewBox="0 0 20 20" fill="currentColor">
    <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
  </svg>
);

const WarningIcon = ({ className = "w-5 h-5" }: { className?: string }) => (
  <svg xmlns="http://www.w3.org/2000/svg" className={className} viewBox="0 0 20 20" fill="currentColor">
    <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
  </svg>
);

// Pipeline Step Icons
const QCIcon = ({ className = "w-6 h-6" }: { className?: string }) => (
  <svg xmlns="http://www.w3.org/2000/svg" className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
  </svg>
);

const CleanIcon = ({ className = "w-6 h-6" }: { className?: string }) => (
  <svg xmlns="http://www.w3.org/2000/svg" className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.828 14.828a4 4 0 01-5.656 0M9 10h1.586a1 1 0 01.707.293l4.414 4.414a1 1 0 01.293.707V16a1 1 0 01-1 1h-1a1 1 0 01-.707-.293L9 12.414V10z" />
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 10V8a1 1 0 011-1h1.586a1 1 0 01.707.293l2.414 2.414a1 1 0 01.293.707V12a1 1 0 01-1 1h-1.586a1 1 0 01-.707-.293L9 10z" />
  </svg>
);

const AlignmentIcon = ({ className = "w-6 h-6" }: { className?: string }) => (
  <svg xmlns="http://www.w3.org/2000/svg" className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 3C8.5 3 6 5.5 6 9c0 2.5 1.5 4.5 3 6 1.5 1.5 3 3 3 6 0-3 1.5-4.5 3-6 1.5-1.5 3-3.5 3-6 0-3.5-2.5-6-6-6z" />
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 9h6M10.5 12h3M9 15h6" />
  </svg>
);

const CountIcon = ({ className = "w-6 h-6" }: { className?: string }) => (
  <svg xmlns="http://www.w3.org/2000/svg" className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <rect x="2" y="4" width="20" height="16" rx="2" strokeWidth={2} />
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 8h2M6 12h2M6 16h2M10 8h2M10 12h2M10 16h2M14 8h2M14 12h2M14 16h2M18 8h2M18 12h2" />
  </svg>
);

const DEGIcon = ({ className = "w-6 h-6" }: { className?: string }) => (
  <svg xmlns="http://www.w3.org/2000/svg" className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
  </svg>
);

const ArrowRightIcon = ({ className = "w-4 h-4" }: { className?: string }) => (
  <svg xmlns="http://www.w3.org/2000/svg" className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
  </svg>
);

const ArrowDownIcon = ({ className = "w-4 h-4" }: { className?: string }) => (
  <svg xmlns="http://www.w3.org/2000/svg" className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 14l-7 7m0 0l-7-7m7 7V3" />
  </svg>
);

