import os
from conan import ConanFile
from conan.tools.cmake import CMake, CMakeToolchain, cmake_layout


class Leaf(ConanFile):
    name = "leaf"
    package_type = "library"
    settings = "os", "compiler", "build_type", "arch"
    options = {"shared": [True, False], "fPIC": [True, False]}
    default_options = {"shared": False, "fPIC": True}
    exports_sources = "CMakeLists.txt", "leaf.cc", "leaf.h"

    def layout(self):
        cmake_layout(self)

    def generate(self):
        CMakeToolchain(self).generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        CMake(self).install()
        if self.conf.get("tools.build:install_strip", default=False):
            self.run('strip --strip-debug "{}"'.format(os.path.join(self.package_folder, "lib", "libleaf.a")))

    def package_info(self):
        self.cpp_info.libs = ["leaf"]
