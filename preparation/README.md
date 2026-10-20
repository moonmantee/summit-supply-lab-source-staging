# Preparation and organizer tools

These files are used to build, stage, install, test or recover the exercise. They are separate from software that normally runs during the competition.

| Folder | Purpose |
| --- | --- |
| `image-builds/` | Role-specific construction, readable scoring inputs, vulnerability staging and scoped solve/reset source |
| `database/` | Schema, fictional product seed and application account template |
| `installation-and-event-setup/` | Score01 install and event/inject setup |
| `packaging/` | Portal and panel package builders and guarded installers |
| `acceptance/`, `red-team/`, `verification/` | Native checks, acceptance and organizer verification |
| `tests/score01/`, `panel-context/` | Isolated source tests and required fixtures |
| `network/` | Firewall and isolation construction source |
| `operations/`, `recovery/` | Organizer maintenance and solve/reset helpers |

For scorer and panel testing or packaging, first use `../tools/prepare_workspace.py`; see [getting started](../docs/GETTING-STARTED.md). It provides the expected sibling files using only this candidate. Do not run categorized installers in place and assume their original relative paths still apply.

Image-construction scripts preserve their role-specific inputs, but require an appropriate base OS, upstream Aeacus binaries, supplied private credentials, console/snapshot recovery and deliberate guest configuration. See [image prerequisites](../docs/IMAGE-BUILDS.md). Bootstrap SSH wrappers, obsolete workstation baselines, raw observations and encoded generated bundles are excluded. Builders that create bundles remain as readable source.

The preparation tree includes organizer solutions. It is not a contestant distribution; release only the intended handouts and task resources to participants.
