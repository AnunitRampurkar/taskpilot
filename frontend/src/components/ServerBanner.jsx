import { useEffect, useState } from "react";
import { API_URL } from "../api";

// Render's free plan puts the backend to sleep. Ping it on load and tell the
// user what's going on instead of letting the first request look broken.
export default function ServerBanner() {
  const [state, setState] = useState("checking");

  useEffect(() => {
    let stopped = false;
    const slowTimer =setTimeout(() => !stopped && setState((s) => (s === "checking" ? "waking" : s)), 2500);

    async function ping(attempt = 0) {
      try {
        const res = await fetch(`${API_URL}/health`);
        if (!res.ok) throw new Error();
        if (!stopped) setState("up");
      } catch {
        if (stopped) return;
        if (attempt < 12) setTimeout(() => ping(attempt + 1), 5000);
        else setState("down");
      }
    }
    ping();

    return () => {
      stopped = true;
      clearTimeout(slowTimer);
    };
  }, []);

  if (state === "waking") {
    return <div className="banner banner-info">Waking up the server (free hosting sleeps when idle). This can take up to a minute...</div>;
  }
  if (state === "down") {
    return <div className="banner banner-error">Can't reach the server right now. Please refresh in a bit.</div>;
  }
  return null;
}
