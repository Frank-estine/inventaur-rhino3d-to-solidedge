> **Inventaur Inc.** - by **Krishna Parmar**

# Public Release Checklist

## Before creating a release

- [ ] Review `Docs/RELEASE_READINESS_AUDIT.md` and close every applicable acceptance item.
- [ ] Confirm the project owner/copyright holder and choose a license for original workflow code. No project-wide license is included until that decision is made.
- [ ] Review `THIRD_PARTY_NOTICES.md` for CPython/PSF license, psutil BSD license, pywin32 PSF license, McNeel Yak/MIT, self-contained .NET notices and managed dependency licenses.
- [ ] Confirm redistribution terms for self-contained .NET runtime files, CPython and Python wheels, Interop.SolidEdge and transitive dependencies; retain all required notices.
- [ ] Verify the Python runtime payload and offline wheelhouse are included; clean-install the `.venv` without any package index/network access.
- [ ] Verify `ThirdParty/RhinoAI/LICENSE` accompanies the bundled Rhino MCP Yak package.
- [ ] Run the Python test suite, compileall, PowerShell parser and batch BOM checks.
- [ ] Run `INSTALL.bat` from the extracted beta.3 ZIP on a clean folder; verify both MCP `--version` calls, bundled Python identity, offline wheel installation and Yak list checks.
- [ ] Run a live test with a disposable Rhino model and disposable Solid Edge documents on the target application versions.
- [ ] Review the generated ZIP manifest, exact archive file list and ZIP SHA-256 sidecar.
- [ ] Search staged package for usernames, absolute paths, private model names, credentials, live logs, source CAD files and client data.
- [ ] Confirm no local output under Runs, Logs or `_local` has entered the ZIP.
- [ ] Verify Rhino MCP setup and Solid Edge template discovery on a second workstation.
- [ ] Include tested versions and known limitations in release notes.

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
