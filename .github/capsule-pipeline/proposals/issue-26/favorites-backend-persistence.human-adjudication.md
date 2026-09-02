# Human adjudication and manual salvage

The hosted feature-specify run reached its wall-clock ceiling after the second critique completed but before its verdict node could run. The final automated critique is retained beside this note and ends `VERDICT: ITERATE`; this package does not misrepresent that as an automated SHIP.

The final critique proved one narrow remaining gap: a reviewer-plausible implementation could accept `data_dir` but ignore it, storing every instance's favorites in one global file. The gate only compared fresh processes using the same `data_dir`, so that implementation passed.

The gate was corrected exactly as prescribed: AC-1 now adds under one runtime-created `data_dir`, confirms persistence from a fresh process using that same directory, then confirms absence from another fresh process using a different independently-created `data_dir`. No route, module, filename, representation, or request-shape requirement was added.

## Corrected proof matrix

| Leg | Expected | Observed census |
|---|---|---|
| Pinned base | RED | AC-1/2/3 UNMET; AC-4 MET |
| Honest hypothesis A | GREEN | AC-1/2/3/4 MET |
| Honest hypothesis B | GREEN | AC-1/2/3/4 MET |
| Gate-blind rival | GREEN | AC-1/2/3/4 MET |
| Global-store void stub | RED | AC-1 UNMET; AC-2/3/4 MET |

The repository's authoritative `verify_shipped_gate.sh` also passed against the exact packaged gate and fixture at the pinned base SHA.

The maintainer reviewed this evidence and approved the corrected gate for publication. This is the feature lane's documented human-judgment exit, not an automated SHIP verdict. Merging the capsule PR is the signal to begin implementation.
