# Panel packaging prerequisites

Create a local workspace with `python tools/prepare_workspace.py panel`. This keeps the legacy installer layout while sourcing current code from `competition-code/red-team/`.

The panel installer is a guarded upgrade of an existing lab, not a CALDERA bootstrap installer. Do not run it against an unrelated host. It validates predecessor hashes, configuration identity, recovery state and runtime dependencies. Source tests can run without generating a release.

To create a new release, obtain and review these inputs for your own target installation:

- A pinned CALDERA checkout and its matching Magma submodule, with the custom plugin and Navigation patch applied.
- A freshly built Magma production frontend in `build/plugins/magma/dist/` within the workspace. Retain upstream dependency licenses in any distributed bundle.
- `reference/predecessor-manifest.json`: a mapping of target paths to their reviewed installed SHA-256 hashes.
- `reference/runtime-dependencies.json`: the reviewed hash inventory of unchanged dependencies for that installation.

Then run `python prepare_release.py` inside the workspace. Review the resulting manifest, run the installer acceptance workflow in a disposable clone, and retain that verification before using `build_release_archive.py`. Do not substitute hashes from an unrelated source tree or disable predecessor checks to get past a mismatch.

Private deployment manifests and compiled assets are intentionally absent. This folder does not claim a newly accepted installation release. The retained installer and release builder are source for review until the inputs above are supplied.
