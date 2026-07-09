import React, { useState, useEffect } from 'react';

interface ModuleStatistics {
  pass_count: number;
  warn_count: number;
  fail_count: number;
  total_modules: number;
  module_details: Record<string, { status: string }>;
  failed_modules: string[];
  warned_modules: string[];
}

interface QCStatisticsProps {
  statistics: ModuleStatistics;
  sampleName: string;
}

const QCStatistics: React.FC<QCStatisticsProps> = ({ statistics, sampleName }) => {
  const { pass_count, warn_count, fail_count, total_modules } = statistics;

  // Animation state - start from 0
  const [animatedValues, setAnimatedValues] = useState({
    passPercent: 0,
    warnPercent: 0,
    failPercent: 0
  });

  // Calculate actual percentages
  const actualPassPercent = total_modules > 0 ? (pass_count / total_modules) * 100 : 0;
  const actualWarnPercent = total_modules > 0 ? (warn_count / total_modules) * 100 : 0;
  const actualFailPercent = total_modules > 0 ? (fail_count / total_modules) * 100 : 0;

  // Trigger animation after mount
  useEffect(() => {
    const timer = setTimeout(() => {
      setAnimatedValues({
        passPercent: actualPassPercent,
        warnPercent: actualWarnPercent,
        failPercent: actualFailPercent
      });
    }, 100); // Small delay to ensure CSS transition works

    return () => clearTimeout(timer);
  }, [actualPassPercent, actualWarnPercent, actualFailPercent]);

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-6 mb-4">
      {/* Header */}
      <div className="flex items-center justify-between mb-4 pb-4 border-b border-gray-200">
        <h3 className="text-lg font-semibold text-gray-800">QC Module Statistics</h3>
        <span className="text-sm font-normal text-gray-500">{sampleName}</span>
      </div>

      {/* QC Module Statistics Bar Chart */}
      <div className="space-y-4">
        {/* Pass Module */}
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 w-24">
            <svg className="w-5 h-5 text-green-500" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
            </svg>
            <span className="font-medium text-gray-700 text-sm">Pass</span>
          </div>
          <div className="flex-1">
            <div className="relative w-full bg-gray-200 rounded h-8">
              <div
                className="absolute left-0 top-0 h-8 bg-green-500 rounded flex items-center justify-end pr-2 transition-all duration-1000 ease-out"
                style={{ width: `${animatedValues.passPercent}%`, minWidth: animatedValues.passPercent > 0 ? '50px' : '0' }}
              >
                <span className="text-xs font-bold text-white">
                  {pass_count}/{total_modules}
                </span>
              </div>
            </div>
          </div>
          <span className="w-8 text-right font-bold text-green-600">
            {pass_count}
          </span>
        </div>

        {/* Warning Module */}
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 w-24">
            <svg className="w-5 h-5 text-yellow-500" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
            </svg>
            <span className="font-medium text-gray-700 text-sm">Warning</span>
          </div>
          <div className="flex-1">
            <div className="relative w-full bg-gray-200 rounded h-8">
              <div
                className="absolute left-0 top-0 h-8 bg-yellow-500 rounded flex items-center justify-end pr-2 transition-all duration-1000 ease-out"
                style={{ width: `${animatedValues.warnPercent}%`, minWidth: animatedValues.warnPercent > 0 ? '50px' : '0' }}
              >
                <span className="text-xs font-bold text-white">
                  {warn_count}/{total_modules}
                </span>
              </div>
            </div>
          </div>
          <span className="w-8 text-right font-bold text-yellow-600">
            {warn_count}
          </span>
        </div>

        {/* Fail Module */}
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 w-24">
            <svg className="w-5 h-5 text-red-500" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
            </svg>
            <span className="font-medium text-gray-700 text-sm">Fail</span>
          </div>
          <div className="flex-1">
            <div className="relative w-full bg-gray-200 rounded h-8">
              <div
                className="absolute left-0 top-0 h-8 bg-red-500 rounded flex items-center justify-end pr-2 transition-all duration-1000 ease-out"
                style={{ width: `${animatedValues.failPercent}%`, minWidth: animatedValues.failPercent > 0 ? '50px' : '0' }}
              >
                <span className="text-xs font-bold text-white">
                  {fail_count}/{total_modules}
                </span>
              </div>
            </div>
          </div>
          <span className="w-8 text-right font-bold text-red-600">
            {fail_count}
          </span>
        </div>

        {/* Failed Modules List */}
        {statistics.failed_modules.length > 0 && (
          <div className="mt-4 p-3 bg-red-50 rounded">
            <h4 className="text-sm font-medium text-red-800 mb-2">Failed Modules:</h4>
            <ul className="list-disc list-inside space-y-1">
              {statistics.failed_modules.map((module) => (
                <li key={module} className="text-sm text-red-700">
                  {module}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Warned Modules List */}
        {statistics.warned_modules.length > 0 && (
          <div className="mt-4 p-3 bg-yellow-50 rounded">
            <h4 className="text-sm font-medium text-yellow-800 mb-2">Warning Modules:</h4>
            <ul className="list-disc list-inside space-y-1">
              {statistics.warned_modules.map((module) => (
                <li key={module} className="text-sm text-yellow-700">
                  {module}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* All Pass Message */}
        {pass_count === total_modules && (
          <div className="mt-4 p-3 bg-green-50 rounded">
            <p className="text-sm text-green-700 font-medium">
              ✨ All quality control modules passed!
            </p>
          </div>
        )}
      </div>
    </div>
  );
};

export default QCStatistics;