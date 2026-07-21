# Known limitations — M8B-0 engineering build

- M7 user acceptance remains open; UI details may still change before M8E.
- This build is generated from the current working tree and may record `git.dirty=true`.
- Clean-machine verification without any preinstalled developer runtime remains an M8E gate.
- Code signing, installer/MSIX, automatic update and application-store delivery are not included.
- M8C-0 provides the pinned Markdown-to-DOCX pipeline and representative review manuals. The
  complete bilingual 12-manual set, final UI screenshots and master technical reference remain
  M8C-1/M8E deliverables.
- Project backup/restore/migration UI and redacted diagnostic bundles are M8D deliverables.
- The starter Evidence algorithms, thresholds, BN topology and CPTs have not been scientifically
  calibrated by domain experts and do not authorize formal operational assessment.
- Production exporters/adapters for future real I/G/EEG/ECG/camera device formats may require new
  trusted profiles or source changes when those exact formats are available.
