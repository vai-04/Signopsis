import { lazy, Suspense, useEffect } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { useHashRoute, go } from "./hooks/useHashRoute.js";
import { Navbar, BottomNav } from "./components/Navbar.jsx";
import { Footer } from "./components/Footer.jsx";
import Intro from "./pages/Intro.jsx";
import Home from "./pages/Home.jsx";

const PAGES = {
  home: Home,
  converse: lazy(() => import("./pages/ConversePage.jsx")),
  live: lazy(() => import("./pages/LiveStage.jsx")),
  compose: lazy(() => import("./pages/ComposePage.jsx")),
  enroll: lazy(() => import("./pages/EnrollPage.jsx")),
  glance: lazy(() => import("./pages/GlancePage.jsx")),
  diagnostics: lazy(() => import("./pages/DiagnosticsPage.jsx")),
  library: lazy(() => import("./pages/Library.jsx")),
  settings: lazy(() => import("./pages/Settings.jsx")),
  privacy: lazy(() => import("./pages/Privacy.jsx")),
};
const TITLES = {
  home: "Sign ⇄ speech, without the guesswork", converse: "Converse", live: "Live stage", compose: "Compose",
  enroll: "Teach a sign", glance: "Screen Glance", diagnostics: "Diagnostics", library: "Sign library", settings: "Settings", privacy: "Privacy",
};
// app screens use the full viewport and skip the marketing footer
const APP_SCREENS = new Set(["converse", "live"]);

function Loading() {
  return (
    <div className="grid min-h-[60vh] place-items-center" role="status">
      <span className="flex items-center gap-3 font-mono text-xs font-semibold uppercase tracking-[.25em] text-mute">
        <span className="h-2.5 w-2.5 animate-pulse-soft rounded-full bg-coral" /> loading
      </span>
    </div>
  );
}

export default function App() {
  const { path, anchor } = useHashRoute();
  const Page = PAGES[path];

  useEffect(() => {
    document.title = path ? `SIGNOPSIS · ${TITLES[path] || "Not found"}` : "SIGNOPSIS";
  }, [path]);

  useEffect(() => {
    if (!path) return;
    if (anchor) {
      const t = setTimeout(() => document.getElementById(anchor)?.scrollIntoView({ behavior: "smooth", block: "start" }), 120);
      return () => clearTimeout(t);
    }
    window.scrollTo({ top: 0 });
  }, [path, anchor]);

  if (!path) return <Intro onEnter={() => go("home")} />;

  return (
    <div className="min-h-screen">
      <Navbar path={path} />
      <main id="main" tabIndex={-1} className="outline-none">
        <AnimatePresence mode="wait">
          <motion.div key={path} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} transition={{ duration: 0.28 }}>
            <Suspense fallback={<Loading />}>
              {Page ? <Page anchor={anchor} /> : <NotFound />}
            </Suspense>
          </motion.div>
        </AnimatePresence>
      </main>
      {!APP_SCREENS.has(path) && <Footer />}
      {!APP_SCREENS.has(path) && <BottomNav path={path} />}
    </div>
  );
}

function NotFound() {
  return (
    <section className="mx-auto grid min-h-[60vh] max-w-xl place-items-center px-6 text-center">
      <div>
        <p className="text-7xl">🤷</p>
        <h1 className="mt-4 text-4xl font-extrabold">That page isn't here.</h1>
        <p className="mt-2 text-mute">We'd rather say so than guess where you meant.</p>
        <a className="btn-primary mt-6" href="#/home">Go home</a>
      </div>
    </section>
  );
}
