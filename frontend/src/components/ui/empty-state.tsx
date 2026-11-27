import * as React from 'react';
import { cn } from './button';

export interface EmptyStateProps {
  message: string;
  description?: string;
  className?: string;
  action?: React.ReactNode;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  message,
  description,
  className,
  action,
}) => {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center p-6 text-center border border-dashed border-border rounded-[6px] bg-surface-subtle/50 my-2',
        className
      )}
      role="status"
    >
      <p className="text-sm font-semibold text-text-primary">{message}</p>
      {description && (
        <p className="mt-1 text-xs text-text-secondary max-w-sm">{description}</p>
      )}
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
};
