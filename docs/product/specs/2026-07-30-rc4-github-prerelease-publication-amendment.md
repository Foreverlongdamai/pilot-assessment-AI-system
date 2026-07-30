# RC.4 GitHub Prerelease Publication Amendment

| Field | Value |
|---|---|
| Status | Approved by product owner on 2026-07-30 |
| Repository | `Foreverlongdamai/pilot-assessment-AI-system` |
| Repository visibility at execution | `public` |
| Tag | annotated `v0.1.0-rc.4`, peeling to `e14232f448a9ef9609860b894ea26fba43d59ba8` |
| Candidate status | `engineering candidate / user_acceptance=pending` |
| Scientific status | `engineering-only`; starter `formal_run_authorized=false` |

## 1. Reason for amendment

The approved public-narrative design initially reserved GitHub Releases for a future accepted product and explicitly kept uploading out of scope. After opening that link, the product owner requested that the existing downloadable product be added now.

This amendment supersedes only the no-upload sentence in section 7 of `2026-07-30-github-readme-public-narrative-design.md`. It does not change the research narrative, product architecture, candidate bytes, tag, user-acceptance state, or scientific status.

## 2. Publication decision

Publish the already-built and already-tagged RC.4 package as a GitHub **prerelease**, not as the accepted final `v0.1.0` release. The release title and notes must visibly retain the candidate boundary.

The release shall be created as a draft, populated with all required assets, verified through the GitHub API, and only then made non-draft with `prerelease=true`.

Required assets:

| Asset | Required identity |
|---|---|
| `PilotAssessment-0.1.0-rc.4-win-x64.zip` | 291,239,082 bytes; SHA-256 `a5fe85b6ce24dab76acff1d6b840a9fa2b5498e7f511ebb56d228db1c422f7f4` |
| `PilotAssessment-0.1.0-rc.4-win-x64.zip.sha256` | adjacent human-readable checksum |
| `PilotAssessment-0.1.0-rc.4-win-x64.delivery.json` | build, source, documentation, model and scientific provenance |

The GitHub release body shall provide:

- a direct Windows ZIP download description;
- four-step launch instructions: download, optional checksum verification, extract all files, run root `PilotAssessment.exe`;
- confirmation that system Python, Visual Studio and a separately started SQLite service are not required;
- the RC.4 corrections and preserved product capabilities;
- explicit `user_acceptance=pending` and scientific-calibration limitations;
- links to the repository README and RC.4 verification record.

## 3. Safety and privacy boundary

The exact archive is reused without rebuilding. Fresh publication checks must confirm its SHA-256, root structure and absence of sensitive-looking filenames. The existing release verification remains the authority for the repository-external launch, checksum manifest, DOCX privacy scan and exclusion of user Project, Session, result and biometric data.

No repository visibility change is part of this action because the repository is already public. No user data, new binary, replacement tag, accepted-version label or scientific claim may be introduced.

## 4. README and audit update

After the published release and its three assets are verified, the root README shall show:

- the current downloadable RC.4 prerelease;
- a direct ZIP link;
- a direct checksum link;
- the release-page link;
- the distinction between a downloadable engineering candidate and a future accepted stable release.

Save the GitHub release URL, release ID, asset names/sizes/digests, exact local hash and verification time in a product review record.

## 5. Acceptance criteria

- the public release URL returns the RC.4 release rather than an empty releases page;
- GitHub reports `draft=false` and `prerelease=true`;
- all three named assets exist at their exact expected sizes;
- the ZIP digest reported by GitHub matches the local SHA-256 when the API provides a digest;
- the README direct links target the verified release assets;
- RC.4 remains `user_acceptance=pending` and is not marked as the accepted final product.
