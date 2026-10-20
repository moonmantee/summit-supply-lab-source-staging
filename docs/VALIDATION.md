# Validation — October 19, 2026

The current candidate was tested locally using Ubuntu 24.04 / Python 3.12.3. No source was transferred to lab VMs for this run. Test state used disposable local directories and test servers, not live lab configuration.

| Check | Result |
| --- | --- |
| Scorer/probes/lifecycle/reporting | 134 passed |
| Portal, package-source and installer behavior | 33 passed |
| Panel/API/store/socket/control | 51 passed; 1 upstream parser integration skipped |
| Controller/policy regressions | 17 passed |
| Shell syntax | 56 files passed |
| PowerShell syntax | 66 files passed |
| Independent source-copy package build | 23 payload files; all file hashes and ZIP members verified |
| Packaged custom runtime imports | Passed |
| Reusing stale package/workspace output | Refused as intended |
| Workspace output inside source inputs | Refused as intended |

Total: **235 tests passed, one skipped, no failures or errors** in the final local Linux runs. The skipped test compares launcher arguments with the complete upstream CALDERA parser. A full matching checkout and dependencies are required to run it; custom plugin-selection and API authentication tests did run.

The independent copy had no private source archive. It assembled both workspaces and built the portal package from the candidate alone. [Machine-readable results](validation-results.json) record the checks. [Source integrity](SOURCE-MANIFEST.json) is checked with `python tools/check_source.py`, together with Python/JSON parsing, local documentation links and publication exclusions.

An initial Windows attempt encountered sandbox, file-lock and POSIX-mode differences. Those failures were not silently skipped or treated as success; the supported Linux runs above supersede them. Detailed local troubleshooting logs remain outside this candidate.

PHP syntax was not rerun during this curation because no local PHP runtime was installed. The three deployed PHP routes retain their original source except line-ending normalization; the earlier private collection recorded successful PHP syntax checks. This is historical evidence, not a new PHP test result.

Source tests and package construction do not establish a successful fresh nine-VM deployment, new panel production bundle, native guest acceptance, full four-hour exercise, or restore rehearsal. No live installer, scorer, guest fault, recovery action or exercise was run for this curation.
