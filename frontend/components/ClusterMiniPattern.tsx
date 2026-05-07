import React, { useMemo } from 'react';

interface ClusterMiniPatternProps {
  mean: number[];
  median?: number[];
  width?: number;
  height?: number;
  className?: string;
}

export function ClusterMiniPattern({
  mean,
  median = [],
  width = 120,
  height = 44,
  className = ''
}: ClusterMiniPatternProps) {
  const pathData = useMemo(() => {
    const values = [...mean, ...median].filter((v) => Number.isFinite(v));
    if (mean.length < 2 || values.length === 0) return null;

    const minVal = Math.min(...values);
    const maxVal = Math.max(...values);
    const range = Math.max(1e-9, maxVal - minVal);

    const padX = 4;
    const padY = 4;
    const plotW = width - padX * 2;
    const plotH = height - padY * 2;

    const toPoint = (arr: number[], index: number) => {
      const x = padX + ((arr.length === 1 ? 0 : index / (arr.length - 1)) * plotW);
      const y = padY + (((maxVal - arr[index]) / range) * plotH);
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    };

    const meanPoints = mean.map((_, i) => toPoint(mean, i)).join(' ');
    const medianPoints = median.length > 1 ? median.map((_, i) => toPoint(median, i)).join(' ') : '';

    return { meanPoints, medianPoints };
  }, [mean, median, width, height]);

  if (!pathData) {
    return (
      <div className={`rounded border border-slate-200 bg-slate-50 ${className}`} style={{ width, height }} />
    );
  }

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className={className}
      aria-label="Cluster pattern preview"
    >
      <rect x="0" y="0" width={width} height={height} fill="white" stroke="#e2e8f0" rx="4" />
      {pathData.medianPoints && (
        <polyline
          points={pathData.medianPoints}
          fill="none"
          stroke="#16a34a"
          strokeWidth="1.3"
          strokeDasharray="3 2"
          strokeLinecap="round"
          strokeLinejoin="round"
          opacity="0.9"
        />
      )}
      <polyline
        points={pathData.meanPoints}
        fill="none"
        stroke="#2563eb"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

