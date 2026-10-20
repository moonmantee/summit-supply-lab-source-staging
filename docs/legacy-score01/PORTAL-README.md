# Summit Supply team portal

The portal provides Overview, the existing Summit Scoreboard and history, Services, Injects, README, Help, and a private Organizer console. The existing availability scorer remains authoritative. Released automatic tasks add service probes to that scorer; portal views read its database read-only. Portal state is separate and scoped to the current event. Aeacus host scores remain in each VM's local report and are excluded from the portal total. The embedded scoreboard preserves its existing styling and omits organizer controls and control tokens.

## Install

Copy the contents of the generated team-portal-package directory to a private staging directory on score01. From its console run:

```bash
sudo bash /home/jwang/team-portal-package/portal-install.sh
```

The installer checks score01, backs up scorer code/configuration and the database plus the previous portal/Nginx configuration, briefly quiesces the check timer, installs the additional probes, and restores the timer's previous running state. It preserves existing event state, score history, credentials and portal history. It validates Nginx and starts summit-team-portal.service. It does not start/reset the competition or change defended guests.

Team URL: http://10.77.70.10:8080/portal/. Existing public files remain under /downloads/ or their original direct paths. Set the browser's proxy bypass list to include 10.77.70.10 and the lab's internal destinations; Squid intentionally rejects private destinations. The HTTP endpoint is intended only for the existing isolated lab network. Use an SSH tunnel for off-lab access; do not publish it to the internet. A production HTTPS endpoint requires a trusted certificate and an explicit network deployment decision.

Retrieve the generated team and organizer passwords locally from /home/jwang/summit-portal/portal-state/INITIAL-PORTAL-CREDENTIALS.txt. This file is mode 600 and is never served by the portal. Issue only the team password to competitors. Default usernames are team and admin; passwords are generated on the target and are distinct from VM credentials.

## Organizer access

From the organizer computer, use the existing trusted SSH configuration:

```powershell
ssh -N -L 8767:127.0.0.1:8767 score01
```

Open http://127.0.0.1:8767/portal/#organizer and sign in as admin. Organizer login and actions are rejected through the team-facing Nginx endpoint even with the correct organizer password. Lifecycle Start/Stop/Reset remain on the existing organizer scoreboard at loopback port 8766.

The private console supports:

- Creating drafts with task details, points, release time, deadline, and acceptance criteria.
- Attaching up to ten files per draft, each at most 2 MB. Use simple filenames without paths or spaces. Attachments become team-accessible only after the card is released.
- Manual release or scheduled release while the event is RUNNING.
- Announcements, support contact, console link, and event end time.
- Private JSON configuration for automatic service checks before release. Credentials are never returned in API snapshots or audit records. Automatic tasks cannot receive manual point awards.
- Manual verification for explicitly selected manual-review tasks.
- Current-event audit records and summaries of preserved prior events.

I01â€“I06 are private automatic starter drafts, worth 100 completion points in total (10, 10, 15, 15, 25, 25). The installer configures I01 DNS (UDP and TCP), I02 exact passive FTP retrieval with anonymous and upload denial, and I04 trusted TLS, forum content marker and HTTP redirect. It generates fictional inventory, a dedicated inventory_reader password and a lab-only forum certificate/key package on score01; attachments remain private until release. The default forum content marker is Summit; verify it against your forum page and adjust the private check before releasing. I03 remains blocked until the organizer supplies the real operations mailbox credentials, mail DNS name and trusted certificate path. Its check uses authenticated STARTTLS submission on 587 and IMAPS retrieval on 993. The mail DNS name must resolve exclusively to 10.77.30.30 on score01.

I05 publishes the supplied shipping-policy.txt at https://10.77.30.10/shipping-policy.txt with shop01's existing certificate. I06 deploys http://10.77.20.10:8080/health.json on workstation01. Both verify HTTP 200 and exact fixture bytes by SHA256; redirects, edits, login pages and error pages fail. Each awards 25 completion points after three consecutive on-time PASS rounds, plus 3 availability points per PASS and a 10-point SLA deduction per five consecutive DOWN rounds. Resources include a final newline; publish the attachment unchanged. White Team must allow only score01 to workstation01 TCP 8080 on range-fw (preparation/network/add-inject-warehouse-rule.php); competitors handle the guest firewall and endpoint. These tasks do not install their service on competitors' behalf.

When released, a task becomes a new availability service. Three consecutive recorded PASS rounds completed before its deadline award its completion points once. A DOWN or INVALID resets the completion streak. New services continue earning per-round points and receiving the existing five-DOWN SLA deductions after completion or deadline expiry. Stopping freezes scoring; reset selects a new event and excludes old task services. A released HTTPS task also permits the exact required HTTPS redirect in the original forum HTTP check, so fulfilling that task does not cause an HTTP outage penalty.

Automatic release schedule: the organizer can arm I01â€“I06 for the next Start while READY or STOPPED. The selected default is a four-hour completion window, first release at Start, later releases every 30 minutes, and a 30-minute grace period per task. Relative timing anchors to the next Start/Resume, rather than the previous start of an existing event. During grace there are no new-service probes, availability points, completion passes, or SLA deductions; the service enters the uptime scoreboard on the first check round after grace expires. Existing baseline services keep being checked. Grace starts at actual publication, including a delayed release. Unconfigured tasks remain blocked. Pauses do not extend wall-clock schedules, grace, or deadlines. The four-hour window sets the completion deadline and display clock; the organizer still presses Stop to end uptime scoring. Released task timing is immutable. Relative schedules and grace are preserved with event history, and a reset does not inherit them.

The FTP check does not overwrite/delete the business fixture, and the HTTPS check does not create forum posts. Those operational policies are distinguished from the exact automatically graded criteria in the card. Mail probe messages carry a unique header; only those messages are marked deleted, and other mailbox messages are never expunged.

Example private configuration for the mail draft (replace values locally in the organizer form):

```json
{"probe":"mail_alias","host":"10.77.30.30","server_name":"mail01.corp.summit.test","ca_file":"/home/jwang/summit-portal/portal-state/resources/mail-ca.crt","username":"operations@corp.summit.test","password":"REPLACE_AT_DEPLOYMENT","recipient":"dispatch@corp.summit.test","points":4,"sla_penalty":12}
```

## Event behavior

The team can acknowledge while RUNNING and before the deadline. Automatic cards show the live service status and 0â€“3 passing-round progress; they do not require a submission. Manual cards retain Ready for verification and organizer feedback. Completed points are permanent. Deadline eligibility uses completed scoring-round timestamps, not probe start time.

Deadlines are absolute timestamps. Stopping the event blocks new team actions and scheduled releases but does not extend deadlines. Scheduled cards whose windows were missed remain visible as Expired when the event resumes. Set release/deadline inputs using the organizer browser's local timezone; team displays use America/Denver.

Reset & archive on the existing scorer selects a new event. The portal automatically shows empty injects and zero inject awards for that new event, preserving older records. Run portal_server.py seed for the new event if the same draft set is wanted. Do not reset the lab merely to install or test the portal.

The portal refreshes every 30 seconds. Scoring timestamps older than six minutes while RUNNING are labeled stale. Missing scorer data is explicitly unavailable rather than fabricated UP/DOWN or zero-score evidence. Check actual client workflows regardless of the configured probe result.

## README and credentials

The package contains the current shared Markdown and Word handouts. README viewing/download requires login. Blank credential fields stay blank. Publish a filled team copy only inside portal-state/files; never copy a credential-filled handout to the unauthenticated /srv/summit-downloads directory.

For the originally planned named competitor accounts, this handout retains the currently documented admin usernames. Merely listing jwang everywhere would not create or authorize those accounts on the guests.

## Operations and rollback

```bash
systemctl --user status summit-team-portal.service
journalctl --user -u summit-team-portal.service -n 40 --no-pager
python3 /home/jwang/summit-portal/portal_server.py passwords
```

Password rotation prompts interactively and invalidates existing sessions. The initial credential file records only initial passwords; remove or archive it privately after rotation. Sessions expire after eight hours, use HttpOnly/SameSite cookies, and require CSRF protection for changes. Five failed password attempts from one source temporarily block login for 15 minutes.

Installation failure automatically restores the prior scorer code/configuration, Nginx, portal and unit where present. For later rollback, use the exact reported backup: stop the check timer and portal, restore scorer.py/config.json and the backed-up scorer helper modules, restore Nginx and prior portal/unit, validate Nginx, reload user systemd and restore previous service states. Keep portal SQLite and attachments together. Preserve results.sqlite3 when rolling back code; restoring the database snapshot would discard subsequent score history.

Before an event, verify team login from workstation01, organizer denial through Nginx, README download, draft invisibility, attachment visibility only after release, submission/grade behavior, fresh service results, and unchanged organizer scoreboard/check timer. These live checks are separate from the local automated tests.
