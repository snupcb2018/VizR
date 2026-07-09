import React, { useState, useRef, useEffect } from 'react';

interface AudioEqualizerProps {
    groups: string[];
    values: Record<string, number>;
    onChange: (group: string, value: number) => void;
    disabled?: Record<string, boolean>;
    onToggleGroup?: (group: string, enabled: boolean) => void;
    minValue?: number;
    maxValue?: number;
    step?: number;
    preset?: string;
    onPresetChange?: (preset: string) => void;
    onReset?: () => void;
}

const AudioEqualizer: React.FC<AudioEqualizerProps> = ({
    groups,
    values,
    onChange,
    disabled = {},
    onToggleGroup,
    minValue = 0,
    maxValue = 10,
    step = 0.1,
    preset = 'custom',
    onPresetChange,
    onReset
}) => {
    const [isDragging, setIsDragging] = useState<string | null>(null);
    const containerRef = useRef<HTMLDivElement>(null);

    // Scale marks (0-10)
    const scaleMarks = ['10', '8', '6', '4', '2', '0'];

    const handleMouseDown = (group: string) => {
        if (!disabled[group]) {
            setIsDragging(group);
        }
    };

    const handleMouseMove = (e: MouseEvent) => {
        if (isDragging && containerRef.current) {
            const rect = containerRef.current.getBoundingClientRect();
            const y = e.clientY - rect.top;
            const height = rect.height;
            const rawValue = Math.max(minValue, Math.min(maxValue,
                maxValue - (y / height) * maxValue
            ));
            // 소수 첫째 자리로 반올림
            const value = Math.round(rawValue * 10) / 10;
            onChange(isDragging, value);
            // 사용자가 노브를 직접 조작하면 Custom으로 변경
            if (preset !== 'custom' && onPresetChange) {
                onPresetChange('custom');
            }
        }
    };

    const handleValueChange = (group: string, value: number) => {
        onChange(group, value);
        // 사용자가 값을 직접 변경하면 Custom으로 변경
        if (preset !== 'custom' && onPresetChange) {
            onPresetChange('custom');
        }
    };

    const handlePresetSelect = (e: React.ChangeEvent<HTMLSelectElement>) => {
        const newPreset = e.target.value;
        if (onPresetChange) {
            onPresetChange(newPreset);
        }
    };

    const handleMouseUp = () => {
        setIsDragging(null);
    };

    useEffect(() => {
        if (isDragging) {
            document.addEventListener('mousemove', handleMouseMove);
            document.addEventListener('mouseup', handleMouseUp);
            return () => {
                document.removeEventListener('mousemove', handleMouseMove);
                document.removeEventListener('mouseup', handleMouseUp);
            };
        }
    }, [isDragging]);

    return (
        <div className="bg-gradient-to-b from-slate-50 to-white rounded-lg p-6 shadow-xl border border-slate-200">
            {/* Header */}
            <div className="flex items-center justify-between mb-6">
                <h4 className="text-slate-900 font-semibold text-lg">Pattern Equalizer</h4>
                <div className="flex items-center space-x-2">
                    <span className="text-xs text-slate-600">PRESET:</span>
                    <select
                        value={preset}
                        onChange={handlePresetSelect}
                        className="bg-white text-slate-900 text-xs px-2 py-1 rounded border border-slate-300 focus:border-blue-400 focus:outline-none"
                    >
                        <option value="custom">Custom</option>
                        <option value="weak-up">Weak Up-regulate</option>
                        <option value="strong-up">Strong Up-regulate</option>
                        <option value="weak-down">Weak Down-regulate</option>
                        <option value="strong-down">Strong Down-regulate</option>
                    </select>
                </div>
            </div>

            {/* Main Equalizer */}
            <div className="relative">
                {/* Grid and Sliders Container */}
                <div className="relative" ref={containerRef}>
                    {/* Grid Background */}
                    <div className="absolute inset-0 pointer-events-none">
                        {/* Horizontal grid lines */}
                        {scaleMarks.map((mark, i) => (
                            <div
                                key={mark}
                                className="absolute w-full border-t border-slate-200"
                                style={{ top: `${(i / (scaleMarks.length - 1)) * 100}%` }}
                            />
                        ))}
                    </div>

                    {/* Scale Labels */}
                    <div className="absolute -left-12 top-0 h-full text-xs text-slate-600">
                        {scaleMarks.map((mark, i) => (
                            <span
                                key={mark}
                                className="absolute text-right w-10"
                                style={{
                                    top: `${(i / (scaleMarks.length - 1)) * 100}%`,
                                    transform: 'translateY(-50%)'
                                }}
                            >
                                {mark}
                            </span>
                        ))}
                    </div>

                    {/* Sliders Container */}
                    <div className="flex items-stretch justify-around h-80 px-4">
                        {groups.map((group, index) => {
                            const value = values[group] ?? 0;
                            const isDisabled = disabled[group];
                            const sliderHeight = (value / maxValue) * 100;

                            return (
                                <div key={group} className="flex-1 max-w-16 mx-1">
                                    {/* Slider Track and Knob */}
                                    <div className="relative h-full w-full flex justify-center">
                                        {/* Vertical Track */}
                                        <div className="absolute inset-x-1/2 transform -translate-x-1/2 w-1 h-full bg-slate-300 rounded-full">
                                            {/* Track Fill */}
                                            {value > 0 && (
                                                <div
                                                    className={`absolute bottom-0 w-full rounded-full transition-all duration-75 ${
                                                        isDisabled
                                                            ? 'bg-gradient-to-t from-slate-400 to-slate-300'
                                                            : 'bg-gradient-to-t from-green-500 to-green-400'
                                                    }`}
                                                    style={{
                                                        height: `${sliderHeight}%`
                                                    }}
                                                />
                                            )}
                                        </div>

                                        {/* Slider Knob */}
                                        <div
                                            className={`absolute w-10 h-10 transform -translate-x-1/2 ${
                                                isDisabled ? 'cursor-not-allowed' : 'cursor-ns-resize'
                                            } ${
                                                isDragging === group ? 'scale-110' : ''
                                            }`}
                                            style={{
                                                bottom: `${sliderHeight}%`,
                                                transform: 'translateY(50%) translateX(-50%)',
                                                left: '50%'
                                            }}
                                            onMouseDown={() => !isDisabled && handleMouseDown(group)}
                                        >
                                            {/* Knob Design */}
                                            <div className="relative w-full h-full">
                                                {/* Outer Ring */}
                                                <div className={`absolute inset-0 rounded-full shadow-lg ${
                                                    isDisabled
                                                        ? 'bg-gradient-to-b from-slate-300 to-slate-400'
                                                        : 'bg-gradient-to-b from-green-300 to-green-400'
                                                }`} />
                                                {/* Inner Circle */}
                                                <div className={`absolute inset-1 rounded-full ${
                                                    isDisabled
                                                        ? 'bg-gradient-to-b from-slate-400 to-slate-500'
                                                        : 'bg-gradient-to-b from-green-500 to-green-600'
                                                }`} />
                                                {/* Center Dot */}
                                                <div className={`absolute inset-2 rounded-full ${
                                                    isDisabled
                                                        ? 'bg-gradient-to-b from-slate-300 to-slate-400'
                                                        : 'bg-gradient-to-b from-green-400 to-green-500'
                                                }`} />
                                                {/* Highlight */}
                                                <div className="absolute top-1 left-1/2 transform -translate-x-1/2 w-2 h-2 rounded-full bg-white opacity-50" />
                                            </div>

                                            {/* Value Display */}
                                            <div className="absolute -top-8 left-1/2 transform -translate-x-1/2 whitespace-nowrap">
                                                <span className={`px-2 py-0.5 bg-slate-900 bg-opacity-90 text-xs rounded font-mono ${
                                                    isDisabled ? 'text-slate-400' : 'text-blue-400'
                                                }`}>
                                                    {value.toFixed(1)}
                                                </span>
                                            </div>
                                        </div>

                                        {/* Hidden HTML Range Input for Accessibility */}
                                        {!isDisabled && (
                                            <input
                                                type="range"
                                                min={minValue}
                                                max={maxValue}
                                                step={step}
                                                value={value}
                                                onChange={(e) => handleValueChange(group, parseFloat(e.target.value))}
                                                className="absolute inset-0 opacity-0 cursor-ns-resize"
                                                style={{
                                                    writingMode: 'bt-lr',
                                                    WebkitAppearance: 'slider-vertical',
                                                    width: '100%',
                                                    height: '100%'
                                                }}
                                            />
                                        )}
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                </div>

                {/* Group Labels and Controls - Outside Grid Area */}
                <div className="flex justify-around px-4 mt-4">
                    {groups.map((group) => {
                        const isDisabled = disabled[group];
                        return (
                            <div key={group} className="flex-1 max-w-16 mx-1 text-center">
                                <div className="text-sm font-medium text-slate-900 mb-3">{group}</div>
                                {/* Enable/Disable Toggle */}
                                {onToggleGroup && (
                                    <button
                                        onClick={() => onToggleGroup(group, isDisabled)}
                                        className={`px-2 py-1 text-xs rounded transition-colors ${
                                            isDisabled
                                                ? 'bg-slate-200 text-slate-600 hover:bg-slate-300'
                                                : 'bg-green-600 text-white hover:bg-green-700'
                                        }`}
                                    >
                                        {isDisabled ? 'OFF' : 'ON'}
                                    </button>
                                )}
                            </div>
                        );
                    })}
                </div>

                {/* Bottom Controls */}
                <div className="mt-6">
                    <button
                        onClick={onReset}
                        className="px-3 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs rounded transition-colors"
                    >
                        Reset
                    </button>
                </div>
            </div>
        </div>
    );
};

export default AudioEqualizer;