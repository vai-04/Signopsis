import { useCallback, useEffect, useRef, useState } from "react";
import { CameraSource } from "../services/camera/mediapipeSource.js";

/**
 * Webcam + MediaPipe (hands, pose, face) -> WireFrame callback.
 *   const cam = useCamera({ onFrame: f => session.sendFrame(f) });
 *   <video ref={cam.videoRef} />  cam.start()  cam.stop()
 */
export function useCamera({ onFrame } = {}) {
  const videoRef = useRef(null);
  const src = useRef(null);
  const cb = useRef(onFrame);
  cb.current = onFrame;
  const [state, setState] = useState("off");       // off | loading | on | error
  const [error, setError] = useState(null);
  const [log, setLog] = useState([]);
  const [fps, setFps] = useState(0);

  const start = useCallback(async () => {
    if (!videoRef.current) return;
    setError(null);
    setState("loading");
    try {
      if (!src.current) {
        src.current = new CameraSource({
          video: videoRef.current,
          onFrame: f => cb.current?.(f),
          log: m => setLog(l => [...l.slice(-6), m]),
        });
      }
      await src.current.start();
      setState("on");
    } catch (e) {
      src.current?.stop();
      setState("error");
      const msg = e?.name === "NotAllowedError" ? "Camera permission was denied. Allow it in the address bar and try again."
        : e?.name === "NotFoundError" ? "No camera found on this device."
        : `Couldn't start the camera: ${e?.message || e}`;
      setError(msg);
    }
  }, []);

  const stop = useCallback(() => {
    src.current?.stop();
    setState("off");
  }, []);

  useEffect(() => {
    if (state !== "on") return undefined;
    const id = setInterval(() => setFps(Math.round(src.current?.fps || 0)), 1000);
    return () => clearInterval(id);
  }, [state]);

  useEffect(() => () => src.current?.stop(), []);

  return { videoRef, state, error, log, fps, start, stop, supported: typeof navigator !== "undefined" && !!navigator.mediaDevices?.getUserMedia };
}
