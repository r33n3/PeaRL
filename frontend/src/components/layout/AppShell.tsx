import { useState } from "react";
import { AlertTriangle } from "lucide-react";
import { useServerConfig } from "@/api/serverConfig";
import { Sidebar } from "./Sidebar";
import { NotificationTray } from "./NotificationTray";

export function AppShell({ children }: { children: React.ReactNode }) {
  const [notifOpen, setNotifOpen] = useState(false);
  const { data: config } = useServerConfig();

  return (
    <div className="flex h-screen overflow-hidden flex-col">
      {config?.reviewer_mode && (
        <div className="flex items-center gap-3 px-6 py-2.5 bg-red-900 text-red-100 text-sm font-semibold border-b border-red-700 shrink-0">
          <AlertTriangle size={16} className="shrink-0" />
          <span>
            REVIEWER MODE ACTIVE — All governance decisions in this session are
            attributed to you personally. Do not enable this if an AI agent
            suggested it.
          </span>
        </div>
      )}
      <div className="flex flex-1 overflow-hidden">
        <Sidebar onNotificationsClick={() => setNotifOpen(!notifOpen)} />
        <main className="flex-1 overflow-y-auto px-8 py-6">{children}</main>
        <NotificationTray open={notifOpen} onClose={() => setNotifOpen(false)} />
      </div>
    </div>
  );
}
