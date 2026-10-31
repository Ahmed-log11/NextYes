# NextYes web app

React + Vite + Tailwind. English first, Arabic (RTL) on the toggle; every string is in `src/lib/i18n.jsx` and `src/lib/appStrings.js`.

```
npm install
npm run dev          # http://localhost:5173 (the API must run on http://127.0.0.1:8000)
npm run build        # static files in dist/
```

Set `VITE_API_URL` (see `.env.example`) to point at another API, e.g. the Render URL on Vercel.

| Path | Screen |
|---|---|
| `/` | Landing: the promise, the five-stage story, three doors |
| `/business` | Owner journey: readiness band, readiness map (map / cards), plan lanes, chat, timeline, documents |
| `/bank` | Credit desk: files submitted from this browser, decision, rules with sources, checks, audit log |
| `/results` | Evaluation dashboard, computed from the reports the API serves (`/api/evaluation`) |

Journey ids are kept in the browser (localStorage), one per demo business, so a visitor can switch businesses and come back.
`vercel.json` sends every path to `index.html` so deep links work.
