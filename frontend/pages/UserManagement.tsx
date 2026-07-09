
import React, { useState, useEffect } from 'react';
import { APIError } from '../services/api';

interface User {
    id: number;
    username: string;
    email: string;
    full_name: string;
    created_at: string;
}

export default function UserManagement(): React.ReactNode {
    const [users, setUsers] = useState<User[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string>('');
    const [editingUser, setEditingUser] = useState<User | null>(null);
    const [deleteConfirmUser, setDeleteConfirmUser] = useState<User | null>(null);

    // Edit form state
    const [editForm, setEditForm] = useState({
        email: '',
        full_name: '',
        password: ''
    });

    useEffect(() => {
        fetchUsers();
    }, []);

    const fetchUsers = async () => {
        try {
            setLoading(true);
            const response = await fetch('/api/auth/users', {
                credentials: 'include'
            });

            if (!response.ok) {
                throw new APIError('Failed to fetch users', response.status);
            }

            const data = await response.json();
            setUsers(data.users || []);
        } catch (error) {
            console.error('Error fetching users:', error);
            setError('Failed to load users');
        } finally {
            setLoading(false);
        }
    };

    const handleEditClick = (user: User) => {
        setEditingUser(user);
        setEditForm({
            email: user.email,
            full_name: user.full_name,
            password: ''
        });
        setError('');
    };

    const handleCancelEdit = () => {
        setEditingUser(null);
        setEditForm({ email: '', full_name: '', password: '' });
        setError('');
    };

    const handleUpdateUser = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!editingUser) return;

        try {
            const response = await fetch(`/api/auth/users/${editingUser.id}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json'
                },
                credentials: 'include',
                body: JSON.stringify({
                    email: editForm.email,
                    full_name: editForm.full_name,
                    password: editForm.password || undefined
                })
            });

            if (!response.ok) {
                const data = await response.json();
                throw new APIError(data.error || 'Failed to update user', response.status);
            }

            // Refresh user list
            await fetchUsers();
            setEditingUser(null);
            setEditForm({ email: '', full_name: '', password: '' });
        } catch (error) {
            if (error instanceof APIError) {
                setError(error.message);
            } else {
                setError('Failed to update user');
            }
        }
    };

    const handleDeleteClick = (user: User) => {
        setDeleteConfirmUser(user);
        setError('');
    };

    const handleCancelDelete = () => {
        setDeleteConfirmUser(null);
        setError('');
    };

    const handleConfirmDelete = async () => {
        if (!deleteConfirmUser) return;

        try {
            const response = await fetch(`/api/auth/users/${deleteConfirmUser.id}`, {
                method: 'DELETE',
                credentials: 'include'
            });

            if (!response.ok) {
                const data = await response.json();
                throw new APIError(data.error || 'Failed to delete user', response.status);
            }

            // Refresh user list
            await fetchUsers();
            setDeleteConfirmUser(null);
        } catch (error) {
            if (error instanceof APIError) {
                setError(error.message);
            } else {
                setError('Failed to delete user');
            }
        }
    };

    const formatDate = (dateString: string) => {
        return new Date(dateString).toLocaleDateString('en-US', {
            year: 'numeric',
            month: 'short',
            day: 'numeric'
        });
    };

    if (loading) {
        return (
            <div className="min-h-screen bg-slate-50 p-8 flex items-center justify-center">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary"></div>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-slate-50 p-8">
            <div className="max-w-6xl mx-auto">
                <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-8">
                    <div className="mb-8">
                        <h1 className="text-3xl font-bold text-slate-800 mb-2">User Management</h1>
                        <p className="text-slate-600">
                            Manage user accounts - edit information or delete users.
                        </p>
                    </div>

                    {error && (
                        <div className="mb-6 p-4 bg-red-50 border border-red-200 text-red-700 rounded-lg">
                            {error}
                        </div>
                    )}

                    {/* User List Table */}
                    <div className="overflow-x-auto">
                        <table className="w-full">
                            <thead>
                                <tr className="border-b border-slate-200">
                                    <th className="text-left py-3 px-4 font-semibold text-slate-700">Username</th>
                                    <th className="text-left py-3 px-4 font-semibold text-slate-700">Email</th>
                                    <th className="text-left py-3 px-4 font-semibold text-slate-700">Full Name</th>
                                    <th className="text-left py-3 px-4 font-semibold text-slate-700">Created</th>
                                    <th className="text-right py-3 px-4 font-semibold text-slate-700">Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {users.map((user) => (
                                    <tr key={user.id} className="border-b border-slate-100 hover:bg-slate-50">
                                        <td className="py-3 px-4 font-medium text-slate-800">
                                            {user.username}
                                            {user.username === 'admin' && (
                                                <span className="ml-2 text-xs bg-blue-100 text-blue-800 px-2 py-1 rounded">Admin</span>
                                            )}
                                        </td>
                                        <td className="py-3 px-4 text-slate-600">{user.email}</td>
                                        <td className="py-3 px-4 text-slate-600">{user.full_name || '-'}</td>
                                        <td className="py-3 px-4 text-slate-600">{formatDate(user.created_at)}</td>
                                        <td className="py-3 px-4 text-right">
                                            {user.username !== 'admin' && (
                                                <div className="flex justify-end gap-2">
                                                    <button
                                                        onClick={() => handleEditClick(user)}
                                                        className="px-3 py-1 text-sm bg-blue-100 text-blue-700 rounded hover:bg-blue-200 transition-colors"
                                                    >
                                                        Edit
                                                    </button>
                                                    <button
                                                        onClick={() => handleDeleteClick(user)}
                                                        className="px-3 py-1 text-sm bg-red-100 text-red-700 rounded hover:bg-red-200 transition-colors"
                                                    >
                                                        Delete
                                                    </button>
                                                </div>
                                            )}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>

                        {users.length === 0 && (
                            <div className="text-center py-8 text-slate-500">
                                No users found
                            </div>
                        )}
                    </div>
                </div>
            </div>

            {/* Edit Modal */}
            {editingUser && (
                <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
                    <div className="bg-white rounded-xl shadow-xl max-w-md w-full p-6">
                        <h2 className="text-2xl font-bold text-slate-800 mb-4">
                            Edit User: {editingUser.username}
                        </h2>

                        <form onSubmit={handleUpdateUser} className="space-y-4">
                            <div>
                                <label className="block text-sm font-medium text-slate-700 mb-1">
                                    Email
                                </label>
                                <input
                                    type="email"
                                    value={editForm.email}
                                    onChange={(e) => setEditForm(prev => ({ ...prev, email: e.target.value }))}
                                    required
                                    className="w-full px-4 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary focus:border-primary"
                                />
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-slate-700 mb-1">
                                    Full Name
                                </label>
                                <input
                                    type="text"
                                    value={editForm.full_name}
                                    onChange={(e) => setEditForm(prev => ({ ...prev, full_name: e.target.value }))}
                                    className="w-full px-4 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary focus:border-primary"
                                />
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-slate-700 mb-1">
                                    New Password (leave empty to keep current)
                                </label>
                                <input
                                    type="password"
                                    value={editForm.password}
                                    onChange={(e) => setEditForm(prev => ({ ...prev, password: e.target.value }))}
                                    placeholder="Enter new password"
                                    className="w-full px-4 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary focus:border-primary"
                                />
                            </div>

                            <div className="flex gap-3 pt-4">
                                <button
                                    type="submit"
                                    className="flex-1 bg-primary text-white font-semibold py-2 px-4 rounded-lg hover:bg-primary-dark transition-colors"
                                >
                                    Update User
                                </button>
                                <button
                                    type="button"
                                    onClick={handleCancelEdit}
                                    className="flex-1 bg-slate-200 text-slate-700 font-semibold py-2 px-4 rounded-lg hover:bg-slate-300 transition-colors"
                                >
                                    Cancel
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}

            {/* Delete Confirmation Modal */}
            {deleteConfirmUser && (
                <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
                    <div className="bg-white rounded-xl shadow-xl max-w-md w-full p-6">
                        <h2 className="text-2xl font-bold text-red-600 mb-4">
                            Delete User
                        </h2>

                        <p className="text-slate-700 mb-6">
                            Are you sure you want to delete user <strong>{deleteConfirmUser.username}</strong>?
                            This action cannot be undone.
                        </p>

                        <div className="flex gap-3">
                            <button
                                onClick={handleConfirmDelete}
                                className="flex-1 bg-red-600 text-white font-semibold py-2 px-4 rounded-lg hover:bg-red-700 transition-colors"
                            >
                                Delete User
                            </button>
                            <button
                                onClick={handleCancelDelete}
                                className="flex-1 bg-slate-200 text-slate-700 font-semibold py-2 px-4 rounded-lg hover:bg-slate-300 transition-colors"
                            >
                                Cancel
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
