import React, { useCallback, useState, useRef, useImperativeHandle, forwardRef } from 'react';
import { apiService } from '../services/api';

interface UploadedFile {
  id: number; // temp_upload_id
  name: string;
  size: number;
  tempFilename: string;
  uploadProgress: number;
  uploadStatus: 'uploading' | 'completed' | 'failed' | 'cancelled';
  error?: string;
  abortController?: AbortController;
}

interface FileUploadProps {
  files: UploadedFile[];
  onFilesChange: (files: UploadedFile[]) => void;
  onProgressUpdate: (tempId: number, progress: number) => void;
  onUploadComplete: (tempId: number, uploadResult: any) => void;
  onUploadError: (tempId: number, error: string) => void;
  accept?: string;
  multiple?: boolean;
  className?: string;
  maxConcurrentUploads?: number;
}

export interface FileUploadRef {
  cancelAllUploads: () => void;
}

const FileUpload = forwardRef<FileUploadRef, FileUploadProps>(({
  files,
  onFilesChange,
  onProgressUpdate,
  onUploadComplete,
  onUploadError,
  accept = ".fastq,.fq,.fasta,.fa,.gz,.fastq.gz,.fq.gz,.fasta.gz,.fa.gz",
  multiple = true,
  className = "",
  maxConcurrentUploads = 6
}, ref) => {
  const [isDragOver, setIsDragOver] = useState(false);
  const [duplicateMessage, setDuplicateMessage] = useState<string>('');
  const [uploadQueue, setUploadQueue] = useState<File[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const uploadsInProgress = useRef<number>(0);
  const uploadQueueRef = useRef<File[]>([]);
  const filesRef = useRef<UploadedFile[]>([]);
  const queueClearedByModal = useRef<boolean>(false);

  // Keep uploadQueueRef in sync with uploadQueue state
  React.useEffect(() => {
    uploadQueueRef.current = uploadQueue;
  }, [uploadQueue]);

  // Keep filesRef in sync with files prop
  React.useEffect(() => {
    filesRef.current = files;
  }, [files]);

  // Expose cancelAllUploads function to parent via ref
  useImperativeHandle(ref, () => ({
    cancelAllUploads: () => {
      // Set flag immediately to prevent further queue processing
      queueClearedByModal.current = true;

      // Clear queue and reset progress counter
      setUploadQueue([]);
      uploadsInProgress.current = 0;
    }
  }), []);

  // Process upload queue
  const processUploadQueue = useCallback(async () => {
    const currentQueue = uploadQueueRef.current;

    // Check if queue was cleared by modal close
    if (queueClearedByModal.current) {
      return;
    }

    if (uploadsInProgress.current >= maxConcurrentUploads) {
      return;
    }

    if (currentQueue.length === 0) {
      return;
    }

    const fileToUpload = currentQueue[0];

    setUploadQueue(prev => prev.slice(1));
    uploadsInProgress.current++;

    // Create AbortController for this upload
    const abortController = new AbortController();

    // Create temporary upload entry
    const tempId = Date.now() + Math.random();
    const newUploadedFile: UploadedFile = {
      id: tempId,
      name: fileToUpload.name,
      size: fileToUpload.size,
      tempFilename: '',
      uploadProgress: 0,
      uploadStatus: 'uploading',
      abortController: abortController
    };

    const currentFiles = filesRef.current;
    const newFilesList = [...currentFiles, newUploadedFile];
    onFilesChange(newFilesList);

    // Process next files in queue immediately for concurrent uploads
    if (uploadsInProgress.current < maxConcurrentUploads && uploadQueueRef.current.length > 0) {
      setTimeout(processUploadQueue, 10);
    }

    try {
      const result = await apiService.uploadTempFile(
        fileToUpload,
        (progress) => {
          onProgressUpdate(tempId, progress);
        },
        abortController
      );

      onUploadComplete(tempId, result);

    } catch (error: any) {
      const errorMsg = error.message || 'Upload failed';
      console.error(`Upload failed: ${fileToUpload.name}`, {
        error: errorMsg,
        status: error.status,
        type: error.constructor.name
      });
      onUploadError(tempId, errorMsg);
    } finally {
      uploadsInProgress.current--;

      // Check if queue was cleared by modal close
      if (queueClearedByModal.current) {
        uploadsInProgress.current = 0;
        return;
      }

      // Check if all files are cancelled/failed
      const allFilesCancelledOrFailed = filesRef.current.length > 0 &&
        filesRef.current.every(f => f.uploadStatus === 'cancelled' || f.uploadStatus === 'failed');

      const hasQueuedFiles = uploadQueueRef.current.length > 0;

      // Continue processing if there are queued files OR if not all files are cancelled/failed
      if (allFilesCancelledOrFailed && !hasQueuedFiles) {
        uploadsInProgress.current = 0;
      } else {
        setTimeout(processUploadQueue, 200);
      }
    }
  }, [onFilesChange, maxConcurrentUploads]);

  const addFiles = useCallback((newFiles: File[], isDrop = false) => {
    if (newFiles.length === 0) {
      return;
    }

    // Reset modal close flag when new files are added
    if (queueClearedByModal.current) {
      queueClearedByModal.current = false;
    }

    // Filter out duplicate files based on name and size
    const existingFiles = new Set(
      files.map(f => `${f.name}-${f.size}`)
    );

    const uniqueNewFiles = newFiles.filter(file => {
      const fileKey = `${file.name}-${file.size}`;
      return !existingFiles.has(fileKey);
    });

    if (uniqueNewFiles.length === 0) {
      setDuplicateMessage('All selected files are already in the list');
      setTimeout(() => setDuplicateMessage(''), 3000);
      return;
    }

    // Add to upload queue
    setUploadQueue(prev => [...prev, ...uniqueNewFiles]);

    // Show info about duplicates if any
    const duplicateCount = newFiles.length - uniqueNewFiles.length;
    if (duplicateCount > 0) {
      setDuplicateMessage(`${duplicateCount} duplicate file(s) were skipped`);
      setTimeout(() => setDuplicateMessage(''), 3000);
    }

    // Start processing queue with delay to allow React state updates
    setTimeout(() => {
      processUploadQueue();
    }, 500);
  }, [files, processUploadQueue]);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);

    const droppedFiles = Array.from(e.dataTransfer.files);
    addFiles(droppedFiles, true);
  }, [addFiles]);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
  }, []);

  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFiles = Array.from(e.target.files || []);
    addFiles(selectedFiles, false);

    // Reset input
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  }, [addFiles]);

  const removeFile = useCallback(async (file: UploadedFile, index: number) => {
    try {
      // If file is uploading, cancel it first
      if (file.uploadStatus === 'uploading' && file.abortController) {
        file.abortController.abort();
      }

      // If file is uploaded, delete from server
      if (file.uploadStatus === 'completed' && file.id > 0) {
        await apiService.deleteTempFile(file.id);
      }

      // Remove from local state
      const newFiles = files.filter((_, i) => i !== index);
      onFilesChange(newFiles);
    } catch (error) {
      // Still remove from UI even if server delete fails
      const newFiles = files.filter((_, i) => i !== index);
      onFilesChange(newFiles);
    }
  }, [files, onFilesChange]);

  const cancelUpload = useCallback((file: UploadedFile, index: number) => {
    // Cancel upload if in progress
    if (file.abortController) {
      file.abortController.abort();
    }

    // Update status to cancelled
    const cancelledFiles = files.map((f, i) =>
      i === index
        ? { ...f, uploadStatus: 'cancelled' as const }
        : f
    );
    onFilesChange(cancelledFiles);
  }, [files, onFilesChange]);

  const retryUpload = useCallback(async (file: UploadedFile, index: number) => {
    // Reset status and retry
    const retryingFiles = files.map((f, i) => 
      i === index 
        ? { ...f, uploadStatus: 'uploading', uploadProgress: 0, error: undefined }
        : f
    );
    onFilesChange(retryingFiles);

    try {
      const fileObj = new File([], file.name, { lastModified: Date.now() });
      const result = await apiService.uploadTempFile(fileObj, (progress) => {
        const progressFiles = files.map((f, i) => 
          i === index 
            ? { ...f, uploadProgress: progress }
            : f
        );
        onFilesChange(progressFiles);
      });

      const successFiles = files.map((f, i) => 
        i === index 
          ? { 
              ...f, 
              id: result.temp_upload_id,
              tempFilename: result.temp_filename,
              uploadProgress: 100,
              uploadStatus: 'completed'
            }
          : f
      );
      onFilesChange(successFiles);

    } catch (error: any) {
      const errorFiles = files.map((f, i) => 
        i === index 
          ? { 
              ...f, 
              uploadStatus: 'failed',
              error: error.message || 'Upload failed'
            }
          : f
      );
      onFilesChange(errorFiles);
    }
  }, [files, onFilesChange]);

  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  const getStatusColor = (status: UploadedFile['uploadStatus']) => {
    switch (status) {
      case 'uploading': return 'text-blue-600';
      case 'completed': return 'text-green-600';
      case 'failed': return 'text-red-600';
      case 'cancelled': return 'text-gray-600';
      default: return 'text-gray-600';
    }
  };

  const getStatusIcon = (file: UploadedFile) => {
    switch (file.uploadStatus) {
      case 'uploading':
        return <SpinnerIcon className="w-4 h-4 text-blue-600 animate-spin" />;
      case 'completed':
        return <CheckIcon className="w-4 h-4 text-green-600" />;
      case 'failed':
        return <XIcon className="w-4 h-4 text-red-600" />;
      case 'cancelled':
        return <StopIcon className="w-4 h-4 text-gray-600" />;
      default:
        return <DocumentIcon className="w-4 h-4 text-gray-400" />;
    }
  };

  return (
    <div className={`${className}`}>
      {/* Drag & Drop Area */}
      <div
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        className={`
          border-2 border-dashed rounded-lg transition-all duration-200 cursor-pointer min-h-[300px] flex flex-col
          ${isDragOver 
            ? 'border-primary bg-primary/5 scale-[1.02]' 
            : 'border-slate-300 hover:border-slate-400'
          }
        `}
        onClick={() => fileInputRef.current?.click()}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept={accept}
          multiple={multiple}
          onChange={handleFileSelect}
          className="hidden"
        />
        
        {files.length === 0 && uploadQueue.length === 0 ? (
          // Empty state
          <div className="flex-1 flex items-center justify-center p-8">
            <div className="text-center space-y-4">
              <div className="mx-auto w-16 h-16 text-slate-400">
                <UploadIcon />
              </div>
              <div>
                <p className="text-slate-600 font-medium text-lg">
                  Drag & drop your files here
                </p>
                <p className="text-sm text-slate-500 mt-2">
                  or <span className="text-primary font-semibold">browse files</span>
                </p>
                <p className="text-xs text-slate-400 mt-3">
                  Supports FASTQ (.fastq, .fq, .gz) and FASTA (.fasta, .fa) files<br/>
                  Upload up to {maxConcurrentUploads} files simultaneously
                </p>
              </div>
            </div>
          </div>
        ) : (
          // File list with upload progress
          <div className="flex-1 flex flex-col p-4">
            <div className="flex items-center justify-between mb-4">
              <h4 className="text-sm font-semibold text-slate-700">
                Files ({files.length}{uploadQueue.length > 0 ? ` + ${uploadQueue.length} queued` : ''})
              </h4>
              <p className="text-xs text-slate-500">
                Click to add more files or drag & drop
              </p>
            </div>
            
            {duplicateMessage && (
              <div className="mb-3 p-2 bg-yellow-50 border border-yellow-200 rounded text-sm text-yellow-700">
                {duplicateMessage}
              </div>
            )}
            
            <div className="flex-1 overflow-auto max-h-[400px] min-h-[200px] border border-slate-200 rounded-lg bg-slate-50">
              <div className="p-2 space-y-2">
                {files.map((file, index) => (
                  <div
                    key={`${file.name}-${index}`}
                    className="p-3 bg-white rounded-lg border border-slate-200 hover:border-slate-300 transition-colors"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center space-x-3 flex-1 min-w-0">
                        <div className="flex-shrink-0">
                          {getStatusIcon(file)}
                        </div>
                        
                        <div className="flex-1 min-w-0">
                          <div className="text-sm text-slate-800 font-medium truncate" title={file.name}>
                            {file.name}
                          </div>
                          <div className="flex items-center space-x-3 text-xs text-slate-500 mt-1">
                            <span>{formatFileSize(file.size)}</span>
                            <span>•</span>
                            <span className={getStatusColor(file.uploadStatus)}>
                              {file.uploadStatus === 'uploading' && `${file.uploadProgress}%`}
                              {file.uploadStatus === 'completed' && 'Uploaded'}
                              {file.uploadStatus === 'failed' && 'Failed'}
                              {file.uploadStatus === 'cancelled' && 'Cancelled'}
                            </span>
                          </div>
                          
                          {/* Progress Bar */}
                          {file.uploadStatus === 'uploading' && (
                            <div className="mt-2 w-full bg-gray-200 rounded-full h-1.5">
                              <div 
                                className="bg-blue-600 h-1.5 rounded-full transition-all duration-300" 
                                style={{ width: `${file.uploadProgress}%` }}
                              ></div>
                            </div>
                          )}
                          
                          {/* Error Message */}
                          {file.uploadStatus === 'failed' && file.error && (
                            <div className="mt-2 p-2 bg-red-50 border border-red-200 rounded text-xs text-red-700">
                              <div className="flex items-start space-x-2">
                                <span className="text-red-500 font-bold flex-shrink-0">⚠</span>
                                <div className="flex-1">
                                  <div className="font-semibold mb-1">Upload Failed</div>
                                  <div className="text-red-600">{file.error}</div>
                                </div>
                              </div>
                            </div>
                          )}
                        </div>
                      </div>
                      
                      {/* Action Buttons */}
                      <div className="flex items-center space-x-1 ml-2">
                        {file.uploadStatus === 'uploading' && (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              cancelUpload(file, index);
                            }}
                            className="p-1.5 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded transition-colors"
                            title="Cancel upload"
                          >
                            <StopIcon className="w-3.5 h-3.5" />
                          </button>
                        )}
                        
                        {file.uploadStatus === 'failed' && (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              retryUpload(file, index);
                            }}
                            className="p-1.5 text-slate-400 hover:text-blue-500 hover:bg-blue-50 rounded transition-colors"
                            title="Retry upload"
                          >
                            <RefreshIcon className="w-3.5 h-3.5" />
                          </button>
                        )}
                        
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            removeFile(file, index);
                          }}
                          className="p-1.5 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded transition-colors"
                          title="Remove file"
                        >
                          <TrashIcon className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
                
                {/* Show queued files */}
                {uploadQueue.map((file, index) => (
                  <div
                    key={`queued-${file.name}-${index}`}
                    className="p-3 bg-slate-100 rounded-lg border border-slate-200"
                  >
                    <div className="flex items-center space-x-3">
                      <ClockIcon className="w-4 h-4 text-slate-400" />
                      <div className="flex-1 min-w-0">
                        <div className="text-sm text-slate-600 font-medium truncate">
                          {file.name}
                        </div>
                        <div className="text-xs text-slate-500">
                          {formatFileSize(file.size)} • Queued for upload
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
});

// Icons
const UploadIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
  </svg>
);

const DocumentIcon = ({ className = "w-4 h-4" }: { className?: string }) => (
  <svg xmlns="http://www.w3.org/2000/svg" className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
  </svg>
);

const TrashIcon = ({ className = "w-4 h-4" }: { className?: string }) => (
  <svg xmlns="http://www.w3.org/2000/svg" className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1-1v3M4 7h16" />
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

const SpinnerIcon = ({ className = "w-4 h-4" }: { className?: string }) => (
  <svg className={className} viewBox="0 0 24 24" fill="none">
    <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeDasharray="32" strokeDashoffset="32">
      <animate attributeName="stroke-dashoffset" dur="1s" values="32;0" repeatCount="indefinite"/>
    </circle>
  </svg>
);

const StopIcon = ({ className = "w-4 h-4" }: { className?: string }) => (
  <svg xmlns="http://www.w3.org/2000/svg" className={className} viewBox="0 0 20 20" fill="currentColor">
    <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8 7a1 1 0 00-1 1v4a1 1 0 001 1h4a1 1 0 001-1V8a1 1 0 00-1-1H8z" clipRule="evenodd" />
  </svg>
);

const RefreshIcon = ({ className = "w-4 h-4" }: { className?: string }) => (
  <svg xmlns="http://www.w3.org/2000/svg" className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
  </svg>
);

const ClockIcon = ({ className = "w-4 h-4" }: { className?: string }) => (
  <svg xmlns="http://www.w3.org/2000/svg" className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
  </svg>
);
export default FileUpload;
