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
  recommendations: {
    immediate_actions: string[];
    preprocessing: string[];
    downstream_considerations: string[];
  };
  expected_outcomes: {
    alignment_rate: string;
    sequence_quality: string;
    coverage_uniformity: string;
  };
  evidence?: {
    per_base_quality?: string;
    adapter_content?: string;
    duplication_level?: string;
    n_content?: string;
    sequence_bias?: string;
  };
  decision_rationale?: string[];
  uncertainties?: string[];
  processing_time?: number;
}

interface QCAIAnalysisProps {
  analysis?: AIAnalysis | null;
  sampleName: string;
  aiAnalysisStatus?: string;
  aiAnalysisReason?: string;
}

const QCAIAnalysis: React.FC<QCAIAnalysisProps> = ({ analysis, sampleName, aiAnalysisStatus, aiAnalysisReason }) => {

  // If AI analysis is disabled
  if (aiAnalysisStatus === 'skipped') {
    return (
      <div className="bg-white rounded-lg border border-gray-200 p-6 mb-4">
        {/* Header */}
        <div className="flex items-center justify-between mb-4 pb-4 border-b border-gray-200">
          <div className="flex items-start gap-2">
            {/* Robot Icon - grayed out */}
            <svg className="w-5 h-5 text-gray-400 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
            </svg>
            <div>
              <h3 className="text-lg font-semibold text-gray-700">AI Quality Analysis</h3>
              <p className="text-sm text-gray-500">for {sampleName}</p>
            </div>
          </div>
        </div>

        {/* Disabled Message */}
        <div className="text-center py-8">
          <div className="text-gray-500 mb-2">
            <svg className="w-12 h-12 mx-auto mb-3 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728L5.636 5.636m12.728 12.728L5.636 5.636" />
            </svg>
          </div>
          <p className="text-gray-600 font-medium">AI Analysis Disabled</p>
          <p className="text-sm text-gray-500 mt-1">
            AI quality analysis has been disabled in settings.
          </p>
          <p className="text-xs text-gray-400 mt-2">
            Enable AI analysis in Settings → AI Analysis to get automated quality insights.
          </p>
        </div>
      </div>
    );
  }

  // If no analysis available yet (pending/processing)
  if (!analysis) {
    return (
      <div className="bg-white rounded-lg border border-gray-200 p-6 mb-4">
        {/* Header */}
        <div className="flex items-center justify-between mb-4 pb-4 border-b border-gray-200">
          <div className="flex items-start gap-2">
            {/* Robot Icon */}
            <svg className="w-5 h-5 text-gray-600 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
            </svg>
            <div className="flex-1 max-w-xl pr-3">
              <div className="flex items-center gap-2 mb-1">
                <h3 className="text-lg font-semibold text-gray-800">Quality Assessment</h3>
                <span className="inline-flex items-center px-2 py-1 text-xs font-medium rounded-full bg-blue-100 text-blue-800">
                  Auto-Analysis
                </span>
              </div>
              <p className="text-xs text-gray-500">
                This analysis is provided for reference purposes only. Results may vary depending on experimental conditions and are not absolute. We recommend users conduct their own direct analysis and utilize these results as supplementary guidance.
              </p>
            </div>
          </div>
        </div>

        {/* Empty State */}
        <div className="flex flex-col items-center justify-center py-8">
          <svg className="w-12 h-12 text-gray-300 mb-4" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-12a1 1 0 10-2 0v4a1 1 0 00.293.707l2.828 2.829a1 1 0 101.415-1.415L11 9.586V6z" clipRule="evenodd" />
          </svg>
          <p className="text-gray-500 text-center">
            Quality analysis will appear automatically<br/>
            <span className="text-sm">after FastQC processing completes</span>
          </p>
        </div>
      </div>
    );
  }

  // Get usability color and text
  const getUsabilityConfig = (usability: string) => {
    switch (usability) {
      case 'excellent':
        return { colorClass: 'bg-green-100 text-green-800', text: 'Excellent' };
      case 'good':
        return { colorClass: 'bg-blue-100 text-blue-800', text: 'Good' };
      case 'fair':
        return { colorClass: 'bg-yellow-100 text-yellow-800', text: 'Fair' };
      case 'poor':
        return { colorClass: 'bg-red-100 text-red-800', text: 'Poor' };
      default:
        return { colorClass: 'bg-gray-100 text-gray-800', text: 'Unknown' };
    }
  };

  const usabilityConfig = getUsabilityConfig(analysis.quality_evaluation.usability);

  // Get alert style based on usability
  const getAlertStyle = (usability: string) => {
    switch (usability) {
      case 'excellent':
      case 'good':
        return 'border-green-400 bg-green-50 text-green-700';
      case 'fair':
        return 'border-yellow-400 bg-yellow-50 text-yellow-700';
      case 'poor':
        return 'border-red-400 bg-red-50 text-red-700';
      default:
        return 'border-gray-400 bg-gray-50 text-gray-700';
    }
  };

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-6 mb-4">
      {/* Header */}
      <div className="flex items-center justify-between mb-4 pb-4 border-b border-gray-200">
        <div className="flex items-start gap-2">
          {/* Robot Icon */}
          <svg className="w-5 h-5 text-gray-600 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
          </svg>
          <div className="flex-1 max-w-xl pr-3">
            <div className="flex items-center gap-2 mb-1">
              <h3 className="text-lg font-semibold text-gray-800">Quality Assessment</h3>
              <span className="inline-flex items-center px-2 py-1 text-xs font-medium rounded-full bg-green-100 text-green-800">
                Auto-Generated
              </span>
            </div>
            <p className="text-xs text-gray-500">
              This analysis is provided for reference purposes only. Results may vary depending on experimental conditions and are not absolute. We recommend users conduct their own direct analysis and utilize these results as supplementary guidance.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 text-sm text-gray-500 flex-shrink-0 whitespace-nowrap">
          {/* Experiment Icon */}
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" />
          </svg>
          <span>{analysis.experiment_type}</span>
        </div>
      </div>

      <div className="space-y-4">
        {/* Overall Assessment */}
        <div className={`border-l-4 p-4 ${getAlertStyle(analysis.quality_evaluation.usability)}`}>
          <div className="flex items-center mb-2">
            <svg className="w-5 h-5 mr-2" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
            </svg>
            <h4 className="font-semibold">Overall Assessment</h4>
          </div>
          <p className="text-sm">{analysis.overall_assessment}</p>
        </div>

        {/* Quality Evaluation */}
        <div className="bg-gray-50 p-4 rounded">
          <div className="flex items-center justify-between mb-3">
            <h4 className="font-medium flex items-center gap-2">
              {/* Bulb Icon */}
              <svg className="w-5 h-5 text-yellow-500" fill="currentColor" viewBox="0 0 20 20">
                <path d="M11 3a1 1 0 10-2 0v1a1 1 0 102 0V3zM15.657 5.757a1 1 0 00-1.414-1.414l-.707.707a1 1 0 001.414 1.414l.707-.707zM18 10a1 1 0 01-1 1h-1a1 1 0 110-2h1a1 1 0 011 1zM5.05 6.464A1 1 0 106.464 5.05l-.707-.707a1 1 0 00-1.414 1.414l.707.707zM5 10a1 1 0 01-1 1H3a1 1 0 110-2h1a1 1 0 011 1zM8 16v-1h4v1a2 2 0 11-4 0zM12 14c.015-.34.208-.646.477-.859a4 4 0 10-4.954 0c.27.213.462.519.476.859h4.002z" />
              </svg>
              Quality Evaluation
            </h4>
            <span className={`inline-flex items-center px-2 py-1 text-xs font-medium rounded-full ${usabilityConfig.colorClass}`}>
              {usabilityConfig.text} Quality
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Strengths */}
            {analysis.quality_evaluation.strengths.length > 0 && (
              <div>
                <h5 className="text-sm font-medium text-green-700 mb-2">Strengths:</h5>
                <ul className="space-y-1">
                  {analysis.quality_evaluation.strengths.map((item, idx) => (
                    <li key={idx} className="text-sm flex items-start gap-1">
                      <svg className="w-4 h-4 text-green-600 mt-0.5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                      </svg>
                      <span>{item}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Concerns */}
            {analysis.quality_evaluation.notes.length > 0 && (
              <div>
                <h5 className="text-sm font-medium text-blue-700 mb-2">Analysis Notes:</h5>
                <ul className="space-y-1">
                  {analysis.quality_evaluation.notes.map((item, idx) => (
                    <li key={idx} className="text-sm flex items-start gap-1">
                      <svg className="w-4 h-4 text-blue-600 mt-0.5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
                      </svg>
                      <span>{item}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>

        {/* Recommendations */}
        <div className="bg-blue-50 p-4 rounded">
          <h4 className="font-medium mb-3 flex items-center gap-2">
            {/* Lightning Icon */}
            <svg className="w-5 h-5 text-blue-600" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M11.3 1.046A1 1 0 0112 2v5h4a1 1 0 01.82 1.573l-7 10A1 1 0 018 18v-5H4a1 1 0 01-.82-1.573l7-10a1 1 0 011.12-.38z" clipRule="evenodd" />
            </svg>
            Recommendations
          </h4>

          {/* Immediate Actions */}
          {analysis.recommendations.immediate_actions.length > 0 && (
            <div className="mb-3">
              <h5 className="text-sm font-medium text-red-700 mb-2">⚡ Immediate Actions:</h5>
              <ul className="space-y-1">
                {analysis.recommendations.immediate_actions.map((item, idx) => (
                  <li key={idx} className="text-sm text-red-700">• {item}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Preprocessing */}
          {analysis.recommendations.preprocessing.length > 0 && (
            <div className="mb-3">
              <h5 className="text-sm font-medium text-blue-700 mb-2">🔧 Preprocessing Steps:</h5>
              <ul className="space-y-1">
                {analysis.recommendations.preprocessing.map((item, idx) => (
                  <li key={idx} className="text-sm text-blue-700">• {item}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Downstream Considerations */}
          {analysis.recommendations.downstream_considerations.length > 0 && (
            <div>
              <h5 className="text-sm font-medium text-gray-700 mb-2">📊 Downstream Analysis:</h5>
              <ul className="space-y-1">
                {analysis.recommendations.downstream_considerations.map((item, idx) => (
                  <li key={idx} className="text-sm text-gray-700">• {item}</li>
                ))}
              </ul>
            </div>
          )}
        </div>

        {/* Expected Outcomes */}
        <div className="bg-purple-50 p-4 rounded">
          <h4 className="font-medium mb-3 flex items-center gap-2">
            {/* Chart Icon */}
            <svg className="w-5 h-5 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z" />
            </svg>
            Expected Outcomes
          </h4>
          <div className="grid grid-cols-3 gap-4">
            <div className="text-center p-3 bg-white rounded">
              <div className="text-xs text-gray-600 mb-1">Alignment Rate</div>
              <div className="font-medium text-purple-700">{analysis.expected_outcomes.alignment_rate}</div>
            </div>
            <div className="text-center p-3 bg-white rounded">
              <div className="text-xs text-gray-600 mb-1">Sequence Quality</div>
              <div className="font-medium text-purple-700">{analysis.expected_outcomes.sequence_quality}</div>
            </div>
            <div className="text-center p-3 bg-white rounded">
              <div className="text-xs text-gray-600 mb-1">Coverage Uniformity</div>
              <div className="font-medium text-purple-700">{analysis.expected_outcomes.coverage_uniformity}</div>
            </div>
          </div>
        </div>

        {/* Evidence Section */}
        {analysis.evidence && Object.keys(analysis.evidence).length > 0 && (
          <div className="bg-gray-50 p-4 rounded">
            <h4 className="font-medium mb-3 flex items-center gap-2">
              {/* Evidence Icon */}
              <svg className="w-5 h-5 text-gray-600" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-8.293l-3-3a1 1 0 00-1.414 1.414L10.586 9.5 9.293 8.207a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l3-3z" clipRule="evenodd" />
              </svg>
              Quantitative Evidence
            </h4>
            <div className="grid grid-cols-1 gap-2 text-sm">
              {analysis.evidence.per_base_quality && (
                <div className="flex items-start gap-2">
                  <span className="font-medium text-gray-600">Base Quality:</span>
                  <span className="text-gray-800">{analysis.evidence.per_base_quality}</span>
                </div>
              )}
              {analysis.evidence.adapter_content && (
                <div className="flex items-start gap-2">
                  <span className="font-medium text-gray-600">Adapter Content:</span>
                  <span className="text-gray-800">{analysis.evidence.adapter_content}</span>
                </div>
              )}
              {analysis.evidence.duplication_level && (
                <div className="flex items-start gap-2">
                  <span className="font-medium text-gray-600">Duplication Level:</span>
                  <span className="text-gray-800">{analysis.evidence.duplication_level}</span>
                </div>
              )}
              {analysis.evidence.n_content && (
                <div className="flex items-start gap-2">
                  <span className="font-medium text-gray-600">N Content:</span>
                  <span className="text-gray-800">{analysis.evidence.n_content}</span>
                </div>
              )}
              {analysis.evidence.sequence_bias && (
                <div className="flex items-start gap-2">
                  <span className="font-medium text-gray-600">Sequence Bias:</span>
                  <span className="text-gray-800">{analysis.evidence.sequence_bias}</span>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Decision Rationale */}
        {analysis.decision_rationale && analysis.decision_rationale.length > 0 && (
          <div className="bg-indigo-50 p-4 rounded">
            <h4 className="font-medium mb-3 flex items-center gap-2">
              {/* Decision Icon */}
              <svg className="w-5 h-5 text-indigo-600" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
              </svg>
              Decision Rationale
            </h4>
            <ul className="space-y-1">
              {analysis.decision_rationale.map((rationale, idx) => (
                <li key={idx} className="text-sm text-indigo-700 flex items-start gap-1">
                  <span className="text-indigo-500 mt-0.5">→</span>
                  <span>{rationale}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Uncertainties */}
        {analysis.uncertainties && analysis.uncertainties.length > 0 && (
          <div className="bg-yellow-50 p-4 rounded">
            <h4 className="font-medium mb-3 flex items-center gap-2">
              {/* Warning Icon */}
              <svg className="w-5 h-5 text-yellow-600" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
              </svg>
              Analysis Uncertainties
            </h4>
            <ul className="space-y-1">
              {analysis.uncertainties.map((uncertainty, idx) => (
                <li key={idx} className="text-sm text-yellow-700 flex items-start gap-1">
                  <svg className="w-4 h-4 text-yellow-600 mt-0.5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-8-3a1 1 0 00-.867.5 1 1 0 11-1.731-1A3 3 0 0113 8a3.001 3.001 0 01-2 2.83V11a1 1 0 11-2 0v-1a1 1 0 011-1 1 1 0 100-2zm0 8a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd" />
                  </svg>
                  <span>{uncertainty}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Confidence Score */}
        <div className="text-right text-sm text-gray-500">
          Confidence Score: {(analysis.confidence_score * 100).toFixed(0)}%
          {analysis.processing_time && (
            <span className="ml-4">
              Processing Time: {analysis.processing_time.toFixed(2)}s
            </span>
          )}
        </div>
      </div>
    </div>
  );
};

export default QCAIAnalysis;