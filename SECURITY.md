# Security policy

## Reporting a problem

Do not open a public issue for anything you think is a vulnerability. Saurix indexes arbitrary repos and shells out to git for GitHub URLs, so I take reports about command injection, path traversal, or graph file parsing seriously.

The best way to report is GitHub's private vulnerability reporting on this repo (Security tab, then "Report a vulnerability"). If you prefer email, write to anisbaziz.sub@gmail.com with "[saurix security]" in the subject and include:

- What you did, step by step, so I can reproduce it
- What you expected to happen and what happened instead
- The Saurix version (`saurix --version` or the commit hash) and your OS and Python version

Scratch repos or transcripts help. Feel free to redact anything personal.

## What happens next

- I will acknowledge your report within 72 hours.
- I will confirm whether it reproduces and tell you how I see the severity within a week.
- If it is real, I will fix it, add a regression test, and credit you in the release notes unless you ask me not to. I will coordinate the disclosure date with you before publishing anything.
- If it turns out not to be a vulnerability, I will say so plainly and, with your permission, move the discussion to a public issue so the fix or docs change still lands.

## Scope

Saurix is pre-1.0 and maintained by one person. There is no bug bounty and no SLA beyond the timelines above. Supported versions are the latest PyPI release and `main`. Older releases get a fix only by upgrading.
