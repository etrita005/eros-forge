# MemorySanitizer profile for x86_64 native compilation
# Detects uninitialized memory reads

[settings]
arch=x86_64
build_type=Debug
compiler=gcc
compiler.cppstd=gnu20
compiler.version=13
compiler.libcxx=libstdc++11
os=Linux

[conf]
tools.cmake.cmaketoolchain:generator=Unix Makefiles
tools.cmake.cmaketoolchain:system_name=Linux
tools.cmake.cmaketoolchain:system_processor=x86_64
tools.build:cflags=["-O0", "-g", "-fsanitize=memory"]
tools.build:cxxflags=["-O0", "-g", "-fsanitize=memory"]
tools.build:exelinkflags=["-fsanitize=memory"]
tools.build:sharedlinkflags=["-fsanitize=memory"]
