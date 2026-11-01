import type { ReactNode } from "react";
import { FolderOpen, House, LogOut } from "lucide-react";
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
  const onProjects = pathname === "/" || pathname === "/projects/new";
  return (
    <div className="flex min-h-dvh flex-col">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-50 focus:rounded-md focus:bg-card focus:px-3 focus:py-2 focus:shadow-raised"
      >
        {copy.app.skipToContent}
      </a>
      <header className="sticky top-0 z-30 border-b border-border/80 bg-card/90 backdrop-blur-md supports-[backdrop-filter]:bg-card/75">
        <div className="mx-auto flex h-16 max-w-6xl items-center gap-3 px-4 sm:px-6">
          <Link to="/" aria-label={copy.app.homeLink} className="flex items-center gap-3 rounded-lg font-semibold tracking-tight transition-opacity hover:opacity-90">
            <span className="grid size-9 place-items-center rounded-xl bg-gradient-to-br from-primary to-primary-hover text-primary-foreground shadow-sm ring-1 ring-primary/20">
              <House className="size-4.5" aria-hidden="true" />
            </span>
            <div className="flex flex-col">
              <span className="text-base font-bold leading-none tracking-tight text-foreground sm:inline">
                {copy.app.name}
              </span>
              <span className="hidden text-[11px] font-medium text-muted-foreground sm:inline">
                AI Exterior Architecture
              </span>
            </div>
          </Link>
          {IS_MOCK && (
            <Badge variant="warning" title={copy.app.demoBadge} className="ml-2 font-medium">
              <span aria-hidden="true" className="xl:hidden">
                {copy.app.demoShort}
              </span>
              <span className="sr-only xl:not-sr-only">{copy.app.demoBadge}</span>
            </Badge>
          )}
          <nav className="ml-auto flex items-center gap-2" aria-label="Main">
            <Button
              variant="ghost"
              size="sm"
              asChild
              className={cn("rounded-lg px-3 py-1.5 font-medium transition-all", onProjects && "bg-secondary text-secondary-foreground")}
            >
              <Link to="/" aria-current={pathname === "/" ? "page" : undefined}>
                <FolderOpen aria-hidden="true" className="hidden size-4 sm:block" />
                {copy.nav.myProjects}
              </Link>
            </Button>
            {me.data?.email && (
              <div className="hidden items-center gap-2 rounded-full border border-border/60 bg-muted/50 px-2.5 py-1 lg:flex">
                <span className="grid size-5 place-items-center rounded-full bg-primary/10 text-[11px] font-bold text-primary">
                  {me.data.email[0].toUpperCase()}
                </span>
                <span className="max-w-40 truncate text-xs font-medium text-muted-foreground">{me.data.email}</span>
              </div>
            )}
            <Button
              variant="ghost"
              size="sm"
              className="rounded-lg text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
              disabled={logout.isPending}
              onClick={() => logout.mutate(undefined, { onSettled: () => navigate("/login") })}
            >
              <LogOut aria-hidden="true" className="size-4" />
              <span className="sr-only sm:not-sr-only">{copy.nav.logOut}</span>
            </Button>
          </nav>
        </div>
      </header>
      <main id="main" tabIndex={-1} className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 outline-none sm:px-6 sm:py-8">
        <Outlet />
      </main>
    </div>
  );
}
