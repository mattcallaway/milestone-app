# Milestone App

A monorepo containing a desktop application (Electron + React) and backend API (Python FastAPI).

## Prerequisites

- **Node.js** 18+ and npm
- **Python** 3.11+
- **Git**

## Project Structure

```
milestone-app/
├── apps/desktop/       # Electron + React desktop application
├── services/api/       # Python FastAPI backend
├── packages/shared/    # Shared TypeScript types/schemas
└── docs/               # Architecture and documentation
```

## Local Development

### Quick Start (Both Frontend & Backend)

```bash
# Terminal 1: Start the API
cd services/api
pip install -e ".[dev]"
uvicorn src.main:app --reload

# Terminal 2: Start the Desktop App
cd apps/desktop
npm install
npm run dev
```

### Frontend Only (Desktop App)

```bash
cd apps/desktop
npm install
npm run dev
```

### Backend Only (API)

```bash
cd services/api
pip install -e ".[dev]"
uvicorn src.main:app --reload --host 127.0.0.1 --port 8000
```

## Build Commands

### Desktop App

```bash
cd apps/desktop
npm run build        # Build for production
npm run package      # Package Electron app
```

### Backend API

```bash
cd services/api
pip install -e .
# Deploy with: uvicorn src.main:app --host 0.0.0.0 --port 8000
```

## Running Scans on Test Data Safely

> ⚠️ **Safe-by-Default**: The application runs in **read-only mode** by default.

To run scans on test data without risking modifications:

1. **Do NOT set `WRITE_MODE=true`** in your environment
2. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```
3. Ensure `WRITE_MODE=false` (the default)
4. Run the application normally - all write operations will be blocked

To enable write operations (use with caution):
```bash
# In your .env file:
WRITE_MODE=true
```

## Linting & Testing

### Desktop App

```bash
cd apps/desktop
npm run lint         # ESLint
npm run typecheck    # TypeScript check
npm run test         # Jest tests
```

### Backend API

```bash
cd services/api
ruff check .         # Python linting
mypy src             # Type checking
pytest               # Run tests
```

## License

MIT
