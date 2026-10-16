import hashlib
import os

from conan import ConanFile
from conan.errors import ConanException
from conan.tools.cmake import CMake, CMakeDeps, CMakeToolchain, cmake_layout
from conan.tools.files import patch


class Bar(ConanFile):
    name = "bar"
    package_type = "library"
    settings = "os", "compiler", "build_type", "arch"
    options = {"shared": [True, False], "fPIC": [True, False]}
    default_options = {"shared": False, "fPIC": True}
    exports_sources = "CMakeLists.txt", "bar.cc", "forge_dependency.h", "bar_config.h.in", "patches/*"

    def requirements(self):
        self.requires("leaf/1.0", transitive_headers=True, transitive_libs=True)

    def layout(self):
        cmake_layout(self)

    def source(self):
        source = os.path.join(self.source_folder, "bar.cc")
        digest = hashlib.sha256(open(source, "rb").read()).hexdigest()
        expected = self.conan_data["source_sha256"]
        if digest != expected:
            raise ConanException("controlled source checksum mismatch: expected " + expected + ", got " + digest)
        patch(self, patch_file=os.path.join(self.source_folder, "patches", "value.patch"), base_path=self.source_folder)

    def generate(self):
        CMakeDeps(self).generate()
        CMakeToolchain(self).generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        CMake(self).install()
        if self.conf.get("tools.build:install_strip", default=False):
            self.run('strip --strip-debug "{}"'.format(os.path.join(self.package_folder, "lib", "libbar.a")))

    def package_info(self):
        self.cpp_info.libs = ["bar"]
        self.cpp_info.system_libs = ["pthread"]
