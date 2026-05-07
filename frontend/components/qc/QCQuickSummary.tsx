import React from 'react';

interface AIAnalysis {
  overall_assessment: string;
  confidence_score: number;
  experiment_type: string;
  quality_evaluation: {
    usability: 'excellent' | 'good' | 'fair' | 'poor';
    notes: string[];
    strengths: string[];
  };
  expected_outcomes: {
    alignment_rate: string;
    sequence_quality: string;
    coverage_uniformity: string;
  };
}

interface QCQuickSummaryProps {
  analysis?: AIAnalysis | null;
  totalSequences: number | string;
  avgQuality: number | string;
  avgLength: number | string;
  aiAnalysisStatus?: string;
  aiAnalysisReason?: string;
}

const QCQuickSummary: React.FC<QCQuickSummaryProps> = ({
  analysis,
  totalSequences,
  avgQuality,
  avgLength,
  aiAnalysisStatus,
  aiAnalysisReason
}) => {
  // Get quality color based on usability
  const getQualityColor = (usability?: string) => {
    switch (usability) {
      case 'excellent':
        return { bg: 'bg-green-100', text: 'text-green-800', border: 'border-green-300' };
      case 'good':
        return { bg: 'bg-blue-100', text: 'text-blue-800', border: 'border-blue-300' };
      case 'fair':
        return { bg: 'bg-yellow-100', text: 'text-yellow-800', border: 'border-yellow-300' };
      case 'poor':
        return { bg: 'bg-red-100', text: 'text-red-800', border: 'border-red-300' };
      default:
        return { bg: 'bg-gray-100', text: 'text-gray-800', border: 'border-gray-300' };
    }
  };

  const qualityColors = analysis ? getQualityColor(analysis.quality_evaluation.usability) : getQualityColor();

  // Format large numbers with commas
  const formatNumber = (num: string | number): string => {
    if (typeof num === 'string') {
      if (!isNaN(Number(num.replace(/,/g, '')))) {
        return new Intl.NumberFormat('en-US').format(Number(num.replace(/,/g, '')));
      }
      return num;
    }
    return new Intl.NumberFormat('en-US').format(num);
  };

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-gray-800">Quick Summary</h3>
        {analysis && (
          <span className={`inline-flex items-center px-2.5 py-1 text-xs font-medium rounded-full ${qualityColors.bg} ${qualityColors.text}`}>
            {analysis.quality_evaluation.usability.toUpperCase()}
          </span>
        )}
      </div>

      {/* Quality Score Card */}
      <div className={`rounded-lg p-4 mb-4 ${qualityColors.bg} border ${qualityColors.border}`}>
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-medium text-gray-700">Overall Quality</span>
          {analysis && (
            <span className={`text-2xl font-bold ${qualityColors.text}`}>
              {(analysis.confidence_score * 100).toFixed(0)}%
            </span>
          )}
          {!analysis && aiAnalysisStatus !== 'skipped' && (
            <span className="text-2xl font-bold text-gray-400">--</span>
          )}
        </div>
        {analysis ? (
          <p className="text-sm text-gray-700 leading-relaxed">
            {analysis.overall_assessment.substring(0, 150)}
            {analysis.overall_assessment.length > 150 && '...'}
          </p>
        ) : aiAnalysisStatus === 'skipped' ? (
          <p className="text-sm text-gray-500 italic">
            AI analysis disabled in settings
          </p>
        ) : (
          <p className="text-sm text-gray-500 italic">
            Quality analysis pending...
          </p>
        )}
      </div>

      {/* Key Metrics Grid */}
      <div className="grid grid-cols-1 gap-3">
        {/* Total Sequences */}
        <div className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
          <div className="flex items-center gap-2">
            <svg className="w-4 h-4 text-gray-500" fill="currentColor" viewBox="0 0 20 20">
              <path d="M3 4a1 1 0 011-1h12a1 1 0 011 1v2a1 1 0 01-1 1H4a1 1 0 01-1-1V4zM3 10a1 1 0 011-1h6a1 1 0 011 1v6a1 1 0 01-1 1H4a1 1 0 01-1-1v-6zM14 9a1 1 0 00-1 1v6a1 1 0 001 1h2a1 1 0 001-1v-6a1 1 0 00-1-1h-2z"/>
            </svg>
            <span className="text-sm text-gray-600">Total Sequences</span>
          </div>
          <span className="text-sm font-bold text-gray-800">
            {formatNumber(totalSequences)}
          </span>
        </div>

        {/* Average Quality */}
        <div className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
          <div className="flex items-center gap-2">
            <svg className="w-4 h-4 text-gray-500" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M5 2a1 1 0 011 1v1h1a1 1 0 010 2H6v1a1 1 0 01-2 0V6H3a1 1 0 010-2h1V3a1 1 0 011-1zm0 10a1 1 0 011 1v1h1a1 1 0 110 2H6v1a1 1 0 11-2 0v-1H3a1 1 0 110-2h1v-1a1 1 0 011-1zM12 2a1 1 0 01.967.744L14.146 7.2 17.5 9.134a1 1 0 010 1.732l-3.354 1.935-1.18 4.455a1 1 0 01-1.933 0L9.854 12.8 6.5 10.866a1 1 0 010-1.732l3.354-1.935 1.18-4.455A1 1 0 0112 2z" clipRule="evenodd"/>
            </svg>
            <span className="text-sm text-gray-600">Avg Quality</span>
          </div>
          <span className="text-sm font-bold text-gray-800">
            Q{avgQuality}
          </span>
        </div>

        {/* Average Length */}
        <div className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
          <div className="flex items-center gap-2">
            <svg className="w-4 h-4 text-gray-500" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M3 17a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm3.293-7.707a1 1 0 011.414 0L9 10.586V3a1 1 0 112 0v7.586l1.293-1.293a1 1 0 111.414 1.414l-3 3a1 1 0 01-1.414 0l-3-3a1 1 0 010-1.414z" clipRule="evenodd"/>
            </svg>
            <span className="text-sm text-gray-600">Avg Length</span>
          </div>
          <span className="text-sm font-bold text-gray-800">
            {avgLength} bp
          </span>
        </div>
      </div>

      {/* Expected Outcomes (if available) */}
      {analysis && analysis.expected_outcomes && (
        <div className="mt-4 pt-4 border-t border-gray-200">
          <h4 className="text-sm font-medium text-gray-700 mb-2">Expected Outcomes</h4>
          <div className="grid grid-cols-3 gap-2 text-xs">
            <div className="text-center p-2 bg-purple-50 rounded">
              <div className="text-gray-600">Alignment</div>
              <div className="font-bold text-purple-700">{analysis.expected_outcomes.alignment_rate}</div>
            </div>
            <div className="text-center p-2 bg-purple-50 rounded">
              <div className="text-gray-600">Quality</div>
              <div className="font-bold text-purple-700">{analysis.expected_outcomes.sequence_quality}</div>
            </div>
            <div className="text-center p-2 bg-purple-50 rounded">
              <div className="text-gray-600">Coverage</div>
              <div className="font-bold text-purple-700">{analysis.expected_outcomes.coverage_uniformity}</div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default QCQuickSummary;