> **Inventaur Inc.** — by **Krishna Parmar**

# CAD Workflow Supervision and Recovery

## Main execution

Run the canonical `Scripts/inventaur_run_rhino3d_to_solidedge.py` script. It performs: source preflight, required colourisation, inventory/identity, STEP export, native PAR import, nested ASM build and root verification.

## Failure recovery

1. Read the owning stage report and runner log.
2. Patch the defect in the canonical script/test.
3. Preserve the source snapshot, run config and iteration log.
4. Delete the failed iteration's derived colourized model, STEP, PAR, ASM and stage reports.
5. Rerun the main script from the beginning.

Do not manually repeat CAD GUI actions or reuse an unverified output. Do not restart the user's Rhino instance. Use only the run-owned Solid Edge bridge.

## What blocks an import

A failed STEP write, missing native model/body, failed `.par` save/reopen, missing reference, incomplete occurrence set or wrong placement transform. `Body.Valid`, naked edges, face-count differences and mass-property differences are diagnostics only.

## Completion

All expected part and assembly documents must exist and reopen. Repeated definitions must point to the same native file. Root and nested assemblies must have no missing/unexpected occurrences and must match expected transforms. Otherwise report INCOMPLETE with the exact failed definition/occurrence.
