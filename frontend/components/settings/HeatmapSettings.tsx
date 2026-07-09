import React, { useState, useMemo, useRef, useEffect } from 'react';
import { HexColorPicker } from 'react-colorful';
import Plot from 'react-plotly.js';
import { useHeatmapColors } from '../../contexts/UserSettingsContext';

const HeatmapSettings: React.FC = () => {
  const { colors, setColors, saveColors, isLoading, isSaving } = useHeatmapColors();
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  // Local state for editing (synced with context)
  const [highColor, setHighColor] = useState(colors.high);
  const [middleColor, setMiddleColor] = useState(colors.middle);
  const [lowColor, setLowColor] = useState(colors.low);

  // Sync local state with context when colors are loaded
  useEffect(() => {
    setHighColor(colors.high);
    setMiddleColor(colors.middle);
    setLowColor(colors.low);
  }, [colors]);

  // Popover state
  const [openPicker, setOpenPicker] = useState<'high' | 'middle' | 'low' | null>(null);
  const pickerRef = useRef<HTMLDivElement>(null);

  // Close popover when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (pickerRef.current && !pickerRef.current.contains(event.target as Node)) {
        setOpenPicker(null);
      }
    };

    if (openPicker) {
      // Use setTimeout to avoid immediate closing when opening
      const timeoutId = setTimeout(() => {
        document.addEventListener('mousedown', handleClickOutside);
      }, 0);

      return () => {
        clearTimeout(timeoutId);
        document.removeEventListener('mousedown', handleClickOutside);
      };
    }
  }, [openPicker]);

  // Sample heatmap data for preview - 20 genes x 12 samples
  const sampleData = useMemo(() => {
    // Generate downregulation pattern data (high -> low across samples)
    const generateZScores = () => {
      const data: number[][] = [];
      for (let i = 0; i < 20; i++) {
        const row: number[] = [];
        // Each gene has different downregulation intensity
        const baseIntensity = 2.5 - (i * 0.1); // Genes have varying starting points (2.5 to 0.6)
        const downregulationRate = 0.3 + (i * 0.01); // Different rates of decrease (0.3 to 0.49)

        for (let j = 0; j < 12; j++) {
          // Downregulation pattern: starts high, gradually decreases across samples
          const sampleFactor = j / 11; // 0 to 1 progression
          const noise = (Math.random() - 0.5) * 0.3; // Small random variation
          const value = baseIntensity - (downregulationRate * j) + noise;
          row.push(Number(value.toFixed(2)));
        }
        data.push(row);
      }
      return data;
    };

    return {
      z: generateZScores(),
      x: ['S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7', 'S8', 'S9', 'S10', 'S11', 'S12'],
      y: Array.from({ length: 20 }, (_, i) => `Gene${i + 1}`)
    };
  }, []);

  // Generate custom colorscale from selected colors
  const customColorscale = useMemo(() => {
    return [
      [0, lowColor],    // Lowest value
      [0.5, middleColor], // Middle value
      [1, highColor]    // Highest value
    ];
  }, [highColor, middleColor, lowColor]);

  // Plotly config for preview heatmap
  const plotConfig = useMemo(() => {
    return {
      data: [{
        type: 'heatmap',
        z: sampleData.z,
        x: sampleData.x,
        y: sampleData.y,
        colorscale: customColorscale,
        zmid: 0,
        zmin: -2.5,
        zmax: 2.5,
        colorbar: {
          title: 'Z-score',
          titleside: 'right',
          thickness: 15,
          len: 0.7,
          x: 1.02,
          titlefont: { size: 12 },
          tickfont: { size: 10 }
        },
        hovertemplate: 'Gene: %{y}<br>Sample: %{x}<br>Z-score: %{z:.2f}<extra></extra>',
        xgap: 1,
        ygap: 1
      }],
      layout: {
        title: {
          text: 'Color Preview',
          font: { size: 14, family: 'Arial, sans-serif' }
        },
        xaxis: {
          title: 'Samples',
          side: 'bottom',
          tickfont: { size: 9 },
          tickangle: -45
        },
        yaxis: {
          title: 'Genes',
          tickfont: { size: 8 }
        },
        width: 700,
        height: 550,
        margin: { l: 80, r: 100, t: 50, b: 80 },
        paper_bgcolor: 'white',
        plot_bgcolor: 'white'
      },
      config: {
        displaylogo: false,
        responsive: true,
        staticPlot: true // Disable interactions for preview
      }
    };
  }, [sampleData, customColorscale]);

  // Color picker component
  const ColorPickerPopover = ({
    color,
    onChange,
    label
  }: {
    color: string;
    onChange: (color: string) => void;
    label: string;
  }) => {
    const pickerType = label.includes('High') ? 'high' : label.includes('Middle') ? 'middle' : 'low';
    const isOpen = openPicker === pickerType;

    return (
      <div className="space-y-2">
        <label className="block text-sm font-medium text-slate-700">{label}</label>
        <div className="relative">
          <button
            onClick={(e) => {
              e.stopPropagation(); // Prevent event bubbling to document click listener
              setOpenPicker(isOpen ? null : pickerType);
            }}
            className="flex items-center gap-3 w-full px-4 py-2 border border-slate-300 rounded-lg hover:border-blue-500 transition-colors"
          >
            <div
              className="w-8 h-8 rounded border-2 border-slate-300"
              style={{ backgroundColor: color }}
            />
            <span className="text-sm font-mono text-slate-700">{color.toUpperCase()}</span>
            <svg
              className={`ml-auto w-4 h-4 text-slate-400 transition-transform ${isOpen ? 'rotate-180' : ''}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </button>

          {isOpen && (
            <div
              ref={pickerRef}
              className="absolute z-10 mt-2 p-4 bg-white rounded-lg shadow-xl border border-slate-200"
            >
              <HexColorPicker color={color} onChange={onChange} />
              <div className="mt-3 flex items-center gap-2">
                <input
                  type="text"
                  value={color}
                  onChange={(e) => {
                    const value = e.target.value;
                    if (/^#[0-9A-Fa-f]{0,6}$/.test(value)) {
                      onChange(value);
                    }
                  }}
                  className="flex-1 px-2 py-1 text-sm font-mono border border-slate-300 rounded focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  placeholder="#RRGGBB"
                />
                <button
                  onClick={() => setOpenPicker(null)}
                  className="px-3 py-1 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors"
                >
                  Apply
                </button>
              </div>

              {/* Preset colors */}
              <div className="mt-3 pt-3 border-t border-slate-200">
                <p className="text-xs text-slate-500 mb-2">Quick Presets:</p>
                <div className="grid grid-cols-8 gap-1">
                  {['#D32F2F', '#E91E63', '#9C27B0', '#3F51B5', '#2196F3', '#00BCD4', '#4CAF50', '#FF9800'].map((presetColor) => (
                    <button
                      key={presetColor}
                      onClick={() => onChange(presetColor)}
                      className="w-6 h-6 rounded border-2 border-slate-300 hover:border-blue-500 transition-colors"
                      style={{ backgroundColor: presetColor }}
                      title={presetColor}
                    />
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    );
  };

  // Save colors to backend
  const handleSave = async () => {
    setSaveError(null);
    setSaveSuccess(false);

    const newColors = {
      high: highColor,
      middle: middleColor,
      low: lowColor
    };

    try {
      // Save colors to backend with the new values
      await saveColors(newColors);

      // Update context after successful save
      setColors(newColors);

      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch (error) {
      console.error('Failed to save heatmap colors:', error);
      setSaveError('Failed to save settings. Please try again.');
      setTimeout(() => setSaveError(null), 5000);
    }
  };

  // Reset to default colors
  const handleReset = () => {
    setHighColor('#D32F2F');
    setMiddleColor('#FFFFFF');
    setLowColor('#1976D2');
  };

  // Check if colors have changed
  const hasChanges = useMemo(() => {
    return highColor !== colors.high || middleColor !== colors.middle || lowColor !== colors.low;
  }, [highColor, middleColor, lowColor, colors]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h3 className="text-lg font-semibold text-slate-800 mb-2">🎨 Heatmap Color Settings</h3>
        <p className="text-slate-600">
          Customize the color scale for your heatmap visualizations. Changes are previewed in real-time.
        </p>
      </div>

      {/* Success Message */}
      {saveSuccess && (
        <div className="bg-green-50 border border-green-200 text-green-700 p-4 rounded-lg">
          ✓ Colors saved successfully! All heatmaps will now use your custom colors.
        </div>
      )}

      {/* Error Message */}
      {saveError && (
        <div className="bg-red-50 border border-red-200 text-red-700 p-4 rounded-lg">
          {saveError}
        </div>
      )}

      {/* Main Content: 2-Column Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-[400px_1fr] gap-6">
        {/* Left Column: Color Configuration */}
        <div className="bg-slate-50 p-6 rounded-lg border border-slate-200">
          <h4 className="text-md font-semibold text-slate-800 mb-4">Color Scale Configuration</h4>

          <div className="space-y-4">
            <ColorPickerPopover
              color={highColor}
              onChange={setHighColor}
              label="High Value Color"
            />

            <ColorPickerPopover
              color={middleColor}
              onChange={setMiddleColor}
              label="Middle Value Color"
            />

            <ColorPickerPopover
              color={lowColor}
              onChange={setLowColor}
              label="Low Value Color"
            />
          </div>

          {/* Color Legend Reference */}
          <div className="mt-6 p-4 bg-white rounded-lg border border-slate-200">
            <p className="text-sm font-medium text-slate-700 mb-2">Current Color Scale:</p>
            <div className="flex items-center gap-2">
              <div className="flex items-center gap-1 text-xs text-slate-600">
                <span>Low</span>
                <div className="w-4 h-4 rounded border border-slate-300" style={{ backgroundColor: lowColor }} />
              </div>
              <div className="flex-1 h-6 rounded" style={{
                background: `linear-gradient(to right, ${lowColor}, ${middleColor}, ${highColor})`
              }} />
              <div className="flex items-center gap-1 text-xs text-slate-600">
                <div className="w-4 h-4 rounded border border-slate-300" style={{ backgroundColor: highColor }} />
                <span>High</span>
              </div>
            </div>
          </div>

          {/* Action Buttons */}
          <div className="mt-6 pt-4 border-t border-slate-200 flex gap-3">
            <button
              onClick={handleSave}
              disabled={!hasChanges || isSaving}
              className={`flex-1 px-4 py-2 text-sm font-semibold rounded-lg transition-colors ${
                hasChanges && !isSaving
                  ? 'bg-blue-600 text-white hover:bg-blue-700'
                  : 'bg-slate-200 text-slate-400 cursor-not-allowed'
              }`}
            >
              {isSaving ? 'Saving...' : 'Save Colors'}
            </button>
            <button
              onClick={handleReset}
              className="px-4 py-2 text-sm bg-slate-200 text-slate-700 rounded-lg hover:bg-slate-300 transition-colors"
            >
              Reset to Default
            </button>
          </div>
        </div>

        {/* Right Column: Live Preview */}
        <div className="bg-white p-6 rounded-lg border border-slate-200">
          <h4 className="text-md font-semibold text-slate-800 mb-4">Live Preview</h4>
          <p className="text-sm text-slate-600 mb-4">
            Preview of your custom color scale with sample data.
          </p>

          <div className="flex justify-center">
            <Plot {...plotConfig} />
          </div>
        </div>
      </div>

      {/* Info Section */}
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
        <div className="flex gap-2">
          <span className="text-blue-600 text-lg">ℹ️</span>
          <div className="text-sm text-blue-800">
            <p className="font-medium mb-1">How it works:</p>
            <ul className="list-disc list-inside space-y-1">
              <li>Select your preferred colors using the color pickers</li>
              <li>Preview changes in real-time with the sample heatmap</li>
              <li>Click "Save Colors" to apply to all heatmaps</li>
              <li>Saved colors will be used in all future heatmap visualizations</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
};

export default HeatmapSettings;
