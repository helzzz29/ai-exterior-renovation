import { useState, type ReactNode } from "react";
import {
  Folder,
  House,
  LogOut,
  Menu,
  Plus,
  X,
} from "lucide-react";
import { Link, Navigate, Outlet, useLocation, useNavigate } from "react-router";
import { useLogout, useMe, useProject } from "@/api/hooks";
import { copy } from "@/copy";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ErrorState, PageSkeleton } from "@/components/states";
import { IS_MOCK } from "@/lib/config";
import { cn } from "@/lib/utils";

export function RequireAuth({ children }: { children: ReactNode }) {
  const me = useMe();
  const location = useLocation();
  if (me.isPending) {
    return (
      <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
        <PageSkeleton />
      </div>
    );
  }
  if (me.isError) {
    return (
      <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
        <ErrorState error={me.error} onRetry={() => void me.refetch()} />
      </div>
    );
  }
  if (!me.data) {
    return <Navigate to="/login" replace state={{ from: `${location.pathname}${location.search}` }} />;
  }
  return <>{children}</>;
}

export function AppShell() {
  const me = useMe();
  const logout = useLogout();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);

  // Extract projectId if currently inside a project route: /projects/:projectId/...
  const projectMatch = pathname.match(/^\/projects\/([a-zA-Z0-9_-]+)/);
  const activeProjectId = projectMatch && projectMatch[1] !== "new" ? projectMatch[1] : null;
  const activeProject = useProject(activeProjectId ?? "");
  const onProjects = pathname === "/" || pathname === "/projects";
  const onNew = pathname === "/projects/new";

  return (
    <div className="min-h-dvh bg-background text-foreground flex flex-col font-sans">
      {/* Top Navigation Bar — Matching Reference Picture 2 */}
      <header className="sticky top-0 z-40 border-b border-border/80 bg-white/95 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
          {/* Left Brand & Primary Tabs */}
          <div className="flex items-center gap-6 lg:gap-8">
            {/* Brand Logo & Name */}
            <Link to="/" aria-label="Home Makeover Planner: my projects" className="flex items-center gap-2.5 group">
              <span className="grid size-9 place-items-center rounded-xl bg-blue-600 text-white shadow-xs transition-transform group-hover:scale-105">
                <House className="size-5" />
              </span>
              <div className="flex flex-col">
                <span className="text-base font-extrabold leading-none tracking-tight text-slate-900 uppercase">
                  Renova AI
                </span>
                <span className="text-[10px] font-semibold text-blue-600 tracking-normal mt-0.5">
                  Exterior Cost &amp; Design
                </span>
              </div>
            </Link>

            {/* Nav Tabs */}
            <nav aria-label="Main" className="hidden md:flex items-center gap-1 self-stretch pt-1">
              <Link
                to="/"
                aria-current={onProjects ? "page" : undefined}
                className={cn(
                  "relative flex items-center gap-2 px-3 py-2 text-sm font-semibold transition-colors",
                  onProjects
                    ? "text-blue-600 after:absolute after:bottom-0 after:left-2 after:right-2 after:h-0.5 after:bg-blue-600 after:rounded-full"
                    : "text-slate-600 hover:text-slate-900",
                )}
              >
                <Folder className="size-4" />
                <span>My projects</span>
              </Link>

              <Link
                to="/projects/new"
                className={cn(
                  "relative flex items-center gap-2 px-3 py-2 text-sm font-semibold transition-colors",
                  onNew
                    ? "text-blue-600 after:absolute after:bottom-0 after:left-2 after:right-2 after:h-0.5 after:bg-blue-600 after:rounded-full"
                    : "text-slate-600 hover:text-slate-900",
                )}
              >
                <Plus className="size-4" />
                <span>New Renovation</span>
              </Link>
            </nav>

            {/* Active Project Breadcrumb (if inside project) */}
            {activeProjectId && activeProject.data && (
              <div className="hidden lg:flex items-center gap-2 border-l border-slate-200 pl-4 text-xs">
                <span className="text-slate-400">Project:</span>
                <span className="font-bold text-slate-800 max-w-[180px] truncate">
                  {activeProject.data.name}
                </span>
              </div>
            )}
          </div>

          {/* Right User & Actions */}
          <div className="flex items-center gap-3">
            {IS_MOCK && (
              <Badge variant="warning" title={copy.app.demoBadge} className="hidden sm:inline-flex font-medium text-xs">
                {copy.app.demoShort}
              </Badge>
            )}

            {/* User Profile Info Pill */}
            <div className="hidden sm:flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50/80 px-3 py-1.5 text-xs text-slate-700">
              <span className="grid size-5 place-items-center rounded-full bg-blue-600 text-[10px] font-bold text-white">
                {me.data?.email ? me.data.email[0].toUpperCase() : "U"}
              </span>
              <span className="font-medium text-slate-700 max-w-[140px] truncate">
                {me.data?.email ?? "user@example.com"}
              </span>
            </div>

            {/* Sign Out Button */}
            <Button
              variant="ghost"
              size="sm"
              className="size-8 p-0 text-slate-500 hover:bg-slate-100 hover:text-slate-900"
              disabled={logout.isPending}
              onClick={() => logout.mutate(undefined, { onSettled: () => navigate("/login") })}
              title={copy.nav.logOut}
            >
              <LogOut className="size-4" />
              <span className="sr-only">{copy.nav.logOut}</span>
            </Button>

            {/* Mobile Hamburger Button */}
            <button
              type="button"
              className="rounded-lg p-2 text-slate-600 hover:bg-slate-100 md:hidden"
              onClick={() => setMobileOpen(!mobileOpen)}
              aria-label="Toggle navigation menu"
            >
              {mobileOpen ? <X className="size-5" /> : <Menu className="size-5" />}
            </button>
          </div>
        </div>

        {/* Mobile Navigation Drawer */}
        {mobileOpen && (
          <div className="border-t border-slate-200 bg-white px-4 py-3 md:hidden space-y-2 animate-in slide-in-from-top-2">
            <Link
              to="/"
              onClick={() => setMobileOpen(false)}
              className={cn(
                "flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-semibold",
                onProjects ? "bg-blue-50 text-blue-800" : "text-slate-700 hover:bg-slate-50",
              )}
            >
              <Folder className="size-4 text-blue-600" />
              <span>My projects</span>
            </Link>
            <Link
              to="/projects/new"
              onClick={() => setMobileOpen(false)}
              className={cn(
                "flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-semibold",
                onNew ? "bg-blue-50 text-blue-800" : "text-slate-700 hover:bg-slate-50",
              )}
            >
              <Plus className="size-4 text-blue-600" />
              <span>New Renovation</span>
            </Link>
            {activeProjectId && activeProject.data && (
              <div className="rounded-lg bg-slate-50 p-2.5 text-xs text-slate-700">
                <span className="text-[10px] uppercase font-bold text-slate-400">Current Project:</span>
                <p className="font-bold text-slate-900 mt-0.5 truncate">{activeProject.data.name}</p>
              </div>
            )}
            <div className="pt-2 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
              <span className="truncate">{me.data?.email}</span>
              <button
                type="button"
                onClick={() => logout.mutate(undefined, { onSettled: () => navigate("/login") })}
                className="text-red-600 font-semibold hover:underline"
              >
                Log Out
              </button>
            </div>
          </div>
        )}
      </header>

      {/* Main Page Canvas */}
      <main id="main" tabIndex={-1} className="flex-1 w-full max-w-7xl mx-auto px-4 py-6 sm:px-6 sm:py-8 lg:px-8 outline-none">
        <Outlet />
      </main>
    </div>
  );
}
