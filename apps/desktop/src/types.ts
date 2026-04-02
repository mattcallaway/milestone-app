export type Screen = 'dashboard' | 'drives' | 'roots' | 'scan' | 'library' | 'items' | 'item-detail' | 'operations' | 'cleanup' | 'failure-domains' | 'simulation' | 'risk' | 'planning' | 'plan-review';

export interface ScreenParams {
    itemId?: number;
    planId?: number;
    type?: string;
    min_copies?: number;
    max_copies?: number;
    status?: string;
}

export type NavigateFunction = (screen: Screen, params?: ScreenParams) => void;
