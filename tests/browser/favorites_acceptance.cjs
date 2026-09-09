'use strict';

// Run only against the isolated fixture prepared by tests/fixtures/favorites.
// This harness intentionally owns one browser and one browser context at a time.
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const net = require('node:net');
const path = require('node:path');
const { spawn } = require('node:child_process');

const REPO_ROOT = path.resolve(__dirname, '..', '..');
const WORK_DIR = path.join(REPO_ROOT, '.work');
const LEDGER_FILE = path.join(WORK_DIR, 'resources.json');
const FINAL_FILE = path.join(WORK_DIR, 'browser-final.json');
const LOCK_FILE = path.join(WORK_DIR, 'favorites-browser.lock');
const RUN_SERVER = path.join(REPO_ROOT, 'tests', 'fixtures', 'favorites', 'run_server.sh');
const RUN_LIMIT_MS = 9 * 60 * 1000;
const ACTION_TIMEOUT_MS = 15_000;
const MAX_STARTUP_OUTPUT_BYTES = 64 * 1024;
const deadline = Date.now() + RUN_LIMIT_MS;
const results = [];
const commands = [];
const screenshots = [];
const storeSnapshots = [];
const runId = `favorites-${new Date().toISOString().replace(/[:.]/g, '-')}-${process.pid}`;
const screenshotDir = path.join(WORK_DIR, 'browser-artifacts', runId);
let ledger;
let server;
let browserEntry;
let baseUrl;
let port;
let ownedServerPid = null;
let serverOutput = '';
let browser = null;
let activeContext = null;
let cleanupPromise = null;
let lockFd = null;
let ownsLedger = false;
function remaining() {
    const ms = deadline - Date.now();
    assert(ms > 0, 'overall browser acceptance deadline exceeded');
    return ms;
}
function command(commandText, result) {
    const entry = { at: new Date().toISOString(), command: commandText, result };
    commands.push(entry);
    console.log(`COMMAND ${commandText} => ${result}`);
}
function writeLedger() {
    fs.writeFileSync(LEDGER_FILE, `${JSON.stringify(ledger, null, 2)}\n`);
}
function updateServer(status, updates = {}) {
    Object.assign(server, updates, { status });
    writeLedger();
}
function updateBrowser(status) {
    Object.assign(browserEntry, { status, run_id: runId });
    writeLedger();
}
function isAlive(pid) {
    try {
        process.kill(pid, 0);
        return true;
    } catch (error) {
        if (error.code === 'ESRCH') return false;
        throw error;
    }
}
function processCommandLine(pid) {
    const commandLine = fs.readFileSync(`/proc/${pid}/cmdline`, 'utf8').replace(/\0/g, ' ');
    command(`read /proc/${pid}/cmdline`, commandLine || 'empty');
    return commandLine;
}
function appendServerOutput(data) {
    // Keep draining child pipes after startup without retaining access logs for
    // the full acceptance run.
    if (serverOutput === null || serverOutput.length >= MAX_STARTUP_OUTPUT_BYTES) return;
    serverOutput += data.toString().slice(0, MAX_STARTUP_OUTPUT_BYTES - serverOutput.length);
}
function assertFixtureProcess(pid) {
    assert(Number.isInteger(pid) && pid > 1, `invalid fixture PID: ${pid}`);
    assert(isAlive(pid), `recorded fixture PID ${pid} is not live`);
    const commandLine = processCommandLine(pid);
    let procCwd = '';
    try { procCwd = fs.readlinkSync(`/proc/${pid}/cwd`); } catch {}
    assert(commandLine.includes(REPO_ROOT) || procCwd === REPO_ROOT, `PID ${pid} is not from this worktree`);
    assert(commandLine.includes('tests.fixtures.favorites.fixture_app'), `PID ${pid} is not fixture_app`);
    assert(new RegExp(`--port\\s+${port}(?:\\s|$)`).test(commandLine), 'fixture command port differs from ledger');
}
function assertFixtureListener(pid) {
    assertFixtureProcess(pid);
    const sockets = new Set(fs.readdirSync(`/proc/${pid}/fd`).flatMap((fd) => {
        try {
            const target = fs.readlinkSync(`/proc/${pid}/fd/${fd}`);
            const match = /^socket:\[(\d+)\]$/.exec(target);
            return match ? [match[1]] : [];
        } catch { return []; }
    }));
    const expected = `0100007F:${port.toString(16).toUpperCase().padStart(4, '0')}`;
    const ownsPort = fs.readFileSync(`/proc/${pid}/net/tcp`, 'utf8').split('\n').some((line) => {
        const fields = line.trim().split(/\s+/);
        return fields[1] === expected && fields[3] === '0A' && sockets.has(fields[9]);
    });
    assert(ownsPort, `fixture PID ${pid} does not own the loopback listener`);
}
function portOpen() {
    return new Promise((resolve) => {
        const socket = net.connect({ host: '127.0.0.1', port });
        let settled = false;
        const finish = (open) => {
            if (settled) return;
            settled = true;
            socket.off('connect', onConnect);
            socket.off('error', onError);
            socket.off('timeout', onTimeout);
            socket.destroy();
            resolve(open);
        };
        const onConnect = () => finish(true);
        const onError = () => finish(false);
        const onTimeout = () => finish(false);
        // Preserve an error listener through destroy so a reset immediately
        // after a successful connect is not reported as uncaught.
        socket.on('error', () => {});
        socket.once('connect', onConnect);
        socket.once('error', onError);
        socket.setTimeout(750, onTimeout);
    });
}
async function waitFor(predicate, message, timeout = ACTION_TIMEOUT_MS) {
    const until = Date.now() + Math.min(timeout, remaining());
    let lastError;
    while (Date.now() < until) {
        try {
            const result = await predicate();
            if (result) return result;
        } catch (error) {
            lastError = error;
        }
        await new Promise((resolve) => setTimeout(resolve, 100));
    }
    throw new Error(`${message}${lastError ? `: ${lastError.message}` : ''}`);
}
async function waitForPort(open, message) {
    await waitFor(() => portOpen().then((actual) => actual === open), message, 20_000);
    command(`wait for ${server.address} ${open ? 'open' : 'closed'}`, 'ok');
}
async function stopOwnedServer(reason) {
    if (!ownedServerPid) return;
    const pid = ownedServerPid;
    if (isAlive(pid)) {
        assertFixtureProcess(pid);
        command(`kill -TERM ${pid}`, reason);
        process.kill(pid, 'SIGTERM');
        await waitFor(() => !isAlive(pid), `fixture PID ${pid} did not exit`, 20_000);
    }
    await waitForPort(false, 'fixture port remained open after stop');
    ownedServerPid = null;
}
async function startOwnedServer(previousPid) {
    assert(!await portOpen(), 'refusing to spawn fixture while its port is still live');
    const pythonBin = process.env.PYTHON_BIN;
    assert(pythonBin, 'PYTHON_BIN must be set before a fixture-server restart');
    updateServer('planned', { pid: null, previous_pid: previousPid });
    command(`${RUN_SERVER} (PYTHON_BIN=${pythonBin}, FILEBROWSER_TEST_PORT=${port})`, 'spawning');
    serverOutput = '';
    const serverChild = spawn(RUN_SERVER, [], {
        cwd: REPO_ROOT,
        env: { ...process.env, PYTHON_BIN: pythonBin, FILEBROWSER_TEST_PORT: String(port) },
        stdio: ['ignore', 'pipe', 'pipe'],
    });
    serverChild.stdout.on('data', appendServerOutput);
    serverChild.stderr.on('data', appendServerOutput);
    serverChild.once('error', (error) => { appendServerOutput(`\nspawn error: ${error.message}`); });
    assert(serverChild.pid, 'fixture spawn returned no PID');
    ownedServerPid = serverChild.pid;
    await waitForPort(true, 'spawned fixture did not listen');
    await waitFor(
        () => serverOutput.includes(`Fixture filebrowser module: ${server.worktree_source_proof}`),
        'spawned fixture did not prove its worktree module source',
        20_000,
    );
    serverOutput = null;
    assertFixtureProcess(ownedServerPid);
    assertFixtureListener(ownedServerPid);
    updateServer('active', { pid: ownedServerPid, source_proof: server.worktree_source_proof });
    command(`${RUN_SERVER}`, `PID ${ownedServerPid} listening with source proof`);
}
async function restartServer() {
    assert(ownedServerPid, 'cannot restart an unowned fixture server');
    const oldPid = ownedServerPid;
    await stopOwnedServer('restart');
    assert(!isAlive(oldPid) && !await portOpen(), 'old fixture remains live; refusing a second app process');
    await startOwnedServer(oldPid);
}
async function openContext() {
    assert(browser && !activeContext, 'only one browser context may be open');
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    context.setDefaultTimeout(Math.min(ACTION_TIMEOUT_MS, remaining()));
    activeContext = context;
    return context.newPage();
}
async function closeContext() {
    if (!activeContext) return;
    await activeContext.close();
    activeContext = null;
}
async function api(page, method, url, body) {
    const response = await page.evaluate(async ({ method: verb, url: endpoint, body: requestBody }) => {
        const response = await fetch(endpoint, {
            method: verb,
            credentials: 'same-origin',
            headers: requestBody === undefined ? {} : { 'Content-Type': 'application/json' },
            body: requestBody === undefined ? undefined : JSON.stringify(requestBody),
        });
        const text = await response.text();
        let payload;
        try { payload = text ? JSON.parse(text) : null; } catch { payload = text; }
        return { status: response.status, payload };
    }, { method, url, body });
    command(`${method} ${url}`, `HTTP ${response.status}`);
    return response;
}
async function favorites(page) {
    const response = await api(page, 'GET', '/api/favorites');
    assert.equal(response.status, 200, 'favorites probe failed');
    return response.payload;
}
async function locations(page) {
    const response = await api(page, 'GET', '/api/locations');
    assert.equal(response.status, 200, 'locations probe failed');
    return response.payload;
}
function userStore(username) {
    return path.join(
        WORK_DIR,
        'test-data',
        'favorites-users',
        `${crypto.createHash('sha256').update(username, 'utf8').digest('hex')}.json`,
    );
}
async function assertFavoriteStore(page, username, expectedPaths) {
    const apiPaths = (await favorites(page)).map((entry) => entry.path);
    const diskPaths = JSON.parse(fs.readFileSync(userStore(username), 'utf8')).favorites.map((entry) => entry.path);
    assert.deepEqual(apiPaths, expectedPaths, `${username} favorites API mismatch`);
    assert.deepEqual(diskPaths, expectedPaths, `${username} favorites disk store mismatch`);
    storeSnapshots.push({ username, api: apiPaths, disk: diskPaths, at: new Date().toISOString() });
}
async function login(page, username) {
    await page.goto(baseUrl, { waitUntil: 'domcontentloaded', timeout: remaining() });
    await page.locator('#fb-username').fill(username);
    await page.locator('#fb-password').fill('password123');
    const loaded = page.waitForResponse((response) => response.url() === `${baseUrl}/api/favorites`
        && response.request().method() === 'GET' && response.status() === 200);
    await page.getByRole('button', { name: 'Sign In', exact: true }).click();
    await page.locator(`.username:text-is("${username}")`).waitFor({ state: 'visible' });
    await loaded;
    await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
}
async function logout(page) {
    await page.locator('.logout-btn').click();
    await page.locator('#fb-username').waitFor({ state: 'visible' });
}
function rootFolder(page, name) {
    return page.locator(`.file-tree .tree-folder[title="${name}"]`).first();
}
function rootFile(page, name) {
    return page.locator(`.file-tree .tree-file[title="${name}"]`).first();
}
async function contextAction(page, target, action) {
    await target.click({ button: 'right' });
    const menu = page.locator('.context-menu');
    await menu.waitFor({ state: 'visible', timeout: 5000 });
    const item = menu.locator('button.context-menu-item', { hasText: action });
    await item.waitFor({ state: 'visible' });
    await item.click();
}
function favoriteFolder(page, name) {
    return page.locator(`.favorites-section .favorites-item[title="${name}"]`);
}
async function ensureAlphaPinned(page, alphaPath) {
    await rootFolder(page, 'alpha').waitFor({ state: 'visible' });
    await unpinIfPresent(page, 'alpha');
    await contextAction(page, rootFolder(page, 'alpha'), 'Pin to favorites');
    await favoriteFolder(page, 'alpha').waitFor({ state: 'visible' });
    await assertFavoriteStore(page, 'alice', [alphaPath]);
}
async function unpinIfPresent(page, name) {
    const pinned = favoriteFolder(page, name);
    if (await pinned.count()) {
        await pinned.first().hover();
        const btn = pinned.locator('.favorites-unpin').first();
        await btn.waitFor({ state: 'visible', timeout: 3000 });
        await btn.click();
        await waitFor(() => pinned.count().then((count) => count === 0), `${name} did not unpin through the UI`);
    }
}
async function screenshot(page, label) {
    fs.mkdirSync(screenshotDir, { recursive: true });
    const file = path.join(screenshotDir, `${label}.png`);
    await page.screenshot({ path: file, fullPage: true });
    screenshots.push(file);
}
async function preview(page, name, selector) {
    await rootFile(page, name).click();
    await page.locator(`.file-info-name:text-is("${name}")`).waitFor({ state: 'visible' });
    await page.locator(selector).waitFor({ state: 'visible', timeout: Math.min(30_000, remaining()) });
    await screenshot(page, name.replace(/\W/g, '_'));
}
async function scenario(name, work) {
    const started = Date.now();
    try {
        await work();
        results.push({ name, status: 'pass', duration_ms: Date.now() - started });
        console.log(`SCENARIO PASS ${name}`);
    } catch (error) {
        results.push({ name, status: 'fail', duration_ms: Date.now() - started, error: error.stack || error.message });
        console.error(`SCENARIO FAIL ${name}:`, error);
        throw error;
    }
}
async function initialize() {
    assert(process.env.PYTHON_BIN, 'PYTHON_BIN must be set before this restart-capable harness runs');
    // Reserve exclusively before inspecting or mutating the resource ledger.
    // A stale lock requires explicit operator inspection; never steal it.
    lockFd = fs.openSync(LOCK_FILE, 'wx', 0o600);
    fs.writeSync(lockFd, `${process.pid}\n`);
    ledger = JSON.parse(fs.readFileSync(LEDGER_FILE, 'utf8'));
    server = ledger.resources.find((resource) => resource.kind === 'fixture-server');
    browserEntry = ledger.resources.find((resource) => resource.kind === 'browser');
    assert(server && browserEntry, 'fixture and browser resources must exist in .work/resources.json');
    assert.equal(browserEntry.status, 'closed', 'browser ledger must start closed');
    const [host, portText] = server.address.split(':');
    assert.equal(host, '127.0.0.1', 'fixture server must bind to loopback');
    port = Number(portText);
    assert(Number.isInteger(port) && port > 0 && port <= 65_535, 'fixture server has an invalid port');
    baseUrl = `http://${server.address}`;
    assert(fs.existsSync(server.worktree_source_proof), 'fixture worktree source proof is absent');
    assert.equal(path.resolve(server.worktree_source_proof), path.join(REPO_ROOT, 'filebrowser', '__init__.py'));
    ownsLedger = true;
    if (server.status === 'stopped' || !server.pid || !isAlive(server.pid)) {
        await startOwnedServer(server.pid || server.previous_pid || null);
    } else {
        assert.equal(server.status, 'active', 'fixture server ledger must start active');
        assertFixtureProcess(server.pid);
        assertFixtureListener(server.pid);
        ownedServerPid = server.pid;
    }
    updateBrowser('reserved');
    command('reserve browser ledger', browserEntry.id || 'reserved');
}
async function cleanup() {
    if (cleanupPromise) return cleanupPromise;
    cleanupPromise = (async () => {
        let cleanupFailure = null;
        const attempt = async (label, action) => {
            try {
                await action();
                return true;
            } catch (error) {
                cleanupFailure ??= error;
                console.error(`CLEANUP FAIL ${label}`, error);
                return false;
            }
        };

        await attempt('browser context', closeContext);
        const browserClosed = await attempt('browser', async () => {
            if (!browser) return;
            await browser.close();
            browser = null;
            command('browser.close', 'ok');
        });
        const serverStopped = await attempt('fixture server', () => stopOwnedServer('final teardown'));
        if (serverStopped && ownsLedger && server) {
            await attempt('fixture server ledger', () => updateServer('stopped', { pid: null }));
        }
        if (browserClosed && ownsLedger && browserEntry) {
            await attempt('browser ledger', () => updateBrowser('closed'));
        }
        return cleanupFailure;
    })();
    return cleanupPromise;
}
for (const [signal, exitCode] of [['SIGINT', 130], ['SIGTERM', 143]]) {
    process.once(signal, () => {
        void cleanup().finally(() => process.exit(exitCode));
    });
}
async function main() {
    let failure;
    let cleanupFailure;
    try {
        await initialize();
        await waitForPort(true, 'recorded fixture server is not listening');
        const playwrightModule = process.env.PLAYWRIGHT_MODULE || require.resolve('playwright');
        const { chromium } = require(playwrightModule);
        const executablePath = process.env.BROWSER_EXECUTABLE || undefined;
        command(`require(${playwrightModule})`, 'loaded');
        browser = await chromium.launch({ headless: true, executablePath, timeout: remaining() });
        command('chromium.launch', 'ok');

        const alphaPath = path.join(WORK_DIR, 'test-home', 'alpha');
        const betaPath = path.join(WORK_DIR, 'test-home', 'beta');
        const externalPath = path.join(WORK_DIR, 'test-external');
        const legacyFile = path.join(WORK_DIR, 'test-data', 'favorites.json');
        const legacyBytes = fs.readFileSync(legacyFile);
        let page = await openContext();

        await scenario('Alice pins alpha without changing legacy browser or disk state', async () => {
            await page.goto(baseUrl, { waitUntil: 'domcontentloaded', timeout: remaining() });
            await page.evaluate(() => localStorage.setItem('fb-favorites', JSON.stringify(['legacy-only'])));
            await login(page, 'alice');
            await ensureAlphaPinned(page, alphaPath);
            assert.equal(
                await page.evaluate(() => localStorage.getItem('fb-favorites')),
                JSON.stringify(['legacy-only']),
                'legacy browser storage changed',
            );
            assert.equal(await favoriteFolder(page, 'legacy-only').count(), 0);
            const duplicate = await api(page, 'POST', '/api/favorites', { path: alphaPath });
            assert.equal(duplicate.status, 200);
            await assertFavoriteStore(page, 'alice', [alphaPath]);
        });

        await scenario('Alice favorites survive logout and a fresh browser context', async () => {
            await logout(page);
            await login(page, 'alice');
            await favoriteFolder(page, 'alpha').waitFor({ state: 'visible' });
            await assertFavoriteStore(page, 'alice', [alphaPath]);
            await closeContext();
            page = await openContext();
            await login(page, 'alice');
            assert.equal(await page.evaluate(() => localStorage.getItem('fb-favorites')), null);
            await favoriteFolder(page, 'alpha').waitFor({ state: 'visible' });
            await assertFavoriteStore(page, 'alice', [alphaPath]);
            await screenshot(page, 'alice-fresh-context');
        });

        await scenario('Bob cannot see or alter Alice favorites', async () => {
            await logout(page);
            await login(page, 'bob');
            assert.equal(await favoriteFolder(page, 'alpha').count(), 0, 'Bob UI leaked Alice alpha');
            await screenshot(page, 'bob-isolated');
            let bobFavorites = await favorites(page);
            assert.equal(bobFavorites.some((entry) => entry.path === alphaPath), false, 'Bob received Alice alpha');
            if (bobFavorites.some((entry) => entry.path === betaPath)) await unpinIfPresent(page, 'beta');
            bobFavorites = await favorites(page);
            assert.deepEqual(bobFavorites, [], 'Bob should start with no personal favorites');
            const removeAlice = await api(page, 'DELETE', `/api/favorites?path=${encodeURIComponent(alphaPath)}`);
            assert.equal(removeAlice.status, 404, 'Bob could delete Alice alpha');
            await contextAction(page, rootFolder(page, 'beta'), 'Pin to favorites');
            await assertFavoriteStore(page, 'bob', [betaPath]);
            await unpinIfPresent(page, 'beta');
            await assertFavoriteStore(page, 'bob', []);
            await logout(page);
            await login(page, 'alice');
            await assertFavoriteStore(page, 'alice', [alphaPath]);
        });

        await scenario('Alice favorite data survives restart and durable removal', async () => {
            await closeContext();
            await restartServer();
            page = await openContext();
            await login(page, 'alice');
            await favoriteFolder(page, 'alpha').waitFor({ state: 'visible' });
            await assertFavoriteStore(page, 'alice', [alphaPath]);
            await screenshot(page, 'alice-after-restart');
            await unpinIfPresent(page, 'alpha');
            await assertFavoriteStore(page, 'alice', []);
            await closeContext();
            await restartServer();
            page = await openContext();
            await login(page, 'alice');
            assert.equal(await favoriteFolder(page, 'alpha').count(), 0);
            await assertFavoriteStore(page, 'alice', []);
            assert.deepEqual(fs.readFileSync(legacyFile), legacyBytes, 'legacy favorites.json bytes changed');
            await screenshot(page, 'alice-durable-unpin');
        });

        await scenario('External location is synthesized, not a personal favorite', async () => {
            let beforeLocations = await locations(page);
            let external = beforeLocations.find((location) => location.path === externalPath);
            if (!external) {
                const addRes = await api(page, 'POST', '/api/locations', { path: externalPath, name: 'test-external' });
                assert.equal(addRes.status, 200, 'failed to register external location');
                await page.reload({ waitUntil: 'domcontentloaded' });
                beforeLocations = await locations(page);
                external = beforeLocations.find((location) => location.path === externalPath);
            }
            assert(external, `registered external location is missing: ${externalPath}`);
            assert.deepEqual(await favorites(page), [], 'registered location leaked into personal favorites API');
            const root = page.locator(`.favorites-section .favorites-item[title="@ext/${external.id}"]`);
            await root.waitFor({ state: 'visible' });
            await root.click();
            const sub = page.locator('.favorites-section .tree-folder[title="sub"]').first();
            await sub.waitFor({ state: 'visible' });
            await contextAction(page, sub, 'Pin to favorites');
            await assertFavoriteStore(page, 'alice', [path.join(externalPath, 'sub')]);
            await contextAction(page, page.locator('.favorites-section .tree-folder[title="sub"]').first(), 'Unpin from favorites');
            await assertFavoriteStore(page, 'alice', []);
            assert.deepEqual(await locations(page), beforeLocations, 'pinning a location child changed locations');
            await contextAction(page, root, 'Remove location');
            await waitFor(async () => !(await locations(page)).some((location) => location.path === externalPath), 'location was not removed');
            await page.locator('[title="Add Folder"]').click();
            const modal = page.locator('.add-location-modal');
            await modal.locator('.modal-label input').nth(0).fill(externalPath);
            await modal.locator('.modal-label input').nth(1).fill(external.name);
            await modal.getByRole('button', { name: 'Add', exact: true }).click();
            const restored = await waitFor(async () => (await locations(page)).find(
                (location) => location.path === externalPath && location.name === external.name,
            ), 'Add Folder did not restore the external location');
            await page.locator(`.favorites-section .favorites-item[title="@ext/${restored.id}"]`).click();
            await page.locator('.favorites-section .tree-file[title="ext_info.txt"]').click();
            await page.locator('.file-info-name:text-is("ext_info.txt")').waitFor({ state: 'visible' });
            await screenshot(page, 'browse');
        });

        await scenario('Fixture previews render without terminal interaction', async () => {
            await preview(page, 'notes.txt', '.editable-viewer');
            await preview(page, 'script.py', '.editable-viewer');
            await preview(page, 'readme.md', '.markdown-viewer');
            await preview(page, 'sample.png', '.image-viewer img[alt="sample.png"]');
            await preview(page, 'graph.dot', '.graphviz-canvas svg');
            assert.equal(await page.locator('.terminal-container').count(), 0);
        });
    } catch (error) {
        failure = error;
    } finally {
        cleanupFailure = await cleanup();
        const passed = results.filter((result) => result.status === 'pass').length;
        const failed = results.filter((result) => result.status === 'fail').length;
        fs.writeFileSync(FINAL_FILE, `${JSON.stringify({
            run_id: runId,
            status: failure || cleanupFailure ? 'fail' : 'pass',
            counts: { passed, failed, total: results.length },
            results,
            screenshots,
            store_snapshots: storeSnapshots,
            notes: ['External child rendering is captured in browse.png; cosmetic tree labels are not mutated.'],
            commands,
            error: (failure || cleanupFailure)?.stack || null,
        }, null, 2)}\n`);
        console.log(`RESULT COUNTS pass=${passed} fail=${failed} total=${results.length}`);
        if (lockFd !== null) {
            fs.closeSync(lockFd);
            fs.unlinkSync(LOCK_FILE);
        }
    }
    if (failure) throw failure;
    if (cleanupFailure) throw cleanupFailure;
}
main().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});