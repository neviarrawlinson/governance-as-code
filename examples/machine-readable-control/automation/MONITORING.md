# Scheduled assurance monitoring

`Governance Assurance Monitoring` observes the weekly assurance workflow on `main`.
It runs after a scheduled assurance run completes and independently checks daily at
07:17 UTC. Manual runs default to preview; choose `live` to allow updates to the
dedicated monitoring issue. Automatic runs also begin in preview. After reviewing
the first report, set the repository Actions variable `GAC_MONITORING_ENABLED` to
the exact value `true` to enable automatic monitoring issue updates. Remove it or
set it to `false` to return automatic runs to preview. Manual preview remains
read-only regardless of that variable.

The monitor alerts when the newest scheduled run completes unsuccessfully, when
no successful scheduled run is observed, or when the last scheduled success began
more than eight days ago. Manual and push successes do not reset this clock.
An eight-day threshold gives the weekly schedule one day of grace. Long-running
or queued runs cannot indefinitely conceal an overdue success.

The single issue is assigned to `neviarrawlinson` with a one-business-day review
target. It contains run links, available failed job/step names, and the next action.
Review Actions scheduling, run errors, and trusted-state availability. GitHub
assignment and subscription settings determine notification delivery; the monitor
does not send email or configure account notifications.

Unchanged evidence causes no issue update. On recovery, the generated section is
updated to HEALTHY; the owner records a review decision and closes the monitoring
issue manually. A subsequent problem reopens that issue. Human notes outside the
generated section are preserved. Duplicate monitor markers or damaged section
boundaries stop updates for human reconciliation. Control issue #3 is separate.

Run summaries and `governance-monitoring-<run-id>` artifacts retain observations for
30 days. Monitor API failures fail the monitor workflow; they never imply healthy
assurance. Because both schedules depend on GitHub Actions, this does not detect a
complete Actions outage or a disabled monitoring workflow. An external recurring
review is still useful. Artifact retention policy is unchanged.

## Review before activation

After merging, run the monitoring workflow on `main` with `mode=preview` and inspect
its proposed operation. A missing recent scheduled success can legitimately propose
an issue even when manual preview runs are successful. Do not manufacture a success
or reset trusted history to suppress an alert. Merge installs the automatic checks;
issue updates require the separate activation variable described above.

Local regression checks run with the existing automation test suite:
`python -m unittest discover -s automation/tests`.
