export const RISK_COLORS: Record<string, string> = {
    Critical: '#f44336',
    High: '#ff5722',
    Medium: '#ff9800',
    Low: '#ffc107',
    Minimal: '#4caf50',
};

export const HEALTH_COLORS: Record<string, string> = {
    healthy: '#4caf50',
    warning: '#ff9800',
    degraded: '#f44336',
    avoid_for_new_copies: '#ff5722',
};

export function getRiskColor(score: number): string {
    if (score >= 70) return RISK_COLORS.Critical;
    if (score >= 50) return RISK_COLORS.High;
    if (score >= 30) return RISK_COLORS.Medium;
    if (score >= 10) return RISK_COLORS.Low;
    return RISK_COLORS.Minimal;
}
