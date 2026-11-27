import * as React from 'react';
import { useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { Lock, LogIn } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useAuth } from './AuthContext';
import { resumeSyncAfterAuth } from '@/lib/offline/syncEngine';

interface ReAuthDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export const ReAuthDialog: React.FC<ReAuthDialogProps> = ({ open, onOpenChange }) => {
  const { user, login } = useAuth();
  const [password, setPassword] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);

    try {
      const email = user?.email || 'salesman.a@foodmfr.local';
      await login(email, password);
      setPassword('');
      onOpenChange(false);
      // Resume sync immediately
      resumeSyncAfterAuth();
    } catch (err: any) {
      setError(err.message || 'Authentication failed. Please check your credentials.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 animate-in fade-in-0" />
        <Dialog.Content
          className="fixed left-[50%] top-[50%] z-50 w-full max-w-sm translate-x-[-50%] translate-y-[-50%] rounded-[6px] bg-surface p-6 shadow-popover border border-border focus:outline-none"
          data-testid="reauth-dialog"
        >
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 rounded-full bg-blue-50 text-blue-700 border border-blue-200 flex items-center justify-center shrink-0">
              <Lock className="w-5 h-5" />
            </div>
            <div>
              <Dialog.Title className="text-sm font-semibold text-text-primary tracking-tight">
                Session Expired
              </Dialog.Title>
              <Dialog.Description className="text-xs text-text-secondary mt-0.5">
                Sign in to resume syncing orders
              </Dialog.Description>
            </div>
          </div>

          <p className="text-xs text-text-secondary mb-4">
            Your queued orders are safely preserved on this device. Enter your password to reconnect and flush your outbox.
          </p>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-text-secondary uppercase tracking-wider mb-1">
                Account
              </label>
              <input
                type="text"
                disabled
                value={user?.email || 'salesman.a@foodmfr.local'}
                className="w-full h-8 px-2.5 rounded-[4px] border border-border bg-surface-subtle text-xs text-text-muted cursor-not-allowed"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-text-secondary uppercase tracking-wider mb-1">
                Password
              </label>
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter your password"
                className="w-full h-8 px-2.5 rounded-[4px] border border-border text-xs text-text-primary focus:outline-none focus:ring-2 focus:ring-accent"
                autoFocus
              />
            </div>

            {error && (
              <p className="text-xs text-status-breach-text" data-testid="reauth-error">
                {error}
              </p>
            )}

            <div className="flex items-center justify-end gap-2 pt-2">
              <Button
                type="submit"
                variant="primary"
                size="sm"
                disabled={isSubmitting}
                className="w-full gap-1.5"
                data-testid="reauth-submit-button"
              >
                <LogIn className="w-3.5 h-3.5" />
                <span>{isSubmitting ? 'Signing in...' : 'Sign In & Resume Sync'}</span>
              </Button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
};
