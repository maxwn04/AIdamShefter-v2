import { QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";
import { Toaster } from "sonner";

import { queryClient } from "@/app/query-client";

export function AppProviders({
  children,
}: PropsWithChildren): React.JSX.Element {
  return (
    <QueryClientProvider client={queryClient}>
      {children}
      <Toaster richColors position="bottom-right" closeButton />
    </QueryClientProvider>
  );
}
