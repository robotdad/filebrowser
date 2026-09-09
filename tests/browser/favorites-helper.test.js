'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const REPO_ROOT = path.resolve(__dirname, '..', '..');
const HELPERS_FILE = path.join(REPO_ROOT, 'filebrowser', 'static', 'js', 'favorites.js');
const LAYOUT_FILE = path.join(
    REPO_ROOT,
    'filebrowser',
    'static',
    'js',
    'components',
    'layout.js',
);

function deferred() {
    let resolve;
    let reject;
    const promise = new Promise((resolvePromise, rejectPromise) => {
        resolve = resolvePromise;
        reject = rejectPromise;
    });
    return { promise, resolve, reject };
}

async function waitFor(predicate, message) {
    for (let attempt = 0; attempt < 50; attempt += 1) {
        if (predicate()) return;
        await new Promise((resolve) => setImmediate(resolve));
    }
    assert.fail(message);
}

async function loadHelpers() {
    // favorites.js has no imports, so loading its exact source through a data
    // URL keeps this test executable without package.json or a DOM harness.
    const source = fs.readFileSync(HELPERS_FILE);
    const url = `data:text/javascript;base64,${source.toString('base64')}`;
    return import(url);
}

async function testPathMapping(helpers) {
    const locations = [
        { id: 7, path: '/srv/archive', name: 'Archive' },
        { id: 8, path: '/srv/archive/deep', name: 'Deep archive' },
        { id: 9, path: '/home/alice/projects', name: 'Projects' },
    ];

    assert.equal(
        helpers.favoritePhysicalToVirtualPath('/home/alice', '/home/alice', locations),
        '',
        'the home directory itself maps to the tree root',
    );
    assert.equal(
        helpers.favoritePhysicalToVirtualPath('/home/alice/docs', '/home/alice', locations),
        'docs',
    );
    assert.equal(
        helpers.favoriteVirtualToPhysicalPath('', '/home/alice', locations),
        '/home/alice',
        'the tree root maps back to the physical home directory',
    );
    assert.equal(
        helpers.favoriteVirtualToPhysicalPath('docs', '/home/alice', locations),
        '/home/alice/docs',
    );
    assert.equal(
        helpers.favoritePhysicalToVirtualPath('/home/alice-other/docs', '/home/alice', locations),
        null,
        'a shared string prefix is not a home-directory containment match',
    );
    assert.equal(
        helpers.favoritePhysicalToVirtualPath('/srv/archive-old', '/home/alice', locations),
        null,
        'a shared string prefix is not an external-location containment match',
    );
    assert.equal(
        helpers.favoritePhysicalToVirtualPath('/home/alice//docs', '/home/alice', locations),
        null,
        'a malformed physical path is not rendered as an absolute tree path',
    );

    assert.equal(
        helpers.favoritePhysicalToVirtualPath('/srv/archive', '/home/alice', locations),
        '@ext/7',
    );
    assert.equal(
        helpers.favoritePhysicalToVirtualPath('/srv/archive/notes/today', '/home/alice', locations),
        '@ext/7/notes/today',
    );
    assert.equal(
        helpers.favoriteVirtualToPhysicalPath('@ext/7/notes/today', '/home/alice', locations),
        '/srv/archive/notes/today',
    );
    assert.equal(
        helpers.favoritePhysicalToVirtualPath('/srv/archive/deep/report', '/home/alice', locations),
        '@ext/8/report',
        'the most specific overlapping external location wins',
    );
    assert.equal(
        helpers.favoritePhysicalToVirtualPath('/home/alice/projects/app', '/home/alice', locations),
        '@ext/9/app',
        'a more specific external location wins over the home root',
    );
    assert.equal(
        helpers.favoritePhysicalToVirtualPath('/unavailable/folder', '/home/alice', locations),
        null,
        'unknown physical paths are not rendered as broken relative paths',
    );
    assert.equal(
        helpers.favoriteVirtualToPhysicalPath('@ext/99/missing', '/home/alice', locations),
        null,
        'unknown external virtual paths are not sent to the API',
    );
    assert.equal(
        helpers.favoriteVirtualToPhysicalPath('@ext/7/../escape', '/home/alice', locations),
        null,
    );
    assert.equal(
        helpers.favoritePhysicalToVirtualPath('/var/log', '/', []),
        'var/log',
        'the filesystem root is a valid home root',
    );
    assert.equal(
        helpers.favoriteVirtualToPhysicalPath('var/log', '/', []),
        '/var/log',
    );

    assert.equal(
        helpers.externalLocationForFavoriteRoot('@ext/7', locations).id,
        7,
    );
    assert.equal(
        helpers.externalLocationForFavoriteRoot('@ext/7/notes', locations),
        null,
        'only the exact external root is a removable location',
    );
    assert.equal(
        helpers.externalLocationForFavoritePath('@ext/7/notes', locations).id,
        7,
        'external favorite descendants reuse their registered location metadata',
    );
    assert.equal(
        helpers.externalLocationForFavoritePath('@ext/99/missing', locations),
        null,
        'unknown external virtual paths have no registered location metadata',
    );

    assert.deepEqual(
        helpers.mapFavoritePaths(
            [
                { path: '/home/alice/docs' },
                { path: '/srv/archive' },
                { path: '/srv/archive/deep/report' },
                { path: '/unavailable/folder' },
                { path: '/home/alice/docs/' },
            ],
            '/home/alice',
            locations,
        ),
        ['docs', '@ext/7', '@ext/8/report'],
    );
    assert.deepEqual(
        helpers.mergeFavoritePaths(['docs', '@ext/7'], locations),
        ['docs', '@ext/7', '@ext/8', '@ext/9'],
        'registered locations are synthesized once rather than persisted as duplicates',
    );
    assert.deepEqual(
        helpers.orderFavoritePaths(
            ['docs', '@ext/7', '@ext/8'],
            ['@ext/8', 'missing', 'docs'],
        ),
        ['@ext/8', 'docs', '@ext/7'],
        'drag ordering remains client-only while new paths are appended',
    );
}

async function testController(helpers) {
    const initialLoad = deferred();
    const addResult = deferred();
    let addCalls = 0;
    let removeCalls = 0;
    const states = [];
    const controller = helpers.createFavoritesController({
        loadFavorites: () => initialLoad.promise,
        addFavorite: (path) => {
            addCalls += 1;
            assert.equal(path, '/home/alice/work');
            return addResult.promise;
        },
        removeFavorite: () => {
            removeCalls += 1;
            return Promise.reject(new Error('network failure'));
        },
        onChange: (state) => states.push(state),
    });

    controller.activate('alice');
    assert.equal(
        await controller.toggle('alice', '/home/alice/work'),
        false,
        'a favorite cannot mutate before its authenticated list has loaded',
    );
    assert.equal(addCalls, 0);

    initialLoad.resolve([]);
    await waitFor(() => states.some((state) => state.loaded), 'initial favorites did not load');

    const firstAdd = controller.toggle('alice', '/home/alice/work');
    assert.equal(
        await controller.toggle('alice', '/home/alice/work'),
        false,
        'the same in-flight favorite action is not duplicated',
    );
    await waitFor(() => addCalls === 1, 'the add request was not made');
    addResult.resolve({ path: '/home/alice/work' });
    assert.equal(await firstAdd, true);
    assert.deepEqual(states.at(-1), {
        paths: ['/home/alice/work'],
        loaded: true,
    });

    assert.equal(
        await controller.toggle('alice', '/home/alice/work'),
        false,
        'a failed delete does not optimistically remove the favorite',
    );
    assert.equal(removeCalls, 1);
    assert.deepEqual(states.at(-1), {
        paths: ['/home/alice/work'],
        loaded: true,
    });
}

async function testStaleIdentityGuards(helpers) {
    const loads = [];
    const states = [];
    const staleMutation = deferred();
    let addCalls = 0;
    const controller = helpers.createFavoritesController({
        loadFavorites: () => {
            const result = deferred();
            loads.push(result);
            return result.promise;
        },
        addFavorite: () => {
            addCalls += 1;
            return staleMutation.promise;
        },
        removeFavorite: () => Promise.resolve({ ok: true }),
        onChange: (state) => states.push(state),
    });

    controller.activate('alice');
    await waitFor(() => loads.length === 1, 'alice load did not start');
    controller.activate('bob');
    await waitFor(() => loads.length === 2, 'bob load did not start');

    loads[0].resolve([{ path: '/home/alice/old' }]);
    loads[1].resolve([{ path: '/home/bob/current' }]);
    await waitFor(
        () => states.at(-1)?.loaded,
        'bob favorites did not finish loading',
    );
    assert.deepEqual(states.at(-1), {
        paths: ['/home/bob/current'],
        loaded: true,
    }, 'an old identity load cannot overwrite the current identity');

    const aliceLoad = deferred();
    const secondStates = [];
    const secondController = helpers.createFavoritesController({
        loadFavorites: () => aliceLoad.promise,
        addFavorite: () => {
            addCalls += 1;
            return staleMutation.promise;
        },
        removeFavorite: () => Promise.resolve({ ok: true }),
        onChange: (state) => secondStates.push(state),
    });
    secondController.activate('alice');
    aliceLoad.resolve([]);
    await waitFor(() => secondStates.at(-1)?.loaded, 'alice favorites did not load');

    const pendingMutation = secondController.toggle('alice', '/home/alice/work');
    await waitFor(() => addCalls === 1, 'alice mutation did not start');
    secondController.activate('bob');
    staleMutation.resolve({ path: '/home/alice/work' });
    assert.equal(
        await pendingMutation,
        false,
        'a mutation response from an old identity is discarded',
    );
    assert.equal(
        secondStates.some((state) => state.paths.includes('/home/alice/work')),
        false,
        'the old mutation cannot publish into the next identity state',
    );

    const unmountLoad = deferred();
    let unmountLoadStarted = false;
    const unmountStates = [];
    const unmountController = helpers.createFavoritesController({
        loadFavorites: () => {
            unmountLoadStarted = true;
            return unmountLoad.promise;
        },
        addFavorite: () => Promise.resolve({ path: '/home/alice/work' }),
        removeFavorite: () => Promise.resolve({ ok: true }),
        onChange: (state) => unmountStates.push(state),
    });
    const unmountSession = unmountController.activate('alice');
    await waitFor(() => unmountLoadStarted, 'unmount load did not start');
    unmountController.deactivate(unmountSession);
    unmountLoad.resolve([{ path: '/home/alice/ignored' }]);
    await new Promise((resolve) => setImmediate(resolve));
    assert.deepEqual(
        unmountStates,
        [{ paths: [], loaded: false }],
        'an unmounted favorites controller ignores its pending load result',
    );
}

async function main() {
    const layoutSource = fs.readFileSync(LAYOUT_FILE, 'utf8');
    const helperSource = fs.readFileSync(HELPERS_FILE, 'utf8');
    assert.equal(layoutSource.includes('fb-favorites'), false);
    assert.equal(helperSource.includes('localStorage'), false);

    const helpers = await loadHelpers();
    await testPathMapping(helpers);
    await testController(helpers);
    await testStaleIdentityGuards(helpers);
    process.stdout.write('favorites helper tests passed\n');
}

main().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});