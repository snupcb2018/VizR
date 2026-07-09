import React, { useState, useEffect, useRef } from 'react';
import { apiService } from '../services/api';
import ConfirmModal from './ConfirmModal';

interface GeneSetEditorModalProps {
    isOpen: boolean;
    onClose: () => void;
    onSuccess: () => void;
    mode: 'create' | 'edit';
    folderPath?: string;  // For create mode
    filePath?: string;    // For edit mode
    fileName?: string;    // For edit mode
}

// 파일 트리 구조를 위한 타입
interface FileTreeNode {
    name: string;
    path: string;
    type: 'file' | 'folder';
    children?: FileTreeNode[];
    file?: File;
}

// 폴더 트리 구조를 위한 타입
interface FolderTreeNode {
    name: string;
    path: string;
    children?: FolderTreeNode[];
    isEditing?: boolean;
    isExpanded?: boolean;
}

// 트리 노드 컴포넌트
const FileTreeNodeComponent: React.FC<{
    node: FileTreeNode;
    level: number;
}> = ({ node, level }) => {
    const [isExpanded, setIsExpanded] = useState(true);

    const indent = level * 16;

    if (node.type === 'file') {
        return (
            <div
                className="flex items-center py-1 text-sm text-slate-700"
                style={{ paddingLeft: `${indent}px` }}
            >
                <span className="mr-2 text-slate-400">├─</span>
                <span>{node.name}</span>
            </div>
        );
    }

    // Folder
    const fileCount = countFiles(node);

    return (
        <div>
            <div
                className="flex items-center py-1 text-sm cursor-pointer hover:bg-slate-50"
                style={{ paddingLeft: `${indent}px` }}
                onClick={() => setIsExpanded(!isExpanded)}
            >
                <span className="mr-2 text-blue-600">
                    {isExpanded ? '▼' : '▶'}
                </span>
                <span className="font-medium text-slate-800">{node.name}</span>
                <span className="ml-2 text-xs text-slate-500">({fileCount} files)</span>
            </div>
            {isExpanded && node.children && (
                <div>
                    {node.children.map((child, index) => (
                        <FileTreeNodeComponent
                            key={child.path}
                            node={child}
                            level={level + 1}
                        />
                    ))}
                </div>
            )}
        </div>
    );
};

// 파일 개수 계산 (재귀)
const countFiles = (node: FileTreeNode): number => {
    if (node.type === 'file') return 1;
    if (!node.children) return 0;
    return node.children.reduce((sum, child) => sum + countFiles(child), 0);
};

// 폴더 선택 트리 노드 컴포넌트
const FolderTreeNodeComponent: React.FC<{
    node: FolderTreeNode;
    level: number;
    selectedPath: string;
    onSelect: (path: string) => void;
    onCreateFolder: (parentPath: string, folderName: string) => void;
    onCancelEdit: (path: string) => void;
    onToggleExpand: (path: string) => void;
    onDeleteFolder: (folderPath: string, folderName: string) => void;
}> = ({ node, level, selectedPath, onSelect, onCreateFolder, onCancelEdit, onToggleExpand, onDeleteFolder }) => {
    const [newFolderName, setNewFolderName] = useState('');

    const indent = level * 16;
    const isSelected = selectedPath === node.path;
    const isExpanded = node.isExpanded !== undefined ? node.isExpanded : (level === 0);

    const handleKeyPress = (e: React.KeyboardEvent<HTMLInputElement>) => {
        if (e.key === 'Enter') {
            if (newFolderName.trim()) {
                onCreateFolder(node.path, newFolderName.trim());
                setNewFolderName('');
            }
        } else if (e.key === 'Escape') {
            onCancelEdit(node.path);
            setNewFolderName('');
        }
    };

    return (
        <div>
            {/* 폴더 노드 */}
            <div
                className={`group flex items-center py-1 text-sm hover:bg-blue-50 ${
                    isSelected ? 'bg-blue-100' : ''
                }`}
                style={{ paddingLeft: `${indent}px` }}
            >
                <div
                    className="flex items-center flex-1 cursor-pointer"
                    onClick={() => {
                        onSelect(node.path);
                        if (node.children && node.children.length > 0) {
                            onToggleExpand(node.path);
                        }
                    }}
                >
                    <span className="mr-2 text-blue-600 w-4">
                        {node.children && node.children.length > 0 ? (isExpanded ? '▼' : '▶') : ''}
                    </span>
                    <svg className="w-4 h-4 text-yellow-600 mr-2" fill="currentColor" viewBox="0 0 20 20">
                        <path d="M2 6a2 2 0 012-2h5l2 2h5a2 2 0 012 2v6a2 2 0 01-2 2H4a2 2 0 01-2-2V6z" />
                    </svg>
                    <span className="font-medium text-slate-800">{node.name || './'}</span>
                </div>
                {/* 루트가 아닌 경우에만 삭제 버튼 표시 */}
                {node.path !== '' && (
                    <button
                        onClick={(e) => {
                            e.stopPropagation();
                            onDeleteFolder(node.path, node.name);
                        }}
                        className="p-1 hover:bg-red-200 rounded opacity-0 group-hover:opacity-100 transition-opacity"
                        title="Delete folder"
                    >
                        <svg className="w-3.5 h-3.5 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                        </svg>
                    </button>
                )}
            </div>

            {/* 자식 노드들 */}
            {isExpanded && node.children && (
                <div>
                    {node.children.map((child) => (
                        <FolderTreeNodeComponent
                            key={child.path}
                            node={child}
                            level={level + 1}
                            selectedPath={selectedPath}
                            onSelect={onSelect}
                            onCreateFolder={onCreateFolder}
                            onCancelEdit={onCancelEdit}
                            onToggleExpand={onToggleExpand}
                            onDeleteFolder={onDeleteFolder}
                        />
                    ))}

                    {/* 새 폴더 입력 필드 */}
                    {node.isEditing && (
                        <div
                            className="flex items-center py-1"
                            style={{ paddingLeft: `${(level + 1) * 16}px` }}
                        >
                            <span className="mr-2 w-4"></span>
                            <svg className="w-4 h-4 text-yellow-400 mr-2" fill="currentColor" viewBox="0 0 20 20">
                                <path d="M2 6a2 2 0 012-2h5l2 2h5a2 2 0 012 2v6a2 2 0 01-2 2H4a2 2 0 01-2-2V6z" />
                            </svg>
                            <input
                                type="text"
                                value={newFolderName}
                                onChange={(e) => setNewFolderName(e.target.value)}
                                onKeyDown={handleKeyPress}
                                onBlur={() => {
                                    if (!newFolderName.trim()) {
                                        onCancelEdit(node.path);
                                    }
                                }}
                                placeholder="folder name..."
                                className="flex-1 px-2 py-0.5 text-sm border border-blue-400 rounded focus:outline-none focus:ring-1 focus:ring-blue-500"
                                autoFocus
                            />
                        </div>
                    )}
                </div>
            )}
        </div>
    );
};

const GeneSetEditorModal: React.FC<GeneSetEditorModalProps> = ({
    isOpen,
    onClose,
    onSuccess,
    mode,
    folderPath = '',
    filePath = '',
    fileName = ''
}) => {
    const [newFileName, setNewFileName] = useState('');
    const [genesText, setGenesText] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // Tab state (only for create mode)
    const [activeTab, setActiveTab] = useState<'manual' | 'upload'>('manual');
    const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
    const fileInputRef = useRef<HTMLInputElement>(null);
    const folderInputRef = useRef<HTMLInputElement>(null);

    // Folder selection state
    const [selectedFolderPath, setSelectedFolderPath] = useState(folderPath);
    const [folderTree, setFolderTree] = useState<FolderTreeNode[]>([]);
    const [isFoldersLoading, setIsFoldersLoading] = useState(false);

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

    // Load folder list when modal opens
    useEffect(() => {
        if (isOpen && mode === 'create') {
            loadFolderList();
        }
    }, [isOpen, mode]);

    // Load existing genes when editing or initialize create mode
    useEffect(() => {
        if (isOpen && mode === 'edit' && filePath) {
            loadExistingGenes();
        } else if (isOpen && mode === 'create') {
            setNewFileName('');
            setGenesText('');
            setSelectedFiles([]);
            setActiveTab('manual');
            setError(null);

            // Set initial folder path
            const lastSelectedFolder = localStorage.getItem('lastSelectedGeneSetFolder');
            if (folderPath) {
                // Use provided folderPath (from + button click)
                setSelectedFolderPath(folderPath);
            } else if (lastSelectedFolder) {
                // Use last selected folder
                setSelectedFolderPath(lastSelectedFolder);
            } else {
                // Default to root
                setSelectedFolderPath('');
            }
        }
    }, [isOpen, mode, filePath, folderPath]);

    const loadFolderList = async () => {
        setIsFoldersLoading(true);
        try {
            const response = await apiService.getInterestingGenesTree();
            if (response.success) {
                // Build folder tree (exclude files)
                const buildFolderTree = (items: any[]): FolderTreeNode[] => {
                    return items
                        .filter(item => item.type === 'folder')
                        .map(item => ({
                            name: item.name,
                            path: item.path,
                            children: item.children ? buildFolderTree(item.children) : []
                        }));
                };

                const tree = buildFolderTree(response.tree);

                // Add root folder
                const rootNode: FolderTreeNode = {
                    name: '',
                    path: '',
                    children: tree
                };

                setFolderTree([rootNode]);
            }
        } catch (err: any) {
            console.error('Failed to load folder list:', err);
        } finally {
            setIsFoldersLoading(false);
        }
    };

    const loadExistingGenes = async () => {
        setIsLoading(true);
        setError(null);
        try {
            const response = await apiService.getInterestingGenes(filePath);
            if (response.success) {
                setGenesText(response.genes.join('\n'));
            } else {
                setError(response.error || 'Failed to load genes');
            }
        } catch (err: any) {
            setError(err.message || 'Failed to load genes');
        } finally {
            setIsLoading(false);
        }
    };

    // 트리 노드 토글
    const toggleNodeExpand = (path: string) => {
        const toggleNodes = (nodes: FolderTreeNode[]): FolderTreeNode[] => {
            return nodes.map(node => {
                if (node.path === path) {
                    return {
                        ...node,
                        isExpanded: !node.isExpanded
                    };
                }
                if (node.children) {
                    return {
                        ...node,
                        children: toggleNodes(node.children)
                    };
                }
                return node;
            });
        };

        setFolderTree(toggleNodes(folderTree));
    };

    // 경로에 포함된 모든 폴더를 찾아서 확장 상태 설정
    const expandPathToNode = (path: string) => {
        if (!path) return;

        // path를 분리하여 모든 상위 경로 생성
        // 예: "a/b/c" -> ["a", "a/b", "a/b/c"]
        const parts = path.split('/');
        const pathsToExpand: string[] = [];

        for (let i = 0; i < parts.length; i++) {
            pathsToExpand.push(parts.slice(0, i + 1).join('/'));
        }

        // 각 경로의 노드를 찾아서 펼침 상태로 설정
        const expandNodes = (nodes: FolderTreeNode[]): FolderTreeNode[] => {
            return nodes.map(node => {
                if (pathsToExpand.includes(node.path) || node.path === '') {
                    // 이 경로는 펼쳐야 함 (루트도 포함)
                    return {
                        ...node,
                        isExpanded: true,
                        children: node.children ? expandNodes(node.children) : node.children
                    };
                }
                return node;
            });
        };

        setFolderTree(expandNodes(folderTree));
    };

    // 폴더 경로가 변경되면 해당 경로까지 트리 펼침
    useEffect(() => {
        if (folderPath && folderTree.length > 0) {
            expandPathToNode(folderPath);
        }
    }, [folderPath, folderTree.length]);

    // 트리에서 특정 경로의 노드를 찾아 isEditing 플래그 설정
    const setNodeEditing = (nodes: FolderTreeNode[], targetPath: string, isEditing: boolean): FolderTreeNode[] => {
        return nodes.map(node => {
            if (node.path === targetPath) {
                return { ...node, isEditing };
            }
            if (node.children) {
                return {
                    ...node,
                    children: setNodeEditing(node.children, targetPath, isEditing)
                };
            }
            return node;
        });
    };

    // 새 폴더 추가
    const handleCreateFolder = (parentPath: string, folderName: string) => {
        const newPath = parentPath ? `${parentPath}/${folderName}` : folderName;

        // 트리에 새 폴더 추가
        const addFolder = (nodes: FolderTreeNode[]): FolderTreeNode[] => {
            return nodes.map(node => {
                if (node.path === parentPath) {
                    const newFolder: FolderTreeNode = {
                        name: folderName,
                        path: newPath,
                        children: []
                    };
                    return {
                        ...node,
                        isEditing: false,
                        children: [...(node.children || []), newFolder]
                    };
                }
                if (node.children) {
                    return {
                        ...node,
                        children: addFolder(node.children)
                    };
                }
                return node;
            });
        };

        setFolderTree(addFolder(folderTree));
        setSelectedFolderPath(newPath);
    };

    // 새 폴더 입력 취소
    const handleCancelEdit = (path: string) => {
        setFolderTree(setNodeEditing(folderTree, path, false));
    };

    // 폴더 삭제
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
                        // 트리 다시 로드
                        await loadFolderList();
                        // 삭제된 폴더가 선택되어 있었다면 루트로 변경
                        if (selectedFolderPath === folderPath || selectedFolderPath.startsWith(folderPath + '/')) {
                            setSelectedFolderPath('');
                        }
                    } else {
                        setError(`Failed to delete folder: ${response.error}`);
                    }
                } catch (err: any) {
                    setError(`Failed to delete folder: ${err.message}`);
                }
            }
        });
    };

    // New Folder 버튼 클릭
    const handleNewFolderClick = () => {
        if (!selectedFolderPath && selectedFolderPath !== '') {
            setError('Please select a folder first');
            return;
        }

        // 선택된 폴더를 펼치고 편집 모드로 설정
        const expandAndEdit = (nodes: FolderTreeNode[]): FolderTreeNode[] => {
            return nodes.map(node => {
                if (node.path === selectedFolderPath) {
                    return {
                        ...node,
                        isExpanded: true,
                        isEditing: true
                    };
                }
                if (node.children) {
                    return {
                        ...node,
                        children: expandAndEdit(node.children)
                    };
                }
                return node;
            });
        };

        setFolderTree(expandAndEdit(folderTree));
    };

    const parseGenes = (text: string): string[] => {
        return text
            .split('\n')
            .map(line => line.trim())
            .filter(line => line.length > 0);
    };

    // 파일 목록을 트리 구조로 변환
    const buildFileTree = (files: File[]): FileTreeNode[] => {
        const root: { [key: string]: FileTreeNode } = {};

        files.forEach(file => {
            const fileWithPath = file as any;
            const relativePath = fileWithPath.webkitRelativePath || file.name;
            const parts = relativePath.split('/');

            let currentLevel = root;

            parts.forEach((part, index) => {
                if (!currentLevel[part]) {
                    const isFile = index === parts.length - 1;
                    currentLevel[part] = {
                        name: part,
                        path: parts.slice(0, index + 1).join('/'),
                        type: isFile ? 'file' : 'folder',
                        children: isFile ? undefined : {},
                        file: isFile ? file : undefined
                    };
                }

                if (index < parts.length - 1) {
                    currentLevel = currentLevel[part].children as any;
                }
            });
        });

        // 객체를 배열로 변환
        const convertToArray = (obj: { [key: string]: FileTreeNode }): FileTreeNode[] => {
            return Object.values(obj).map(node => ({
                ...node,
                children: node.children ? convertToArray(node.children as any) : undefined
            }));
        };

        return convertToArray(root);
    };

    const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
        const files = event.target.files;
        if (files) {
            const txtFiles = Array.from(files).filter(file => file.name.endsWith('.txt'));
            setSelectedFiles(prev => [...prev, ...txtFiles]);
            setError(null);
        }
    };

    const handleFolderSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
        const files = event.target.files;
        if (files) {
            const txtFiles = Array.from(files).filter(file => file.name.endsWith('.txt'));
            setSelectedFiles(prev => [...prev, ...txtFiles]);
            setError(null);
        }
    };

    const handleSave = async () => {
        if (activeTab === 'manual') {
            // Manual entry mode
            const genes = parseGenes(genesText);

            if (genes.length === 0) {
                setError('Please enter at least one gene ID');
                return;
            }

            if (mode === 'create' && !newFileName.trim()) {
                setError('Please enter a file name');
                return;
            }

            setIsLoading(true);
            setError(null);

            try {
                if (mode === 'create') {
                    const response = await apiService.createGeneSet(
                        selectedFolderPath,
                        newFileName,
                        genes
                    );

                    if (response.success) {
                        // Save last selected folder
                        localStorage.setItem('lastSelectedGeneSetFolder', selectedFolderPath);
                        onSuccess();
                        onClose();
                    } else {
                        setError(response.error || 'Failed to create gene set');
                    }
                } else {
                    const response = await apiService.updateGeneSet(filePath, genes);

                    if (response.success) {
                        onSuccess();
                        onClose();
                    } else {
                        setError(response.error || 'Failed to update gene set');
                    }
                }
            } catch (err: any) {
                setError(err.message || `Failed to ${mode} gene set`);
            } finally {
                setIsLoading(false);
            }
        } else {
            // Upload mode
            if (selectedFiles.length === 0) {
                setError('Please select at least one file to upload');
                return;
            }

            setIsLoading(true);
            setError(null);

            try {
                // 선택한 Location을 그대로 사용
                // 백엔드가 webkitRelativePath를 처리하여 폴더 구조를 보존함
                const uploadPath = selectedFolderPath;

                const response = await apiService.uploadGeneSets(uploadPath, selectedFiles);

                if (response.success) {
                    // Save last selected folder
                    localStorage.setItem('lastSelectedGeneSetFolder', selectedFolderPath);
                    onSuccess();
                    onClose();
                } else {
                    setError(response.error || 'Failed to upload files');
                }
            } catch (err: any) {
                setError(err.message || 'Failed to upload files');
            } finally {
                setIsLoading(false);
            }
        }
    };

    const handleClose = () => {
        setNewFileName('');
        setGenesText('');
        setSelectedFiles([]);
        setActiveTab('manual');
        setError(null);
        onClose();
    };

    if (!isOpen) return null;

    const geneCount = parseGenes(genesText).length;

    return (
        <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex items-center justify-center p-4">
            <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] flex flex-col">
                {/* Header */}
                <div className="px-6 py-4 border-b border-slate-200 flex justify-between items-center">
                    <h2 className="text-xl font-bold text-slate-800">
                        {mode === 'create' ? 'Create New Gene Set' : 'Edit Gene Set'}
                    </h2>
                    <button
                        onClick={handleClose}
                        className="text-slate-400 hover:text-slate-600 transition-colors"
                        disabled={isLoading}
                    >
                        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                    </button>
                </div>

                {/* Tabs (only for create mode) */}
                {mode === 'create' && (
                    <div className="px-6 pt-4 border-b border-slate-200">
                        <div className="flex gap-2">
                            <button
                                onClick={() => setActiveTab('manual')}
                                className={`px-4 py-2 text-sm font-medium rounded-t-lg transition-colors ${
                                    activeTab === 'manual'
                                        ? 'bg-white text-blue-600 border-t-2 border-x-2 border-blue-600'
                                        : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                                }`}
                                disabled={isLoading}
                            >
                                Text Input
                            </button>
                            <button
                                onClick={() => setActiveTab('upload')}
                                className={`px-4 py-2 text-sm font-medium rounded-t-lg transition-colors ${
                                    activeTab === 'upload'
                                        ? 'bg-white text-blue-600 border-t-2 border-x-2 border-blue-600'
                                        : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                                }`}
                                disabled={isLoading}
                            >
                                Upload Files
                            </button>
                        </div>
                    </div>
                )}

                {/* Content */}
                <div className="overflow-auto p-6 space-y-4" style={{ height: '500px' }}>
                    {/* Folder tree selector */}
                    {mode === 'create' && (
                        <div>
                            <div className="flex items-center justify-between mb-1">
                                <label className="block text-sm font-medium text-slate-700">
                                    Location <span className="text-red-500">*</span>
                                </label>
                                <button
                                    type="button"
                                    onClick={handleNewFolderClick}
                                    className="text-xs text-blue-600 hover:text-blue-700 font-medium flex items-center gap-1"
                                    disabled={isLoading || isFoldersLoading}
                                >
                                    <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                                    </svg>
                                    New Folder
                                </button>
                            </div>
                            {isFoldersLoading ? (
                                <div className="px-3 py-2 bg-slate-50 border border-slate-200 rounded text-sm text-slate-400">
                                    Loading folders...
                                </div>
                            ) : (
                                <div className="max-h-48 overflow-y-auto border border-slate-200 rounded-lg p-2 bg-slate-50">
                                    {folderTree.map(node => (
                                        <FolderTreeNodeComponent
                                            key={node.path}
                                            node={node}
                                            level={0}
                                            selectedPath={selectedFolderPath}
                                            onSelect={setSelectedFolderPath}
                                            onCreateFolder={handleCreateFolder}
                                            onCancelEdit={handleCancelEdit}
                                            onToggleExpand={toggleNodeExpand}
                                            onDeleteFolder={handleDeleteFolder}
                                        />
                                    ))}
                                </div>
                            )}
                            <p className="text-xs text-slate-500 mt-1">
                                Selected: <strong>{selectedFolderPath || './'}</strong>
                            </p>
                        </div>
                    )}

                    {/* Manual Entry Tab Content */}
                    {(mode === 'edit' || activeTab === 'manual') && (
                        <div className="flex flex-col h-full gap-4">
                            {/* File name */}
                            {mode === 'create' ? (
                                <div className="flex-shrink-0">
                                    <label htmlFor="fileName" className="block text-sm font-medium text-slate-700 mb-1">
                                        File Name <span className="text-red-500">*</span>
                                    </label>
                                    <input
                                        type="text"
                                        id="fileName"
                                        value={newFileName}
                                        onChange={(e) => setNewFileName(e.target.value)}
                                        placeholder="e.g., MY_GENES"
                                        className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                                        disabled={isLoading}
                                    />
                                    <p className="text-xs text-slate-500 mt-1">
                                        .txt extension will be added automatically
                                    </p>
                                </div>
                            ) : (
                                <div className="flex-shrink-0">
                                    <label className="block text-sm font-medium text-slate-700 mb-1">
                                        File Name
                                    </label>
                                    <div className="px-3 py-2 bg-slate-50 border border-slate-200 rounded text-sm text-slate-600">
                                        {fileName}
                                    </div>
                                </div>
                            )}

                            {/* Gene IDs */}
                            <div className="flex-1 flex flex-col min-h-0">
                                <label htmlFor="genes" className="block text-sm font-medium text-slate-700 mb-1 flex-shrink-0">
                                    Gene IDs <span className="text-red-500">*</span>
                                    {geneCount > 0 && (
                                        <span className="ml-2 text-xs text-slate-500">
                                            ({geneCount} gene{geneCount > 1 ? 's' : ''})
                                        </span>
                                    )}
                                </label>
                                <textarea
                                    id="genes"
                                    value={genesText}
                                    onChange={(e) => setGenesText(e.target.value)}
                                    placeholder="Enter gene IDs, one per line&#10;e.g.,&#10;AT1G01010&#10;AT1G01020&#10;AT1G01030"
                                    className="flex-1 w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent font-mono text-sm resize-none"
                                    disabled={isLoading}
                                />
                                <p className="text-xs text-slate-500 mt-1 flex-shrink-0">
                                    One gene ID per line. Empty lines will be ignored.
                                </p>
                            </div>
                        </div>
                    )}

                    {/* Upload Tab Content */}
                    {mode === 'create' && activeTab === 'upload' && (
                        <>
                            <div>
                                <label className="block text-sm font-medium text-slate-700 mb-2">
                                    Select Files or Folder <span className="text-red-500">*</span>
                                </label>
                                <div className="border-2 border-dashed border-slate-300 rounded-lg p-6">
                                    {/* Hidden file inputs */}
                                    <input
                                        ref={fileInputRef}
                                        type="file"
                                        multiple
                                        accept=".txt"
                                        onChange={handleFileSelect}
                                        className="hidden"
                                    />
                                    <input
                                        ref={folderInputRef}
                                        type="file"
                                        {...({ webkitdirectory: "", directory: "" } as any)}
                                        multiple
                                        onChange={handleFolderSelect}
                                        className="hidden"
                                    />

                                    {/* Buttons */}
                                    <div className="flex justify-center gap-3">
                                        <button
                                            type="button"
                                            onClick={() => fileInputRef.current?.click()}
                                            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors flex items-center gap-2"
                                            disabled={isLoading}
                                        >
                                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                                            </svg>
                                            Choose Files
                                        </button>
                                        <button
                                            type="button"
                                            onClick={() => folderInputRef.current?.click()}
                                            className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors flex items-center gap-2"
                                            disabled={isLoading}
                                        >
                                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
                                            </svg>
                                            Choose Folder
                                        </button>
                                    </div>
                                    <p className="text-xs text-slate-500 mt-3 text-center">
                                        Select individual .txt files or an entire folder containing gene sets
                                    </p>
                                </div>
                            </div>

                            {/* Selected files tree */}
                            {selectedFiles.length > 0 && (
                                <div>
                                    <div className="flex items-center justify-between mb-2">
                                        <label className="block text-sm font-medium text-slate-700">
                                            Selected Files ({selectedFiles.length})
                                        </label>
                                        <button
                                            type="button"
                                            onClick={() => setSelectedFiles([])}
                                            className="text-xs text-red-600 hover:text-red-700 font-medium"
                                            disabled={isLoading}
                                        >
                                            Clear All
                                        </button>
                                    </div>
                                    <div className="max-h-64 overflow-y-auto border border-slate-200 rounded-lg p-3 bg-slate-50">
                                        {buildFileTree(selectedFiles).map(node => (
                                            <FileTreeNodeComponent
                                                key={node.path}
                                                node={node}
                                                level={0}
                                            />
                                        ))}
                                    </div>
                                    <p className="text-xs text-slate-500 mt-2">
                                        These files will be uploaded to: <strong>{selectedFolderPath || './'}</strong>
                                    </p>
                                </div>
                            )}
                        </>
                    )}

                    {/* Error message */}
                    {error && (
                        <div className="px-4 py-3 bg-red-50 border border-red-200 rounded-lg">
                            <div className="flex items-start">
                                <svg className="w-5 h-5 text-red-400 mr-2 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                                </svg>
                                <p className="text-sm text-red-700">{error}</p>
                            </div>
                        </div>
                    )}
                </div>

                {/* Footer */}
                <div className="px-6 py-4 border-t border-slate-200 flex justify-end gap-3 bg-slate-50">
                    <button
                        onClick={handleClose}
                        className="px-4 py-2 bg-slate-200 text-slate-700 rounded-lg hover:bg-slate-300 transition-colors text-sm font-semibold"
                        disabled={isLoading}
                    >
                        Cancel
                    </button>
                    <button
                        onClick={handleSave}
                        className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm font-semibold disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                        disabled={isLoading}
                    >
                        {isLoading && (
                            <svg className="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24">
                                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                            </svg>
                        )}
                        {activeTab === 'upload' ? 'Upload' : (mode === 'create' ? 'Create' : 'Save Changes')}
                    </button>
                </div>
            </div>

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

export default GeneSetEditorModal;
