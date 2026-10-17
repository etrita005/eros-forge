from pathlib import Path

from conan import ConanFile
from conan.tools.cmake import CMake, CMakeToolchain, cmake_layout
from conan.tools.files import check_sha256


class TinyMath(ConanFile):
    name = "tiny_math"
    license = "MIT"
    package_type = "library"
    settings = "os", "arch", "compiler", "build_type"
    options = {"shared": [True, False], "fPIC": [True, False]}
    default_options = {"shared": False, "fPIC": True}
    exports_sources = "CMakeLists.txt", "LICENSE", "include/tiny_math/answer.h", "src/tiny_math.cc"

    def layout(self):
        cmake_layout(self)

    def source(self):
        check_sha256(self, str(Path(self.source_folder) / "src/tiny_math.cc"),
                     self.conan_data["sources"][str(self.version)]["sha256"])

    def generate(self):
        CMakeToolchain(self).generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        CMake(self).install()

    def package_info(self):
        self.cpp_info.libs = ["tiny_math"]
        self.cpp_info.set_property("cmake_file_name", "tiny_math")
        self.cpp_info.set_property("cmake_target_name", "tiny_math::tiny_math")
