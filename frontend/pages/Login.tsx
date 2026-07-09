
import React, { useState } from 'react';
import { useAuth } from '../contexts/AuthContext';
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
        <label htmlFor={id} className="block text-sm font-medium text-slate-600 mb-1">
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
            className="w-full px-4 py-2 bg-slate-100 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-dark/50 focus:border-primary-dark"
        />
    </div>
);

export default function Login(): React.ReactNode {
    const { login } = useAuth();
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string>('');

    // Login form state
    const [loginData, setLoginData] = useState({
        username: '',
        password: '',
        rememberMe: false
    });

    const handleLogin = async (e: React.FormEvent) => {
        e.preventDefault();
        setIsLoading(true);
        setError('');

        try {
            await login({
                username: loginData.username,
                password: loginData.password
            });
        } catch (error) {
            if (error instanceof APIError) {
                setError(error.message);
            } else {
                setError('Login failed. Please try again.');
            }
            console.error('Login error:', error);
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="min-h-screen bg-slate-100 flex font-sans">
            <div className="w-1/2 hidden lg:flex flex-col items-center justify-center bg-primary text-white p-12 relative overflow-hidden">
                <div className="absolute -top-24 -left-24 w-72 h-72 bg-primary-dark/30 rounded-full"></div>
                <div className="absolute -bottom-32 -right-16 w-96 h-96 bg-primary-dark/30 rounded-full"></div>
                 <div className="z-10 text-center">
                    <div className="flex items-center justify-center text-5xl font-bold">
                        <DnaIcon />
                        <span className="ml-3">VizR</span>
                    </div>
                    <p className="mt-6 text-2xl font-light max-w-md">
                        Unlock the story of your RNA data.
                    </p>
                    <p className="mt-4 text-primary-light/80">
                        From raw sequences to insightful visualizations, seamlessly.
                    </p>
                </div>
            </div>

            <div className="w-full lg:w-1/2 flex items-center justify-center p-8">
                <div className="max-w-md w-full">
                    <div className="bg-white rounded-2xl shadow-xl p-8">
                        <h2 className="text-2xl font-bold text-slate-800 text-center mb-2">Welcome Back!</h2>
                        <p className="text-slate-500 text-center text-sm mb-6">Enter your credentials to access your account.</p>

                        {error && (
                            <div className="mb-4 p-3 bg-red-100 border border-red-400 text-red-700 rounded-lg text-sm">
                                {error}
                            </div>
                        )}

                        <form onSubmit={handleLogin} className="space-y-6">
                            <FormInput
                                id="username"
                                label="Username or Email"
                                type="text"
                                placeholder="username or email@example.com"
                                value={loginData.username}
                                onChange={(value) => setLoginData(prev => ({ ...prev, username: value }))}
                                required
                            />
                            <FormInput
                                id="password"
                                label="Password"
                                type="password"
                                placeholder="••••••••"
                                value={loginData.password}
                                onChange={(value) => setLoginData(prev => ({ ...prev, password: value }))}
                                required
                            />
                            <div className="flex items-center justify-between">
                                <div className="flex items-center">
                                    <input
                                        id="remember"
                                        name="remember"
                                        type="checkbox"
                                        checked={loginData.rememberMe}
                                        onChange={(e) => setLoginData(prev => ({ ...prev, rememberMe: e.target.checked }))}
                                        className="h-4 w-4 text-primary rounded border-slate-300 focus:ring-primary"
                                    />
                                    <label htmlFor="remember" className="ml-2 block text-sm text-slate-700">Remember me</label>
                                </div>
                            </div>
                            <button
                                type="submit"
                                disabled={isLoading || !loginData.username || !loginData.password}
                                className="w-full bg-primary text-white font-bold py-3 px-4 rounded-lg hover:bg-primary-dark transition-all duration-300 shadow-lg shadow-primary/30 disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                                {isLoading ? 'Signing In...' : 'Sign In'}
                            </button>
                        </form>
                    </div>
                </div>
            </div>
        </div>
    );
}

// Re-using the better DnaIcon from Sidebar
const DnaIcon = () => <svg xmlns="http://www.w3.org/2000/svg" className="h-12 w-12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M15.3 16.7a4.5 4.5 0 1 1-6.4 0 4.5 4.5 0 1 1 6.4 0Z"/><path d="M15.3 7.3a4.5 4.5 0 1 1-6.4 0 4.5 4.5 0 1 1 6.4 0Z"/><path d="M8.9 12A4.5 4.5 0 1 0 15.3 12"/><path d="M4.6 4.6l.9.9"/><path d="M18.5 18.5l.9.9"/><path d="M18.5 4.6l-.9.9"/><path d="M4.6 18.5l.9-.9"/></svg>;
