import { useEffect, useState } from "react";
import { backend } from "../services/backend.js";

/** live backend connection status: {resolved: "live"|"mock"|null, checking, health, error, requested} */
export function useBackend() {
  const [s, set] = useState(backend.status);
  useEffect(() => {
    const off = backend.subscribe(set);
    if (!backend.status.resolved) backend.resolve();
    return off;
  }, []);
  return s;
}
