import React, { useState, useEffect } from 'react';
import { useAuth } from '../../contexts/AuthContext';
import { apiService, APIError } from '../../services/api';

interface ProfileSettingsProps {
  showComingSoon: () => void;
}

const ProfileSettings: React.FC<ProfileSettingsProps> = ({ showComingSoon }) => {
  const { user, checkAuth } = useAuth();

  // Profile form state
  const [email, setEmail] = useState('');
  const [fullName, setFullName] = useState('');
  const [isProfileSaving, setIsProfileSaving] = useState(false);
  const [profileMessage, setProfileMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Password form state
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [isPasswordSaving, setIsPasswordSaving] = useState(false);
  const [passwordMessage, setPasswordMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Initialize form with user data
  useEffect(() => {
    if (user) {
      setEmail(user.email || '');
      setFullName(user.full_name || '');
    }
  }, [user]);

  const handleProfileSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setProfileMessage(null);

    if (!email.trim()) {
      setProfileMessage({ type: 'error', text: 'Email is required' });
      return;
    }

    try {
      setIsProfileSaving(true);
      const response = await apiService.updateProfile({
        email: email.trim(),
        full_name: fullName.trim()
      });

      setProfileMessage({ type: 'success', text: 'Profile updated successfully' });

      // Refresh user data in context
      await checkAuth();

      // Clear success message after 3 seconds
      setTimeout(() => setProfileMessage(null), 3000);
    } catch (error) {
      if (error instanceof APIError) {
        setProfileMessage({ type: 'error', text: error.message });
      } else {
        setProfileMessage({ type: 'error', text: 'Failed to update profile' });
      }
    } finally {
      setIsProfileSaving(false);
    }
  };

  const handlePasswordSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setPasswordMessage(null);

    if (!currentPassword || !newPassword || !confirmPassword) {
      setPasswordMessage({ type: 'error', text: 'All password fields are required' });
      return;
    }

    if (newPassword !== confirmPassword) {
      setPasswordMessage({ type: 'error', text: 'New passwords do not match' });
      return;
    }

    if (newPassword.length < 6) {
      setPasswordMessage({ type: 'error', text: 'Password must be at least 6 characters' });
      return;
    }

    try {
      setIsPasswordSaving(true);
      await apiService.changePassword({
        current_password: currentPassword,
        new_password: newPassword,
        confirm_password: confirmPassword
      });

      setPasswordMessage({ type: 'success', text: 'Password changed successfully' });

      // Clear password fields
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');

      // Clear success message after 3 seconds
      setTimeout(() => setPasswordMessage(null), 3000);
    } catch (error) {
      if (error instanceof APIError) {
        setPasswordMessage({ type: 'error', text: error.message });
      } else {
        setPasswordMessage({ type: 'error', text: 'Failed to change password' });
      }
    } finally {
      setIsPasswordSaving(false);
    }
  };

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h3 className="text-lg font-semibold text-slate-800 mb-2">👤 User Profile</h3>
        <p className="text-slate-600">
          Manage your account information and security settings.
        </p>
      </div>

      {/* Account Information (Read-only) */}
      <div className="bg-slate-50 border border-slate-200 rounded-lg p-6">
        <h4 className="font-medium text-slate-800 mb-4">Account Information</h4>
        <div className="space-y-3">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Username</label>
            <input
              type="text"
              value={user?.username || ''}
              disabled
              className="w-full px-3 py-2 bg-slate-100 border border-slate-300 rounded-lg text-slate-600 cursor-not-allowed"
            />
            <p className="text-xs text-slate-500 mt-1">Username cannot be changed</p>
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Member Since</label>
            <input
              type="text"
              value={user?.created_at ? apiService.formatDate(user.created_at) : ''}
              disabled
              className="w-full px-3 py-2 bg-slate-100 border border-slate-300 rounded-lg text-slate-600 cursor-not-allowed"
            />
          </div>
        </div>
      </div>

      {/* Profile Edit Form */}
      <form onSubmit={handleProfileSubmit} className="bg-white border border-slate-200 rounded-lg p-6">
        <h4 className="font-medium text-slate-800 mb-4">Edit Profile</h4>

        {profileMessage && (
          <div className={`mb-4 p-3 rounded-lg ${
            profileMessage.type === 'success'
              ? 'bg-green-50 text-green-800 border border-green-200'
              : 'bg-red-50 text-red-800 border border-red-200'
          }`}>
            {profileMessage.text}
          </div>
        )}

        <div className="space-y-4">
          <div>
            <label htmlFor="fullName" className="block text-sm font-medium text-slate-700 mb-1">
              Full Name
            </label>
            <input
              id="fullName"
              type="text"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="Enter your full name"
              className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <div>
            <label htmlFor="email" className="block text-sm font-medium text-slate-700 mb-1">
              Email <span className="text-red-500">*</span>
            </label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              placeholder="Enter your email"
              className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <button
            type="submit"
            disabled={isProfileSaving}
            className="bg-blue-600 text-white font-semibold px-6 py-2 rounded-lg hover:bg-blue-700 transition-colors disabled:bg-blue-300 disabled:cursor-not-allowed"
          >
            {isProfileSaving ? 'Saving...' : 'Save Profile'}
          </button>
        </div>
      </form>

      {/* Password Change Form */}
      <form onSubmit={handlePasswordSubmit} className="bg-white border border-slate-200 rounded-lg p-6">
        <h4 className="font-medium text-slate-800 mb-4">Change Password</h4>

        {passwordMessage && (
          <div className={`mb-4 p-3 rounded-lg ${
            passwordMessage.type === 'success'
              ? 'bg-green-50 text-green-800 border border-green-200'
              : 'bg-red-50 text-red-800 border border-red-200'
          }`}>
            {passwordMessage.text}
          </div>
        )}

        <div className="space-y-4">
          <div>
            <label htmlFor="currentPassword" className="block text-sm font-medium text-slate-700 mb-1">
              Current Password <span className="text-red-500">*</span>
            </label>
            <input
              id="currentPassword"
              type="password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              required
              placeholder="Enter current password"
              className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <div>
            <label htmlFor="newPassword" className="block text-sm font-medium text-slate-700 mb-1">
              New Password <span className="text-red-500">*</span>
            </label>
            <input
              id="newPassword"
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              required
              placeholder="Enter new password (min 6 characters)"
              className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <div>
            <label htmlFor="confirmPassword" className="block text-sm font-medium text-slate-700 mb-1">
              Confirm New Password <span className="text-red-500">*</span>
            </label>
            <input
              id="confirmPassword"
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              required
              placeholder="Re-enter new password"
              className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <button
            type="submit"
            disabled={isPasswordSaving}
            className="bg-blue-600 text-white font-semibold px-6 py-2 rounded-lg hover:bg-blue-700 transition-colors disabled:bg-blue-300 disabled:cursor-not-allowed"
          >
            {isPasswordSaving ? 'Changing...' : 'Change Password'}
          </button>
        </div>
      </form>
    </div>
  );
};

export default ProfileSettings;
