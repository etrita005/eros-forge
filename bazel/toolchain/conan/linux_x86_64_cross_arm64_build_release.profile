# Build profile for x86_64 -> ARM64 cross-compilation
# This describes the BUILD machine (x86_64 native)

[settings]
arch=x86_64
build_type=Release
compiler=gcc
compiler.cppstd=gnu20
compiler.version=13
compiler.libcxx=libstdc++11
os=Linux

[conf]
tools.cmake.cmaketoolchain:generator=Unix Makefiles
tools.cmake.cmaketoolchain:system_name=Linux
tools.cmake.cmaketoolchain:system_processor=x86_64
tools.build:cflags=["-O3", "-DNDEBUG"]
tools.build:cxxflags=["-O3", "-DNDEBUG"]
