import { useState, useEffect, useCallback } from 'react';
import { api, MediaItem } from '../api';
import './Screens.css';

interface ItemsScreenProps {
    initialFilters?: {
        type?: string;
        min_copies?: number;
        max_copies?: number;
        status?: string;
    };
    onViewItem: (itemId: number) => void;
}

export function ItemsScreen({ initialFilters, onViewItem }: ItemsScreenProps) {
    const [items, setItems] = useState<MediaItem[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [total, setTotal] = useState(0);
    const [page, setPage] = useState(1);
    const [pageSize] = useState(50);

    // Filters
    const [filterType, setFilterType] = useState(initialFilters?.type || '');
    const [filterStatus, setFilterStatus] = useState(initialFilters?.status || '');
    const [minCopies, setMinCopies] = useState<string>(
        initialFilters?.min_copies?.toString() || ''
    );
    const [maxCopies, setMaxCopies] = useState<string>(
        initialFilters?.max_copies?.toString() || ''
    );
    const [search, setSearch] = useState('');

    const loadItems = useCallback(async () => {
        try {
            setLoading(true);
            const params: Record<string, unknown> = { page, page_size: pageSize };

            if (filterType) params.type = filterType;
            if (filterStatus) params.status = filterStatus;
            if (minCopies) params.min_copies = parseInt(minCopies);
            if (maxCopies) params.max_copies = parseInt(maxCopies);
            if (search.trim()) params.search = search.trim();

            const result = await api.getItems(params);
            setItems(result.items);
            setTotal(result.total);
            setError(null);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to load items');
        } finally {
            setLoading(false);
        }
    }, [page, pageSize, filterType, filterStatus, minCopies, maxCopies, search]);

    useEffect(() => {
        loadItems();
    }, [loadItems]);

    useEffect(() => {
        // Apply initial filters when they change
        if (initialFilters) {
            if (initialFilters.type) setFilterType(initialFilters.type);
            if (initialFilters.status) setFilterStatus(initialFilters.status);
            if (initialFilters.min_copies !== undefined) setMinCopies(initialFilters.min_copies.toString());
            if (initialFilters.max_copies !== undefined) setMaxCopies(initialFilters.max_copies.toString());
            setPage(1);
        }
    }, [initialFilters]);

    const handleSearch = (e: React.FormEvent) => {
        e.preventDefault();
        setPage(1);
        loadItems();
    };

    const clearFilters = () => {
        setFilterType('');
        setFilterStatus('');
        setMinCopies('');
        setMaxCopies('');
        setSearch('');
        setPage(1);
    };

    const getTypeIcon = (type: string): string => {
        switch (type) {
            case 'movie': return '🎬';
            case 'tv_episode': return '📺';
            default: return '❓';
        }
    };

    const getStatusBadge = (status: string): JSX.Element | null => {
        if (status === 'needs_verification') {
            return <span className="badge badge-warning">Verify</span>;
        }
        if (status === 'verified') {
            return <span className="badge badge-success">✓</span>;
        }
        return null;
    };

    const formatTitle = (item: MediaItem): string => {
        let title = item.title || 'Untitled';
        if (item.type === 'tv_episode' && item.season !== null && item.episode !== null) {
            title += ` S${String(item.season).padStart(2, '0')}E${String(item.episode).padStart(2, '0')}`;
        }
        if (item.year) {
            title += ` (${item.year})`;
        }
        return title;
    };

    const totalPages = Math.ceil(total / pageSize);

    return (
        <div className="screen">
            <div className="screen-header">
                <h2>Media Items</h2>
                <p className="subtitle">{total.toLocaleString()} items</p>
            </div>

            <form className="filter-form" onSubmit={handleSearch}>
                <input
                    type="text"
                    placeholder="Search title..."
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    className="input"
                />
                <select
                    value={filterType}
                    onChange={(e) => { setFilterType(e.target.value); setPage(1); }}
                    className="input select"
                >
                    <option value="">All types</option>
                    <option value="movie">Movies</option>
                    <option value="tv_episode">TV Episodes</option>
                    <option value="unknown">Unknown</option>
                </select>
                <select
                    value={filterStatus}
                    onChange={(e) => { setFilterStatus(e.target.value); setPage(1); }}
                    className="input select"
                >
                    <option value="">All status</option>
                    <option value="auto">Auto</option>
                    <option value="verified">Verified</option>
                    <option value="needs_verification">Needs Verification</option>
                </select>
                <input
                    type="number"
                    placeholder="Min copies"
                    value={minCopies}
                    onChange={(e) => setMinCopies(e.target.value)}
                    className="input input-sm"
                    min="0"
                />
                <input
                    type="number"
                    placeholder="Max copies"
                    value={maxCopies}
                    onChange={(e) => setMaxCopies(e.target.value)}
                    className="input input-sm"
                    min="0"
                />
                <button type="submit" className="btn btn-primary">Filter</button>
                <button type="button" className="btn btn-secondary" onClick={clearFilters}>Clear</button>
            </form>

            {error && <div className="error-banner">{error}</div>}

            {loading ? (
                <div className="loading">Loading items...</div>
            ) : items.length === 0 ? (
                <div className="empty-state">
                    <p>No media items found.</p>
                    <p className="hint">Run a scan and process files to create items.</p>
                </div>
            ) : (
                <>
                    <div className="items-list">
                        {items.map((item) => (
                            <div
                                key={item.id}
                                className="item-row"
                                onClick={() => onViewItem(item.id)}
                            >
                                <span className="item-type-icon">{getTypeIcon(item.type)}</span>
                                <div className="item-info">
                                    <span className="item-title">{formatTitle(item)}</span>
                                    {getStatusBadge(item.status)}
                                </div>
                                <span className="item-copies">
                                    <span className="copy-pill">{item.copy_count}</span>
                                    {item.copy_count === 1 ? 'copy' : 'copies'}
                                </span>
                            </div>
                        ))}
                    </div>

                    <div className="pagination">
                        <button
                            className="btn btn-sm"
                            disabled={page <= 1}
                            onClick={() => setPage(page - 1)}
                        >
                            ← Previous
                        </button>
                        <span className="page-info">
                            Page {page} of {totalPages}
                        </span>
                        <button
                            className="btn btn-sm"
                            disabled={page >= totalPages}
                            onClick={() => setPage(page + 1)}
                        >
                            Next →
                        </button>
                    </div>
                </>
            )}
        </div>
    );
}
