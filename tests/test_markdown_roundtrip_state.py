"""Node-executed state regressions for MarkdownEditorDocument save callbacks."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest


EDITOR = Path(__file__).parents[1] / "filebrowser/static/js/components/markdown-editor.js"
DRIVER = Path(__file__).parent / "browser" / "markdown_roundtrip_browser.mjs"
NODE = shutil.which("node")
requires_node = pytest.mark.skipif(NODE is None, reason="node is required")

# This is deliberately a small hook/HTM substitute, not a Preact implementation.
# It executes the component's callbacks and exposes the Source-tab child props.
NODE_HARNESS = r"""
import fs from 'node:fs';

const noOp = () => {};
const api = { put: (...args) => active.put(...args) };
const CodeEditor = Symbol('CodeEditor'), EditBar = Symbol('EditBar');
let active;

function same(a, b) {
  return a && b && a.length === b.length && a.every((v, i) => v === b[i]);
}
function html(strings, ...values) {
  let type, props = {}, buttons = [];
  for (let i = 0; i < values.length; i++) {
    const before = strings[i];
    if (before.endsWith('<')) type = values[i];
    const prop = before.match(/([A-Za-z][A-Za-z0-9]*)=$/);
    if (prop) {
      props[prop[1]] = values[i];
      if (prop[1] === 'onClick') buttons.push(values[i]);
    }
  }
  if (type === CodeEditor) active.child.code = props;
  if (type === EditBar) active.child.bar = props;
  if (buttons.length) active.buttons = buttons;
  return { type, props };
}
function useState(initial) {
  const i = active.next++;
  if (!(i in active.state)) active.state[i] = typeof initial === 'function' ? initial() : initial;
  return [active.state[i], value => {
    active.state[i] = typeof value === 'function' ? value(active.state[i]) : value;
    active.requested = true;
    if (!active.rendering) active.render();
  }];
}
function useRef(value) {
  const i = active.next++;
  return active.refs[i] ||= { current: value };
}
function effect(layout, fn, deps) {
  const i = active.next++, old = active.effects[i];
  active.effects[i] = { layout, fn, deps, changed: !old || !same(old.deps, deps), cleanup: old?.cleanup };
}
const useEffect = (fn, deps) => effect(false, fn, deps);
const useLayoutEffect = (fn, deps) => effect(true, fn, deps);
const useMemo = fn => fn();
const useCallback = fn => fn;
const log = { debug: noOp, info: noOp, error: noOp };
const stripFrontmatter = text => ({ frontmatter: null, body: text });
const transformWikilinks = text => text;
const renderFrontmatter = () => '';
const marked = { parse: () => '' }, DOMPurify = { sanitize: text => text };
const undo = noOp, redo = noOp, confirm = () => true;
globalThis.document = { createElement: () => ({ content: { querySelectorAll: () => [] } }) };
globalThis.__markdownHarness = {
  api, CodeEditor, EditBar, WysiwygEditor: Symbol('WysiwygEditor'),
  WysiwygBar: Symbol('WysiwygBar'), createLogger: () => log, DOMPurify,
  html, marked, redo, renderFrontmatter, rewriteImageSrc: (_, src) => src,
  stripFrontmatter, transformWikilinks, undo, useCallback, useEffect,
  useLayoutEffect, useMemo, useRef, useState,
};

let source = fs.readFileSync(process.env.MARKDOWN_EDITOR, 'utf8');
source = (
  'const { api, CodeEditor, EditBar, WysiwygEditor, WysiwygBar, createLogger, DOMPurify, html, marked, redo, renderFrontmatter, rewriteImageSrc, stripFrontmatter, transformWikilinks, undo, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } = globalThis.__markdownHarness;\n'
  + source.replace(/^import .*;\n/gm, '') + '\nexport { MarkdownEditorDocument };'
);
const module = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));

function mount(props, put) {
  const runtime = { state: [], refs: [], effects: [], child: {}, buttons: [], props, put, requested: false };
  runtime.render = next => {
    if (next) runtime.props = next;
    runtime.rendering = true;
    do {
      runtime.requested = false; runtime.next = 0; runtime.child = {}; runtime.buttons = [];
      active = runtime; module.MarkdownEditorDocument(runtime.props);
      for (const layout of [true, false]) for (const entry of runtime.effects) {
        if (entry?.layout === layout && entry.changed) {
          entry.cleanup?.(); entry.cleanup = entry.fn(); entry.changed = false;
        }
      }
    } while (runtime.requested);
    runtime.rendering = false;
  };
  runtime.source = () => { runtime.buttons[2](); runtime.render(); };
  runtime.edit = text => { runtime.child.code.onDocChange(text); runtime.render(); };
  runtime.save = () => runtime.child.code.onSave();
  runtime.unmount = () => runtime.effects.forEach(entry => entry?.cleanup?.());
  runtime.render(); runtime.source();
  return runtime;
}
function deferred() {
  let resolve;
  return { promise: new Promise(done => { resolve = done; }), resolve };
}
async function tick() { await Promise.resolve(); await Promise.resolve(); }

async function race() {
  const pending = [], puts = [], saves = [], dirty = [];
  const view = mount({ text: 'base', path: 'a.md', onSave: text => {
    saves.push(text);
    // PreviewPane echoes successful saves back as the text prop.
    view.render({ ...view.props, text });
  }, onDirtyChange: value => dirty.push(value) }, (...args) => {
    const gate = deferred(); puts.push(args); pending.push(gate); return gate.promise;
  });
  view.edit('first draft');
  const first = view.save(), duplicate = view.save();
  if (puts.length !== 1) throw Error('duplicate save started another PUT');
  view.edit('latest draft');
  pending[0].resolve({ version: 1 }); await first; await duplicate; await tick();
  const dirtyAfterFirstAck = dirty.at(-1);
  const docAfterFirstAck = view.child.code.doc;
  if (dirtyAfterFirstAck !== true) throw Error('parent acknowledgement cleared newer draft dirty state');
  if (docAfterFirstAck !== 'latest draft') throw Error('parent acknowledgement replaced newer draft');
  const second = view.save();
  if (puts.length !== 2 || puts[1][1].content !== 'latest draft') throw Error('second save did not snapshot latest draft');
  pending[1].resolve({ version: 2 }); await second;
  return { puts: puts.map(call => call[1].content), saves, dirtyAfterFirstAck, docAfterFirstAck, dirtyAfterSecondAck: dirty.at(-1) };
}
async function external() {
  const pending = [], saves = [], dirty = [];
  const view = mount({ text: 'base', path: 'a.md', onSave: text => saves.push(text), onDirtyChange: value => dirty.push(value) }, () => {
    const gate = deferred(); pending.push(gate); return gate.promise;
  });
  view.edit('locally saved'); const save = view.save();
  view.render({ text: 'external replacement', path: 'a.md', onSave: text => saves.push(text), onDirtyChange: value => dirty.push(value) });
  pending[0].resolve({ version: 1 }); await save; await tick();
  if (saves.length || view.child.code.doc !== 'external replacement') throw Error('stale acknowledgement survived replacement');
  return { saves, doc: view.child.code.doc, dirty: dirty.at(-1) };
}
async function unmount() {
  const pending = [], saves = [];
  const view = mount({ text: 'base', path: 'a.md', onSave: text => saves.push(text) }, () => {
    const gate = deferred(); pending.push(gate); return gate.promise;
  });
  view.edit('draft'); const save = view.save(); view.unmount();
  pending[0].resolve({ version: 1 }); await save; await tick();
  if (saves.length) throw Error('unmounted editor called onSave');
  return { saves };
}
async function externalWhileSaving() {
  const pending = [], puts = [], saves = [];
  const view = mount({ text: 'base', path: 'a.md', onSave: text => saves.push(text) }, (_, body) => {
    const gate = deferred(); puts.push(body.content); pending.push(gate); return gate.promise;
  });
  view.edit('old request'); const oldSave = view.save();
  view.render({ ...view.props, text: 'external replacement' });
  view.edit('new replacement draft');
  await view.save();
  if (puts.length !== 1) throw Error('external reload unlocked an outstanding PUT');
  pending[0].resolve({}); await oldSave;
  if (saves.length) throw Error('stale acknowledgement reached parent');
  const doc = view.child.code.doc;
  const newSave = view.save();
  if (puts.length !== 2) throw Error('settled stale PUT did not release save lock');
  pending[1].resolve({}); await newSave;
  return { puts, saves, doc };
}
async function failedSave() {
  const failed = [];
  const view = mount({
    text: 'base', path: 'a.md', onSaveFailed: path => failed.push(path),
  }, () => Promise.reject(Error('fixture write failure')));
  view.edit('retryable draft');
  await view.save(); await tick();
  if (failed.join(',') !== 'a.md') throw Error('failed save did not notify parent to clear its lock');
  return { failed, doc: view.child.code.doc };
}
const result = await ({ race, external, unmount, externalWhileSaving, failedSave })[process.argv[1]]();
process.stdout.write(JSON.stringify(result));
"""


def run_scenario(scenario: str) -> dict:
    assert NODE is not None
    result = subprocess.run(
        [NODE, "--input-type=module", "-e", NODE_HARNESS, scenario],
        env={**os.environ, "MARKDOWN_EDITOR": str(EDITOR)},
        capture_output=True,
        text=True,
        check=True,
        timeout=15,
    )
    return json.loads(result.stdout)


@requires_node
def test_pending_save_keeps_newer_edit_dirty_and_second_save_uses_latest_draft():
    result = run_scenario("race")
    assert result["dirtyAfterFirstAck"] is True
    assert result["docAfterFirstAck"] == "latest draft"
    assert result["dirtyAfterSecondAck"] is False
    assert result["puts"] == ["first draft", "latest draft"]


@requires_node
def test_synchronous_duplicate_save_starts_only_one_put():
    result = run_scenario("race")
    assert result["puts"] == ["first draft", "latest draft"]
    assert result["saves"] == ["first draft", "latest draft"]


@requires_node
def test_external_replacement_invalidates_a_stale_save_acknowledgement():
    result = run_scenario("external")
    assert result == {"saves": [], "doc": "external replacement", "dirty": False}


@requires_node
def test_unmount_suppresses_on_save_from_a_pending_acknowledgement():
    assert run_scenario("unmount") == {"saves": []}


@requires_node
def test_external_reload_keeps_save_lock_until_old_put_settles():
    assert run_scenario("externalWhileSaving") == {
        "puts": ["old request", "new replacement draft"],
        "saves": ["new replacement draft"],
        "doc": "new replacement draft",
    }


@requires_node
def test_failed_save_notifies_parent_to_release_its_cross_remount_lock():
    assert run_scenario("failedSave") == {
        "failed": ["a.md"],
        "doc": "retryable draft",
    }


@requires_node
@pytest.mark.parametrize("python_bin", [None, "/definitely/not/an/interpreter"])
def test_browser_driver_invalid_python_releases_no_lock_or_resource(tmp_path: Path, python_bin: str | None):
    """Preflight failures occur before the exclusive lock or fixture resources exist."""
    isolated_work_dir = tmp_path / "synthetic-work"
    env = {
        **os.environ,
        "MARKDOWN_ROUNDTRIP_WORK_DIR": str(isolated_work_dir),
    }
    if python_bin is None:
        env.pop("PYTHON_BIN", None)
    else:
        env["PYTHON_BIN"] = python_bin

    for _ in range(2):
        result = subprocess.run(
            [NODE, str(DRIVER)],
            cwd=DRIVER.parents[2],
            env=env,
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert result.returncode != 0
        assert "PYTHON_BIN must be an existing executable absolute interpreter path" in result.stderr
        assert "EEXIST" not in (result.stdout + result.stderr)
        assert not (isolated_work_dir / "markdown-roundtrip-browser.lock").exists()
        assert not (isolated_work_dir / "resources.json").exists()
        assert not (isolated_work_dir / "markdown-roundtrip-browser").exists()