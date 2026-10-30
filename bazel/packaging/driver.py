#!/usr/bin/env python3
"""Declared-input runtime exports and deterministic tar/deb assembly.

The public validation functions deliberately do not discover libraries on the
host. The environment manifest is the only authority for SDK runtime libraries.
"""

import argparse
import dataclasses
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import posixpath
import re
import shutil
import stat
import struct
import subprocess
import sys
import tarfile
import tempfile
import zlib


class PackagingError(ValueError):
    pass


@dataclasses.dataclass(frozen=True)
class Entry:
    path: str
    source: Path | None = None
    link: str | None = None
    mode: int = 0o644
    directory: bool = False


def relative_path(value, *, allow_empty=False):
    value = str(value)
    if not value and allow_empty:
        return ""
    if not value or value.startswith("/") or "\\" in value:
        raise PackagingError(f"invalid private installation path: {value!r}")
    parts = value.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise PackagingError(f"installation path escapes or is not normalized: {value!r}")
    return value


def _link_destination(path, link):
    if not link or link.startswith("/") or "\\" in link:
        raise PackagingError(f"symlink escape at {path}: {link!r}")
    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(path), link))
    if resolved == ".." or resolved.startswith("../"):
        raise PackagingError(f"symlink escapes private installation root: {path} -> {link}")
    return resolved


def collect_entries(mappings):
    """Expand [{source, destination, dereference?}] with strict collision checks.

    Directory sources map their contents, including relative SONAME symlinks.
    Only implicit Bazel runfile symlinks may request dereferencing. Explicit
    install mappings never get this exception to the escape checks.
    """
    entries = {}

    def add(entry):
        old = entries.get(entry.path)
        if old is not None:
            if old.directory and entry.directory:
                return
            if old == entry:
                return
            if old.source is not None and entry.source is not None:
                if old.source.absolute() == entry.source.absolute() and old.link == entry.link:
                    return
                if old.source.resolve() == entry.source.resolve() and not (old.link is not None and entry.link is not None and old.link != entry.link):
                    if entry.link is not None:
                        entries[entry.path] = entry
                    return
                if old.source.is_file() and entry.source.is_file() and not (old.link is not None and entry.link is not None and old.link != entry.link):
                    same_mode = bool(old.source.stat().st_mode & 0o111) == bool(entry.source.stat().st_mode & 0o111)
                    if same_mode and old.source.stat().st_size == entry.source.stat().st_size and _sha256(old.source) == _sha256(entry.source):
                        if entry.link is not None:
                            entries[entry.path] = entry
                        return
            raise PackagingError(f"installation path collision at {entry.path}: {old.source or old.link} versus {entry.source or entry.link}")
        entries[entry.path] = entry

    def visit(source, destination, dereference=False):
        if not os.path.lexists(source):
            raise PackagingError(f"missing declared runtime input: {source} (install {destination})")
        # Bazel's sandbox presents an artifact through an absolute indirection.
        # Peel only an indirection back to that exact declared execroot path;
        # a payload's own absolute or escaping symlink remains a hard error.
        declared = source.as_posix()
        if not source.is_absolute() and "sandbox" in Path.cwd().parts and source.is_symlink():
            target = os.readlink(source)
            suffixes = [declared]
            if declared.startswith("external/"):
                suffixes.append("/".join(declared.split("/")[2:]))
            if os.path.isabs(target) and any(suffix and target.endswith("/" + suffix) for suffix in suffixes):
                source = Path(target)
        mode = source.lstat().st_mode
        if stat.S_ISLNK(mode) and not dereference:
            link = os.readlink(source)
            _link_destination(destination, link)
            add(Entry(destination, source=source, link=link, mode=0o777))
        elif source.is_dir():
            if destination:
                add(Entry(destination, source=source, mode=0o755, directory=True))
            for child in sorted(source.iterdir()):
                visit(child, posixpath.join(destination, child.name), dereference)
        elif source.is_file():
            add(Entry(destination, source=source.resolve() if dereference else source,
                      mode=0o755 if source.stat().st_mode & 0o111 else 0o644))
        else:
            raise PackagingError(f"unsupported special runtime input: {source}")

    for mapping in mappings:
        source = Path(mapping.get("source", mapping.get("file", "")))
        destination = relative_path(mapping.get("destination", mapping.get("path", "")), allow_empty=source.is_dir())
        visit(source, destination, bool(mapping.get("dereference", False)))

    for path in entries:
        parent = posixpath.dirname(path)
        while parent:
            if parent in entries and not entries[parent].directory:
                raise PackagingError(f"installation path collision: {parent} is not a directory (for {path})")
            parent = posixpath.dirname(parent)
    for path, entry in entries.items():
        if entry.link is not None:
            resolve_entry(entries, path)
    return entries


def resolve_entry(entries, path):
    seen = set()
    while path in entries and entries[path].link is not None:
        if path in seen:
            raise PackagingError(f"symlink cycle in runtime payload: {path}")
        seen.add(path)
        path = _link_destination(path, entries[path].link)
    if path not in entries:
        raise PackagingError(f"missing symlink target in runtime payload: {path}")
    return entries[path]


def inspect_elf(path):
    """Read ELF identities, dynamic strings, notes, and debug section names."""
    with open(path, "rb") as stream:
        signature = stream.read(4)
        if signature != b"\x7fELF":
            return None
        data = signature + stream.read()
    if len(data) < 52 or data[4] not in (1, 2) or data[5] not in (1, 2):
        raise PackagingError(f"malformed ELF header: {path}")
    endian = "<" if data[5] == 1 else ">"
    bits = 64 if data[4] == 2 else 32
    fmt = endian + ("HHIQQQIHHHHHH" if bits == 64 else "HHIIIIIHHHHHH")
    try:
        header = struct.unpack_from(fmt, data, 16)
        machine, phoff, shoff = header[1], header[4], header[5]
        phsize, phnum, shsize, shnum, shstridx = header[8:13]
        loads, dynamic, notes = [], [], []
        for i in range(phnum):
            values = struct.unpack_from(endian + ("IIQQQQQQ" if bits == 64 else "IIIIIIII"), data, phoff + i * phsize)
            if bits == 64:
                kind, _, offset, address, _, size, _, _ = values
            else:
                kind, offset, address, _, size, _, _, _ = values
            if kind == 1:
                loads.append((address, offset, size))
            elif kind == 2:
                stride = 16 if bits == 64 else 8
                for off in range(offset, offset + size, stride):
                    tag, value = struct.unpack_from(endian + ("qQ" if bits == 64 else "iI"), data, off)
                    if tag == 0:
                        break
                    dynamic.append((tag, value))
            elif kind == 4:
                notes.append((offset, size))

        sections = []
        for i in range(shnum):
            values = struct.unpack_from(endian + ("IIQQQQIIQQ" if bits == 64 else "IIIIIIIIII"), data, shoff + i * shsize)
            sections.append(values)
            if values[1] == 7:
                notes.append((values[4], values[5]))

        def cstring(offset):
            end = data.find(b"\0", offset)
            if end < 0:
                raise PackagingError(f"unterminated ELF string: {path}")
            return data[offset:end].decode("utf-8", errors="replace")

        names = []
        if sections and shstridx < len(sections):
            table = sections[shstridx][4]
            names = [cstring(table + section[0]) for section in sections]
        external_dwarf = False
        for name, section in zip(names, sections):
            if name not in (".debug_info", ".zdebug_info", ".debug_str", ".zdebug_str"):
                continue
            contents = data[section[4]:section[4] + section[5]]
            if section[2] & 0x800:
                compression = struct.unpack_from(endian + "I", contents)[0]
                if compression != 1:
                    continue
                contents = zlib.decompress(contents[24 if bits == 64 else 12:])
            elif name.startswith(".zdebug_") and contents.startswith(b"ZLIB"):
                contents = zlib.decompress(contents[12:])
            if name.endswith("_str"):
                external_dwarf |= ".debug_addr" in names and b".dwo\0" in contents
                continue
            offset = 0
            while offset + 6 <= len(contents):
                length = struct.unpack_from(endian + "I", contents, offset)[0]
                prefix = 4
                if length == 0xFFFFFFFF:
                    length = struct.unpack_from(endian + "Q", contents, offset + 4)[0]
                    prefix = 12
                if length == 0:
                    break
                version = struct.unpack_from(endian + "H", contents, offset + prefix)[0]
                if version >= 5 and contents[offset + prefix + 2] in (4, 5, 6):
                    external_dwarf = True
                offset += prefix + length
        straddr = next((value for tag, value in dynamic if tag == 5), None)
        stroff = None
        if straddr is not None:
            stroff = next((offset + straddr - address for address, offset, size in loads if address <= straddr < address + size), None)
            if stroff is None:
                raise PackagingError(f"ELF DT_STRTAB is outside load segments: {path}")
        strings = lambda tag: [cstring(stroff + value) for item, value in dynamic if item == tag] if stroff is not None else []
        build_ids = set()
        for offset, size in notes:
            end = offset + size
            while offset + 12 <= end:
                namesz, descsz, kind = struct.unpack_from(endian + "III", data, offset)
                offset += 12
                name = data[offset:offset + namesz].rstrip(b"\0")
                offset += (namesz + 3) & ~3
                desc = data[offset:offset + descsz]
                offset += (descsz + 3) & ~3
                if name == b"GNU" and kind == 3:
                    build_ids.add(desc.hex())
        if len(build_ids) > 1:
            raise PackagingError(f"ELF has conflicting GNU build IDs: {path}")
        return {"machine": machine, "architecture": {183: "arm64", 62: "amd64"}.get(machine, f"elf-machine-{machine}"),
                "bits": bits, "needed": strings(1), "soname": next(iter(strings(14)), None),
                "runpath": strings(29), "rpath": strings(15), "build_id": next(iter(build_ids), None),
                "has_debug_info": any(name in (".debug_info", ".zdebug_info") for name in names),
                "requires_external_dwarf": external_dwarf, "sections": names}
    except (struct.error, IndexError, zlib.error) as exc:
        raise PackagingError(f"malformed ELF {path}: {exc}") from exc


def _runtime_boundary(environment, preset):
    cross = "cross" in preset
    boundary = environment.get("sdk", {}) if cross else environment.get("toolchains", {}).get("native", {})
    if cross and not boundary.get("present", False):
        boundary = environment.get("toolchains", {}).get("cross_arm64", {})
    sonames = boundary.get("runtime_sonames", environment.get("runtime_sonames", []))
    files = boundary.get("runtime_files", [])
    for item in files:
        if isinstance(item, str):
            sonames = list(sonames) + [Path(item).name]
        elif isinstance(item, dict):
            name = item.get("soname") or Path(item.get("path", "")).name
            if name:
                sonames = list(sonames) + [name]
    if not sonames:
        raise PackagingError(f"environment manifest has no explicit {'SDK' if cross else 'native'} runtime SONAME boundary for {preset}")
    return set(sonames)


def prune_runtime_entries(entries, mappings):
    """Drop unused link alternatives; explicit data mappings remain roots."""
    explicit = set()
    for mapping in mappings:
        if not mapping.get("explicit"):
            continue
        destination = mapping.get("destination", mapping.get("path", ""))
        source = Path(mapping["source"])
        if source.is_dir():
            explicit.update(path for path in entries if not destination or path == destination or path.startswith(destination + "/"))
        else:
            explicit.add(destination)
    explicit.update(resolve_entry(entries, path).path for path in list(explicit) if path in entries)
    infos = {path: inspect_elf(entry.source) for path, entry in entries.items()
             if entry.source is not None and not entry.directory and entry.link is None}
    infos = {path: info for path, info in infos.items() if info is not None}
    roots = {path for path in infos if path in explicit or path.startswith("bin/")}
    if not any(path.startswith("bin/") for path in infos):
        roots.update(infos)
    selected = set(roots)
    pending = list(roots)
    while pending:
        path = pending.pop()
        info = infos[path]
        for group in info["runpath"] or info["rpath"]:
            for directory in group.split(":"):
                if "$ORIGIN" not in directory and "${ORIGIN}" not in directory:
                    continue
                directory = directory.replace("${ORIGIN}", posixpath.dirname(path)).replace("$ORIGIN", posixpath.dirname(path))
                for needed in info["needed"]:
                    candidate = posixpath.normpath(posixpath.join(directory, needed))
                    if candidate in entries:
                        resolved = resolve_entry(entries, candidate)
                        if resolved.path in infos and resolved.path not in selected:
                            selected.add(resolved.path)
                            pending.append(resolved.path)
    keep = {}
    for path, entry in entries.items():
        resolved = resolve_entry(entries, path) if entry.link is not None else entry
        if resolved.path in infos:
            if resolved.path in selected:
                keep[path] = entry
        elif path in explicit or entry.directory or path.startswith(("bin/", "share/")):
            keep[path] = entry
    for path, entry in keep.items():
        if entry.link is not None:
            resolve_entry(keep, path)
    return keep


def validate_elf_closure(entries, environment, preset="linux_arm64", external_libraries=None):
    """Validate every ELF, including data-only plugins, against its own RUNPATH."""
    external_libraries = external_libraries or {}
    used_packages = set()
    elfs = {path: inspect_elf(entry.source) for path, entry in entries.items()
            if entry.source is not None and entry.link is None and not entry.directory}
    elfs = {path: info for path, info in elfs.items() if info is not None}
    if not elfs:
        if external_libraries:
            raise PackagingError("external Debian runtime dependencies are not used by any ELF")
        return {}
    boundary = _runtime_boundary(environment, preset)
    expected = "amd64" if preset == "linux_x86_64" else "arm64"
    if preset == "auto":
        expected = "amd64" if environment.get("host", {}).get("cpu") == "x86_64" else "arm64"
    for path, info in elfs.items():
        if info["architecture"] != expected:
            raise PackagingError(f"runtime payload architecture mismatch for preset {preset}: {path} is {info['architecture']}, expected {expected}")
        origin = posixpath.dirname(path)
        paths = []
        for group in info["runpath"] or info["rpath"]:
            for item in group.split(":"):
                if "$ORIGIN" in item or "${ORIGIN}" in item:
                    candidate = item.replace("${ORIGIN}", origin).replace("$ORIGIN", origin)
                    paths.append(posixpath.normpath(candidate))
        for needed in info["needed"]:
            found = False
            for directory in paths:
                candidate = posixpath.normpath(posixpath.join(directory, needed))
                if candidate in entries:
                    dependency = resolve_entry(entries, candidate)
                    depinfo = inspect_elf(dependency.source) if dependency.source else None
                    if depinfo is None or depinfo["machine"] != info["machine"]:
                        raise PackagingError(f"runtime dependency architecture mismatch: {path} -> {candidate}")
                    found = True
                    break
                if candidate in external_libraries:
                    dependency = external_libraries[candidate]
                    if dependency["machine"] != info["machine"] or dependency["soname"] != needed:
                        raise PackagingError(f"external runtime dependency identity mismatch: {path} -> {candidate}")
                    used_packages.add(dependency["package"])
                    found = True
                    break
            if not found and needed not in boundary:
                raise PackagingError(f"missing private runtime dependency: {path} needs {needed}; own RUNPATH={info['runpath'] or info['rpath']}; declared SDK boundary does not supply it")
    unused = {item["package"] for item in external_libraries.values()} - used_packages
    if unused:
        raise PackagingError(f"external Debian runtime dependencies are not used by any ELF: {sorted(unused)}")
    return elfs


def validate_architecture(entries, architecture):
    if architecture not in ("arm64", "amd64", "all"):
        raise PackagingError(f"unsupported Debian architecture: {architecture!r}")
    for path, entry in entries.items():
        if entry.directory or entry.link is not None or entry.source is None:
            continue
        elf = inspect_elf(entry.source)
        objects = [(path, elf["machine"])] if elf else []
        if not elf:
            with entry.source.open("rb") as stream:
                if stream.read(8) == b"!<arch>\n":
                    while header := stream.read(60):
                        if len(header) != 60 or header[58:] != b"`\n":
                            raise PackagingError(f"malformed static archive: {path}")
                        try:
                            size = int(header[48:58])
                            member = header[:16].decode("ascii").strip()
                            offset = stream.tell()
                            name_size = int(member[3:]) if member.startswith("#1/") else 0
                        except (ValueError, UnicodeDecodeError) as exc:
                            raise PackagingError(f"malformed static archive member: {path}") from exc
                        if size < 0 or name_size < 0 or name_size > size:
                            raise PackagingError(f"invalid static archive member size: {path}({member})")
                        stream.seek(offset + name_size)
                        identity = stream.read(min(20, size - name_size))
                        if identity.startswith(b"\x7fELF"):
                            if len(identity) < 20 or identity[5] not in (1, 2):
                                raise PackagingError(f"malformed archived ELF: {path}({member})")
                            machine = struct.unpack_from("<H" if identity[5] == 1 else ">H", identity, 18)[0]
                            objects.append((f"{path}({member})", machine))
                        stream.seek(offset + size + size % 2)
        for name, machine in objects:
            actual = {183: "arm64", 62: "amd64"}.get(machine, f"elf-machine-{machine}")
            if architecture == "all" or actual != architecture:
                raise PackagingError(f"Debian architecture/payload mismatch: Architecture={architecture}, {name} is {actual} (ELF machine {machine}); 'all' is only valid for non-ELF payloads")


def validate_debug_manifest(manifest, *, binary_root=None, debug_root=None):
    """Check build IDs for every archived binary/symbol pair, not just filenames."""
    manifest_path = Path(manifest) if not isinstance(manifest, dict) else None
    document = json.loads(manifest_path.read_text()) if manifest_path is not None else manifest
    base = manifest_path.parent if manifest_path else Path(".")
    pairs = document.get("binaries", document.get("artifacts", []))
    if not pairs:
        if document.get("enabled") is False:
            return document
        raise PackagingError(f"empty debug identity manifest: {manifest}")
    for pair in pairs:
        binary_name = pair.get("binary", pair.get("file"))
        debug_name = pair.get("debug_file", pair.get("debug"))
        if not binary_name or not debug_name:
            raise PackagingError(f"incomplete debug identity entry: {pair}")
        binary = Path(binary_root or base) / binary_name
        debug = Path(debug_root or base) / debug_name
        if not binary.is_file() or not debug.is_file():
            raise PackagingError(f"missing binary/debug input for identity validation: {binary}, {debug}")
        for field, source in (("binary_sha256", binary), ("debug_sha256", debug)):
            if pair.get(field) and _sha256(source) != pair[field]:
                raise PackagingError(f"debug identity digest mismatch ({field}): {source}")
        if not pair.get("build_id"):
            if not pair.get("binary_sha256") or not pair.get("debug_sha256"):
                raise PackagingError(f"debug identity entry lacks build ID and archive digests: {pair}")
            if _sha256(binary) != pair["binary_sha256"] or _sha256(debug) != pair["debug_sha256"]:
                raise PackagingError(f"debug archive identity mismatch: {binary} and {debug}")
            continue
        binfo, dinfo = inspect_elf(binary), inspect_elf(debug)
        expected = pair["build_id"].lower()
        if not binfo or not dinfo or binfo["build_id"] != expected or dinfo["build_id"] != expected:
            raise PackagingError(f"debug build ID mismatch: {binary} and {debug}; expected {expected}, binary={binfo and binfo['build_id']}, symbols={dinfo and dinfo['build_id']}")
        if not dinfo["has_debug_info"]:
            raise PackagingError(f"debug symbols have no usable DWARF info: {debug}")
        if dinfo.get("requires_external_dwarf", False):
            raise PackagingError(f"debug symbols still require uncollected split DWARF: {debug}")
    sources = document.get("sources") or []
    for source in [sources] if isinstance(sources, dict) else sources:
        source_root = Path(debug_root or base) / source["directory"]
        for item in source.get("files", []):
            path = source_root / relative_path(item["path"])
            if "symlink" in item:
                if not path.is_symlink() or os.readlink(path) != item["symlink"]:
                    raise PackagingError(f"debug source symlink identity mismatch: {path}")
                _link_destination(item["path"], item["symlink"])
                try:
                    path.resolve(strict=True).relative_to(source_root.resolve())
                except (ValueError, RuntimeError, OSError) as exc:
                    raise PackagingError(f"debug source symlink escapes or is broken: {path}") from exc
                continue
            if not path.is_file() or not item.get("sha256") or _sha256(path) != item["sha256"]:
                raise PackagingError(f"debug source identity mismatch: {path}")
    return document


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")


def _tar_bytes(entries, prefix="", extra=None):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w", format=tarfile.PAX_FORMAT) as archive:
        parents = set()
        for path, entry in entries.items():
            destination = posixpath.join(prefix, path)
            parent = destination if entry.directory else posixpath.dirname(destination)
            while parent:
                parents.add(parent)
                parent = posixpath.dirname(parent)
        for path in extra or {}:
            parent = posixpath.dirname(posixpath.join(prefix, path))
            while parent:
                parents.add(parent)
                parent = posixpath.dirname(parent)
        for path in sorted(parents):
            member = tarfile.TarInfo(path)
            member.type, member.mode, member.mtime = tarfile.DIRTYPE, 0o755, 0
            archive.addfile(member)
        for path, entry in sorted(entries.items()):
            if entry.directory:
                continue
            member = tarfile.TarInfo(posixpath.join(prefix, path))
            member.mode, member.mtime, member.uid, member.gid = entry.mode, 0, 0, 0
            member.uname = member.gname = "root"
            if entry.link is not None:
                member.type, member.linkname = tarfile.SYMTYPE, entry.link
                archive.addfile(member)
            else:
                member.size = entry.source.stat().st_size
                with entry.source.open("rb") as stream:
                    archive.addfile(member, stream)
        for path, content in sorted((extra or {}).items()):
            member = tarfile.TarInfo(posixpath.join(prefix, path))
            member.mode, member.mtime, member.uid, member.gid = 0o644, 0, 0, 0
            member.size = len(content)
            archive.addfile(member, io.BytesIO(content))
    return output.getvalue()


def _compress(data):
    output = io.BytesIO()
    with gzip.GzipFile(fileobj=output, mode="wb", filename="", mtime=0) as stream:
        stream.write(data)
    return output.getvalue()


def _write_archive(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    if str(path).endswith((".gz", ".tgz")):
        data = _compress(data)
    Path(path).write_bytes(data)


def _manifest(entries, elfs, spec, environment):
    files = []
    for path, entry in sorted(entries.items()):
        item = {"path": path, "mode": oct(entry.mode), "type": "directory" if entry.directory else "symlink" if entry.link is not None else "file"}
        if entry.link is not None:
            item["target"] = entry.link
        elif not entry.directory:
            item["sha256"] = _sha256(entry.source)
        if path in elfs:
            item["elf"] = elfs[path]
        files.append(item)
    provenance = []
    for path in spec.get("manifests", []):
        source = Path(path)
        if not source.is_file():
            raise PackagingError(f"missing declared provenance manifest: {source}")
        provenance.append({"name": source.name, "sha256": _sha256(source), "content": json.loads(source.read_text())})
    return {"schema_version": 1, "label": spec.get("label"), "package": spec["package"],
            "preset": spec["preset"], "sanitizer": spec.get("sanitizer", "none"), "layout": "bin/, lib/, share/ relative to package root",
            "install_root": spec.get("package_dir", ""), "entry_points": spec.get("entry_points") or [p for p in elfs if p.startswith("bin/")],
            "environment_sha256": environment.get("environment_sha256"), "sdk": environment.get("sdk", {}),
            "runtime_boundary": sorted(_runtime_boundary(environment, spec["preset"])) if elfs else [],
            "provenance": provenance, "files": files,
            "external_packages": spec.get("external_package_records", []),
            "debug_manifests": [{"label": document.get("label"), "variant": document.get("variant", {"preset": document.get("preset")}),
                                 "binaries": [{key: pair.get(key) for key in ("build_id", "binary_sha256", "debug_sha256", "architecture")} for pair in document.get("binaries", [])]}
                                for document in [json.loads(Path(path).read_text()) for path in spec.get("debug_manifests", [])]]}


def _relocated_sources(document, manifest, entries, destination_base=""):
    source = document.get("sources")
    if not source:
        return None
    original = (Path(manifest).parent / source["directory"]).resolve()
    for path, entry in entries.items():
        if entry.directory and entry.source and entry.source.resolve() == original:
            return dict(source, directory=posixpath.relpath(path, destination_base or "."))
    raise PackagingError(f"debug output group omitted declared source snapshot: {original}")


def _archive_debug(spec, installed, elfs):
    symbols = {}
    for mapping in spec.get("debug_entries", []):
        added = collect_entries([mapping])
        if set(symbols) & set(added):
            raise PackagingError("debug archive installation path collision")
        symbols.update(added)
    by_source = {str(entry.source.resolve()): path for path, entry in symbols.items() if entry.source and not entry.directory and entry.link is None}
    by_id = {info["build_id"]: path for path, info in elfs.items() if info["build_id"]}
    pairs = []
    sources = []
    for path in spec.get("debug_manifests", []):
        manifest = json.loads(Path(path).read_text())
        source = _relocated_sources(manifest, path, symbols, "debug")
        if source:
            sources.append(source)
        for pair in manifest.get("binaries", []):
            binary = by_id.get(pair.get("build_id"))
            if binary is None:
                continue
            source = (Path(path).parent / pair.get("debug_file", pair.get("debug", ""))).resolve()
            symbol = by_source.get(str(source))
            if symbol is None:
                raise PackagingError(f"published ELF lacks declared matching symbols in test export: {binary}")
            pairs.append({"binary": "../" + binary, "debug_file": posixpath.relpath(symbol, "debug"),
                          "build_id": pair["build_id"], "architecture": elfs[binary]["architecture"],
                          "binary_sha256": _sha256(installed[binary].source), "debug_sha256": _sha256(source)})
    if spec.get("separate_debug") and set(by_id) - {pair["build_id"] for pair in pairs}:
        raise PackagingError("test export contains ELF without a matching declared debug identity")
    # Per-target manifests refer to build output paths. Replace them with one
    # relocatable manifest whose paths resolve wholly inside the CI archive.
    symbols = {path: entry for path, entry in symbols.items() if not path.endswith("/debug_manifest.json")}
    if set(installed) & set(symbols):
        raise PackagingError("debug files collide with installed runtime files")
    return symbols, {"schema_version": 1, "preset": spec["preset"], "binaries": pairs, "sources": sources}


def export_debug_package(spec, environment):
    entries = collect_entries(spec["entries"])
    installed = collect_entries(spec.get("runtime_entries", []))
    binary_sources = {str(entry.source.resolve()): path for path, entry in installed.items() if entry.source and not entry.directory and entry.link is None}
    identities, digests = {}, {}
    for path, entry in installed.items():
        if not entry.source or entry.directory or entry.link is not None:
            continue
        info = inspect_elf(entry.source)
        if info and info["build_id"]:
            identities[info["build_id"]] = path
        digests[_sha256(entry.source)] = path
    symbols = {str(entry.source.resolve()): path for path, entry in entries.items() if entry.source and not entry.directory and entry.link is None}
    records = []
    variants = []
    sources = []
    for index, path in enumerate(spec.get("debug_manifests", [])):
        document = validate_debug_manifest(path)
        source = _relocated_sources(document, path, entries)
        if source:
            sources.append(source)
        variants.append(document.get("variant", {"label": document.get("label"), "preset": document.get("preset")}))
        for pair in document.get("binaries", []):
            original_binary = (Path(path).parent / pair["binary"]).resolve()
            original_debug = (Path(path).parent / pair["debug_file"]).resolve()
            symbol = symbols.get(str(original_debug))
            if symbol is None:
                raise PackagingError(f"debug output group omitted declared symbols: {original_debug}")
            binary = binary_sources.get(str(original_binary)) or identities.get(pair.get("build_id")) or digests.get(pair.get("binary_sha256"))
            binary = binary or f"artifacts/{index}/{original_binary.name}"
            records.append({"binary": binary, "debug_file": symbol, "build_id": pair.get("build_id"),
                            "binary_sha256": pair.get("binary_sha256") or _sha256(original_binary),
                            "debug_sha256": pair.get("debug_sha256") or _sha256(original_debug)})
    entries = {path: entry for path, entry in entries.items() if not path.endswith("debug_manifest.json")}
    identity = {"schema_version": 1, "symbols_only": True, "requires_matching_payload": True,
                "enabled": spec.get("separate_debug", False), "preset": spec["preset"],
                "environment_sha256": environment.get("environment_sha256"), "variants": variants, "binaries": records, "sources": sources}
    manifest = {"schema_version": 1, "kind": "debug_symbols", "label": spec.get("label"), "package": spec["package"],
                "preset": spec["preset"], "environment_sha256": environment.get("environment_sha256"),
                "sdk": environment.get("sdk", {}), "debug_manifest": "debug_manifest.json",
                "files": [{"path": path, "target": entry.link, "sha256": _sha256(entry.source) if entry.source and not entry.directory and entry.link is None else None} for path, entry in sorted(entries.items())]}
    write_json(spec["manifest"], manifest)
    extra = {"debug_manifest.json": (json.dumps(identity, sort_keys=True, indent=2) + "\n").encode(),
             "eros_manifest.json": (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode()}
    prefix = spec.get("package_dir", "").strip("/")
    if prefix:
        relative_path(prefix)
    _write_archive(spec["output"], _tar_bytes(entries, prefix, extra))


def _external_runtime(spec, environment):
    """Check declared Forge debs and index their real, separately owned libraries."""
    packages = spec.get("external_packages", [])
    if not packages:
        return {}
    if spec.get("package_dir", "").strip("/") != "opt/eros/" + spec["package"]:
        raise PackagingError("external Debian dependencies require the default /opt/eros/<package> layout")
    libraries = {}
    records = []
    for item in packages:
        metadata = json.loads(Path(item["manifest"]).read_text())
        package = metadata["package"]
        if package == spec["package"] or not re.fullmatch(r"[a-z0-9][a-z0-9+.-]+", package):
            raise PackagingError(f"invalid external Debian package identity: {package!r}")
        if any(record["package"] == package for record in records):
            raise PackagingError(f"duplicate external Debian package: {package}")
        if metadata.get("sha256") != _sha256(item["deb"]) or metadata.get("payload_sha256") != _sha256(item["payload"]):
            raise PackagingError(f"external Debian package/payload identity mismatch: {package}")
        expected = "amd64" if spec["preset"] == "linux_x86_64" or (spec["preset"] == "auto" and environment.get("host", {}).get("cpu") == "x86_64") else "arm64"
        if metadata["architecture"] != expected or metadata["preset"] != spec["preset"]:
            raise PackagingError(f"external Debian package architecture/preset mismatch: {package}")
        root = "opt/eros/" + package
        for entries in _read_payload(item["payload"]):
            manifest_path = root + "/eros_manifest.json"
            if manifest_path not in entries or entries[manifest_path].source is None:
                raise PackagingError(f"external Debian package lacks a Forge runtime manifest: {package}")
            manifest = json.loads(entries[manifest_path].source.read_text())
            if (manifest.get("package") != package or manifest.get("install_root", "").strip("/") != root
                    or manifest.get("preset") != spec["preset"]
                    or manifest.get("environment_sha256") != environment.get("environment_sha256")):
                raise PackagingError(f"external Debian runtime identity mismatch: {package}")
            for path, entry in entries.items():
                if not entry.directory and not path.startswith(root + "/"):
                    raise PackagingError(f"external Debian payload escapes its private root: {path}")
                if not path.startswith(root + "/lib/") or entry.directory:
                    continue
                local = path[len(root) + 1:]
                external = "../" + package + "/" + local
                resolved = resolve_entry(entries, path)
                info = inspect_elf(resolved.source) if resolved.source else None
                if info is None or not info["soname"]:
                    continue
                if info["architecture"] != expected:
                    raise PackagingError(f"external Debian library architecture mismatch: {path}")
                value = {"package": package, "local": local, "real": resolved.path[len(root) + 1:],
                         "link": entry.link, "elf": info,
                         "sha256": _sha256(entry.source) if entry.link is None else None,
                         "size": entry.source.stat().st_size if entry.link is None else None,
                         "machine": info["machine"], "soname": info["soname"]}
                libraries[external] = value
        if not any(value["package"] == package for value in libraries.values()):
            raise PackagingError(f"external Debian package has no shared libraries: {package}")
        records.append({"package": package, "version": metadata["version"], "architecture": metadata["architecture"],
                        "deb_sha256": metadata["sha256"], "payload_sha256": metadata["payload_sha256"]})
    spec["external_package_records"] = records
    return libraries


def _runtime_candidates(path, info, needed):
    origin = posixpath.dirname(path)
    for group in info["runpath"] or info["rpath"]:
        for directory in group.split(":"):
            if "$ORIGIN" not in directory and "${ORIGIN}" not in directory:
                continue
            directory = directory.replace("${ORIGIN}", origin).replace("$ORIGIN", origin)
            yield posixpath.normpath(posixpath.join(directory, needed))


def _referenced_external_libraries(entries, libraries):
    direct = set()
    has_elf = False
    for path, entry in entries.items():
        if entry.directory or entry.link is not None or entry.source is None:
            continue
        info = inspect_elf(entry.source)
        if info is None:
            continue
        has_elf = True
        for needed in info["needed"]:
            for candidate in _runtime_candidates(path, info, needed):
                if candidate in entries:
                    break
                external = libraries.get(candidate)
                if external is not None:
                    if external["machine"] == info["machine"] and external["soname"] == needed:
                        direct.add((external["package"], external["real"]))
                    break
    selected = set(direct)
    by_real = {(value["package"], value["real"]): value for value in libraries.values()}
    pending = list(direct)
    while pending:
        package, real = pending.pop()
        info = by_real[(package, real)]["elf"]
        for needed in info["needed"]:
            for candidate in _runtime_candidates("../" + package + "/" + real, info, needed):
                external = libraries.get(candidate)
                if external is not None:
                    key = (external["package"], external["real"])
                    if external["machine"] == info["machine"] and external["soname"] == needed and key not in selected:
                        selected.add(key)
                        pending.append(key)
                    break
    return selected, direct, has_elf


def export_package(spec, environment):
    if spec.get("debug_only"):
        return export_debug_package(spec, environment)
    external_libraries = _external_runtime(spec, environment)
    entries = collect_entries(spec["entries"])
    selected, direct, has_elf = _referenced_external_libraries(entries, external_libraries) if external_libraries else (set(), set(), False)
    selected_values = [value for value in external_libraries.values() if (value["package"], value["real"]) in selected]
    removed = set()
    matched_direct = set()
    for external in selected_values:
        path = external["local"]
        entry = entries.get(path)
        if entry is None:
            continue
        key = (external["package"], external["real"])
        if entry.link != external["link"] or (entry.link is None and _sha256(entry.source) != external["sha256"]):
            if key in direct:
                raise PackagingError(f"bundled runtime library differs from external Debian package {external['package']}: {path}")
            continue
        removed.add(path)
        if key in direct:
            matched_direct.add(key)
    if external_libraries and has_elf and not direct:
        raise PackagingError("missing private runtime dependency: no declared external Debian library is resolved by ELF RUNPATH")
    if direct - matched_direct or {value["package"] for value in external_libraries.values()} - {key[0] for key in matched_direct}:
        raise PackagingError("external Debian library is missing from the Bazel runtime closure")
    entries = prune_runtime_entries(entries, spec["entries"])
    for path in removed:
        entries.pop(path, None)
    runtime_manifest_content = None
    if external_libraries:
        old_manifest = entries.get("runtime_manifest.json")
        if old_manifest and old_manifest.source and old_manifest.source.parent.name.endswith(".runtime"):
            # The native runfiles manifest predates the deb split; retain its identity but update its closure.
            metadata = json.loads(old_manifest.source.read_text())
            if metadata.get("schema_version") != 1 or metadata.get("install_root") != "" or not isinstance(metadata.get("files"), list):
                raise PackagingError("invalid generated runtime_manifest.json in Bazel runtime closure")
            entries.pop("runtime_manifest.json")
            metadata["files"] = [item for item in metadata["files"] if item["path"] in entries]
            metadata["external_packages"] = spec["external_package_records"]
            runtime_manifest_content = (json.dumps(metadata, sort_keys=True, indent=2) + "\n").encode()
        external_files = {value["sha256"] for value in selected_values if value["sha256"]}
        sizes = {value["size"] for value in selected_values if value["size"] is not None}
        for path, entry in entries.items():
            if entry.source and not entry.directory and entry.link is None and entry.source.stat().st_size in sizes:
                if _sha256(entry.source) in external_files:
                    raise PackagingError(f"external Debian library is also bundled at {path}")
    elfs = validate_elf_closure(entries, environment, spec["preset"], external_libraries)
    for manifest in spec.get("debug_manifests", []):
        validate_debug_manifest(manifest)
    manifest = _manifest(entries, elfs, spec, environment)
    if spec.get("test_package") and not manifest["entry_points"]:
        raise PackagingError("test package has no declared executable entry point")
    for path in manifest["entry_points"]:
        relative_path(path)
        entry = resolve_entry(entries, path)
        if entry.directory or entry.source is None or not entry.mode & 0o111:
            raise PackagingError(f"test/program entry point is not an executable runtime file: {path}")
    write_json(spec["manifest"], manifest)
    extra = {"eros_manifest.json": (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode()}
    if runtime_manifest_content is not None:
        extra["runtime_manifest.json"] = runtime_manifest_content
    if "eros_manifest.json" in entries:
        raise PackagingError("reserved installation path collision: eros_manifest.json")
    if spec.get("test_package"):
        symbols, debug_manifest = _archive_debug(spec, entries, elfs)
        entries.update(symbols)
        if debug_manifest["binaries"]:
            extra["debug/debug_manifest.json"] = (json.dumps(debug_manifest, sort_keys=True, indent=2) + "\n").encode()
            manifest["debug_manifest"] = "debug/debug_manifest.json"
        manifest["debug_directories"] = [mapping["destination"] for mapping in spec.get("debug_entries", [])]
        manifest["instructions"] = "Execute entry_points in a target environment matching preset and SDK. Cross exports are not executed by Forge. Do not set LD_LIBRARY_PATH to build directories."
        write_json(spec["manifest"], manifest)
        extra["eros_manifest.json"] = (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode()
    prefix = spec.get("package_dir", "").strip("/")
    if prefix:
        relative_path(prefix)
    _write_archive(spec["output"], _tar_bytes(entries, prefix, extra))


def export_layout(spec, environment):
    entries = collect_entries(spec["entries"])
    entries = prune_runtime_entries(entries, spec["entries"])
    elfs = validate_elf_closure(entries, environment, spec["preset"])
    root = Path(spec["output"])
    root.mkdir(parents=True, exist_ok=True)
    for name, entry in sorted(entries.items()):
        output = root / name
        output.parent.mkdir(parents=True, exist_ok=True)
        if entry.directory:
            output.mkdir(exist_ok=True)
        elif entry.link is not None:
            output.symlink_to(entry.link)
        else:
            shutil.copyfile(entry.source, output)
            output.chmod(entry.mode)
    write_json(root / "runtime_manifest.json", _manifest(entries, elfs, spec, environment))
    Path(spec["executable"]).symlink_to(spec["executable_target"])


def _read_payload(path):
    entries = {}
    with tempfile.TemporaryDirectory(prefix="eros-deb-") as directory:
        root = Path(directory)
        with tarfile.open(path, "r:*") as archive:
            members = archive.getmembers()
            for member in members:
                name = member.name.removeprefix("./").rstrip("/")
                relative_path(name)
                if name in entries:
                    raise PackagingError(f"duplicate path in data tar: {name}")
                if member.isdir():
                    entry = Entry(name, directory=True, mode=0o755)
                elif member.issym():
                    _link_destination(name, member.linkname)
                    entry = Entry(name, link=member.linkname, mode=0o777)
                elif member.isfile():
                    source = root / name
                    source.parent.mkdir(parents=True, exist_ok=True)
                    with archive.extractfile(member) as stream, source.open("wb") as out:
                        shutil.copyfileobj(stream, out)
                    entry = Entry(name, source=source, mode=0o755 if member.mode & 0o111 else 0o644)
                else:
                    raise PackagingError(f"unsupported data tar entry (hardlinks/devices forbidden): {name}")
                entries[name] = entry
        for name, entry in entries.items():
            parent = posixpath.dirname(name)
            while parent:
                if parent in entries and not entries[parent].directory:
                    raise PackagingError(f"data tar path collision: {parent} is not a directory (for {name})")
                parent = posixpath.dirname(parent)
            if entry.link is not None:
                if name.startswith("opt/eros/"):
                    private = "/".join(name.split("/")[:3])
                    destination = _link_destination(name, entry.link)
                    if destination != private and not destination.startswith(private + "/"):
                        raise PackagingError(f"symlink escapes private package root: {name} -> {entry.link}")
                resolve_entry(entries, name)
        yield entries


def resolve_version(explicit="", environment=None, define=""):
    value = explicit or (environment if environment is not None else os.environ).get("DEB_VERSION", "") or define or "0.1.0"
    if not re.fullmatch(r"[0-9][A-Za-z0-9.+:~\-]*", value):
        raise PackagingError(f"invalid Debian version: {value!r}")
    return value


def _ar_member(name, data):
    header = f"{name + '/':<16}{0:<12}{0:<6}{0:<6}{'100644':<8}{len(data):<10}`\n".encode("ascii")
    if len(header) != 60:
        raise PackagingError(f"invalid ar member header: {name}")
    return header + data + (b"\n" if len(data) % 2 else b"")


def build_deb(spec):
    package = spec["package"]
    if not re.fullmatch(r"[a-z0-9][a-z0-9+.-]+", package):
        raise PackagingError(f"invalid Debian package name: {package!r}")
    version = resolve_version(spec.get("version", ""), define=spec.get("define_version", ""))
    architecture = spec["architecture"]
    runtime = json.loads(Path(spec["runtime_manifest"]).read_text()) if spec.get("runtime_manifest") else None
    external_packages = {item["package"]: item for item in runtime.get("external_packages", [])} if runtime else {}
    depends = list(spec.get("depends", []))
    for path in spec.get("dependency_manifests", []):
        dependency = json.loads(Path(path).read_text())
        name = dependency["package"]
        exported = external_packages.get(name)
        if (exported is None or exported["version"] != dependency["version"]
                or exported["architecture"] != dependency["architecture"]
                or exported["deb_sha256"] != dependency["sha256"]
                or exported["payload_sha256"] != dependency["payload_sha256"]):
            raise PackagingError(f"Debian dependency {name} does not match the checked external runtime payload")
        if any(value.split(" ", 1)[0] == name for value in depends):
            raise PackagingError(f"duplicate or conflicting Debian dependency: {name}")
        depends.append(f"{name} (= {dependency['version']})")
    if spec.get("runtime_manifest"):
        for external in runtime.get("external_packages", []):
            dependency = f"{external['package']} (= {external['version']})"
            if runtime["package"] != package or external["architecture"] != architecture or dependency not in depends:
                raise PackagingError(f"external runtime package requires matching name, architecture and Depends: {dependency}")
    for entries in _read_payload(spec["data"]):
        validate_architecture(entries, architecture)
        fields = {"Package": package, "Version": version, "Architecture": architecture,
                  "Maintainer": spec.get("maintainer", "EROS maintainers <maintainers@eros.invalid>"),
                  "Description": spec.get("description", package), "Section": spec.get("section", "misc"),
                  "Priority": spec.get("priority", "optional"),
                  "Installed-Size": str((sum(entry.source.stat().st_size for entry in entries.values() if entry.source is not None and not entry.directory) + 1023) // 1024)}
        for key, attr in (("Depends", "depends"), ("Pre-Depends", "predepends"), ("Recommends", "recommends"),
                          ("Suggests", "suggests"), ("Conflicts", "conflicts"), ("Breaks", "breaks"),
                          ("Replaces", "replaces"), ("Provides", "provides"), ("Homepage", "homepage")):
            value = depends if attr == "depends" else spec.get(attr)
            if value:
                fields[key] = ", ".join(value) if isinstance(value, list) else value
        for key, value in fields.items():
            if "\n" in value or "\r" in value:
                if key == "Description":
                    fields[key] = value.replace("\r", "").replace("\n", "\n ")
                else:
                    raise PackagingError(f"control field contains newline: {key}")
        control = "".join(f"{key}: {value}\n" for key, value in fields.items()).encode()
        control_files = {"control": control}
        for script, source in spec.get("scripts", {}).items():
            if script not in ("preinst", "postinst", "prerm", "postrm", "config", "templates", "conffiles"):
                raise PackagingError(f"unsupported maintainer script: {script}")
            control_files[script] = Path(source).read_bytes()
        control_entries = {}
        with tempfile.TemporaryDirectory(prefix="eros-control-") as temp:
            for name, content in control_files.items():
                path = Path(temp) / name
                path.write_bytes(content)
                control_entries[name] = Entry(name, path, mode=0o644 if name in ("control", "templates", "conffiles") else 0o755)
            control_tar = _compress(_tar_bytes(control_entries))
        data_tar = _compress(_tar_bytes(entries))
        output = b"!<arch>\n" + _ar_member("debian-binary", b"2.0\n") + _ar_member("control.tar.gz", control_tar) + _ar_member("data.tar.gz", data_tar)
        Path(spec["output"]).parent.mkdir(parents=True, exist_ok=True)
        Path(spec["output"]).write_bytes(output)
    if spec.get("manifest"):
        write_json(spec["manifest"], {"schema_version": 1, "package": package, "version": version,
                                    "architecture": architecture, "preset": spec.get("preset"), "sha256": _sha256(spec["output"]),
                                    "payload_sha256": _sha256(spec["data"])})


def publish_native(spec, environment):
    debug_dir = Path(spec["debug_dir"])
    debug_dir.mkdir(parents=True, exist_ok=True)
    preset = spec["preset"]
    tools = environment.get("toolchains", {}).get("cross_arm64" if "cross" in preset else "native", {}).get("tools", environment.get("tools", {}))

    def tool(name):
        value = tools.get(name, environment.get("tools", {}).get(name))
        if not value:
            raise PackagingError(f"environment manifest does not declare {name} for {preset}")
        return value["path"] if isinstance(value, dict) else value

    pairs = []
    for item in spec["binaries"]:
        source, output = Path(item["source"]), Path(item["output"])
        if not source.is_file():
            raise PackagingError(f"missing native ELF output: {source}")
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, output)
        output.chmod(0o755)
        info = inspect_elf(source)
        if info is None:
            raise PackagingError(f"declared native binary is not ELF: {source}")
        if spec["separate_debug"]:
            if not info["build_id"] or not info["has_debug_info"]:
                raise PackagingError(f"native separate_debug_info requires GNU build ID and usable DWARF, not split-DWARF placeholders: {source}")
            if info["requires_external_dwarf"] or ".debug_info.dwo" in info["sections"] or ".gnu_debugaltlink" in info["sections"]:
                raise PackagingError(f"uncollected split DWARF is unsupported; compile with -g, not -gsplit-dwarf: {source}")
            debug = debug_dir / (output.name + ".debug")
            subprocess.run([tool("objcopy"), "--only-keep-debug", str(source), str(debug)], check=True)
            subprocess.run([tool("strip"), "--strip-debug", str(output)], check=True)
            subprocess.run([tool("objcopy"), "--add-gnu-debuglink=" + str(debug), str(output)], check=True)
            build_id = info["build_id"]
            build_link = debug_dir / ".build-id" / build_id[:2] / (build_id[2:] + ".debug")
            build_link.parent.mkdir(parents=True, exist_ok=True)
            build_link.symlink_to(os.path.relpath(debug, build_link.parent))
            pairs.append({"binary": os.path.relpath(output, debug_dir), "debug_file": debug.name,
                          "build_id": build_id, "architecture": info["architecture"],
                          "binary_sha256": _sha256(output), "debug_sha256": _sha256(debug)})
    manifest = {"schema_version": 1, "label": spec["label"], "preset": preset,
                "environment_sha256": environment.get("environment_sha256"), "enabled": spec["separate_debug"], "binaries": pairs}
    write_json(debug_dir / "debug_manifest.json", manifest)
    standalone = dict(manifest)
    standalone["binaries"] = [dict(pair, binary=os.path.relpath(debug_dir / pair["binary"], Path(spec["debug_manifest"]).parent),
                                   debug_file=os.path.relpath(debug_dir / pair["debug_file"], Path(spec["debug_manifest"]).parent)) for pair in pairs]
    write_json(spec["debug_manifest"], standalone)
    if pairs:
        validate_debug_manifest(debug_dir / "debug_manifest.json")
    for item in spec.get("symlinks", []):
        output = Path(item["output"])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.symlink_to(item["target"])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("export", "layout", "deb", "native", "validate-debug"))
    parser.add_argument("--spec")
    parser.add_argument("--environment")
    parser.add_argument("--manifest")
    parser.add_argument("--binary-root")
    parser.add_argument("--debug-root")
    args = parser.parse_args(argv)
    try:
        if args.mode == "validate-debug":
            validate_debug_manifest(args.manifest, binary_root=args.binary_root, debug_root=args.debug_root)
            return 0
        spec = json.loads(Path(args.spec).read_text())
        environment = json.loads(Path(args.environment).read_text()) if args.environment else {}
        if args.mode == "export":
            export_package(spec, environment)
        elif args.mode == "layout":
            export_layout(spec, environment)
        elif args.mode == "deb":
            build_deb(spec)
        else:
            publish_native(spec, environment)
        return 0
    except (PackagingError, OSError, subprocess.CalledProcessError, json.JSONDecodeError, tarfile.TarError) as exc:
        print(f"Forge {args.mode} failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
