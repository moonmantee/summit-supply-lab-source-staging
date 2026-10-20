# Third-party notices

Original Summit Supply material has no new license grant; see [rights](RIGHTS.md). Existing upstream rights remain intact.

## CALDERA and Magma

CALDERA and Magma are upstream works distributed under Apache License 2.0. The modified Magma component at `competition-code/red-team/caldera/plugins/magma/src/components/core/Navigation.vue` remains subject to that license. A modification notice identifies the Summit Supply integration changes. The full [Apache license](third-party/Apache-2.0.txt) and [retained CALDERA notice](third-party/CALDERA-NOTICE.txt) accompany the integration source. Original upstream copyright and license notices, where present, are retained.

Obtain the full matching upstream source and dependencies from the recorded revisions in [dependencies](docs/DEPENDENCIES.md). This snapshot does not distribute a compiled Magma bundle, a complete CALDERA checkout or bundled third-party Python/Node packages. If distributing a built bundle later, retain the notices for its actual contents.

`third-party/caldera-test-support/app/utility/config_util.py` is the retained Apache-licensed CALDERA configuration utility from the recorded revision. Isolated API tests use its real Argon2 verification function. It is upstream code, not an original Summit Supply contribution or a replacement CALDERA installation.

## Other platforms

Aeacus/Phocus is an external GPL-2.0 dependency; neither its incomplete copied engine source nor its native binaries are distributed here. Custom check inputs and probe source are included. phpBB, MailEnable, pfSense, Proxmox and operating systems remain the work of their respective authors; this repository provides custom code, schema or configuration examples rather than those products' distributions.

The demonstration stills show the fictional training environment. No club-member photographs or third-party event photographs are included.
