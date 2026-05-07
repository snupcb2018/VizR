import React from 'react';
import { QCSampleDetailProps, SampleStatus } from './types';
import QCStatistics from './QCStatistics';
import QCAIAnalysis from './QCAIAnalysis';
import QCQuickSummary from './QCQuickSummary';
import {
    ChartContainer,
    PerBaseQualityChart,
    PerSequenceQualityChart,
    PerBaseSequenceContentChart,
    PerSequenceGcContentChart,
    PerBaseNContentChart,
    SequenceLengthDistributionChart,
    AdapterContentChart,
    DuplicationLevelsChart
} from './QCCharts';

const QCSampleDetail: React.FC<QCSampleDetailProps> = ({ sample }) => {

    const formatNumber = (num: string | number): string => {
        if (typeof num === 'string') {
            // Try to parse string and add commas if it's a number
            if (!isNaN(Number(num.replace(/,/g, '')))) {
                return new Intl.NumberFormat('en-US').format(Number(num.replace(/,/g, '')));
            }
            return num; // Return original string if not a parseable number
        }
        return new Intl.NumberFormat('en-US').format(num);
    };

    // Helper function to get module status from FastQC module name
    const getModuleStatus = (moduleName: string): 'pass' | 'warn' | 'fail' | undefined => {
        if (!sample.statistics?.module_details) return undefined;

        const moduleStatus = sample.statistics.module_details[moduleName]?.status;
        if (moduleStatus === 'pass' || moduleStatus === 'warn' || moduleStatus === 'fail') {
            return moduleStatus as 'pass' | 'warn' | 'fail';
        }
        return undefined;
    };

    return (
        <div className="p-6">
            {/* Header */}
            <div className="mb-6">
                <div className="flex items-center justify-between">
                    <div>
                        <h1 className="text-2xl font-bold text-gray-800">{sample.name}</h1>
                        {sample.group && (
                            <p className="text-sm text-gray-600 mt-1">Group: {sample.group}</p>
                        )}
                    </div>
                    {sample.summary?.filename && (
                        <span className="text-sm text-gray-500">
                            File: {sample.summary.filename}
                        </span>
                    )}
                </div>

                {/* Summary Statistics */}
                <div className="grid grid-cols-4 gap-4 mt-4">
                    <div className="bg-white rounded-lg border border-gray-200 p-4">
                        <div className="text-sm font-medium text-gray-500">Total Sequences</div>
                        <div className="text-xl font-bold text-gray-800 mt-1">
                            {formatNumber(sample.summary.totalSequences)}
                        </div>
                    </div>
                    <div className="bg-white rounded-lg border border-gray-200 p-4">
                        <div className="text-sm font-medium text-gray-500">Average Length</div>
                        <div className="text-xl font-bold text-gray-800 mt-1">
                            {sample.summary.avgLength} bp
                        </div>
                    </div>
                    <div className="bg-white rounded-lg border border-gray-200 p-4">
                        <div className="text-sm font-medium text-gray-500">Average Quality</div>
                        <div className="text-xl font-bold text-gray-800 mt-1">
                            {sample.summary.avgQuality}
                        </div>
                    </div>
                    <div className="bg-white rounded-lg border border-gray-200 p-4">
                        <div className="text-sm font-medium text-gray-500">Sample ID</div>
                        <div className="text-xl font-bold text-gray-800 mt-1">
                            {sample.id}
                        </div>
                    </div>
                </div>
            </div>

            {/* Layer 1: Core Metrics Summary (2 columns) */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
                {/* Module Statistics */}
                {sample.statistics && (
                    <QCStatistics
                        statistics={sample.statistics}
                        sampleName={sample.name}
                    />
                )}

                {/* Quick Summary */}
                <QCQuickSummary
                    analysis={sample.ai_analysis}
                    totalSequences={sample.summary.totalSequences}
                    avgQuality={sample.summary.avgQuality}
                    avgLength={sample.summary.avgLength}
                    aiAnalysisStatus={sample.ai_analysis_status}
                    aiAnalysisReason={sample.ai_analysis_reason}
                />
            </div>

            {/* Layer 2: Detailed Quality Analysis (Full Width) */}
            <div className="mb-6">
                <div className="bg-white rounded-lg border border-gray-200">
                    <div className="p-6 border-b border-gray-200">
                        <h2 className="text-xl font-bold text-gray-800 flex items-center gap-2">
                            <svg className="w-6 h-6 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                            </svg>
                            Detailed Quality Analysis
                        </h2>
                        <p className="text-sm text-gray-500 mt-1">
                            Comprehensive AI-powered analysis of sequencing data quality
                        </p>
                    </div>
                    <div className="p-6">
                        <QCAIAnalysis
                            analysis={sample.ai_analysis}
                            sampleName={sample.name}
                            aiAnalysisStatus={sample.ai_analysis_status}
                            aiAnalysisReason={sample.ai_analysis_reason}
                        />
                    </div>
                </div>
            </div>

            {/* Layer 3: Quality Metrics Charts (2 column grid) */}
            <div className="mb-6">
                <div className="mb-4">
                    <h2 className="text-xl font-bold text-gray-800 flex items-center gap-2">
                        <svg className="w-6 h-6 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                        </svg>
                        Quality Metrics Visualization
                    </h2>
                    <p className="text-sm text-gray-500 mt-1">
                        Interactive charts showing detailed quality metrics across different dimensions
                    </p>
                </div>
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Per Base Quality */}
                {sample.metrics.per_base_quality && sample.metrics.per_base_quality.length > 0 && (
                    <ChartContainer title="Per Base Sequence Quality" status={getModuleStatus('Per base sequence quality')}>
                        <PerBaseQualityChart data={sample.metrics.per_base_quality} />
                    </ChartContainer>
                )}

                {/* Per Sequence Quality */}
                {sample.metrics.per_sequence_quality && sample.metrics.per_sequence_quality.length > 0 && (
                    <ChartContainer title="Per Sequence Quality Scores" status={getModuleStatus('Per sequence quality scores')}>
                        <PerSequenceQualityChart data={sample.metrics.per_sequence_quality} />
                    </ChartContainer>
                )}

                {/* Per Base Sequence Content */}
                {sample.metrics.per_base_sequence_content && sample.metrics.per_base_sequence_content.length > 0 && (
                    <ChartContainer title="Per Base Sequence Content" status={getModuleStatus('Per base sequence content')}>
                        <PerBaseSequenceContentChart data={sample.metrics.per_base_sequence_content} />
                    </ChartContainer>
                )}

                {/* Per Sequence GC Content */}
                {sample.metrics.per_sequence_gc_content && sample.metrics.per_sequence_gc_content.length > 0 && (
                    <ChartContainer title="Per Sequence GC Content" status={getModuleStatus('Per sequence GC content')}>
                        <PerSequenceGcContentChart data={sample.metrics.per_sequence_gc_content} />
                    </ChartContainer>
                )}

                {/* Per Base N Content */}
                {sample.metrics.per_base_n_content && sample.metrics.per_base_n_content.length > 0 && (
                    <ChartContainer title="Per Base N Content" status={getModuleStatus('Per base N content')}>
                        <PerBaseNContentChart data={sample.metrics.per_base_n_content} />
                    </ChartContainer>
                )}

                {/* Sequence Length Distribution */}
                {sample.metrics.sequence_length_distribution && sample.metrics.sequence_length_distribution.length > 0 && (
                    <ChartContainer title="Sequence Length Distribution" status={getModuleStatus('Sequence Length Distribution')}>
                        <SequenceLengthDistributionChart data={sample.metrics.sequence_length_distribution} />
                    </ChartContainer>
                )}

                {/* Adapter Content */}
                {sample.metrics.adapter_content && sample.metrics.adapter_content.length > 0 && (
                    <ChartContainer title="Adapter Content" status={getModuleStatus('Adapter Content')}>
                        <AdapterContentChart data={sample.metrics.adapter_content} />
                    </ChartContainer>
                )}

                {/* Duplication Levels */}
                {sample.metrics.duplication_levels && sample.metrics.duplication_levels.length > 0 && (
                    <ChartContainer title="Sequence Duplication Levels" status={getModuleStatus('Sequence Duplication Levels')}>
                        <DuplicationLevelsChart data={sample.metrics.duplication_levels} />
                    </ChartContainer>
                )}
                </div>
            </div>

            {/* No Data Message */}
            {(!sample.metrics || Object.keys(sample.metrics).length === 0) && (
                <div className="text-center py-12 bg-gray-50 rounded-lg">
                    <svg className="mx-auto h-12 w-12 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                    </svg>
                    <h3 className="mt-2 text-sm font-medium text-gray-900">No chart data available</h3>
                    <p className="mt-1 text-sm text-gray-500">
                        Quality metrics are not available for this sample.
                    </p>
                </div>
            )}
        </div>
    );
};

export default QCSampleDetail;