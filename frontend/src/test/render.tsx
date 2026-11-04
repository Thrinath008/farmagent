import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { TooltipProvider } from "@/components/ui/tooltip";
import { FarmProvider } from "@/providers/FarmProvider";
import { tokenStore } from "@/services/api";

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location" hidden>{location.pathname}</output>;
}

function Providers({ route, children }: { route: string; children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
  });
  return (
    <QueryClientProvider client={client}>
      <TooltipProvider>
        <MemoryRouter initialEntries={[route]}>
          <FarmProvider>
            {children}
            <LocationProbe />
          </FarmProvider>
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>
  );
}

/** Renders one page with the app's real providers, as a guest who already has a session. */
export function renderPage(ui: ReactNode, { route = "/", paths = ["*"] }: { route?: string; paths?: string[] } = {}) {
  tokenStore.set("test-token");
  const result = render(
    <Providers route={route}>
      <Routes>
        {paths.map((path) => (
          <Route key={path} path={path} element={ui} />
        ))}
        {!paths.includes("*") && <Route path="*" element={<p>Another page</p>} />}
      </Routes>
    </Providers>,
  );
  return { ...result, user: userEvent.setup() };
}

/** Renders the whole app, routes and shell included. */
export function renderApp(ui: ReactNode, route: string) {
  tokenStore.set("test-token");
  return { ...render(<Providers route={route}>{ui}</Providers>), user: userEvent.setup() };
}
