import React, { useState, useEffect } from 'react';
import { settingsAPI, SettingsAPIError } from '../../services/settingsApi';

interface AIProvider {
  id: string;
  name: string;
  models: AIModel[];
}

interface AIModel {
  id: string;
  name: string;
  description?: string;
}

const AI_PROVIDERS: AIProvider[] = [
  {
    id: 'openai',
    name: 'OpenAI',
    models: [
      { id: 'gpt-4-turbo', name: 'GPT-4 Turbo', description: 'Most capable, higher cost' },
      { id: 'gpt-4o', name: 'GPT-4o', description: 'Balanced performance and cost' },
      { id: 'gpt-3.5-turbo', name: 'GPT-3.5 Turbo', description: 'Fast and cost-effective' }
    ]
  },
  {
    id: 'anthropic',
    name: 'Anthropic',
    models: [
      { id: 'claude-opus-4-1-20250805', name: 'Claude Opus 4.1', description: 'Most advanced reasoning capabilities' },
      { id: 'claude-3-7-sonnet-20250219', name: 'Claude 3.7 Sonnet', description: 'Excellent balance of capability and speed' },
      { id: 'claude-3-5-sonnet-20241022', name: 'Claude 3.5 Sonnet', description: 'Balanced performance' },
      { id: 'claude-3-haiku-20240307', name: 'Claude 3 Haiku', description: 'Fast and efficient' }
    ]
  },
  {
    id: 'google',
    name: 'Google',
    models: [
      { id: 'gemini-2.5-pro', name: 'Gemini 2.5 Pro', description: 'Advanced reasoning capabilities' },
      { id: 'gemini-flash', name: 'Gemini Flash', description: 'Fast responses' }
    ]
  }
];

const AIAnalysisSettings: React.FC = () => {
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [isTesting, setIsTesting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState(false);

  // Field-specific errors
  const [fieldErrors, setFieldErrors] = useState<{
    provider?: string;
    model?: string;
    apiKey?: string;
  }>({});

  // Form state
  const [provider, setProvider] = useState<string>('');
  const [model, setModel] = useState<string>('');
  const [apiKey, setApiKey] = useState<string>('');
  const [apiKeyConfigured, setApiKeyConfigured] = useState<boolean>(false);
  const [analysisEnabled, setAnalysisEnabled] = useState<boolean>(true); // AI Analysis global toggle
  const [featuresEnabled, setFeaturesEnabled] = useState({
    qc_analysis: true,
    deg_interpretation: true,
    pipeline_summary: false
  });

  // Original values for change detection
  const [originalValues, setOriginalValues] = useState({
    provider: '',
    model: '',
    apiKey: '',
    analysisEnabled: true,
    featuresEnabled: {
      qc_analysis: true,
      deg_interpretation: true,
      pipeline_summary: false
    }
  });

  // Connection test state
  const [testResult, setTestResult] = useState<{
    status: 'success' | 'error' | null;
    message: string;
    response_time?: number;
  }>({
    status: null,
    message: ''
  });

  // Load settings on component mount
  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    try {
      console.log('[AI SETTINGS] Starting to load settings...');
      setIsLoading(true);
      setError(null);

      const settings = await settingsAPI.getAISettings();
      console.log('[AI SETTINGS] Loaded settings from API:', settings);

      console.log('[AI SETTINGS] Raw api_key_configured value:', settings.api_key_configured, typeof settings.api_key_configured);

      setProvider(settings.provider || '');
      setModel(settings.model || '');

      const configuredValue = settings.api_key_configured || false;
      console.log('[AI SETTINGS] Setting apiKeyConfigured to:', configuredValue);
      setApiKeyConfigured(configuredValue);
      setApiKey(''); // Always start with empty input

      // Set AI Analysis enabled state - handle null/undefined as true (default enabled)
      const analysisEnabledValue = settings.analysis_enabled !== false; // null/undefined/true → true, false → false
      console.log('[AI SETTINGS] Analysis enabled value:', settings.analysis_enabled, '→', analysisEnabledValue);
      setAnalysisEnabled(analysisEnabledValue);

      const featuresEnabledValue = settings.features_enabled || {
        qc_analysis: true,
        deg_interpretation: true,
        pipeline_summary: false
      };
      setFeaturesEnabled(featuresEnabledValue);

      // Store original values for change detection
      setOriginalValues({
        provider: settings.provider || '',
        model: settings.model || '',
        apiKey: '', // API key is always empty on load
        analysisEnabled: analysisEnabledValue,
        featuresEnabled: featuresEnabledValue
      });

      console.log('[AI SETTINGS] Applied settings to state:', {
        provider: settings.provider || '',
        model: settings.model || '',
        apiKeyConfigured: configuredValue,
        analysisEnabled: analysisEnabledValue,
        featuresEnabled: featuresEnabledValue
      });

    } catch (error) {
      console.error('[AI SETTINGS] Failed to load AI settings:', error);
      setError('Failed to load settings. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  // API Key validation - simple length check
  const validateApiKey = (key: string) => {
    // Clear previous API key error
    setFieldErrors(prev => {
      const { apiKey, ...rest } = prev;
      return rest;
    });

    // Simple validation: if no key provided and none configured, show error
    if (!key.trim() && !apiKeyConfigured) {
      setFieldErrors(prev => ({
        ...prev,
        apiKey: 'API key is required'
      }));
      return false;
    }

    return true;
  };

  const handleSave = async () => {
    try {
      setIsSaving(true);
      setError(null);
      setSaveSuccess(false);

      const hasAIChanges =
        provider !== originalValues.provider ||
        model !== originalValues.model ||
        apiKey.trim() !== originalValues.apiKey ||
        analysisEnabled !== originalValues.analysisEnabled ||
        JSON.stringify(featuresEnabled) !== JSON.stringify(originalValues.featuresEnabled);
      let hasErrors = false;
      if (!provider) {
        setFieldErrors(prev => ({ ...prev, provider: 'Please select an AI provider' }));
        hasErrors = true;
      } else {
        setFieldErrors(prev => {
          const { provider, ...rest } = prev;
          return rest;
        });
      }

      if (!model) {
        setFieldErrors(prev => ({ ...prev, model: 'Please select a model' }));
        hasErrors = true;
      } else {
        setFieldErrors(prev => {
          const { model, ...rest } = prev;
          return rest;
        });
      }

      if (!validateApiKey(apiKey)) {
        hasErrors = true;
      }

      if (hasErrors || !hasAIChanges) {
        return;
      }

      const settings: any = {
        provider,
        model,
        analysis_enabled: analysisEnabled,
        features_enabled: featuresEnabled
      };

      // Only include API key if user entered a new one
      if (apiKey.trim()) {
        settings.api_key = apiKey;
      }

      await settingsAPI.saveAISettings(settings);

      setSaveSuccess(true);
      // If user entered new API key, update the configured state
      if (apiKey.trim()) {
        setApiKeyConfigured(true);
        setApiKey(''); // Clear input after successful save
      }

      // Update original values after successful save
      setOriginalValues({
        provider,
        model,
        apiKey: '', // API key is cleared after save
        analysisEnabled,
        featuresEnabled
      });

      // Clear success message after 3 seconds
      setTimeout(() => setSaveSuccess(false), 3000);

    } catch (error) {
      console.error('Failed to save AI settings:', error);
      if (error instanceof SettingsAPIError) {
        setError(`Failed to save settings: ${error.message}`);
      } else {
        setError('Failed to save settings. Please try again.');
      }
    } finally {
      setIsSaving(false);
    }
  };

  const handleTestConnection = async () => {
    try {
      setIsTesting(true);
      setTestResult({ status: null, message: '' });

      // Validate required fields for testing
      if (!provider) {
        setTestResult({
          status: 'error',
          message: 'Please select an AI provider first.'
        });
        return;
      }

      if (!model) {
        setTestResult({
          status: 'error',
          message: 'Please select a model first.'
        });
        return;
      }

      // Use current API key input or fall back to configured key
      const keyToTest = apiKey.trim() || (apiKeyConfigured ? 'use_configured' : '');

      if (!keyToTest) {
        setTestResult({
          status: 'error',
          message: 'Please enter an API key to test.'
        });
        return;
      }

      // Test with current form values (not saved values)
      const result = await settingsAPI.testAIConnection({
        provider,
        model,
        api_key: keyToTest === 'use_configured' ? null : apiKey.trim() // null means use configured key
      });

      setTestResult({
        status: result.status,
        message: result.message,
        response_time: result.response_time
      });

    } catch (error) {
      console.error('Connection test failed:', error);
      setTestResult({
        status: 'error',
        message: error instanceof SettingsAPIError ? error.message : 'Connection test failed'
      });
    } finally {
      setIsTesting(false);
    }
  };

  const selectedProvider = AI_PROVIDERS.find(p => p.id === provider);
  const availableModels = selectedProvider?.models || [];

  // Check if save button should be enabled
  const isSaveButtonEnabled = () => {
    const hasAIChanges = (
      provider !== originalValues.provider ||
      model !== originalValues.model ||
      apiKey.trim() !== originalValues.apiKey ||
      analysisEnabled !== originalValues.analysisEnabled ||
      JSON.stringify(featuresEnabled) !== JSON.stringify(originalValues.featuresEnabled)
    );
    if (!hasAIChanges) {
      return false;
    }

    if (!provider || !model) {
      return false;
    }

    if (!apiKeyConfigured && !apiKey.trim()) {
      return false;
    }

    return true;
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center p-8">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
        <span className="ml-2 text-slate-600">Loading AI settings...</span>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div>
        <h3 className="text-lg font-semibold text-slate-800 mb-2">🤖 AI Analysis Settings</h3>
        <p className="text-slate-600">
          Configure AI providers for automated analysis of your RNA-seq results.
        </p>
      </div>

      {/* AI Analysis Global Toggle */}
      <div className="bg-blue-50 p-4 rounded-lg border border-blue-200">
        <div className="flex items-center justify-between">
          <div>
            <h4 className="text-md font-semibold text-slate-800">Enable AI Analysis</h4>
            <p className="text-sm text-slate-600 mt-1">
              Turn AI analysis features on or off for your RNA-seq workflows.
            </p>
          </div>
          <label className="relative inline-flex items-center cursor-pointer">
            <input
              type="checkbox"
              checked={analysisEnabled}
              onChange={(e) => setAnalysisEnabled(e.target.checked)}
              className="sr-only"
            />
            <div className={`w-11 h-6 rounded-full transition-colors ${
              analysisEnabled ? 'bg-blue-600' : 'bg-gray-300'
            }`}>
              <div className={`w-4 h-4 bg-white rounded-full mt-1 transition-transform ${
                analysisEnabled ? 'translate-x-6' : 'translate-x-1'
              }`} />
            </div>
          </label>
        </div>
      </div>

      {/* Error Message */}
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 p-4 rounded-lg">
          {error}
        </div>
      )}

      {/* Success Message */}
      {saveSuccess && (
        <div className="bg-green-50 border border-green-200 text-green-700 p-4 rounded-lg">
          Settings saved successfully!
        </div>
      )}

      {/* AI Provider Configuration Section */}
      <div className={`p-6 rounded-lg border transition-colors ${
        analysisEnabled ? 'bg-slate-50' : 'bg-gray-100'
      }`}>
        <h4 className={`text-md font-semibold mb-4 ${
          analysisEnabled ? 'text-slate-800' : 'text-gray-500'
        }`}>AI Provider Configuration</h4>

        {/* Provider Selection */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <label className={`block text-sm font-medium ${
            analysisEnabled ? 'text-slate-700' : 'text-gray-500'
          }`}>
            AI Provider
          </label>
          {fieldErrors.provider && (
            <span className="text-red-600 text-sm font-medium">
              ⚠️ {fieldErrors.provider}
            </span>
          )}
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {AI_PROVIDERS.map((prov) => (
            <label
              key={prov.id}
              className={`relative flex items-center p-4 border rounded-lg transition-colors ${
                analysisEnabled
                  ? 'cursor-pointer hover:bg-gray-50'
                  : 'cursor-not-allowed bg-gray-50'
              } ${
                provider === prov.id && analysisEnabled
                  ? 'border-blue-500 bg-blue-50'
                  : analysisEnabled
                    ? 'border-gray-200'
                    : 'border-gray-300'
              }`}
            >
              <input
                type="radio"
                name="provider"
                value={prov.id}
                checked={provider === prov.id}
                disabled={!analysisEnabled}
                onChange={(e) => {
                  if (analysisEnabled) {
                    setProvider(e.target.value);
                    setModel(''); // Reset model when provider changes
                    setApiKey(''); // Reset API key when provider changes
                    setApiKeyConfigured(false); // Reset configured status
                    // Clear provider and model errors when selection is made
                    setFieldErrors(prev => {
                      const { provider, model, ...rest } = prev;
                      return rest;
                    });
                  }
                }}
                className="sr-only"
              />
              <div className="flex-1">
                <div className={`font-medium ${
                  analysisEnabled ? 'text-slate-900' : 'text-gray-500'
                }`}>{prov.name}</div>
                <div className={`text-sm ${
                  analysisEnabled ? 'text-slate-500' : 'text-gray-400'
                }`}>
                  {prov.models.length} models available
                </div>
              </div>
              {provider === prov.id && analysisEnabled && (
                <div className="absolute top-2 right-2 text-blue-500">
                  ✓
                </div>
              )}
            </label>
          ))}
        </div>
      </div>

      {/* Model Selection */}
      {provider && (
        <div>
          <div className="flex items-center justify-between mb-3">
            <label className={`block text-sm font-medium ${
              analysisEnabled ? 'text-slate-700' : 'text-gray-500'
            }`}>
              Model
            </label>
            {fieldErrors.model && (
              <span className="text-red-600 text-sm font-medium">
                ⚠️ {fieldErrors.model}
              </span>
            )}
          </div>
          <div className="space-y-2">
            {availableModels.map((modelOption) => (
              <label
                key={modelOption.id}
                className={`flex items-center p-3 border rounded-lg transition-colors ${
                  analysisEnabled
                    ? 'cursor-pointer hover:bg-gray-50'
                    : 'cursor-not-allowed bg-gray-50'
                } ${
                  model === modelOption.id && analysisEnabled
                    ? 'border-blue-500 bg-blue-50'
                    : analysisEnabled
                      ? 'border-gray-200'
                      : 'border-gray-300'
                }`}
              >
                <input
                  type="radio"
                  name="model"
                  value={modelOption.id}
                  checked={model === modelOption.id}
                  disabled={!analysisEnabled}
                  onChange={(e) => {
                    if (analysisEnabled) {
                      setModel(e.target.value);
                      // Clear model error when selection is made
                      setFieldErrors(prev => {
                        const { model, ...rest } = prev;
                        return rest;
                      });
                    }
                  }}
                  className="sr-only"
                />
                <div className="flex-1">
                  <div className={`font-medium ${
                    analysisEnabled ? 'text-slate-900' : 'text-gray-500'
                  }`}>{modelOption.name}</div>
                  {modelOption.description && (
                    <div className={`text-sm ${
                      analysisEnabled ? 'text-slate-500' : 'text-gray-400'
                    }`}>{modelOption.description}</div>
                  )}
                </div>
                {model === modelOption.id && analysisEnabled && (
                  <div className="text-blue-500">✓</div>
                )}
              </label>
            ))}
          </div>
        </div>
      )}

      {/* API Key Input */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <label htmlFor="apiKey" className={`block text-sm font-medium ${
            analysisEnabled ? 'text-slate-700' : 'text-gray-500'
          }`}>
            API Key <span className="text-red-500">*</span>
          </label>
          {fieldErrors.apiKey && (
            <span className="text-red-600 text-sm font-medium">
              ⚠️ {fieldErrors.apiKey}
            </span>
          )}
        </div>
        <div className="relative">
          <input
            type="password"
            id="apiKey"
            value={apiKey}
            disabled={!analysisEnabled}
            onChange={(e) => {
              if (analysisEnabled) {
                const newValue = e.target.value;
                setApiKey(newValue);
                // Real-time validation
                validateApiKey(newValue);
              }
            }}
            onBlur={() => {
              if (analysisEnabled) {
                // Validate on blur
                validateApiKey(apiKey);
              }
            }}
            placeholder={
              !analysisEnabled
                ? "Enable AI Analysis to configure API key"
                : apiKeyConfigured && !apiKey
                  ? "API key is configured. Enter new key to replace it."
                  : "Enter your API key"
            }
            className={`w-full px-3 py-2 border rounded-lg transition-colors ${
              analysisEnabled
                ? 'focus:ring-2 focus:ring-blue-500 focus:border-blue-500'
                : 'bg-gray-100 cursor-not-allowed'
            } ${
              fieldErrors.apiKey && analysisEnabled
                ? 'border-red-300 focus:ring-red-500 focus:border-red-500'
                : analysisEnabled
                  ? 'border-gray-300'
                  : 'border-gray-300'
            }`}
          />
          {apiKeyConfigured && !apiKey && analysisEnabled && (
            <div className="absolute right-2 top-2 text-green-500 text-sm">
              ✓ Configured
            </div>
          )}
        </div>
        <p className={`mt-1 text-sm ${
          analysisEnabled ? 'text-slate-500' : 'text-gray-400'
        }`}>
          Your API key is encrypted and stored securely. It will not be visible after saving.
        </p>
      </div>

      {/* Connection Test */}
      <div>
        <div className="mb-3">
          <h5 className={`text-sm font-medium mb-1 ${
            analysisEnabled ? 'text-slate-700' : 'text-gray-500'
          }`}>Connection Test</h5>
          <p className={`text-sm ${
            analysisEnabled ? 'text-slate-500' : 'text-gray-400'
          }`}>
            Test the connection to your selected AI provider using the saved configuration.
          </p>
        </div>

        <button
          onClick={handleTestConnection}
          disabled={!analysisEnabled || isTesting || (!apiKeyConfigured && !apiKey)}
          className={`px-4 py-2 rounded-lg transition-colors ${
            analysisEnabled
              ? 'bg-blue-600 text-white hover:bg-blue-700'
              : 'bg-gray-300 text-gray-500 cursor-not-allowed'
          } disabled:opacity-50 disabled:cursor-not-allowed`}
        >
          {isTesting ? 'Testing Connection...' : 'Test Connection'}
        </button>

        {!analysisEnabled && (
          <p className="mt-2 text-sm text-gray-500">
            ℹ️ Enable AI Analysis to test connection.
          </p>
        )}

        {analysisEnabled && (!apiKeyConfigured && !apiKey) && (
          <p className="mt-2 text-sm text-amber-600">
            ⚠️ Please configure and save an API key first to test the connection.
          </p>
        )}

        {testResult.status && (
          <div className={`mt-3 p-3 rounded-lg border ${
            testResult.status === 'success'
              ? 'bg-green-50 border-green-200 text-green-700'
              : 'bg-red-50 border-red-200 text-red-700'
          }`}>
            <div className="flex items-center">
              <span className="text-lg mr-2">
                {testResult.status === 'success' ? '✅' : '❌'}
              </span>
              <div>
                <div className="font-medium">{testResult.message}</div>
                {testResult.response_time && (
                  <div className="text-sm opacity-75">
                    Response time: {testResult.response_time.toFixed(2)}s
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
        </div>
      </div>


      {/* Enabled Features Section */}
      <div className={`p-6 rounded-lg border transition-colors ${
        analysisEnabled ? 'bg-slate-50' : 'bg-gray-100'
      }`}>
        <h4 className={`text-md font-semibold mb-4 ${
          analysisEnabled ? 'text-slate-800' : 'text-gray-500'
        }`}>Enabled Features</h4>
        <div className="space-y-3">
          <label className={`flex items-center ${
            analysisEnabled ? 'cursor-pointer' : 'cursor-not-allowed'
          }`}>
            <input
              type="checkbox"
              checked={featuresEnabled.qc_analysis}
              disabled={!analysisEnabled}
              onChange={(e) => {
                if (analysisEnabled) {
                  setFeaturesEnabled(prev => ({
                    ...prev,
                    qc_analysis: e.target.checked
                  }));
                }
              }}
              className={`h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded ${
                !analysisEnabled ? 'opacity-50 cursor-not-allowed' : ''
              }`}
            />
            <span className={`ml-2 text-sm ${
              analysisEnabled ? 'text-slate-700' : 'text-gray-500'
            }`}>
              QC Report Analysis - AI interpretation of FastQC results
            </span>
          </label>

          <label className={`flex items-center ${
            analysisEnabled ? 'cursor-pointer' : 'cursor-not-allowed'
          }`}>
            <input
              type="checkbox"
              checked={featuresEnabled.deg_interpretation}
              disabled={!analysisEnabled}
              onChange={(e) => {
                if (analysisEnabled) {
                  setFeaturesEnabled(prev => ({
                    ...prev,
                    deg_interpretation: e.target.checked
                  }));
                }
              }}
              className={`h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded ${
                !analysisEnabled ? 'opacity-50 cursor-not-allowed' : ''
              }`}
            />
            <span className={`ml-2 text-sm ${
              analysisEnabled ? 'text-slate-700' : 'text-gray-500'
            }`}>
              DEG Result Interpretation - Summary of differential expression analysis
            </span>
          </label>

          <label className={`flex items-center ${
            analysisEnabled ? 'cursor-pointer' : 'cursor-not-allowed'
          }`}>
            <input
              type="checkbox"
              checked={featuresEnabled.pipeline_summary}
              disabled={!analysisEnabled}
              onChange={(e) => {
                if (analysisEnabled) {
                  setFeaturesEnabled(prev => ({
                    ...prev,
                    pipeline_summary: e.target.checked
                  }));
                }
              }}
              className={`h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded ${
                !analysisEnabled ? 'opacity-50 cursor-not-allowed' : ''
              }`}
            />
            <span className={`ml-2 text-sm ${
              analysisEnabled ? 'text-slate-700' : 'text-gray-500'
            }`}>
              Pipeline Summary - Overall analysis workflow summary
            </span>
          </label>
        </div>
      </div>

      {/* Save Button */}
      <div className="pt-4 border-t">
        <button
          onClick={handleSave}
          disabled={isSaving || !isSaveButtonEnabled()}
          className={`px-6 py-2 rounded-lg transition-colors ${
            isSaveButtonEnabled() && !isSaving
              ? 'bg-green-600 text-white hover:bg-green-700'
              : 'bg-gray-300 text-gray-500 cursor-not-allowed'
          } disabled:opacity-50 disabled:cursor-not-allowed`}
        >
          {isSaving ? 'Saving...' : 'Save Settings'}
        </button>

        {!isSaveButtonEnabled() && !isSaving && (
          <p className="mt-2 text-sm text-gray-500">
            {provider !== originalValues.provider || model !== originalValues.model || apiKey.trim() !== originalValues.apiKey || analysisEnabled !== originalValues.analysisEnabled || JSON.stringify(featuresEnabled) !== JSON.stringify(originalValues.featuresEnabled)
              ? (!provider || !model || (!apiKeyConfigured && !apiKey.trim())
                ? 'Please fill in all required fields (Provider, Model, API Key)'
                : 'No changes to save')
              : davidEmail.trim() === originalValues.davidEmail.trim()
                ? 'No changes to save'
                : 'No changes to save'}
          </p>
        )}
      </div>
    </div>
  );
};

export default AIAnalysisSettings;
