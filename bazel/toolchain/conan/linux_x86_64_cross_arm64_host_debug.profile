# Host profile for x86_64 -> ARM64 cross-compilation
# This describes the TARGET machine (ARM64)

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
tools.build:compiler_executables={"c": "/usr/bin/aarch64-linux-gnu-gcc", "cpp": "/usr/bin/aarch64-linux-gnu-g++", "asm": "/usr/bin/aarch64-linux-gnu-gcc"}
tools.cmake.cmaketoolchain:extra_variables={"CMAKE_FIND_ROOT_PATH_MODE_PROGRAM": "NEVER", "CMAKE_FIND_ROOT_PATH_MODE_LIBRARY": "ONLY", "CMAKE_FIND_ROOT_PATH_MODE_INCLUDE": "ONLY", "CMAKE_TRY_COMPILE_TARGET_TYPE": "STATIC_LIBRARY", "CMAKE_ASM_COMPILER": "/usr/bin/aarch64-linux-gnu-gcc", "CMAKE_LINKER": "/usr/bin/aarch64-linux-gnu-ld", "CMAKE_AR": "/usr/bin/aarch64-linux-gnu-ar", "CMAKE_OBJCOPY": "/usr/bin/aarch64-linux-gnu-objcopy", "CMAKE_OBJDUMP": "/usr/bin/aarch64-linux-gnu-objdump", "CMAKE_STRIP": "/usr/bin/aarch64-linux-gnu-strip", "CMAKE_NM": "/usr/bin/aarch64-linux-gnu-nm"}
tools.build:cflags=["-B", "/usr/bin/aarch64-linux-gnu-", "-O0", "-g"]
tools.build:cxxflags=["-B", "/usr/bin/aarch64-linux-gnu-", "-O0", "-g"]
tools.build:exelinkflags=["-B", "/usr/bin/aarch64-linux-gnu-", "-L/usr/lib/gcc-cross/aarch64-linux-gnu/13", "-L/usr/aarch64-linux-gnu/lib", "-L/usr/lib/aarch64-linux-gnu", "-Wl,--rpath=/opt/eros/lib", "-Wl,--dynamic-linker=/opt/eros/lib/ld-linux-aarch64.so.1"]
tools.build:sharedlinkflags=["-B", "/usr/bin/aarch64-linux-gnu-", "-L/usr/lib/gcc-cross/aarch64-linux-gnu/13", "-L/usr/aarch64-linux-gnu/lib", "-L/usr/lib/aarch64-linux-gnu", "-Wl,--rpath=/opt/eros/lib", "-Wl,--dynamic-linker=/opt/eros/lib/ld-linux-aarch64.so.1"]
