# Image-construction prerequisites

The source targets preconfigured guest machines. It is not a universal installer. Take independent VM snapshots and use disposable clones when validating construction; prepare console recovery before changing authentication or networking.

| Role | Inputs and context |
| --- | --- |
| dc01 | Windows Server 2022 with the intended domain/roster; `preparation/image-builds/dc01/competition/` generates final checks and scenario resources. Upstream Windows Aeacus tools are external. |
| workstation01 | AlmaLinux 9.8, domain membership, desktop and approved local identities; `aeacus-alma/` contains finish/staging source and probes. Generate a fresh finish bundle from `build-finish-script.py` after supplying its documented source inputs. |
| shop01 | Ubuntu 24.04, upstream Aeacus 2.1.1 archive in `vendor/aeacus-linux-v2.1.1.zip`, and local construction inputs. `site/index.html` is the earlier bootstrap storefront; current database-backed PHP runtime is under `competition-code/shop/`. |
| sql01 | Linux Mint 22.3, domain/SSH/MariaDB baseline and application data. `package_build.py` requires upstream `aeacus-linux-v2.1.1.zip` in the role directory, then generates a fresh private build entry point. |
| forum01 | Windows Server 2022, IIS/PHP/phpBB plus MariaDB connectivity; source creates the competition state and native probes. Application and initial credentials are external inputs. |
| mail01 | Windows Server 2022 with installed MailEnable/IIS and mail identities; construction and forensics scripts supply custom scenario state. Mail credentials, private certificates and proprietary software are excluded. |

The role builders retain assertions about original hostnames, accounts and native configuration. Review those preconditions rather than removing them to force a build onto an arbitrary machine. Generated acceptance records and old encoded installers are excluded; run the readable builders to produce artifacts for the intended clone. Trust fixtures and per-image keys should be generated for that clone.

The [collection checklist](VM-COLLECTION-CHECKLIST.md) records remaining exports that could improve exact reconstruction. Native guest acceptance, clean OS construction, functional services and exercise recovery need separate validation before calling this a turnkey lab.
