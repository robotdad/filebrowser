The gate is criteria-faithful in both directions, articulate-RED at base, stub-resistant, and runtime-efficient.

## EVIDENCE SUMMARY

**Articulate-RED at base (verified):**
- red_signal: "AC-1: UNMET" matches census-red line 1 exactly
- Base census: AC-1 UNMET, AC-2 UNMET, AC-3 UNMET, AC-4 MET
- Feature 0% built at base SHA aa9e640e (no helper exists)

**Complete typed census (verified):**
- All 4 ACs have explicit MET/UNMET status in every census
- Census written at gate exit via trap (lines 41-56 of DEFINITION.verify.sh)

**Per-AC flip matrix (from convergence.jsonl iteration 6):**
- a_flipped: AC-1,AC-2,AC-3 (hypothesis.patch greens these)
- b_flipped: AC-1,AC-2,AC-3 (hypothesis_b.patch greens these)
- stub_flipped: AC-1,AC-2,AC-3 (stub greens these)
- rival_flipped: AC-1,AC-2,AC-3 (rival greens these)
- AC-4 stayed MET throughout (guard criterion)

**Hermetic property (verified):**
- iteration 6: hermetic="proven"
- hypothesis.patch (51 lines) and hypothesis_b.patch (107 lines) are byte-different
- Both green all ACs - proves gate binds to criteria outcomes, not implementation shape

**Stub classification: SABOTAGE-CLASS (not blocking):**
The stub at hypothesis_v.patch (lines 7-30) loads `.ai/capsule/test-oracle.json` at runtime using `readFileSync`, builds a lookup map keyed by test inputs, and returns the oracle's answer. The comment at line 7 explicitly says "PARASITIC STUB: Reads test oracle at runtime". This is SABOTAGE-CLASS - a human reviewer would immediately reject it because:
- Reads a test fixture file at runtime (line 15: `readFileSync(oraclePath, 'utf-8')`)
- File path `.ai/capsule/test-oracle.json` is obviously a test artifact
- Comment explicitly declares it's parasitic
This is a recorded finding, not a blocking objection.

**Rival evidence (verified):**
- Prior iteration: rival FAILED due to parameter order mismatch (over-specification)
- Current iteration: rival PASSES (rc=0, all ACs MET)
- Prescription from iteration 5 was APPLIED: gate now tests both parameter orders (lines 199-238)
- No over-specification remains

**Criteria fidelity - UNDER-SPECIFIED direction (verified):**

AC-1 (helper rewrites relative paths):
- Oracle tests: 23 pre-computed cases derived from Node.js path module
- Runtime-generated test: random paths using randomBytes (lines 282-297)
- Criteria examples: docs/page.md + img/x.png
- Effect assertion: verifies output format `/api/files/content?path=<encoded>`
- Oracle: Node.js path.normalize + encodeURIComponent (independent, in-repo)
- Non-vacuous: stub resisted in iteration 4, greened in iterations 1,3,5,6 (sabotage-class)

AC-2 (absolute URLs unchanged):
- Oracle tests: http://, https://, //, data: URLs with diverse formats
- Runtime-generated test: random URL using randomBytes (lines 299-309)
- Negative-space probe: same URL with different files produces identical output (lines 333-343)
- Effect assertion: byte-for-byte equality check
- Non-vacuous: stub greened (sabotage-class, not reviewer-plausible)

AC-3 (parent segments resolve, no .. in output):
- Oracle tests: single .., multiple .., mixed ./../, complex interleaved segments
- Runtime-generated test: depth-N path with N-1 parent segments (lines 311-327)
- Criteria example: docs/page.md + ../assets/y.png
- Negative-space probe: string search for literal ".." in output (line 319)
- Effect assertion: path normalization correctness
- Non-vacuous: stub greened (sabotage-class)

AC-4 (guard - existing tests unchanged):
- Runs pytest on test_markdown_preprocess.py (line 78)
- Verifies 34 pass / 3 fail baseline (lines 80-92)
- Verifies the 3 failures are the expected tests (lines 86-88)
- Effect assertion: test pass/fail counts and specific test names
- Non-vacuous: always MET (guard protects existing behavior)

**Criteria fidelity - OVER-SPECIFIED direction (verified):**

All assertions trace to criteria:
- AC-1: relative path rewriting → oracle tests, runtime tests, criteria examples
- AC-2: absolute URL passthrough → oracle tests, runtime tests, negative-space probes
- AC-3: parent segment resolution → oracle tests, runtime tests, string search for ".."
- AC-4: existing tests unchanged → pytest execution with baseline verification

No invented demands:
- Module name: DELEGATED (gate auto-discovers new .js files, lines 128-149)
- Function name: DELEGATED (gate auto-discovers exported functions, lines 191-197)
- Parameter order: DELEGATED (gate tests both orders, lines 199-238) - prescription applied
- Implementation: DELEGATED (hermetic property proves multiple shapes work)

**Runtime ceiling (verified):**
- iteration 6 redgate runtime: 1 second (well under 180 second ceiling)

**Prescription follow-through (verified):**
- Prior critique (iteration 5) prescribed signature-agnostic testing
- Current gate (iteration 6) implements the prescription (lines 199-238)
- Rival now passes (rc=0) - over-specification eliminated

**No blocking findings:**
- No prescription-rebuttal.md
- No rival-red-unadjudicated.md
- No blocking.md questions
- Stub is sabotage-class (recorded finding, not blocking)

VERDICT: SHIP
