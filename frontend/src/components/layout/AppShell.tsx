import { Suspense, useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  CloudSun,
  Droplets,
  FlaskConical,
  History,
  LayoutDashboard,
  Leaf,
  Map as MapIcon,
  Menu,
  MessageSquareText,
  Settings,
  Sprout,
} from "lucide-react";
import { Link, NavLink, Outlet, useLocation } from "react-router";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { SelectField } from "@/components/forms/Field";
import { Logo } from "@/components/layout/Logo";
import { LoadingState } from "@/components/states/States";
import { useFarmContext } from "@/providers/FarmProvider";
import { cn } from "@/lib/utils";

const PRIMARY_NAV = [
  { to: "/", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/assistant", label: "AI Farming Assistant", icon: MessageSquareText },
  { to: "/weather", label: "Weather Intelligence", icon: CloudSun },
  { to: "/irrigation", label: "Irrigation Advisor", icon: Droplets },
  { to: "/crop-health", label: "Crop Health & Risk", icon: Leaf },
  { to: "/farm", label: "My Farm", icon: MapIcon },
  { to: "/history", label: "Farming History", icon: History },
  { to: "/settings", label: "Settings", icon: Settings },
];

function FarmSwitcher() {
  const { farms, farm, crop, isLoading, selectFarm, selectCrop } = useFarmContext();
  if (isLoading) return null;
  if (farms.length === 0 || !farm) {
    return (
      <Link
        to="/welcome"
        className="flex items-center gap-2 rounded border border-dashed border-sidebar-border px-3 py-2.5 text-sm text-sidebar-foreground hover:bg-sidebar-accent"
      >
        <Sprout className="size-4" aria-hidden="true" /> Set up your farm
      </Link>
    );
  }
  return (
    <div className="grid gap-1.5 [&_[data-slot=select-trigger]]:border-sidebar-border [&_[data-slot=select-trigger]]:bg-sidebar-accent [&_[data-slot=select-trigger]]:text-sidebar-foreground [&_[data-slot=select-trigger]_svg]:text-sidebar-foreground/70">
      <label htmlFor="farm-switcher" className="eyebrow !text-sidebar-foreground/70">
        Farm
      </label>
      <SelectField
        id="farm-switcher"
        value={farm.id}
        onChange={selectFarm}
        options={farms.map((item) => ({
          value: item.id,
          label: item.name ?? item.location_name ?? "Unnamed farm",
        }))}
      />
      {farm.crops.length > 1 && crop && (
        <>
          <label htmlFor="crop-switcher" className="eyebrow mt-1 !text-sidebar-foreground/70">
            Crop
          </label>
          <SelectField
            id="crop-switcher"
            value={crop.id}
            onChange={selectCrop}
            options={farm.crops.map((item) => ({
              value: item.id,
              label: item.variety ? `${item.crop_name}, ${item.variety}` : item.crop_name,
            }))}
          />
        </>
      )}
    </div>
  );
}

function NavItems({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <nav aria-label="Main" className="grid gap-0.5">
      {PRIMARY_NAV.map(({ to, label, icon: Icon, end }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          onClick={onNavigate}
          className={({ isActive }) =>
            cn(
              "relative flex items-center gap-2.5 rounded px-3 py-2.5 text-sm transition-colors",
              isActive
                ? "bg-sidebar-accent font-medium text-white before:absolute before:inset-y-1.5 before:left-0 before:w-0.5 before:bg-sidebar-primary"
                : "text-sidebar-foreground/85 hover:bg-sidebar-accent/60 hover:text-white",
            )
          }
        >
          <Icon className="size-4 shrink-0" aria-hidden="true" />
          {label}
        </NavLink>
      ))}
      {/* Set apart from the working pages, because everything behind it is made-up weather. */}
      <NavLink
        to="/scenario-lab"
        onClick={onNavigate}
        className={({ isActive }) =>
          cn(
            "mt-3 flex items-center gap-2.5 rounded border border-dashed border-sidebar-border px-3 py-2.5 text-sm transition-colors",
            isActive
              ? "bg-sidebar-accent font-medium text-white"
              : "text-sidebar-foreground/85 hover:bg-sidebar-accent/60 hover:text-white",
          )
        }
      >
        <FlaskConical className="size-4 shrink-0" aria-hidden="true" />
        <span className="flex-1">Scenario Lab</span>
        <span className="font-mono text-[0.625rem] tracking-wide uppercase opacity-80">Simulated</span>
      </NavLink>
    </nav>
  );
}

function SidebarBody({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <div className="flex h-full flex-col gap-5 p-4">
      <Link to="/" onClick={onNavigate} className="flex items-center gap-2 px-1 pt-1 text-white">
        <Logo className="size-6" />
        <span className="display text-lg">FarmAgent</span>
      </Link>
      <FarmSwitcher />
      <NavItems onNavigate={onNavigate} />
    </div>
  );
}

export function AppShell() {
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    window.scrollTo?.({ top: 0 });
  }, [location.pathname]);

  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[15.5rem_minmax(0,1fr)]">
      <a
        href="#main"
        className="sr-only z-50 rounded bg-card px-3 py-2 focus:not-sr-only focus:absolute focus:top-2 focus:left-2"
      >
        Skip to content
      </a>

      <aside className="hidden bg-sidebar text-sidebar-foreground lg:block">
        <div className="sticky top-0 h-dvh overflow-y-auto">
          <SidebarBody />
        </div>
      </aside>

      <div className="sticky top-0 z-30 flex items-center gap-2 bg-sidebar px-3 py-2 text-white lg:hidden" data-print-hide>
        <Sheet open={menuOpen} onOpenChange={setMenuOpen}>
          <SheetTrigger asChild>
            <Button variant="ghost" size="icon" aria-label="Open menu" className="text-white hover:bg-sidebar-accent hover:text-white">
              <Menu aria-hidden="true" />
            </Button>
          </SheetTrigger>
          <SheetContent side="left" className="w-72 border-none bg-sidebar p-0 text-sidebar-foreground [&>button]:text-white">
            <SheetTitle className="sr-only">Menu</SheetTitle>
            <SheetDescription className="sr-only">Pages and farm selection</SheetDescription>
            <SidebarBody onNavigate={() => setMenuOpen(false)} />
          </SheetContent>
        </Sheet>
        <Link to="/" className="flex items-center gap-2">
          <Logo className="size-5" />
          <span className="display text-base">FarmAgent</span>
        </Link>
      </div>

      <main id="main" tabIndex={-1} className="min-w-0 outline-none">
        {/* Enter only. An exit animation would render the next route's page inside the outgoing
            wrapper too, mounting every page twice and losing any click made during the fade. */}
        <motion.div
          key={location.pathname.split("/")[1]}
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.14 }}
          className="mx-auto w-full max-w-[74rem] px-4 py-6 sm:px-6 lg:px-8 lg:py-8"
        >
          {/* Pages load lazily. Without this boundary a loading page suspends the whole shell, which
              hides the sidebar and leaves its farm switcher stuck on whatever it first rendered. */}
          <Suspense fallback={<LoadingState label="Loading" />}>
            <Outlet />
          </Suspense>
        </motion.div>
      </main>
    </div>
  );
}
