# Third-party notices — M8B-0 inventory

This product includes self-contained .NET and Windows App SDK components, the CPython embedded
distribution, and Python wheels resolved from the frozen `uv.lock` production closure.

- .NET: <https://github.com/dotnet/runtime>
- Windows App SDK: <https://github.com/microsoft/WindowsAppSDK>
- CPython: <https://www.python.org/psf/license/>
- Python package identities and versions: `manifest/release-manifest.json`
- Machine-readable component inventory: `manifest/sbom.spdx.json`

The builder copies CPython's `LICENSE.txt` and license/notice files that Python wheels include in
their `.dist-info` metadata into this directory. SPDX entries currently use `NOASSERTION` for
declared/concluded license fields until the final M8E legal inventory is reviewed. This M8B-0 file is
an engineering inventory and must not be represented as final legal approval.
