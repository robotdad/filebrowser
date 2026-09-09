/**
 * Helpers for the authenticated favorites API.
 *
 * Favorites are persisted as physical, absolute paths.  The file tree uses
 * virtual paths relative to the authenticated home directory or an external
 * location, so the conversion lives here rather than in the tree component.
 */

function normalizeAbsolutePath(path) {
    if (typeof path !== 'string' || !path.startsWith('/')) return null;
    const normalized = path.replace(/\/+$/, '');
    return normalized || '/';
}

function isAtOrBelow(path, root) {
    return root === '/' ? path.startsWith('/') : path === root || path.startsWith(`${root}/`);
}

function relativeToRoot(path, root) {
    if (path === root) return '';
    return root === '/' ? path.slice(1) : path.slice(root.length + 1);
}

function isSafeVirtualRelativePath(path) {
    if (typeof path !== 'string' || path.startsWith('/')) return false;
    if (path === '') return true;
    return path.split('/').every((part) => part && part !== '.' && part !== '..');
}

function getExternalVirtualPath(location) {
    if (!location || location.id === undefined || location.id === null) return null;
    return `@ext/${location.id}`;
}

function parseExternalVirtualPath(path, externalLocations) {
    if (typeof path !== 'string') return null;
    const parts = path.split('/');
    if (parts.length < 2 || parts[0] !== '@ext' || !parts[1]) return null;

    const location = (externalLocations || []).find(
        (candidate) => getExternalVirtualPath(candidate) === `@ext/${parts[1]}`,
    );
    const root = normalizeAbsolutePath(location?.path);
    const relativeParts = parts.slice(2);
    if (!location || !root || !relativeParts.every((part) => part && part !== '.' && part !== '..')) {
        return null;
    }

    return { location, root, relativePath: relativeParts.join('/') };
}

function uniquePhysicalPaths(entries) {
    const paths = [];
    const seen = new Set();
    for (const entry of Array.isArray(entries) ? entries : []) {
        const rawPath = typeof entry === 'string' ? entry : entry?.path;
        const path = normalizeAbsolutePath(rawPath);
        if (path && !seen.has(path)) {
            seen.add(path);
            paths.push(path);
        }
    }
    return paths;
}

/**
 * Convert an API favorite's physical path to a FileTree virtual path.
 *
 * A path must be contained by a known root on a path-component boundary.
 * Where roots overlap, the most specific root wins so an external child is
 * represented by its own location rather than a broader parent root.
 */
export function favoritePhysicalToVirtualPath(physicalPath, homeDir, externalLocations = []) {
    const path = normalizeAbsolutePath(physicalPath);
    const homeRoot = normalizeAbsolutePath(homeDir);
    if (!path) return null;

    let match = homeRoot && isAtOrBelow(path, homeRoot)
        ? { type: 'home', root: homeRoot }
        : null;

    for (const location of externalLocations || []) {
        const root = normalizeAbsolutePath(location?.path);
        const virtualRoot = getExternalVirtualPath(location);
        if (!root || !virtualRoot || !isAtOrBelow(path, root)) continue;

        if (
            !match
            || root.length > match.root.length
            || (root.length === match.root.length && match.type === 'home')
        ) {
            match = { type: 'external', root, location, virtualRoot };
        }
    }

    if (!match) return null;

    const relativePath = relativeToRoot(path, match.root);
    if (!isSafeVirtualRelativePath(relativePath)) return null;
    if (match.type === 'home') return relativePath;
    return relativePath ? `${match.virtualRoot}/${relativePath}` : match.virtualRoot;
}

/**
 * Convert a FileTree virtual path to the physical path expected by the API.
 */
export function favoriteVirtualToPhysicalPath(virtualPath, homeDir, externalLocations = []) {
    if (typeof virtualPath !== 'string') return null;

    if (virtualPath.startsWith('@ext/')) {
        const externalPath = parseExternalVirtualPath(virtualPath, externalLocations);
        if (!externalPath) return null;
        return externalPath.relativePath
            ? `${externalPath.root}/${externalPath.relativePath}`
            : externalPath.root;
    }

    const homeRoot = normalizeAbsolutePath(homeDir);
    if (!homeRoot || !isSafeVirtualRelativePath(virtualPath)) return null;
    return virtualPath ? `${homeRoot === '/' ? '' : homeRoot}/${virtualPath}` : homeRoot;
}

/**
 * Return the registered location that contains a favorite virtual path.
 */
export function externalLocationForFavoritePath(virtualPath, externalLocations = []) {
    return parseExternalVirtualPath(virtualPath, externalLocations)?.location || null;
}

/**
 * Return the registered location only when virtualPath names its exact root.
 */
export function externalLocationForFavoriteRoot(virtualPath, externalLocations = []) {
    const externalPath = parseExternalVirtualPath(virtualPath, externalLocations);
    return externalPath && externalPath.relativePath === '' ? externalPath.location : null;
}

/**
 * Map API entries to unique, renderable tree paths. Unknown physical paths are
 * deliberately omitted rather than treated as home-relative paths.
 */
export function mapFavoritePaths(entries, homeDir, externalLocations = []) {
    const mapped = [];
    const seen = new Set();
    for (const physicalPath of uniquePhysicalPaths(entries)) {
        const virtualPath = favoritePhysicalToVirtualPath(
            physicalPath,
            homeDir,
            externalLocations,
        );
        if (virtualPath !== null && !seen.has(virtualPath)) {
            seen.add(virtualPath);
            mapped.push(virtualPath);
        }
    }
    return mapped;
}

/**
 * Render personal favorites and registered locations as one de-duplicated list.
 * Registered locations are synthesized here; they are never persisted as a
 * user's favorite.
 */
export function mergeFavoritePaths(favoritePaths, externalLocations = []) {
    const merged = [];
    const seen = new Set();
    for (const path of favoritePaths || []) {
        if (typeof path === 'string' && !seen.has(path)) {
            seen.add(path);
            merged.push(path);
        }
    }
    for (const location of externalLocations || []) {
        const path = getExternalVirtualPath(location);
        if (path && !seen.has(path)) {
            seen.add(path);
            merged.push(path);
        }
    }
    return merged;
}

/**
 * Preserve a drag-and-drop order in component state while accepting newly
 * loaded favorites and locations.
 */
export function orderFavoritePaths(paths, preferredOrder = []) {
    const available = new Set(paths || []);
    const ordered = [];
    const seen = new Set();

    for (const path of preferredOrder || []) {
        if (available.has(path) && !seen.has(path)) {
            seen.add(path);
            ordered.push(path);
        }
    }
    for (const path of paths || []) {
        if (!seen.has(path)) {
            seen.add(path);
            ordered.push(path);
        }
    }
    return ordered;
}

/**
 * Serialize API mutations and discard callbacks belonging to an inactive
 * authenticated identity. The controller intentionally has no storage layer:
 * the API is the sole source of persisted favorites.
 */
export function createFavoritesController({
    loadFavorites,
    addFavorite,
    removeFavorite,
    onChange,
}) {
    let activeSession = null;
    let paths = [];
    let loaded = false;
    let queue = Promise.resolve();
    let sessionSequence = 0;
    let revision = 0;
    const pending = new Set();

    const publish = () => onChange({ paths: [...paths], loaded });
    const isActive = (session) => activeSession === session;

    const activate = (username) => {
        const session = { id: ++sessionSequence, username };
        activeSession = session;
        paths = [];
        loaded = false;
        queue = Promise.resolve();
        pending.clear();
        const loadRevision = ++revision;
        publish();

        Promise.resolve()
            .then(loadFavorites)
            .then((entries) => {
                if (!isActive(session) || revision !== loadRevision) return;
                paths = uniquePhysicalPaths(entries);
                loaded = true;
                publish();
            })
            .catch(() => {});

        return session;
    };

    const deactivate = (session) => {
        if (isActive(session)) {
            activeSession = null;
            paths = [];
            loaded = false;
            queue = Promise.resolve();
            pending.clear();
            revision += 1;
        }
    };

    const toggle = (username, physicalPath) => {
        const session = activeSession;
        const path = normalizeAbsolutePath(physicalPath);
        if (!session || session.username !== username || !path || !loaded) {
            return Promise.resolve(false);
        }

        const pendingKey = `${session.id}\u0000${path}`;
        if (pending.has(pendingKey)) return Promise.resolve(false);

        pending.add(pendingKey);
        revision += 1;
        const run = async () => {
            if (!isActive(session)) return false;

            const isPinned = paths.includes(path);
            try {
                if (isPinned) {
                    await removeFavorite(path);
                    if (!isActive(session)) return false;
                    paths = paths.filter((candidate) => candidate !== path);
                } else {
                    const entry = await addFavorite(path);
                    if (!isActive(session)) return false;
                    const savedPath = normalizeAbsolutePath(entry?.path) || path;
                    paths = uniquePhysicalPaths([...paths, savedPath]);
                }
                publish();
                return true;
            } catch {
                return false;
            }
        };

        const scheduled = queue.catch(() => {}).then(run);
        queue = scheduled.catch(() => {});
        return scheduled.then(
            (result) => {
                pending.delete(pendingKey);
                return result;
            },
            () => {
                pending.delete(pendingKey);
                return false;
            },
        );
    };

    return { activate, deactivate, toggle };
}