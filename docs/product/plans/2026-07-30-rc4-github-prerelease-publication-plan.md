# RC.4 GitHub Prerelease Publication Plan

**Goal:** Make the existing verified RC.4 Windows package visible and downloadable from the repository's public GitHub Releases page without changing its bytes or acceptance status.

**Execution mode:** INLINE; lightweight release verification only, following the product owner's earlier instruction not to repeat the full release test matrix.

## Task 1: Verify the exact local candidate

- [x] Confirm the worktree starts clean and `v0.1.0-rc.4` exists remotely.
- [x] Recompute the ZIP SHA-256 and compare it with the adjacent checksum and delivery JSON.
- [x] Inspect the ZIP central directory for the expected single product root and sensitive-looking filenames.
- [x] Confirm the GitHub repository is public, writable, and has no existing release for the tag.

## Task 2: Publish atomically

- [x] Create `v0.1.0-rc.4` as a draft GitHub release with `prerelease=true` and candidate/scientific boundaries in the body.
- [x] Upload the ZIP, `.zip.sha256`, and delivery JSON.
- [x] Query the draft through the GitHub API and verify asset names, sizes and available SHA-256 digests.
- [x] Publish only after all checks pass; otherwise retain or remove the draft rather than exposing an incomplete release.

## Task 3: Make the download discoverable

- [x] Add direct RC.4 ZIP/checksum/release links to the root README while retaining the future stable-release explanation.
- [x] Add this amendment and plan to the product documentation index.
- [x] Save a GitHub publication verification record with exact release and asset evidence.
- [x] Run Markdown link, required wording, `git diff --check`, and Markdown-only scope checks.
- [x] Commit and push the documentation update to `main`.
- [x] Re-query the public GitHub release after the push and confirm `HEAD == origin/main`.
