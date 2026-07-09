import React, { useState, useMemo } from 'react';
import AudioEqualizer from './AudioEqualizer';

interface PatternAnalysisConfig {
    pattern: Record<string, number>;
    constraints: {
        minSpearman: number;
        equalTol: number;
        orderGap: number;
        minLog2FC: number;
        minCPM: number;
    };
    cvFilter?: {
        enabled: boolean;
        maxCV: number;
        minGroups: number;
    };
    equalityPairs?: string[][];
}

interface PatternSelectionPanelProps {
    groups: string[];
    isExpanded: boolean;
    onToggle: () => void;
    onAnalyze: (config: PatternAnalysisConfig) => void;
}

interface SliderControlProps {
    label: string;
    value: number;
    onChange: (value: number) => void;
    min: number;
    max: number;
    step: number;
    helpText?: string;
    unit?: string;
}

const SliderControl: React.FC<SliderControlProps> = ({
    label,
    value,
    onChange,
    min,
    max,
    step,
    helpText,
    unit = ''
}) => {
    return (
        <div className="space-y-2">
            <div className="flex items-center justify-between">
                <label className="text-sm font-medium text-slate-700">
                    {label}
                </label>
                <span className="text-sm font-mono text-slate-900">
                    {value.toFixed(step < 1 ? 1 : 0)}{unit}
                </span>
            </div>
            <input
                type="range"
                min={min}
                max={max}
                step={step}
                value={value}
                onChange={(e) => onChange(parseFloat(e.target.value))}
                className="w-full h-2 bg-slate-200 rounded-lg appearance-none cursor-pointer slider"
            />
            {helpText && (
                <p className="text-xs text-slate-500">{helpText}</p>
            )}
        </div>
    );
};

const PatternSelectionPanel: React.FC<PatternSelectionPanelProps> = ({
    groups,
    isExpanded,
    onToggle,
    onAnalyze
}) => {
    // 🔍 DEBUG: Log sample group order
    console.log('🎚️ [PatternSelectionPanel] Sample groups order:', groups);
    console.log('🎚️ [PatternSelectionPanel] Sample groups count:', groups.length);

    // Preset state
    const [preset, setPreset] = useState<string>('custom');

    // Pattern values state (normalized 0-10 scale for equalizer)
    const [patternValues, setPatternValues] = useState<Record<string, number>>(
        () => groups.reduce((acc, group) => ({ ...acc, [group]: 0 }), {})
    );

    // Disabled groups state
    const [disabledGroups, setDisabledGroups] = useState<Record<string, boolean>>(
        () => groups.reduce((acc, group) => ({ ...acc, [group]: false }), {})
    );

    // Statistical constraints
    const [minSpearman, setMinSpearman] = useState(0.6);
    const [minLog2FC, setMinLog2FC] = useState(1.0);
    const [minCPM, setMinCPM] = useState(0);

    // Tolerance constraints
    const [equalTol, setEqualTol] = useState(0.3);
    const [orderGap, setOrderGap] = useState(0.5);

    // CV Filter
    const [enableCVFilter, setEnableCVFilter] = useState(false);
    const [maxCV, setMaxCV] = useState(0.5);
    const [cvMinGroups, setCvMinGroups] = useState(1);

    // Equality pairs
    const [equalityPairs, setEqualityPairs] = useState<string[][]>([]);
    const [newPairFirst, setNewPairFirst] = useState('');
    const [newPairSecond, setNewPairSecond] = useState('');

    const handlePatternChange = (group: string, value: number) => {
        setPatternValues(prev => ({ ...prev, [group]: value }));
    };

    const handleToggleGroup = (group: string, wasDisabled: boolean) => {
        setDisabledGroups(prev => ({ ...prev, [group]: !wasDisabled }));
        // 값은 변경하지 않고 그 자리에서 ON/OFF만 전환
    };

    const handleAddEqualityPair = () => {
        if (newPairFirst && newPairSecond && newPairFirst !== newPairSecond) {
            setEqualityPairs(prev => [...prev, [newPairFirst, newPairSecond]]);
            setNewPairFirst('');
            setNewPairSecond('');
        }
    };

    const handleRemoveEqualityPair = (index: number) => {
        setEqualityPairs(prev => prev.filter((_, i) => i !== index));
    };

    const handlePresetChange = (newPreset: string) => {
        setPreset(newPreset);

        if (newPreset === 'custom') {
            // Custom은 변경하지 않음
            return;
        }

        // 활성화된 그룹만 가져오기
        const activeGroups = groups.filter(g => !disabledGroups[g]);
        const groupCount = activeGroups.length;

        let newValues: Record<string, number> = {};

        switch (newPreset) {
            case 'weak-up':
                // 약한 Up-regulate: 3 → 6 범위로 증가
                activeGroups.forEach((group, index) => {
                    newValues[group] = 3 + (3 / Math.max(1, groupCount - 1)) * index;
                });
                break;

            case 'strong-up':
                // 강한 Up-regulate: 2 → 9 범위로 증가
                activeGroups.forEach((group, index) => {
                    newValues[group] = 2 + (7 / Math.max(1, groupCount - 1)) * index;
                });
                break;

            case 'weak-down':
                // 약한 Down-regulate: 6 → 3 범위로 감소
                activeGroups.forEach((group, index) => {
                    newValues[group] = 6 - (3 / Math.max(1, groupCount - 1)) * index;
                });
                break;

            case 'strong-down':
                // 강한 Down-regulate: 9 → 2 범위로 감소
                activeGroups.forEach((group, index) => {
                    newValues[group] = 9 - (7 / Math.max(1, groupCount - 1)) * index;
                });
                break;
        }

        // 비활성화된 그룹은 0으로 유지
        groups.forEach(group => {
            if (disabledGroups[group]) {
                newValues[group] = 0;
            }
        });

        setPatternValues(newValues);
    };

    const handleReset = () => {
        setPreset('custom');
        setPatternValues(groups.reduce((acc, group) => ({ ...acc, [group]: 0 }), {}));
        setDisabledGroups(groups.reduce((acc, group) => ({ ...acc, [group]: false }), {}));
        setMinSpearman(0.6);
        setMinLog2FC(1.0);
        setMinCPM(0);
        setEqualTol(0.3);
        setOrderGap(0.5);
        setEnableCVFilter(false);
        setMaxCV(0.5);
        setCvMinGroups(1);
        setEqualityPairs([]);
    };

    const handleAnalyze = () => {
        // Convert equalizer values (0-10) to pattern values for analysis
        const activePattern = Object.entries(patternValues)
            .filter(([group]) => !disabledGroups[group])
            .reduce((acc, [group, value]) => ({
                ...acc,
                [group]: value  // Keep as is, backend will normalize
            }), {});

        const config: PatternAnalysisConfig = {
            pattern: activePattern,
            constraints: {
                minSpearman,
                equalTol,
                orderGap,
                minLog2FC,
                minCPM
            },
            cvFilter: enableCVFilter ? {
                enabled: true,
                maxCV,
                minGroups: cvMinGroups
            } : undefined,
            equalityPairs: equalityPairs.length > 0 ? equalityPairs : undefined
        };

        onAnalyze(config);
    };

    const activeGroupCount = useMemo(() => {
        return Object.values(disabledGroups).filter(disabled => !disabled).length;
    }, [disabledGroups]);

    const isValidPattern = activeGroupCount >= 2;

    return (
        <div className="mb-6 bg-white rounded-lg shadow-sm border border-slate-200">
            {/* Header with Toggle */}
            <button
                onClick={onToggle}
                className="w-full px-6 py-4 flex items-center justify-between hover:bg-slate-50 transition-colors"
            >
                <div className="flex items-center space-x-3">
                    <svg
                        className={`w-5 h-5 transform transition-transform ${isExpanded ? 'rotate-90' : ''}`}
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                    >
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                    </svg>
                    <h3 className="text-lg font-semibold text-slate-900">
                        Pattern-Based Gene Selection
                    </h3>
                </div>
                <div className="text-sm text-slate-500">
                    {activeGroupCount > 0
                        ? `Pattern configured for ${activeGroupCount} groups`
                        : 'Click to configure'}
                </div>
            </button>

            {/* Expandable Content */}
            {isExpanded && (
                <div className="px-6 pb-6 border-t border-slate-200">
                    {/* Audio Equalizer */}
                    <div className="mt-6">
                        <AudioEqualizer
                            groups={groups}
                            values={patternValues}
                            onChange={handlePatternChange}
                            disabled={disabledGroups}
                            onToggleGroup={handleToggleGroup}
                            preset={preset}
                            onPresetChange={handlePresetChange}
                            onReset={handleReset}
                        />
                    </div>

                    {/* Filter Controls */}
                    <div className="mt-8 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                        {/* Statistical Thresholds */}
                        <div className="space-y-4">
                            <h5 className="text-sm font-semibold text-slate-700 uppercase tracking-wider">
                                Statistical Thresholds
                            </h5>
                            <SliderControl
                                label="Min Spearman Correlation"
                                value={minSpearman}
                                onChange={setMinSpearman}
                                min={0}
                                max={1}
                                step={0.1}
                                helpText="Minimum correlation with pattern (higher = stricter)"
                            />
                            <SliderControl
                                label="Min Log2 Fold Change"
                                value={minLog2FC}
                                onChange={setMinLog2FC}
                                min={0}
                                max={5}
                                step={0.1}
                                helpText="Minimum expression range across groups"
                            />
                            <div className="space-y-2">
                                <label className="text-sm font-medium text-slate-700">
                                    Min CPM (Counts Per Million)
                                </label>
                                <input
                                    type="number"
                                    value={minCPM}
                                    onChange={(e) => setMinCPM(parseFloat(e.target.value) || 0)}
                                    min={0}
                                    step={0.5}
                                    className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                                />
                                <p className="text-xs text-slate-500">
                                    Minimum expression level in at least one group
                                </p>
                            </div>
                        </div>

                        {/* Constraint Tolerances */}
                        <div className="space-y-4">
                            <h5 className="text-sm font-semibold text-slate-700 uppercase tracking-wider">
                                Constraint Tolerances
                            </h5>
                            <SliderControl
                                label="Equality Tolerance"
                                value={equalTol}
                                onChange={setEqualTol}
                                min={0}
                                max={1}
                                step={0.1}
                                helpText="Max difference for groups at same level (log2 scale)"
                            />
                            <SliderControl
                                label="Order Gap"
                                value={orderGap}
                                onChange={setOrderGap}
                                min={0}
                                max={2}
                                step={0.1}
                                helpText="Min difference between ordered groups (log2 scale)"
                            />
                        </div>

                        {/* CV Filter */}
                        <div className="space-y-4">
                            <div className="flex items-center justify-between">
                                <h5 className="text-sm font-semibold text-slate-700 uppercase tracking-wider">
                                    CV Filter
                                </h5>
                                <label className="relative inline-flex items-center cursor-pointer">
                                    <input
                                        type="checkbox"
                                        checked={enableCVFilter}
                                        onChange={(e) => setEnableCVFilter(e.target.checked)}
                                        className="sr-only peer"
                                    />
                                    <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-blue-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
                                </label>
                            </div>
                            {enableCVFilter && (
                                <>
                                    <SliderControl
                                        label="Max CV (Coefficient of Variation)"
                                        value={maxCV}
                                        onChange={setMaxCV}
                                        min={0}
                                        max={2}
                                        step={0.1}
                                        helpText="Maximum within-group variation (SD/mean)"
                                    />
                                    <div className="space-y-2">
                                        <label className="text-sm font-medium text-slate-700">
                                            Min Groups Pass CV
                                        </label>
                                        <select
                                            value={cvMinGroups}
                                            onChange={(e) => setCvMinGroups(parseInt(e.target.value))}
                                            className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                                        >
                                            {groups.map((_, i) => (
                                                <option key={i + 1} value={i + 1}>{i + 1}</option>
                                            ))}
                                        </select>
                                        <p className="text-xs text-slate-500">
                                            Number of groups that must pass CV threshold
                                        </p>
                                    </div>
                                </>
                            )}
                        </div>
                    </div>

                    {/* Equality Pairs */}
                    <div className="mt-8">
                        <h5 className="text-sm font-semibold text-slate-700 uppercase tracking-wider mb-4">
                            Equality Constraints (Optional)
                        </h5>
                        <div className="bg-slate-50 rounded-lg p-4">
                            <p className="text-sm text-slate-600 mb-4">
                                Define pairs of groups that should have similar expression levels
                            </p>

                            {/* Add New Pair */}
                            <div className="flex items-center space-x-2 mb-4">
                                <select
                                    value={newPairFirst}
                                    onChange={(e) => setNewPairFirst(e.target.value)}
                                    className="flex-1 px-3 py-2 border border-slate-300 rounded-lg"
                                >
                                    <option value="">Select first group</option>
                                    {groups.filter(g => !disabledGroups[g]).map(group => (
                                        <option key={group} value={group}>{group}</option>
                                    ))}
                                </select>
                                <span className="text-slate-500">=</span>
                                <select
                                    value={newPairSecond}
                                    onChange={(e) => setNewPairSecond(e.target.value)}
                                    className="flex-1 px-3 py-2 border border-slate-300 rounded-lg"
                                >
                                    <option value="">Select second group</option>
                                    {groups.filter(g => !disabledGroups[g] && g !== newPairFirst).map(group => (
                                        <option key={group} value={group}>{group}</option>
                                    ))}
                                </select>
                                <button
                                    onClick={handleAddEqualityPair}
                                    disabled={!newPairFirst || !newPairSecond}
                                    className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
                                >
                                    Add
                                </button>
                            </div>

                            {/* Existing Pairs */}
                            {equalityPairs.length > 0 && (
                                <div className="space-y-2">
                                    {equalityPairs.map((pair, index) => (
                                        <div key={index} className="flex items-center justify-between bg-white rounded px-3 py-2">
                                            <span className="text-sm">
                                                <span className="font-medium">{pair[0]}</span>
                                                <span className="mx-2 text-slate-500">≈</span>
                                                <span className="font-medium">{pair[1]}</span>
                                            </span>
                                            <button
                                                onClick={() => handleRemoveEqualityPair(index)}
                                                className="text-red-500 hover:text-red-700"
                                            >
                                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                                                </svg>
                                            </button>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    </div>

                    {/* Action Buttons */}
                    <div className="mt-8 flex items-center justify-between">
                        <div className="text-sm text-slate-500">
                            {isValidPattern
                                ? `Pattern will analyze ${activeGroupCount} active groups`
                                : 'Select at least 2 groups to analyze'}
                        </div>
                        <div className="flex space-x-3">
                            <button
                                onClick={handleReset}
                                className="px-4 py-2 border border-slate-300 text-slate-700 rounded-lg hover:bg-slate-50 transition-colors"
                            >
                                Reset All
                            </button>
                            <button
                                onClick={handleAnalyze}
                                disabled={!isValidPattern}
                                className="px-6 py-2 bg-gradient-to-r from-purple-600 to-blue-600 text-white rounded-lg hover:from-purple-700 hover:to-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-lg"
                            >
                                Analyze Pattern
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default PatternSelectionPanel;