/**
 * API Service for VizR Frontend
 * Handles all communication with the Flask backend
 */

import {
  User,
  LoginCredentials,
  RegisterData,
  LoginResponse,
  RegisterResponse,
  Workbench,
  WorkbenchCreateData,
  DashboardStats,
  APIResponse,
  PipelineJobStatus
} from '../types';

const API_BASE_URL = '/api';

class APIError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = 'APIError';
  }
}

class APIService {
  private async fetchJSON<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${API_BASE_URL}${endpoint}`;
    const config: RequestInit = {
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
      credentials: 'include', // Include cookies for session management
      ...options,
    };

    
    try {
      const response = await fetch(url, config);
      const data = await response.json();

      if (!response.ok) {
        throw new APIError(response.status, data.error || 'Request failed');
      }

      return data;
    } catch (error) {
      if (error instanceof APIError) {
        throw error;
      }
      throw new APIError(0, 'Network error occurred');
    }
  }

  // Health check
  async healthCheck(): Promise<{ status: string; timestamp: string; version: string }> {
    return this.fetchJSON('/health');
  }

  // Authentication endpoints
  async login(credentials: LoginCredentials): Promise<LoginResponse> {
    return this.fetchJSON('/auth/login', {
      method: 'POST',
      body: JSON.stringify(credentials),
    });
  }

  async register(userData: RegisterData): Promise<RegisterResponse> {
    return this.fetchJSON('/auth/register', {
      method: 'POST',
      body: JSON.stringify(userData),
    });
  }

  async logout(): Promise<{ message: string }> {
    return this.fetchJSON('/auth/logout', {
      method: 'POST',
    });
  }

  async getProfile(): Promise<{ user: User }> {
    return this.fetchJSON('/auth/profile');
  }

  async updateProfile(profileData: { email: string; full_name: string }): Promise<{ message: string; user: User }> {
    return this.fetchJSON('/auth/profile', {
      method: 'PUT',
      body: JSON.stringify(profileData),
    });
  }

  async changePassword(passwordData: {
    current_password: string;
    new_password: string;
    confirm_password: string;
  }): Promise<{ message: string }> {
    return this.fetchJSON('/auth/change-password', {
      method: 'POST',
      body: JSON.stringify(passwordData),
    });
  }

  // Dashboard endpoints
  async getDashboardStats(): Promise<{ stats: DashboardStats }> {
    return this.fetchJSON('/dashboard/stats');
  }

  async getRecentWorkbenches(): Promise<{ workbenches: Workbench[] }> {
    return this.fetchJSON('/dashboard/recent-workbenches');
  }

  // Workbench endpoints
  async getWorkbenches(): Promise<{ workbenches: Workbench[] }> {
    return this.fetchJSON('/workbenches');
  }

  async createWorkbench(workbenchData: WorkbenchCreateData): Promise<{ message: string; workbench_id: number }> {
    return this.fetchJSON('/workbenches', {
      method: 'POST',
      body: JSON.stringify(workbenchData),
    });
  }

  async getImportWorkbenchSources(species?: string): Promise<{
    sources: Array<{
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
    }>;
  }> {
    const query = species ? `?species=${encodeURIComponent(species)}` : '';
    return this.fetchJSON(`/workbenches/import-sources${query}`);
  }

  async getWorkbench(workbenchId: number): Promise<{
    workbench: Workbench;
    raw_files: any[];
    samples: any[];
    pipeline: any;
  }> {
    return this.fetchJSON(`/workbenches/${workbenchId}`);
  }

  async deleteWorkbench(workbenchId: number, deleteRawData: boolean = false): Promise<{ 
    message: string; 
    workbench_id: number;
    deleted_completely?: boolean;
    raw_data_preserved?: boolean;
  }> {
    return this.fetchJSON(`/workbenches/${workbenchId}`, {
      method: 'DELETE',
      body: JSON.stringify({ delete_raw_data: deleteRawData }),
    });
  }

  // File upload endpoints
  async uploadTempFile(
    file: File,
    onProgress?: (progress: number) => void,
    controller?: AbortController
  ): Promise<{
    message: string;
    temp_upload_id: number;
    temp_filename: string;
    original_filename: string;
    file_size: number;
  }> {
    const formData = new FormData();
    formData.append('file', file);

    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();

      // Connect AbortController to XHR if provided
      if (controller) {
        controller.signal.addEventListener('abort', () => {
          xhr.abort();
        });
      }

      // Progress tracking
      if (onProgress) {
        xhr.upload.addEventListener('progress', (e) => {
          if (e.lengthComputable) {
            const progress = Math.round((e.loaded / e.total) * 100);
            onProgress(progress);
          }
        });
      }

      xhr.addEventListener('load', () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            const result = JSON.parse(xhr.responseText);
            resolve(result);
          } catch (e) {
            console.error(`Failed to parse upload response for ${file.name}:`, e);
            reject(new APIError(xhr.status, 'Invalid response format'));
          }
        } else {
          try {
            const errorData = JSON.parse(xhr.responseText);
            const errorMsg = errorData.error || 'Upload failed';

            // Log validation errors with more detail
            if (xhr.status === 400 && errorData.file_invalid) {
              console.error(`File validation failed for ${file.name}:`, errorMsg);
            } else {
              console.error(`Upload failed for ${file.name} (${xhr.status}):`, errorMsg);
            }

            reject(new APIError(xhr.status, errorMsg));
          } catch (e) {
            console.error(`Upload failed for ${file.name} (${xhr.status}): Unable to parse error`);
            reject(new APIError(xhr.status, 'Upload failed'));
          }
        }
      });

      xhr.addEventListener('error', () => {
        console.error(`Network error uploading ${file.name}`);
        reject(new APIError(0, 'Network error'));
      });

      xhr.addEventListener('abort', () => {
        reject(new APIError(0, 'Upload cancelled'));
      });

      xhr.open('POST', `${API_BASE_URL}/upload/temp`);
      xhr.withCredentials = true;
      xhr.send(formData);
    });
  }

  async deleteTempFile(filename: string): Promise<{ message: string }> {
    const response = await fetch(`${API_BASE_URL}/upload/temp/${encodeURIComponent(filename)}`, {
      method: 'DELETE',
      credentials: 'include',
    });

    if (!response.ok) {
      const errorData = await response.json();
      throw new APIError(response.status, errorData.error || 'Delete failed');
    }

    return response.json();
  }

  async uploadFile(file: File, workbenchId: number): Promise<{
    message: string;
    upload_id: number;
    filename: string;
    file_size: number;
  }> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('workbench_id', workbenchId.toString());

    const response = await fetch(`${API_BASE_URL}/upload`, {
      method: 'POST',
      body: formData,
      credentials: 'include',
    });

    if (!response.ok) {
      const errorData = await response.json();
      throw new APIError(response.status, errorData.error || 'Upload failed');
    }

    return response.json();
  }

  // Pipeline Job Management endpoints
  async createPipelineJob(workbenchId: number): Promise<{
    message: string;
    job_id: string;
    workbench_id: number;
    workbench_name: string;
  }> {
    return this.fetchJSON('/pipeline/jobs', {
      method: 'POST',
      body: JSON.stringify({ workbench_id: workbenchId }),
    });
  }

  async stopAnalysis(workbenchId: number): Promise<{
    success: boolean;
    message: string;
    stopped_jobs: number;
    stopped_workers: number;
    workbench_id: number;
  }> {
    return this.fetchJSON(`/pipeline/workbench/${workbenchId}/stop-analysis`, {
      method: 'POST'
    });
  }

  async getPipelineJobStatus(jobId: string): Promise<PipelineJobStatus> {
    try {
      return await this.fetchJSON(`/pipeline/jobs/${jobId}`);
    } catch (error) {
      // 404 에러인 경우 job이 삭제된 것으로 판단하고 특별 처리
      if (error instanceof APIError && error.status === 404) {
        console.warn(`⚠️ Pipeline job ${jobId} not found (likely deleted). Throwing special error to stop polling.`);
        // 특별한 에러 객체로 polling 중단을 알림
        const deletedJobError = new APIError(404, 'Job deleted or not found');
        (deletedJobError as any).shouldStopPolling = true;
        throw deletedJobError;
      }
      throw error;
    }
  }

  async cancelPipelineJob(jobId: string): Promise<{ message: string }> {
    return this.fetchJSON(`/pipeline/jobs/${jobId}`, {
      method: 'DELETE',
    });
  }

  async listPipelineJobs(workbenchId?: number, status?: string): Promise<any[]> {
    const params = new URLSearchParams();
    if (workbenchId) params.append('workbench_id', workbenchId.toString());
    if (status) params.append('status', status);
    
    const endpoint = params.toString() ? `/pipeline/jobs?${params}` : '/pipeline/jobs';
    return this.fetchJSON(endpoint);
  }

  async getPipelineSystemStatus(): Promise<{
    manager_status: string;
    workers: any;
    job_stats: any;
    queue_stats: any;
    system_resources: any;
    timestamp: string;
  }> {
    return this.fetchJSON('/pipeline/system/status');
  }





  // NCBI endpoints
  async searchNCBIBioproject(bioprojectId: string): Promise<{
    success: boolean;
    bioproject_id: string;
    files: {
      run: string;
      library_layout: string;
      library_strategy: string;
      sample_name: string;
      size_mb: string;
      bases: string;
      spots: string;
      scientific_name: string;
      platform: string;
      model: string;
      avg_length: number;
      read_class: 'SHORT' | 'BORDERLINE' | 'LONG';
    }[];
    total_files: number;
    validation: {
      total_files: number;
      short_read_count: number;
      borderline_count: number;
      long_read_count: number;
      has_long_reads: boolean;
      has_borderline: boolean;
      all_compatible: boolean;
    };
    message: string;
  }> {
    return this.fetchJSON(`/ncbi/search/${bioprojectId}`);
  }


  // Macrogen endpoints
  async fetchMacrogenFileList(reportUrl: string): Promise<{
    success: boolean;
    report_url: string;
    files: {
      name: string;
      sample_name: string;
      size_bytes: number;
      size_mb: string;
      md5: string;
      url: string;
      read_num: number;
    }[];
    total_files: number;
    layout: 'single' | 'paired';
  }> {
    return this.fetchJSON('/macrogen/fetch-file-list', {
      method: 'POST',
      body: JSON.stringify({ report_url: reportUrl }),
    });
  }


  // Utility methods
  formatFileSize(bytes: number): string {
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
    if (bytes === 0) return '0 Bytes';
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return Math.round(bytes / Math.pow(1024, i) * 100) / 100 + ' ' + sizes[i];
  }

  formatDate(dateString: string): string {
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  }

  formatRelativeTime(dateString: string): string {
    const date = new Date(dateString);
    const now = new Date();
    const diffInSeconds = Math.floor((now.getTime() - date.getTime()) / 1000);

    if (diffInSeconds < 60) return 'Just now';
    if (diffInSeconds < 3600) return `${Math.floor(diffInSeconds / 60)} minutes ago`;
    if (diffInSeconds < 86400) return `${Math.floor(diffInSeconds / 3600)} hours ago`;
    if (diffInSeconds < 2592000) return `${Math.floor(diffInSeconds / 86400)} days ago`;
    
    return this.formatDate(dateString);
  }

  // Workbench download progress endpoint
  async fetchWorkbenchDownloadProgress(workbenchId: number): Promise<{
    workbench_id: number;
    workbench_name: string;
    summary: {
      total_files: number;
      downloading_files: number;
      completed_files: number;
      pending_files: number;
      last_updated: number | null;
      total_size: number;
      downloaded_size: number;
    };
    files: Record<string, {
      status: string;
      progress: number;
      file_size: number;
      downloaded_size: number;
      timestamp: number;
    }>;
    overall_status: string;
    last_updated: string | null;
  }> {
    return this.fetchJSON(`/workbenches/${workbenchId}/download-progress`);
  }

  // DEG progress endpoint
  async fetchDEGProgress(workbenchId: number): Promise<{
    status: 'pending' | 'running' | 'completed' | 'failed' | 'not_started';
    tool_name: string | null;
  }> {
    return this.fetchJSON(`/workbenches/${workbenchId}/deg/progress`);
  }

  // DEG comparisons endpoint
  async fetchDEGComparisons(workbenchId: number): Promise<{
    comparisons: Array<{
      name: string;
      tool_name: string;
      file_count: number;
      de_result_file: string;
    }>;
    total: number;
  }> {
    return this.fetchJSON(`/workbenches/${workbenchId}/deg/comparisons`);
  }

  async fetchPrerankedGSEATemplate(
    workbenchId: number,
    params: { comparison_name: string; deg_tool: string }
  ): Promise<{
    ranked_list_text: string;
    gene_count: number;
    comparison_name: string;
    deg_tool: string;
    ranking_metric: string;
  }> {
    const query = new URLSearchParams({
      comparison_name: params.comparison_name,
      deg_tool: params.deg_tool,
    });
    return this.fetchJSON(`/workbenches/${workbenchId}/gsea/preranked-template?${query.toString()}`);
  }

  async fetchBuiltInGSEADatabases(
      workbenchId: number
    ): Promise<{
      species: string;
    databases: Array<{
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
    }>;
    }> {
      return this.fetchJSON(`/workbenches/${workbenchId}/gsea/databases`);
    }

  async fetchPrecomputedGSEAResult(
    workbenchId: number,
    params: {
      comparison_name: string;
      deg_tool: string;
      gene_set_db: string;
    }
  ): Promise<{
    state: 'ready' | 'pending' | 'failed' | 'missing';
    comparison_name: string;
    deg_tool: string;
    gene_set_db: string;
    gene_set_db_label?: string;
    database_metadata?: {
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
    };
    ranking_metric?: string;
    zero_cross_index?: number | null;
    validation?: {
      ranked_gene_count: number;
      tested_gene_sets: number;
      min_overlap: number;
      permutations: number;
    };
    rows?: Array<{
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
    }>;
    message?: string;
    error_message?: string;
  }> {
    const query = new URLSearchParams({
      comparison_name: params.comparison_name,
      deg_tool: params.deg_tool,
      gene_set_db: params.gene_set_db,
    });
    console.log('[VizR][GSEA][API] fetchPrecomputedGSEAResult:request', {
      workbenchId,
      params,
      url: `/workbenches/${workbenchId}/gsea/results?${query.toString()}`,
    });
    const response = await this.fetchJSON(`/workbenches/${workbenchId}/gsea/results?${query.toString()}`);
    console.log('[VizR][GSEA][API] fetchPrecomputedGSEAResult:response', {
      workbenchId,
      state: response?.state,
      rowCount: Array.isArray(response?.rows) ? response.rows.length : null,
      testedGeneSets: response?.validation?.tested_gene_sets ?? null,
      rankedGeneCount: response?.validation?.ranked_gene_count ?? null,
      errorMessage: response?.error_message ?? null,
    });
    return response;
  }

  async fetchGSEAValidationInputs(
    workbenchId: number,
    params: {
      comparison_name: string;
      deg_tool: string;
      gene_set_db: string;
    }
  ): Promise<{
    comparison_name: string;
    deg_tool: string;
    gene_set_db: string;
    gene_set_db_label: string;
    ranking_metric: string;
    ranked_gene_count: number;
    ranked_filename: string;
    ranked_list_text: string;
    gmt_filename: string;
    gmt_text: string;
    readme_filename: string;
    readme_text: string;
  }> {
    const query = new URLSearchParams({
      comparison_name: params.comparison_name,
      deg_tool: params.deg_tool,
      gene_set_db: params.gene_set_db,
    });
    return this.fetchJSON(`/workbenches/${workbenchId}/gsea/validation-inputs?${query.toString()}`);
  }

  async runComparisonGSEA(
      workbenchId: number,
      payload: {
      comparison_name: string;
      deg_tool: string;
      gene_set_db: string;
    }
  ): Promise<{
    comparison_name: string;
    deg_tool: string;
    gene_set_db: string;
    gene_set_db_label: string;
    ranking_metric: string;
    zero_cross_index: number | null;
    validation: {
      ranked_gene_count: number;
      tested_gene_sets: number;
      min_overlap: number;
      permutations: number;
    };
    rows: Array<{
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
    }>;
  }> {
    return this.fetchJSON(`/workbenches/${workbenchId}/gsea/deg-comparison`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async fetchGSEAPlotDetail(
    workbenchId: number,
    payload: {
      comparison_name: string;
      deg_tool: string;
      gene_set_db: string;
      gene_set: string;
    },
    signal?: AbortSignal
  ): Promise<{
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
  }> {
    console.log('[VizR][GSEA][API] fetchGSEAPlotDetail:request', {
      workbenchId,
      payload,
    });
    const response = await this.fetchJSON(`/workbenches/${workbenchId}/gsea/plot-detail`, {
      method: 'POST',
      body: JSON.stringify(payload),
      signal,
    });
    console.log('[VizR][GSEA][API] fetchGSEAPlotDetail:response', {
      workbenchId,
      geneSet: response?.gene_set,
      leadingEdgeSize: response?.leading_edge_size ?? null,
      hitCount: Array.isArray(response?.hit_indices) ? response.hit_indices.length : null,
      runningScoreCount: Array.isArray(response?.running_scores) ? response.running_scores.length : null,
      zeroCrossIndex: response?.zero_cross_index ?? null,
    });
    return response;
  }

  async runPrerankedGSEA(
    workbenchId: number,
    payload: {
      comparison_name?: string;
      deg_tool?: string;
      ranked_list_text: string;
      gmt_temp_file: string;
    }
  ): Promise<{
    comparison_name?: string;
    deg_tool?: string;
    ranking_metric: string;
    validation: {
      ranked_gene_count: number;
      tested_gene_sets: number;
      min_overlap: number;
      permutations: number;
    };
    rows: Array<{
      gene_set: string;
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
      peak_index: number;
    }>;
  }> {
    return this.fetchJSON(`/workbenches/${workbenchId}/gsea/preranked`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  // DEG results endpoint
  async fetchDEGResults(
    workbenchId: number,
    comparisonName: string,
    params: {
      tool_name?: string;
      page?: number;
      limit?: number;
      search?: string;
      data_type?: 'matrix' | 'ma_plot' | 'volcano_plot';
      filter_type?: 'up' | 'down' | 'all';
      filters?: { [key: string]: { operator: string; value: string } };
      sort_by?: string;
      sort_order?: 'asc' | 'desc';
      low_expr_enabled?: boolean;
      low_expr_min_tmm?: number;
      low_expr_min_sample_pct?: number;
    } = {}
  ): Promise<any> {
    const queryParams = new URLSearchParams();
    if (params.tool_name) queryParams.append('tool_name', params.tool_name);
    if (params.page) queryParams.append('page', params.page.toString());
    if (params.limit) queryParams.append('limit', params.limit.toString());
    if (params.search) queryParams.append('search', params.search);
    if (params.data_type) queryParams.append('data_type', params.data_type);
    if (params.filter_type) queryParams.append('filter_type', params.filter_type);

    // Add filters as JSON string
    if (params.filters) {
      // Only include filters that have both operator and value
      const activeFilters: { [key: string]: { operator: string; value: string } } = {};
      Object.entries(params.filters).forEach(([key, filter]) => {
        if (filter.operator && filter.value) {
          activeFilters[key] = filter;
        }
      });
      if (Object.keys(activeFilters).length > 0) {
        queryParams.append('filters', JSON.stringify(activeFilters));
      }
    }

    // Add sort parameters
    if (params.sort_by) queryParams.append('sort_by', params.sort_by);
    if (params.sort_order) queryParams.append('sort_order', params.sort_order);
    if (params.low_expr_enabled) queryParams.append('low_expr_enabled', 'true');
    if (params.low_expr_min_tmm !== undefined) queryParams.append('low_expr_min_tmm', params.low_expr_min_tmm.toString());
    if (params.low_expr_min_sample_pct !== undefined) queryParams.append('low_expr_min_sample_pct', params.low_expr_min_sample_pct.toString());

    const queryString = queryParams.toString();
    const url = `/workbenches/${workbenchId}/deg/results/${comparisonName}${queryString ? `?${queryString}` : ''}`;
    return this.fetchJSON(url);
  }

  // GO Enrichment Analysis
  async runGOEnrichment(
    workbenchId: number,
    params: {
      genes: string[];
      databases?: string[];
      p_value_cutoff?: number;
      description?: string;
      organism?: string;
      provider?: 'david' | 'gprofiler';
    }
  ): Promise<any> {
    const url = `/workbenches/${workbenchId}/deg/go-enrichment`;
    return this.fetchJSON(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(params)
    });
  }

  async getGODatabases(workbenchId: number): Promise<{ databases: Record<string, string> }> {
    return this.fetchJSON(`/workbenches/${workbenchId}/deg/go-enrichment/databases`);
  }

  // KEGG Pathway Analysis
  async runKEGGPathway(
    workbenchId: number,
    params: {
      genes: string[];
      p_value_cutoff?: number;
      organism?: string;
    }
  ): Promise<any> {
    const url = `/workbenches/${workbenchId}/deg/kegg-pathway`;
    return this.fetchJSON(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(params)
    });
  }

  // Significant genes TMM counts endpoint
  async fetchSignificantTMMCounts(
    workbenchId: number,
    comparisonName: string,
    toolName: string = 'edgeR',
    fdrCutoff: number = 0.05
  ): Promise<{
    success: boolean;
    gene_count: number;
    sample_names: string[];
    data: { [geneId: string]: number[] };
  }> {
    const queryParams = new URLSearchParams();
    queryParams.append('comparison', comparisonName);
    queryParams.append('tool_name', toolName);
    queryParams.append('fdr_cutoff', fdrCutoff.toString());

    const url = `/workbenches/${workbenchId}/deg/significant-tmm-counts?${queryParams.toString()}`;
    return this.fetchJSON(url);
  }

  // Fetch TMM counts for specific gene IDs
  async fetchTMMCountsByGenes(
    workbenchId: number,
    geneIds: string[],
    comparisonName: string,
    toolName: string = 'edgeR'
  ): Promise<{
    success: boolean;
    data: { [geneId: string]: number[] };
    sample_names: string[];
    found_count: number;
    total_requested: number;
  }> {
    const url = `/workbenches/${workbenchId}/deg/tmm-counts-by-genes`;
    return this.fetchJSON(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        gene_ids: geneIds,
        comparison: comparisonName,
        tool_name: toolName
      })
    });
  }

  async uploadTempMatrixFile(
    file: File,
    onProgress?: (progress: number) => void,
    controller?: AbortController
  ): Promise<{
    message: string;
    temp_upload_id: number;
    temp_filename: string;
    original_filename: string;
    file_size: number;
  }> {
    const formData = new FormData();
    formData.append('file', file);

    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();

      if (controller) {
        controller.signal.addEventListener('abort', () => {
          xhr.abort();
        });
      }

      if (onProgress) {
        xhr.upload.addEventListener('progress', (e) => {
          if (e.lengthComputable) {
            onProgress(Math.round((e.loaded / e.total) * 100));
          }
        });
      }

      xhr.addEventListener('load', () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            resolve(JSON.parse(xhr.responseText));
          } catch {
            reject(new APIError(xhr.status, 'Invalid response format'));
          }
        } else {
          try {
            const errorData = JSON.parse(xhr.responseText);
            reject(new APIError(xhr.status, errorData.error || 'Upload failed'));
          } catch {
            reject(new APIError(xhr.status, 'Upload failed'));
          }
        }
      });

      xhr.addEventListener('error', () => reject(new APIError(0, 'Network error')));
      xhr.addEventListener('abort', () => reject(new APIError(0, 'Upload cancelled')));

      xhr.open('POST', `${API_BASE_URL}/upload/temp-matrix`);
      xhr.withCredentials = true;
      xhr.send(formData);
    });
  }

  async uploadTempGmtFile(
    file: File,
    onProgress?: (progress: number) => void,
    controller?: AbortController
  ): Promise<{
    message: string;
    temp_upload_id: number;
    temp_filename: string;
    original_filename: string;
    file_size: number;
  }> {
    return this.uploadTempMatrixFile(file, onProgress, controller);
  }

  async validateMatrixFiles(payload: {
    counts_temp_file: string;
    tpm_temp_file?: string | null;
  }): Promise<{
    valid: boolean;
    errors: string[];
    warnings: string[];
    sample_columns: string[];
    sample_count: number;
    gene_count: number;
    has_tpm_matrix: boolean;
  }> {
    return this.fetchJSON('/workbenches/validate-matrix-files', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async fetchSelectedCountResults(
    workbenchId: number,
    params: {
      matrix_type: 'TMM' | 'TPM' | 'RAW';
      selected_genes: string[];
      search?: string;
      page?: number;
      limit?: number;
    }
  ): Promise<{
    workbench_id: number;
    matrix_type: string;
    matrix: Array<Record<string, any>>;
    samples: string[];
    groups: string[];
    total_genes: number;
    showing_genes: number;
    current_page: number;
    total_pages: number;
    page_size: number;
    matched_gene_ids: string[];
    matrix_file: string | null;
    status: string;
    search_query?: string;
    is_search_result?: boolean;
  }> {
    const url = `/workbenches/${workbenchId}/count-results/selected`;
    return this.fetchJSON(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(params)
    });
  }

  async generateHeatmap(
    workbenchId: number,
    params: {
      genes: string[];
      comparison: string;
      tool: string;
      clustering_method?: string;
      normalize?: string;
    }
  ): Promise<{
    z: number[][];
    x: string[];
    y: string[];
    row_order: number[];
    col_order: number[];
  }> {
    const url = `/workbenches/${workbenchId}/deg/heatmap`;
    return this.fetchJSON(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(params)
    });
  }

  // Clustering Analysis endpoints
  async runTreeCutting(
    workbenchId: number,
    params: {
      p_value: number;
      fold_change: number;
      ptree: number;
    }
  ): Promise<{
    success: boolean;
    message: string;
    total: number;
    clusters: Array<{
      id: string;
      gene_count: number;
      file_name: string;
    }>;
    error?: string;
  }> {
    const url = `/workbenches/${workbenchId}/clustering/tree-cutting/run`;
    return this.fetchJSON(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(params)
    });
  }

  async getTreeCuttingClusters(
    workbenchId: number,
    params: {
      p_value: number;
      fold_change: number;
      ptree: number;
      search?: string;
      auto_run?: boolean;
    }
  ): Promise<{
    exists: boolean;
    clusters: Array<{
      id: string;
      gene_count: number;
      file_name: string;
    }>;
    total: number;
    is_search_result: boolean;
    search_query: string;
  }> {
    const queryParams = new URLSearchParams();
    queryParams.append('p_value', params.p_value.toString());
    queryParams.append('fold_change', params.fold_change.toString());
    queryParams.append('ptree', params.ptree.toString());
    if (params.search) queryParams.append('search', params.search);
    if (params.auto_run !== undefined) queryParams.append('auto_run', params.auto_run ? 'true' : 'false');

    const url = `/workbenches/${workbenchId}/clustering/tree-cutting/clusters?${queryParams.toString()}`;
    return this.fetchJSON(url);
  }

  async getTreeCuttingClusterData(
    workbenchId: number,
    clusterId: string,
    params: {
      p_value: number;
      fold_change: number;
      ptree: number;
      search?: string;
      page?: number;
      limit?: number;
    }
  ): Promise<{
    cluster_id: string;
    gene_count: number;
    total_genes: number;
    showing_genes: number;
    current_page: number;
    total_pages: number;
    page_size: number;
    samples: string[];
    statistics: {
      mean: number[];
      median: number[];
      min: number[];
      max: number[];
    };
    genes: Array<{
      gene_id: string;
      gene_symbol: string;
      [sampleName: string]: string | number;
    }>;
    is_search_result: boolean;
    search_query: string;
  }> {
    const queryParams = new URLSearchParams();
    queryParams.append('p_value', params.p_value.toString());
    queryParams.append('fold_change', params.fold_change.toString());
    queryParams.append('ptree', params.ptree.toString());

    // 검색 및 페이지네이션 파라미터 추가
    if (params.search) {
      queryParams.append('search', params.search);
    }
    if (params.page !== undefined) {
      queryParams.append('page', params.page.toString());
    }
    if (params.limit !== undefined) {
      queryParams.append('limit', params.limit.toString());
    }

    const url = `/workbenches/${workbenchId}/clustering/tree-cutting/cluster/${clusterId}?${queryParams.toString()}`;
    return this.fetchJSON(url);
  }

  async getTreeCuttingClusterPreviews(
    workbenchId: number,
    params: {
      p_value: number;
      fold_change: number;
      ptree: number;
      cluster_ids: string[];
    }
  ): Promise<{
    exists: boolean;
    previews: Array<{
      id: string;
      gene_count: number;
      samples: string[];
      statistics: {
        mean: number[];
        median: number[];
      };
    }>;
    total: number;
  }> {
    const queryParams = new URLSearchParams();
    queryParams.append('p_value', params.p_value.toString());
    queryParams.append('fold_change', params.fold_change.toString());
    queryParams.append('ptree', params.ptree.toString());
    queryParams.append('cluster_ids', params.cluster_ids.join(','));

    const url = `/workbenches/${workbenchId}/clustering/tree-cutting/previews?${queryParams.toString()}`;
    return this.fetchJSON(url);
  }

  async getTreeCuttingDendrogram(
    workbenchId: number,
    params: {
      p_value: number;
      fold_change: number;
      ptree: number;
    }
  ): Promise<{
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
  }> {
    const queryParams = new URLSearchParams();
    queryParams.append('p_value', params.p_value.toString());
    queryParams.append('fold_change', params.fold_change.toString());
    queryParams.append('ptree', params.ptree.toString());

    const url = `/workbenches/${workbenchId}/clustering/tree-cutting/dendrogram?${queryParams.toString()}`;
    return this.fetchJSON(url);
  }

  async getTreeCuttingMergedPreview(
    workbenchId: number,
    params: {
      p_value: number;
      fold_change: number;
      ptree: number;
      merged_id: string;
      cluster_ids: string[];
    }
  ): Promise<{
    exists: boolean;
    preview: {
      id: string;
      source_cluster_ids: string[];
      gene_count: number;
      samples: string[];
      statistics: {
        mean: number[];
        median: number[];
      };
    };
  }> {
    const queryParams = new URLSearchParams();
    queryParams.append('p_value', params.p_value.toString());
    queryParams.append('fold_change', params.fold_change.toString());
    queryParams.append('ptree', params.ptree.toString());
    queryParams.append('merged_id', params.merged_id);
    queryParams.append('cluster_ids', params.cluster_ids.join(','));

    const url = `/workbenches/${workbenchId}/clustering/tree-cutting/merged-preview?${queryParams.toString()}`;
    return this.fetchJSON(url);
  }

  async getTreeCuttingMergedClusterData(
    workbenchId: number,
    params: {
      p_value: number;
      fold_change: number;
      ptree: number;
      merged_id: string;
      cluster_ids: string[];
      search?: string;
      page?: number;
      limit?: number;
    }
  ): Promise<{
    cluster_id: string;
    source_cluster_ids: string[];
    gene_count: number;
    total_genes: number;
    showing_genes: number;
    current_page: number;
    total_pages: number;
    page_size: number;
    samples: string[];
    statistics: {
      mean: number[];
      median: number[];
      min: number[];
      max: number[];
    };
    genes: Array<{
      gene_id: string;
      gene_symbol: string;
      [sampleName: string]: string | number;
    }>;
    is_search_result: boolean;
    search_query: string;
  }> {
    const queryParams = new URLSearchParams();
    queryParams.append('p_value', params.p_value.toString());
    queryParams.append('fold_change', params.fold_change.toString());
    queryParams.append('ptree', params.ptree.toString());
    queryParams.append('merged_id', params.merged_id);
    queryParams.append('cluster_ids', params.cluster_ids.join(','));

    if (params.search) queryParams.append('search', params.search);
    if (params.page !== undefined) queryParams.append('page', params.page.toString());
    if (params.limit !== undefined) queryParams.append('limit', params.limit.toString());

    const url = `/workbenches/${workbenchId}/clustering/tree-cutting/merged-data?${queryParams.toString()}`;
    return this.fetchJSON(url);
  }

  // Mfuzz Clustering endpoints
  async runMfuzz(
    workbenchId: number,
    params: {
      source_type: 'deg' | 'variance' | 'tmm';
      p_value?: number | null;
      fold_change?: number | null;
      top_n_genes?: number;
      cluster_count: number;
      m_value: number | null;
      min_membership: number;
    }
  ): Promise<{
    success: boolean;
    clusters: Array<{
      id: number;
      gene_count: number;
      file_name: string;
    }>;
    total: number;
    output_dir: string;
    parameters: {
      source_type: string;
      cluster_count: number;
      m_value: number | null;
      min_membership: number;
      p_value?: number | null;
      fold_change?: number | null;
      top_n_genes?: number | null;
    };
    error?: string;
  }> {
    const url = `/workbenches/${workbenchId}/clustering/mfuzz/run`;
    return this.fetchJSON(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(params)
    });
  }

  async getMfuzzClusters(
    workbenchId: number,
    params: {
      source_type: 'deg' | 'variance' | 'tmm';
      p_value?: number | null;
      fold_change?: number | null;
      top_n_genes?: number;
      cluster_count: number;
      m_value: number | null;
      min_membership: number;
      search?: string;
    }
  ): Promise<{
    exists: boolean;
    clusters: Array<{
      id: number;
      gene_count: number;
      file_name: string;
    }>;
    total: number;
    parameters: {
      source_type: string;
      cluster_count: number;
      m_value: number | null;
      min_membership: number;
      p_value?: number | null;
      fold_change?: number | null;
      top_n_genes?: number | null;
    };
    is_search_result: boolean;
    search_query: string;
  }> {
    const queryParams = new URLSearchParams();
    queryParams.append('source_type', params.source_type);
    if (params.p_value !== undefined && params.p_value !== null) {
      queryParams.append('p_value', params.p_value.toString());
    }
    if (params.fold_change !== undefined && params.fold_change !== null) {
      queryParams.append('fold_change', params.fold_change.toString());
    }
    if (params.top_n_genes !== undefined) {
      queryParams.append('top_n_genes', params.top_n_genes.toString());
    }
    queryParams.append('cluster_count', params.cluster_count.toString());
    queryParams.append('m_value', params.m_value === null ? 'auto' : params.m_value.toString());
    queryParams.append('min_membership', params.min_membership.toString());
    if (params.search) queryParams.append('search', params.search);

    const url = `/workbenches/${workbenchId}/clustering/mfuzz/clusters?${queryParams.toString()}`;
    return this.fetchJSON(url);
  }

  async getMfuzzClusterData(
    workbenchId: number,
    clusterId: number,
    params: {
      source_type: 'deg' | 'variance' | 'tmm';
      p_value?: number | null;
      fold_change?: number | null;
      top_n_genes?: number;
      cluster_count: number;
      m_value: number | null;
      min_membership: number;
      search?: string;
      page?: number;
      limit?: number;
    }
  ): Promise<{
    cluster_id: number;
    gene_count: number;
    total_genes: number;
    showing_genes: number;
    current_page: number;
    total_pages: number;
    page_size: number;
    samples: string[];
    is_search_result: boolean;
    search_query: string;
    genes: Array<{
      gene_id: string;
      gene_symbol: string;
      membership: number;
      [sampleName: string]: string | number;
    }>;
  }> {
    const queryParams = new URLSearchParams();
    queryParams.append('source_type', params.source_type);
    if (params.p_value !== undefined && params.p_value !== null) {
      queryParams.append('p_value', params.p_value.toString());
    }
    if (params.fold_change !== undefined && params.fold_change !== null) {
      queryParams.append('fold_change', params.fold_change.toString());
    }
    if (params.top_n_genes !== undefined) {
      queryParams.append('top_n_genes', params.top_n_genes.toString());
    }
    queryParams.append('cluster_count', params.cluster_count.toString());
    queryParams.append('m_value', params.m_value === null ? 'auto' : params.m_value.toString());
    queryParams.append('min_membership', params.min_membership.toString());

    // 검색 및 페이지네이션 파라미터 추가
    if (params.search) {
      queryParams.append('search', params.search);
    }
    if (params.page !== undefined) {
      queryParams.append('page', params.page.toString());
    }
    if (params.limit !== undefined) {
      queryParams.append('limit', params.limit.toString());
    }

    const url = `/workbenches/${workbenchId}/clustering/mfuzz/cluster/${clusterId}?${queryParams.toString()}`;
    return this.fetchJSON(url);
  }

  async getMfuzzClusterPreviews(
    workbenchId: number,
    params: {
      source_type: 'deg' | 'variance' | 'tmm';
      p_value?: number | null;
      fold_change?: number | null;
      top_n_genes?: number;
      cluster_count: number;
      m_value: number | null;
      min_membership: number;
      cluster_ids: number[];
    }
  ): Promise<{
    exists: boolean;
    previews: Array<{
      id: number;
      gene_count: number;
      samples: string[];
      statistics: {
        mean: number[];
        median: number[];
      };
    }>;
    total: number;
  }> {
    const queryParams = new URLSearchParams();
    queryParams.append('source_type', params.source_type);
    queryParams.append('cluster_count', params.cluster_count.toString());
    queryParams.append('min_membership', params.min_membership.toString());
    queryParams.append('cluster_ids', params.cluster_ids.join(','));
    if (params.source_type === 'deg') {
      if (params.p_value != null) queryParams.append('p_value', params.p_value.toString());
      if (params.fold_change != null) queryParams.append('fold_change', params.fold_change.toString());
    }
    if (params.source_type === 'variance' && params.top_n_genes != null) {
      queryParams.append('top_n_genes', params.top_n_genes.toString());
    }
    if (params.m_value != null) {
      queryParams.append('m_value', params.m_value.toString());
    } else {
      queryParams.append('m_value', 'auto');
    }

    const url = `/workbenches/${workbenchId}/clustering/mfuzz/previews?${queryParams.toString()}`;
    return this.fetchJSON(url);
  }

  // WGCNA Clustering endpoints
  async runWgcna(
    workbenchId: number,
    params: {
      source_type: 'deg' | 'variance' | 'tmm';
      p_value?: number | null;
      fold_change?: number | null;
      top_n_genes?: number;
      soft_power: 'auto' | number;
      min_module_size: number;
      deep_split: number;
      merge_cut_height: number;
    }
  ): Promise<{
    success: boolean;
    modules: Array<{
      id: string;
      gene_count: number;
      file_name: string;
    }>;
    total: number;
    output_dir: string;
    parameters: {
      source_type: string;
      soft_power: 'auto' | number;
      min_module_size: number;
      deep_split: number;
      merge_cut_height: number;
      p_value?: number | null;
      fold_change?: number | null;
      top_n_genes?: number | null;
    };
    error?: string;
  }> {
    const url = `/workbenches/${workbenchId}/clustering/wgcna/run`;
    return this.fetchJSON(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(params)
    });
  }

  async getWgcnaModules(
    workbenchId: number,
    params: {
      source_type: 'deg' | 'variance' | 'tmm';
      p_value?: number | null;
      fold_change?: number | null;
      top_n_genes?: number;
      soft_power: 'auto' | number;
      min_module_size: number;
      deep_split: number;
      merge_cut_height: number;
      search?: string;
    }
  ): Promise<{
    exists: boolean;
    modules: Array<{
      id: string;
      gene_count: number;
      file_name: string;
    }>;
    total: number;
    is_search_result: boolean;
    search_query: string;
    parameters: {
      source_type: string;
      soft_power: 'auto' | number;
      min_module_size: number;
      deep_split: number;
      merge_cut_height: number;
      p_value?: number | null;
      fold_change?: number | null;
      top_n_genes?: number | null;
    };
  }> {
    const queryParams = new URLSearchParams();
    queryParams.append('source_type', params.source_type);
    if (params.p_value !== undefined && params.p_value !== null) {
      queryParams.append('p_value', params.p_value.toString());
    }
    if (params.fold_change !== undefined && params.fold_change !== null) {
      queryParams.append('fold_change', params.fold_change.toString());
    }
    if (params.top_n_genes !== undefined) {
      queryParams.append('top_n_genes', params.top_n_genes.toString());
    }
    queryParams.append('soft_power', params.soft_power === 'auto' ? 'auto' : params.soft_power.toString());
    queryParams.append('min_module_size', params.min_module_size.toString());
    queryParams.append('deep_split', params.deep_split.toString());
    queryParams.append('merge_cut_height', params.merge_cut_height.toString());

    // Search parameter
    if (params.search) {
      queryParams.append('search', params.search);
    }

    const url = `/workbenches/${workbenchId}/clustering/wgcna/modules?${queryParams.toString()}`;
    return this.fetchJSON(url);
  }

  async getWgcnaModulePreviews(
    workbenchId: number,
    params: {
      source_type: 'deg' | 'variance' | 'tmm';
      p_value?: number | null;
      fold_change?: number | null;
      top_n_genes?: number;
      soft_power: 'auto' | number;
      min_module_size: number;
      deep_split: number;
      merge_cut_height: number;
      module_ids: string[];
    }
  ): Promise<{
    exists: boolean;
    previews: Array<{
      id: string;
      gene_count: number;
      samples: string[];
      statistics: {
        mean: number[];
        median: number[];
      };
    }>;
    total: number;
  }> {
    const queryParams = new URLSearchParams();
    queryParams.append('source_type', params.source_type);
    queryParams.append('soft_power', params.soft_power === 'auto' ? 'auto' : params.soft_power.toString());
    queryParams.append('min_module_size', params.min_module_size.toString());
    queryParams.append('deep_split', params.deep_split.toString());
    queryParams.append('merge_cut_height', params.merge_cut_height.toString());
    queryParams.append('module_ids', params.module_ids.join(','));
    if (params.source_type === 'deg') {
      if (params.p_value != null) queryParams.append('p_value', params.p_value.toString());
      if (params.fold_change != null) queryParams.append('fold_change', params.fold_change.toString());
    }
    if (params.source_type === 'variance' && params.top_n_genes != null) {
      queryParams.append('top_n_genes', params.top_n_genes.toString());
    }

    const url = `/workbenches/${workbenchId}/clustering/wgcna/previews?${queryParams.toString()}`;
    return this.fetchJSON(url);
  }

  async getWgcnaModuleData(
    workbenchId: number,
    moduleId: string,
    params: {
      source_type: 'deg' | 'variance' | 'tmm';
      p_value?: number | null;
      fold_change?: number | null;
      top_n_genes?: number;
      soft_power: 'auto' | number;
      min_module_size: number;
      deep_split: number;
      merge_cut_height: number;
      search?: string;
      page?: number;
      limit?: number;
    }
  ): Promise<{
    module_id: string;
    gene_count: number;
    total_genes: number;
    showing_genes: number;
    current_page: number;
    total_pages: number;
    page_size: number;
    samples: string[];
    eigengene_values: number[];
    is_search_result: boolean;
    search_query: string;
    genes: Array<{
      gene_id: string;
      gene_symbol: string;
      module_membership: number;
      [sampleName: string]: string | number;
    }>;
  }> {
    const queryParams = new URLSearchParams();
    queryParams.append('source_type', params.source_type);
    if (params.p_value !== undefined && params.p_value !== null) {
      queryParams.append('p_value', params.p_value.toString());
    }
    if (params.fold_change !== undefined && params.fold_change !== null) {
      queryParams.append('fold_change', params.fold_change.toString());
    }
    if (params.top_n_genes !== undefined) {
      queryParams.append('top_n_genes', params.top_n_genes.toString());
    }
    queryParams.append('soft_power', params.soft_power === 'auto' ? 'auto' : params.soft_power.toString());
    queryParams.append('min_module_size', params.min_module_size.toString());
    queryParams.append('deep_split', params.deep_split.toString());
    queryParams.append('merge_cut_height', params.merge_cut_height.toString());

    // 검색 및 페이지네이션 파라미터 추가
    if (params.search) {
      queryParams.append('search', params.search);
    }
    if (params.page !== undefined) {
      queryParams.append('page', params.page.toString());
    }
    if (params.limit !== undefined) {
      queryParams.append('limit', params.limit.toString());
    }

    const url = `/workbenches/${workbenchId}/clustering/wgcna/modules/${moduleId}?${queryParams.toString()}`;
    return this.fetchJSON(url);
  }

  // Interesting Genes API
  async getInterestingGenesTree(): Promise<{
    success: boolean;
    tree: Array<{
      name: string;
      type: 'folder' | 'file';
      path: string;
      fullName?: string;
      children?: any[];
    }>;
    error?: string;
  }> {
    const url = '/interesting-genes/tree';
    return this.fetchJSON(url);
  }

  async getInterestingGenes(filePath: string): Promise<{
    success: boolean;
    genes: string[];
    count: number;
    file_path: string;
    error?: string;
  }> {
    const url = `/interesting-genes/genes?file_path=${encodeURIComponent(filePath)}`;
    return this.fetchJSON(url);
  }

  async createGeneSet(folderPath: string, fileName: string, genes: string[]): Promise<{
    success: boolean;
    file_path: string;
    gene_count: number;
    error?: string;
  }> {
    const url = '/interesting-genes/create';
    return this.fetchJSON(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        folder_path: folderPath,
        file_name: fileName,
        genes: genes
      })
    });
  }

  async updateGeneSet(filePath: string, genes: string[]): Promise<{
    success: boolean;
    file_path: string;
    gene_count: number;
    error?: string;
  }> {
    const url = '/interesting-genes/update';
    return this.fetchJSON(url, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        file_path: filePath,
        genes: genes
      })
    });
  }

  async deleteGeneSet(filePath: string): Promise<{
    success: boolean;
    message: string;
    error?: string;
  }> {
    const url = `/interesting-genes/delete?file_path=${encodeURIComponent(filePath)}`;
    return this.fetchJSON(url, {
      method: 'DELETE'
    });
  }

  async deleteFolder(folderPath: string): Promise<{
    success: boolean;
    message: string;
    error?: string;
  }> {
    const url = `/interesting-genes/delete-folder?folder_path=${encodeURIComponent(folderPath)}`;
    return this.fetchJSON(url, {
      method: 'DELETE'
    });
  }

  async uploadGeneSets(folderPath: string, files: File[]): Promise<{
    success: boolean;
    uploaded_files: Array<{
      original_name: string;
      saved_path: string;
      gene_count: number;
    }>;
    total_count: number;
    error?: string;
  }> {
    const url = `${API_BASE_URL}/interesting-genes/upload`;
    const formData = new FormData();
    formData.append('folder_path', folderPath);

    files.forEach(file => {
      // webkitRelativePath가 있으면 파일명으로 사용 (하위 폴더 구조 보존)
      const fileWithPath = file as any;
      if (fileWithPath.webkitRelativePath) {
        // webkitRelativePath를 파일명으로 사용하기 위해 새 File 객체 생성
        const newFile = new File([file], fileWithPath.webkitRelativePath, { type: file.type });
        formData.append('files[]', newFile);
      } else {
        formData.append('files[]', file);
      }
    });

    // Use fetch directly for FormData - don't set Content-Type header
    try {
      const response = await fetch(url, {
        method: 'POST',
        credentials: 'include',
        body: formData
      });

      const data = await response.json();

      if (!response.ok) {
        throw new APIError(response.status, data.error || 'Upload failed');
      }

      return data;
    } catch (error) {
      if (error instanceof APIError) {
        throw error;
      }
      throw new APIError(0, 'Network error occurred');
    }
  }

  // Workbench Share endpoints
  async getAvailableUsers(workbenchId: number): Promise<{
    users: Array<{
      id: number;
      username: string;
      email: string;
      full_name?: string;
    }>;
  }> {
    return this.fetchJSON(`/workbenches/${workbenchId}/available-users`);
  }

  async getSharedUsers(workbenchId: number): Promise<{
    shared_users: Array<{
      id: number;
      username: string;
      email: string;
      full_name?: string;
    }>;
  }> {
    return this.fetchJSON(`/workbenches/${workbenchId}/shared-users`);
  }

  async shareWorkbench(workbenchId: number, userIds: number[]): Promise<{
    message: string;
    shared_user_ids: number[];
  }> {
    return this.fetchJSON(`/workbenches/${workbenchId}/share`, {
      method: 'POST',
      body: JSON.stringify({ user_ids: userIds }),
    });
  }

  async unshareWorkbench(workbenchId: number, targetUserId: number): Promise<{
    message: string;
    shared_user_ids: number[];
  }> {
    return this.fetchJSON(`/workbenches/${workbenchId}/share/${targetUserId}`, {
      method: 'DELETE',
    });
  }

  // Reference Genome Management endpoints
  async getReferences(): Promise<{
    references: Array<{
      name: string;
      version: string;
      species: string;
      organism: string;
      is_default: boolean;
      total_size_mb: number;
      created_at: string;
    }>;
  }> {
    return this.fetchJSON('/settings/references');
  }

  async uploadReference(formData: FormData): Promise<{
    message: string;
    reference_name: string;
  }> {
    const response = await fetch(`${API_BASE_URL}/settings/references/upload`, {
      method: 'POST',
      credentials: 'include',
      body: formData
    });

    if (!response.ok) {
      const errorData = await response.json();
      throw new APIError(response.status, errorData.message || 'Upload failed');
    }

    return response.json();
  }

  async setDefaultReference(name: string, species: string): Promise<{
    message: string;
  }> {
    return this.fetchJSON(`/settings/references/${name}/default`, {
      method: 'PUT',
      body: JSON.stringify({ species })
    });
  }

  async deleteReference(name: string, species: string): Promise<{
    message: string;
  }> {
    return this.fetchJSON(`/settings/references/${name}?species=${encodeURIComponent(species)}`, {
      method: 'DELETE'
    });
  }

  // Server file validation endpoints
  async validateServerFiles(filePaths: string[]): Promise<{
    valid_files: Array<{
      path: string;
      filename: string;
      format: string;
      is_gzipped: boolean;
      read_type: string;
      size: number;
    }>;
    invalid_files: Array<{
      path: string;
      filename: string;
      error: string;
    }>;
  }> {
    return this.fetchJSON('/server/validate-files', {
      method: 'POST',
      body: JSON.stringify({ file_paths: filePaths })
    });
  }

  // Pipeline configuration endpoints
  async updateWorkbenchPipeline(workbenchId: number, pipelineData: {
    pipelineSteps: Array<{
      step: string;
      tool: string;
      description: string;
      parameters: any;
    }>;
    referenceSet: string;
  }): Promise<{
    message: string;
    workbench_id: number;
  }> {
    console.log('[API] 🔧 updateWorkbenchPipeline - Starting');
    console.log('[API]    ├─ Workbench ID:', workbenchId);
    console.log('[API]    ├─ Pipeline steps count:', pipelineData.pipelineSteps.length);
    console.log('[API]    ├─ Reference set:', pipelineData.referenceSet);
    console.log('[API]    └─ Full pipeline data:', JSON.stringify(pipelineData, null, 2));

    try {
      const response = await this.fetchJSON(`/workbenches/${workbenchId}/pipeline`, {
        method: 'PUT',
        body: JSON.stringify(pipelineData)
      });

      console.log('[API] ✅ updateWorkbenchPipeline - Success');
      console.log('[API]    └─ Response:', response);

      return response;
    } catch (error) {
      console.error('[API]    ├─ Error:', error);
      console.error('[API]    └─ Pipeline data that failed:', pipelineData);
      throw error;
    }
  }
}

// Export singleton instance
export const apiService = new APIService();
export { APIError };
