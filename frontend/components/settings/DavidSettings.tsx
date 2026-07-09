import React, { useEffect, useMemo, useState } from 'react';
import { settingsAPI, SettingsAPIError } from '../../services/settingsApi';
import { useUserSettings } from '../../contexts/UserSettingsContext';

const DAVID_REGISTER_URL = 'https://davidbioinformatics.nih.gov/webservice/register.htm';

const DavidSettings: React.FC = () => {
  const { reloadSettings } = useUserSettings();
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [email, setEmail] = useState('');
  const [originalEmail, setOriginalEmail] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState(false);

  useEffect(() => {
    const loadSettings = async () => {
      try {
        setIsLoading(true);
        setError(null);
        const goSettings = await settingsAPI.getGOSettings();
        const savedEmail = (goSettings.david_email || '').trim();
        setEmail(savedEmail);
        setOriginalEmail(savedEmail);
      } catch (err) {
        console.error('[DAVID SETTINGS] Failed to load settings:', err);
        setError('Failed to load DAVID settings. Please try again.');
      } finally {
        setIsLoading(false);
      }
    };

    void loadSettings();
  }, []);

  const hasChanges = useMemo(() => email.trim() !== originalEmail.trim(), [email, originalEmail]);

  const handleSave = async () => {
    try {
      setIsSaving(true);
      setError(null);
      setSaveSuccess(false);

      const normalizedEmail = email.trim();
      await settingsAPI.saveGOSettings({
        david_email: normalizedEmail
      });
      await reloadSettings();

      setEmail(normalizedEmail);
      setOriginalEmail(normalizedEmail);
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch (err) {
      console.error('[DAVID SETTINGS] Failed to save settings:', err);
      if (err instanceof SettingsAPIError) {
        setError(`Failed to save settings: ${err.message}`);
      } else {
        setError('Failed to save DAVID settings. Please try again.');
      }
    } finally {
      setIsSaving(false);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center p-8">
        <div className="h-8 w-8 animate-spin rounded-full border-b-2 border-blue-600" />
        <span className="ml-2 text-slate-600">Loading DAVID settings...</span>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div>
        <h3 className="mb-2 text-lg font-semibold text-slate-800">DAVID</h3>
        <p className="text-slate-600">
          Configure the registered email used for DAVID GO Enrichment.
        </p>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-700">
          {error}
        </div>
      )}

      {saveSuccess && (
        <div className="rounded-lg border border-green-200 bg-green-50 p-4 text-green-700">
          DAVID settings saved successfully.
        </div>
      )}

      <div className="rounded-lg border border-slate-200 bg-white p-6">
        <div className="mb-4 flex items-start justify-between gap-4">
          <div>
            <h4 className="text-md font-semibold text-slate-800">DAVID Registered Email</h4>
            <p className="mt-1 text-sm text-slate-600">
              To use the DAVID provider from GO Enrichment menus, you need an email address
              registered with DAVID.
            </p>
          </div>
          <a
            href={DAVID_REGISTER_URL}
            target="_blank"
            rel="noreferrer"
            className="text-sm font-medium text-blue-600 hover:text-blue-700 hover:underline"
          >
            DAVID Registration Page
          </a>
        </div>

        <div className="space-y-4">
          <div>
            <label htmlFor="davidEmail" className="mb-2 block text-sm font-medium text-slate-700">
              Email
            </label>
            <input
              id="davidEmail"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="name@example.org"
              className="w-full rounded-lg border border-slate-300 px-3 py-2 transition-colors focus:border-blue-500 focus:ring-2 focus:ring-blue-500"
            />
            <p className="mt-2 text-sm text-slate-500">
              If this field is empty, the DAVID option stays disabled in GO Enrichment submenus.
            </p>
          </div>

          <button
            type="button"
            onClick={handleSave}
            disabled={isSaving || !hasChanges}
            className={`rounded-lg px-6 py-2 font-semibold transition-colors ${
              hasChanges && !isSaving
                ? 'bg-blue-600 text-white hover:bg-blue-700'
                : 'cursor-not-allowed bg-slate-300 text-slate-500'
            }`}
          >
            {isSaving ? 'Saving...' : 'Save Settings'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default DavidSettings;
