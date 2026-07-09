import React, { useState, useEffect } from 'react';
import { apiService } from '../../services/api';

interface ReferenceSet {
  name: string;
  version: string;
  species: string;
  organism: string;
  is_default: boolean;
  total_size_mb: number;
  created_at: string;
}

interface ReferenceSettingsProps {
  showComingSoon?: () => void;
}

export default function ReferenceSettings({ showComingSoon }: ReferenceSettingsProps): React.ReactNode {
  const [references, setReferences] = useState<ReferenceSet[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showUploadForm, setShowUploadForm] = useState(false);

  // Upload form state
  const [uploadForm, setUploadForm] = useState({
    name: '',
    version: '',
    species: 'arabidopsis',
    organism: '',
    description: '',
    cdnaFile: null as File | null,
    genomicFile: null as File | null,
    gtfFile: null as File | null
  });

  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    fetchReferences();
  }, []);

  const fetchReferences = async () => {
    try {
      setLoading(true);
      const data = await apiService.getReferences();
      setReferences(data.references || []);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load references');
      console.error('Error fetching references:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleUploadFormChange = (field: string, value: any) => {
    setUploadForm(prev => ({ ...prev, [field]: value }));
  };

  const handleFileSelect = (field: string, file: File | null) => {
    setUploadForm(prev => ({ ...prev, [field]: file }));
  };

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!uploadForm.cdnaFile || !uploadForm.genomicFile || !uploadForm.gtfFile) {
      alert('Please select all required files');
      return;
    }

    try {
      setUploading(true);

      const formData = new FormData();
      formData.append('name', uploadForm.name);
      formData.append('version', uploadForm.version);
      formData.append('species', uploadForm.species);
      formData.append('organism', uploadForm.organism);
      formData.append('description', uploadForm.description);
      formData.append('cdna', uploadForm.cdnaFile);
      formData.append('genomic', uploadForm.genomicFile);
      formData.append('gtf', uploadForm.gtfFile);

      await apiService.uploadReference(formData);

      // Reset form
      setUploadForm({
        name: '',
        version: '',
        species: 'arabidopsis',
        organism: '',
        description: '',
        cdnaFile: null,
        genomicFile: null,
        gtfFile: null
      });
      setShowUploadForm(false);

      // Refresh list
      await fetchReferences();

      alert('Reference uploaded successfully!');
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Upload failed');
      console.error('Upload error:', err);
    } finally {
      setUploading(false);
    }
  };

  const handleSetDefault = async (name: string, species: string) => {
    try {
      await apiService.setDefaultReference(name, species);
      await fetchReferences();
      alert(`${name} set as default reference`);
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to set default');
      console.error('Set default error:', err);
    }
  };

  const handleDelete = async (name: string, species: string) => {
    if (!confirm(`Are you sure you want to delete reference "${name}"? This action cannot be undone.`)) {
      return;
    }

    try {
      await apiService.deleteReference(name, species);
      await fetchReferences();
      alert(`Reference "${name}" deleted successfully`);
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to delete reference');
      console.error('Delete error:', err);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h3 className="text-lg font-semibold text-slate-800">Reference Genome Management</h3>
          <p className="text-sm text-slate-500 mt-1">
            Manage reference genome sets for alignment and quantification
          </p>
        </div>
        <button
          onClick={() => setShowUploadForm(!showUploadForm)}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
        >
          {showUploadForm ? 'Cancel' : 'Upload New Reference'}
        </button>
      </div>

      {/* Error Message */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <p className="text-red-800">{error}</p>
        </div>
      )}

      {/* Upload Form */}
      {showUploadForm && (
        <form onSubmit={handleUpload} className="bg-blue-50 border border-blue-200 rounded-lg p-6 space-y-4">
          <h4 className="text-md font-semibold text-blue-900 mb-4">Upload New Reference Set</h4>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Name */}
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Reference Name <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                value={uploadForm.name}
                onChange={(e) => handleUploadFormChange('name', e.target.value)}
                placeholder="e.g., TAIR11"
                required
                className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              />
            </div>

            {/* Version */}
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Version
              </label>
              <input
                type="text"
                value={uploadForm.version}
                onChange={(e) => handleUploadFormChange('version', e.target.value)}
                placeholder="e.g., 11"
                className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              />
            </div>

            {/* Species */}
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Species <span className="text-red-500">*</span>
              </label>
              <select
                value={uploadForm.species}
                onChange={(e) => handleUploadFormChange('species', e.target.value)}
                required
                className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              >
                <option value="arabidopsis">Arabidopsis thaliana</option>
                <option value="lemna_gibba">Lemna gibba</option>
                <option value="lemna_minor">Lemna minor</option>
              </select>
            </div>

            {/* Organism */}
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Organism Name
              </label>
              <input
                type="text"
                value={uploadForm.organism}
                onChange={(e) => handleUploadFormChange('organism', e.target.value)}
                placeholder="e.g., Arabidopsis thaliana"
                className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              />
            </div>
          </div>

          {/* Description */}
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Description
            </label>
            <textarea
              value={uploadForm.description}
              onChange={(e) => handleUploadFormChange('description', e.target.value)}
              placeholder="Brief description of this reference set..."
              rows={2}
              className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>

          {/* File Uploads */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* cDNA File */}
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                cDNA FASTA <span className="text-red-500">*</span>
              </label>
              <input
                type="file"
                accept=".fa,.fasta,.fa.gz,.fasta.gz"
                onChange={(e) => handleFileSelect('cdnaFile', e.target.files?.[0] || null)}
                required
                className="w-full text-sm text-slate-500 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100"
              />
              <p className="text-xs text-slate-500 mt-1">
                {uploadForm.cdnaFile ? uploadForm.cdnaFile.name : 'For Bowtie alignment'}
              </p>
            </div>

            {/* Genomic File */}
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Genomic DNA FASTA <span className="text-red-500">*</span>
              </label>
              <input
                type="file"
                accept=".fa,.fasta,.fa.gz,.fasta.gz"
                onChange={(e) => handleFileSelect('genomicFile', e.target.files?.[0] || null)}
                required
                className="w-full text-sm text-slate-500 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100"
              />
              <p className="text-xs text-slate-500 mt-1">
                {uploadForm.genomicFile ? uploadForm.genomicFile.name : 'For HISAT2 alignment'}
              </p>
            </div>

            {/* GTF File */}
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                GTF Annotation <span className="text-red-500">*</span>
              </label>
              <input
                type="file"
                accept=".gtf,.gtf.gz"
                onChange={(e) => handleFileSelect('gtfFile', e.target.files?.[0] || null)}
                required
                className="w-full text-sm text-slate-500 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100"
              />
              <p className="text-xs text-slate-500 mt-1">
                {uploadForm.gtfFile ? uploadForm.gtfFile.name : 'For StringTie quantification'}
              </p>
            </div>
          </div>

          {/* Submit Button */}
          <div className="flex justify-end">
            <button
              type="submit"
              disabled={uploading}
              className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:bg-slate-400 disabled:cursor-not-allowed flex items-center space-x-2"
            >
              {uploading && (
                <div className="animate-spin w-4 h-4 border-2 border-white border-t-transparent rounded-full"></div>
              )}
              <span>{uploading ? 'Uploading...' : 'Upload Reference'}</span>
            </button>
          </div>
        </form>
      )}

      {/* Reference List Table */}
      <div className="bg-white border border-slate-200 rounded-lg overflow-hidden">
        <table className="w-full">
          <thead className="bg-slate-50 border-b border-slate-200">
            <tr>
              <th className="px-4 py-3 text-left text-xs font-semibold text-slate-700 uppercase">Name</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-slate-700 uppercase">Version</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-slate-700 uppercase">Species</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-slate-700 uppercase">Organism</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-slate-700 uppercase">Size</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-slate-700 uppercase">Default</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-slate-700 uppercase">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200">
            {references.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-slate-500">
                  No reference sets found. Upload your first reference to get started.
                </td>
              </tr>
            ) : (
              references.map((ref) => (
                <tr key={`${ref.species}-${ref.name}`} className="hover:bg-slate-50">
                  <td className="px-4 py-3 text-sm font-medium text-slate-800">{ref.name}</td>
                  <td className="px-4 py-3 text-sm text-slate-600">{ref.version}</td>
                  <td className="px-4 py-3 text-sm text-slate-600 capitalize">{ref.species.replace('_', ' ')}</td>
                  <td className="px-4 py-3 text-sm text-slate-600">{ref.organism}</td>
                  <td className="px-4 py-3 text-sm text-slate-600">{ref.total_size_mb.toFixed(0)} MB</td>
                  <td className="px-4 py-3">
                    {ref.is_default ? (
                      <span className="inline-flex items-center px-2 py-1 bg-green-100 text-green-800 text-xs font-medium rounded-full">
                        ✓ Default
                      </span>
                    ) : (
                      <span className="text-slate-400 text-xs">-</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center space-x-2">
                      {!ref.is_default && (
                        <button
                          onClick={() => handleSetDefault(ref.name, ref.species)}
                          className="px-3 py-1 text-xs font-medium text-blue-700 bg-blue-50 rounded hover:bg-blue-100 transition-colors"
                        >
                          Set Default
                        </button>
                      )}
                      {!ref.is_default && (
                        <button
                          onClick={() => handleDelete(ref.name, ref.species)}
                          className="px-3 py-1 text-xs font-medium text-red-700 bg-red-50 rounded hover:bg-red-100 transition-colors"
                        >
                          Delete
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Help Text */}
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
        <h4 className="text-sm font-semibold text-blue-900 mb-2">📚 Reference Set Information</h4>
        <ul className="text-sm text-blue-800 space-y-1">
          <li>• <strong>cDNA FASTA</strong>: Used by Bowtie/Bowtie2 for transcript-level alignment</li>
          <li>• <strong>Genomic DNA FASTA</strong>: Used by HISAT2 for genome-level alignment</li>
          <li>• <strong>GTF Annotation</strong>: Used by StringTie for transcript quantification</li>
          <li>• Indexes are automatically generated on first use (~30-50 minutes)</li>
          <li>• Default reference cannot be deleted</li>
        </ul>
      </div>
    </div>
  );
}
