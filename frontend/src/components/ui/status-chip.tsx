import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from './button';

const chipVariants = cva(
  'inline-flex items-center gap-1.5 px-2 py-0.5 rounded-[4px] text-xs font-semibold uppercase tracking-wider border select-none tabular-nums',
  {
    variants: {
      status: {
        ok: 'bg-status-ok-bg text-status-ok-text border-status-ok-border',
        warning: 'bg-status-warning-bg text-status-warning-text border-status-warning-border',
        breach: 'bg-status-breach-bg text-status-breach-text border-status-breach-border',
        neutral: 'bg-surface-subtle text-text-secondary border-border',
      },
      size: {
        sm: 'text-[11px] px-1.5 py-0.2',
        md: 'text-xs px-2 py-0.5',
      },
    },
    defaultVariants: {
      status: 'neutral',
      size: 'md',
    },
  }
);

export interface StatusChipProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof chipVariants> {
  label: string;
  dot?: boolean;
}

export const StatusChip: React.FC<StatusChipProps> = ({
  status = 'neutral',
  size = 'md',
  label,
  dot = false,
  className,
  ...props
}) => {
  return (
    <span
      className={cn(chipVariants({ status, size, className }))}
      data-testid="status-chip"
      data-status={status}
      {...props}
    >
      {dot && (
        <span
          className={cn(
            'w-1.5 h-1.5 rounded-full shrink-0',
            status === 'ok' && 'bg-status-ok-text',
            status === 'warning' && 'bg-status-warning-text',
            status === 'breach' && 'bg-status-breach-text',
            status === 'neutral' && 'bg-text-secondary'
          )}
          aria-hidden="true"
        />
      )}
      <span>{label}</span>
    </span>
  );
};
