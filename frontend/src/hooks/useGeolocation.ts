import { useEffect, useState } from "react";

export type LocationStatus = "idle" | "loading" | "granted" | "denied" | "unavailable";

export function useGeolocation() {
  const [state, setState] = useState<{ lat?: number; lon?: number; status: LocationStatus; error?: string }>({
    status: "idle",
  });

  useEffect(() => {
    if (!navigator.geolocation) {
      setState({ status: "unavailable", error: "Location is not available in this browser." });
      return;
    }
    setState({ status: "loading" });
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => setState({ lat: coords.latitude, lon: coords.longitude, status: "granted" }),
      (error) => setState({
        status: error.code === error.PERMISSION_DENIED ? "denied" : "unavailable",
        error: error.code === error.PERMISSION_DENIED ? "Location permission was denied." : "We could not find your location.",
      }),
      { enableHighAccuracy: false, timeout: 8000, maximumAge: 300000 },
    );
  }, []);

  return state;
}
