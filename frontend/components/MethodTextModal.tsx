
import React, { useState, useEffect, useRef } from 'react';
import Modal from './Modal';

interface MethodTextModalProps {
  isOpen: boolean;
  onClose: () => void;
  workbenchId: number;
  workbenchName: string;
}

interface MethodData {
  method_text: string;
  workbench_name: string;
  pipeline_steps: any[];
  sample_count: number;
  layout: string;
  species: string;
}

export default function MethodTextModal({ isOpen, onClose, workbenchId, workbenchName }: MethodTextModalProps): React.ReactNode {
  const [methodData, setMethodData] = useState<MethodData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const textRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (isOpen && workbenchId) {
      fetchMethodText();
    }
  }, [isOpen, workbenchId]);

  useEffect(() => {
    if (!isOpen) {
      setCopied(false);
      setError(null);
    }
  }, [isOpen]);

  const fetchMethodText = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`/api/workbenches/${workbenchId}/method-text`, {
        credentials: 'include'
      });
      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.error || 'Failed to fetch method text');
      }
      const data = await response.json();
      setMethodData(data);
    } catch (err: any) {
      setError(err.message || 'Failed to generate method text');
    } finally {
      setLoading(false);
    }
  };

  const handleCopy = async () => {
    if (!methodData) return;
    try {
      await navigator.clipboard.writeText(methodData.method_text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback for older browsers
      const range = document.createRange();
      if (textRef.current) {
        range.selectNodeContents(textRef.current);
        const selection = window.getSelection();
        selection?.removeAllRanges();
        selection?.addRange(range);
        document.execCommand('copy');
        selection?.removeAllRanges();
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      }
    }
  };

  const getStepIcon = (step: string) => {
    const icons: Record<string, string> = {
      qc: '1',
      clean: '2',
      alignment: '3',
      count: '4',
      deg: '5',
    };
    return icons[step] || '?';
  };

  const getStepLabel = (step: string, tool: string) => {
    const labels: Record<string, string> = {
      qc: 'Quality Control',
      clean: 'Preprocessing',
      alignment: 'Alignment',
      count: 'Quantification',
      deg: 'Differential Expression',
    };
    const toolLabels: Record<string, string> = {
      fastqc: 'FastQC',
      multiqc: 'MultiQC',
      fastp: 'fastp',
      trimmomatic_only: 'Trimmomatic',
      prinseq_only: 'PRINSEQ',
      trimmomatic_prinseq: 'Trimmomatic + PRINSEQ',
      hisat2: 'HISAT2',
      bowtie: 'Bowtie',
      bowtie2: 'Bowtie2',
      stringtie: 'StringTie',
      rsem: 'RSEM',
      deseq2: 'DESeq2',
      edger: 'edgeR',
    };
    return `${labels[step] || step} — ${toolLabels[tool] || tool}`;
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Method Section for Paper" size="lg">
      {loading ? (
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin w-8 h-8 border-4 border-primary border-t-transparent rounded-full"></div>
          <span className="ml-3 text-slate-600">Generating method text...</span>
        </div>
      ) : error ? (
        <div className="text-center py-8">
          <svg className="w-12 h-12 mx-auto text-red-400 mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
          </svg>
          <p className="text-slate-600 mb-4">{error}</p>
          <button
            onClick={fetchMethodText}
            className="px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary-dark transition-colors"
          >
            Try Again
          </button>
        </div>
      ) : methodData ? (
        <div className="space-y-6">
          {/* Workbench Info */}
          <div className="bg-slate-50 rounded-lg p-4">
            <div className="text-sm text-slate-500 mb-1">Workbench</div>
            <div className="font-semibold text-slate-800">{methodData.workbench_name}</div>
            <div className="flex gap-4 mt-2 text-sm text-slate-500">
              <span>{methodData.sample_count} samples</span>
              <span>{methodData.layout === 'pe' ? 'Paired-end' : 'Single-end'}</span>
              {methodData.species && <span className="italic">{methodData.species.replace('_', ' ')}</span>}
            </div>
          </div>

          {/* Pipeline Steps Summary */}
          <div>
            <h3 className="text-sm font-semibold text-slate-600 uppercase tracking-wide mb-3">Pipeline Steps</h3>
            <div className="flex flex-wrap gap-2">
              {methodData.pipeline_steps.map((step: any, idx: number) => (
                <div
                  key={idx}
                  className="flex items-center bg-white border border-slate-200 rounded-lg px-3 py-2 text-sm"
                >
                  <span className="w-6 h-6 bg-primary text-white rounded-full flex items-center justify-center text-xs font-bold mr-2">
                    {getStepIcon(step.step)}
                  </span>
                  <span className="text-slate-700">{getStepLabel(step.step, step.tool)}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Method Text */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-slate-600 uppercase tracking-wide">Generated Method Text</h3>
              <button
                onClick={handleCopy}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                  copied
                    ? 'bg-green-100 text-green-700 border border-green-300'
                    : 'bg-primary text-white hover:bg-primary-dark'
                }`}
              >
                {copied ? (
                  <>
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                    Copied!
                  </>
                ) : (
                  <>
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3" />
                    </svg>
                    Copy to Clipboard
                  </>
                )}
              </button>
            </div>
            <div
              ref={textRef}
              className="bg-slate-50 rounded-lg p-5 text-slate-700 leading-relaxed text-sm border border-slate-200 select-all cursor-text"
            >
              {methodData.method_text}
            </div>
            <p className="text-xs text-slate-400 mt-2">
              * This text is auto-generated based on the pipeline configuration.
              Please verify tool versions and add citation references before submission.
            </p>
          </div>
        </div>
      ) : null}
    </Modal>
  );
}
