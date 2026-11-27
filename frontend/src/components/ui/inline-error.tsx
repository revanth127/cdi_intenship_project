import * as React from 'react';
import { AlertCircle, RotateCcw } from 'lucide-react';
import { Button } from './button';
import { cn } from './button';

export interface InlineErrorProps {
  message?: string;
  onRetry?: () => void;
  className?: string;
}

export const InlineError: React.FC<InlineErrorProps> = ({
  message = 'Failed to load operational data.',
  onRetry,
  className,
}) => {
  return (
    <div
      className={cn(
        'flex items-center justify-between p-3 rounded-[6px] bg-status-breach-bg border border-status-breach-border text-status-breach-text my-2',
        className
      )}
      role="alert"
    >
      <div className="flex items-center gap-2">
        <AlertCircle className="w-4 h-4 shrink-0" aria-hidden="true" />
        <span className="text-xs font-semibold">{message}</span>
      </div>
      {onRetry && (
        <Button
          variant="secondary"
          size="sm"
          onClick={onRetry}
          className="text-xs h-7 px-2 border-status-breach-border hover:bg-white text-status-breach-text gap-1"
        >
          <RotateCcw className="w-3 h-3" />
          <span>Retry</span>
        </Button>
      )}
    </div>
  );
};
