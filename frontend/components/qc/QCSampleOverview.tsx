import React from 'react';
import { QCSampleOverviewProps, Sample, SampleStatus } from './types';

const QCSampleOverview: React.FC<QCSampleOverviewProps> = ({ samples, onSelectSample, moduleStatistics }) => {
    const getStatusColor = (status: SampleStatus) => {
        switch (status) {
            case SampleStatus.PASS:
                return 'border-green-400 bg-green-50';
            case SampleStatus.WARN:
                return 'border-yellow-400 bg-yellow-50';
            case SampleStatus.FAIL:
                return 'border-red-400 bg-red-50';
            default:
                return 'border-gray-400 bg-gray-50';
        }
    };

    const getStatusTextColor = (status: SampleStatus) => {
        switch (status) {
            case SampleStatus.PASS:
                return 'text-green-700 bg-green-100';
            case SampleStatus.WARN:
                return 'text-yellow-700 bg-yellow-100';
            case SampleStatus.FAIL:
                return 'text-red-700 bg-red-100';
            default:
                return 'text-gray-700 bg-gray-100';
        }
    };

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

    return (
        <div className="p-6">
            {/* Header */}
            <div className="mb-6">
                <h1 className="text-2xl font-bold text-gray-800">Quality Control Overview</h1>
                <p className="text-gray-600 mt-2">
                    Click on any sample card to view detailed quality metrics
                </p>
            </div>

            {/* FastQC Module Statistics */}
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
                <div className="bg-white rounded-lg shadow p-4">
                    <div className="text-sm font-medium text-gray-500">Total Samples</div>
                    <div className="text-2xl font-bold text-gray-800 mt-1">
                        {moduleStatistics?.total_samples || samples.length}
                    </div>
                </div>
                <div className="bg-white rounded-lg shadow p-4">
                    <div className="text-sm font-medium text-gray-500">Total Modules</div>
                    <div className="text-2xl font-bold text-blue-600 mt-1">
                        {moduleStatistics?.total_modules || 0}
                    </div>
                </div>
                <div className="bg-white rounded-lg shadow p-4">
                    <div className="text-sm font-medium text-gray-500">Passed Modules</div>
                    <div className="text-2xl font-bold text-green-600 mt-1">
                        {moduleStatistics?.passed_modules || 0}
                    </div>
                </div>
                <div className="bg-white rounded-lg shadow p-4">
                    <div className="text-sm font-medium text-gray-500">Warning Modules</div>
                    <div className="text-2xl font-bold text-yellow-600 mt-1">
                        {moduleStatistics?.warning_modules || 0}
                    </div>
                </div>
                <div className="bg-white rounded-lg shadow p-4">
                    <div className="text-sm font-medium text-gray-500">Failed Modules</div>
                    <div className="text-2xl font-bold text-red-600 mt-1">
                        {moduleStatistics?.failed_modules || 0}
                    </div>
                </div>
            </div>

            {/* Sample Cards Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                {samples.map((sample) => (
                    <div
                        key={sample.id}
                        className={`bg-white rounded-lg shadow-sm border-2 cursor-pointer transition-all hover:shadow-md ${getStatusColor(sample.status)}`}
                        onClick={() => onSelectSample(sample)}
                    >
                        <div className="p-4">
                            {/* Sample Name and Status */}
                            <div className="flex items-start justify-between mb-3">
                                <h3 className="font-semibold text-gray-800 text-sm truncate flex-1">
                                    {sample.name}
                                </h3>
                                <span className={`text-xs px-2 py-1 rounded-full font-medium ${getStatusTextColor(sample.status)}`}>
                                    {sample.status}
                                </span>
                            </div>

                            {/* Group Info */}
                            {sample.group && (
                                <div className="text-xs text-gray-500 mb-3">
                                    Group: {sample.group}
                                </div>
                            )}

                            {/* Summary Metrics */}
                            <div className="space-y-2 text-sm">
                                <div className="flex justify-between items-center">
                                    <span className="text-gray-600">Total Sequences:</span>
                                    <span className="font-medium text-gray-800">
                                        {formatNumber(sample.summary.totalSequences)}
                                    </span>
                                </div>
                                <div className="flex justify-between items-center">
                                    <span className="text-gray-600">Avg Length:</span>
                                    <span className="font-medium text-gray-800">
                                        {sample.summary.avgLength} bp
                                    </span>
                                </div>
                                <div className="flex justify-between items-center">
                                    <span className="text-gray-600">Avg Quality:</span>
                                    <span className="font-medium text-gray-800">
                                        {sample.summary.avgQuality}
                                    </span>
                                </div>
                            </div>

                            {/* View Details Link */}
                            <div className="mt-4 pt-3 border-t border-gray-200">
                                <button className="text-blue-600 hover:text-blue-800 text-sm font-medium flex items-center">
                                    View Details
                                    <svg className="w-4 h-4 ml-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                                    </svg>
                                </button>
                            </div>
                        </div>
                    </div>
                ))}
            </div>

            {/* Empty State */}
            {samples.length === 0 && (
                <div className="text-center py-12">
                    <svg className="mx-auto h-12 w-12 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                    <h3 className="mt-2 text-sm font-medium text-gray-900">No QC results</h3>
                    <p className="mt-1 text-sm text-gray-500">
                        No quality control results found for this workbench.
                    </p>
                </div>
            )}
        </div>
    );
};

export default QCSampleOverview;