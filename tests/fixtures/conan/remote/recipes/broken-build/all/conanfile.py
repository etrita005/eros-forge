from conan import ConanFile
from conan.tools.cmake import CMake, CMakeToolchain, cmake_layout


class BrokenBuild(ConanFile):
    name = "broken-build"
    version = "1.0"
    settings = "os", "compiler", "build_type", "arch"
    exports_sources = "CMakeLists.txt", "broken.cc"

    def layout(self):
        cmake_layout(self)

    def generate(self):
        CMakeToolchain(self).generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()
