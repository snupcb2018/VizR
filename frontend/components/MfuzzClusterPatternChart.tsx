import React, { useMemo, useState } from 'react';
import { MfuzzClusterData, MfuzzParams } from '../types';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer
} from 'recharts';

interface MfuzzClusterPatternChartProps {
  data: MfuzzClusterData;
  clusterId: number;
  params: MfuzzParams;
  showIndividualGenes: boolean;
  setShowIndividualGenes: (show: boolean) => void;
  showMean: boolean;
  setShowMean: (show: boolean) => void;
  showMedian: boolean;
  setShowMedian: (show: boolean) => void;
}

export function MfuzzClusterPatternChart({
  data,
  clusterId,
  params,
  showIndividualGenes,
  setShowIndividualGenes,
  showMean,
  setShowMean,
  showMedian,
  setShowMedian
}: MfuzzClusterPatternChartProps) {
  const MAX_DISPLAY_GENES = 300; // 최대 표시할 유전자 수

  // membership 기준 상위 유전자 선택
  const topGenes = useMemo(() => {
    return [...data.genes]
      .sort((a, b) => b.membership - a.membership)
      .slice(0, MAX_DISPLAY_GENES);
  }, [data.genes]);

  const chartData = useMemo(() => {
    // 평균 및 중앙값 계산 (전체 유전자 기준)
    const statsData = data.samples.map((sample, idx) => {
      const values = data.genes.map(gene => {
        const value = gene[sample];
        return typeof value === 'number' ? value : parseFloat(value as string) || 0;
      });
      const mean = values.reduce((sum, val) => sum + val, 0) / values.length;

      // Median 계산
      const sortedValues = [...values].sort((a, b) => a - b);
      const mid = Math.floor(sortedValues.length / 2);
      const median = sortedValues.length % 2 === 0
        ? (sortedValues[mid - 1] + sortedValues[mid]) / 2
        : sortedValues[mid];

      return {
        sample,
        mean,
        median
      };
    });

    // 개별 유전자 데이터 추가 (상위 유전자만)
    topGenes.forEach((gene, geneIdx) => {
      data.samples.forEach((sample, sampleIdx) => {
        const value = gene[sample];
        const numValue = typeof value === 'number' ? value : parseFloat(value as string) || 0;
        statsData[sampleIdx][`gene_${geneIdx}`] = numValue;
      });
    });

    return statsData;
  }, [data, topGenes]);

  // 커스텀 툴팁 (mean과 median 표시)
  const CustomTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
      const data = payload[0].payload;
      return (
        <div
          style={{
            backgroundColor: 'rgba(255, 255, 255, 0.95)',
            border: '1px solid #ccc',
            borderRadius: '4px',
            padding: '8px'
          }}
        >
          <p style={{ margin: 0, fontSize: '12px', fontWeight: 'bold' }}>{data.sample}</p>
          <p style={{ margin: '4px 0 0 0', fontSize: '12px', color: '#2563eb' }}>
            Mean: {data.mean?.toFixed(2)}
          </p>
          <p style={{ margin: '2px 0 0 0', fontSize: '12px', color: '#16a34a' }}>
            Median: {data.median?.toFixed(2)}
          </p>
        </div>
      );
    }
    return null;
  };

  return (
    <div className="bg-white rounded-lg border border-gray-200 shadow-sm">
      <div className="p-4 border-b border-gray-200">
        <div className="flex justify-between items-start">
          <div>
            <h3 className="text-lg font-semibold text-gray-800">
              Expression Pattern - Cluster {clusterId}
            </h3>
            <p className="text-sm text-gray-600 mt-1">
              {data.gene_count.toLocaleString()} genes · Fuzzy c-means clustering
              {showIndividualGenes && data.gene_count > MAX_DISPLAY_GENES && (
                <span className="ml-2 text-blue-600">
                  (showing top {MAX_DISPLAY_GENES} by membership)
                </span>
              )}
            </p>
            <div className="text-xs text-gray-500 mt-2 space-x-3">
              <span>Source: {params.sourceType}</span>
              {params.sourceType === 'deg' && (
                <>
                  <span>P-value: {params.pValue}</span>
                  <span>Log2 FC: {params.foldChange}</span>
                </>
              )}
              {params.sourceType === 'variance' && (
                <span>Top genes: {params.topNGenes}</span>
              )}
              <span>Clusters: {params.clusterCount}</span>
              <span>Min membership: {params.minMembership}</span>
            </div>
          </div>

          {/* Toggle Switches */}
          <div className="flex items-center gap-4">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={showIndividualGenes}
                onChange={(e) => setShowIndividualGenes(e.target.checked)}
                className="sr-only peer"
              />
              <div className="relative w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-blue-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-gray-600"></div>
              <span className="text-sm text-gray-700">Genes</span>
            </label>

            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={showMean}
                onChange={(e) => setShowMean(e.target.checked)}
                className="sr-only peer"
              />
              <div className="relative w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-blue-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
              <span className="text-sm text-gray-700">Mean</span>
            </label>

            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={showMedian}
                onChange={(e) => setShowMedian(e.target.checked)}
                className="sr-only peer"
              />
              <div className="relative w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-green-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-green-600"></div>
              <span className="text-sm text-gray-700">Median</span>
            </label>
          </div>
        </div>
      </div>
      <div className="p-4">
        <ResponsiveContainer width="100%" height={500}>
          <LineChart
            data={chartData}
            margin={{ top: 5, right: 30, left: 20, bottom: 5 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
            <XAxis
              dataKey="sample"
              tick={{ fontSize: 12 }}
              angle={-45}
              textAnchor="end"
              height={80}
            />
            <YAxis
              label={{
                value: 'log2(Expression)',
                angle: -90,
                position: 'insideLeft',
                style: { fontSize: 12 }
              }}
              tick={{ fontSize: 12 }}
            />
            <Tooltip content={<CustomTooltip />} />
            <Legend wrapperStyle={{ paddingTop: '10px' }} iconType="line" />

            {/* 개별 유전자 패턴 (회색) - 상위 유전자만 */}
            {showIndividualGenes && topGenes.map((_, geneIdx) => (
              <Line
                key={`gene_${geneIdx}`}
                type="monotone"
                dataKey={`gene_${geneIdx}`}
                stroke="rgba(120, 120, 120, 0.35)"
                strokeWidth={0.8}
                dot={false}
                legendType="none"
                isAnimationActive={false}
              />
            ))}

            {/* Mean 선 (파란색) */}
            {showMean && (
              <Line
                type="monotone"
                dataKey="mean"
                stroke="#2563eb"
                strokeWidth={3}
                name="Mean"
                dot={{ fill: '#2563eb', r: 3 }}
                activeDot={{ r: 5 }}
              />
            )}

            {/* Median 선 (초록색, 점선) */}
            {showMedian && (
              <Line
                type="monotone"
                dataKey="median"
                stroke="#16a34a"
                strokeWidth={3}
                strokeDasharray="5 5"
                name="Median"
                dot={{ fill: '#16a34a', r: 3 }}
                activeDot={{ r: 5 }}
              />
            )}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
