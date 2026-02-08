# API Specification

## Base URL

- Development: `http://127.0.0.1:8000`

## Endpoints

### GET /

Root endpoint.

**Response:**
```json
{
  "message": "Milestone API",
  "status": "running"
}
```

### GET /health

Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "write_mode": false
}
```

### GET /mode

Get current operation mode.

**Response:**
```json
{
  "mode": "read-only"
}
```

### POST /example-write

Example write operation (requires `WRITE_MODE=true`).

**Success Response (200):**
```json
{
  "message": "Write operation completed"
}
```

**Error Response (403) - Write mode disabled:**
```json
{
  "detail": "Write operations are disabled. Set WRITE_MODE=true to enable."
}
```

## Authentication

*To be implemented in future milestone.*

## Rate Limiting

*To be implemented in future milestone.*
