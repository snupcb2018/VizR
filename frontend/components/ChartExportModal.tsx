import React, { useEffect, useMemo, useState } from 'react';

export type ChartExportFormat = 'png' | 'svg';
export type ChartExportSizePreset = 'current' | 'single_column' | 'double_column' | 'presentation' | 'custom';
export type ChartExportBackground = 'white' | 'transparent';

export interface ChartExportOptions {
    format: ChartExportFormat;
    dpi: number;
    background: ChartExportBackground;
    widthPx: number;
    heightPx: number;
    filename: string;
}

interface ChartExportModalProps {
    isOpen: boolean;
    onClose: () => void;
    onExport: (options: ChartExportOptions) => Promise<void> | void;
    isExporting?: boolean;
    defaultFilename: string;
    currentWidth: number;
    currentHeight: number;
}

const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));

const sanitizeFilename = (filename: string) => {
    const trimmed = filename.trim();
    const safe = trimmed.replace(/[<>:"/\\|?*\u0000-\u001F]/g, '_');
    return safe || 'figure_export';
};

const ChartExportModal: React.FC<ChartExportModalProps> = ({
    isOpen,
    onClose,
    onExport,
    isExporting = false,
    defaultFilename,
    currentWidth,
    currentHeight
}) => {
    const [format, setFormat] = useState<ChartExportFormat>('svg');
    const [sizePreset, setSizePreset] = useState<ChartExportSizePreset>('current');
    const [dpi, setDpi] = useState<number>(300);
    const [background, setBackground] = useState<ChartExportBackground>('white');
    const [filename, setFilename] = useState<string>(defaultFilename);
    const [customWidth, setCustomWidth] = useState<number>(currentWidth);
    const [customHeight, setCustomHeight] = useState<number>(currentHeight);

    useEffect(() => {
        if (!isOpen) return;
        setFormat('svg');
        setSizePreset('current');
        setDpi(300);
        setBackground('white');
        setFilename(defaultFilename);
        setCustomWidth(currentWidth);
        setCustomHeight(currentHeight);
    }, [isOpen, defaultFilename, currentWidth, currentHeight]);

    const dimensions = useMemo(() => {
        const ratio = currentHeight > 0 ? currentWidth / currentHeight : 1.6;
        const makeHeight = (width: number) => Math.max(200, Math.round(width / Math.max(0.1, ratio)));

        if (sizePreset === 'single_column') {
            const width = 1200;
            return { widthPx: width, heightPx: makeHeight(width) };
        }

        if (sizePreset === 'double_column') {
            const width = 2200;
            return { widthPx: width, heightPx: makeHeight(width) };
        }

        if (sizePreset === 'presentation') {
            return { widthPx: 1920, heightPx: 1080 };
        }

        if (sizePreset === 'custom') {
            return {
                widthPx: clamp(Math.round(customWidth || currentWidth), 200, 6000),
                heightPx: clamp(Math.round(customHeight || currentHeight), 200, 6000)
            };
        }

        return {
            widthPx: clamp(Math.round(currentWidth), 200, 6000),
            heightPx: clamp(Math.round(currentHeight), 200, 6000)
        };
    }, [sizePreset, currentWidth, currentHeight, customWidth, customHeight]);

    const handleExport = async () => {
        await onExport({
            format,
            dpi,
            background,
            widthPx: dimensions.widthPx,
            heightPx: dimensions.heightPx,
            filename: sanitizeFilename(filename)
        });
    };

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-[120] flex items-center justify-center bg-black/40 p-4">
            <div className="w-full max-w-md rounded-lg bg-white shadow-xl border border-slate-200">
                <div className="flex items-center justify-between border-b border-slate-200 px-5 py-3">
                    <h3 className="text-base font-semibold text-slate-800">Download Figure</h3>
                    <button
                        type="button"
                        onClick={onClose}
                        disabled={isExporting}
                        className="text-slate-500 hover:text-slate-700 disabled:opacity-50"
                    >
                        x
                    </button>
                </div>

                <div className="space-y-4 px-5 py-4">
                    <div className="grid grid-cols-2 gap-3">
                        <div>
                            <label className="block text-xs text-slate-600 mb-1">Format</label>
                            <select
                                value={format}
                                onChange={(e) => setFormat(e.target.value as ChartExportFormat)}
                                className="w-full text-sm border border-slate-300 rounded px-2 py-1.5 focus:ring-1 focus:ring-primary focus:border-primary"
                            >
                                <option value="svg">SVG (vector)</option>
                                <option value="png">PNG (raster)</option>
                            </select>
                        </div>
                        <div>
                            <label className="block text-xs text-slate-600 mb-1">Size</label>
                            <select
                                value={sizePreset}
                                onChange={(e) => setSizePreset(e.target.value as ChartExportSizePreset)}
                                className="w-full text-sm border border-slate-300 rounded px-2 py-1.5 focus:ring-1 focus:ring-primary focus:border-primary"
                            >
                                <option value="current">Current View</option>
                                <option value="single_column">Journal Single Column</option>
                                <option value="double_column">Journal Double Column</option>
                                <option value="presentation">Presentation (1920x1080)</option>
                                <option value="custom">Custom</option>
                            </select>
                        </div>
                    </div>

                    {sizePreset === 'custom' && (
                        <div className="grid grid-cols-2 gap-3">
                            <div>
                                <label className="block text-xs text-slate-600 mb-1">Width (px)</label>
                                <input
                                    type="number"
                                    value={customWidth}
                                    min={200}
                                    max={6000}
                                    onChange={(e) => setCustomWidth(Number(e.target.value))}
                                    className="w-full text-sm border border-slate-300 rounded px-2 py-1.5 focus:ring-1 focus:ring-primary focus:border-primary"
                                />
                            </div>
                            <div>
                                <label className="block text-xs text-slate-600 mb-1">Height (px)</label>
                                <input
                                    type="number"
                                    value={customHeight}
                                    min={200}
                                    max={6000}
                                    onChange={(e) => setCustomHeight(Number(e.target.value))}
                                    className="w-full text-sm border border-slate-300 rounded px-2 py-1.5 focus:ring-1 focus:ring-primary focus:border-primary"
                                />
                            </div>
                        </div>
                    )}

                    <div className="grid grid-cols-2 gap-3">
                        <div>
                            <label className="block text-xs text-slate-600 mb-1">Resolution</label>
                            <select
                                value={dpi}
                                onChange={(e) => setDpi(Number(e.target.value))}
                                disabled={format !== 'png'}
                                className="w-full text-sm border border-slate-300 rounded px-2 py-1.5 focus:ring-1 focus:ring-primary focus:border-primary disabled:opacity-50"
                            >
                                <option value={150}>150 dpi</option>
                                <option value={300}>300 dpi</option>
                                <option value={600}>600 dpi</option>
                            </select>
                        </div>
                        <div>
                            <label className="block text-xs text-slate-600 mb-1">Background</label>
                            <select
                                value={background}
                                onChange={(e) => setBackground(e.target.value as ChartExportBackground)}
                                className="w-full text-sm border border-slate-300 rounded px-2 py-1.5 focus:ring-1 focus:ring-primary focus:border-primary"
                            >
                                <option value="white">White</option>
                                <option value="transparent">Transparent</option>
                            </select>
                        </div>
                    </div>

                    <div>
                        <label className="block text-xs text-slate-600 mb-1">Filename</label>
                        <input
                            type="text"
                            value={filename}
                            onChange={(e) => setFilename(e.target.value)}
                            className="w-full text-sm border border-slate-300 rounded px-2 py-1.5 focus:ring-1 focus:ring-primary focus:border-primary"
                        />
                        <p className="text-[11px] text-slate-500 mt-1">
                            Output: {dimensions.widthPx} x {dimensions.heightPx} px
                            {format === 'png' ? ` @ ${dpi} dpi` : ''}
                        </p>
                    </div>
                </div>

                <div className="flex items-center justify-end gap-2 border-t border-slate-200 px-5 py-3">
                    <button
                        type="button"
                        onClick={onClose}
                        disabled={isExporting}
                        className="px-3 py-1.5 text-sm border border-slate-300 rounded hover:bg-slate-50 disabled:opacity-50"
                    >
                        Cancel
                    </button>
                    <button
                        type="button"
                        onClick={handleExport}
                        disabled={isExporting}
                        className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
                    >
                        {isExporting ? 'Exporting...' : 'Download'}
                    </button>
                </div>
            </div>
        </div>
    );
};

export default ChartExportModal;
