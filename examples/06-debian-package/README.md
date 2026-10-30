# 06: Build A Private Debian Package

Goal: turn a native program and its declared resource into a Debian package with
a private `/opt/eros/<package>` layout, then inspect and extract it without
`sudo`. This lesson is self-contained and does not consume lesson 05 outputs.

## Files And Targets

| File/target | Role |
| --- | --- |
| `main.cc` | Computes `20 * 2 + 1` and reads the packaged resource |
| `resource.txt` | Resource copied below the package's `share/` directory |
| `//06-debian-package:app` | Native program used as the package source |
| `//06-debian-package:deb` | Deb with explicit version `1.2.3` |
| `//06-debian-package:deb_default_version` | Deb using environment/define/default version precedence |

`eros_install_map` assigns `resource.txt` to `share/debian-package.txt`.
`pkg_eros_deb(srcs = [":app"])` creates the checked runtime tar internally and
wraps it as a deb. The rule derives the Debian architecture from the native
platform; it does not silently use `all` for an ELF payload. The private package
name is `forge-example-debian-package` (the default target uses
`forge-example-debian-package-default`).

## Build And Inspect

Working directory for every command below: `forge/examples`, which contains the
shared `MODULE.bazel`.

```bash
../forge-bazel build --config=debug //06-debian-package:deb
../forge-bazel build --config=release //06-debian-package:deb
```

The output for either mode is `bazel-bin/06-debian-package/deb.deb`. Inspect it
without installing anything:

```bash
dpkg-deb --field bazel-bin/06-debian-package/deb.deb
dpkg-deb --contents bazel-bin/06-debian-package/deb.deb
```

The `Package` field must be `forge-example-debian-package`, `Version` must be
`1.2.3`, and `Architecture` must match the native ELF (`amd64` on x86_64,
`arm64` on ARM64). The payload must contain the program and the declared
resource under `/opt/eros/forge-example-debian-package`. After extraction,
`readelf -h` on the installed program confirms the ELF machine.

## Version Precedence

The version inputs have this order:

1. `version` on the packaging rule.
2. `DEB_VERSION` in the action environment.
3. `--define=DEB_VERSION=...`.
4. `0.1.0`.

Build the default-version target with environment and define values:

```bash
DEB_VERSION=2.3.4 ../forge-bazel build --config=release \
  --define=DEB_VERSION=3.4.5 //06-debian-package:deb_default_version
dpkg-deb --field bazel-bin/06-debian-package/deb_default_version.deb Version
```

The field must be `2.3.4`. Removing `DEB_VERSION` and using only the define
produces `3.4.5`; providing neither produces `0.1.0`. The explicit `deb` target
stays `1.2.3` even when the environment or define supplies another value.

## Extract And Run

```bash
root=$(mktemp -d /tmp/kilo/forge-debian-package.XXXXXX)
dpkg-deb --extract bazel-bin/06-debian-package/deb.deb "$root"
env -u LD_LIBRARY_PATH -u LD_PRELOAD \
  "$root/opt/eros/forge-example-debian-package/bin/app"
```

The command must print
`result=41 marker=FORGE_DEBIAN_PACKAGE_MARKER layout=private` and exit zero.
This proves that the private payload works after native extraction; it does not
prove clean target installation, target ABI compatibility or a deployment
lifecycle.

## Verify

```bash
../forge-shell
# Inside the shell, still in forge/examples:
python3 06-debian-package/check.py
```

The checker builds both modes, validates control metadata against the ELF and
payload, checks the version precedence matrix, extracts each deb and runs the
installed program with library path overrides removed. Inside `../forge-shell`,
replace `../forge-bazel` with `bazel`. Reuse this workspace/output base.
