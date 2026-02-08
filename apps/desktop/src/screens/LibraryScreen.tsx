import { useState, useEffect, useCallback } from 'react';
import { api, FileItem, FileStats } from '../api';
import './Screens.css';

export function LibraryScreen() {
    const [files, setFiles] = useState<FileItem[]>([]);
    const [stats, setStats] = useState<FileStats | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [total, setTotal] = useState(0);
    const [page, setPage] = useState(1);
    const [pageSize] = useState(100);

    // Filters
    const [searchPath, setSearchPath] = useState('');
    const [filterExt, setFilterExt] = useState('');
    const [minSize, setMinSize] = useState('');
    const [maxSize, setMaxSize] = useState('');

    const loadFiles = useCallback(async () => {
        try {
            setLoading(true);
            const params: Record<string, unknown> = { page, page_size: pageSize };

            if (searchPath.trim()) params.path_contains = searchPath.trim();
            if (filterExt.trim()) params.ext = filterExt.trim().replace('.', '');
            if (minSize) params.min_size = parseInt(minSize);
            if (maxSize) params.max_size = parseInt(maxSize);

            const result = await api.getFiles(params);
            setFiles(result.files);
            setTotal(result.total);
            setError(null);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to load files');
        } finally {
            setLoading(false);
        }
    }, [page, pageSize, searchPath, filterExt, minSize, maxSize]);

    const loadStats = async () => {
        try {
            const s = await api.getFileStats();
            setStats(s);
        } catch (err) {
            console.error('Failed to load stats:', err);
        }
    };

    useEffect(() => {
        loadFiles();
    }, [loadFiles]);

    useEffect(() => {
        loadStats();
    }, []);

    const handleSearch = (e: React.FormEvent) => {
        e.preventDefault();
        setPage(1);
        loadFiles();
    };

    const formatBytes = (bytes: number | null): string => {
        if (bytes === null) return '-';
        const units = ['B', 'KB', 'MB', 'GB'];
        let value = bytes;
        let unitIndex = 0;
        while (value >= 1024 && unitIndex < units.length - 1) {
            value /= 1024;
            unitIndex++;
        }
        return `${value.toFixed(1)} ${units[unitIndex]}`;
    };

    const formatDate = (timestamp: string | null): string => {
        if (!timestamp) return '-';
        return new Date(timestamp).toLocaleDateString();
    };

    const totalPages = Math.ceil(total / pageSize);

    return (
        <div className="screen">
            <div className="screen-header">
                <h2>Library</h2>
                <p className="subtitle">
                    {total.toLocaleString()} files indexed
                    {stats && ` (${formatBytes(stats.total_size)} total)`}
                </p>
            </div>

            <form className="filter-form" onSubmit={handleSearch}>
                <input
                    type="text"
                    placeholder="Search path..."
                    value={searchPath}
                    onChange={(e) => setSearchPath(e.target.value)}
                    className="input"
                />
                <input
                    type="text"
                    placeholder="Extension (e.g., mp4)"
                    value={filterExt}
                    onChange={(e) => setFilterExt(e.target.value)}
                    className="input input-sm"
                />
                <input
                    type="number"
                    placeholder="Min size (bytes)"
                    value={minSize}
                    onChange={(e) => setMinSize(e.target.value)}
                    className="input input-sm"
                />
                <input
                    type="number"
                    placeholder="Max size (bytes)"
                    value={maxSize}
                    onChange={(e) => setMaxSize(e.target.value)}
                    className="input input-sm"
                />
                <button type="submit" className="btn btn-primary">
                    Search
                </button>
            </form>

            {error && <div className="error-banner">{error}</div>}

            {stats && stats.by_extension.length > 0 && (
                <div className="ext-chips">
                    {stats.by_extension.slice(0, 10).map((ext) => (
                        <button
                            key={ext.ext}
                            className={`chip ${filterExt === ext.ext ? 'active' : ''}`}
                            onClick={() => {
                                setFilterExt(filterExt === ext.ext ? '' : ext.ext);
                                setPage(1);
                            }}
                        >
                            .{ext.ext} ({ext.count})
                        </button>
                    ))}
                </div>
            )}

            {loading ? (
                <div className="loading">Loading files...</div>
            ) : files.length === 0 ? (
                <div className="empty-state">
                    <p>No files found.</p>
                    <p className="hint">Run a scan to index files, or adjust your filters.</p>
                </div>
            ) : (
                <>
                    <div className="files-table-wrapper">
                        <table className="files-table">
                            <thead>
                                <tr>
                                    <th>Path</th>
                                    <th>Extension</th>
                                    <th>Size</th>
                                    <th>Last Seen</th>
                                </tr>
                            </thead>
                            <tbody>
                                {files.map((file) => (
                                    <tr key={file.id}>
                                        <td className="path-cell" title={file.path}>
                                            {file.path}
                                        </td>
                                        <td className="ext-cell">.{file.ext || '-'}</td>
                                        <td className="size-cell">{formatBytes(file.size)}</td>
                                        <td className="date-cell">{formatDate(file.last_seen)}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
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
