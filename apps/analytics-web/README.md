# Compass Analytics Web

Independent React product for the commerce analytics workflow.

```bash
cd apps/analytics-web
npm install
npm run dev
```

The app listens on http://localhost:5174 and proxies `/api` and `/health` to
the analytics API on port 8090. Production builds are served from the app's
own Nginx image; they are not bundled into the support API container.
