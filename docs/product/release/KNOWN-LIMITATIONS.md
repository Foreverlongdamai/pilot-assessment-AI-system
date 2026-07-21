# Known limitations — v0.1.0-rc.1

- User acceptance is `pending`; this candidate must not be represented as the accepted final
  `v0.1.0` release.
- The release candidate requires an explicitly selected, saved and closed current system. Its
  exact model identity/counts, source commit and annotated `v0.1.0-rc.1` tag are recorded.
- Automated verification uses a repository-external disposable directory and restricted `PATH`.
  It is not evidence that Windows Sandbox or a separately provisioned physical clean machine ran.
- Code signing, installer/MSIX, automatic update and application-store delivery are not included.
- The package is a portable directory/ZIP. A dedicated backup/restore archive and UI are
  intentionally out of scope; only whole-directory copy while closed is supported.
- The starter Evidence algorithms, thresholds, BN topology and CPTs have not been scientifically
  calibrated by domain experts and do not authorize formal operational assessment.
- Production exporters/adapters for future real I/G/EEG/ECG/camera device formats may require new
  trusted profiles or source changes when those exact formats are available.
