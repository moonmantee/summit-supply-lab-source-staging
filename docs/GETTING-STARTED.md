# Testing and packaging locally

Use Python 3.12 on Linux for the inherited test suites. Package/workspace assembly also runs on Windows. No tool here should be run as root for source tests.

From the repository root:

```sh
python tools/prepare_workspace.py score01
cd .build/score01
python -B package_portal.py
python -B -m unittest test_scorer test_lifecycle test_reporting test_server test_inject_services test_inject_schedule test_http_resource test_mail_inject test_shop_probe
python -B -m unittest test_portal test_portal_installer test_shop_probe_installer test_inject_upgrade
```

The package builder emits `team-portal-package/`, a ZIP and a fresh SHA-256 inventory. It refuses to reuse an existing output directory so files from an old build cannot slip into a new package. For another run choose a new workspace with `--output PATH`.

Inside the repository, custom output paths must be under `.build/` so a workspace cannot overwrite or recursively copy its own source inputs. A new directory outside the repository is also supported.

For the panel, install the Python dependencies in your own virtual environment, then return to the repository root. The workspace includes an attributed upstream utility for isolated authentication tests; it does not need the private source archive:

```sh
python -m pip install -r preparation/panel-context/requirements.txt
python tools/prepare_workspace.py panel
cd .build/panel
python -B -m unittest discover -s tests -v
python -B tests/run_regressions.py
```

The test that compares launcher arguments with the actual CALDERA parser needs the matching upstream checkout and its dependencies. Set `CALDERA_ROOT` to that checkout. Without it, that one integration test reports a skip; custom plugin-selection tests still run. [Panel packaging](PANEL-PACKAGING.md) documents the additional frontend build and target-specific inventory needed for a new guarded release.

Runtime examples use the fictional lab network. Supply fresh deployment credentials locally; examples intentionally contain redacted values. The scorer needs its configuration, trust certificates and intended services. Portal installation upgrades an existing score01 deployment with its established scoring database and Nginx site; it does not create a nine-VM lab. Review the [portal operation notes](legacy-score01/PORTAL-README.md) before any disposable-clone installation.

No VM disks, operating-system installers, private signing keys, authentication stores or current event databases are included. See [image prerequisites](IMAGE-BUILDS.md), [validation](VALIDATION.md) and [remaining collection](VM-COLLECTION-CHECKLIST.md).
