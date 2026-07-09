import React, { useState, useEffect } from 'react';
import { apiService } from '../services/api';
import GeneSetEditorModal from './GeneSetEditorModal';
import ConfirmModal from './ConfirmModal';

interface TreeNode {
    name: string;
    type: 'folder' | 'file';
    path: string;
    fullName?: string;
    children?: TreeNode[];
}

interface InterestingGenesSidebarProps {
    workbenchId: number;
    onGenesSelected: (genes: string[], fileNames: string[]) => void;
}

const InterestingGenesSidebar: React.FC<InterestingGenesSidebarProps> = ({
    workbenchId,
    onGenesSelected
}) => {
    const [treeData, setTreeData] = useState<TreeNode[]>([]);
    const [filteredTreeData, setFilteredTreeData] = useState<TreeNode[]>([]);
    const [selectedFiles, setSelectedFiles] = useState<Set<string>>(new Set());
    const [expandedFolders, setExpandedFolders] = useState<Set<string>>(new Set());
    const [searchQuery, setSearchQuery] = useState('');
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    // Editor modal state
    const [isEditorOpen, setIsEditorOpen] = useState(false);
    const [editorMode, setEditorMode] = useState<'create' | 'edit'>('create');
    const [editorFolderPath, setEditorFolderPath] = useState('');
    const [editorFilePath, setEditorFilePath] = useState('');
    const [editorFileName, setEditorFileName] = useState('');

    // Selected folder for create new gene set
    const [selectedFolderForCreate, setSelectedFolderForCreate] = useState<string>('');

    // Confirm modal state
    const [confirmModal, setConfirmModal] = useState<{
        isOpen: boolean;
        title: string;
        message: string;
        onConfirm: () => void;
    }>({
        isOpen: false,
        title: '',
        message: '',
        onConfirm: () => {}
    });

    // Load tree structure on mount
    useEffect(() => {
        loadTreeData();
    }, []);

    const loadTreeData = async () => {
        setIsLoading(true);
        setError(null);
        try {
            const response = await apiService.getInterestingGenesTree();
            if (response.success) {
                setTreeData(response.tree);
                setFilteredTreeData(response.tree);
                // 첫 번째 레벨 폴더를 자동으로 펼치기
                const firstLevelFolders = new Set(
                    response.tree.filter(node => node.type === 'folder').map(node => node.path)
                );
                setExpandedFolders(firstLevelFolders);
            } else {
                setError(response.error || 'Failed to load gene sets');
            }
        } catch (err: any) {
            console.error('Failed to load interesting genes tree:', err);
            setError(err.message || 'Failed to load gene sets');
        } finally {
            setIsLoading(false);
        }
    };

    // Filter tree based on search query
    const filterTree = (nodes: TreeNode[], query: string): TreeNode[] => {
        if (!query.trim()) return nodes;

        const lowerQuery = query.toLowerCase();
        const filtered: TreeNode[] = [];

        for (const node of nodes) {
            if (node.type === 'folder') {
                // Recursively filter children
                const filteredChildren = filterTree(node.children || [], query);

                // Include folder if it has matching children or its name matches
                if (filteredChildren.length > 0 || node.name.toLowerCase().includes(lowerQuery)) {
                    filtered.push({
                        ...node,
                        children: filteredChildren.length > 0 ? filteredChildren : node.children
                    });
                }
            } else {
                // Include file if its name matches
                if (node.name.toLowerCase().includes(lowerQuery)) {
                    filtered.push(node);
                }
            }
        }

        return filtered;
    };

    // Auto-expand folders when searching
    const collectFolderPaths = (nodes: TreeNode[], paths: Set<string> = new Set()): Set<string> => {
        for (const node of nodes) {
            if (node.type === 'folder') {
                paths.add(node.path);
                if (node.children) {
                    collectFolderPaths(node.children, paths);
                }
            }
        }
        return paths;
    };

    // Handle search input change
    useEffect(() => {
        const filtered = filterTree(treeData, searchQuery);
        setFilteredTreeData(filtered);

        // Auto-expand all folders when searching
        if (searchQuery.trim()) {
            const allFolderPaths = collectFolderPaths(filtered);
            setExpandedFolders(allFolderPaths);
        } else {
            // Reset to first level only when search is cleared
            const firstLevelFolders = new Set(
                treeData.filter(node => node.type === 'folder').map(node => node.path)
            );
            setExpandedFolders(firstLevelFolders);
        }
    }, [searchQuery, treeData]);

    const toggleFolder = (folderPath: string) => {
        const newExpanded = new Set(expandedFolders);
        if (newExpanded.has(folderPath)) {
            newExpanded.delete(folderPath);
        } else {
            newExpanded.add(folderPath);
        }
        setExpandedFolders(newExpanded);
    };

    const handleFileClick = async (filePath: string, event: React.MouseEvent) => {
        const isCtrlPressed = event.ctrlKey || event.metaKey;

        let newSelectedFiles = new Set(selectedFiles);

        if (isCtrlPressed) {
            // Ctrl + 클릭: 토글
            if (newSelectedFiles.has(filePath)) {
                newSelectedFiles.delete(filePath);
            } else {
                newSelectedFiles.add(filePath);
            }
        } else {
            // 단일 선택
            newSelectedFiles = new Set([filePath]);
        }

        setSelectedFiles(newSelectedFiles);

        // Load genes from all selected files
        await loadSelectedGenes(Array.from(newSelectedFiles));
    };

    const loadSelectedGenes = async (filePaths: string[]) => {
        if (filePaths.length === 0) {
            onGenesSelected([], []);
            return;
        }

        try {
            // Load genes from all selected files in parallel
            const promises = filePaths.map(path => apiService.getInterestingGenes(path));
            const results = await Promise.all(promises);

            // Combine all genes (remove duplicates)
            const allGenes = new Set<string>();
            results.forEach(result => {
                if (result.success) {
                    result.genes.forEach(gene => allGenes.add(gene));
                }
            });

            // Extract file names from paths
            const fileNames = filePaths.map(path => {
                const parts = path.split('/');
                return parts[parts.length - 1].replace('.txt', '');
            });

            onGenesSelected(Array.from(allGenes), fileNames);
        } catch (err) {
            console.error('Failed to load genes:', err);
            onGenesSelected([], []);
        }
    };

    // Editor handlers
    const handleOpenCreate = () => {
        setEditorMode('create');
        setEditorFolderPath(selectedFolderForCreate);
        setIsEditorOpen(true);
    };

    const handleOpenEdit = (filePath: string, fileName: string) => {
        setEditorMode('edit');
        setEditorFilePath(filePath);
        setEditorFileName(fileName);
        setIsEditorOpen(true);
    };

    const handleDelete = (filePath: string, fileName: string) => {
        setConfirmModal({
            isOpen: true,
            title: 'Delete Gene Set',
            message: `Are you sure you want to delete "${fileName}"?`,
            onConfirm: async () => {
                setConfirmModal({ ...confirmModal, isOpen: false });
                try {
                    const response = await apiService.deleteGeneSet(filePath);
                    if (response.success) {
                        // Reload tree
                        await loadTreeData();
                        // Clear selection if deleted file was selected
                        if (selectedFiles.has(filePath)) {
                            const newSelected = new Set(selectedFiles);
                            newSelected.delete(filePath);
                            setSelectedFiles(newSelected);
                            await loadSelectedGenes(Array.from(newSelected));
                        }
                    } else {
                        alert(`Failed to delete: ${response.error}`);
                    }
                } catch (err: any) {
                    alert(`Failed to delete: ${err.message}`);
                }
            }
        });
    };

    const handleDeleteFolder = (folderPath: string, folderName: string) => {
        setConfirmModal({
            isOpen: true,
            title: 'Delete Folder',
            message: `Are you sure you want to delete folder "${folderName}" and all its contents?`,
            onConfirm: async () => {
                setConfirmModal({ ...confirmModal, isOpen: false });
                try {
                    const response = await apiService.deleteFolder(folderPath);
                    if (response.success) {
                        // Reload tree
                        await loadTreeData();
                        // Clear folder from create selection
                        if (selectedFolderForCreate === folderPath) {
                            setSelectedFolderForCreate('');
                        }
                    } else {
                        alert(`Failed to delete folder: ${response.error}`);
                    }
                } catch (err: any) {
                    alert(`Failed to delete folder: ${err.message}`);
                }
            }
        });
    };

    const handleEditorSuccess = async () => {
        // Reload tree
        await loadTreeData();
    };

    // Collect all folder paths for "New Gene Set" dropdown
    const collectAllFolders = (nodes: TreeNode[], folders: Array<{name: string, path: string}> = [], parentName: string = ''): Array<{name: string, path: string}> => {
        for (const node of nodes) {
            if (node.type === 'folder') {
                const displayName = parentName ? `${parentName} / ${node.name}` : node.name;
                folders.push({ name: displayName, path: node.path });
                if (node.children) {
                    collectAllFolders(node.children, folders, displayName);
                }
            }
        }
        return folders;
    };

    // Highlight search query in text
    const highlightText = (text: string, query: string) => {
        if (!query.trim()) return <span>{text}</span>;

        const lowerText = text.toLowerCase();
        const lowerQuery = query.toLowerCase();
        const index = lowerText.indexOf(lowerQuery);

        if (index === -1) return <span>{text}</span>;

        const before = text.substring(0, index);
        const match = text.substring(index, index + query.length);
        const after = text.substring(index + query.length);

        return (
            <span>
                {before}
                <mark className="bg-yellow-200 font-semibold">{match}</mark>
                {after}
            </span>
        );
    };

    const renderTreeNode = (node: TreeNode, level: number = 0) => {
        const isExpanded = expandedFolders.has(node.path);
        const isSelected = selectedFiles.has(node.path);
        const isFolderSelectedForCreate = selectedFolderForCreate === node.path;
        const paddingLeft = `${level * 16 + 8}px`;

        if (node.type === 'folder') {
            return (
                <div key={node.path}>
                    <div
                        className={`group flex items-center py-1.5 px-2 hover:bg-slate-100 cursor-pointer select-none ${
                            isFolderSelectedForCreate ? 'bg-blue-100 border-l-2 border-blue-500' : ''
                        }`}
                        style={{ paddingLeft }}
                    >
                        <div
                            className="flex items-center flex-1"
                            onClick={() => {
                                toggleFolder(node.path);
                                setSelectedFolderForCreate(node.path);
                            }}
                        >
                            <svg
                                className={`w-4 h-4 mr-1 transition-transform ${isExpanded ? 'rotate-90' : ''}`}
                                fill="none"
                                stroke="currentColor"
                                viewBox="0 0 24 24"
                            >
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                            </svg>
                            <svg className="w-4 h-4 mr-2 text-yellow-500" fill="currentColor" viewBox="0 0 20 20">
                                <path d="M2 6a2 2 0 012-2h5l2 2h5a2 2 0 012 2v6a2 2 0 01-2 2H4a2 2 0 01-2-2V6z" />
                            </svg>
                            <span className="text-sm font-medium text-slate-700">
                                {highlightText(node.name, searchQuery)}
                            </span>
                        </div>
                        {/* Delete button (show on hover) */}
                        <button
                            onClick={(e) => {
                                e.stopPropagation();
                                handleDeleteFolder(node.path, node.name);
                            }}
                            className="p-1 hover:bg-red-200 rounded opacity-0 group-hover:opacity-100 transition-opacity"
                            title="Delete folder"
                        >
                            <svg className="w-3.5 h-3.5 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                            </svg>
                        </button>
                    </div>
                    {isExpanded && node.children && (
                        <div>
                            {node.children.map(child => renderTreeNode(child, level + 1))}
                        </div>
                    )}
                </div>
            );
        } else {
            // File node
            return (
                <div
                    key={node.path}
                    className={`group flex items-center py-1.5 px-2 hover:bg-blue-50 cursor-pointer select-none ${
                        isSelected ? 'bg-blue-100' : ''
                    }`}
                    style={{ paddingLeft }}
                >
                    <svg className="w-4 h-4 mr-2 text-slate-400 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4z" clipRule="evenodd" />
                    </svg>
                    <span
                        className={`text-sm flex-1 ${isSelected ? 'font-semibold text-blue-700' : 'text-slate-600'}`}
                        onClick={(e) => handleFileClick(node.path, e)}
                    >
                        {highlightText(node.name, searchQuery)}
                    </span>
                    {/* Action buttons (show on hover) */}
                    <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                        <button
                            onClick={(e) => {
                                e.stopPropagation();
                                handleOpenEdit(node.path, node.name);
                            }}
                            className="p-1 hover:bg-blue-200 rounded"
                            title="Edit"
                        >
                            <svg className="w-3.5 h-3.5 text-slate-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                            </svg>
                        </button>
                        <button
                            onClick={(e) => {
                                e.stopPropagation();
                                handleDelete(node.path, node.name);
                            }}
                            className="p-1 hover:bg-red-200 rounded"
                            title="Delete"
                        >
                            <svg className="w-3.5 h-3.5 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                            </svg>
                        </button>
                    </div>
                </div>
            );
        }
    };

    const allFolders = collectAllFolders(treeData);

    return (
        <div className="h-full flex flex-col border-r border-slate-200 bg-white" style={{ minWidth: '200px', width: '280px', resize: 'horizontal', overflow: 'auto' }}>
            {/* Header */}
            <div className="px-4 py-3 border-b border-slate-200 bg-slate-50">
                <div className="flex items-center justify-between mb-1">
                    <h3 className="text-sm font-semibold text-slate-800">Interesting Gene Sets</h3>
                    {/* New Gene Set Button */}
                    <button
                        onClick={handleOpenCreate}
                        className="p-1 hover:bg-slate-200 rounded transition-colors"
                        title="Create New Gene Set"
                    >
                        <svg className="w-4 h-4 text-slate-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                        </svg>
                    </button>
                </div>
                {selectedFiles.size > 0 && (
                    <p className="text-xs text-slate-500 mt-1">
                        {selectedFiles.size} set{selectedFiles.size > 1 ? 's' : ''} selected
                    </p>
                )}
            </div>

            {/* Search bar */}
            <div className="px-3 py-2 border-b border-slate-200 bg-white">
                <div className="relative">
                    <svg
                        className="absolute left-2 top-1/2 transform -translate-y-1/2 w-4 h-4 text-slate-400"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                    >
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                    </svg>
                    <input
                        type="text"
                        placeholder="Search gene sets..."
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        className="w-full pl-8 pr-8 py-1.5 text-sm border border-slate-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                    />
                    {searchQuery && (
                        <button
                            onClick={() => setSearchQuery('')}
                            className="absolute right-2 top-1/2 transform -translate-y-1/2 text-slate-400 hover:text-slate-600"
                        >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                            </svg>
                        </button>
                    )}
                </div>
            </div>

            {/* Tree content */}
            <div className="flex-1 overflow-y-auto">
                {isLoading ? (
                    <div className="flex items-center justify-center py-8">
                        <div className="text-center">
                            <svg className="animate-spin h-6 w-6 text-blue-600 mx-auto" fill="none" viewBox="0 0 24 24">
                                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                            </svg>
                            <p className="text-xs text-slate-500 mt-2">Loading...</p>
                        </div>
                    </div>
                ) : error ? (
                    <div className="px-4 py-8 text-center">
                        <svg className="w-8 h-8 text-red-400 mx-auto mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        <p className="text-xs text-red-600">{error}</p>
                        <button
                            onClick={loadTreeData}
                            className="mt-2 text-xs text-blue-600 hover:text-blue-700 underline"
                        >
                            Retry
                        </button>
                    </div>
                ) : filteredTreeData.length === 0 ? (
                    <div className="px-4 py-8 text-center">
                        <p className="text-xs text-slate-500">
                            {searchQuery ? 'No matching gene sets found' : 'No gene sets available'}
                        </p>
                    </div>
                ) : (
                    <div className="py-1">
                        {filteredTreeData.map(node => renderTreeNode(node, 0))}
                    </div>
                )}
            </div>

            {/* Footer hint */}
            <div className="px-3 py-2 border-t border-slate-200 bg-slate-50">
                <p className="text-xs text-slate-500">
                    Ctrl+Click to select multiple
                </p>
            </div>

            {/* Gene Set Editor Modal */}
            <GeneSetEditorModal
                isOpen={isEditorOpen}
                onClose={() => setIsEditorOpen(false)}
                onSuccess={handleEditorSuccess}
                mode={editorMode}
                folderPath={editorFolderPath}
                filePath={editorFilePath}
                fileName={editorFileName}
            />

            {/* Confirm Modal */}
            <ConfirmModal
                isOpen={confirmModal.isOpen}
                title={confirmModal.title}
                message={confirmModal.message}
                confirmText="Delete"
                cancelText="Cancel"
                onConfirm={confirmModal.onConfirm}
                onCancel={() => setConfirmModal({ ...confirmModal, isOpen: false })}
                variant="danger"
            />
        </div>
    );
};

export default InterestingGenesSidebar;
