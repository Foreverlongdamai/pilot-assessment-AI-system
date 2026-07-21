"""Derive all Windows desktop icon assets from the checked-in RGBA master."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "src" / "PilotAssessment.Desktop" / "Assets"
MASTER = ASSETS / "Brand" / "PilotAssessmentIcon-1024.png"

SQUARE_ASSETS = {
    "LockScreenLogo.scale-200.png": (48, 48),
    "Square150x150Logo.scale-200.png": (300, 300),
    "Square44x44Logo.scale-200.png": (88, 88),
    "Square44x44Logo.targetsize-24_altform-unplated.png": (24, 24),
    "Square44x44Logo.targetsize-48_altform-lightunplated.png": (48, 48),
    "StoreLogo.png": (50, 50),
}

WIDE_ASSETS = {
    "SplashScreen.scale-200.png": ((1240, 600), 420),
    "Wide310x150Logo.scale-200.png": ((620, 300), 210),
}


def resized(source: Image.Image, size: tuple[int, int]) -> Image.Image:
    return source.resize(size, Image.Resampling.LANCZOS)


def centered(source: Image.Image, canvas_size: tuple[int, int], icon_size: int) -> Image.Image:
    canvas = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    icon = resized(source, (icon_size, icon_size))
    origin = ((canvas.width - icon.width) // 2, (canvas.height - icon.height) // 2)
    canvas.alpha_composite(icon, origin)
    return canvas


def main() -> None:
    source = Image.open(MASTER).convert("RGBA")
    if source.size != (1024, 1024):
        raise ValueError(f"Icon master must be 1024x1024, got {source.size!r}")

    for name, size in SQUARE_ASSETS.items():
        resized(source, size).save(ASSETS / name, optimize=True)

    for name, (canvas_size, icon_size) in WIDE_ASSETS.items():
        centered(source, canvas_size, icon_size).save(ASSETS / name, optimize=True)

    source.save(
        ASSETS / "AppIcon.ico",
        format="ICO",
        sizes=[
            (16, 16),
            (20, 20),
            (24, 24),
            (32, 32),
            (40, 40),
            (48, 48),
            (64, 64),
            (96, 96),
            (128, 128),
            (256, 256),
        ],
    )


if __name__ == "__main__":
    main()
