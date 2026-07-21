# Third-party notices — v0.1.0 release-candidate engineering inventory

This product includes self-contained .NET and Windows App SDK components, the CPython embedded
distribution, the bundled uv dependency tool, and Python wheels resolved from the frozen `uv.lock`
production closure.

- .NET: <https://github.com/dotnet/runtime>
- Windows App SDK: <https://github.com/microsoft/WindowsAppSDK>
- CPython: <https://www.python.org/psf/license/>
- uv: <https://github.com/astral-sh/uv> (upstream dual MIT/Apache-2.0 licensing)
- Python package identities and versions: `manifest/release-manifest.json`
- Machine-readable component inventory: `manifest/sbom.spdx.json`

The builder copies CPython's `LICENSE.txt` and license/notice files that Python wheels include in
their `.dist-info` metadata into this directory. SPDX entries currently use `NOASSERTION` for
declared/concluded license fields until a legal inventory is reviewed. This release-candidate file
is an engineering inventory, leaves `user_acceptance=pending`, and must not be represented as final
legal approval.
