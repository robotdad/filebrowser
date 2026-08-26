# Finding: the STUB PROBE claims no cheap capability-fake is constructible (author CLAIM -- the critic must verify, never accept)

void wrote a # NO-STUB: header instead of an adversarial stub. An honest claim, not an acquittal: nothing here proves the gate is stub-proof -- and the asymptotic limit (a sufficiently faithful fake IS an implementation) makes this claim most plausible exactly when the gate is strongest, so the critic must read the explanation against the gate teeth.

--- author explanation (.ai/hypothesis_v.patch) ---
# NO-STUB: Gate has oracle-based random test cases that prevent vacuous stubs
#
# Attempted dodges and why they fail:
#
# 1. HARDCODED TEST CASES: The gate includes runtime-generated random test cases in AC-1
#    (lines 249-266 of DEFINITION.verify.sh). It generates random directory, file, subdir,
#    and image names, then verifies the output matches Node.js path.normalize(path.join(...))
#    oracle. No hardcoded map can predict random inputs.
#
# 2. WRONG ALGORITHM: Any path resolution algorithm that differs from the oracle will fail
#    the random test. The oracle is: normalize(join(dirname(currentFile), imageSource)).
#    To pass this test, the implementation MUST produce byte-identical results to this
#    oracle for arbitrary random inputs.
#
# 3. DETECT TEST ENVIRONMENT: The gate runs the helper as a plain ES module import in Node.js
#    (lines 157-200). There is no distinguishing feature - no environment variable, no special
#    module path, no injected global - that would let the helper detect "I'm in the gate"
#    vs "I'm in production". The test script is a temporary file with random name.
#
# 4. PARASITIC FIXTURE SCAVENGING: The only existing module in static/js/lib/ is
#    preprocess-markdown.js, which handles YAML frontmatter and wikilinks - no path
#    manipulation code to reuse. The gate explicitly tests a NEW module, not modifications
#    to existing ones.
#
# 5. RIGHT-SHAPED WRONG VALUES: The gate's assertEquals (lines 205-216) does exact string
#    comparison. For the random test, it computes the expected value using the oracle and
#    checks `actual === expected`. Even a single-byte difference fails.
#
# 6. PARTIAL SURFACE FAKE: The gate tests all 3 feature ACs (AC-1, AC-2, AC-3) against the
#    same function. AC-1 requires correct relative path resolution, AC-2 requires passthrough
#    of absolute URLs, AC-3 requires ".." normalization. A stub that fakes AC-2 (simple
#    string prefix checks) but fails AC-1 or AC-3 would not green the gate - the gate exits
#    with rc=1 if ANY AC is UNMET (lines 381-395).
#
# 7. SABOTAGE-CLASS BUGS: Adding console.log, missing error handling for edge cases not
#    tested by the gate (empty strings, null inputs, paths escaping repo root) would make
#    the code smell in review but would still DELIVER THE FEATURE. The gate measures whether
#    the demanded capability exists, not code quality. A function that correctly resolves
#    paths and constructs API URLs HAS delivered the feature, even if it has bugs in
#    untested edge cases.
#
# CONCLUSION: The gate's random oracle-based tests create an asymptotic limit where any
# patch that greens the gate must implement correct path resolution using the Node.js path
# module (or equivalent logic). The cheapest green IS a correct implementation. No vacuous
# stub exists that can pass these tests without delivering the demanded behavior.
