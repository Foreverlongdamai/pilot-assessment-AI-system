# Known limitations — v0.1.0-rc.2

- User acceptance is `pending`; RC.2 must not be represented as the accepted final `v0.1.0`.
- RC.1 remains an immutable `changes-required` candidate. RC.2 corrects the portable root layout
  in a new tag and package rather than rewriting RC.1.
- Automated verification uses a repository-external disposable directory and restricted `PATH`;
  it is not evidence that Windows Sandbox or a separately provisioned physical clean machine ran.
- Code signing, installer/MSIX, automatic update and application-store delivery are not included.
- The package is a portable directory/ZIP. Whole-directory copy while the app is closed is the
  supported way to duplicate an edited software copy.
- The starter Evidence algorithms, thresholds, BN topology and CPTs have not been scientifically
  calibrated by domain experts and do not authorise formal operational assessment.
- Production adapters for future real I/G/EEG/ECG/camera formats may require new trusted profiles
  or source changes when those exact formats are available.

