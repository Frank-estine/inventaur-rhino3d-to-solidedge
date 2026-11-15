> **Inventaur Inc.** — by **Krishna Parmar**

# Rhino Geometry Repair Playbook

## Purpose

This playbook covers BREP and polysurface defects discovered while preparing Rhino geometry for STEP export and Solid Edge import. It is intentionally separate from the critical conversion path. The main workflow does not silently repair, Boolean, rebuild or simplify user geometry.

A Rhino repair command returning success is not proof that the result is geometrically equivalent or suitable for downstream CAD.

## 1. Preserve the source

Before any repair:

1. Record the original 3DM path and SHA-256.
2. Capture the intended live document to a run-owned snapshot.
3. Create a second, clearly named repair candidate from that snapshot.
4. Keep the original snapshot read-only. Never save the repair candidate over the original.
5. Record Rhino version, model units, absolute tolerance, object IDs, block definition IDs and occurrence paths.

All testing and editing takes place in the repair candidate. If an accepted downstream file already exists, do not overwrite it during diagnosis.

## 2. Diagnose before choosing an operation

For every suspect object or block-definition member, collect:

| Evidence | Why it matters |
|---|---|
| Object GUID and definition name | Identifies the exact source geometry |
| Object type | Separates Brep, extrusion, mesh, SubD, curve and instance reference |
| Rhino validity and full validity log | Reports topology/geometry defects |
| Solid/open state | Distinguishes a closed solid from an intentionally open surface |
| Face and edge counts | Detects unexplained topology changes |
| Naked-edge count and edge locations | Helps locate open boundaries |
| Bounding box and centre | Detects displacement, truncation or scale change |
| Surface area and volume, when defined | Helps detect geometry loss or change |
| Units and absolute tolerance | Makes all geometric comparisons meaningful |
| Name, layer, material/colour and alpha | Ensures metadata survives the repair |

Use Rhino's inspection tools (for example, Check, ShowEdges, SelBadObjects, object properties and the block editor) to understand the failure. Record screenshots or a viewport capture for ambiguous defects. Do not select a broad class of objects and apply a repair to all of them without a per-object diagnosis.

## 3. Classify the defect

Do not collapse these into one category:

- **Invalid Brep:** Rhino reports a geometry/topology validity problem.
- **Open Brep or polysurface:** the object is valid but has naked edges and is not a solid. It may be intentional.
- **Disconnected shells:** a Brep contains multiple disconnected components. Determine whether those components represent one part or several.
- **Unjoined surfaces:** edges may coincide within model tolerance but are represented as separate surfaces.
- **Degenerate or sliver geometry:** tiny edges/faces or collapsed regions may be below a useful manufacturing tolerance.
- **Self-intersection or overlap:** faces intersect or overlap; joining alone does not resolve the design intent.
- **STEP translator discrepancy:** Rhino geometry may be valid while the exported/imported representation changes.
- **Non-solid import:** Solid Edge may correctly import surfaces/construction geometry without creating a solid body.

The distinction determines whether the problem belongs in Rhino, in STEP translation, or in Solid Edge import/validation.

## 4. Choose the least destructive operation

Only after diagnosis, select a targeted operation:

1. **No repair:** if the geometry is valid and the open/non-solid state is intentional, keep it and document the expected result.
2. **Join coincident surfaces:** use Rhino's join workflow only when boundary edges are intended to coincide within the document tolerance. Joining is not Boolean union.
3. **Repair a duplicate Brep:** the optional Scripts/inventaur_repair_breps_for_step_v1.py uses RhinoCommon Brep.Repair and PrepareForBooleans on duplicate candidates and writes a new 3DM/report. By default it uses the source document's ModelAbsoluteTolerance, then tests 2x and 5x values. A run-config override is available through brep_repair_tolerance. These larger tolerance attempts can change topology and must be reviewed; they are not silent defaults for the production pipeline.
4. **Rebuild edges:** consider only when edge curves are the diagnosed issue and the resulting surface boundaries can be verified.
5. **Rebuild or replace a face/surface:** use only when the intended design surface is known and can be reconstructed from reliable reference geometry. Document the changed face and deviation.
6. **Split or separate disconnected components:** do this only when component identity and intended part boundaries are clear.
7. **Boolean operations:** last resort. They can remove seams, alter face topology, or change the design. They require explicit approval and strong before/after geometric checks.

The optional Scripts/inventaur_join_lowest_block_breps_v2.py uses RhinoCommon JoinBreps (not Boolean union), operates on leaf definitions, and defaults to the source document's ModelAbsoluteTolerance. Its report records model units and the document tolerance. It is not a required production stage.

Never use Boolean union merely to force IsSolid=True. Never delete naked edges or faces just to make the validity count look better. Never use a larger tolerance as an unexamined way to force a join.

## 5. Optional script behavior and limits

inventaur_repair_breps_for_step_v1.py:

- Reads the run-scoped CAD_WORKFLOW_CONFIG; it does not use a shared active-run fallback.
- Opens the joined model headlessly.
- Inspects directly owned Breps in leaf block definitions.
- Attempts repair/preparation on duplicated Breps.
- Replaces definition geometry only when its current acceptance logic considers the candidate improved.
- Writes a separate repaired 3DM and JSON report.
- Retains original Breps when a candidate is not accepted.
- Records model units, document absolute tolerance, attempted tolerance values, before/after validity, solid state, face/edge counts and naked edges.

It is an optional utility, not a universal STEP healer. Its present acceptance logic checks validity, solid state, face/edge counts and naked edges; it does not constitute a full engineering-equivalence proof. It does not currently prove bounded surface deviation, volume preservation or manufacturing suitability. Review the report and inspect the output before using it on important geometry.

The production supervisor does not run either optional join or BREP repair utility in its required stage sequence.

## 6. Before/after acceptance

A repaired candidate is acceptable only when the operator can explain the change and all relevant checks pass:

- Rhino validity is improved or remains valid; any unresolved invalid object remains clearly identified.
- No unexplained face, edge, shell or object loss occurred.
- Solid/open state matches the design intent.
- Bounding box, centre, area and volume remain within an approved geometric deviation.
- No unexpected movement, scale, rotation or reflection was introduced.
- Block definition identity, nested references, occurrence transforms and object attributes are preserved.
- The repaired 3DM is reopened from disk and its report is bound to the exact output hash.
- STEP is exported from the repaired candidate and checked against the export manifest.
- A disposable Solid Edge import is saved, closed and reopened from disk.
- Native body count, model/construction state, face/edge counts, validity and open-edge diagnostics are recorded.
- Warnings and visual-review requirements are not suppressed.

If a geometric deviation threshold has not been defined for the part, do not invent one. Mark the candidate as NEEDS HUMAN REVIEW.

## 7. Manual Rhino operation protocol for an AI assistant

When a human must perform the repair in Rhino, the assistant should:

1. Identify the exact object GUID, block definition and instance path.
2. Give the operator a short inspection sequence and the intended selection scope.
3. Ask for the validity log and a viewport/screenshot when the diagnosis is ambiguous.
4. State the proposed command, expected effect and possible risk before the operator executes it.
5. Wait for a fresh report/viewport after the operation.
6. Compare the before/after evidence and decide whether to keep or undo the repair.
7. Record the repaired copy path, source/output hashes, operation and acceptance status.

Do not give an unqualified instruction such as "run Repair All" or "join everything". The target and expected outcome must be explicit.

## 8. If downstream import still fails

Return to the source evidence. Compare the STEP header/units, STEP entity and body counts, Rhino export warning, and Solid Edge import report. Determine whether the missing/invalid entity is absent from STEP, rejected by the translator, or represented as a surface/construction body. Do not repeat the same Rhino repair blindly when the defect is in the translation or validation layer.
