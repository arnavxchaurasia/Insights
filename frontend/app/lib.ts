// Base URL of the FastAPI backend. NEXT_PUBLIC_ is required so client components
// (the notification bell) can read it in the browser; it also works server-side.
export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";
