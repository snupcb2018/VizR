import React from 'react';
import {
    LineChart, Line, AreaChart, Area, BarChart, Bar,
    XAxis, YAxis, CartesianGrid, Tooltip, Legend,
    ResponsiveContainer, TooltipProps
} from 'recharts';
import {
    PerBaseQualityData,
    PerBaseContentData,
    GenericCountData,
    GenericDistributionData,
    ChartContainerProps
} from './types';

// Chart Container Wrapper
export const ChartContainer: React.FC<ChartContainerProps> = ({ title, status, children }) => {
    const getStatusColor = () => {
        switch (status) {
            case 'pass': return 'border-green-200 bg-green-50';
            case 'warn': return 'border-yellow-200 bg-yellow-50';
            case 'fail': return 'border-red-200 bg-red-50';
            default: return 'border-gray-200 bg-white';
        }
    };

    const getStatusBadge = () => {
        switch (status) {
            case 'pass': return 'bg-green-500';
            case 'warn': return 'bg-yellow-500';
            case 'fail': return 'bg-red-500';
            default: return 'bg-gray-500';
        }
    };

    return (
        <div className={`rounded-lg border p-4 ${getStatusColor()}`}>
            <div className="flex items-center justify-between mb-4">
                <h3 className="text-sm font-semibold text-gray-700">{title}</h3>
                {status && (
                    <span className={`w-2 h-2 rounded-full ${getStatusBadge()}`} />
                )}
            </div>
            <div className="h-64">
                {children}
            </div>
        </div>
    );
};

// Custom Tooltip Component
const CustomTooltip: React.FC<TooltipProps<number, string>> = ({ active, payload, label }) => {
    if (active && payload && payload.length) {
        return (
            <div className="bg-white p-2 border border-gray-200 rounded shadow-sm">
                <p className="text-xs font-semibold text-gray-700">{label}</p>
                {payload.map((entry, index) => (
                    <p key={index} className="text-xs" style={{ color: entry.color }}>
                        {entry.name}: {typeof entry.value === 'number' ? entry.value.toFixed(2) : entry.value}
                    </p>
                ))}
            </div>
        );
    }
    return null;
};

// 1. Per Base Quality Chart
export const PerBaseQualityChart: React.FC<{ data: PerBaseQualityData[] }> = ({ data }) => {
    return (
        <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} margin={{ top: 5, right: 5, left: 5, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
                <XAxis
                    dataKey="position"
                    tick={{ fontSize: 10 }}
                    interval="preserveStartEnd"
                />
                <YAxis
                    domain={[0, 42]}
                    tick={{ fontSize: 10 }}
                />
                <Tooltip content={<CustomTooltip />} />
                <Area
                    type="monotone"
                    dataKey="p10"
                    stroke="none"
                    fill="#fee2e2"
                    fillOpacity={1}
                />
                <Area
                    type="monotone"
                    dataKey="q25"
                    stroke="none"
                    fill="#fed7aa"
                    fillOpacity={1}
                />
                <Area
                    type="monotone"
                    dataKey="median"
                    stroke="none"
                    fill="#fef3c7"
                    fillOpacity={1}
                />
                <Area
                    type="monotone"
                    dataKey="q75"
                    stroke="none"
                    fill="#d9f99d"
                    fillOpacity={1}
                />
                <Area
                    type="monotone"
                    dataKey="p90"
                    stroke="none"
                    fill="#bbf7d0"
                    fillOpacity={1}
                />
                <Line
                    type="monotone"
                    dataKey="mean"
                    stroke="#2563eb"
                    strokeWidth={2}
                    dot={false}
                />
            </AreaChart>
        </ResponsiveContainer>
    );
};

// 2. Per Sequence Quality Chart
export const PerSequenceQualityChart: React.FC<{ data: GenericCountData[] }> = ({ data }) => {
    return (
        <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 5, right: 5, left: 5, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
                <XAxis
                    dataKey="value"
                    tick={{ fontSize: 10 }}
                    label={{ value: 'Quality Score', position: 'insideBottom', offset: -5, fontSize: 10 }}
                />
                <YAxis
                    tick={{ fontSize: 10 }}
                    label={{ value: 'Count', angle: -90, position: 'insideLeft', fontSize: 10 }}
                />
                <Tooltip content={<CustomTooltip />} />
                <Line
                    type="monotone"
                    dataKey="count"
                    stroke="#10b981"
                    strokeWidth={2}
                    dot={false}
                />
            </LineChart>
        </ResponsiveContainer>
    );
};

// 3. Per Base Sequence Content Chart
export const PerBaseSequenceContentChart: React.FC<{ data: PerBaseContentData[] }> = ({ data }) => {
    return (
        <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} margin={{ top: 5, right: 5, left: 5, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
                <XAxis
                    dataKey="position"
                    tick={{ fontSize: 10 }}
                    interval="preserveStartEnd"
                />
                <YAxis
                    tick={{ fontSize: 10 }}
                    label={{ value: 'Percentage', angle: -90, position: 'insideLeft', fontSize: 10 }}
                />
                <Tooltip content={<CustomTooltip />} />
                <Area type="monotone" dataKey="A" stackId="1" stroke="#ef4444" fill="#ef4444" />
                <Area type="monotone" dataKey="T" stackId="1" stroke="#3b82f6" fill="#3b82f6" />
                <Area type="monotone" dataKey="G" stackId="1" stroke="#10b981" fill="#10b981" />
                <Area type="monotone" dataKey="C" stackId="1" stroke="#f59e0b" fill="#f59e0b" />
                <Legend
                    wrapperStyle={{ fontSize: '10px' }}
                    iconSize={10}
                />
            </AreaChart>
        </ResponsiveContainer>
    );
};

// 4. Per Sequence GC Content Chart
export const PerSequenceGcContentChart: React.FC<{ data: GenericCountData[] }> = ({ data }) => {
    return (
        <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 5, right: 5, left: 5, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
                <XAxis
                    dataKey="value"
                    tick={{ fontSize: 10 }}
                    label={{ value: 'GC Content (%)', position: 'insideBottom', offset: -5, fontSize: 10 }}
                />
                <YAxis
                    tick={{ fontSize: 10 }}
                    label={{ value: 'Count', angle: -90, position: 'insideLeft', fontSize: 10 }}
                />
                <Tooltip content={<CustomTooltip />} />
                <Line
                    type="monotone"
                    dataKey="count"
                    stroke="#8b5cf6"
                    strokeWidth={2}
                    dot={false}
                />
            </LineChart>
        </ResponsiveContainer>
    );
};

// 5. Per Base N Content Chart
export const PerBaseNContentChart: React.FC<{ data: GenericDistributionData[] }> = ({ data }) => {
    return (
        <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 5, right: 5, left: 5, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
                <XAxis
                    dataKey="name"
                    tick={{ fontSize: 10 }}
                    interval="preserveStartEnd"
                />
                <YAxis
                    tick={{ fontSize: 10 }}
                    label={{ value: 'N Content (%)', angle: -90, position: 'insideLeft', fontSize: 10 }}
                />
                <Tooltip content={<CustomTooltip />} />
                <Line
                    type="monotone"
                    dataKey="value"
                    stroke="#dc2626"
                    strokeWidth={2}
                    dot={false}
                />
            </LineChart>
        </ResponsiveContainer>
    );
};

// 6. Sequence Length Distribution Chart
export const SequenceLengthDistributionChart: React.FC<{ data: GenericCountData[] }> = ({ data }) => {
    return (
        <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} margin={{ top: 5, right: 5, left: 5, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
                <XAxis
                    dataKey="value"
                    tick={{ fontSize: 10 }}
                    label={{ value: 'Sequence Length', position: 'insideBottom', offset: -5, fontSize: 10 }}
                />
                <YAxis
                    tick={{ fontSize: 10 }}
                    label={{ value: 'Count', angle: -90, position: 'insideLeft', fontSize: 10 }}
                />
                <Tooltip content={<CustomTooltip />} />
                <Bar dataKey="count" fill="#3b82f6" />
            </BarChart>
        </ResponsiveContainer>
    );
};

// 7. Adapter Content Chart
export const AdapterContentChart: React.FC<{ data: GenericDistributionData[] }> = ({ data }) => {
    return (
        <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 5, right: 5, left: 5, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
                <XAxis
                    dataKey="name"
                    tick={{ fontSize: 10 }}
                    interval="preserveStartEnd"
                />
                <YAxis
                    tick={{ fontSize: 10 }}
                    label={{ value: 'Adapter Content (%)', angle: -90, position: 'insideLeft', fontSize: 10 }}
                />
                <Tooltip content={<CustomTooltip />} />
                <Line
                    type="monotone"
                    dataKey="value"
                    stroke="#f59e0b"
                    strokeWidth={2}
                    dot={false}
                />
            </LineChart>
        </ResponsiveContainer>
    );
};

// 8. Duplication Levels Chart
export const DuplicationLevelsChart: React.FC<{ data: GenericDistributionData[] }> = ({ data }) => {
    return (
        <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} margin={{ top: 5, right: 5, left: 5, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
                <XAxis
                    dataKey="name"
                    tick={{ fontSize: 10 }}
                    angle={-45}
                    textAnchor="end"
                    height={60}
                />
                <YAxis
                    tick={{ fontSize: 10 }}
                    label={{ value: 'Percentage (%)', angle: -90, position: 'insideLeft', fontSize: 10 }}
                />
                <Tooltip content={<CustomTooltip />} />
                <Bar dataKey="value" fill="#10b981" />
            </BarChart>
        </ResponsiveContainer>
    );
};