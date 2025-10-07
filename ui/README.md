# MCC Underwriter UI

This is a lightweight Next.js app for the Underwriter workflow.

- Intake form posts to backend `/api/v1/mcc/recommend`
- Decision panel shows final recommendation + ranked `mcc_proposal`
- Research Chat stub (to be wired to `/api/v1/chat` later)

## Quickstart

1. Copy env:
```bash
cp .env.local.example .env.local
```
2. Set the backend URL in `.env.local`:
```
NEXT_PUBLIC_API_URL=http://127.0.0.1:8090
```
3. Install deps and run:
```bash
npm install
npm run dev
```
Open http://localhost:3000

## Notes

- Designed to pair with the FastAPI backend in `MCC_AI_Agent`.
- Uses App Router and simple dark styling similar to trycast.com.
