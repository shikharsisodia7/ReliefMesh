# Public repository security audit

Audited commit set: reachable implementation history through `643a4c1`, plus the current QA worktree.

## Method

- Current-tree and reachable-history pattern scan for Mongo URIs, AWS keys, Resend-like keys, private-key blocks, wallet/key material, and credential assignments; results were recorded as locations only, never values.
- `git fsck --no-reflogs --unreachable` found only Git's empty-tree object.
- Manual review of `backend/.env.example`, Docker/Render configuration, test fixtures, and dependency lock signatures.
- `gitleaks`, `trufflehog`, and the Semgrep CLI were not installed on this machine; this is a transparent limitation, not a claim that those scanners ran.

## Findings

| Location | Secret type | Current/historical | Severity | Rotation required |
| --- | --- | --- | --- | --- |
| `backend/.env.example` | Placeholder connection string and env names | Current and historical | Informational | No; contains `USER`, `PASSWORD`, and empty fields only. |
| `docker-compose.yml` | Local development JWT value | Current and historical | Informational | No; explicitly local-only and not a production credential. |
| `backend/tests/*` | Test-only tokens/password strings | Current and historical | Informational | No; fixtures only. |
| `frontend/package-lock.json` | Package integrity hashes | Current and historical | Informational | No; not credentials. |

No actual MongoDB URI with credentials, API key, JWT production secret, Resend token, wallet private key, seed phrase, or other personal credential was found in the scanned current tree or reachable Git history.

## Dependency audit

| Ecosystem | Result |
| --- | --- |
| npm production | `npm audit --omit=dev --json`: 0 findings. |
| npm full tree | `npm audit --json`: 0 findings. |
| Python | `pip-audit -r backend/requirements.txt`: one medium development-test finding, `PYSEC-2026-1845` / `CVE-2025-71176`, affecting pytest through 9.0.2 on UNIX. The declared `<9.0` cap blocks the fixed 9.0.3. Claude should test and raise that cap. |
| Docker and Actions | Python slim image reviewed; no GitHub Actions directory exists. A container CVE scanner was unavailable locally. |

## Verdict

`PUBLIC_REPO_SAFE = YES`

This verdict is strictly about exposed repository content. It does not override the functional/security release blockers in `RELEASE_VERDICT.md`. Before every public release, re-run a dedicated secret scanner in CI and rotate any credential that is ever accidentally committed.
