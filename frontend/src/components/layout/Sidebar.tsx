import { NavLink, useLocation } from "react-router-dom";
import {
  LayoutDashboard,
  ShieldCheck,
  Settings,
  Bell,
  Building2,
} from "lucide-react";

const MAIN_NAV = [
  { to: "/", icon: LayoutDashboard, label: "Projects" },
  { to: "/approvals", icon: ShieldCheck, label: "Clearances" },
];

const ADMIN_NAV = [
  { to: "/admin/business-units", icon: Building2, label: "Business Units" },
];

export function Sidebar({
  onNotificationsClick,
}: {
  onNotificationsClick: () => void;
}) {
  const location = useLocation();

  function navClass(to: string) {
    const isActive =
      to === "/" ? location.pathname === "/" : location.pathname.startsWith(to);
    return `flex items-center gap-3 px-3 py-2.5 rounded-md text-sm font-heading font-semibold uppercase tracking-wider transition-all duration-150 ${
      isActive
        ? "bg-cold-teal/10 text-cold-teal border border-cold-teal/20"
        : "text-bone-muted hover:text-bone hover:bg-wet-stone border border-transparent"
    }`;
  }

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
      <nav className="flex-1 py-4 px-3 space-y-1 overflow-y-auto">
        {MAIN_NAV.map(({ to, icon: Icon, label }) => (
          <NavLink key={to} to={to} className={navClass(to)}>
            <Icon size={16} />
            {label}
          </NavLink>
        ))}

        {/* Admin section */}
        <div className="pt-3 pb-1">
          <p className="text-[9px] font-heading uppercase tracking-widest text-bone-dim px-3 mb-1">
            Administration
          </p>
          {ADMIN_NAV.map(({ to, icon: Icon, label }) => (
            <NavLink key={to} to={to} className={navClass(to)}>
              <Icon size={16} />
              {label}
            </NavLink>
          ))}
        </div>

        <NavLink to="/settings" className={navClass("/settings")}>
          <Settings size={16} />
          Configuration
        </NavLink>
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
