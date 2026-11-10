import React from 'react';

export const TableSkeleton: React.FC<{ rows?: number }> = ({ rows = 6 }) => {
  return (
    <div className="w-full divide-y divide-neutral-100 animate-pulse">
      {Array.from({ length: rows }).map((_, idx) => (
        <div key={idx} className="flex items-center justify-between py-4 px-6 gap-4">
          <div className="flex items-center gap-3 w-1/4">
            <div className="h-8 w-8 rounded-lg bg-neutral-200 shrink-0" />
            <div className="space-y-1.5 w-full">
              <div className="h-3.5 bg-neutral-200 rounded w-3/4" />
              <div className="h-2.5 bg-neutral-100 rounded w-1/2" />
            </div>
          </div>
          <div className="h-3.5 bg-neutral-200 rounded w-24" />
          <div className="h-3.5 bg-neutral-100 rounded w-20" />
          <div className="h-3.5 bg-neutral-200 rounded w-24" />
          <div className="h-6 bg-neutral-200 rounded-full w-24" />
          <div className="h-3.5 bg-neutral-100 rounded w-20" />
        </div>
      ))}
    </div>
  );
};

export const StatTileSkeleton: React.FC = () => {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3 animate-pulse">
      {Array.from({ length: 4 }).map((_, idx) => (
        <div key={idx} className="p-4 rounded-xl border border-neutral-200 bg-white space-y-2">
          <div className="h-3 bg-neutral-200 rounded w-1/2" />
          <div className="h-6 bg-neutral-300 rounded w-1/3" />
        </div>
      ))}
    </div>
  );
};
