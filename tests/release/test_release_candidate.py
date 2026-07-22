from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path

import pytest

RELEASE_TOOLS = Path(__file__).resolve().parents[2] / "tools" / "release"
sys.path.insert(0, str(RELEASE_TOOLS))


def _valid_identity_arguments() -> dict[str, object]:
    return {
        "product_version": "0.1.0",
        "release_label": "v0.1.0-rc.4",
        "release_channel": "release-candidate",
        "candidate": "rc.4",
        "user_acceptance": "pending",
        "documentation_status": "released",
        "skip_archive": False,
    }


def test_release_candidate_identity_is_explicit_and_names_the_rc_directory() -> None:
    from build_portable import _internal_verification_root, _release_identity

    identity = _release_identity(**_valid_identity_arguments())

    assert identity.package_name == "PilotAssessment-0.1.0-rc.4-win-x64"
    assert identity.release_label == "v0.1.0-rc.4"
    assert identity.user_acceptance == "pending"
    assert (
        _internal_verification_root(
            work_root=Path("disposable-verification"),
            identity=identity,
        ).name
        == identity.package_name
    )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("product_version", "0.1.1", "base product version"),
        ("release_label", "v0.1.0", "release label"),
        ("candidate", "candidate-2", "candidate must match"),
        ("documentation_status", "review", "24 released"),
        ("skip_archive", True, "cannot be built with --skip-archive"),
    ],
)
def test_release_candidate_rejects_ambiguous_or_incomplete_identity(
    field: str,
    value: object,
    message: str,
) -> None:
    from build_portable import ReleaseBuildError, _release_identity

    arguments = _valid_identity_arguments()
    arguments[field] = value

    with pytest.raises(ReleaseBuildError, match=message):
        _release_identity(**arguments)


def test_release_candidate_requires_clean_annotated_tag_at_head() -> None:
    from build_portable import ReleaseBuildError, _validate_candidate_git_state

    commit = "a" * 40
    valid = {
        "release_label": "v0.1.0-rc.4",
        "commit": commit,
        "status": "",
        "tag_type": "tag",
        "peeled_commit": commit,
    }
    assert _validate_candidate_git_state(**valid)["tag_type"] == "annotated"

    with pytest.raises(ReleaseBuildError, match="worktree must be clean"):
        _validate_candidate_git_state(**{**valid, "status": " M tracked.py"})
    with pytest.raises(ReleaseBuildError, match="annotated Git tag"):
        _validate_candidate_git_state(**{**valid, "tag_type": "commit"})
    with pytest.raises(ReleaseBuildError, match="does not peel"):
        _validate_candidate_git_state(**{**valid, "peeled_commit": "b" * 40})


def test_outer_delivery_manifest_contains_only_relative_delivery_facts(tmp_path: Path) -> None:
    from build_portable import _sha256, _write_delivery_manifest, _write_json

    package_root = tmp_path / "PilotAssessment-0.1.0-rc.4-win-x64"
    manifest_root = package_root / "manifest"
    manifest_root.mkdir(parents=True)
    _write_json(
        manifest_root / "release-manifest.json",
        {
            "product": "Pilot Assessment System",
            "product_version": "0.1.0",
            "release_channel": "release-candidate",
            "release_label": "v0.1.0-rc.4",
            "candidate": "rc.4",
            "user_acceptance": "pending",
            "build_kind": "m8e-release-candidate",
            "git": {"commit": "a" * 40, "dirty": False},
            "system_model": {"node_count": 54, "scheme_count": 2},
            "documentation": {"generated_output_count": 24},
            "scientific_status": {"formal_run_authorized": False},
        },
    )
    _write_json(manifest_root / "sbom.spdx.json", {"spdxVersion": "SPDX-2.3"})
    archive = tmp_path / f"{package_root.name}.zip"
    archive.write_bytes(b"candidate")
    delivery_path = archive.with_suffix(".delivery.json")

    payload = _write_delivery_manifest(
        delivery_path,
        package_root=package_root,
        archive_path=archive,
        archive_sha256=_sha256(archive),
    )

    serialized = delivery_path.read_text(encoding="utf-8")
    assert payload["archive"]["file"] == archive.name
    assert str(tmp_path) not in serialized
    assert json.loads(serialized)["user_acceptance"] == "pending"


def test_packaged_candidate_identity_requires_pending_handoff_files(tmp_path: Path) -> None:
    from verify_portable import _verify_release_identity

    root = tmp_path / "PilotAssessment-0.1.0-rc.4-win-x64"
    (root / "manifest").mkdir(parents=True)
    (root / "manifest" / "release-manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "pilot-assessment-release-manifest-v3",
                "product_version": "0.1.0",
                "release_channel": "release-candidate",
                "release_label": "v0.1.0-rc.4",
                "candidate": "rc.4",
                "user_acceptance": "pending",
                "documentation_status": "released",
                "build_kind": "m8e-release-candidate",
                "entrypoint": "PilotAssessment.exe",
                "portable_layout": {
                    "schema_version": "pilot-assessment-portable-layout-v2",
                    "launcher": "PilotAssessment.exe",
                    "desktop_payload_root": "app",
                    "desktop_executable": "app/PilotAssessment.Desktop.exe",
                    "semantic_root_directories": [
                        "app",
                        "backend",
                        "developer",
                        "docs",
                        "licenses",
                        "manifest",
                        "runtime",
                        "system",
                    ],
                },
                "git": {
                    "commit": "a" * 40,
                    "dirty": False,
                    "tag": "v0.1.0-rc.4",
                    "tag_type": "annotated",
                    "tag_peels_to_head": True,
                },
                "scientific_status": {"formal_run_authorized": False},
            }
        ),
        encoding="utf-8",
    )
    handoff_root = root / "docs"
    handoff_root.mkdir()
    for filename in (
        "README-CANDIDATE.md",
        "RELEASE-NOTES.md",
        "ACCEPTANCE-CHECKLIST.md",
        "KNOWN-LIMITATIONS.md",
    ):
        (handoff_root / filename).write_text(
            "v0.1.0-rc.4 user acceptance pending",
            encoding="utf-8",
        )

    verified = _verify_release_identity(root)

    assert verified["user_acceptance"] == "pending"
    assert verified["formal_run_authorized"] is False


def test_portable_root_surface_exposes_only_semantic_directories_and_one_launcher(
    tmp_path: Path,
) -> None:
    from verify_portable import PortableVerificationError, _verify_root_surface

    root = tmp_path / "PilotAssessment-0.1.0-rc.4-win-x64"
    for directory in (
        "app",
        "backend",
        "developer",
        "docs",
        "licenses",
        "manifest",
        "runtime",
        "system",
    ):
        (root / directory).mkdir(parents=True, exist_ok=True)
    (root / "PilotAssessment.exe").write_bytes(b"launcher")
    (root / "README.txt").write_text("Start with PilotAssessment.exe", encoding="utf-8")

    assert _verify_root_surface(root) == {
        "root_directories": 8,
        "root_files": 2,
        "launchers": ["PilotAssessment.exe"],
        "desktop_payload_root": "app",
    }

    (root / "Microsoft.WindowsAppRuntime.dll").write_bytes(b"leaked payload")
    with pytest.raises(PortableVerificationError, match="unexpected root entries"):
        _verify_root_surface(root)


def _docx_payload(xml: bytes = b"<document />") -> bytes:
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w") as document:
        document.writestr("word/document.xml", xml)
    return target.getvalue()


def test_external_archive_scan_requires_24_private_path_free_docx(tmp_path: Path) -> None:
    from verify_archive_external import ExternalArchiveVerificationError, _scan_archive_content

    archive = tmp_path / "candidate.zip"
    with zipfile.ZipFile(archive, "w") as package:
        for index in range(24):
            package.writestr(
                f"PilotAssessment-0.1.0-rc.4-win-x64/docs/en-GB/manual-{index:02d}.docx",
                _docx_payload(),
            )
    assert _scan_archive_content(archive)["docx_files"] == 24

    bad_archive = tmp_path / "candidate-private.zip"
    with zipfile.ZipFile(bad_archive, "w") as package:
        for index in range(24):
            xml = (
                b"<document>C:\\Users\\Alice\\secret</document>" if index == 3 else b"<document />"
            )
            package.writestr(
                f"PilotAssessment-0.1.0-rc.4-win-x64/docs/en-GB/manual-{index:02d}.docx",
                _docx_payload(xml),
            )
    with pytest.raises(ExternalArchiveVerificationError, match="private user-home path"):
        _scan_archive_content(bad_archive)
