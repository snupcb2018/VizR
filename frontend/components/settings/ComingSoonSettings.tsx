import React from 'react';

interface ComingSoonSettingsProps {
  title: string;
  icon: string;
  description: string;
  features?: string[];
  showComingSoon: () => void;
}

const ComingSoonSettings: React.FC<ComingSoonSettingsProps> = ({
  title,
  icon,
  description,
  features = [],
  showComingSoon
}) => {
  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-slate-800 mb-2">
          {icon} {title}
        </h3>
        <p className="text-slate-600">{description}</p>
      </div>

      <div className="bg-gray-50 border border-gray-200 rounded-lg p-6">
        <h4 className="font-medium text-slate-800 mb-2">Coming Soon</h4>
        <p className="text-slate-600 mb-4">
          This feature is under development and will be available in a future update.
        </p>

        {features.length > 0 && (
          <div className="mb-4">
            <h5 className="font-medium text-slate-700 mb-2">Planned Features:</h5>
            <ul className="list-disc list-inside space-y-1">
              {features.map((feature, index) => (
                <li key={index} className="text-slate-600 text-sm">
                  {feature}
                </li>
              ))}
            </ul>
          </div>
        )}

        <button
          onClick={showComingSoon}
          className="bg-gray-500 text-white font-semibold px-4 py-2 rounded-lg hover:bg-gray-600 transition-colors"
        >
          Learn More
        </button>
      </div>
    </div>
  );
};

export default ComingSoonSettings;