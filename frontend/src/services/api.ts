import axios from "axios";

/** Base URL of the FastAPI backend, from VITE_API_BASE_URL. */
export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api").replace(/\/+$/, "");

export const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 90_000,
  headers: { "Content-Type": "application/json" },
});

// ------------------------------------------------------------ demo mode state
// Demo mode is switched on only when the backend cannot be reached.
// Every page shows a banner while it is active, and mutations are disabled.

type Listener = (demo: boolean) => void;
let demoMode = false;
const listeners = new Set<Listener>();

export const demoState = {
  get: () => demoMode,
  set(value: boolean) {
    if (value === demoMode) return;
    demoMode = value;
    listeners.forEach((l) => l(value));
  },
  subscribe(listener: Listener) {
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  },
};

export class DemoModeError extends Error {
  constructor(message = "Action indisponible en mode démo : le backend n'est pas connecté.") {
    super(message);
    this.name = "DemoModeError";
  }
}

export function assertLive(): void {
  if (demoMode) throw new DemoModeError();
}

/** Drop empty values so they are not sent as query parameters. */
export function cleanParams<T extends object>(params: T): Partial<T> {
  return Object.fromEntries(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== ""),
  ) as Partial<T>;
}
