import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Menu, X, ArrowRight, MessageSquare, Presentation, PenLine, BookOpen, Settings, Home, GraduationCap, ScanEye, Activity, ShieldCheck } from "lucide-react";
import { Logo } from "./Brand.jsx";
import { ModeBadge } from "./Bits.jsx";
import { go } from "../hooks/useHashRoute.js";
import { cx } from "../utils/cx.js";

export const NAV = [
  { path: "converse", label: "Converse", Icon: MessageSquare },
  { path: "live", label: "Live stage", Icon: Presentation },
  { path: "compose", label: "Compose", Icon: PenLine },
  { path: "library", label: "Library", Icon: BookOpen },
  { path: "settings", label: "Settings", Icon: Settings },
];
const MORE = [
  { path: "enroll", label: "Teach a sign", Icon: GraduationCap },
  { path: "glance", label: "Screen Glance", Icon: ScanEye },
  { path: "diagnostics", label: "Diagnostics", Icon: Activity },
  { path: "privacy", label: "Privacy", Icon: ShieldCheck },
];

const href = p => `#/${p}`;

export function Navbar({ path }) {
  const [open, setOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const on = () => setScrolled(window.scrollY > 8);
    on();
    window.addEventListener("scroll", on, { passive: true });
    return () => window.removeEventListener("scroll", on);
  }, []);
  useEffect(() => setOpen(false), [path]);
  useEffect(() => {
    if (!open) return undefined;
    const esc = e => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", esc);
    document.body.style.overflow = "hidden";
    return () => { window.removeEventListener("keydown", esc); document.body.style.overflow = ""; };
  }, [open]);

  return (
    <>
      <button type="button" onClick={() => { const m = document.getElementById("main"); m?.focus(); m?.scrollIntoView(); }}
        className="sr-only-focusable fixed left-3 top-3 z-[100] rounded-full bg-ink px-4 py-3 font-semibold text-light">Skip to content</button>
      <header className={cx("sticky top-0 z-50 transition-[background,box-shadow] duration-300",
        scrolled ? "bg-light/85 shadow-[0_1px_0_rgba(31,36,33,.08)] backdrop-blur-xl" : "bg-transparent")}>
        <nav className="mx-auto flex h-[72px] max-w-7xl items-center gap-3 px-4 sm:px-6" aria-label="Main">
          <a href="#/home" className="flex min-h-12 items-center rounded-xl" aria-label="SIGNOPSIS home">
            <Logo tone={open ? "light" : "ink"} />
          </a>
          <ul className="ml-6 hidden items-center gap-1 lg:flex">
            {NAV.map(n => (
              <li key={n.path}>
                <a href={href(n.path)} aria-current={path === n.path ? "page" : undefined}
                  className={cx("relative flex min-h-12 items-center rounded-full px-4 text-[15px] font-semibold transition-colors",
                    path === n.path ? "text-ink" : "text-ink-soft hover:text-ink")}>
                  {path === n.path && <motion.span layoutId="nav-pill" className="absolute inset-x-2 bottom-2 h-[3px] rounded-full bg-coral" />}
                  {n.label}
                </a>
              </li>
            ))}
          </ul>
          <div className="ml-auto flex items-center gap-2">
            <ModeBadge wrapClass="hidden sm:block" onClick={() => go("settings", "backend")} />
            <a href="#/converse" className="btn-primary hidden sm:inline-flex">
              Try SIGNOPSIS <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </a>
            <button type="button" className="btn-icon bg-white text-ink shadow-sm lg:hidden" aria-expanded={open} aria-controls="mobile-menu"
              aria-label={open ? "Close menu" : "Open menu"} onClick={() => setOpen(o => !o)}>
              {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </button>
          </div>
        </nav>
      </header>

      <AnimatePresence>
        {open && (
          <motion.div id="mobile-menu" className="fixed inset-0 z-40 bg-ink text-light lg:hidden"
            initial={{ clipPath: "circle(0% at 92% 36px)" }} animate={{ clipPath: "circle(150% at 92% 36px)" }} exit={{ clipPath: "circle(0% at 92% 36px)" }}
            transition={{ duration: 0.5, ease: [0.7, 0, 0.2, 1] }}>
            <div className="flex h-full flex-col overflow-y-auto px-6 pb-10 pt-24">
              <ul className="space-y-1">
                {[{ path: "home", label: "Home", Icon: Home }, ...NAV, ...MORE].map((n, i) => (
                  <motion.li key={n.path} initial={{ opacity: 0, x: -16 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.12 + i * 0.03 }}>
                    <a href={href(n.path)} className={cx("flex min-h-14 items-center gap-4 rounded-2xl px-3 text-2xl font-extrabold tracking-tight",
                      path === n.path ? "bg-white/10 text-sage" : "hover:bg-white/5")}>
                      <n.Icon className="h-6 w-6 text-coral" aria-hidden="true" />{n.label}
                    </a>
                  </motion.li>
                ))}
              </ul>
              <div className="mt-auto flex flex-wrap items-center gap-3 pt-8">
                <ModeBadge onClick={() => go("settings", "backend")} />
                <a href="#/converse" className="btn-coral">Try SIGNOPSIS <ArrowRight className="h-4 w-4" aria-hidden="true" /></a>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}

/** mobile bottom navigation */
export function BottomNav({ path }) {
  const items = [{ path: "home", label: "Home", Icon: Home }, ...NAV.slice(0, 3), { path: "settings", label: "More", Icon: Settings }];
  return (
    <nav aria-label="Quick" className="fixed inset-x-0 bottom-0 z-40 border-t border-ink/10 bg-white/92 pb-[env(safe-area-inset-bottom)] backdrop-blur-xl lg:hidden">
      <ul className="mx-auto grid max-w-lg grid-cols-5">
        {items.map(n => {
          const on = path === n.path || (n.path === "settings" && ["settings", "library", "privacy", "diagnostics", "enroll", "glance"].includes(path));
          return (
            <li key={n.path}>
              <a href={href(n.path)} aria-current={on ? "page" : undefined}
                className={cx("flex min-h-[60px] flex-col items-center justify-center gap-0.5 text-[11px] font-bold", on ? "text-ink" : "text-mute")}>
                <span className={cx("grid h-8 w-12 place-items-center rounded-full transition", on && "bg-sage-soft")}>
                  <n.Icon className="h-5 w-5" aria-hidden="true" />
                </span>
                {n.label.split(" ")[0]}
              </a>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
