import { type ReactNode, useState } from "react";
import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { toast, Toaster } from "sonner";
import { ApiError, errorMessage } from "@/api/client";
import { qk } from "@/api/hooks";
import { TooltipProvider } from "@/components/ui/tooltip";

/** Mutations show a friendly toast when they fail, unless the screen handles the error itself. */
declare module "@tanstack/react-query" {
  interface Register {
    mutationMeta: { silent?: boolean };
  }
}

const isSignedOut = (err: unknown) => err instanceof ApiError && err.status === 401;

export function makeQueryClient(): QueryClient {
  // A session that runs out mid-use: forget the user, so the sign-in guard sends them to the
  // login page and back to the same screen afterwards (instead of errors "Try again" can't fix).
  const signedOut = () => client.setQueryData(qk.me, null);
  const client: QueryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: (count, err) => !(err instanceof ApiError && err.status >= 400 && err.status < 500) && count < 2,
        refetchOnWindowFocus: false,
      },
    },
    queryCache: new QueryCache({
      onError: (err, query) => {
        if (isSignedOut(err) && query.queryKey[0] !== qk.me[0]) signedOut();
      },
    }),
    mutationCache: new MutationCache({
      onError: (err, _vars, _ctx, mutation) => {
        if (mutation.meta?.silent) return;
        toast.error(errorMessage(err), { id: isSignedOut(err) ? "signed-out" : undefined });
        if (isSignedOut(err)) signedOut();
      },
    }),
  });
  return client;
}

export function AppProviders({ children, client }: { children: ReactNode; client?: QueryClient }) {
  const [qc] = useState(() => client ?? makeQueryClient());
  return (
    <QueryClientProvider client={qc}>
      <TooltipProvider delayDuration={300}>
        {children}
        {/* Plain (not "rich") colours: sonner's green and red fall short of AA contrast. */}
        <Toaster
          position="top-center"
          closeButton
          toastOptions={{ className: "rounded-xl! border-border! shadow-raised!", duration: 5000 }}
        />
      </TooltipProvider>
    </QueryClientProvider>
  );
}
