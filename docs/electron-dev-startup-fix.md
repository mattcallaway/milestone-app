# Electron Development Startup Fix

## Root Cause
The Electron app was encountering two primary issues in the development environment:
1. **Connection Mismatch**: Vite was occasionally starting on a different port (e.g., 5174) than the one hardcoded in the Electron main process (5173), leading to a blank window.
2. **Environment Poisoning**: The `ELECTRON_RUN_AS_NODE` environment variable was accidentally inherited, causing Electron to behave as standard Node.js (missing `app.whenReady`) and crashing the main process.
3. **Invalid Load Path**: In some development configurations, the app incorrectly attempted to load `dist/index.html` (production path) before it was even built.

## Files Changed
- `apps/desktop/src/main.ts`:
    - Added a robust `isElectron` check with explicit diagnostics.
    - Updated URL loading logic to use `VITE_DEV_SERVER_URL` or a fallback to `http://localhost:5173`.
    - Added an explicit `isDev` check using `!app.isPackaged` to ensure correct loading behavior regardless of `NODE_ENV`.
- `apps/desktop/vite.config.ts`:
    - Fixed the development port to `5173` using `strictPort: true` to ensure a stable connection target for Electron.
- `apps/desktop/package.json`:
    - Added `cross-env` and `wait-on` to the development scripts.
    - Updated `dev:main` to wait for the renderer to be ready before starting the shell.
    - Explicitly unsets `ELECTRON_RUN_AS_NODE` during startup.
- `apps/desktop/src/components/SidecarPanel.tsx`:
    - Fixed a relative import path for `Screens.css` that was causing Vite pre-transform errors.

## Verification Steps
1. Navigate to `apps/desktop`.
2. Run `npm run build:main` to ensure the new binary logic compiles.
3. Ensure no stale node processes are running (`Stop-Process -Name node`).
4. Run `npm run dev`.
5. **Expected Outcome**:
    - Vite starts on `localhost:5173`.
    - Electron waits for the port to be open.
    - The main window opens and correctly displays the React dashboard.
    - No "File Not Found" errors or blank windows occur.

## Final Commands
```bash
cd apps/desktop
npm install
npm run dev
```
