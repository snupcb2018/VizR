
// User types
export interface User {
  id: number;
  username: string;
  email: string;
  full_name?: string;
  created_at: string;
}

// Share user type (for share modal)
export interface ShareUser {
  id: number;
  username: string;
  email: string;
  full_name?: string;
}

export interface LoginCredentials {
  username: string;
  password: string;
}

export interface RegisterData {
  username: string;
  email: string;
  password: string;
  full_name?: string;
}

// Workbench types
export enum WorkbenchStatus {
  pending = 'pending',
  running = 'running',
  completed = 'completed',
  failed = 'failed',
}

export interface Workbench {
  id: number;
  name: string;
  description?: string;
  species: string;
  source_mode?: 'raw' | 'existing_workbench' | 'matrix_files';
  has_tpm_matrix?: boolean;
  has_gsea_results?: boolean;
  status: WorkbenchStatus;
  user_id: number;
  created_at: string;
  updated_at: string;
  raw_files_count?: number;
  samples_count?: number;
  shared_users?: number[];  // List of user IDs that this workbench is shared with
  is_owner?: boolean;        // True if current user is the owner
  permission?: 'owner' | 'shared';  // Current user's permission level
  created_by?: string;       // Owner username for display
}

export interface WorkbenchCreateData {
  name: string;
  description?: string;
  species: string;
}

// Raw data types
export interface RawDataFile {
  id: number;
  workbench_id: number;
  file_name: string;
  file_path: string;
  file_size: number;
  file_type: string;
  md5_checksum?: string;
  data_source: 'upload' | 'ncbi' | 'server';
  ncbi_bioproject?: string;
  created_at: string;
}

// Sample types
export interface Sample {
  id: number;
  workbench_id: number;
  sample_name: string;
  group_name?: string;
  replicate_number?: number;
  description?: string;
  created_at: string;
}

// Pipeline types
export interface PipelineExecution {
  id: number;
  workbench_id: number;
  pipeline_type: string;
  status: WorkbenchStatus;
  started_at?: string;
  completed_at?: string;
  error_message?: string;
  log_file_path?: string;
  created_at: string;
  updated_at: string;
}

// Pipeline Job Status
export interface PipelineJobStatus {
  job_id: string;
  workbench_id: number;
  workbench_name: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  total_steps: number;
  completed_steps: number;
  failed_steps: number;
  progress_percentage: number;
  current_step: string | null;
  started_at: string | null;
  completed_at: string | null;
  estimated_duration: number | null;
  actual_duration: number | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  steps: StepDetail[];
}

// Pipeline Step Detail
export interface StepDetail {
  step_id?: string;  // Legacy field (kept for backward compatibility)
  step: string;      // Actual field name used by backend
  step_name?: string;
  tool_name?: string;
  tool?: string;     // Actual field name used by backend
  step_order?: number;
  status?: 'pending' | 'running' | 'completed' | 'failed';
  depends_on?: string[];
  input_files?: string[];
  output_files?: string[];
  description?: string;  // Added: description field from backend
  parameters?: Record<string, any>;
  started_at?: string;
  completed_at?: string;
  duration_seconds?: number;
  exit_code?: number;
  error_message?: string;
  retry_count?: number;
  created_at?: string;
  updated_at?: string;
}

// Pipeline Step Status for UI
export type PipelineStepStatus = 'pending' | 'running' | 'completed' | 'failed';

// QC types
export interface QCResult {
  id: number;
  workbench_id: number;
  sample_name: string;
  tool_name: string;
  result_data: string; // JSON string
  html_report_path?: string;
  created_at: string;
}

// Alignment types
export interface AlignmentResult {
  id: number;
  workbench_id: number;
  sample_name: string;
  total_reads: number;
  mapped_reads: number;
  uniquely_mapped_reads: number;
  multi_mapped_reads: number;
  unmapped_reads: number;
  mapping_rate: number;
  unique_mapping_rate: number;
  exonic_reads?: number;
  exonic_rate?: number;
  created_at: string;
}

// Gene expression types
export interface GeneCount {
  id: number;
  workbench_id: number;
  gene_id: string;
  sample_id: number;
  raw_count?: number;
  tpm?: number;
  tmm?: number;
  fpkm?: number;
  created_at: string;
}

// DEG types
export interface DEGAnalysis {
  id: number;
  workbench_id: number;
  comparison_name: string;
  condition1: string;
  condition2: string;
  method: string;
  created_at: string;
}

export interface DEGResult {
  id: number;
  deg_analysis_id: number;
  gene_id: string;
  log_fc: number;
  log_cpm: number;
  p_value: number;
  fdr: number;
  is_significant: boolean;
  created_at: string;
}

// Heatmap types
export interface Heatmap {
  id: number;
  workbench_id: number;
  title: string;
  description?: string;
  gene_list: string; // JSON array of gene IDs
  clustering_method: string;
  color_scheme: string; // JSON object for color settings
  created_by: number;
  created_at: string;
}

// Dashboard types
export interface DashboardStats {
  total_workbenches: number;
  active_workbenches: number;
  completed_workbenches: number;
  failed_workbenches: number;
  pending_workbenches: number;
}

// API response types
export interface APIResponse<T> {
  message?: string;
  error?: string;
  data?: T;
}

export interface LoginResponse {
  message: string;
  user: User;
}

export interface RegisterResponse {
  message: string;
  user: User;
}

// File upload types
export interface FileUpload {
  id: number;
  workbench_id?: number;
  original_filename: string;
  stored_filename: string;
  file_path: string;
  file_size: number;
  mime_type?: string;
  upload_status: 'uploading' | 'completed' | 'failed';
  error_message?: string;
  created_at: string;
}

// NCBI download types
export interface NCBIDownload {
  id: number;
  workbench_id?: number;
  bioproject_id: string;
  download_status: 'pending' | 'downloading' | 'completed' | 'failed';
  progress_percentage: number;
  downloaded_files_count: number;
  total_files_count: number;
  error_message?: string;
  started_at?: string;
  completed_at?: string;
  created_at: string;
}

// Clustering types
export interface ClusterParams {
  pValue: number;
  foldChange: number;
  ptree: number;
}

export interface ClusterInfo {
  id: string;
  gene_count: number;
  file_name: string;
}

export interface ClusterPreview {
  id: string;
  gene_count: number;
  samples: string[];
  statistics: {
    mean: number[];
    median: number[];
  };
}

export interface TreeCuttingDendrogramData {
  exists: boolean;
  status: 'available' | 'not_available' | 'insufficient_clusters';
  method?: {
    distance: string;
    linkage: string;
  };
  clusters?: string[];
  samples?: string[];
  leaf_order?: number[];
  dendrogram?: {
    icoord: number[][];
    dcoord: number[][];
    color_list: string[];
  };
  y_range?: {
    min: number;
    max: number;
  };
  cutline?: {
    ptree: number;
    y: number;
  };
}

export interface TreeMergeSpec {
  id: string;
  source_cluster_ids: string[];
  source_item_ids?: string[];
  created_at: number;
}

export interface ClusterGene {
  gene_id: string;
  gene_symbol: string;
  [sampleName: string]: string | number;
}

export interface ClusterStatistics {
  mean: number[];
  median: number[];
  min: number[];
  max: number[];
}

export interface ClusterData {
  cluster_id: string;
  source_cluster_ids?: string[];
  gene_count: number;  // backward compatibility
  total_genes?: number;  // total genes after search filter
  showing_genes?: number;  // genes shown on current page
  current_page?: number;
  total_pages?: number;
  page_size?: number;
  genes: ClusterGene[];
  samples: string[];
  statistics: ClusterStatistics;
  is_search_result?: boolean;
  search_query?: string;
}

export interface ClusteringRunResponse {
  success: boolean;
  clusters: ClusterInfo[];
  total: number;
  output_dir: string;
  error?: string;
}

export interface ClusterListResponse {
  exists: boolean;
  clusters: ClusterInfo[];
  total: number;
}

// Mfuzz Clustering types
export type MfuzzSourceType = 'deg' | 'variance' | 'tmm';

export interface MfuzzParams {
  sourceType: MfuzzSourceType;
  pValue: number | null;
  foldChange: number | null;
  topNGenes: number;
  clusterCount: number;
  mValue: number | null;
  minMembership: number;
}

export interface MfuzzClusterInfo {
  id: number;
  gene_count: number;
  file_name: string;
}

export interface MfuzzClusterPreview {
  id: number;
  gene_count: number;
  samples: string[];
  statistics: {
    mean: number[];
    median: number[];
  };
}

export interface MfuzzGene {
  gene_id: string;
  gene_symbol: string;
  membership: number;
  [sampleName: string]: string | number;
}

export interface MfuzzClusterData {
  cluster_id: number;
  gene_count: number;
  genes: MfuzzGene[];
  samples: string[];
}

export interface MfuzzRunResponse {
  success: boolean;
  clusters: MfuzzClusterInfo[];
  total: number;
  output_dir: string;
  parameters: {
    source_type: MfuzzSourceType;
    cluster_count: number;
    m_value: number | null;
    min_membership: number;
    p_value?: number | null;
    fold_change?: number | null;
    top_n_genes?: number | null;
  };
  error?: string;
}

export interface MfuzzClusterListResponse {
  exists: boolean;
  clusters: MfuzzClusterInfo[];
  total: number;
  parameters: {
    source_type: MfuzzSourceType;
    cluster_count: number;
    m_value: number | null;
    min_membership: number;
    p_value?: number | null;
    fold_change?: number | null;
    top_n_genes?: number | null;
  };
}

// WGCNA Clustering types
export type WgcnaSourceType = 'deg' | 'variance' | 'tmm';

export interface WgcnaParams {
  sourceType: WgcnaSourceType;
  pValue?: number | null;
  foldChange?: number | null;
  topNGenes: number;
  softPower: 'auto' | number;
  minModuleSize: number;
  deepSplit: number;
  mergeCutHeight: number;
}

export interface WgcnaModuleInfo {
  id: string;           // Module color (e.g., "turquoise", "blue")
  gene_count: number;
  file_name: string;
}

export interface WgcnaModulePreview {
  id: string;
  gene_count: number;
  samples: string[];
  statistics: {
    mean: number[];
    median: number[];
  };
}

export interface WgcnaGene {
  gene_id: string;
  gene_symbol: string;
  module_membership: number;    // kME value
  [sampleName: string]: string | number;
}

export interface WgcnaModuleData {
  module_id: string;
  gene_count: number;
  genes: WgcnaGene[];
  samples: string[];
  eigengene_values: number[];  // Module eigengene values for each sample
}

export interface WgcnaRunResponse {
  success: boolean;
  modules: WgcnaModuleInfo[];
  total: number;
  output_dir: string;
  parameters: {
    source_type: WgcnaSourceType;
    soft_power: 'auto' | number;
    min_module_size: number;
    deep_split: number;
    merge_cut_height: number;
    p_value?: number | null;
    fold_change?: number | null;
    top_n_genes?: number | null;
  };
  error?: string;
}

export interface WgcnaModuleListResponse {
  exists: boolean;
  modules: WgcnaModuleInfo[];
  total: number;
  parameters: {
    source_type: WgcnaSourceType;
    soft_power: 'auto' | number;
    min_module_size: number;
    deep_split: number;
    merge_cut_height: number;
    p_value?: number | null;
    fold_change?: number | null;
    top_n_genes?: number | null;
  };
}

// Navigation types
export type PageType = 'dashboard' | 'settings';
export type WorkbenchTab =
  | 'overview'
  | 'rawdata'
  | 'qc'
  | 'preprocessing'
  | 'alignment'
  | 'count'
  | 'deg'
  | 'pca'
  | 'clustering'
  | 'heatmap'
  | 'venndiagram';

export interface NavigationState {
  page: PageType | 'workbench';
  workbenchId?: number;
  tab?: WorkbenchTab;
}


