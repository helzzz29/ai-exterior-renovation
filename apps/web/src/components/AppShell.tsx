import { useState, type ReactNode } from "react";
import { FolderOpen, House, LogOut, Menu, PlusCircle, Sparkles, X } from "lucide-react";
import { Link, Navigate, Outlet, useLocation, useNavigate } from "react-router";
import { useLogout, useMe } from "@/api/hooks";
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
    // Remember the whole address (including ?design=) so the user lands back on the same screen.
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

  const onProjects = pathname === "/" || pathname === "/projects";
  const onNew = pathname === "/projects/new";

  return (
    <div className="flex min-h-dvh bg-background text-foreground">
      {/* Mobile Backdrop */}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm md:hidden"
          onClick={() => setMobileOpen(false)}
        />
      )}

      {/* Desktop & Mobile Sidebar */}
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex w-64 flex-col border-r border-border/80 bg-card/95 transition-transform duration-300 md:translate-x-0",
          mobileOpen ? "translate-x-0" : "-translate-x-full"
        )}
      >
        {/* Brand Header */}
        <div className="flex h-16 items-center justify-between border-b border-border/80 px-5">
          <Link
            to="/"
            onClick={() => setMobileOpen(false)}
            className="flex items-center gap-3 font-semibold tracking-tight"
          >
            <span className="grid size-9 place-items-center rounded-xl bg-gradient-to-br from-primary to-primary-hover text-primary-foreground shadow-md ring-1 ring-primary/30">
              <House className="size-4.5" aria-hidden="true" />
            </span>
            <div className="flex flex-col">
              <span className="text-base font-bold leading-none tracking-tight text-foreground">
                {copy.app.name}
              </span>
              <span className="text-[10px] font-semibold uppercase tracking-wider text-primary">
                Exterior Studio
              </span>
            </div>
          </Link>
          <button
            type="button"
            className="rounded-lg p-1.5 text-muted-foreground hover:bg-muted md:hidden"
            onClick={() => setMobileOpen(false)}
            aria-label="Close sidebar"
          >
            <X className="size-5" />
          </button>
        </div>

        {/* Sidebar Navigation */}
        <div className="flex-1 space-y-6 overflow-y-auto px-3 py-4">
          <div>
            <p className="px-3 pb-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/80">
              Workspace
            </p>
            <nav className="space-y-1">
              <Link
                to="/"
                onClick={() => setMobileOpen(false)}
                className={cn(
                  "flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors",
                  onProjects
                    ? "bg-primary/10 text-primary font-semibold"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground"
                )}
              >
                <FolderOpen className="size-4.5" />
                <span>{copy.nav.myProjects}</span>
              </Link>

              <Link
                to="/projects/new"
                onClick={() => setMobileOpen(false)}
                className={cn(
                  "flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors",
                  onNew
                    ? "bg-primary/10 text-primary font-semibold"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground"
                )}
              >
                <PlusCircle className="size-4.5" />
                <span>New Project</span>
              </Link>
            </nav>
          </div>

          <div className="rounded-xl border border-primary/20 bg-gradient-to-br from-primary/5 via-card to-primary/10 p-4">
            <div className="flex items-center gap-2 text-primary">
              <Sparkles className="size-4" />
              <span className="text-xs font-bold uppercase tracking-wider">AI Powered</span>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              Instant exterior segmentation, material swapping & cost breakdowns.
            </p>
          </div>
        </div>

        {/* User Card & Logout */}
        <div className="border-t border-border/80 p-3">
          <div className="flex items-center justify-between rounded-xl bg-muted/40 p-2.5">
            <div className="flex min-w-0 items-center gap-2.5">
              <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-primary/20 text-xs font-bold text-primary">
                {me.data?.email ? me.data.email[0].toUpperCase() : "U"}
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-xs font-semibold text-foreground">
                  {me.data?.email?.split("@")[0] ?? "User"}
                </p>
                <p className="truncate text-[10px] text-muted-foreground">{me.data?.email}</p>
              </div>
            </div>
            <Button
              variant="ghost"
              size="sm"
              className="size-8 p-0 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
              disabled={logout.isPending}
              onClick={() => logout.mutate(undefined, { onSettled: () => navigate("/login") })}
              title={copy.nav.logOut}
            >
              <LogOut className="size-4" />
              <span className="sr-only">{copy.nav.logOut}</span>
            </Button>
          </div>
        </div>
      </aside>

      {/* Main Container */}
      <div className="flex min-h-dvh flex-1 flex-col md:pl-64">
        {/* Top Navbar */}
        <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-border/80 bg-card/80 px-4 backdrop-blur-md sm:px-6">
          <div className="flex items-center gap-3">
            <button
              type="button"
              className="rounded-lg p-2 text-muted-foreground hover:bg-muted md:hidden"
              onClick={() => setMobileOpen(true)}
              aria-label="Open sidebar"
            >
              <Menu className="size-5" />
            </button>
            <span className="text-sm font-medium text-muted-foreground">
              {onProjects ? "Overview" : onNew ? "New Project" : "Studio"}
            </span>
          </div>

          <div className="flex items-center gap-3">
            {IS_MOCK && (
              <Badge variant="warning" title={copy.app.demoBadge} className="font-medium">
                {copy.app.demoShort}
              </Badge>
            )}
            <div className="flex items-center gap-1.5 rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2.5 py-1 text-[11px] font-semibold text-emerald-400">
              <span className="size-1.5 rounded-full bg-emerald-400 animate-pulse" />
              System Online
            </div>
          </div>
        </header>

        {/* Page Content */}
        <main id="main" tabIndex={-1} className="flex-1 px-4 py-6 sm:px-8 sm:py-8 outline-none">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
