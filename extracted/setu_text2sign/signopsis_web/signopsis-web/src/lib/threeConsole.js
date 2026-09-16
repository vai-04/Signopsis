// three r183+ deprecates THREE.Clock, which @react-three/fiber 9 still constructs internally.
// Filter that one known, harmless deprecation; forward everything else unchanged.
import { setConsoleFunction } from "three";

const MUTED = ["Clock: This module has been deprecated"];

setConsoleFunction((level, message, ...rest) => {
  if (MUTED.some(m => String(message).includes(m))) return;
  (console[level] || console.log)(message, ...rest);
});
