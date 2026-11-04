import { Component, lazy, Suspense, type ReactNode } from "react";
import { AlertTriangle } from "lucide-react";
import { Link, Route, Routes } from "react-router";
import { AppShell } from "@/components/layout/AppShell";
import { EmptyState, ErrorState, LoadingState } from "@/components/states/States";
import { Button } from "@/components/ui/button";
import { useSession } from "@/hooks/queries";

// Named exports become lazy chunks here, so charts and forms load only with the pages that use them.
const OverviewPage = lazy(() =>
  import("@/features/dashboard/OverviewPage").then((m) => ({ default: m.OverviewPage })),
);
const WeatherPage = lazy(() =>
  import("@/features/weather/WeatherPage").then((m) => ({ default: m.WeatherPage })),
);
const AssistantPage = lazy(() =>
  import("@/features/assistant/AssistantPage").then((m) => ({ default: m.AssistantPage })),
);
const IrrigationPage = lazy(() =>
  import("@/features/irrigation/IrrigationPage").then((m) => ({ default: m.IrrigationPage })),
);
const CropHealthPage = lazy(() =>
  import("@/features/crop-health/CropHealthPage").then((m) => ({ default: m.CropHealthPage })),
);
const ScenarioLabPage = lazy(() =>
  import("@/features/scenario-lab/ScenarioLabPage").then((m) => ({ default: m.ScenarioLabPage })),
);
const FarmPage = lazy(() => import("@/features/farm/FarmPage").then((m) => ({ default: m.FarmPage })));
const HistoryPage = lazy(() =>
  import("@/features/history/HistoryPage").then((m) => ({ default: m.HistoryPage })),
);
const SettingsPage = lazy(() =>
  import("@/features/settings/SettingsPage").then((m) => ({ default: m.SettingsPage })),
);
const OnboardingPage = lazy(() =>
  import("@/features/onboarding/OnboardingPage").then((m) => ({ default: m.OnboardingPage })),
);

/** Pages that store data need a session. The Scenario Lab does not, so it stays outside this. */
function Guarded({ children }: { children: ReactNode }) {
  const session = useSession();
  if (session.isPending) return <LoadingState label="Starting your session" className="p-4" />;
  if (session.isError) {
    return (
      <div className="space-y-4 p-4">
        <ErrorState
          title="FarmAgent could not start your session"
          error={session.error}
          onRetry={() => session.refetch()}
        />
        <Button variant="outline" asChild>
          <Link to="/scenario-lab">Open the Scenario Lab, which works without a session</Link>
        </Button>
      </div>
    );
  }
  return <>{children}</>;
}

class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div className="mx-auto max-w-lg p-6">
        <EmptyState
          icon={AlertTriangle}
          title="This page failed to display"
          action={<Button onClick={() => window.location.assign("/")}>Reload FarmAgent</Button>}
        >
          Your saved farms and recommendations are safe. Reloading usually fixes this.
        </EmptyState>
      </div>
    );
  }
}

function NotFound() {
  return (
    <EmptyState
      title="That page does not exist"
      action={
        <Button asChild>
          <Link to="/">Go to the overview</Link>
        </Button>
      }
    >
      The link may be out of date.
    </EmptyState>
  );
}

function guarded(page: ReactNode) {
  return <Guarded>{page}</Guarded>;
}

export default function App() {
  return (
    <ErrorBoundary>
      <Suspense fallback={<LoadingState label="Loading" className="p-6" />}>
        <Routes>
          <Route path="welcome" element={guarded(<OnboardingPage />)} />
          <Route element={<AppShell />}>
            <Route index element={guarded(<OverviewPage />)} />
            <Route path="assistant" element={guarded(<AssistantPage />)} />
            <Route path="assistant/:conversationId" element={guarded(<AssistantPage />)} />
            <Route path="weather" element={guarded(<WeatherPage />)} />
            <Route path="irrigation" element={guarded(<IrrigationPage />)} />
            <Route path="crop-health" element={guarded(<CropHealthPage />)} />
            <Route path="farm" element={guarded(<FarmPage />)} />
            <Route path="history" element={guarded(<HistoryPage />)} />
            <Route path="settings" element={guarded(<SettingsPage />)} />
            <Route path="scenario-lab" element={<ScenarioLabPage />} />
            <Route path="*" element={<NotFound />} />
          </Route>
        </Routes>
      </Suspense>
    </ErrorBoundary>
  );
}
