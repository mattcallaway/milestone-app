/**
 * Shared types and schemas for the Milestone App
 */

// API Response types
export interface ApiResponse<T> {
    success: boolean;
    data?: T;
    error?: string;
}

export interface HealthResponse {
    status: 'healthy' | 'unhealthy';
    write_mode: boolean;
}

export interface ModeResponse {
    mode: 'read-only' | 'write';
}

// Application configuration
export interface AppConfig {
    writeMode: boolean;
    apiHost: string;
    apiPort: number;
}

// Common status types
export type OperationStatus = 'pending' | 'running' | 'completed' | 'failed';

export interface OperationResult {
    status: OperationStatus;
    message: string;
    timestamp: string;
}
