# Rainwise frontend

This Vite + React + TypeScript app is designed for Vercel. Copy `.env.example` to
`.env.local` for local development. Set these Vercel environment variables:

- `VITE_API_URL`: public URL of the FastAPI backend, without a trailing slash.
- `VITE_PHONE_NUMBER`: IVR phone number displayed to users.
- `VITE_USE_MOCK`: set to `true` to build or demo without the backend; use `false`
  in production.

Only public configuration belongs in these variables. Never put API keys or
private backend credentials in frontend environment variables.
