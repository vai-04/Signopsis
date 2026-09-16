import { useEffect, useMemo, useState } from "react";
import { SignPlayer } from "../lib/signPlayer.js";

/** create (once) and subscribe to a SignPlayer */
export function usePlayer(existing) {
  const player = useMemo(() => existing || new SignPlayer(), [existing]);
  const [snap, setSnap] = useState(() => player.snapshot());
  useEffect(() => player.subscribe(setSnap), [player]);
  return [player, snap];
}
