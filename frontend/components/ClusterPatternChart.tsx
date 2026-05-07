import React, { useMemo } from 'react';
import { ClusterData, ClusterParams } from '../types';
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

interface ClusterPatternChartProps {
  data: ClusterData;
  clusterId: string;
  params: ClusterParams;
  showIndividualGenes: boolean;
  setShowIndividualGenes: (show: boolean) => void;
  showMean: boolean;
  setShowMean: (show: boolean) => void;
  showMedian: boolean;
  setShowMedian: (show: boolean) => void;
}

export function ClusterPatternChart({
  data,
  clusterId,
  params,
  showIndividualGenes,
  setShowIndividualGenes,
  showMean,
  setShowMean,
  showMedian,
  setShowMedian
}: ClusterPatternChartProps) {
  const MAX_DISPLAY_GENES = 300; // max displayed gene lines
  const displayClusterName = clusterId.startsWith('merged_') ? clusterId.replace('merged_', 'Merged ') : clusterId.replace('subcluster_', 'Cluster ');

  // ?곸쐞 ?좎쟾???좏깮 (泥?300媛?
  const topGenes = useMemo(() => {
    return data.genes.slice(0, MAX_DISPLAY_GENES);
  }, [data.genes]);

  const chartData = useMemo(() => {
    // ?듦퀎 ?곗씠??
    const statsData = data.samples.map((sample, idx) => ({
      sample,
      mean: data.statistics.mean[idx],
      median: data.statistics.median[idx],
      min: data.statistics.min[idx],
      max: data.statistics.max[idx]
    }));

    // 媛쒕퀎 ?좎쟾???곗씠??異붽? (?곸쐞 ?좎쟾?먮쭔)
    topGenes.forEach((gene, geneIdx) => {
      data.samples.forEach((sample, sampleIdx) => {
        const value = gene[sample];
        const numValue = typeof value === 'number' ? value : parseFloat(value as string) || 0;
        statsData[sampleIdx][`gene_${geneIdx}`] = numValue;
      });
    });

    return statsData;
  }, [data, topGenes]);

  // 而ㅼ뒪? ?댄똻 (mean怨?median留??쒖떆)
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
              Expression Pattern - {displayClusterName}
            </h3>
            <p className="text-sm text-gray-600 mt-1">
              {data.gene_count.toLocaleString()} genes 쨌 log2(median-centered FPKM)
              {showIndividualGenes && data.gene_count > MAX_DISPLAY_GENES && (
                <span className="ml-2 text-blue-600">
                  (showing top {MAX_DISPLAY_GENES} genes)
                </span>
              )}
            </p>
            <div className="text-xs text-gray-500 mt-2 space-x-3">
              <span>P-value: {params.pValue}</span>
              <span>Log2 FC: {params.foldChange}</span>
              <span>Ptree: {params.ptree}</span>
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

            {/* 媛쒕퀎 ?좎쟾???⑦꽩 (?뚯깋) */}
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

            {/* Mean ??(援듦쾶) */}
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

            {/* Median ??(援듦쾶) */}
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



