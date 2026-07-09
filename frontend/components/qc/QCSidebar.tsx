import React from 'react';
import { QCSidebarProps, Sample } from './types';

const QCSidebar: React.FC<QCSidebarProps> = ({ samples, selectedSampleId, onSelectSample }) => {
    // Helper function to get status badge color directly from qc_status
    const getStatusBadgeColorFromQcStatus = (qcStatus: string) => {
        switch (qcStatus) {
            case 'passed':
                return 'bg-green-500';
            case 'warning':
                return 'bg-yellow-500';
            case 'failed':
                return 'bg-red-500';
            default:
                return 'bg-gray-500';
        }
    };


    // Helper function to get hover/selection background color from qc_status
    const getSelectionColorFromQcStatus = (qcStatus: string) => {
        switch (qcStatus) {
            case 'passed':
                return 'text-green-600 bg-green-50 border-green-200';
            case 'warning':
                return 'text-yellow-600 bg-yellow-50 border-yellow-200';
            case 'failed':
                return 'text-red-600 bg-red-50 border-red-200';
            default:
                return 'text-gray-600 bg-gray-50 border-gray-200';
        }
    };

    return (
        <aside className="w-64 bg-white border-r border-gray-200 flex flex-col h-full">
            {/* Header */}
            <div className="p-4 border-b border-gray-200">
                <h2 className="text-lg font-semibold text-gray-800">QC Analysis</h2>
            </div>

            {/* Sample List */}
            <div className="flex-1 overflow-y-auto">
                {/* Overview Option */}
                <div
                    className={`p-3 cursor-pointer transition-colors hover:bg-gray-50 border-b border-gray-100 ${
                        selectedSampleId === null ? 'bg-blue-50 border-l-4 border-l-blue-500' : ''
                    }`}
                    onClick={() => onSelectSample(null)}
                >
                    <div className="flex items-center">
                        <svg className="w-5 h-5 mr-2 text-gray-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
                        </svg>
                        <span className="font-medium text-gray-700">Overview</span>
                    </div>
                </div>

                {/* Sample Items */}
                <div className="p-2">
                    <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider px-2 py-1">
                        Samples ({samples.length})
                    </div>
                    {samples.map((sample) => (
                        <div
                            key={sample.id}
                            className={`p-2 rounded-lg cursor-pointer transition-all mb-1 border ${
                                selectedSampleId === sample.id
                                    ? getSelectionColorFromQcStatus(sample.qc_status)
                                    : 'hover:bg-gray-50 border-transparent'
                            }`}
                            onClick={() => onSelectSample(sample.id)}
                        >
                            <div className="flex items-center justify-between">
                                <div className="flex items-center flex-1 min-w-0">
                                    <div className={`w-2 h-2 rounded-full mr-2 flex-shrink-0 ${getStatusBadgeColorFromQcStatus(sample.qc_status)}`} />
                                    <span className="text-sm font-medium text-gray-700 truncate">
                                        {sample.name}
                                    </span>
                                </div>
                                <div className="text-right">
                                    <div className="text-xs text-gray-600">
                                        {sample.summary?.totalSequences ?
                                            (typeof sample.summary.totalSequences === 'string' ?
                                                // Try to parse string and add commas if it's a number
                                                (!isNaN(Number(sample.summary.totalSequences.replace(/,/g, ''))) ?
                                                    new Intl.NumberFormat('en-US').format(Number(sample.summary.totalSequences.replace(/,/g, ''))) :
                                                    sample.summary.totalSequences
                                                ) :
                                                new Intl.NumberFormat('en-US').format(Number(sample.summary.totalSequences))
                                            ) : 'N/A'
                                        }
                                    </div>
                                    <div className="text-xs text-gray-500">
                                        Q{sample.summary?.avgQuality || 'N/A'}
                                    </div>
                                </div>
                            </div>
                            {sample.group && (
                                <div className="text-xs text-gray-500 mt-1 ml-4">
                                    Group: {sample.group}
                                </div>
                            )}
                        </div>
                    ))}
                </div>
            </div>

            {/* Footer */}
            <div className="p-3 border-t border-gray-200 bg-gray-50">
                <div className="text-xs text-gray-500">
                    Total Samples: {samples.length}
                </div>
            </div>
        </aside>
    );
};

export default QCSidebar;