set -euo pipefail

# Markdown Image Source Rewriter - Definition of Done verification
# Verifies the helper module exists, exports the required function, and correctly
# rewrites relative image sources to /api/files/content URLs.

REPO_ROOT="$(pwd)"
CENSUS_FILE=".ai/census"
ORACLE_FILE=".ai/capsule/test-oracle.json"

# Remove any stale census file
rm -f "$CENSUS_FILE"

# Track AC states (will write to census at end)
declare -A AC_STATUS

# Utility: mark an AC as MET or UNMET
mark_ac() {
    local ac_id="$1"
    local status="$2"
    AC_STATUS["$ac_id"]="$status"
}

# Utility: print diagnostic and mark UNMET
fail_ac() {
    local ac_id="$1"
    shift
    echo "FAIL $ac_id: $*"
    mark_ac "$ac_id" "UNMET"
}

# Utility: mark MET with diagnostic
pass_ac() {
    local ac_id="$1"
    shift
    echo "PASS $ac_id: $*"
    mark_ac "$ac_id" "MET"
}

# Write census file at exit
write_census() {
    # Ensure all ACs have a status
    for ac_id in AC-1 AC-2 AC-3 AC-4; do
        if [[ -z "${AC_STATUS[$ac_id]:-}" ]]; then
            echo "ERROR: AC $ac_id has no status recorded" >&2
            exit 2
        fi
    done
    
    # Write census in order
    for ac_id in AC-1 AC-2 AC-3 AC-4; do
        echo "$ac_id: ${AC_STATUS[$ac_id]}" >> "$CENSUS_FILE"
    done
}

trap write_census EXIT

echo "=== Markdown Image Rewriter Gate ==="
echo "Base SHA: aa9e640e5bfc7712f417bd3266d4032692c9de2e"
echo "Repo root: $REPO_ROOT"
echo

# ============================================================================
# AC-4 [guard]: Existing module and tests keep passing unchanged
# ============================================================================
echo "--- AC-4: Guard - existing preprocess-markdown.js unchanged ---"

# Check if preprocess-markdown.js exists
if [[ ! -f "filebrowser/static/js/lib/preprocess-markdown.js" ]]; then
    fail_ac "AC-4" "preprocess-markdown.js missing"
else
    # Check if tests exist
    if [[ ! -f "tests/test_markdown_preprocess.py" ]]; then
        fail_ac "AC-4" "test_markdown_preprocess.py missing"
    else
        # Run the tests
        echo "Running tests/test_markdown_preprocess.py..."
        if ! TEST_OUTPUT=$(uv run --with pytest pytest tests/test_markdown_preprocess.py -v --tb=no 2>&1); then
            # Tests failed - check if it's the expected 34 pass / 3 fail pattern
            PASSED=$(echo "$TEST_OUTPUT" | grep -oP '\d+(?= passed)' || echo "0")
            FAILED=$(echo "$TEST_OUTPUT" | grep -oP '\d+(?= failed)' || echo "0")
            
            if [[ "$PASSED" == "34" ]] && [[ "$FAILED" == "3" ]]; then
                # Expected baseline: 34 pass, 3 fail
                # Verify the 3 failures are the expected ones
                if echo "$TEST_OUTPUT" | grep -q "test_empty_frontmatter_block" && \
                   echo "$TEST_OUTPUT" | grep -q "test_nested_brackets_are_not_matched" && \
                   echo "$TEST_OUTPUT" | grep -q "test_wikilink_with_pipe_in_display_text"; then
                    pass_ac "AC-4" "preprocess-markdown.js tests: 34 passed, 3 failed (expected baseline)"
                else
                    fail_ac "AC-4" "tests have 34 pass / 3 fail but different failures than baseline"
                fi
            else
                fail_ac "AC-4" "tests have unexpected pass/fail counts: $PASSED passed, $FAILED failed (expected 34/3)"
            fi
        else
            # All tests passed - this is different from baseline
            fail_ac "AC-4" "all tests passed (baseline has 3 failures)"
        fi
    fi
fi

# ============================================================================
# AC-1, AC-2, AC-3: Helper module tests
# ============================================================================
echo
echo "--- AC-1, AC-2, AC-3: Helper module tests ---"

# Verify oracle file exists
if [[ ! -f "$ORACLE_FILE" ]]; then
    echo "ERROR: Oracle file missing at $ORACLE_FILE" >&2
    fail_ac "AC-1" "oracle file missing (infrastructure problem)"
    fail_ac "AC-2" "oracle file missing (infrastructure problem)"
    fail_ac "AC-3" "oracle file missing (infrastructure problem)"
    exit 2
fi

# Known existing files at base SHA (these are NOT the new helper)
KNOWN_FILES=(
    "change-detector.js"
    "fit-scale.js"
    "package.json"
    "preprocess-dot.js"
    "preprocess-markdown.js"
)

# Find all .js files in lib/
LIB_DIR="filebrowser/static/js/lib"
if [[ ! -d "$LIB_DIR" ]]; then
    fail_ac "AC-1" "lib directory missing"
    fail_ac "AC-2" "lib directory missing (cannot test)"
    fail_ac "AC-3" "lib directory missing (cannot test)"
else
    # Look for new .js files
    NEW_MODULES=()
    for jsfile in "$LIB_DIR"/*.js; do
        [[ -e "$jsfile" ]] || continue  # Handle case where glob matches nothing
        basename_file=$(basename "$jsfile")
        is_known=false
        for known in "${KNOWN_FILES[@]}"; do
            if [[ "$basename_file" == "$known" ]]; then
                is_known=true
                break
            fi
        done
        if [[ "$is_known" == "false" ]]; then
            NEW_MODULES+=("$jsfile")
        fi
    done

    if [[ ${#NEW_MODULES[@]} -eq 0 ]]; then
        fail_ac "AC-1" "no new helper module found in $LIB_DIR"
        fail_ac "AC-2" "no helper module (cannot test)"
        fail_ac "AC-3" "no helper module (cannot test)"
    else
        # Try to import and test each new module
        HELPER_FOUND=false
        for module_path in "${NEW_MODULES[@]}"; do
            module_name=$(basename "$module_path" .js)
            echo "Testing module: $module_name"
            
            # Create a Node.js test script to probe the helper
            TEST_SCRIPT=$(mktemp --suffix=.mjs)
            cat > "$TEST_SCRIPT" << 'EOTEST'
import { readFileSync } from 'fs';
import { join, dirname, normalize } from 'path';
import { randomBytes } from 'crypto';
import { pathToFileURL } from 'url';

// Import the helper module from RELATIVE path (cwd is repo root by gate contract)
const moduleRelPath = process.argv[2];
const oracleRelPath = process.argv[3];

const modulePath = join(process.cwd(), moduleRelPath);
const oraclePath = join(process.cwd(), oracleRelPath);

const moduleUrl = pathToFileURL(modulePath).href;
const helperModule = await import(moduleUrl);

// Load oracle test cases
let oracleTests;
try {
    const oracleContent = readFileSync(oraclePath, 'utf-8');
    oracleTests = JSON.parse(oracleContent);
} catch (e) {
    console.error('ERROR: Failed to load oracle file:', e.message);
    process.exit(2);
}

// Find the exported function (we don't know its name)
const exportedFunctions = Object.entries(helperModule)
    .filter(([name, value]) => typeof value === 'function' && !name.startsWith('_'));

if (exportedFunctions.length === 0) {
    console.error('ERROR: No exported functions found');
    process.exit(2);
}

// Try each exported function with BOTH parameter orders to find the image rewriter
// This is signature-agnostic: we test behavior, not parameter order
let rewriteImageSrc = null;
let paramOrder = null;

for (const [name, func] of exportedFunctions) {
    // Try order 1: func(currentFile, imageSource)
    try {
        const result1 = func('docs/page.md', 'img/x.png');
        if (typeof result1 === 'string' && result1 === '/api/files/content?path=docs%2Fimg%2Fx.png') {
            // Found it with (currentFile, imageSource) order
            rewriteImageSrc = func;
            paramOrder = 'file-first';
            console.log(`Found function '${name}' with parameter order (currentFile, imageSource)`);
            break;
        }
    } catch (e) {
        // Not this signature, try next order
    }
    
    // Try order 2: func(imageSource, currentFile)
    try {
        const result2 = func('img/x.png', 'docs/page.md');
        if (typeof result2 === 'string' && result2 === '/api/files/content?path=docs%2Fimg%2Fx.png') {
            // Found it with (imageSource, currentFile) order - wrap to normalize
            rewriteImageSrc = (currentFile, imageSource) => func(imageSource, currentFile);
            paramOrder = 'src-first';
            console.log(`Found function '${name}' with parameter order (imageSource, currentFile) - wrapped for normalized calling`);
            break;
        }
    } catch (e) {
        // Not this signature either
    }
}

if (!rewriteImageSrc) {
    console.error('ERROR: No function found that rewrites to /api/files/content URLs');
    console.error('Tried both parameter orders: (currentFile, imageSource) and (imageSource, currentFile)');
    process.exit(2);
}

// Test suite
let allPassed = true;
let ac1Failed = false;
let ac2Failed = false;
let ac3Failed = false;

function assertEquals(actual, expected, testName, acId) {
    if (actual === expected) {
        console.log(`PASS: ${testName}`);
        return true;
    } else {
        console.error(`FAIL: ${testName}`);
        console.error(`  Expected: ${expected}`);
        console.error(`  Actual:   ${actual}`);
        allPassed = false;
        if (acId === 'AC-1') ac1Failed = true;
        if (acId === 'AC-2') ac2Failed = true;
        if (acId === 'AC-3') ac3Failed = true;
        return false;
    }
}

// Run oracle-based tests (using normalized wrapper that always calls as (currentFile, imageSource))
console.log('\n=== Oracle-based tests ===');
for (const testCase of oracleTests) {
    const { description, currentFile, imageSource, expected, ac } = testCase;
    try {
        const actual = rewriteImageSrc(currentFile, imageSource);
        assertEquals(actual, expected, description, ac);
    } catch (e) {
        console.error(`FAIL: ${description} - threw exception: ${e.message}`);
        allPassed = false;
        if (ac === 'AC-1') ac1Failed = true;
        if (ac === 'AC-2') ac2Failed = true;
        if (ac === 'AC-3') ac3Failed = true;
    }
}

// Runtime-generated tests with semantically-neutral identifiers
console.log('\n=== Runtime-generated tests ===');

// AC-1: Random path resolution test
const r1 = randomBytes(6).toString('hex');
const r2 = randomBytes(6).toString('hex');
const r3 = randomBytes(6).toString('hex');
const r4 = randomBytes(6).toString('hex');

const currentFile1 = `${r1}/${r2}.md`;
const imageSource1 = `${r3}/${r4}.png`;
const expectedPath1 = normalize(join(dirname(currentFile1), imageSource1));
const expectedUrl1 = `/api/files/content?path=${encodeURIComponent(expectedPath1)}`;

assertEquals(
    rewriteImageSrc(currentFile1, imageSource1),
    expectedUrl1,
    `AC-1 runtime: ${currentFile1} + ${imageSource1}`,
    'AC-1'
);

// AC-2: Random absolute URL test
const r5 = randomBytes(6).toString('hex');
const r6 = randomBytes(6).toString('hex');
const randomUrl = `https://${r5}.example.com/${r6}.jpg`;

assertEquals(
    rewriteImageSrc('any/file.md', randomUrl),
    randomUrl,
    `AC-2 runtime: random URL ${randomUrl}`,
    'AC-2'
);

// AC-3: Random parent segment test - verify no .. in output
const depth = 4;
const r7 = randomBytes(4).toString('hex');
const deepFile = Array(depth).fill(r7).join('/') + '/file.md';
const r8 = randomBytes(4).toString('hex');
const parentSource = Array(depth - 1).fill('..').join('/') + `/${r8}.png`;
const result = rewriteImageSrc(deepFile, parentSource);

if (result.includes('..')) {
    console.error(`FAIL: AC-3 runtime: output contains '..'`);
    console.error(`  Input: ${deepFile} + ${parentSource}`);
    console.error(`  Output: ${result}`);
    allPassed = false;
    ac3Failed = true;
} else {
    console.log(`PASS: AC-3 runtime: no '..' in output for ${deepFile} + ${parentSource}`);
}

// NEGATIVE-SPACE PROBES
console.log('\n=== Negative-space probes ===');

// Verify absolute URLs are truly unaffected by current file path
const absUrl = 'https://example.com/img.png';
const absResult1 = rewriteImageSrc('a/b/c.md', absUrl);
const absResult2 = rewriteImageSrc('x/y/z.md', absUrl);
if (absResult1 !== absUrl || absResult2 !== absUrl) {
    console.error('FAIL: absolute URL affected by current file path');
    console.error(`  Same URL with different files: ${absResult1} vs ${absResult2}`);
    allPassed = false;
    ac2Failed = true;
} else {
    console.log('PASS: absolute URL unaffected by current file path');
}

// Verify protocol-relative URLs are not treated as relative paths
const protoRel = '//cdn.example.com/image.png';
const protoRelResult = rewriteImageSrc('docs/page.md', protoRel);
if (protoRelResult !== protoRel) {
    console.error('FAIL: protocol-relative URL was modified');
    console.error(`  Expected: ${protoRel}`);
    console.error(`  Actual: ${protoRelResult}`);
    allPassed = false;
    ac2Failed = true;
} else {
    console.log('PASS: protocol-relative URL unchanged');
}

// Verify data URIs are not truncated or modified
const dataUri = 'data:image/png;base64,' + 'A'.repeat(100);
const dataUriResult = rewriteImageSrc('any/file.md', dataUri);
if (dataUriResult !== dataUri) {
    console.error('FAIL: data URI was modified');
    console.error(`  Expected length: ${dataUri.length}`);
    console.error(`  Actual length: ${dataUriResult.length}`);
    allPassed = false;
    ac2Failed = true;
} else {
    console.log('PASS: long data URI unchanged');
}

// Exit with status
if (!allPassed) {
    console.error('\n=== TEST FAILURES SUMMARY ===');
    if (ac1Failed) console.error('AC-1: FAILED');
    if (ac2Failed) console.error('AC-2: FAILED');
    if (ac3Failed) console.error('AC-3: FAILED');
    process.exit(1);
}

process.exit(0);
EOTEST

            # Run the test script with RELATIVE paths
            if node "$TEST_SCRIPT" "$module_path" "$ORACLE_FILE" 2>&1; then
                echo "Helper module '$module_name' passes all tests"
                HELPER_FOUND=true
                pass_ac "AC-1" "helper correctly rewrites relative paths to API URLs"
                pass_ac "AC-2" "helper passes through absolute URLs unchanged"
                pass_ac "AC-3" "helper resolves parent segments with no '..' in output"
                rm -f "$TEST_SCRIPT"
                break
            else
                echo "Helper module '$module_name' failed tests"
                rm -f "$TEST_SCRIPT"
            fi
        done

        if [[ "$HELPER_FOUND" == "false" ]]; then
            fail_ac "AC-1" "no working helper module found"
            fail_ac "AC-2" "no working helper module found"
            fail_ac "AC-3" "no working helper module found"
        fi
    fi
fi

# Final summary
echo
echo "=== Gate Summary ==="
echo "AC-1: ${AC_STATUS[AC-1]}"
echo "AC-2: ${AC_STATUS[AC-2]}"
echo "AC-3: ${AC_STATUS[AC-3]}"
echo "AC-4: ${AC_STATUS[AC-4]}"

# Determine exit code
ALL_MET=true
for ac_id in AC-1 AC-2 AC-3 AC-4; do
    if [[ "${AC_STATUS[$ac_id]}" == "UNMET" ]]; then
        ALL_MET=false
        break
    fi
done

if [[ "$ALL_MET" == "true" ]]; then
    echo "Result: ALL ACCEPTANCE CRITERIA MET"
    exit 0
else
    echo "Result: SOME ACCEPTANCE CRITERIA UNMET"
    exit 1
fi
