# Build profile for ARM64 -> ARM64 cross-compilation (with custom glibc)
# This describes the BUILD machine (ARM64 native)

[settings]
arch=armv8
build_type=Debug
compiler=gcc
compiler.cppstd=gnu20
compiler.version=13
compiler.libcxx=libstdc++11
os=Linux

[conf]
tools.cmake.cmaketoolchain:generator=Unix Makefiles
tools.cmake.cmaketoolchain:system_name=Linux
tools.cmake.cmaketoolchain:system_processor=aarch64
