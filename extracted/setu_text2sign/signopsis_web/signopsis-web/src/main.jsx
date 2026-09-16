import "./lib/threeConsole.js";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { MotionConfig } from "framer-motion";
import App from "./App.jsx";
import { applyPrefs, usePrefs } from "./services/prefs.js";
import "./styles/index.css";

applyPrefs();

function Root() {
  const [prefs] = usePrefs();
  const reduced = prefs.motion === "reduce" ? "always" : prefs.motion === "full" ? "never" : "user";
  return (
    <MotionConfig reducedMotion={reduced}>
      <App />
    </MotionConfig>
  );
}

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <Root />
  </StrictMode>,
);
