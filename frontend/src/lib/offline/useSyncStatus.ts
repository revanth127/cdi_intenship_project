import { useState, useEffect } from 'react';
import { getSyncStatus, flushOutbox } from './syncEngine';
import type { SyncEngineStatus } from './types';

export function useSyncStatus(): {
  status: SyncEngineStatus;
  triggerSync: () => Promise<void>;
} {
  const [status, setStatus] = useState<SyncEngineStatus>({
    isOnline: typeof navigator !== 'undefined' ? navigator.onLine : true,
    isSyncing: false,
    isPausedForAuth: false,
    queuedCount: 0,
    sendingCount: 0,
    needsAttentionCount: 0,
    totalPendingCount: 0,
  });

  useEffect(() => {
    let isMounted = true;

    const refreshStatus = () => {
      getSyncStatus().then((s) => {
        if (isMounted) setStatus(s);
      });
    };

    refreshStatus();

    const handleSyncStatusChanged = (e: any) => {
      if (isMounted && e.detail) {
        setStatus(e.detail);
      } else {
        refreshStatus();
      }
    };

    window.addEventListener('sync:status-changed', handleSyncStatusChanged);
    window.addEventListener('online', refreshStatus);
    window.addEventListener('offline', refreshStatus);

    return () => {
      isMounted = false;
      window.removeEventListener('sync:status-changed', handleSyncStatusChanged);
      window.removeEventListener('online', refreshStatus);
      window.removeEventListener('offline', refreshStatus);
    };
  }, []);

  return {
    status,
    triggerSync: flushOutbox,
  };
}
