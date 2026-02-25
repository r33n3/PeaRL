import { NavLink, useLocation } from "react-router-dom";
import {
  LayoutDashboard,
  ShieldCheck,
  Settings,
  Bell,
} from "lucide-react";

const NAV_ITEMS = [
  { to: "/", icon: LayoutDashboard, label: "Archive Index" },
  { to: "/approvals", icon: ShieldCheck, label: "Clearances" },
  { to: "/settings", icon: Settings, label: "Configuration" },
];

export function Sidebar({
  onNotificationsClick,
}: {
  onNotificationsClick: () => void;
}) {
  const location = useLocation();

  return (
    <aside className="w-60 flex-shrink-0 bg-charcoal border-r border-slate-border flex flex-col">
      {/* Logo / Brand */}
      <div className="px-5 py-5 border-b border-slate-border">
        <h1 className="font-heading text-xl font-bold tracking-widest uppercase text-cold-teal">
          PeaRL
        </h1>
        <p className="font-mono text-[10px] text-bone-muted mt-0.5 tracking-wider">
          ARCHIVE INTERFACE v1.1
        </p>
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-4 px-3 space-y-1">
        {NAV_ITEMS.map(({ to, icon: Icon, label }) => {
          const isActive =
            to === "/" ? location.pathname === "/" : location.pathname.startsWith(to);
          return (
            <NavLink
              key={to}
              to={to}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-md text-sm font-heading font-semibold uppercase tracking-wider transition-all duration-150 ${
                isActive
                  ? "bg-cold-teal/10 text-cold-teal border border-cold-teal/20"
                  : "text-bone-muted hover:text-bone hover:bg-wet-stone border border-transparent"
              }`}
            >
              <Icon size={16} />
              {label}
            </NavLink>
          );
        })}
      </nav>

      {/* Bottom actions */}
      <div className="px-3 py-4 border-t border-slate-border space-y-1">
        <button
          onClick={onNotificationsClick}
          className="flex items-center gap-3 px-3 py-2.5 rounded-md text-sm font-heading font-semibold uppercase tracking-wider text-bone-muted hover:text-bone hover:bg-wet-stone w-full text-left transition-all duration-150"
        >
          <Bell size={16} />
          Alerts
        </button>
      </div>
    </aside>
  );
}
