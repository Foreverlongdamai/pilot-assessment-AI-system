from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest
from PIL import Image
from PIL.PngImagePlugin import PngInfo

from pilot_assessment.ingestion.adapters.base import AdapterInspectionError
from pilot_assessment.ingestion.adapters.image_sequence import inspect_image_sequence
from pilot_assessment.ingestion.profiles import ImageProfile, load_builtin_profiles


def _profile() -> ImageProfile:
    profile = load_builtin_profiles()["png-rgb8-v0.1"]
    assert isinstance(profile, ImageProfile)
    return profile


def _index(path: str, *, width: int, height: int) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "frame_id": pl.Series([0], dtype=pl.UInt64),
            "image_path": pl.Series([path], dtype=pl.String),
            "width": pl.Series([width], dtype=pl.UInt32),
            "height": pl.Series([height], dtype=pl.UInt32),
        }
    )


def _write_png(
    root: Path,
    relative_path: str,
    *,
    size: tuple[int, int],
    mode: str = "RGB",
    pnginfo: PngInfo | None = None,
) -> None:
    path = root.joinpath(*relative_path.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    color: int | tuple[int, int, int]
    color = 0 if mode == "L" else (12, 34, 56)
    Image.new(mode, size, color=color).save(
        path,
        format="PNG",
        compress_level=9,
        optimize=False,
        pnginfo=pnginfo,
    )


@pytest.mark.parametrize(
    ("relative_path", "size"),
    [
        ("streams/vr_scene/frames/frame_000000.png", (64, 36)),
        ("streams/pilot_camera/frames/frame_000000.png", (48, 48)),
    ],
)
def test_rgb8_png_with_exact_synthetic_size_is_accepted(
    tmp_path: Path,
    relative_path: str,
    size: tuple[int, int],
) -> None:
    _write_png(tmp_path, relative_path, size=size)

    inspected = inspect_image_sequence(
        bundle_root=tmp_path,
        frame_index=_index(relative_path, width=size[0], height=size[1]),
        declared_paths=(relative_path,),
        profile=_profile(),
    )

    assert inspected == (relative_path,)


@pytest.mark.parametrize(
    ("mode", "width", "height"),
    [
        ("L", 64, 36),
        ("RGB", 65, 36),
        ("RGB", 100, 100),
    ],
)
def test_mode_index_dimensions_and_synthetic_dimensions_are_exact(
    tmp_path: Path,
    mode: str,
    width: int,
    height: int,
) -> None:
    relative_path = "streams/vr_scene/frames/frame_000000.png"
    actual_size = (64, 36) if width == 65 else (width, height)
    _write_png(tmp_path, relative_path, size=actual_size, mode=mode)

    with pytest.raises(AdapterInspectionError) as caught:
        inspect_image_sequence(
            bundle_root=tmp_path,
            frame_index=_index(relative_path, width=width, height=height),
            declared_paths=(relative_path,),
            profile=_profile(),
        )

    assert caught.value.issue.error_code == "STREAM_SCHEMA_MISMATCH"


def test_missing_and_unindexed_or_undeclared_images_are_rejected(tmp_path: Path) -> None:
    referenced = "streams/vr_scene/frames/frame_000000.png"
    with pytest.raises(AdapterInspectionError) as missing:
        inspect_image_sequence(
            bundle_root=tmp_path,
            frame_index=_index(referenced, width=64, height=36),
            declared_paths=(referenced,),
            profile=_profile(),
        )
    assert missing.value.issue.error_code == "SOURCE_CHANGED_DURING_READINESS"

    extra = "streams/vr_scene/frames/frame_000001.png"
    _write_png(tmp_path, referenced, size=(64, 36))
    _write_png(tmp_path, extra, size=(64, 36))
    with pytest.raises(AdapterInspectionError) as unindexed:
        inspect_image_sequence(
            bundle_root=tmp_path,
            frame_index=_index(referenced, width=64, height=36),
            declared_paths=(referenced, extra),
            profile=_profile(),
        )
    assert unindexed.value.issue.error_code == "STREAM_SCHEMA_MISMATCH"

    with pytest.raises(AdapterInspectionError) as undeclared:
        inspect_image_sequence(
            bundle_root=tmp_path,
            frame_index=_index(referenced, width=64, height=36),
            declared_paths=(extra,),
            profile=_profile(),
        )
    assert undeclared.value.issue.error_code == "STREAM_SCHEMA_MISMATCH"


def test_index_paths_must_be_unique_canonical_bundle_paths(tmp_path: Path) -> None:
    traversal = "streams/vr_scene/frames/../outside.png"
    with pytest.raises(AdapterInspectionError) as escaped:
        inspect_image_sequence(
            bundle_root=tmp_path,
            frame_index=_index(traversal, width=64, height=36),
            declared_paths=(traversal,),
            profile=_profile(),
        )
    assert escaped.value.issue.error_code == "STREAM_SCHEMA_MISMATCH"

    path = "streams/vr_scene/frames/frame_000000.png"
    _write_png(tmp_path, path, size=(64, 36))
    duplicate_index = pl.concat(
        [_index(path, width=64, height=36), _index(path, width=64, height=36)]
    )
    with pytest.raises(AdapterInspectionError) as duplicate:
        inspect_image_sequence(
            bundle_root=tmp_path,
            frame_index=duplicate_index,
            declared_paths=(path,),
            profile=_profile(),
        )
    assert duplicate.value.issue.error_code == "STREAM_SCHEMA_MISMATCH"


def test_animation_and_png_ancillary_payload_are_rejected(tmp_path: Path) -> None:
    animated_path = "streams/vr_scene/frames/animated.png"
    animated = tmp_path.joinpath(*animated_path.split("/"))
    animated.parent.mkdir(parents=True)
    first = Image.new("RGB", (64, 36), color=(1, 2, 3))
    second = Image.new("RGB", (64, 36), color=(4, 5, 6))
    first.save(
        animated,
        format="PNG",
        save_all=True,
        append_images=[second],
        duration=100,
        loop=0,
    )
    with pytest.raises(AdapterInspectionError) as animation:
        inspect_image_sequence(
            bundle_root=tmp_path,
            frame_index=_index(animated_path, width=64, height=36),
            declared_paths=(animated_path,),
            profile=_profile(),
        )
    assert animation.value.issue.error_code == "STREAM_FORMAT_INVALID"

    metadata_path = "streams/vr_scene/frames/metadata.png"
    metadata = PngInfo()
    metadata.add_text("generator", "not allowed")
    _write_png(tmp_path, metadata_path, size=(64, 36), pnginfo=metadata)
    with pytest.raises(AdapterInspectionError) as ancillary:
        inspect_image_sequence(
            bundle_root=tmp_path,
            frame_index=_index(metadata_path, width=64, height=36),
            declared_paths=(metadata_path,),
            profile=_profile(),
        )
    assert ancillary.value.issue.error_code == "STREAM_FORMAT_INVALID"


def test_generic_safety_ceiling_is_16_megapixels(tmp_path: Path) -> None:
    relative_path = "streams/vr_scene/frames/oversize.png"
    size = (4_001, 4_000)
    _write_png(tmp_path, relative_path, size=size)
    permissive_profile = ImageProfile(
        kind="image",
        schema_id="large-png-rgb8-v0.1",
        media_type="image/png",
        mode="RGB",
        bit_depth=8,
        allowed_dimensions=({"width": size[0], "height": size[1]},),
        max_pixels=20_000_000,
        allow_animation=False,
        allow_ancillary_metadata=False,
    )

    with pytest.raises(AdapterInspectionError) as caught:
        inspect_image_sequence(
            bundle_root=tmp_path,
            frame_index=_index(relative_path, width=size[0], height=size[1]),
            declared_paths=(relative_path,),
            profile=permissive_profile,
        )

    assert caught.value.issue.error_code == "STREAM_SCHEMA_MISMATCH"
