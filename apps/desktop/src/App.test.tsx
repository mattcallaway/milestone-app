import { describe, it, expect } from '@jest/globals';

describe('App', () => {
    it('placeholder test passes', () => {
        expect(true).toBe(true);
    });

    it('can define screen types', () => {
        const screens = ['drives', 'roots', 'scan', 'library'];
        expect(screens).toHaveLength(4);
    });
});
