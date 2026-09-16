import { ArrowUpRight } from "lucide-react";
import { Logo } from "./Brand.jsx";

const COLS = [
  { title: "Use it", links: [["Converse", "converse"], ["Live stage", "live"], ["Compose", "compose"], ["Teach a sign", "enroll"], ["Screen Glance", "glance"]] },
  { title: "Know it", links: [["Sign library", "library"], ["Diagnostics", "diagnostics"], ["How trust works", "home#trust"], ["Connect a backend", "settings#backend"]] },
  { title: "Trust it", links: [["Privacy", "privacy"], ["Settings", "settings"], ["Accessibility", "settings#access"]] },
];

export function Footer() {
  return (
    <footer className="relative mt-24 overflow-hidden bg-ink pb-28 pt-16 text-light lg:pb-12">
      <div aria-hidden="true" className="pointer-events-none absolute -right-24 -top-24 h-80 w-80 rounded-full bg-moss/30 blur-3xl" />
      <div aria-hidden="true" className="pointer-events-none absolute -bottom-32 left-10 h-72 w-72 rounded-full bg-coral/25 blur-3xl" />
      <div className="relative mx-auto grid max-w-7xl gap-12 px-4 sm:px-6 lg:grid-cols-[1.3fr_2fr]">
        <div>
          <Logo tone="light" size={44} />
          <p className="mt-5 max-w-sm text-lg text-light/75">
            A two-way sign language interpreter that shows how sure it is, asks when it isn't, and learns the signs you use.
          </p>
          <p className="mt-6 font-mono text-xs uppercase tracking-[.2em] text-light/65">Prototype · ISL first · built with Deaf reviewers in the loop</p>
        </div>
        <div className="grid grid-cols-2 gap-8 sm:grid-cols-3">
          {COLS.map(c => (
            <div key={c.title}>
              <h2 className="font-mono text-xs font-semibold uppercase tracking-[.2em] text-sage">{c.title}</h2>
              <ul className="mt-4 space-y-1">
                {c.links.map(([label, to]) => (
                  <li key={label}>
                    <a href={`#/${to}`} className="group inline-flex min-h-11 items-center gap-1 text-[15px] font-semibold text-light/80 hover:text-light">
                      {label}<ArrowUpRight className="h-3.5 w-3.5 opacity-0 transition group-hover:opacity-100" aria-hidden="true" />
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </div>
      <div className="relative mx-auto mt-16 max-w-7xl px-4 sm:px-6">
        <div data-watermark="signopsis" className="select-none text-[18vw] font-extrabold leading-[.8] tracking-[-0.06em] text-light/[.06] lg:text-[15rem]" aria-hidden="true" />
        <div className="mt-6 flex flex-col justify-between gap-2 border-t border-white/10 pt-6 text-sm text-light/70 sm:flex-row">
          <span>© {new Date().getFullYear()} SIGNOPSIS. Sign motions in this prototype are placeholders.</span>
          <span>Made to be checked by the people who use it.</span>
        </div>
      </div>
    </footer>
  );
}
