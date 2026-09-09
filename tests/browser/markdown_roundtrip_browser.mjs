#!/usr/bin/env node
/**
 * Executable regression driver for Markdown safety & roundtrip browser testing.
 *
 * Tests:
 * 1. Served module integrity (SHA256 match between disk and HTTP)
 * 2. Lossy construct preservation & rich edit blocking (image, code, table, tasklist, sample)
 * 3. Exact original no-edit equality via CodeMirror EditorView.findFromDOM
 * 4. Safe source prose edit (REPLACE prose), PUT payload, disk, and reopen equality
 * 5. Canonical plain Markdown rich edit: EDIT in WYSIWYG + SAVE + REOPEN
 * 6. Pending PUT race A: save snapshot then edit before response (draft must stay dirty, second save persists)
 * 7. Pending PUT race B: save file A switch file B then release response (B must not corrupt)
 * 8. Direct mount harness: same-component switch buffer sync
 */

import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { execFileSync, spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import os from 'node:os';
import net from 'node:net';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const REPO_ROOT = path.resolve(__dirname, '../..');
// The override makes the startup-failure regression hermetic. Runtime fixture
// paths still use the worktree-local .work directory by default.
const WORK_DIR = path.resolve(process.env.MARKDOWN_ROUNDTRIP_WORK_DIR || path.join(REPO_ROOT, '.work'));
const RUN_ID = `markdown-roundtrip-${process.pid}-${crypto.randomBytes(8).toString('hex')}`;
const RUN_ROOT = path.join(WORK_DIR, 'markdown-roundtrip-browser', RUN_ID);
const TEST_HOME = path.join(RUN_ROOT, 'home');
const TEST_DATA = path.join(RUN_ROOT, 'data');
const SCREENSHOTS_DIR = path.join(RUN_ROOT, 'screenshots');
const EVIDENCE_FILE = path.join(RUN_ROOT, 'evidence.json');
const LOCK_FILE = path.join(WORK_DIR, 'markdown-roundtrip-browser.lock');
const SERVER_SCRIPT = path.join(REPO_ROOT, 'tests/browser/markdown_roundtrip_server.py');
const PYTHON_BIN = process.env.PYTHON_BIN;
let BASE_URL = null;
const SESSION = `${RUN_ID}-browser`;
let browserStarted = false;
let browserPids = {};
let fixture = null;
let fixtureOutput = '';
let fixturePort = null;
let lockFd = null;
const report = {
    timestamp: new Date().toISOString(),
    server_url: null,
    session_id: SESSION,
    driver_sha256: sha256(fs.readFileSync(__filename)),
    modules_verified: false,
    module_details: [],
    tests: {},
};

function log(msg) {
    console.log(`[driver] ${msg}`);
}

function validatePythonBin() {
    if (!PYTHON_BIN || !path.isAbsolute(PYTHON_BIN)) {
        throw new Error('PYTHON_BIN must be an existing executable absolute interpreter path');
    }
    try {
        if (!fs.statSync(PYTHON_BIN).isFile()) {
            throw new Error('not a regular file');
        }
        fs.accessSync(PYTHON_BIN, fs.constants.X_OK);
    } catch (error) {
        throw new Error(`PYTHON_BIN must be an existing executable absolute interpreter path: ${error.message}`);
    }
}

function assertSafeWorkPath(candidate) {
    const absolute = path.resolve(candidate);
    if (absolute === WORK_DIR || !absolute.startsWith(`${WORK_DIR}${path.sep}`)) {
        throw new Error(`Fixture path must remain under this worktree's .work directory: ${absolute}`);
    }
    for (let current = absolute; current !== path.dirname(WORK_DIR); current = path.dirname(current)) {
        if (fs.existsSync(current) && fs.lstatSync(current).isSymbolicLink()) {
            throw new Error(`Fixture path must not traverse a symlink: ${current}`);
        }
        if (current === WORK_DIR) break;
    }
    return absolute;
}

function ensureLedger() {
    const resourcesPath = path.resolve(WORK_DIR, 'resources.json');
    assertSafeWorkPath(resourcesPath);
    if (!fs.existsSync(resourcesPath)) fs.writeFileSync(resourcesPath, '{\n  "resources": []\n}\n', { mode: 0o600 });
    return { resourcesPath, data: JSON.parse(fs.readFileSync(resourcesPath, 'utf-8')) };
}

function runBrowser(args) {
    const fullArgs = ['--session', SESSION, ...args];
    try {
        const stdout = execFileSync('agent-browser', fullArgs, {
            encoding: 'utf-8',
            timeout: 30000,
        });
        return stdout.trim();
    } catch (err) {
        throw new Error(`agent-browser ${fullArgs.join(' ')} failed: ${err.message}\n${err.stderr || ''}`);
    }
}

/**
 * Execute JS in page and parse JSON result ONCE (never second-parse user source strings).
 */
function browserEval(js) {
    let code = js.trim();
    if (code.includes('await ') && !code.startsWith('(async') && !code.startsWith('async')) {
        code = `(async () => { return (${code}); })()`;
    }
    const raw = runBrowser(['eval', code]);
    if (!raw || raw === 'undefined' || raw === 'null') return null;
    try {
        return JSON.parse(raw);
    } catch {
        return raw;
    }
}

function sha256(content) {
    return crypto.createHash('sha256').update(content).digest('hex');
}

function updateLedger(status, pid = null, daemon_pid = null, result = null) {
    const { resourcesPath, data } = ensureLedger();
    let entry = data.resources.find(r => r.name === RUN_ID);
    if (!entry) {
        entry = { name: RUN_ID, kind: 'browser', type: 'agent-browser-session' };
        data.resources.push(entry);
    }
    Object.assign(entry, { status, pid, daemon_pid, result,
        session_id: SESSION, address: BASE_URL,
        teardown: `agent-browser --session ${SESSION} close` });
    fs.writeFileSync(resourcesPath, JSON.stringify(data, null, 2) + '\n', 'utf-8');
}

function updateFixtureLedger(status, result = null) {
    const { resourcesPath, data } = ensureLedger();
    let entry = data.resources.find(r => r.name === `${RUN_ID}-fixture`);
    if (!entry) {
        entry = { name: `${RUN_ID}-fixture`, kind: 'fixture-server', type: 'local-synthetic-fixture' };
        data.resources.push(entry);
    }
    Object.assign(entry, {
        status, pid: fixture?.pid ?? null, address: BASE_URL, home: TEST_HOME, data: TEST_DATA,
        source: REPO_ROOT, result, teardown: fixture?.pid ? `kill -TERM ${fixture.pid}` : 'completed',
    });
    fs.writeFileSync(resourcesPath, JSON.stringify(data, null, 2) + '\n', 'utf-8');
}

async function findFreeLoopbackPort() {
    const probe = net.createServer();
    await new Promise((resolve, reject) => {
        probe.once('error', reject);
        probe.listen(0, '127.0.0.1', resolve);
    });
    const address = probe.address();
    await new Promise((resolve, reject) => probe.close(error => error ? reject(error) : resolve()));
    if (!address || typeof address === 'string') throw new Error('Could not reserve a loopback fixture port');
    return address.port;
}

function isAlive(pid) {
    try { process.kill(pid, 0); return true; }
    catch (error) { if (error.code === 'ESRCH') return false; throw error; }
}

async function waitFor(predicate, message, timeoutMs = 20_000) {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
        if (await predicate()) return;
        await new Promise(resolve => setTimeout(resolve, 100));
    }
    throw new Error(message);
}

function assertOwnedFixture() {
    if (!fixture?.pid || !isAlive(fixture.pid)) throw new Error('Owned fixture process is not live');
    const cmdline = fs.readFileSync(`/proc/${fixture.pid}/cmdline`, 'utf8').replace(/\0/g, ' ');
    if (!cmdline.includes(SERVER_SCRIPT) || !fixtureOutput.includes(`Fixture home: ${TEST_HOME}`)
        || !fixtureOutput.includes(`Fixture data: ${TEST_DATA}`)
        || !fixtureOutput.includes(`Fixture source: ${REPO_ROOT}`)) {
        throw new Error('Fixture did not attest its PID, isolated paths, and worktree source');
    }
}

async function startOwnedFixture() {
    for (const fixturePath of [RUN_ROOT, TEST_HOME, TEST_DATA, EVIDENCE_FILE, SCREENSHOTS_DIR]) {
        assertSafeWorkPath(fixturePath);
    }
    fs.mkdirSync(path.dirname(RUN_ROOT), { recursive: true, mode: 0o700 });
    assertSafeWorkPath(path.dirname(RUN_ROOT));
    fs.mkdirSync(RUN_ROOT, { recursive: false, mode: 0o700 });
    fs.mkdirSync(TEST_HOME, { mode: 0o700 });
    fs.mkdirSync(TEST_DATA, { mode: 0o700 });
    fixturePort = await findFreeLoopbackPort();
    BASE_URL = `http://127.0.0.1:${fixturePort}`;
    report.server_url = BASE_URL;
    fixture = spawn(PYTHON_BIN, [SERVER_SCRIPT], {
        cwd: REPO_ROOT,
        env: {
            ...process.env, HOME: TEST_HOME, FILEBROWSER_FIXTURE_HOME: TEST_HOME,
            FILEBROWSER_FIXTURE_DATA: TEST_DATA, FILEBROWSER_TEST_PORT: String(fixturePort),
            PYTHONDONTWRITEBYTECODE: '1', PYTHONPATH: REPO_ROOT,
        },
        stdio: ['ignore', 'pipe', 'pipe'],
    });
    fixture.stdout.on('data', data => { fixtureOutput += data.toString(); });
    fixture.stderr.on('data', data => { fixtureOutput += data.toString(); });
    updateFixtureLedger('starting');
    await waitFor(() => {
        if (fixture.exitCode !== null) {
            throw new Error(`Owned fixture exited before startup: ${fixtureOutput}`);
        }
        return fixtureOutput.includes(`Uvicorn running on ${BASE_URL}`);
    }, 'Owned fixture did not start on its loopback address', 60_000);
    assertOwnedFixture();
    updateFixtureLedger('running', 'PID, HOME, data, and source attested');
}

async function stopOwnedFixture() {
    if (!fixture?.pid) return;
    if (isAlive(fixture.pid)) {
        process.kill(fixture.pid, 'SIGTERM');
        await waitFor(() => !isAlive(fixture.pid), `Fixture PID ${fixture.pid} did not exit`);
    }
    updateFixtureLedger('closed', 'PID exited');
}

function findSessionPids() {
    try {
        const homeDir = os.homedir();
        const pidFile = path.join(homeDir, '.agent-browser', `${SESSION}.pid`);
        let daemon_pid = null;
        let pid = null;
        if (fs.existsSync(pidFile)) {
            daemon_pid = parseInt(fs.readFileSync(pidFile, 'utf-8').trim(), 10);
            try {
                const childPids = execFileSync('pgrep', ['-P', String(daemon_pid)], { encoding: 'utf-8' }).trim().split('\n');
                for (const cp of childPids) {
                    const cpid = parseInt(cp.trim(), 10);
                    if (!isNaN(cpid)) {
                        pid = cpid;
                        break;
                    }
                }
            } catch {}
        }
        return { pid, daemon_pid };
    } catch {
        return { pid: null, daemon_pid: null };
    }
}

async function verifyServedModules() {
    log('Verifying served modules SHA256 integrity...');
    const modules = [
        { disk: 'filebrowser/static/js/components/markdown-editor.js', url: `${BASE_URL}/js/components/markdown-editor.js` },
        { disk: 'filebrowser/static/js/components/preview.js', url: `${BASE_URL}/js/components/preview.js` },
        { disk: 'filebrowser/static/js/components/wysiwyg-editor.js', url: `${BASE_URL}/js/components/wysiwyg-editor.js` },
        { disk: 'filebrowser/static/js/lib/markdown-roundtrip.js', url: `${BASE_URL}/js/lib/markdown-roundtrip.js` }
    ];

    const results = [];
    for (const mod of modules) {
        const diskContent = fs.readFileSync(path.join(REPO_ROOT, mod.disk), 'utf-8');
        const diskHash = sha256(diskContent);
        const resp = await fetch(mod.url);
        if (!resp.ok) throw new Error(`Failed to fetch ${mod.url}: ${resp.status}`);
        const httpContent = await resp.text();
        const httpHash = sha256(httpContent);
        results.push({
            file: mod.disk,
            url: mod.url,
            disk_sha256: diskHash,
            http_sha256: httpHash,
            matches: diskHash === httpHash
        });
    }
    return results;
}

function installBrowserHelpers() {
    const script = `(() => {
        if (!window.__driverHelpersInstalled) {
            window.__putRecords = [];
            window.__holdPuts = false;
            window.__pendingPuts = [];
            window.__failPutContents = new Set();
            window.__releasePendingPut = function(index) {
                const pending = window.__pendingPuts[index];
                if (!pending) throw new Error('No pending PUT at index ' + index);
                pending.resolve();
            };
            window.__releaseAllPendingPuts = function() {
                window.__pendingPuts.forEach(pending => pending.resolve());
                window.__pendingPuts = [];
            };

            const origFetch = window.fetch;
            window.fetch = async function(...args) {
                const [url, opts] = args;
                if (opts && opts.method === 'PUT' && typeof url === 'string' && url.includes('/api/files/content')) {
                    let body = null;
                    try { body = opts.body ? JSON.parse(opts.body) : null; } catch (e) { body = opts.body; }
                    window.__putRecords.push({ url, body, time: Date.now() });
                    if (window.__failPutContents.has(body?.content)) {
                        throw new Error('Injected PUT failure for ' + body.content);
                    }
                    if (window.__holdPuts) {
                        await new Promise((resolve) => {
                            window.__pendingPuts.push({ resolve, body });
                        });
                    }
                }
                return origFetch.apply(this, args);
            };

            window.__openFile = async function(filePath) {
                // Click directory folder if needed
                if (filePath.includes('/')) {
                    const parts = filePath.split('/');
                    const folderName = parts[0];
                    let folderEl = null;
                    for (let i = 0; i < 30; i++) {
                        folderEl = Array.from(document.querySelectorAll('.tree-item.tree-folder'))
                            .find(el => el.textContent.includes(folderName));
                        if (folderEl) break;
                        await new Promise(r => setTimeout(r, 50));
                    }
                    if (folderEl && !folderEl.classList.contains('expanded')) {
                        folderEl.click();
                        for (let i = 0; i < 30; i++) {
                            if (folderEl.classList.contains('expanded')) break;
                            await new Promise(r => setTimeout(r, 50));
                        }
                    }
                }
                const fileName = filePath.split('/').pop();
                let fileEl = null;
                for (let i = 0; i < 40; i++) {
                    fileEl = Array.from(document.querySelectorAll('.tree-item.tree-file'))
                        .find(el => el.textContent.includes(fileName));
                    if (fileEl) break;
                    await new Promise(r => setTimeout(r, 50));
                }
                if (!fileEl) throw new Error("Could not find file element in tree for: " + filePath);
                fileEl.click();
                // Wait for editor tabs to mount
                for (let i = 0; i < 40; i++) {
                    if (document.querySelector('.markdown-editor-tabs')) break;
                    await new Promise(r => setTimeout(r, 50));
                }
                await new Promise(r => setTimeout(r, 200));
                return true;
            };

            window.__clickTab = async function(name) {
                let btn = null;
                for (let i = 0; i < 30; i++) {
                    const btns = Array.from(document.querySelectorAll('.markdown-editor-tabs button'));
                    btn = btns.find(b => b.textContent.includes(name));
                    if (btn) break;
                    await new Promise(r => setTimeout(r, 50));
                }
                if (!btn) throw new Error("Tab button not found: " + name);
                btn.click();
                if (name === 'Source') {
                    for (let i = 0; i < 40; i++) {
                        if (document.querySelector('.cm-editor')) break;
                        await new Promise(r => setTimeout(r, 50));
                    }
                }
                await new Promise(r => setTimeout(r, 200));
                return true;
            };

            window.__clickSave = function() {
                const btn = document.querySelector('.edit-bar-save') || document.querySelector('.btn-save');
                if (!btn) throw new Error("Save button not found in UI");
                btn.click();
            };

            window.__isDirty = function() {
                const btn = document.querySelector('.markdown-editor-tabs button.active');
                return !!btn?.querySelector('.markdown-dirty-indicator');
            };

            window.__getCodeMirrorDoc = async function() {
                const mod = await import('@codemirror/view');
                for (let i = 0; i < 40; i++) {
                    const cmEl = document.querySelector('.cm-editor');
                    if (cmEl) {
                        const view = mod.EditorView.findFromDOM(cmEl);
                        if (view && view.state && view.state.doc) {
                            return view.state.doc.toString();
                        }
                    }
                    await new Promise(r => setTimeout(r, 50));
                }
                return null;
            };

            window.__setCodeMirrorDoc = async function(newText) {
                const mod = await import('@codemirror/view');
                const cmEl = document.querySelector('.cm-editor');
                if (!cmEl) throw new Error("CodeMirror .cm-editor not found");
                const view = mod.EditorView.findFromDOM(cmEl);
                if (!view) throw new Error("EditorView.findFromDOM returned null");
                view.dispatch({
                    changes: { from: 0, to: view.state.doc.length, insert: newText }
                });
                return true;
            };

            window.__getWysiwygHtml = function() {
                const el = document.querySelector('.wysiwyg-content');
                return el ? el.innerHTML : null;
            };

            window.__typeWysiwygProse = function(textToAppend) {
                const el = document.querySelector('.wysiwyg-content');
                if (!el) throw new Error(".wysiwyg-content not found");
                const p = document.createElement('p');
                p.textContent = textToAppend;
                el.appendChild(p);
                el.dispatchEvent(new Event('input', { bubbles: true }));
                return true;
            };

            window.__driverHelpersInstalled = true;
        }
        return true;
    })()`;
    browserEval(script);
}

function syncFixturesToTestHome() {
    log('Restoring synthetic fixture files into test_home/docs...');
    const fixturesDir = path.join(REPO_ROOT, 'tests/fixtures/markdown_roundtrip');
    const docsDir = path.join(TEST_HOME, 'docs');
    fs.mkdirSync(docsDir, { recursive: true });
    for (const file of fs.readdirSync(fixturesDir)) {
        fs.copyFileSync(path.join(fixturesDir, file), path.join(docsDir, file));
    }
}

async function runSuite() {
    syncFixturesToTestHome();

    // 1. Verify Served Modules
    try {
        const modRes = await verifyServedModules();
        report.module_details = modRes;
        report.modules_verified = modRes.every(m => m.matches);
        log(`Module integrity verified: ${report.modules_verified}`);
    } catch (err) {
        log(`Module integrity check failed: ${err.message}`);
        report.module_details = [{ error: err.message }];
    }
    if (!report.modules_verified) throw new Error('Served editor modules do not match this worktree');

    // Open App
    log(`Opening browser session ${SESSION} at ${BASE_URL}...`);
    updateLedger('launching');
    browserStarted = true;
    runBrowser(['open', BASE_URL]);
    runBrowser(['wait', '2000']);
    browserPids = findSessionPids();
    const { pid, daemon_pid } = browserPids;
    updateLedger('running', pid, daemon_pid);
    installBrowserHelpers();

    async function selectFile(relPath) {
        browserEval(`(async () => await window.__openFile(${JSON.stringify(relPath)}))()`);
        runBrowser(['wait', '300']);
    }

    // 2. Test Lossy Construct Protection & CodeMirror Exact Oracle (Source -> Edit -> Source)
    const lossyFixtures = [
        { file: 'image.md', construct: 'image' },
        { file: 'fenced_code.md', construct: 'fenced_code' },
        { file: 'table.md', construct: 'table' },
        { file: 'task_list.md', construct: 'task_list' },
        { file: 'sample.md', construct: 'combined' },
    ];

    for (const fixture of lossyFixtures) {
        log(`Testing construct protection for ${fixture.file}...`);
        await selectFile(`docs/${fixture.file}`);

        const originalDisk = fs.readFileSync(path.join(TEST_HOME, 'docs', fixture.file), 'utf-8');

        // Step 1: Explicitly switch to Source tab first to verify baseline
        browserEval(`(async () => await window.__clickTab('Source'))()`);
        const sourceDocInitial = browserEval(`(async () => await window.__getCodeMirrorDoc())()`);

        // Step 2: Click Edit tab (trigger rich conversion attempt)
        browserEval(`(async () => await window.__clickTab('Edit'))()`);
        runBrowser(['wait', '600']);

        // Check notice and active tab (must fall back to source)
        const noticeText = browserEval(`document.querySelector('.markdown-rich-edit-notice')?.textContent?.trim() || null`);
        const activeTab = browserEval(`document.querySelector('.markdown-editor-tabs button.active')?.textContent?.trim() || null`);

        // Step 3: Exact CodeMirror Oracle check
        const cmDoc = browserEval(`(async () => await window.__getCodeMirrorDoc())()`);

        const blocked = noticeText && noticeText.includes('Rich editing blocked');
        const fallbackToSource = activeTab && activeTab.includes('Source');
        const exactOriginal = cmDoc === originalDisk && sourceDocInitial === originalDisk;

        const pass = blocked && fallbackToSource && exactOriginal;
        report.tests[`lossy_protection_${fixture.construct}`] = {
            file: fixture.file,
            construct: fixture.construct,
            rich_blocked: blocked,
            active_tab_after_attempt: activeTab,
            in_memory_source_exact_match: exactOriginal,
            status: pass ? 'PASS' : 'FAIL',
            notice: noticeText
        };
        log(`  -> ${fixture.file}: blocked=${blocked}, sourceExactMatch=${exactOriginal}, status=${pass ? 'PASS' : 'FAIL'}`);
    }

    // 3. Explicit rich block then safe source prose edit + PUT + disk + reopen equality
    // Requirement: Nearby prose REPLACE (not merely append) for combined fixture
    log('Testing rich block then safe source prose REPLACE & roundtrip equality on sample.md...');
    {
        const file = 'sample.md';
        await selectFile(`docs/${file}`);
        const originalDisk = fs.readFileSync(path.join(TEST_HOME, 'docs', file), 'utf-8');

        fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });

        // Capture 1: View tab screenshot
        browserEval(`(async () => await window.__clickTab('View'))()`);
        runBrowser(['wait', '600']);
        runBrowser(['screenshot', path.join(SCREENSHOTS_DIR, 'view.png')]);

        // Click Edit to verify rich block triggers
        browserEval(`(async () => await window.__clickTab('Edit'))()`);
        runBrowser(['wait', '600']);

        // Capture 2: Rich blocked screenshot
        runBrowser(['screenshot', path.join(SCREENSHOTS_DIR, 'rich_blocked.png')]);

        // Verify it landed back on Source
        browserEval(`(async () => await window.__clickTab('Source'))()`);
        runBrowser(['wait', '600']);

        // REPLACE prose: find introductory prose and replace it with edited version
        const targetProse = "This introductory prose describes the product inventory and operational guidelines.";
        const replacementProse = "This verified replacement prose tests exact in-place editing of safe prose without touching complex constructs.";
        if (!originalDisk.includes(targetProse)) {
            throw new Error(`Target prose not found in ${file}`);
        }
        const intendedContent = originalDisk.replace(targetProse, replacementProse);

        // Update CodeMirror doc
        browserEval(`window.__setCodeMirrorDoc(${JSON.stringify(intendedContent)})`);
        runBrowser(['wait', '500']);

        // Capture 3: Edited Source screenshot
        runBrowser(['screenshot', path.join(SCREENSHOTS_DIR, 'source_edited.png')]);

        const inMemoryBeforeSave = browserEval(`window.__getCodeMirrorDoc()`);

        // Clear PUT records then click save
        browserEval(`window.__putRecords = [];`);
        browserEval(`window.__clickSave()`);
        runBrowser(['wait', '1200']);

        const putRecords = browserEval(`window.__putRecords`);
        const lastPut = Array.isArray(putRecords) && putRecords.length ? putRecords[putRecords.length - 1] : null;

        // Check disk content
        const savedDisk = fs.readFileSync(path.join(TEST_HOME, 'docs', file), 'utf-8');

        // Reopen file: switch to plain.md then back to sample.md
        await selectFile('docs/plain.md');
        await selectFile(`docs/${file}`);
        browserEval(`(async () => await window.__clickTab('Source'))()`);
        runBrowser(['wait', '600']);
        const reopenedSource = browserEval(`window.__getCodeMirrorDoc()`);

        // Capture 4: Saved Reopen screenshot
        runBrowser(['screenshot', path.join(SCREENSHOTS_DIR, 'saved_reopen.png')]);

        const putMatch = lastPut?.body?.content === intendedContent;
        const diskMatch = savedDisk === intendedContent;
        const inMemMatch = inMemoryBeforeSave === intendedContent;
        const reopenMatch = reopenedSource === intendedContent;

        const allMatch = putMatch && diskMatch && inMemMatch && reopenMatch;
        report.tests['safe_source_prose_replace_roundtrip'] = {
            file,
            target_prose_replaced: true,
            in_memory_before_save_matches: inMemMatch,
            put_payload_matches: putMatch,
            disk_content_matches: diskMatch,
            reopened_source_matches: reopenMatch,
            original_sha256: sha256(originalDisk),
            expected_sha256: sha256(intendedContent),
            observed_disk_sha256: sha256(savedDisk),
            observed_reopen_sha256: sha256(reopenedSource || ''),
            original_text: originalDisk,
            expected_text: intendedContent,
            observed_disk_text: savedDisk,
            observed_reopened_text: reopenedSource,
            status: allMatch ? 'PASS' : 'FAIL'
        };
        log(`  -> safe_source_prose_replace_roundtrip: status=${allMatch ? 'PASS' : 'FAIL'} (put=${putMatch}, disk=${diskMatch}, reopen=${reopenMatch})`);
    }

    // 4. Canonical Plain Markdown Rich Edit: EDIT in WYSIWYG + SAVE + REOPEN
    log('Testing canonical plain Markdown rich edit: edit in WYSIWYG + save + reopen...');
    {
        const file = 'plain.md';
        await selectFile(`docs/${file}`);
        const originalDisk = fs.readFileSync(path.join(TEST_HOME, 'docs', file), 'utf-8');

        browserEval(`(async () => await window.__clickTab('Edit'))()`);
        runBrowser(['wait', '600']);

        const notice = browserEval(`document.querySelector('.markdown-rich-edit-notice')?.textContent || null`);
        const activeTab = browserEval(`document.querySelector('.markdown-editor-tabs button.active')?.textContent?.trim() || null`);

        // Perform edit inside WYSIWYG editor
        browserEval(`window.__typeWysiwygProse('Appended rich paragraph from WYSIWYG editor test.')`);
        runBrowser(['wait', '600']);

        const isDirtyAfterEdit = browserEval(`window.__isDirty()`);

        // Save
        browserEval(`window.__putRecords = [];`);
        browserEval(`window.__clickSave()`);
        runBrowser(['wait', '1200']);

        const putRecords = browserEval(`window.__putRecords`);
        const lastPut = Array.isArray(putRecords) && putRecords.length ? putRecords[putRecords.length - 1] : null;

        // Verify disk content was updated
        const savedDisk = fs.readFileSync(path.join(TEST_HOME, 'docs', file), 'utf-8');
        const originalSuffix = originalDisk.match(/\n*$/)[0];
        const originalBody = originalDisk.slice(0, originalDisk.length - originalSuffix.length);
        const expectedPlainContent = originalBody + '\n\nAppended rich paragraph from WYSIWYG editor test.' + originalSuffix;
        const diskExactMatch = savedDisk === expectedPlainContent;
        const putExactMatch = lastPut?.body?.content === expectedPlainContent;

        // Reopen file
        await selectFile('docs/image.md');
        await selectFile(`docs/${file}`);
        browserEval(`(async () => await window.__clickTab('Source'))()`);
        runBrowser(['wait', '600']);
        const reopenedSource = browserEval(`window.__getCodeMirrorDoc()`);
        const reopenExactMatch = reopenedSource === expectedPlainContent;

        const richSuccess = !notice && activeTab?.includes('Edit') && isDirtyAfterEdit && putExactMatch && diskExactMatch && reopenExactMatch;
        report.tests['canonical_plain_rich_edit'] = {
            file,
            rich_notice_absent: !notice,
            stayed_in_edit_tab: activeTab?.includes('Edit'),
            marked_dirty: isDirtyAfterEdit,
            put_dispatched: !!lastPut,
            put_exact_match: putExactMatch,
            disk_exact_match: diskExactMatch,
            reopen_exact_match: reopenExactMatch,
            original_sha256: sha256(originalDisk),
            expected_sha256: sha256(expectedPlainContent),
            observed_disk_sha256: sha256(savedDisk),
            observed_reopen_sha256: sha256(reopenedSource || ''),
            original_text: originalDisk,
            expected_text: expectedPlainContent,
            observed_disk_text: savedDisk,
            observed_reopened_text: reopenedSource,
            status: richSuccess ? 'PASS' : 'FAIL'
        };
        log(`  -> canonical_plain_rich_edit: status=${richSuccess ? 'PASS' : 'FAIL'}`);
    }

    // 5. Race A: Save Snapshot then Edit again before response
    // Must assert: newer exact draft + dirty + second saved/reopen
    log('Testing Race A: edit while save is pending (draft dirty persistence)...');
    {
        const file = 'file_a.md';
        await selectFile(`docs/${file}`);
        browserEval(`window.__clickTab('Source')`);
        runBrowser(['wait', '500']);

        const draft1 = "# File A\n\nFirst edit.";
        const draft2 = "# File A\n\nFirst edit.\n\nSecond edit in-flight.";

        // 1. First edit
        browserEval(`window.__setCodeMirrorDoc(${JSON.stringify(draft1)})`);
        runBrowser(['wait', '300']);

        // 2. Hold PUTs
        browserEval(`window.__holdPuts = true;`);

        // 3. Trigger Save (this PUT will be held in __pendingPuts)
        browserEval(`window.__clickSave()`);
        runBrowser(['wait', '400']);

        // 4. Make second edit while save is in flight
        browserEval(`window.__setCodeMirrorDoc(${JSON.stringify(draft2)})`);
        runBrowser(['wait', '300']);

        const pendingCount = browserEval(`window.__pendingPuts.length`);

        // 5. Release held PUT
        browserEval(`
            window.__holdPuts = false;
            window.__releaseAllPendingPuts();
        `);
        runBrowser(['wait', '1200']);

        // Check if editor retained dirty state and kept in-flight edit
        const dirtyAfterFirstPutResolves = browserEval(`window.__isDirty()`);
        const inMemoryDocOnAck = browserEval(`window.__getCodeMirrorDoc()`);

        // In fixed implementation, dirty must be true and a second save persists draft2
        let secondSaveSucceeded = false;
        let reopenedDoc = null;
        if (dirtyAfterFirstPutResolves) {
            browserEval(`window.__clickSave()`);
            runBrowser(['wait', '1200']);
            const savedDisk = fs.readFileSync(path.join(TEST_HOME, 'docs', file), 'utf-8');
            secondSaveSucceeded = savedDisk === draft2;

            // Reopen file to verify persistent disk state via browser
            await selectFile('docs/plain.md');
            await selectFile(`docs/${file}`);
            browserEval(`(async () => await window.__clickTab('Source'))()`);
            runBrowser(['wait', '600']);
            reopenedDoc = browserEval(`window.__getCodeMirrorDoc()`);
        }

        const reopenMatchesDraft2 = reopenedDoc === draft2;
        const raceAPassed = pendingCount === 1 && dirtyAfterFirstPutResolves && secondSaveSucceeded && inMemoryDocOnAck === draft2 && reopenMatchesDraft2;
        report.tests['race_save_inflight_edit'] = {
            file,
            pending_put_held: pendingCount > 0,
            in_memory_doc_on_ack_matches_draft2: inMemoryDocOnAck === draft2,
            remained_dirty_after_put_resolved: dirtyAfterFirstPutResolves,
            second_save_persisted: secondSaveSucceeded,
            reopened_doc_matches_draft2: reopenMatchesDraft2,
            draft1,
            draft2,
            observed_in_memory_on_ack: inMemoryDocOnAck,
            observed_reopened: reopenedDoc,
            status: raceAPassed ? 'PASS' : 'FAIL',
            observation: raceAPassed
                ? 'PASS: In-flight edit remained dirty, second save persisted draft2, and reopened file matches draft2'
                : 'FAIL: Rescued draft cleared dirty flag when earlier save resolved, dropping dirty tracking for in-flight edit'
        };
        log(`  -> race_save_inflight_edit: status=${report.tests['race_save_inflight_edit'].status}`);
    }

    // 6. Per-path save locks: A remains locked while B settles or fails.
    log('Testing per-path save locks across A and B...');
    {
        await selectFile('docs/file_a.md');
        browserEval(`(async () => await window.__clickTab('Source'))()`);
        runBrowser(['wait', '500']);

        const fileAOriginal = fs.readFileSync(path.join(TEST_HOME, 'docs', 'file_a.md'), 'utf-8');
        const fileBOriginal = fs.readFileSync(path.join(TEST_HOME, 'docs', 'file_b.md'), 'utf-8');
        const modA = "# File A\n\nModified A content pending save.";
        browserEval(`window.__setCodeMirrorDoc(${JSON.stringify(modA)})`);
        runBrowser(['wait', '300']);

        // Hold PUT
        browserEval(`window.__putRecords = [];`);
        browserEval(`window.__holdPuts = true;`);
        browserEval(`window.__clickSave()`);
        runBrowser(['wait', '400']);

        // Start B while A remains held, then settle B first. B must not clear
        // A's lock merely because it became the current file.
        browserEval(`(async () => await window.__openFile('docs/file_b.md'))()`);
        runBrowser(['wait', '800']);
        const heldBeforeRelease = browserEval(`window.__pendingPuts.length`);
        browserEval(`(async () => await window.__clickTab('Source'))()`);
        const modB = '# File B\n\nSaved B while A remains pending.';
        browserEval(`window.__setCodeMirrorDoc(${JSON.stringify(modB)})`);
        browserEval(`window.__clickSave()`);
        const bPutIssued = browserEval(`(async () => {
            const until = Date.now() + 5000;
            while (Date.now() < until) {
                if (window.__pendingPuts.length === 2) return true;
                await new Promise(r => setTimeout(r, 50));
            }
            return false;
        })()`);
        browserEval(`window.__holdPuts = false; window.__releasePendingPut(1);`);
        const bSettledFirst = browserEval(`(async () => {
            const until = Date.now() + 5000;
            while (Date.now() < until) {
                const button = document.querySelector('.edit-bar-save');
                if (button && !button.textContent.includes('Saving')) return true;
                await new Promise(r => setTimeout(r, 50));
            }
            return false;
        })()`);

        // A failed B save also must not clear A's lock.
        const failedB = '# File B\n\nFailed B while A remains pending.';
        browserEval(`window.__setCodeMirrorDoc(${JSON.stringify(failedB)})`);
        browserEval(`window.__failPutContents.add(${JSON.stringify(failedB)}); window.__clickSave();`);
        const bFailureSettled = browserEval(`(async () => {
            const until = Date.now() + 5000;
            while (Date.now() < until) {
                const button = document.querySelector('.edit-bar-save');
                if (button && !button.textContent.includes('Saving')) return true;
                await new Promise(r => setTimeout(r, 50));
            }
            return false;
        })()`);
        const bSaveFailureRecorded = browserEval(`window.__putRecords.length === 3`);

        // Reopen A before allowing the original PUT to reach the server.  This
        // deliberately returns the old on-disk A and is the regression setup.
        await selectFile('docs/file_a.md');
        browserEval(`(async () => await window.__clickTab('Source'))()`);
        runBrowser(['wait', '600']);
        const staleABeforeRelease = browserEval(`window.__getCodeMirrorDoc()`);
        const staleASaveDisabled = browserEval(`(() => {
            const button = document.querySelector('.edit-bar-save');
            return !!button && button.disabled;
        })()`);
        const blockedDraft = `${fileAOriginal}\n\nAttempted stale follow-up.`;
        browserEval(`window.__setCodeMirrorDoc(${JSON.stringify(blockedDraft)})`);
        runBrowser(['wait', '200']);
        browserEval(`window.__clickSave()`);
        runBrowser(['wait', '200']);
        const putsBeforeRelease = browserEval(`window.__putRecords.length`);

        // Release A only after both opposite-order B settlement and B failure.
        browserEval(`
            window.__releasePendingPut(0);
        `);
        const aReconciled = browserEval(`(async () => {
            const until = Date.now() + 5000;
            while (Date.now() < until) {
                if (await window.__getCodeMirrorDoc() === ${JSON.stringify(modA)}) return true;
                await new Promise(r => setTimeout(r, 50));
            }
            return false;
        })()`);
        const savedA = fs.readFileSync(path.join(TEST_HOME, 'docs', 'file_a.md'), 'utf-8');
        const reconciledA = browserEval(`window.__getCodeMirrorDoc()`);

        // Then prove that the original B view was not changed by A's settled
        // response either.
        await selectFile('docs/file_b.md');
        browserEval(`(async () => await window.__clickTab('Source'))()`);
        runBrowser(['wait', '500']);
        const currentDoc = browserEval(`window.__getCodeMirrorDoc()`);
        const matchesFileB = currentDoc === fileBOriginal;

        // After A has settled while B was current, reopening A must not retain
        // the transient save lock.  A normal subsequent save must be possible.
        await selectFile('docs/file_a.md');
        browserEval(`(async () => await window.__clickTab('Source'))()`);
        runBrowser(['wait', '500']);
        const postSettleDraft = `${modA}\n\nNormal post-settle edit.`;
        browserEval(`window.__setCodeMirrorDoc(${JSON.stringify(postSettleDraft)})`);
        browserEval(`window.__clickSave()`);
        const postSettleSaveIssued = browserEval(`(async () => {
            const until = Date.now() + 5000;
            while (Date.now() < until) {
                if (window.__putRecords.length === 4) return true;
                await new Promise(r => setTimeout(r, 50));
            }
            return false;
        })()`);
        const postSettleComplete = browserEval(`(async () => {
            const until = Date.now() + 5000;
            while (Date.now() < until) {
                const button = document.querySelector('.edit-bar-save');
                if (button && !button.textContent.includes('Saving')) return true;
                await new Promise(r => setTimeout(r, 50));
            }
            return false;
        })()`);
        const postSettleSaved = fs.readFileSync(path.join(TEST_HOME, 'docs', 'file_a.md'), 'utf-8');
        const raceBPassed = heldBeforeRelease === 1
            && bPutIssued === true
            && bSettledFirst === true
            && bFailureSettled === true
            && bSaveFailureRecorded === true
            && staleABeforeRelease === fileAOriginal
            && staleASaveDisabled === true
            && putsBeforeRelease === 3
            && aReconciled === true
            && savedA === modA
            && reconciledA === modA
            && currentDoc === modB
            && postSettleSaveIssued === true
            && postSettleComplete === true
            && postSettleSaved === postSettleDraft;
        report.tests['race_per_path_save_locks'] = {
            held_put_verified: heldBeforeRelease > 0,
            b_put_issued: bPutIssued,
            b_settled_before_a: bSettledFirst,
            b_failure_settled: bFailureSettled,
            b_failure_recorded: bSaveFailureRecorded,
            stale_reopen_observed: staleABeforeRelease === fileAOriginal,
            stale_a_save_disabled: staleASaveDisabled,
            stale_follow_up_save_blocked: putsBeforeRelease === 3,
            puts_before_release: putsBeforeRelease,
            file_a_saved_exactly: savedA === modA,
            reopened_a_reconciled: aReconciled,
            reopened_a_reconciled_exactly: reconciledA === modA,
            file_b_expected: modB,
            file_b_observed: currentDoc,
            matches_file_b: currentDoc === modB,
            post_settle_save_issued: postSettleSaveIssued,
            post_settle_save_completed: postSettleComplete,
            post_settle_save_exact: postSettleSaved === postSettleDraft,
            status: raceBPassed ? 'PASS' : 'FAIL',
            observation: raceBPassed
                ? 'PASS: B settlement/failure did not unlock A; A reconciled only after its own PUT settled'
                : 'FAIL: per-path save locks did not preserve A through B activity'
        };
        log(`  -> race_per_path_save_locks: status=${report.tests['race_per_path_save_locks'].status}`);
    }

    // 7. Direct Mount Harness: same-component switch buffer sync & external text replacement
    log('Testing Direct Mount Harness for same-component switch & external text update...');
    {
        runBrowser(['open', `${BASE_URL}/test-harness`]);
        runBrowser(['wait', '1500']);

        const harnessResult = browserEval(`(async () => {
            const mod = await import('@codemirror/view');

            async function getEditorView(timeout = 5000) {
                const start = Date.now();
                while (Date.now() - start < timeout) {
                    const el = document.querySelector('.cm-editor');
                    if (el) {
                        try {
                            const v = mod.EditorView.findFromDOM(el);
                            if (v) return v;
                        } catch {}
                    }
                    await new Promise(r => setTimeout(r, 100));
                }
                return null;
            }

            // Mount 1: file A
            window.__mountEditor({ text: '# Doc A\\n\\nOriginal A.', path: 'a.md' });
            await new Promise(r => setTimeout(r, 600));

            // Switch to Source tab
            const btns1 = Array.from(document.querySelectorAll('.markdown-editor-tabs button'));
            const srcBtn1 = btns1.find(b => b.textContent.includes('Source'));
            if (!srcBtn1) return JSON.stringify({ error: "Source button not found on mount 1" });
            srcBtn1.click();

            const view1 = await getEditorView(5000);
            const doc1 = view1 ? view1.state.doc.toString() : null;

            // Mount 2: file B with same mounted component
            // Root wrapper resets tab to View on file path change, so driver clicks Source
            window.__mountEditor({ text: '# Doc B\\n\\nOriginal B.', path: 'b.md' });
            await new Promise(r => setTimeout(r, 600));

            // Switch to Source tab for file B
            const btns2 = Array.from(document.querySelectorAll('.markdown-editor-tabs button'));
            const srcBtn2 = btns2.find(b => b.textContent.includes('Source'));
            if (srcBtn2) srcBtn2.click();

            const view2 = await getEditorView(5000);
            const doc2 = view2 ? view2.state.doc.toString() : null;

            // Mount 3: same path 'b.md', external text update
            window.__mountEditor({ text: '# Doc B\\n\\nExternally updated B.', path: 'b.md' });
            await new Promise(r => setTimeout(r, 600));

            // Verify CodeMirror doc in Source tab reflects external update
            let view3 = await getEditorView(5000);
            if (!view3) {
                const btns3 = Array.from(document.querySelectorAll('.markdown-editor-tabs button'));
                const srcBtn3 = btns3.find(b => b.textContent.includes('Source'));
                if (srcBtn3) srcBtn3.click();
                view3 = await getEditorView(5000);
            }
            const doc3 = view3 ? view3.state.doc.toString() : null;

            return JSON.stringify({
                doc1,
                doc2,
                doc3,
                synced_path_switch: doc2 === '# Doc B\\n\\nOriginal B.',
                synced_same_path_update: doc3 === '# Doc B\\n\\nExternally updated B.'
            });
        })()`);

        let parsedHarness = typeof harnessResult === 'object' ? harnessResult : {};
        if (typeof harnessResult === 'string') {
            try { parsedHarness = JSON.parse(harnessResult); } catch {}
        }

        const pathSwitchSynced = parsedHarness.synced_path_switch === true;
        const samePathSynced = parsedHarness.synced_same_path_update === true;

        report.tests['direct_mount_switch'] = {
            doc1: parsedHarness.doc1,
            doc2: parsedHarness.doc2,
            buffer_synced: pathSwitchSynced,
            status: pathSwitchSynced ? 'PASS' : 'FAIL'
        };
        report.tests['direct_mount_same_path_text_update'] = {
            doc2: parsedHarness.doc2,
            doc3: parsedHarness.doc3,
            same_path_update_synced: samePathSynced,
            status: samePathSynced ? 'PASS' : 'FAIL'
        };
        log(`  -> direct_mount_switch: status=${pathSwitchSynced ? 'PASS' : 'FAIL'}`);
        log(`  -> direct_mount_same_path_text_update: status=${samePathSynced ? 'PASS' : 'FAIL'}`);
    }

    // 8. Direct Mount Harness: same-path external reload keeps save lock until pending PUT settles
    log('Testing Direct Mount Harness for same-path external reload save lock...');
    {
        runBrowser(['open', `${BASE_URL}/test-harness`]);
        runBrowser(['wait', '1000']);

        const harnessResult = browserEval(`(async () => {
            const mod = await import('@codemirror/view');
            const { api } = await import('/js/api.js');

            async function getEditorView(timeout = 5000) {
                const start = Date.now();
                while (Date.now() - start < timeout) {
                    const el = document.querySelector('.cm-editor');
                    if (el) {
                        try {
                            const v = mod.EditorView.findFromDOM(el);
                            if (v) return v;
                        } catch {}
                    }
                    await new Promise(r => setTimeout(r, 50));
                }
                return null;
            }

            async function waitCond(fn, timeout = 5000) {
                const start = Date.now();
                while (Date.now() - start < timeout) {
                    if (fn()) return true;
                    await new Promise(r => setTimeout(r, 50));
                }
                return false;
            }

            const origPut = api.put.bind(api);
            const puts = [];
            let releaseA;
            const gateA = new Promise(r => { releaseA = r; });

            api.put = async function(url, body) {
                puts.push({ url, body: JSON.parse(JSON.stringify(body)) });
                if (puts.length === 1) {
                    await gateA;
                }
                return origPut(url, body);
            };

            try {
                const textInit = '# File A\\n\\nInitial test content.';
                const editA = '# File A\\n\\nEdit A content pending.';
                const textB = '# File A\\n\\nExternal replacement B.';
                const finalB = '# File A\\n\\nFinal desired B content.';

                window.__mountEditor({ text: textInit, path: 'docs/file_a.md' });
                await new Promise(r => setTimeout(r, 500));

                const btns = Array.from(document.querySelectorAll('.markdown-editor-tabs button'));
                const srcBtn = btns.find(b => b.textContent.includes('Source'));
                if (!srcBtn) return JSON.stringify({ error: 'Source button not found' });
                srcBtn.click();

                let view = await getEditorView();
                if (!view) return JSON.stringify({ error: 'CodeMirror view not found' });

                view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: editA } });
                await new Promise(r => setTimeout(r, 100));

                const saveBtn1 = document.querySelector('.edit-bar-save');
                if (!saveBtn1) return JSON.stringify({ error: 'Save button not found' });
                saveBtn1.click();

                const put1Issued = await waitCond(() => puts.length === 1, 3000);
                if (!put1Issued) return JSON.stringify({ error: 'First PUT was not issued' });

                window.__mountEditor({ text: textB, path: 'docs/file_a.md' });
                await new Promise(r => setTimeout(r, 500));

                const textBObserved = await waitCond(() => {
                    const v = mod.EditorView.findFromDOM(document.querySelector('.cm-editor'));
                    return v && v.state.doc.toString() === textB;
                }, 4000);
                if (!textBObserved) return JSON.stringify({ error: 'Expected intermediate textB was not observed' });
                view = await getEditorView();
                if (!view) return JSON.stringify({ error: 'CodeMirror view not found after textB' });
                const saveBeforeEdit = document.querySelector('.edit-bar-save');
                const intermediateStateBeforeEdit = {
                    doc: view.state.doc.toString(),
                    save_disabled: saveBeforeEdit ? saveBeforeEdit.disabled : null,
                    save_text: saveBeforeEdit ? saveBeforeEdit.textContent : null,
                };
                view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: finalB } });
                await new Promise(r => setTimeout(r, 100));

                const saveBtnBefore = document.querySelector('.edit-bar-save');
                if (saveBtnBefore) saveBtnBefore.click();
                await new Promise(r => setTimeout(r, 300));

                const putCountBefore = puts.length;

                releaseA();
                const lockCleared = await waitCond(() => {
                    const b = document.querySelector('.edit-bar-save');
                    return b && !b.disabled && !b.textContent.includes('Saving');
                }, 5000);

                const saveBtnB = document.querySelector('.edit-bar-save');
                if (saveBtnB) saveBtnB.click();

                const put2Issued = await waitCond(() => puts.length === 2, 5000);
                const finalSaveSettled = await waitCond(() => {
                    const b = document.querySelector('.edit-bar-save');
                    return b && !b.textContent.includes('Saving') && !b.classList.contains('dirty');
                }, 5000);

                view = await getEditorView();
                const inMemoryFinalB = view ? view.state.doc.toString() : null;

                const fetched = await api.get('/api/files/content?path=docs/file_a.md');
                const fetchedText = typeof fetched === 'string' ? fetched : (fetched?.content || '');
                window.__mountEditor({ text: fetchedText, path: 'docs/file_a.md' });
                await new Promise(r => setTimeout(r, 500));
                const btns2 = Array.from(document.querySelectorAll('.markdown-editor-tabs button'));
                const srcBtn2 = btns2.find(b => b.textContent.includes('Source'));
                if (srcBtn2) srcBtn2.click();
                const reopenView = await getEditorView();
                const reopenedDoc = reopenView ? reopenView.state.doc.toString() : null;

                return JSON.stringify({
                    put_count_before: putCountBefore,
                    put_count_total: puts.length,
                    put1_content: puts[0]?.body?.content,
                    put2_content: puts[1]?.body?.content,
                    in_memory_final: inMemoryFinalB,
                    fetched_text: fetchedText,
                    reopened_doc: reopenedDoc,
                    finalB,
                    lock_cleared: lockCleared,
                    put2_issued: put2Issued,
                    final_save_settled: finalSaveSettled,
                    intermediate_textB_observed: textBObserved,
                    intermediate_state_before_edit: intermediateStateBeforeEdit
                });
            } finally {
                api.put = origPut;
            }
        })()`);

        let res = typeof harnessResult === 'object' ? harnessResult : {};
        if (typeof harnessResult === 'string') {
            try { res = JSON.parse(harnessResult); } catch {}
        }

        const diskFileContent = fs.readFileSync(path.join(TEST_HOME, 'docs', 'file_a.md'), 'utf-8');
        const exactFinalB = res.finalB;
        const expectedEditA = '# File A\n\nEdit A content pending.';
        const pass = res.put_count_before === 1
            && res.put_count_total === 2
            && res.put1_content === expectedEditA
            && res.put2_content === exactFinalB
            && res.in_memory_final === exactFinalB
            && res.fetched_text === exactFinalB
            && res.reopened_doc === exactFinalB
            && res.lock_cleared === true
            && res.put2_issued === true
            && res.final_save_settled === true
            && res.intermediate_textB_observed === true
            && res.intermediate_state_before_edit?.doc === '# File A\n\nExternal replacement B.'
            && diskFileContent === exactFinalB;

        report.tests['direct_mount_same_path_save_lock'] = {
            put_count_before: res.put_count_before,
            put_count_total: res.put_count_total,
            in_memory_exact: res.in_memory_final === exactFinalB,
            put_exact: res.put2_content === exactFinalB,
            disk_exact: diskFileContent === exactFinalB,
            reopen_exact: res.reopened_doc === exactFinalB,
            lock_cleared: res.lock_cleared === true,
            put2_issued: res.put2_issued === true,
            final_save_settled: res.final_save_settled === true,
            intermediate_textB_observed: res.intermediate_textB_observed === true,
            intermediate_state_before_edit: res.intermediate_state_before_edit || null,
            status: pass ? 'PASS' : 'FAIL'
        };
        log(`  -> direct_mount_same_path_save_lock: status=${pass ? 'PASS' : 'FAIL'}`);
    }

    // Print summary table
    console.log('\n================ REGRESSION SUITE RESULTS ================');
    console.log(`Modules Verified: ${report.modules_verified ? 'PASS' : 'FAIL'}`);
    let anyFailed = !report.modules_verified;
    for (const [testName, res] of Object.entries(report.tests)) {
        console.log(`- ${testName.padEnd(36)}: ${res.status}`);
        if (res.status !== 'PASS') {
            anyFailed = true;
        }
    }
    console.log('==========================================================\n');

    if (anyFailed) {
        log('Suite completed with test FAILURES.');
        process.exitCode = 1;
    }

    return report;
}

async function cleanup() {
    try {
        if (!browserStarted) return;
        try {
            log('Cleaning up browser session...');
            runBrowser(['close']);
            const pids = Object.values(browserPids).filter(Number.isInteger);
            const alive = pid => {
                try { process.kill(pid, 0); return true; }
                catch (error) { if (error.code === 'ESRCH') return false; throw error; }
            };
            for (let i = 0; i < 30 && pids.some(alive); i++) {
                await new Promise(resolve => setTimeout(resolve, 100));
            }
            if (pids.length !== 2 || pids.some(alive)) throw new Error(`Browser or daemon PID verification failed: count=${pids.length}, alive=${pids.some(alive)}`);
            report.cleanup = { status: 'closed', ...browserPids, pids_verified: true };
            updateLedger('closed', browserPids.pid, browserPids.daemon_pid, 'close succeeded; recorded PIDs exited');
        } catch (error) {
            report.cleanup = { status: 'handoff-required', ...browserPids, error: error.message };
            process.exitCode = 1;
            try {
                updateLedger('handoff-required', browserPids.pid, browserPids.daemon_pid, error.message);
            } catch (ledgerError) {
                console.error('[driver] Could not record browser cleanup failure:', ledgerError);
            }
        }
    } finally {
        try {
            await stopOwnedFixture();
        } catch (error) {
            report.cleanup = { ...(report.cleanup || {}), fixture: 'handoff-required', fixture_error: error.message };
            process.exitCode = 1;
            try {
                updateFixtureLedger('handoff-required', error.message);
            } catch (ledgerError) {
                console.error('[driver] Could not record fixture cleanup failure:', ledgerError);
            }
        } finally {
            try {
                fs.writeFileSync(EVIDENCE_FILE, JSON.stringify(report, null, 2) + '\n', 'utf-8');
                log(`Evidence written to ${EVIDENCE_FILE}`);
            } catch (error) {
                console.error('[driver] Could not write evidence:', error);
                process.exitCode = 1;
            }
        }
    }
}

function releaseLock() {
    if (lockFd === null) return;
    const fd = lockFd;
    lockFd = null;
    try {
        fs.closeSync(fd);
    } catch (error) {
        console.error('[driver] Could not close exclusive lock:', error);
        process.exitCode = 1;
    } finally {
        try {
            fs.unlinkSync(LOCK_FILE);
        } catch (error) {
            if (error.code !== 'ENOENT') {
                console.error('[driver] Could not remove exclusive lock:', error);
                process.exitCode = 1;
            }
        }
    }
}

async function main() {
    // Validate before acquiring the global lock or creating a run directory.
    validatePythonBin();
    assertSafeWorkPath(LOCK_FILE);
    lockFd = fs.openSync(LOCK_FILE, 'wx', 0o600);
    try {
        fs.writeSync(lockFd, `${process.pid}\n`);
        await startOwnedFixture();
        await runSuite();
    } catch (err) {
        console.error('[driver] Fatal error:', err);
        report.error = err.message;
        report.fixture_output = fixtureOutput.slice(-16_384);
        process.exitCode = 1;
    } finally {
        try {
            await cleanup();
        } finally {
            releaseLock();
        }
    }
}

try {
    await main();
} catch (err) {
    console.error('[driver] Fatal startup error:', err);
    process.exitCode = 1;
}
