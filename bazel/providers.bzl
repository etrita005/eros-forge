"""Analysis-time interfaces shared by build, runtime, and packaging rules."""

ErosInstallInfo = provider(
    doc = "Files installed relative to /opt/eros/<package> (or a test root).",
    fields = {
        "entries": "Structs with file, relative path, and optional explicit=True for plugin/resource roots; directories retain contents.",
        "manifests": "List of declared provenance/variant manifests.",
    },
)

ErosDebugInfo = provider(
    doc = "Explicitly archivable symbols and their binary identity manifests.",
    fields = {
        "files": "depset of matching debug artifacts.",
        "manifests": "depset of debug identity manifests.",
    },
)
