# Known limitations — v0.1.0-rc.3

- User acceptance is `pending`; RC.3 must not be represented as the accepted final `v0.1.0`.
- RC.1 and RC.2 remain immutable `changes-required` candidates; RC.3 is a new tag and package.
- Automated verification uses a repository-external disposable directory and restricted `PATH`;
  it is not evidence that Windows Sandbox or a separately provisioned physical clean machine ran.
- Code signing, installer/MSIX, automatic update and application-store delivery are not included.
- The package is a portable directory/ZIP. Whole-directory copy while the app is closed is the
  supported way to duplicate an edited software copy.
- Global node deletion is a staged archival operation. It removes the node and affected active
  downstream closure from the current model but intentionally preserves historical RunSnapshots.
- The starter Evidence algorithms, thresholds, BN topology and CPTs have not been scientifically
  calibrated. A completed Assessment-purpose run with `formal_run_authorized=false` is an
  engineering result, not authorization for operational assessment.
- Production adapters for future real I/G/EEG/ECG/camera formats may require new trusted profiles
  or source changes when those exact formats are available.
