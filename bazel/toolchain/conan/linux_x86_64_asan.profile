# AddressSanitizer profile for linux_x86_64 native compilation
# Detects memory errors

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
tools.build:cflags=["-O0", "-g", "-fsanitize=address"]
tools.build:cxxflags=["-O0", "-g", "-fsanitize=address"]
tools.build:exelinkflags=["-fsanitize=address"]
tools.build:sharedlinkflags=["-fsanitize=address"]
