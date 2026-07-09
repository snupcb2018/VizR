
import React from 'react';

interface ComingSoonModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export default function ComingSoonModal({ isOpen, onClose }: ComingSoonModalProps): React.ReactNode {
    if (!isOpen) return null;

    return (
        <div 
            className="fixed inset-0 bg-black bg-opacity-50 z-50 flex justify-center items-center p-4"
            onClick={onClose}
        >
            <div
                className="bg-white rounded-2xl shadow-xl p-8 text-center max-w-sm w-full"
                onClick={e => e.stopPropagation()}
            >
                <div className="mx-auto flex items-center justify-center h-20 w-20 rounded-full bg-primary-light mb-6">
                    <RocketIcon/>
                </div>
                <h3 className="text-2xl font-bold text-slate-800">Coming Soon!</h3>
                <p className="text-slate-500 mt-2 mb-6">
                    This feature is under active development. Stay tuned for updates!
                </p>
                <button
                    onClick={onClose}
                    className="w-full bg-primary text-white font-semibold py-3 px-4 rounded-lg hover:bg-primary-dark transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-primary-dark focus:ring-opacity-50"
                >
                    Got it, thanks!
                </button>
            </div>
        </div>
    );
}

const RocketIcon = () => <svg xmlns="http://www.w3.org/2000/svg" className="h-10 w-10 text-primary-dark" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
