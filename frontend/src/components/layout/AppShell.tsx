import { useState } from "react";
import { Sidebar } from "./Sidebar";
import { NotificationTray } from "./NotificationTray";

export function AppShell({ children }: { children: React.ReactNode }) {
  const [notifOpen, setNotifOpen] = useState(false);

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar onNotificationsClick={() => setNotifOpen(!notifOpen)} />
      <main className="flex-1 overflow-y-auto px-8 py-6">{children}</main>
      <NotificationTray open={notifOpen} onClose={() => setNotifOpen(false)} />
    </div>
  );
}
