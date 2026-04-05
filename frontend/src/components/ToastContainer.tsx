// frontend/src/components/ToastContainer.tsx

import React from 'react';
import { type Toast, type ToastVariant } from '../hooks/useToast';

interface ToastContainerProps {
  toasts: Toast[];
  onDismiss: (id: number) => void;
}

const VARIANT_STYLES: Record<ToastVariant, { bg: string; icon: string; border: string }> = {
  success: { bg: '#1a2e1a', icon: '✅', border: '#22c55e' },
  error:   { bg: '#2e1a1a', icon: '🚨', border: '#ef4444' },
  warning: { bg: '#2e261a', icon: '⚠️',  border: '#f59e0b' },
  info:    { bg: '#1a1e2e', icon: 'ℹ️',  border: '#3b82f6' },
};

export const ToastContainer: React.FC<ToastContainerProps> = ({ toasts, onDismiss }) => {
  if (toasts.length === 0) return null;

  return (
    <div style={{
      position: 'fixed', bottom: '24px', right: '24px',
      display: 'flex', flexDirection: 'column', gap: '12px',
      zIndex: 9999, maxWidth: '420px', width: '100%',
    }}>
      {toasts.map(toast => {
        const style = VARIANT_STYLES[toast.variant];
        return (
          <div
            key={toast.id}
            role="alert"
            aria-live="assertive"
            style={{
              background: style.bg,
              border: `1px solid ${style.border}`,
              borderLeft: `4px solid ${style.border}`,
              borderRadius: '8px',
              padding: '12px 16px',
              display: 'flex',
              alignItems: 'flex-start',
              gap: '10px',
              color: '#f1f5f9',
              fontSize: '14px',
              lineHeight: '1.5',
              boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
              animation: 'slideIn 0.2s ease-out',
            }}
          >
            <span style={{ fontSize: '16px', flexShrink: 0, marginTop: '1px' }}>
              {style.icon}
            </span>
            <span style={{ flex: 1 }}>{toast.message}</span>
            <button
              onClick={() => onDismiss(toast.id)}
              aria-label="Dismiss notification"
              style={{
                background: 'none', border: 'none', color: '#94a3b8',
                cursor: 'pointer', fontSize: '16px', padding: '0', flexShrink: 0,
                lineHeight: 1,
              }}
            >
              ✕
            </button>
          </div>
        );
      })}
      <style>{`
        @keyframes slideIn {
          from { transform: translateX(20px); opacity: 0; }
          to   { transform: translateX(0);   opacity: 1; }
        }
      `}</style>
    </div>
  );
};
