import { X } from "lucide-react";
import { useNotifications, useMarkNotificationRead } from "@/api/dashboard";
import { formatRelativeTime } from "@/lib/utils";

export function NotificationTray({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const { data: notifications } = useNotifications();
  const markRead = useMarkNotificationRead();

  if (!open) return null;

  return (
    <div className="w-80 flex-shrink-0 bg-charcoal border-l border-slate-border flex flex-col overflow-hidden">
      <div className="flex items-center justify-between px-4 py-4 border-b border-slate-border">
        <h2 className="vault-heading text-sm">Alerts</h2>
        <button onClick={onClose} className="text-bone-muted hover:text-bone">
          <X size={16} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        {!notifications?.length ? (
          <p className="px-4 py-8 text-center text-bone-dim text-sm font-mono">
            No unread alerts
          </p>
        ) : (
          <div className="divide-y divide-slate-border">
            {notifications.map((n) => (
              <button
                key={n.notification_id}
                onClick={() => markRead.mutate(n.notification_id)}
                className="w-full text-left px-4 py-3 hover:bg-wet-stone transition-colors"
              >
                <div className="flex items-center gap-2 mb-1">
                  <span
                    className={`w-1.5 h-1.5 rounded-full ${
                      n.severity === "critical"
                        ? "bg-dried-blood-bright"
                        : n.severity === "warning"
                          ? "bg-clinical-cyan"
                          : "bg-cold-teal"
                    }`}
                  />
                  <span className="text-xs font-heading uppercase tracking-wider text-bone-muted">
                    {n.event_type.replace(".", " ")}
                  </span>
                </div>
                <p className="text-sm text-bone leading-snug">{n.title}</p>
                <p className="text-xs text-bone-dim mt-1 font-mono">
                  {formatRelativeTime(n.created_at)}
                </p>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
