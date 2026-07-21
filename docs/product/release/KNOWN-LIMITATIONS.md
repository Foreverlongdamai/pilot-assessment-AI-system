# Known limitations — M8D engineering build

- M7 user acceptance remains open; UI details may still change before M8E.
- A formal build requires an explicitly selected, saved and closed current system. A clean build
  records its exact model identity/counts and Git state; it is still not the M8E release candidate.
- Clean-machine verification without any preinstalled developer runtime remains an M8E gate.
- Code signing, installer/MSIX, automatic update and application-store delivery are not included.
- M8C-0 provides the pinned Markdown-to-DOCX pipeline and representative review manuals. The
  complete bilingual 12-manual set, final UI screenshots and master technical reference remain
  M8C-1/M8E deliverables.
- M8D current-system capture, manifest-driven model verification, compatibility Diagnostics and
  documented close/copy/reopen project portability are engineering-verified. Dedicated
  backup/restore archives and UI remain intentionally out of scope.
- The starter Evidence algorithms, thresholds, BN topology and CPTs have not been scientifically
  calibrated by domain experts and do not authorize formal operational assessment.
- Production exporters/adapters for future real I/G/EEG/ECG/camera device formats may require new
  trusted profiles or source changes when those exact formats are available.
