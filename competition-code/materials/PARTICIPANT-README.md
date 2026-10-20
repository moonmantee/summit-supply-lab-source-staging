# Summit Supply — CCDC Practice Competition

## Blue Team operations brief

**Team-issued handout · Version 1.0 · October 4, 2026**

| Event details | Team information |
|---|---|
| Team name | ______________________________ |
| Competition date | ______________________________ |
| Start / end time | ______________________________ Mountain Time |
| Team console access | ______________________________ |
| Service scoreboard | ______________________________ |
| Inject board and submission channel | ______________________________ |
| White Team contact | ______________________________ |
| Credential-update channel | ______________________________ |

White Team supplies the event details above and completes the Administrator and default credentials section before Start. Keep the completed credential copy within your team. Additional employee and application credentials may be issued separately.

## Welcome to Summit Supply

Summit Supply is an outdoor-equipment distributor serving retail customers and business partners. Our storefront, partner forum, email, databases, and employee workstation support daily sales and warehouse operations.

Your team is the incoming IT staff. The previous contractor left incomplete documentation and systems that require investigation. Management expects you to secure the environment while keeping the business operating. You may encounter unauthorized accounts, unsafe configurations, and evidence of suspicious activity.

Your responsibilities are to:

- Maintain required services and authorized employee access.
- Investigate and correct security problems without destroying business data or incident evidence.
- Complete technical injects issued by White Team during the event.
- Respond to red-team activity and report infrastructure or scoring problems to White Team.

## Assigned systems

You may administer these six machines. Read the local competition README on each machine before changing its configuration; it contains the detailed security policy for that role.

| Host | Operating system | IPv4 address | Business responsibility |
|---|---|---|---|
| dc01 | Windows Server 2022 Standard | 10.77.40.10 | Active Directory, internal DNS, domain time, and required directory/file services |
| workstation01 | AlmaLinux 9.8 | 10.77.20.10 | Employee graphical workstation, domain authentication, and business application access |
| shop01 | Ubuntu 24.04 | 10.77.30.10 | Apache/PHP storefront over HTTPS; catalog, orders, and order history |
| sql01 | Linux Mint 22.3 | 10.77.50.20 | MariaDB data for the storefront and partner forum |
| forum01 | Windows Server 2022 Datacenter | 10.77.30.20 | IIS/PHP/phpBB partner forum and baseline FTP file distribution |
| mail01 | Windows Server 2022 | 10.77.30.30 | MailEnable email and HTTPS webmail |

The firewall, score01, hypervisors, organizer systems, and physical network are managed by White Team. They are outside your administrative and attack scope. There is one domain controller, dc01; there is no dc02 or separate Linux domain controller.

Do not attack other teams, scoring infrastructure, host computers, school/home networks, or public systems. Preserve required data and authorized access. Do not fabricate service responses or impersonate the scoring service.

## Network and identity

The company domain is **corp.summit.test**, with Windows short name **CORP**. Preserve existing domain membership, hostnames, assigned addresses, and service dependencies.

| Segment | Subnet | Default gateway |
|---|---|---|
| Employee workstation | 10.77.20.0/24 | 10.77.20.1 |
| Business application servers | 10.77.30.0/24 | 10.77.30.1 |
| Identity services | 10.77.40.0/24 | 10.77.40.1 |
| Database services | 10.77.50.0/24 | 10.77.50.1 |

Domain members use **10.77.40.10** for internal DNS. Preserve configured lab time sources. Do not substitute public DNS or connect machines to another network to bypass lab restrictions. Internet access and software installation depend on White Team's approved update arrangements.

Windows domain logins use `CORP\username`; Linux domain logins use the supported `username@corp.summit.test` form. Local recovery accounts use their local username. Application credentials are separate from operating-system credentials.

## Required business operations

| Service | Required behavior |
|---|---|
| Directory and DNS | Authorized users can authenticate and internal names resolve. Preserve AD DS, SYSVOL, NETLOGON, domain trust, time synchronization, directory data, and DNS records. |
| Employee workstation | Approved users can use the graphical desktop and business applications. Preserve GNOME, Firefox, the text editor, SSSD, SELinux, and required network access. |
| Storefront | Customers can browse the catalog and use designated ordering and order-history workflows over HTTPS. Preserve products, prices, orders, approved certificates, and the sql01 connection. Starting endpoint: https://10.77.30.10/. |
| Database | shop_app from 10.77.30.10 accesses summit_shop; forum_app from 10.77.30.20 accesses forum. Preserve tables, business rows, and necessary application privileges. MariaDB uses TCP 3306. |
| Partner forum | Authorized users can log in, read, and post. Preserve content and the sql01 connection. Starting endpoint: http://10.77.30.20/. Protocol changes may be assigned through an inject. |
| File distribution | Preserve authorized read-only FTP retrieval on forum01, including ftp_reader, baseline partner-info.txt, and configured passive ports. FTP control uses TCP 21. |
| Email | Preserve existing mailboxes, delivery, authenticated submission, retrieval, and webmail. Starting protocols include SMTP 25/587, IMAP 143, POP 110, and HTTPS webmail 443. Starting webmail endpoint: https://10.77.30.30/. |
| Administration | Preserve authorized console and SSH access, local recovery, and required remote administration specified in each machine's README. SSH uses TCP 22. |

Maintain access for ordinary authorized clients as well as the scorer. Allowing only the scoring server, replacing an application with a static success page, or stopping a required service does not satisfy business requirements.

Certificate trust, mail TLS endpoints, and application compatibility follow the supplied machine instructions and released injects. Coordinate database TLS and application credential changes with White Team before requiring incompatible client settings. Do not assume IMAPS on TCP 993 is an established starting service; White Team will specify any additional TLS requirement.

## Authorized access

Use the Administrator and default credentials section for initial administrative logins and any supplementary credential sheet for employee and application access. An account's listed role describes its required state; the inherited configuration may grant excessive privileges that your team must correct.

### Domain employees

These 16 accounts must remain enabled, usable, and free of administrative or operator privileges. Their names do not grant server administration or Linux sudo access. Preserve supported employee desktop access as defined by the workstation README.

| Account | Employee | Department |
|---|---|---|
| maya.chen | Maya Chen | Sales |
| emma.wilson | Emma Wilson | Sales |
| liam.brooks | Liam Brooks | Sales |
| jordan.lee | Jordan Lee | Warehouse |
| ava.thompson | Ava Thompson | Warehouse |
| noah.garcia | Noah Garcia | Warehouse |
| sam.patel | Sam Patel | Customer support |
| olivia.martinez | Olivia Martinez | Customer support |
| ethan.clark | Ethan Clark | Customer support |
| isabella.nguyen | Isabella Nguyen | Operations |
| lucas.reed | Lucas Reed | Operations |
| mia.robinson | Mia Robinson | Operations |
| benjamin.scott | Benjamin Scott | Finance |
| charlotte.adams | Charlotte Adams | Finance |
| alex.morgan | Alex Morgan | IT — standard account |
| taylor.ross | Taylor Ross | IT — standard account |

**alex.admin** and **taylor.admin** are the named IT administration accounts. Preserve their authorized domain administration. On workstation01, administration is assigned through Linux-Workstation-Admins and requires authenticated sudo. Domain Admin membership alone does not authorize unrestricted sudo on every Linux machine.

**casey.turner** and **drew.parker** are former employees. Retain their accounts and business records, but disable access and remove privileges. They must not retain independent application access.

Preserve the built-in domain Administrator and organizer bootstrap account CORP\jwang. Computer accounts, krbtgt, legitimate built-in groups, and required service identities are not unauthorized employees.

### Local and recovery identities

| Host | Authorized identities and roles |
|---|---|
| dc01 | CORP\Administrator, alex.admin, and taylor.admin: approved administration; CORP\jwang: organizer recovery |
| workstation01 | competitor-recovery: local competitor fallback administrator; jwang: organizer recovery; summit-employee and summit-auditor: ordinary local employees; summit-admin: retained disabled identity; summit-keyuser: retained noninteractive key fixture |
| shop01 | summit_editor: approved maintenance administrator; jwang: organizer/recovery administrator; summit_employee and summit_support: ordinary employees |
| sql01 | jwang: supported local administration/recovery; alex.admin and taylor.admin: existing authorized domain login without assumed sudo; summit_employee and summit_contractor: locked, noninteractive, unprivileged identities; summit_marker: locked system fixture |
| forum01 | labadmin: competitor administration/recovery; Administrator and jwan5: organizer access; forum.audit: enabled standard user; ftp_reader: read-only FTP service account |
| mail01 | labadmin and mail.fallback: approved local administration/recovery; Administrator: retained administration; mail.audit: enabled standard user; IME_ADMIN and IME_USER: required MailEnable service identities |

Preserve documented domain administration on Windows members and additional authorized domain access specified in local READMEs. Retain required system/application identities and organizer access keys. Consult White Team before removing an ambiguous account on which a service may depend.

Application administrators, mailbox users, database credentials, and authorized scoring identities are supplied through the credential sheet and machine documentation. Service accounts do not receive interactive administration merely because they support a business service.

## Administrator and default credentials

White Team completes the blank password fields with the event's initial credentials before issuing this copy. These are starting competition passwords; they are not factory defaults. Blank fields do not mean an account has an empty password. Use the account exactly as listed, including its domain or local scope.

| System / scope | Administrator login | Authorized role | Initial password |
|---|---|---|---|
| CORP domain / Windows servers | CORP\alex.admin | Named domain administrator; approved workstation sudo | ____________________ |
| CORP domain / Windows servers | CORP\taylor.admin | Named domain administrator; approved workstation sudo | ____________________ |
| dc01 | CORP\Administrator | Built-in domain administrator | ____________________ |
| workstation01 | competitor-recovery | Local fallback administrator; authenticated sudo | ____________________ |
| shop01 | summit_editor | Local maintenance administrator; authenticated sudo | ____________________ |
| sql01 | jwang | Supported local administrator; authenticated sudo | ____________________ |
| forum01 | .\labadmin | Local competitor administrator and recovery | ____________________ |
| mail01 | .\labadmin | Local administrator | ____________________ |
| mail01 | .\mail.fallback | Local fallback administrator | ____________________ |

On Windows, `.\` selects a local account. On Linux, use `alex.admin@corp.summit.test` or `taylor.admin@corp.summit.test` for the corresponding approved domain login. Preserve each machine's existing authorization policy; domain administration does not automatically grant Linux sudo on shop01 or sql01.

Organizer-only access credentials are retained by White Team. Application administration credentials may be recorded below when issued; they do not grant operating-system administration.

| Application | Administrator username | Initial password |
|---|---|---|
| Storefront administration | ____________________ | ____________________ |
| Partner forum administration | ____________________ | ____________________ |
| Mail administration | ____________________ | ____________________ |

Follow the credential-update procedure before rotating any password used by applications or scoring. Keep a record of team password changes in your private team credential log.

## Scoring

The exercise has three scoring components. White Team announces their weighting and event-specific adjustments before Start.

| Component | What your team must do |
|---|---|
| Service availability | Maintain reachable, functional required services throughout the event. Repeated outages can incur SLA deductions. Monitor the scoreboard and verify real client workflows. |
| Host security and forensics | Correct required configurations and answer individual forensic questions. Use each machine's local scoring report. Configuration credit can be lost if a repair regresses. |
| Technical injects | Complete released tasks within their stated windows and satisfy their acceptance criteria. Follow each card's submission or automatic verification instructions. |

Local Aeacus reports and the central availability scoreboard measure different things. A high local score does not prove the business is operating. UP/DOWN describes service health; INVALID indicates a confirmed scoring/configuration problem requiring White Team attention.

Open each forensic question through its individual desktop shortcut. Save the answer in that question's designated section and preserve the question and evidence files. Follow the specified answer format; there is no shared answer sheet.

Do not modify scoring executables, probes, encrypted configuration, report contents, or scoring identities to manufacture credit. Preserve the documented file-specific exception for the official Windows scoring executable where supplied. Report stale reports or suspected scoring errors with the host, check, time, and observed behavior.

## Technical injects

White Team releases task cards during the event. Each card identifies the target systems, required result, supplied resources, deadline, points, and acceptance/submission method. Unreleased tasks have no completion requirement.

Assign someone to track release times and deadlines. Read each entire card, confirm dependencies, and verify ordinary business access after the change. Use supplied certificates, packages, and fixtures when directed. Do not assume public internet access or purchase resources to complete a task.

Unless a card explicitly requests one, a business email, screenshot, or written report is not required. A task must meet its technical acceptance criteria; a claim of completion alone earns no credit. Ask White Team to resolve conflicting instructions before applying a disputed change.

## Red-team activity and incident response

The opposing team may probe services, attempt authentication, exploit weaknesses, or use an existing in-guest foothold within the assigned environment. Some incident evidence on disk is synthetic training material; follow each question's instructions when interpreting it.

Investigate suspicious activity, restrict unauthorized access, remove unauthorized persistence, and repair systems while preserving business functions. Record useful timestamps and actions, retain evidence, and verify that containment did not lock out authorized users.

Do not retaliate against attacker systems or scan outside the assigned environment. Report activity affecting organizer infrastructure or other networks immediately. White Team may identify organizer-controlled incident simulations; their delivery mechanism does not establish a successful remote compromise.

Defensive tools must comply with local machine policy. A scanning tool permitted on an administration system may be prohibited on the employee workstation. Do not execute unknown evidence files to investigate them.

## Change control and recovery

Make defensive changes within the assigned machines, subject to their local policies and released tasks. Preserve business data, legitimate users, service identities, installed access keys, approved trust, and recovery access.

- Coordinate shared account and firewall changes with your teammates.
- Follow the credential-update channel before changing application/scoring credentials. Update dependent clients as part of the same change. If the procedure is unavailable, contact White Team first.
- Obtain White Team direction before rebooting where required by the local README, reverting snapshots, reinstalling, replacing, exporting, or changing network identities.
- Do not remove domain membership or change domain policy as a shortcut to a local repair. Domain administration belongs on dc01 and must preserve access across the lab.
- Preserve required security and scoring services. Use approved update sources and avoid uncoordinated upgrades that break application compatibility.

White Team controls backups and infrastructure restoration. A restore may affect domain trust or service dependencies; request assistance rather than reverting independently.

## Working with White Team

Use the published contact channel for scoring questions, infrastructure failures, credential updates, task clarification, and recovery requests. Include:

1. Host and affected service or task.
2. Time observed, in Mountain Time.
3. Exact symptom or error, without passwords or private keys.
4. Relevant recent changes and what you have checked.
5. The assistance or decision needed.

White Team communicates pauses, deadlines, authorized infrastructure changes, and End. Do not assume a pause or extension until announced. Stop administrative and task activity when End is called unless White Team authorizes further work.

## First 15 minutes

1. Read this brief and the six machine READMEs; confirm your credential sheet and console access.
2. Assign identity/workstation, storefront/database, forum/FTP, mail, and inject tracking/incident coordination responsibilities.
3. Check the scoreboard and starting business workflows. Report unexpected infrastructure failures.
4. Confirm local recovery access before changing authentication or privileges.
5. Establish a shared change log, identify priority risks, and watch for released injects.

Keep the company operating while you secure it.
