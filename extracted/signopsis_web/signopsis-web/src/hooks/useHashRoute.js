import { useEffect, useState } from "react";

// Hash routing (works on any static host, inside the backend's /static mount, and as a single file).
const read = () => {
  const h = window.location.hash.replace(/^#\/?/, "");
  const [path, anchor] = h.split("#");
  return { path: path || "", anchor: anchor || null };
};

export function useHashRoute() {
  const [route, setRoute] = useState(read);
  useEffect(() => {
    const on = () => setRoute(read());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return route;
}

export function go(path, anchor) {
  const next = `#/${path}${anchor ? `#${anchor}` : ""}`;
  if (window.location.hash === next) {
    if (anchor) document.getElementById(anchor)?.scrollIntoView({ behavior: "smooth" });
    return;
  }
  window.location.hash = next;
}
