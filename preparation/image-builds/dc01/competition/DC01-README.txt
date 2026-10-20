Summit Supply - DC01 competition image

DC01 is Windows Server 2022 Standard, the only domain controller and DNS server
for corp.summit.test (CORP), at 10.77.40.10. Keep its hostname, address, domain,
directory database, SYSVOL, NETLOGON, employee accounts, DNS records and lab time.
AD DS, DNS, Netlogon, DFSR, Windows Time and organizer SSH must remain available.
Preserve the existing firewall, domain trusts, certificates and update sources.
Do not change other lab machines, hypervisor, range-fw or score01.

Authorized standard employees (enabled, unlocked, no administrative/operator roles):
maya.chen, emma.wilson, liam.brooks, jordan.lee, ava.thompson, noah.garcia,
sam.patel, olivia.martinez, ethan.clark, isabella.nguyen, lucas.reed, mia.robinson,
benjamin.scott, charlotte.adams, alex.morgan, taylor.ross.
Authorized named domain administrators: alex.admin and taylor.admin.
Preserve CORP\Administrator and organizer bootstrap account CORP\jwang.
Former employees casey.turner and drew.parker must be disabled, retained and
unprivileged. No additional interactive domain accounts are authorized.
Preserve machine accounts, krbtgt and legitimate built-in/service identities.
Credentials are supplied privately by White Team; no password reset is required.

Required protection:
- SMB server must require signing. Preserve SMB2/3 and directory shares.
- corp.summit.test DNS zone must accept secure dynamic updates only and must
  not permit zone transfers. There is no secondary DNS server in this lab.
- Print Spooler and Remote Registry are unnecessary on DC01; stop and disable.
- Keep the Security event log enabled with at least 64 MiB capacity.
- Remove unauthorized persistence and its payload while retaining incident evidence.
- Remove fictional plaintext credential material and unauthorized personal media
  throughout C:\SummitSupply, including renamed copies. Preserve business files.

The retained incident evidence under C:\SummitCompetition\Evidence is synthetic.
It supports three independent forensic questions; it is not a live attack log.
Open each question using its desktop shortcut and save your answer below Answer:.
Question files and evidence must remain available after cleanup.
Do not execute evidence payloads. The simulated persistence has no network activity.

Local Aeacus score: 28 checks, 100 points. Open Summit Scoring Report on the desktop.
Business availability scoring on score01 is a separate organizer system.
Do not alter scoring programs, probes, configuration or manufacture probe output.
Scoring errors or stale reports should be reported to White Team.
Administrator access can inspect local scoring internals; this lab assumes fair play.

White Team retains the pre-build VMware snapshot for recovery. Do not revert,
reinstall, reboot or export without coordinating with White Team. Final desktop,
reboot and recovery acceptance is performed separately before event distribution.

Expanded image: 25 vulnerabilities plus 3 forensic questions; 28 checks, 100 points.
Keep all firewall profiles enabled, Defender real-time protection enabled, and Windows Update service available.
Preserve the file-specific official scorer exception at C:\aeacus\phocus.exe.
Require administrator elevation consent on the secure desktop; keep UAC enabled.
Audit Logon and Process Creation success and failure.
SummitOps share and Operations inventory are required: SMB encryption required; Domain Users read only.
Domain users must not modify Operations files or Automation scripts; preserve inventory data.
Keep SummitInventoryMaintenance enabled as LOCAL SERVICE; its supplied script writes only a harmless marker.
The unauthorized legacy training root CA must not remain trusted. Preserve legitimate certificate trust.
Forensic evidence and all three blank answer files must remain available.

