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
      <header className="sticky top-0 z-30 border-b bg-card/90 backdrop-blur supports-[backdrop-filter]:bg-card/80">
        <div className="mx-auto flex h-14 max-w-6xl items-center gap-3 px-4 sm:px-6">
          <Link to="/" aria-label={copy.app.homeLink} className="flex items-center gap-2.5 rounded-md font-semibold tracking-tight">
            <span className="grid size-8 place-items-center rounded-lg bg-primary text-primary-foreground shadow-sm">
              <House className="size-4" aria-hidden="true" />
            </span>
            <span className="hidden whitespace-nowrap sm:inline" aria-hidden="true">
              {copy.app.name}
            </span>
          </Link>
          {IS_MOCK && (
            <Badge variant="warning" title={copy.app.demoBadge}>
              <span aria-hidden="true" className="xl:hidden">
                {copy.app.demoShort}
              </span>
              <span className="sr-only xl:not-sr-only">{copy.app.demoBadge}</span>
            </Badge>
          )}
          <nav className="ml-auto flex items-center gap-1" aria-label="Main">
            <Button
              variant="ghost"
              size="sm"
              asChild
              className={cn(onProjects && "bg-accent text-accent-foreground")}
            >
              <Link to="/" aria-current={pathname === "/" ? "page" : undefined}>
                <FolderOpen aria-hidden="true" className="hidden sm:block" />
                {copy.nav.myProjects}
              </Link>
            </Button>
            <span className="hidden max-w-48 truncate px-2 text-sm text-muted-foreground lg:inline">{me.data?.email}</span>
            <Button
              variant="ghost"
              size="sm"
              disabled={logout.isPending}
              onClick={() => logout.mutate(undefined, { onSettled: () => navigate("/login") })}
            >
              <LogOut aria-hidden="true" />
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
