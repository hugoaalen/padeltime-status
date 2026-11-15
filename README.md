# PadelTime external monitor

Independent checks of the public PadelTime health endpoint, intended every 15 minutes.
The production clock and the application do not need to be open for this monitor.

A failed probe is retried after 15 seconds. Persistent failures create one public
incident assigned to `hugoaalen`. Repeated failures reuse that issue without new
comments. The next healthy check posts recovery and closes it. A green Actions run
means the monitor completed its work; **Issues show the current service incident**.

GitHub delivery to web/email depends on the owner's notification settings. Verify
with the manually triggered `drill` input. It creates and closes a labelled test issue
without simulating a real service outage. Failed monitor execution itself remains a
failed Actions run, providing a separate signal if the probe or notification mechanism
breaks. No user data, application credentials or collector secrets are used.

This repository is public so standard GitHub-hosted runners are free. The workflow
refuses to run in private or renamed forks; no paid runners, artifacts or application
source are needed. Source for deployment is maintained in the private PadelTime app
under `infra/monitor`; publish only this directory to the status repository.

Limits: scheduled Actions can be delayed, and public repository schedules are disabled
after 60 days without repository activity. This is best-effort monitoring, not an SLA.
Re-enable the workflow if GitHub disables it. Empty sports schedules and a correctly
running idle collector are not treated as outages. A stopped collector, stale active
data, repeated HTTP failures and free-capacity blocks are reported.

Sources:
- https://docs.github.com/en/actions/concepts/billing-and-usage
- https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows
- https://docs.github.com/en/actions/concepts/workflows-and-actions/notifications-for-workflow-runs

Tests: `python3 -m unittest -v test_monitor.py`.
