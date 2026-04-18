# MemorySanitizer profile for ARM64 native compilation
# Detects uninitialized memory reads

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
tools.build:cflags=["-O0", "-g", "-fsanitize=memory"]
tools.build:cxxflags=["-O0", "-g", "-fsanitize=memory"]
tools.build:exelinkflags=["-fsanitize=memory"]
tools.build:sharedlinkflags=["-fsanitize=memory"]
