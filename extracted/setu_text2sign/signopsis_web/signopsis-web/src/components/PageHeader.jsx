import { motion } from "framer-motion";
import { SectionTag } from "./Brand.jsx";

export function PageHeader({ n, eyebrow, title, lead, children }) {
  return (
    <header className="relative py-8 sm:py-12">
      <SectionTag n={n}>{eyebrow}</SectionTag>
      <motion.h1 initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
        className="mt-4 max-w-4xl text-4xl font-extrabold leading-[1.02] sm:text-6xl">{title}</motion.h1>
      {lead && <p className="mt-4 max-w-2xl text-lg text-ink-soft">{lead}</p>}
      {children}
    </header>
  );
}
