import { NavLink, Link, useLocation } from "react-router-dom";
import {
  LayoutDashboard,
  ShieldCheck,
  Settings,
  Bell,
  BookLock,
  LogOut,
  UserCircle,
} from "lucide-react";
import { useAuth } from "@/context/AuthContext";

const MAIN_NAV = [
  { to: "/", icon: LayoutDashboard, label: "Projects" },
  { to: "/approvals", icon: ShieldCheck, label: "Clearances" },
  { to: "/policy", icon: BookLock, label: "Policy" },
];

export function Sidebar({
  onNotificationsClick,
}: {
  onNotificationsClick: () => void;
}) {
  const location = useLocation();
  const { user, logout } = useAuth();

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
        <Link to="/">
          <h1 className="font-heading text-xl font-bold tracking-widest uppercase pearl-wordart">
            PeaRL
          </h1>
        </Link>
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-4 px-3 space-y-1 overflow-y-auto">
        {MAIN_NAV.map(({ to, icon: Icon, label }) => (
          <NavLink key={to} to={to} className={navClass(to)}>
            <Icon size={16} />
            {label}
          </NavLink>
        ))}

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

        {/* User identity */}
        {user && (
          <div className="mt-2 pt-2 border-t border-slate-border">
            <div className="flex items-center gap-2 px-3 py-2 mb-1">
              <UserCircle size={15} className="text-bone-dim shrink-0" />
              <div className="min-w-0 flex-1">
                <div className="text-xs font-mono text-bone truncate">
                  {user.display_name ?? user.email ?? user.sub}
                </div>
                <div className="flex flex-wrap gap-1 mt-0.5">
                  {user.roles.map((r) => (
                    <span
                      key={r}
                      className="text-[10px] font-heading font-semibold uppercase tracking-wide text-cold-teal"
                    >
                      {r}
                    </span>
                  ))}
                </div>
              </div>
            </div>
            <button
              onClick={() => logout()}
              className="flex items-center gap-3 px-3 py-2 rounded-md text-xs font-heading font-semibold uppercase tracking-wider text-bone-dim hover:text-dried-blood-bright hover:bg-dried-blood/10 w-full text-left transition-all duration-150"
            >
              <LogOut size={13} />
              Sign Out
            </button>
          </div>
        )}
      </div>
    </aside>
  );
}
