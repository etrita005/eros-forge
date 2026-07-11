# Build profile for ARM64 -> ARM64 (with custom glibc) cross-compilation
# This describes the BUILD machine (ARM64 native)

[settings]
arch=armv8
build_type=Release
compiler=gcc
compiler.cppstd=gnu20
compiler.version=13
compiler.libcxx=libstdc++11
os=Linux

[conf]
tools.cmake.cmaketoolchain:generator=Unix Makefiles
tools.cmake.cmaketoolchain:system_name=Linux
tools.cmake.cmaketoolchain:system_processor=aarch64
tools.build:cflags=["-O3", "-DNDEBUG"]
tools.build:cxxflags=["-O3", "-DNDEBUG"]
