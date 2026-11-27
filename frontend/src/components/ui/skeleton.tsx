import * as React from 'react';
import { cn } from './button';

export function Skeleton({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn('animate-pulse rounded-[4px] bg-slate-200', className)}
      aria-hidden="true"
      {...props}
    />
  );
}
