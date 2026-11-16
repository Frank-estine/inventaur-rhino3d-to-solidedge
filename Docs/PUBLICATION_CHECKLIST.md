> **Inventaur Inc.** - by **Krishna Parmar**

# Public Release Checklist

## Before creating a release

- [ ] Review `Docs/RELEASE_READINESS_AUDIT.md` and close every applicable acceptance item.
- [x] No first-party root license file added at the project owner's direction. Do not describe the first-party workflow as open-source; preserve all upstream licenses and credits.
- [ ] Review `THIRD_PARTY_NOTICES.md` for CPython/PSF license, psutil BSD license, pywin32 PSF license, McNeel Yak/MIT, self-contained .NET notices and managed dependency licenses.
- [ ] Confirm redistribution terms for both SolidEdge-MCP upstream projects, self-contained .NET runtime files, CPython/Python wheels, Interop.SolidEdge and transitive dependencies; retain all upstream licences/notices.
- [ ] Verify the Python runtime payload and offline wheelhouse are included; clean-install the `.venv` without any package index/network access.
- [ ] Verify `ThirdParty/RhinoAI/LICENSE` accompanies the bundled Rhino MCP Yak package.
- [x] Run the Python test suite (78 passed), compileall, PowerShell parser and batch BOM checks.
- [x] Run the extracted beta.3 installer on a clean folder; exit code 0, bundled Python identity, offline dependency installation and both MCP version checks passed.
- [x] Run the live Rhino 9 / Solid Edge 2026 conversion E2E; 45/45 PAR imports and 27/27 nested assemblies completed; Root.asm has 11/11 direct occurrences verified.
- [x] Review the generated ZIP manifest, exact archive file list and ZIP SHA-256 sidecar; 2,358 manifest hashes and the sidecar were independently verified.
- [ ] Search staged package for usernames, absolute paths, private model names, credentials, live logs, source CAD files and client data.
- [ ] Confirm no local output under Runs, Logs or `_local` has entered the ZIP.
- [ ] Verify Rhino MCP setup and Solid Edge template discovery on a second workstation.
- [ ] Include tested versions and known limitations in release notes.

## Upstream attribution

- [x] Credit Tyler Wagler and SolidEdge-MCP contributors; preserve the original MIT licence and clone provenance under ThirdParty/SolidEdge-MCP.
- [x] Keep the separate .NET MCP server attribution and MIT licence under ThirdParty/DotNet.

## Internal source repository status

The source upload is complete to the private repository https://github.com/Krishna-Inventaur/inventaur-rhino3d-to-solidedge. Branch main points to initial commit 6ad58bdb5fd137245c99f45dfd0d1c22f8d3abfc; 3,907 files and 499 Git LFS paths were pushed and verified. This is not a public release and does not grant redistribution rights.

## Community onboarding documentation — 17 November 2026

- [x] Root README rewritten for Rhino community readers with problem context, feature overview, tested baseline and known limitations.
- [x] Git LFS clone/pull and complete offline-bundle instructions documented.
- [x] INSTALL.bat, Rhino MCP connection, launcher commands, output folders and report-based verification documented.
- [x] Agent/developer instructions, architecture/data contracts, Rhino MCP setup, Solid Edge bridge README and troubleshooting/recovery guides reconciled.
- [x] Private forum post draft rewritten; parent CAD navigation entry checked and retained without a duplicate index row.
- [x] Documentation-only source changes committed and pushed to main in 19b408e; remote readback matched. No release archive or GitHub release was created.

## Before posting publicly

- [ ] Describe the workflow accurately as depending on a Rhino MCP integration exposing `run_python`.
- [ ] State Rhino 9 and Solid Edge 2026 as the live-tested baseline; do not claim universal version compatibility.
- [ ] Explain that geometry repair is a separate, reviewable operation, not an automatic guarantee.
- [ ] Include repository link and ZIP checksum only after a reviewed public release exists.
- [ ] Attach a sanitized demo report and synthetic sample, not customer CAD files.
- [ ] State whether visual inspection was completed. File/hash verification is not visual sign-off.

## Public GitHub release process

1. Review the full bootstrap staging directory created by `tools/build_release.ps1`.
2. Verify `PACKAGE_MANIFEST.sha256` and the outer ZIP SHA-256 sidecar.
3. Extract the ZIP and verify the stable legacy BAT launcher plus offline installer.
4. Run pytest from a clean checkout.
5. Commit only reviewed source/docs/tests/configuration and approved third-party runtime payloads.
6. Create the GitHub release and attach the ZIP and SHA-256 checksum.
