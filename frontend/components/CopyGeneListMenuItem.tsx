import React from 'react';

interface CopyGeneListMenuItemProps {
  genes: string[];
  onCopied?: () => void;
  className?: string;
}

const fallbackCopyText = (text: string) => {
  const textarea = document.createElement('textarea');
  textarea.value = text;
  textarea.setAttribute('readonly', 'true');
  textarea.style.position = 'absolute';
  textarea.style.left = '-9999px';
  document.body.appendChild(textarea);
  textarea.select();
  document.execCommand('copy');
  document.body.removeChild(textarea);
};

const CopyGeneListMenuItem: React.FC<CopyGeneListMenuItemProps> = ({
  genes,
  onCopied,
  className = '',
}) => {
  const handleCopy = async () => {
    const text = genes.join('\n');
    if (!text) {
      return;
    }

    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
      } else {
        fallbackCopyText(text);
      }
      onCopied?.();
    } catch (error) {
      console.error('[COPY-GENE-LIST] Failed to copy selected genes:', error);
    }
  };

  return (
    <button
      type="button"
      onClick={() => {
        void handleCopy();
      }}
      className={`block w-full px-4 py-2 text-left text-sm text-slate-700 hover:bg-slate-100 ${className}`}
    >
      Copy to Clipboard
    </button>
  );
};

export default CopyGeneListMenuItem;
