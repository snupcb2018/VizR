
import React, { useState } from 'react';
import { APIError } from '../services/api';

interface FormInputProps {
    id: string;
    label: string;
    type: string;
    placeholder: string;
    value: string;
    onChange: (value: string) => void;
    required?: boolean;
}

const FormInput = ({ id, label, type, placeholder, value, onChange, required = false }: FormInputProps) => (
    <div>
        <label htmlFor={id} className="block text-sm font-medium text-slate-700 mb-2">
            {label}
        </label>
        <input
            type={type}
            id={id}
            name={id}
            placeholder={placeholder}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            required={required}
            className="w-full px-4 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary focus:border-primary"
        />
    </div>
);

export default function AdminCreateUser(): React.ReactNode {
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string>('');
    const [success, setSuccess] = useState<string>('');

    const [formData, setFormData] = useState({
        username: '',
        email: '',
        fullName: '',
        password: ''
    });

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setIsLoading(true);
        setError('');
        setSuccess('');

        try {
            const response = await fetch('/api/auth/register', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                credentials: 'include',
                body: JSON.stringify({
                    username: formData.username,
                    email: formData.email,
                    full_name: formData.fullName,
                    password: formData.password
                })
            });

            const data = await response.json();

            if (!response.ok) {
                throw new APIError(response.status, data.error || 'Failed to create user');
            }

            setSuccess(`User "${formData.username}" created successfully`);

            // Reset form
            setFormData({
                username: '',
                email: '',
                fullName: '',
                password: ''
            });

        } catch (error) {
            if (error instanceof APIError) {
                setError(error.message);
            } else {
                setError('Failed to create user. Please try again.');
            }
            console.error('User creation error:', error);
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="min-h-screen bg-slate-50 p-8">
            <div className="max-w-2xl mx-auto">
                <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-8">
                    <div className="mb-8">
                        <h1 className="text-3xl font-bold text-slate-800 mb-2">Create New User</h1>
                        <p className="text-slate-600">
                            Create a new user account.
                        </p>
                    </div>

                    {error && (
                        <div className="mb-6 p-4 bg-red-50 border border-red-200 text-red-700 rounded-lg">
                            {error}
                        </div>
                    )}

                    {success && (
                        <div className="mb-6 p-4 bg-green-50 border border-green-200 text-green-700 rounded-lg">
                            {success}
                        </div>
                    )}

                    <form onSubmit={handleSubmit} className="space-y-6">
                        <FormInput
                            id="username"
                            label="Username"
                            type="text"
                            placeholder="Enter username"
                            value={formData.username}
                            onChange={(value) => setFormData(prev => ({ ...prev, username: value }))}
                            required
                        />

                        <FormInput
                            id="email"
                            label="Email Address"
                            type="email"
                            placeholder="user@example.com"
                            value={formData.email}
                            onChange={(value) => setFormData(prev => ({ ...prev, email: value }))}
                            required
                        />

                        <FormInput
                            id="fullName"
                            label="Full Name"
                            type="text"
                            placeholder="Enter full name"
                            value={formData.fullName}
                            onChange={(value) => setFormData(prev => ({ ...prev, fullName: value }))}
                        />

                        <FormInput
                            id="password"
                            label="Password"
                            type="password"
                            placeholder="Enter password"
                            value={formData.password}
                            onChange={(value) => setFormData(prev => ({ ...prev, password: value }))}
                            required
                        />

                        <div className="pt-4">
                            <button
                                type="submit"
                                disabled={isLoading || !formData.username || !formData.email || !formData.password}
                                className="w-full bg-primary text-white font-semibold py-3 px-6 rounded-lg hover:bg-primary-dark transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                                {isLoading ? 'Creating User...' : 'Create User'}
                            </button>
                        </div>
                    </form>

                    <div className="mt-6 p-4 bg-blue-50 border border-blue-200 rounded-lg">
                        <p className="text-sm text-blue-800">
                            <strong>Note:</strong> Users can change their password in Settings → User Profile.
                        </p>
                    </div>
                </div>
            </div>
        </div>
    );
}
