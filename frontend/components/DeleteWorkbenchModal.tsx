import React, { useState } from 'react';

// Icons as SVG components
const ExclamationTriangleIcon = ({ className = "w-6 h-6" }: { className?: string }) => (
  <svg xmlns="http://www.w3.org/2000/svg" className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.732 16.5c-.77.833.192 2.5 1.732 2.5z" />
  </svg>
);

const TrashIcon = ({ className = "w-4 h-4" }: { className?: string }) => (
  <svg xmlns="http://www.w3.org/2000/svg" className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
  </svg>
);

const DocumentIcon = ({ className = "w-4 h-4" }: { className?: string }) => (
  <svg xmlns="http://www.w3.org/2000/svg" className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
  </svg>
);

const ChartBarIcon = ({ className = "w-4 h-4" }: { className?: string }) => (
  <svg xmlns="http://www.w3.org/2000/svg" className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
  </svg>
);

const Cog6ToothIcon = ({ className = "w-4 h-4" }: { className?: string }) => (
  <svg xmlns="http://www.w3.org/2000/svg" className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
    <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
  </svg>
);

interface DeleteWorkbenchModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: (deleteRawData: boolean) => void;
  workbenchName: string;
  isDeleting: boolean;
}

const DeleteWorkbenchModal: React.FC<DeleteWorkbenchModalProps> = ({
  isOpen,
  onClose,
  onConfirm,
  workbenchName,
  isDeleting
}) => {
  const [deleteRawData, setDeleteRawData] = useState(false);
  const [confirmationInput, setConfirmationInput] = useState('');

  if (!isOpen) return null;

  const isConfirmationValid = confirmationInput === workbenchName;

  const handleConfirm = () => {
    if (isConfirmationValid) {
      onConfirm(deleteRawData);
    }
  };

  const handleClose = () => {
    if (!isDeleting) {
      setDeleteRawData(false);
      setConfirmationInput('');
      onClose();
    }
  };

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="flex items-center justify-center min-h-screen pt-4 px-4 pb-20 text-center sm:block sm:p-0">
        {/* Background overlay - no onClick to prevent closing */}
        <div
          className="fixed inset-0 bg-gray-500 bg-opacity-75 transition-opacity"
        />

        {/* Modal panel */}
        <div className="inline-block align-bottom bg-white rounded-lg px-4 pt-5 pb-4 text-left overflow-hidden shadow-xl transform transition-all sm:my-8 sm:align-middle sm:max-w-lg sm:w-full sm:p-6">
          {/* Header */}
          <div className="sm:flex sm:items-start">
            <div className="mx-auto flex-shrink-0 flex items-center justify-center h-12 w-12 rounded-full bg-red-100 sm:mx-0 sm:h-10 sm:w-10">
              <ExclamationTriangleIcon className="h-6 w-6 text-red-600" />
            </div>
            <div className="mt-3 text-center sm:mt-0 sm:ml-4 sm:text-left">
              <h3 className="text-lg leading-6 font-medium text-gray-900">
                Delete Workbench
              </h3>
              <div className="mt-2">
                <p className="text-sm text-gray-500">
                  Are you sure you want to delete <span className="font-semibold text-gray-700">"{workbenchName}"</span>?
                </p>
              </div>
            </div>
          </div>

          {/* Warning content */}
          <div className="mt-4">
            <div className="bg-red-50 border border-red-200 rounded-md p-4">
              <div className="flex">
                <div className="flex-shrink-0">
                  <ExclamationTriangleIcon className="h-5 w-5 text-red-400" />
                </div>
                <div className="ml-3">
                  <h3 className="text-sm font-medium text-red-800">
                    Warning: This action cannot be undone!
                  </h3>
                  <div className="mt-2 text-sm text-red-700">
                    <p>The following data will be deleted:</p>
                    <ul className="mt-2 space-y-1">
                      <li className="flex items-center">
                        <ChartBarIcon className="h-4 w-4 mr-2 flex-shrink-0" />
                        Analysis results and settings
                      </li>
                      <li className="flex items-center">
                        <Cog6ToothIcon className="h-4 w-4 mr-2 flex-shrink-0" />
                        Pipeline configuration
                      </li>
                      <li className="flex items-center">
                        <DocumentIcon className="h-4 w-4 mr-2 flex-shrink-0" />
                        Sample mapping information
                      </li>
                    </ul>
                  </div>
                </div>
              </div>
            </div>

            {/* Raw data deletion option */}
            <div className="mt-4">
              <div className="bg-yellow-50 border border-yellow-200 rounded-md p-4">
                <div className="flex items-start">
                  <input
                    id="delete-raw-data"
                    type="checkbox"
                    checked={deleteRawData}
                    onChange={(e) => setDeleteRawData(e.target.checked)}
                    className="mt-0.5 h-4 w-4 text-red-600 focus:ring-red-500 border-gray-300 rounded"
                    disabled={isDeleting}
                  />
                  <div className="ml-3">
                    <label htmlFor="delete-raw-data" className="text-sm font-medium text-yellow-800">
                      Also delete uploaded raw data files
                    </label>
                    <p className="text-sm text-yellow-700 mt-1">
                      <strong>If unchecked:</strong> The workbench will be deleted, but original FASTQ files will be preserved in the <code className="bg-yellow-100 px-1 rounded text-xs">quanti/raw</code> folder.
                      <br />
                      <strong>If checked:</strong> The workbench and all files will be permanently deleted and cannot be recovered.
                    </p>
                  </div>
                </div>
              </div>
            </div>

            {/* Confirmation input */}
            <div className="mt-4">
              <label htmlFor="confirmation" className="block text-sm font-medium text-gray-700">
                Please enter the workbench name to confirm deletion:
              </label>
              <div className="mt-1">
                <input
                  id="confirmation"
                  type="text"
                  value={confirmationInput}
                  onChange={(e) => setConfirmationInput(e.target.value)}
                  placeholder={workbenchName}
                  className="shadow-sm focus:ring-red-500 focus:border-red-500 block w-full sm:text-sm border-gray-300 rounded-md"
                  disabled={isDeleting}
                />
              </div>
              {confirmationInput && !isConfirmationValid && (
                <p className="mt-1 text-sm text-red-600">
                  Workbench name does not match.
                </p>
              )}
            </div>
          </div>

          {/* Action buttons */}
          <div className="mt-6 sm:flex sm:flex-row-reverse">
            <button
              type="button"
              onClick={handleConfirm}
              disabled={!isConfirmationValid || isDeleting}
              className={`w-full inline-flex justify-center rounded-md border border-transparent shadow-sm px-4 py-2 text-base font-medium text-white focus:outline-none focus:ring-2 focus:ring-offset-2 sm:ml-3 sm:w-auto sm:text-sm ${
                !isConfirmationValid || isDeleting
                  ? 'bg-gray-400 cursor-not-allowed'
                  : 'bg-red-600 hover:bg-red-700 focus:ring-red-500'
              }`}
            >
              {isDeleting ? (
                <>
                  <svg className="animate-spin -ml-1 mr-3 h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  Deleting...
                </>
              ) : (
                <>
                  <TrashIcon className="h-4 w-4 mr-2" />
                  Delete
                </>
              )}
            </button>
            <button
              type="button"
              onClick={handleClose}
              disabled={isDeleting}
              className="mt-3 w-full inline-flex justify-center rounded-md border border-gray-300 shadow-sm px-4 py-2 bg-white text-base font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 sm:mt-0 sm:w-auto sm:text-sm disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Cancel
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default DeleteWorkbenchModal;