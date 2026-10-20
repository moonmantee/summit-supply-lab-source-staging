# External dependencies and provenance

| Dependency | Recorded source/version | Included here |
| --- | --- | --- |
| Aeacus / Phocus | [Official v2.1.1](https://github.com/elysium-suite/aeacus/releases/tag/v2.1.1) | Custom check inputs/probes; no engine source subset or binaries |
| CALDERA | [Recorded immutable revision cb8d6a8160e0f4990af323a7c071d5e8482b42c7](https://github.com/mitre/caldera/tree/cb8d6a8160e0f4990af323a7c071d5e8482b42c7) | Custom launcher, policy and plugin integration |
| Magma | [Recorded submodule revision 317cfdcdfb9e16a32ffbfb7133e9d1ab9caf0596](https://github.com/mitre/magma/tree/317cfdcdfb9e16a32ffbfb7133e9d1ab9caf0596) | Modified Navigation component; obtain the matching full upstream checkout to build |
| Python | Collected Linux hosts: 3.12.3 | Source only; scorer tests use standard library |
| Panel Python dependencies | Recorded lab requirements: aiohttp 3.14.3, PyYAML 6.0.1, aiohttp-security 0.4.0, argon2-cffi 25.1.0, Jinja2 3.1.6 | Direct test dependencies pinned in `preparation/panel-context/requirements.txt`; packages are external |
| PHP, MariaDB, Apache, Nginx, IIS | Role-specific service configuration and SQL schemas | Custom shop and examples; server runtimes external |
| phpBB / MailEnable | Existing forum/mail services | Configuration/schema only; no upstream application or proprietary installer |
| Proxmox / pfSense / guest OSs | Existing lab infrastructure | Selected configuration examples; no platform distributions or VM disks |

The recorded CALDERA/Magma revisions come from the original deployment package's provenance. They are build targets, not a claim that a fresh full upstream checkout was reconstructed or accepted during curation. New dependencies or frontend bundles require their own review and license inventory.

For the Linux Aeacus 2.1.1 release archive, the retained shop installer expects SHA-256 `bd75e05505bd1a1e288b0453a4611ad88f6794dd54063db16485e0328c69f149`. Download upstream packages separately and verify the expected artifact before using them.
