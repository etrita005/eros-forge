import hashlib
import os
from conan import ConanFile
from conan.errors import ConanException


class BrokenDigest(ConanFile):
    name = "broken-digest"
    version = "1.0"
    settings = "os", "compiler", "build_type", "arch"
    exports_sources = "source.cc"

    def source(self):
        digest = hashlib.sha256(open(os.path.join(self.source_folder, "source.cc"), "rb").read()).hexdigest()
        if digest != "0" * 64:
            raise ConanException("controlled source checksum mismatch: " + digest)
