# Summit Supply cyber defense lab

A nine-VM practice environment in which students secure a fictional outdoor-equipment company while keeping its storefront, database, directory, forum and mail services working.

The project combines segmented networking, guest security checks, functional service scoring, timed business tasks, and a controlled simulated red team. It was built for club practice and documented for a maker portfolio. This is a curated source snapshot, not the original development Git history.

**Start with the [architecture](docs/ARCHITECTURE.md), [code tour](docs/CODE-TOUR.md), and [demonstration evidence](docs/DEMO.md).** The [contribution statement](CONTRIBUTIONS.md) identifies design, hands-on work, collaborators, upstream software and AI assistance.

| Folder | What belongs here |
| --- | --- |
| [competition-code](competition-code/README.md) | Custom software and configuration used during the event: Aeacus probes, shop, scorer, portal and red-team runtime |
| [preparation](preparation/README.md) | Image construction, scenario staging, installation, packaging, acceptance, tests and recovery |
| [tools](tools/prepare_workspace.py) | Local workspace assembly for tests and package builds |
| [docs](docs/GETTING-STARTED.md) | Architecture, setup, validation, dependencies and remaining release work |
| [third-party](THIRD_PARTY_NOTICES.md) | Required upstream licensing notices |

## Local source checks

Use Python 3.12. The inherited test suites target Linux; score01 tests use the Python standard library. Panel tests additionally need the [documented dependencies](docs/DEPENDENCIES.md).

```sh
python tools/prepare_workspace.py score01
cd .build/score01
python -B package_portal.py
python -B -m unittest test_scorer test_lifecycle test_reporting test_server test_inject_services test_inject_schedule test_http_resource test_mail_inject test_shop_probe
python -B -m unittest test_portal test_portal_installer test_shop_probe_installer test_inject_upgrade
```

The workspace command only copies local files. See [getting started](docs/GETTING-STARTED.md) for panel tests and configuration prerequisites. Creating a package does not install it.

This snapshot includes source and configuration examples, not VM disks, credentials, live databases, opaque generated installers, or encrypted scoring snapshots. Image builders intentionally create training weaknesses and are intended for disposable isolated lab machines. A clean nine-VM rebuild and full-duration rehearsal have not been validated for this curated snapshot; see [validation](docs/VALIDATION.md) and the [release checklist](docs/RELEASE-CHECKLIST.md).

No license is currently granted for original custom code. Third-party material retains its licenses; see [rights](RIGHTS.md) and [notices](THIRD_PARTY_NOTICES.md). This folder is prepared locally and has not been published.
