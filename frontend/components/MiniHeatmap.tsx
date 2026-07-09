import React, { useMemo } from 'react';
import { interpolateRgb } from 'd3-interpolate';
import { useHeatmapColors } from '../contexts/UserSettingsContext';

interface MiniHeatmapProps {
  values: number[];
  samples: string[];
  logFC?: number; // stroke 색상용 (선택적)
  width?: number;
  height?: number;
}

const MiniHeatmap: React.FC<MiniHeatmapProps> = ({
  values,
  samples,
  logFC,
  width = 192,
  height = 20
}) => {
  const { colors } = useHeatmapColors();
  const padding = 1.5; // stroke가 잘리지 않도록 패딩 추가
  const cellWidth = width / samples.length;
  const zClip = 3; // z-score 클리핑 범위

  // Z-score 정규화
  const { mean, std, zscores } = useMemo(() => {
    const mean = values.reduce((sum, val) => sum + val, 0) / values.length;
    const variance = values.reduce((sum, val) => sum + Math.pow(val - mean, 2), 0) / values.length;
    const std = Math.sqrt(variance) || 1; // 표준편차가 0이면 1로 설정
    const zscores = values.map(val => (val - mean) / std);
    return { mean, std, zscores };
  }, [values]);

  // Custom color interpolator using user settings
  const getColor = useMemo(() => {
    // Create two interpolators: low->middle and middle->high
    const lowToMiddle = interpolateRgb(colors.low, colors.middle);
    const middleToHigh = interpolateRgb(colors.middle, colors.high);

    return (zscore: number) => {
      const zc = Math.max(-zClip, Math.min(zClip, zscore)); // 클리핑
      const t = (zc + zClip) / (2 * zClip);                // [-zClip, zClip] → [0,1]

      // Use different interpolator depending on value
      if (t < 0.5) {
        // Low to middle range
        return lowToMiddle(t * 2); // Map [0, 0.5] to [0, 1]
      } else {
        // Middle to high range
        return middleToHigh((t - 0.5) * 2); // Map [0.5, 1] to [0, 1]
      }
    };
  }, [colors]);

  // logFC 기반 테두리 색상 (up: 빨강, down: 보라)
  const stroke = typeof logFC === 'number'
    ? (logFC > 0 ? 'rgba(200,0,0,0.6)' : logFC < 0 ? 'rgba(90,0,160,0.6)' : 'rgba(0,0,0,0.15)')
    : 'rgba(0,0,0,0.15)';

  return (
    <svg
      width={width}
      height={height}
      viewBox={`${-padding} ${-padding} ${width + padding * 2} ${height + padding * 2}`}
      className="rounded"
    >
      {zscores.map((zscore, i) => (
        <rect
          key={i}
          x={i * cellWidth}
          y={0}
          width={cellWidth}
          height={height}
          fill={getColor(zscore)}
          stroke={stroke}
          strokeWidth={0.5}
        >
          <title>{`${samples[i]}: ${values[i].toFixed(1)} (z-score: ${zscore.toFixed(2)})`}</title>
        </rect>
      ))}
    </svg>
  );
};

export default MiniHeatmap;
