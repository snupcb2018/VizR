import React, { useState, useEffect } from 'react';
import Modal from './Modal';
import { apiService } from '../services/api';

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

interface EditPipelineModalProps {
  isOpen: boolean;
  onClose: () => void;
  workbenchId: number;
  currentPipelineSteps: any[];
  species: string;
  sourceMode?: 'raw' | 'existing_workbench' | 'matrix_files';
  layout?: string;
  currentReferenceSet: string;
  onUpdate: () => void;
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
const IMPORTED_LOCKED_STEP_IDS = new Set(['qc', 'clean', 'quantification']);

export default function EditPipelineModal({
  isOpen,
  onClose,
  workbenchId,
  currentPipelineSteps,
  species,
  sourceMode,
  layout,
  currentReferenceSet,
  onUpdate
}: EditPipelineModalProps): React.ReactNode {
  const [pipelineSteps, setPipelineSteps] = useState<PipelineStep[]>([]);
  const [importedCountStep, setImportedCountStep] = useState<any | null>(null);
  const [importedWorkbenchType, setImportedWorkbenchType] = useState<'existing_workbench' | 'matrix_files' | null>(null);
  const [referenceSet, setReferenceSet] = useState('TAIR10');
  const [availableReferenceSets, setAvailableReferenceSets] = useState<Array<{ name: string; species: string }>>([]);
  const [isLoadingReferences, setIsLoadingReferences] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  // Initialize reference set when modal opens or currentReferenceSet changes
  useEffect(() => {
    if (isOpen && currentReferenceSet) {
      setReferenceSet(currentReferenceSet);
    }
  }, [isOpen, currentReferenceSet]);

  // Adapter settings (for Trimmomatic)
  const [trimmomaticAdapter, setTrimmomaticAdapter] = useState('TruSeq3');
  const [illuminaclipSeedMismatches, setIlluminaclipSeedMismatches] = useState(2);
  const [illuminaclipPalindromeClip, setIlluminaclipPalindromeClip] = useState(30);
  const [illuminaclipSimpleClip, setIlluminaclipSimpleClip] = useState(10);

  useEffect(() => {
    if (String(layout || '').toLowerCase() === 'se' && trimmomaticAdapter === 'NexteraPE') {
      setTrimmomaticAdapter('TruSeq3');
    }
  }, [layout, trimmomaticAdapter]);

  // Alert state
  const [showAlert, setShowAlert] = useState(false);
  const [alertTitle, setAlertTitle] = useState('');
  const [alertMessage, setAlertMessage] = useState('');

  // Load reference sets when modal opens
  useEffect(() => {
    if (!isOpen) return;

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
        setAvailableReferenceSets([{ name: 'TAIR10', species: 'arabidopsis' }]);
      } finally {
        setIsLoadingReferences(false);
      }
    };

    loadReferenceSets();
  }, [isOpen]);

  // Initialize pipeline steps from current config
  useEffect(() => {

    if (!isOpen || currentPipelineSteps.length === 0) {
      return;
    }

    const currentImportedCountStep =
      currentPipelineSteps.find(step => step?.step === 'count' && step?.tool === 'imported_counts') ||
      currentPipelineSteps.find(step => step?.step === 'count' && step?.tool === 'imported_matrix_files') ||
      null;
    const hasImportedLockedMetadata = currentPipelineSteps.some(step =>
      Boolean(step?.parameters?.disabled) ||
      typeof step?.parameters?.locked_reason === 'string'
    );
    setImportedCountStep(currentImportedCountStep);
    setImportedWorkbenchType(
      sourceMode === 'existing_workbench'
        ? 'existing_workbench'
        : sourceMode === 'matrix_files'
          ? 'matrix_files'
        : currentImportedCountStep?.tool === 'imported_counts'
        ? 'existing_workbench'
        : currentImportedCountStep?.tool === 'imported_matrix_files'
          ? 'matrix_files'
          : hasImportedLockedMetadata
            ? 'existing_workbench'
          : null
    );

    // Define available tools for each step (same as CreateWorkbenchModal)
    const stepsDefinition: PipelineStep[] = [
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
            id: 'multiqc',
            name: 'MultiQC',
            description: 'Aggregate results from bioinformatics analyses',
            parameters: [
              { name: 'title', type: 'text', default: 'MultiQC Report', description: 'Report title' }
            ]
          },
          {
            id: 'fastp',
            name: 'fastp',
            description: 'All-in-one preprocessing for FastQ files',
            parameters: [
              { name: 'threads', type: 'number', default: 4, description: 'Number of threads' },
              { name: 'qualified_quality_phred', type: 'number', default: 15, description: 'Quality threshold' }
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
            name: 'Trimmomatic → PRINSEQ',
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
          },
          {
            id: 'none',
            name: 'Skip Cleaning',
            description: 'Use raw data without cleaning',
            parameters: []
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
          },
          {
            id: 'none',
            name: 'Skip DEG Analysis',
            description: 'Skip differential expression analysis',
            parameters: []
          }
        ],
        toolParameters: { fdr: 0.05, logfc: 1, gsea_enabled: true, gsea_databases: DEFAULT_GSEA_DATABASES }
      }
    ];

    // Map current pipeline steps to the definition
    currentPipelineSteps.forEach((step, idx) => {
      console.log(`[EditPipelineModal]       ${idx + 1}. step="${step?.step}", tool="${step?.tool}"`);
    });

    const initializedSteps = stepsDefinition.map(stepDef => {
      const currentStep = currentPipelineSteps.find(s => s?.step === stepDef.id);

      if (currentStep) {
        console.log(`[EditPipelineModal]    ├─ ✅ Found config for "${stepDef.id}": tool="${currentStep.tool}"`);
        console.log(`[EditPipelineModal]    │     Parameters:`, currentStep.parameters);

        // Ensure the selected tool exists in available tools
        const toolExists = stepDef.availableTools.some(t => t.id === currentStep.tool);
        const selectedTool = toolExists ? currentStep.tool : stepDef.selectedTool;

        if (!toolExists) {
          console.warn(`[EditPipelineModal]    │     ⚠️ Tool "${currentStep.tool}" not found in available tools, using default "${stepDef.selectedTool}"`);
        }

        return {
          ...stepDef,
          selectedTool: selectedTool,
          toolParameters: {
            ...stepDef.toolParameters,
            ...(currentStep.parameters || {}),
            ...(stepDef.id === 'deg'
              ? {
                  gsea_enabled: normalizeGSEAEnabled((currentStep.parameters || {}).gsea_enabled),
                  gsea_databases: normalizeGSEADatabases((currentStep.parameters || {}).gsea_databases)
                }
              : {})
          }
        };
      }

      // Step not found in current config - check if "none" or "skip" option exists
      const hasNoneOption = stepDef.availableTools.some(t => t.id === 'none');
      const defaultTool = hasNoneOption ? 'none' : stepDef.selectedTool;

      console.log(`[EditPipelineModal]    ├─ ❌ No config for "${stepDef.id}", using tool="${defaultTool}" (hasNoneOption=${hasNoneOption})`);

      return {
        ...stepDef,
        selectedTool: defaultTool
      };
    });

    setPipelineSteps(initializedSteps);

    // Load adapter settings if exists
    const cleanStep = currentPipelineSteps.find(s => s.step === 'clean');
    if (cleanStep && cleanStep.parameters) {

      if (cleanStep.parameters.trimmomaticAdapter) {
        setTrimmomaticAdapter(cleanStep.parameters.trimmomaticAdapter);
      }
      if (cleanStep.parameters.illuminaclipSeedMismatches) {
        setIlluminaclipSeedMismatches(cleanStep.parameters.illuminaclipSeedMismatches);
      }
      if (cleanStep.parameters.illuminaclipPalindromeClip) {
        setIlluminaclipPalindromeClip(cleanStep.parameters.illuminaclipPalindromeClip);
      }
      if (cleanStep.parameters.illuminaclipSimpleClip) {
        setIlluminaclipSimpleClip(cleanStep.parameters.illuminaclipSimpleClip);
      }
    }

  }, [isOpen, currentPipelineSteps, sourceMode]);

  const isImportedWorkbench = importedWorkbenchType !== null;
  const importedLockedReason = 'Managed by imported count matrices';

  const isStepLocked = (stepId: string) => isImportedWorkbench && IMPORTED_LOCKED_STEP_IDS.has(stepId);

  // Update pipeline step tool selection
  const updatePipelineStep = (stepId: string, toolId: string) => {
    if (isStepLocked(stepId)) {
      return;
    }
    setPipelineSteps(prev => prev.map(step => {
      if (step.id === stepId) {
        const selectedTool = step.availableTools.find(tool => tool.id === toolId);
        const defaultParams: { [key: string]: any } = {};

        if (selectedTool) {
          selectedTool.parameters.forEach(param => {
            defaultParams[param.name] = param.default;
          });
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

  // Update tool parameter
  const updateToolParameter = (stepId: string, paramName: string, value: any) => {
    if (isStepLocked(stepId)) {
      return;
    }
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

  const toggleGSEADatabase = (databaseKey: string) => {
    setPipelineSteps(prev => prev.map(step => {
      if (step.id !== 'deg') {
        return step;
      }

      const currentSelection = Array.isArray(step.toolParameters.gsea_databases)
        ? normalizeGSEADatabases(step.toolParameters.gsea_databases)
        : [...DEFAULT_GSEA_DATABASES];

      const nextSelection = currentSelection.includes(databaseKey)
        ? currentSelection.filter((key: string) => key !== databaseKey)
        : [...currentSelection, databaseKey];

      return {
        ...step,
        toolParameters: {
          ...step.toolParameters,
          gsea_databases: nextSelection
        }
      };
    }));
  };

  const toggleGSEAEnabled = (enabled: boolean) => {
    setPipelineSteps(prev => prev.map(step => {
      if (step.id !== 'deg') return step;
      return {
        ...step,
        toolParameters: {
          ...step.toolParameters,
          gsea_enabled: enabled
        }
      };
    }));
  };

  // Save pipeline configuration
  const handleSave = async () => {

    setIsSaving(true);

    try {
      // Prepare pipeline steps payload
      const editableStepsPayload = pipelineSteps
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
              reference_set: referenceSet,
              species: species === 'Arabidopsis thaliana' ? 'arabidopsis' :
                       species === 'Lemna gibba' ? 'lemna_gibba' : 'lemna_minor'
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
          // Add clean_tools array and Trimmomatic adapter settings to Clean step
          if (step.id === 'clean') {
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
                clean_tools: clean_tools,
                trimmomaticAdapter: trimmomaticAdapter,
                illuminaclipSeedMismatches: illuminaclipSeedMismatches,
                illuminaclipPalindromeClip: illuminaclipPalindromeClip,
                illuminaclipSimpleClip: illuminaclipSimpleClip
              }
            };
          }

          // Keep existing structure for other steps
          return {
            step: step.id,
            tool: step.selectedTool,
            description: step.description,
            parameters: step.toolParameters
          };
          })()];
        });

      const stepsPayload = isImportedWorkbench && importedCountStep
        ? [
            {
              step: 'download',
              tool: 'none',
              description: 'Skipped for imported-count workbench',
              parameters: { disabled: true, locked_reason: importedLockedReason }
            },
            {
              step: 'qc',
              tool: 'none',
              description: 'Skipped for imported-count workbench',
              parameters: { disabled: true, locked_reason: importedLockedReason }
            },
            {
              step: 'clean',
              tool: 'none',
              description: 'Skipped for imported-count workbench',
              parameters: { disabled: true, locked_reason: importedLockedReason }
            },
            {
              step: 'alignment',
              tool: 'none',
              description: 'Skipped for imported-count workbench',
              parameters: { disabled: true, locked_reason: importedLockedReason }
            },
            {
              step: 'count',
              tool: importedCountStep.tool,
              description: importedCountStep.description,
              parameters: importedCountStep.parameters || {}
            },
            ...editableStepsPayload.filter(step => step.step === 'deg')
          ]
        : editableStepsPayload;


      // Update pipeline configuration via API
      await apiService.updateWorkbenchPipeline(workbenchId, {
        pipelineSteps: stepsPayload,
        referenceSet: referenceSet
      });


      // Close modal and refresh

      onUpdate();

      onClose();

    } catch (error) {

      setAlertTitle('Update Failed');
      setAlertMessage(`Failed to update pipeline configuration: ${error instanceof Error ? error.message : 'Unknown error'}`);
      setShowAlert(true);
    } finally {
      setIsSaving(false);
    }
  };

  // Helper function to get pipeline step icons
  const getPipelineStepIcon = (stepId: string) => {
    switch (stepId) {
      case 'qc':
        return <QCIcon className="w-6 h-6 text-blue-600" />;
      case 'clean':
        return <CleanIcon className="w-6 h-6 text-green-600" />;
      case 'quantification':
        return <AlignmentIcon className="w-6 h-6 text-purple-600" />;
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

  const isSingleEndLayout = String(layout || '').toLowerCase() === 'se';
  const renderTrimmomaticAdapterControls = (isLocked: boolean) => (
    <div className="md:col-span-2">
      <label className="block text-xs font-medium text-slate-600 mb-2">
        ILLUMINACLIP Configuration
      </label>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className="block text-xs font-medium text-slate-500 mb-1">
            Adapter
          </label>
          <select
            value={trimmomaticAdapter}
            onChange={(e) => setTrimmomaticAdapter(e.target.value)}
            disabled={isLocked}
            className="w-full px-2 py-1 text-sm border border-slate-300 rounded focus:ring-primary focus:border-primary disabled:bg-slate-100 disabled:text-slate-500 disabled:cursor-not-allowed"
          >
            <option value="TruSeq3">TruSeq v3</option>
            <option value="TruSeq2">TruSeq v2</option>
            <option value="NexteraPE" disabled={isSingleEndLayout}>Nextera (PE only)</option>
            <option value="none">None</option>
          </select>
        </div>

        <div>
          <label className="block text-xs font-medium text-slate-500 mb-1">
            Parameters
          </label>
          <div className="grid grid-cols-3 gap-1">
            <input
              type="number"
              placeholder="2"
              value={illuminaclipSeedMismatches}
              onChange={(e) => setIlluminaclipSeedMismatches(parseInt(e.target.value) || 2)}
              disabled={isLocked}
              className="px-2 py-1 text-xs border border-slate-300 rounded focus:ring-primary focus:border-primary text-center disabled:bg-slate-100 disabled:text-slate-500 disabled:cursor-not-allowed"
              title="Seed mismatches"
            />
            <input
              type="number"
              placeholder="30"
              value={illuminaclipPalindromeClip}
              onChange={(e) => setIlluminaclipPalindromeClip(parseInt(e.target.value) || 30)}
              disabled={isLocked}
              className="px-2 py-1 text-xs border border-slate-300 rounded focus:ring-primary focus:border-primary text-center disabled:bg-slate-100 disabled:text-slate-500 disabled:cursor-not-allowed"
              title="Palindrome clip threshold"
            />
            <input
              type="number"
              placeholder="10"
              value={illuminaclipSimpleClip}
              onChange={(e) => setIlluminaclipSimpleClip(parseInt(e.target.value) || 10)}
              disabled={isLocked}
              className="px-2 py-1 text-xs border border-slate-300 rounded focus:ring-primary focus:border-primary text-center disabled:bg-slate-100 disabled:text-slate-500 disabled:cursor-not-allowed"
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
        Format: {illuminaclipSeedMismatches}:{illuminaclipPalindromeClip}:{illuminaclipSimpleClip}
      </p>
    </div>
  );


  return (
    <>
      <Modal
        isOpen={isOpen}
        onClose={onClose}
        title="Edit Pipeline Configuration"
        size="lg"
        allowBackgroundClose={false}
      >
        <div className="space-y-6">
          <div>
            <h3 className="text-lg font-semibold text-slate-800">Pipeline Configuration</h3>
            <p className="text-sm text-slate-500 mt-1">
              Configure tools and parameters for each step of the RNA-seq analysis pipeline
            </p>
          </div>

          {isImportedWorkbench && (
            <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
              This workbench was created from {importedWorkbenchType === 'existing_workbench' ? 'existing workbenches' : 'matrix files'}.
              QC, cleaning, and quantification are locked because imported count matrices already define the upstream processing.
            </div>
          )}

          {/* Reference Set Selection */}
          <div className="border border-blue-200 rounded-lg p-4 bg-blue-50/30">
            <div className="flex items-center space-x-3 mb-3">
              <svg className="w-5 h-5 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              <h4 className="text-sm font-semibold text-blue-900">Reference Genome Settings</h4>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-2">
                  Reference Set
                  <span className="text-red-500 ml-1">*</span>
                </label>
                <select
                  value={referenceSet}
                  onChange={(e) => {
                    setReferenceSet(e.target.value);
                  }}
                  disabled={isLoadingReferences || isImportedWorkbench}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-primary focus:border-primary disabled:bg-slate-100 disabled:cursor-not-allowed"
                  onClick={() => {
                  }}
                >
                  {isLoadingReferences ? (
                    <option>Loading reference sets...</option>
                  ) : (() => {
                    const speciesMap: Record<string, string> = {
                      'Arabidopsis thaliana': 'arabidopsis',
                      'Lemna gibba (Duckweed)': 'lemna_gibba',
                      'Lemna minor (Duckweed)': 'lemna_minor'
                    };

                    const currentSpecies = speciesMap[species] || 'arabidopsis';
                    const filteredReferences = availableReferenceSets.filter(
                      ref => ref.species === currentSpecies
                    );

                    if (filteredReferences.length === 0) {
                      return <option value="">No reference sets available for {species}</option>;
                    }

                    return filteredReferences.map(ref => (
                      <option key={ref.name} value={ref.name}>
                        {ref.name}
                      </option>
                    ));
                  })()}
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-2">
                  Species
                </label>
                <input
                  type="text"
                  value={species}
                  readOnly
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm bg-slate-50 text-slate-600"
                />
              </div>
            </div>
          </div>

          {/* Pipeline Steps */}
          <div className="space-y-6">
            {pipelineSteps.map((step, index) => {
              const selectedTool = step.availableTools.find(tool => tool.id === step.selectedTool);
              const isLocked = isStepLocked(step.id);

              // 🎯 각 스텝 렌더링 시 로그
              console.log(`[EditPipelineModal] 🎯 Rendering step "${step.id}":`);
              console.log(`[EditPipelineModal]    ├─ name: "${step.name}"`);
              console.log(`[EditPipelineModal]    ├─ selectedTool: "${step.selectedTool}"`);
              console.log(`[EditPipelineModal]    ├─ selectedTool object found: ${selectedTool ? 'YES' : 'NO'}`);
              console.log(`[EditPipelineModal]    ├─ availableTools count: ${step.availableTools.length}`);
              console.log(`[EditPipelineModal]    ├─ availableTools ids: [${step.availableTools.map(t => t.id).join(', ')}]`);
              console.log(`[EditPipelineModal]    └─ parameters:`, step.toolParameters);

              return (
                <div key={step.id} className={`border rounded-xl overflow-hidden ${isLocked ? 'border-amber-200 bg-amber-50/20' : 'border-slate-200'}`}>
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
                        {isLocked && (
                          <p className="mt-2 text-xs font-medium text-amber-700">{importedLockedReason}</p>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Tool Selection */}
                  <div className={`px-6 py-4 ${isLocked ? 'bg-slate-50/80 pointer-events-none' : 'bg-white'}`}>
                    <div className={`grid gap-3 ${step.id === 'clean' ? 'grid-cols-1 md:grid-cols-2' : 'grid-cols-1 md:grid-cols-3'}`}>
                      {step.availableTools.map(tool => {
                        const isSelected = step.selectedTool === tool.id;
                        console.log(`[EditPipelineModal]       🔘 Tool button "${tool.id}": selected=${isSelected}`);

                        return (
                          <button
                            key={tool.id}
                            onClick={() => {
                              console.log(`[EditPipelineModal] 🖱️ Tool button clicked: step="${step.id}", tool="${tool.id}"`);
                              updatePipelineStep(step.id, tool.id);
                            }}
                            disabled={isLocked}
                            className={`
                              p-4 text-left border-2 rounded-lg transition-all duration-200
                              ${isLocked
                                ? 'border-slate-200 bg-white shadow-none'
                                : isSelected
                                ? 'border-primary bg-primary/5 shadow-sm'
                                : 'border-slate-200 hover:border-slate-300 hover:bg-slate-50'
                              }
                              ${isLocked ? 'cursor-not-allowed opacity-60 hover:border-slate-200 hover:bg-white' : ''}
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

                          {/* Sequential Processing Visual */}
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
                        );
                      })}
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
                                        disabled={isLocked}
                                        className="w-full px-2 py-1 text-sm border border-slate-300 rounded focus:ring-primary focus:border-primary disabled:bg-slate-100 disabled:text-slate-500 disabled:cursor-not-allowed"
                                      />
                                    )}
                                    {param.type === 'number' && (
                                      <input
                                        type="number"
                                        value={step.toolParameters[param.name] || param.default}
                                        onChange={(e) => updateToolParameter(step.id, param.name, parseFloat(e.target.value) || param.default)}
                                        disabled={isLocked}
                                        className="w-full px-2 py-1 text-sm border border-slate-300 rounded focus:ring-primary focus:border-primary disabled:bg-slate-100 disabled:text-slate-500 disabled:cursor-not-allowed"
                                      />
                                    )}
                                    <p className="text-xs text-slate-500 mt-1">{param.description}</p>
                                  </div>
                                ))}

                                {renderTrimmomaticAdapterControls(isLocked)}
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
                                        disabled={isLocked}
                                        className="w-full px-2 py-1 text-sm border border-slate-300 rounded focus:ring-primary focus:border-primary disabled:bg-slate-100 disabled:text-slate-500 disabled:cursor-not-allowed"
                                      />
                                    )}
                                    {param.type === 'number' && (
                                      <input
                                        type="number"
                                        value={step.toolParameters[param.name] || param.default}
                                        onChange={(e) => updateToolParameter(step.id, param.name, parseFloat(e.target.value) || param.default)}
                                        disabled={isLocked}
                                        className="w-full px-2 py-1 text-sm border border-slate-300 rounded focus:ring-primary focus:border-primary disabled:bg-slate-100 disabled:text-slate-500 disabled:cursor-not-allowed"
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
                                    disabled={isLocked}
                                    className="w-4 h-4 text-primary focus:ring-primary border-slate-300 rounded disabled:cursor-not-allowed"
                                  />
                                )}
                                {param.type === 'select' && param.options && (
                                  <select
                                    value={step.toolParameters[param.name] || param.default}
                                    onChange={(e) => updateToolParameter(step.id, param.name, e.target.value)}
                                    disabled={isLocked}
                                    className="w-full px-2 py-1 text-sm border border-slate-300 rounded focus:ring-primary focus:border-primary disabled:bg-slate-100 disabled:text-slate-500 disabled:cursor-not-allowed"
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
                            {selectedTool.id.includes('trimmomatic') && renderTrimmomaticAdapterControls(isLocked)}
                          </div>
                        )}
                      </div>
                    )}

                    {step.id === 'deg' && step.selectedTool !== 'none' && (
                      <div className="mt-6 border border-emerald-200 rounded-lg overflow-hidden">
                        <div className="bg-emerald-50 px-6 py-4 border-b border-emerald-200">
                          <div className="flex items-center space-x-4">
                            <div className="flex-shrink-0 w-10 h-10 bg-white rounded-lg flex items-center justify-center shadow-sm">
                              <svg xmlns="http://www.w3.org/2000/svg" className="w-6 h-6 text-emerald-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                              </svg>
                            </div>
                            <div className="flex-1">
                              <h5 className="text-base font-semibold text-slate-800">5. GSEA</h5>
                              <p className="text-sm text-slate-500">
                                Select built-in gene set databases to prepare during the final GSEA pipeline step.
                              </p>
                            </div>
                          </div>
                        </div>

                        <div className="p-4 bg-white space-y-4">
                          <label className="flex items-center justify-between gap-4 rounded-lg border border-emerald-200 bg-emerald-50/70 px-4 py-3">
                            <div>
                              <p className="text-sm font-semibold text-slate-800">Enable GSEA</p>
                              <p className="mt-1 text-xs text-slate-500">
                                When disabled, VizR skips the automatic GSEA step and the DEG GSEA tab stays unavailable until prior GSEA results exist.
                              </p>
                            </div>
                            <input
                              type="checkbox"
                              checked={normalizeGSEAEnabled(step.toolParameters.gsea_enabled)}
                              disabled={isLocked}
                              onChange={(event) => toggleGSEAEnabled(event.target.checked)}
                              className="h-4 w-4 rounded border-slate-300 text-primary focus:ring-primary disabled:cursor-not-allowed"
                            />
                          </label>

                          <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
                            <p className="text-sm text-slate-700">
                              Only selected databases will be prepared and precomputed.
                            </p>
                            <p className="mt-1 text-xs text-slate-500">
                              Default selections include the core built-in databases used by VizR.
                            </p>
                          </div>

                          <div className={`grid grid-cols-1 md:grid-cols-2 gap-3 ${normalizeGSEAEnabled(step.toolParameters.gsea_enabled) ? '' : 'opacity-50 pointer-events-none'}`}>
                            {GSEA_DATABASE_OPTIONS.map(option => {
                              const selectedDatabases = Array.isArray(step.toolParameters.gsea_databases)
                                ? normalizeGSEADatabases(step.toolParameters.gsea_databases)
                                : [...DEFAULT_GSEA_DATABASES];
                              const isChecked = selectedDatabases.includes(option.key);

                              return (
                                <button
                                  key={option.key}
                                  type="button"
                                  onClick={() => toggleGSEADatabase(option.key)}
                                  disabled={isLocked}
                                  className={`flex items-center space-x-3 rounded-lg border px-4 py-3 text-left transition-colors ${
                                    isChecked
                                      ? 'border-emerald-300 bg-emerald-50'
                                      : 'border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50'
                                  } ${isLocked ? 'cursor-not-allowed opacity-60 hover:border-slate-200 hover:bg-white' : ''}`}
                                >
                                  <input
                                    type="checkbox"
                                    checked={isChecked}
                                    disabled={isLocked}
                                    onChange={() => {}}
                                    onClick={(event) => {
                                      event.stopPropagation();
                                      toggleGSEADatabase(option.key);
                                    }}
                                    className="h-4 w-4 rounded border-slate-300 text-primary focus:ring-primary"
                                  />
                                  <span className="text-sm font-medium text-slate-800">{option.label}</span>
                                </button>
                              );
                            })}
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Footer */}
        <div className="mt-8 flex justify-end space-x-3">
          <button
            onClick={onClose}
            disabled={isSaving}
            className="px-4 py-2 text-sm font-semibold bg-slate-200 text-slate-700 rounded-lg hover:bg-slate-300 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={isSaving}
            className="px-4 py-2 text-sm font-semibold bg-primary text-white rounded-lg hover:bg-primary-dark disabled:opacity-50 disabled:cursor-not-allowed flex items-center space-x-2"
          >
            {isSaving && (
              <div className="animate-spin w-4 h-4 border-2 border-white border-t-transparent rounded-full"></div>
            )}
            <span>{isSaving ? 'Saving...' : 'Save Changes'}</span>
          </button>
        </div>
      </Modal>

      {/* Alert Modal */}
      {showAlert && (
        <div className="fixed inset-0 bg-black bg-opacity-60 z-[60] flex justify-center items-center">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md mx-4">
            <div className="px-6 py-4 border-b border-slate-200">
              <h3 className="text-lg font-semibold text-slate-800">{alertTitle}</h3>
            </div>
            <div className="px-6 py-4">
              <p className="text-sm text-slate-600">{alertMessage}</p>
            </div>
            <div className="px-6 py-4 bg-slate-50 rounded-b-2xl flex justify-end">
              <button
                onClick={() => setShowAlert(false)}
                className="px-4 py-2 text-sm font-medium text-white bg-primary rounded-lg hover:bg-primary-dark"
              >
                OK
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

// Icon Components
const DocumentIcon = ({ className = "w-4 h-4" }: { className?: string }) => (
  <svg xmlns="http://www.w3.org/2000/svg" className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
  </svg>
);

const QCIcon = ({ className = "w-6 h-6" }: { className?: string }) => (
  <svg xmlns="http://www.w3.org/2000/svg" className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
  </svg>
);

const CleanIcon = ({ className = "w-6 h-6" }: { className?: string }) => (
  <svg xmlns="http://www.w3.org/2000/svg" className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" />
  </svg>
);

const AlignmentIcon = ({ className = "w-6 h-6" }: { className?: string }) => (
  <svg xmlns="http://www.w3.org/2000/svg" className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 10h16M4 14h16M4 18h16" />
  </svg>
);

const CountIcon = ({ className = "w-6 h-6" }: { className?: string }) => (
  <svg xmlns="http://www.w3.org/2000/svg" className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 20l4-16m2 16l4-16M6 9h14M4 15h14" />
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
