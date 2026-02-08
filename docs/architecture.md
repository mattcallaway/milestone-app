# Architecture

## Overview

Milestone App is a monorepo containing a desktop application and backend API service.

```
┌─────────────────────────────────────────────────────────────┐
│                      Desktop App                            │
│                   (Electron + React)                        │
│                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │   UI Layer  │  │   IPC       │  │   Main      │         │
│  │   (React)   │──┤   Bridge    │──┤   Process   │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
└─────────────────────────────────────────────────────────────┘
                           │
                           │ HTTP/REST
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                      Backend API                            │
│                      (FastAPI)                              │
│                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │  Endpoints  │──┤  Services   │──┤   Config    │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
└─────────────────────────────────────────────────────────────┘
```

## Safe-by-Default Design

- Application runs in **read-only mode** by default
- `WRITE_MODE=true` must be explicitly set to enable destructive operations
- All write endpoints check the mode before executing

## Key Components

### Desktop App (`/apps/desktop`)
- Electron for native desktop capabilities
- React for UI rendering
- Vite for fast development builds

### Backend API (`/services/api`)
- FastAPI for async REST endpoints
- Pydantic for data validation
- Uvicorn as ASGI server

### Shared Types (`/packages/shared`)
- TypeScript type definitions
- Shared between frontend and used as API contract reference
