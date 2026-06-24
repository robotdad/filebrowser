// Pure helpers for on-disk file-change detection (no DOM / framework deps), so the
// detection and the clean-vs-conflict decision can be unit-tested directly in Node.

// True when the on-disk (mtime, size) differs from the last-known pair.
// Compares BOTH fields with !== : catches identical-mtime / different-size writes
// AND mtime rollbacks (older timestamp), which a `>` comparison would miss.
export function hasChanged(known, current) {
    if (!known || !current) return false;
    return known.modified !== current.modified || known.size !== current.size;
}

// Classify what the viewer should do for a tab, given a poll result. Returns
// exactly one active state:
//   { gone:true,  reload:false, conflict:false } -> file deleted/renamed; loud gone-state
//   { gone:false, reload:true,  conflict:false } -> CLEAN file changed on disk; auto-reload
//   { gone:false, reload:false, conflict:true  } -> DIRTY file changed on disk; show banner
//   { gone:false, reload:false, conflict:false } -> nothing to do
export function classifyDiskState({ gone = false, changed = false, dirty = false } = {}) {
    if (gone) return { gone: true, reload: false, conflict: false };
    if (changed && !dirty) return { gone: false, reload: true, conflict: false };
    if (changed && dirty) return { gone: false, reload: false, conflict: true };
    return { gone: false, reload: false, conflict: false };
}
