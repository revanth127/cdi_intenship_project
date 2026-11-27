import * as React from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { AlertTriangle, LogOut } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface SignOutConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  unsentCount: number;
  onConfirmSignOut: () => void;
}

export const SignOutConfirmDialog: React.FC<SignOutConfirmDialogProps> = ({
  open,
  onOpenChange,
  unsentCount,
  onConfirmSignOut,
}) => {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-slate-900/50 backdrop-blur-sm z-50 animate-in fade-in-0" />
        <Dialog.Content
          className="fixed left-[50%] top-[50%] z-50 w-full max-w-md translate-x-[-50%] translate-y-[-50%] rounded-[6px] bg-surface p-6 shadow-popover border border-border focus:outline-none"
          data-testid="signout-confirm-dialog"
        >
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 rounded-full bg-status-breach-bg text-status-breach-text border border-status-breach-border flex items-center justify-center shrink-0">
              <AlertTriangle className="w-5 h-5" />
            </div>
            <div>
              <Dialog.Title className="text-sm font-semibold text-text-primary tracking-tight">
                Unsent Orders Warning
              </Dialog.Title>
              <Dialog.Description className="text-xs text-text-secondary mt-0.5">
                Confirm sign out and cache purge
              </Dialog.Description>
            </div>
          </div>

          <p className="text-xs text-text-secondary leading-relaxed mb-6">
            You currently have{' '}
            <strong className="text-status-breach-text font-semibold">
              {unsentCount} unsent order{unsentCount === 1 ? '' : 's'}
            </strong>{' '}
            saved locally on this phone. Signing out will permanently erase your offline outbox and customer reference cache.
            Unsent orders cannot be recovered after sign out.
          </p>

          <div className="flex items-center justify-end gap-3">
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={() => onOpenChange(false)}
            >
              Cancel
            </Button>
            <Button
              type="button"
              variant="destructive"
              size="sm"
              onClick={() => {
                onOpenChange(false);
                onConfirmSignOut();
              }}
              className="gap-1.5"
              data-testid="confirm-signout-button"
            >
              <LogOut className="w-3.5 h-3.5" />
              <span>Erase & Sign Out</span>
            </Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
};
