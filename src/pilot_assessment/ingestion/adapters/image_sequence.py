"""Bounded, metadata-only inspection of bundle-local PNG frame sequences."""

from __future__ import annotations

import struct
import warnings
from pathlib import Path
from typing import NoReturn, cast

import polars as pl
from PIL import Image, UnidentifiedImageError
from pydantic import JsonValue, TypeAdapter, ValidationError

from pilot_assessment.contracts.common import BundleRelativePath
from pilot_assessment.contracts.errors import DomainErrorData, ErrorSeverity
from pilot_assessment.ingestion.adapters.base import AdapterInspectionError
from pilot_assessment.ingestion.profiles import ImageProfile

MAX_IMAGE_PIXELS = 16_000_000
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_BUNDLE_PATH_ADAPTER = TypeAdapter(BundleRelativePath)
_INDEX_COLUMNS = frozenset({"image_path", "width", "height"})


def inspect_image_sequence(
    *,
    bundle_root: str | Path,
    frame_index: pl.DataFrame,
    declared_paths: tuple[str, ...],
    profile: ImageProfile,
) -> tuple[str, ...]:
    """Validate one frame index against an exact, bounded set of RGB8 PNG files.

    Pixels are never retained. Pillow verifies each image, the file is reopened only
    for bounded header properties, and the function returns canonical path references.
    """

    if not isinstance(profile, ImageProfile):
        _fail(
            "ADAPTER_CONFIG_INVALID",
            "Image sequence inspection requires an ImageProfile",
            remediation="Register the PNG role with its packaged image profile.",
        )
    missing_columns = sorted(_INDEX_COLUMNS - set(frame_index.columns))
    if missing_columns or frame_index.is_empty():
        _fail(
            "STREAM_SCHEMA_MISMATCH",
            "Frame index is empty or lacks image path and dimension columns",
            remediation="Export a non-empty frame index with image_path, width, and height.",
            diagnostics={"missing_columns": missing_columns},
        )

    indexed_paths = cast(list[str], frame_index["image_path"].to_list())
    if any(type(path) is not str for path in indexed_paths):
        _fail(
            "STREAM_SCHEMA_MISMATCH",
            "Frame index image paths must be non-null UTF-8 strings",
            remediation="Export every image_path using the profiled UTF-8 type.",
            field_or_path="image_path",
        )
    _validate_path_inventory(indexed_paths, declared_paths)

    allowed_dimensions = {
        (dimension.width, dimension.height) for dimension in profile.allowed_dimensions
    }
    root = Path(bundle_root).resolve()
    for row in frame_index.select("image_path", "width", "height").iter_rows(named=True):
        relative_path = cast(str, row["image_path"])
        expected_size = (cast(int, row["width"]), cast(int, row["height"]))
        if expected_size not in allowed_dimensions:
            _fail(
                "STREAM_SCHEMA_MISMATCH",
                "Frame index dimensions are not an exact allowed synthetic image size",
                remediation="Use one exact width and height pair declared by the image profile.",
                field_or_path=relative_path,
                diagnostics={
                    "actual_dimensions": list(expected_size),
                    "allowed_dimensions": [list(item) for item in sorted(allowed_dimensions)],
                },
            )
        _validate_pixel_ceiling(expected_size, profile, relative_path)
        source = _safe_bundle_file(root, relative_path)
        _inspect_png(source, relative_path, expected_size, profile)
    return tuple(indexed_paths)


def _validate_path_inventory(indexed_paths: list[str], declared_paths: tuple[str, ...]) -> None:
    for path in (*indexed_paths, *declared_paths):
        try:
            _BUNDLE_PATH_ADAPTER.validate_python(path)
        except ValidationError as error:
            _fail(
                "STREAM_SCHEMA_MISMATCH",
                "Image inventory contains a non-canonical or traversing bundle path",
                remediation="Use canonical POSIX paths that remain below the bundle root.",
                field_or_path=str(path),
                diagnostics={"exception_type": type(error).__name__},
            )

    indexed_folded = [path.casefold() for path in indexed_paths]
    declared_folded = [path.casefold() for path in declared_paths]
    if len(indexed_folded) != len(set(indexed_folded)):
        _fail(
            "STREAM_SCHEMA_MISMATCH",
            "Every frame row must reference one unique image path",
            remediation="Export one distinct PNG path per frame-index row.",
            field_or_path="image_path",
        )
    if len(declared_folded) != len(set(declared_folded)):
        _fail(
            "STREAM_SCHEMA_MISMATCH",
            "Declared image paths collide under Windows case folding",
            remediation="Rename images so every bundle path is case-insensitively unique.",
        )
    if set(indexed_paths) != set(declared_paths):
        _fail(
            "STREAM_SCHEMA_MISMATCH",
            "Frame index and descriptor must declare exactly the same image paths",
            remediation="Add missing frame rows or remove undeclared and unindexed PNG paths.",
            diagnostics={
                "not_declared": sorted(set(indexed_paths) - set(declared_paths)),
                "not_indexed": sorted(set(declared_paths) - set(indexed_paths)),
            },
        )


def _safe_bundle_file(root: Path, relative_path: str) -> Path:
    candidate = root.joinpath(*relative_path.split("/"))
    current = root
    for part in relative_path.split("/"):
        current = current / part
        if current.is_symlink():
            _fail(
                "SOURCE_CHANGED_DURING_READINESS",
                "Image path resolves through a symbolic link",
                remediation="Replace links with regular immutable bundle files.",
                field_or_path=relative_path,
            )
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as error:
        _fail(
            "SOURCE_CHANGED_DURING_READINESS",
            "A frame-index image is missing during readiness inspection",
            remediation="Restore the verified PNG and re-run Session Bundle integrity.",
            field_or_path=relative_path,
            diagnostics={"exception_type": type(error).__name__},
        )
    if not resolved.is_relative_to(root) or not resolved.is_file():
        _fail(
            "SOURCE_CHANGED_DURING_READINESS",
            "A frame-index image no longer resolves to a regular bundle file",
            remediation="Restore a regular file below the bundle root and re-run integrity.",
            field_or_path=relative_path,
        )
    return resolved


def _inspect_png(
    source: Path,
    relative_path: str,
    expected_size: tuple[int, int],
    profile: ImageProfile,
) -> None:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(source) as image:
                if image.format != "PNG":
                    raise ValueError("image format is not PNG")
                image.verify()
            if not profile.allow_ancillary_metadata and _contains_ancillary_png_chunk(source):
                _fail(
                    "STREAM_FORMAT_INVALID",
                    "PNG contains an ancillary metadata or animation chunk",
                    remediation="Export deterministic PNGs without ancillary chunks.",
                    field_or_path=relative_path,
                )
            with Image.open(source) as image:
                actual_size = image.size
                frame_count = int(getattr(image, "n_frames", 1))
                is_animated = bool(getattr(image, "is_animated", False))
                if image.format != "PNG":
                    raise ValueError("image format is not PNG")
                if (frame_count != 1 or is_animated) and not profile.allow_animation:
                    _fail(
                        "STREAM_FORMAT_INVALID",
                        "Animated PNGs are not allowed by the image profile",
                        remediation="Export exactly one still RGB frame per PNG path.",
                        field_or_path=relative_path,
                    )
                if image.mode != profile.mode:
                    _fail(
                        "STREAM_SCHEMA_MISMATCH",
                        "PNG mode is not exact 8-bit RGB",
                        remediation="Export the image in exact RGB8 mode.",
                        field_or_path=relative_path,
                        diagnostics={"expected_mode": profile.mode, "actual_mode": image.mode},
                    )
                if actual_size != expected_size:
                    _fail(
                        "STREAM_SCHEMA_MISMATCH",
                        "PNG dimensions do not match its frame-index row",
                        remediation="Regenerate the index from the immutable PNG dimensions.",
                        field_or_path=relative_path,
                        diagnostics={
                            "expected_dimensions": list(expected_size),
                            "actual_dimensions": list(actual_size),
                        },
                    )
                _validate_pixel_ceiling(actual_size, profile, relative_path)
                if not profile.allow_ancillary_metadata and image.info:
                    _fail(
                        "STREAM_FORMAT_INVALID",
                        "PNG exposes ancillary metadata",
                        remediation="Export PNGs without text, color, timing, or profile metadata.",
                        field_or_path=relative_path,
                        diagnostics={"metadata_keys": sorted(image.info)},
                    )
    except AdapterInspectionError:
        raise
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        OSError,
        SyntaxError,
        UnidentifiedImageError,
        ValueError,
    ) as error:
        _fail(
            "STREAM_FORMAT_INVALID",
            "PNG cannot be safely verified as a bounded still image",
            remediation="Replace the artifact with a valid bounded RGB8 PNG.",
            field_or_path=relative_path,
            diagnostics={"exception_type": type(error).__name__},
        )


def _contains_ancillary_png_chunk(source: Path) -> bool:
    with source.open("rb") as payload:
        if payload.read(len(_PNG_SIGNATURE)) != _PNG_SIGNATURE:
            raise ValueError("invalid PNG signature")
        while True:
            header = payload.read(8)
            if len(header) != 8:
                raise ValueError("truncated PNG chunk header")
            length, chunk_type = struct.unpack(">I4s", header)
            if 97 <= chunk_type[0] <= 122:
                return True
            payload.seek(length + 4, 1)
            if chunk_type == b"IEND":
                return False


def _validate_pixel_ceiling(
    size: tuple[int, int],
    profile: ImageProfile,
    relative_path: str,
) -> None:
    pixels = size[0] * size[1]
    ceiling = min(profile.max_pixels, MAX_IMAGE_PIXELS)
    if pixels > ceiling:
        _fail(
            "STREAM_SCHEMA_MISMATCH",
            "PNG dimensions exceed the bounded image-inspection pixel ceiling",
            remediation="Downscale the image below the declared and 16-megapixel ceilings.",
            field_or_path=relative_path,
            diagnostics={"pixels": pixels, "maximum_pixels": ceiling},
        )


def _fail(
    error_code: str,
    message: str,
    *,
    remediation: str,
    field_or_path: str | None = None,
    diagnostics: dict[str, JsonValue] | None = None,
) -> NoReturn:
    raise AdapterInspectionError(
        DomainErrorData(
            error_code=error_code,
            severity=ErrorSeverity.ERROR,
            recoverable=True,
            message=message,
            field_or_path=field_or_path,
            remediation=remediation,
            diagnostics=diagnostics or {},
        )
    )


__all__ = ["MAX_IMAGE_PIXELS", "inspect_image_sequence"]
