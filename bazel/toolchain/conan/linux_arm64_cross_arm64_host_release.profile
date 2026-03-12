# Host profile for ARM64 -> ARM64 cross-compilation (with custom glibc)
# This describes the TARGET machine (ARM64 with custom glibc)

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
tools.build:compiler_executables={"c": "/usr/bin/aarch64-linux-gnu-gcc", "cpp": "/usr/bin/aarch64-linux-gnu-g++"}
tools.cmake.cmaketoolchain:extra_variables={"CMAKE_FIND_ROOT_PATH_MODE_PROGRAM": "NEVER", "CMAKE_FIND_ROOT_PATH_MODE_LIBRARY": "ONLY", "CMAKE_FIND_ROOT_PATH_MODE_INCLUDE": "ONLY"}
tools.build:exelinkflags=["-L/usr/lib/gcc/aarch64-linux-gnu/13", "-L/usr/aarch64-linux-gnu/lib", "-L/usr/lib/aarch64-linux-gnu", "-Wl,--rpath=/opt/eros/lib", "-Wl,--dynamic-linker=/opt/eros/lib/ld-linux-aarch64.so.1"]
