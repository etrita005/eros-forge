# CMake toolchain file for cross-compilation from ARM64 to ARM64
# Host: aarch64-linux-gnu
# Target: aarch64-linux-gnu

set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR aarch64)

# Cross-compiler
set(CMAKE_C_COMPILER /usr/bin/aarch64-linux-gnu-gcc)
set(CMAKE_CXX_COMPILER /usr/bin/aarch64-linux-gnu-g++)

# Sysroot and library paths
set(CMAKE_FIND_ROOT_PATH /usr/aarch64-linux-gnu)

# Cross-compilation settings
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)

# Additional linker flags
set(CMAKE_EXE_LINKER_FLAGS "-L/usr/lib/gcc-cross/aarch64-linux-gnu/13 -L/usr/aarch64-linux-gnu/lib -L/usr/lib/aarch64-linux-gnu -lstdc++ -lgcc -lm -Wl,--rpath=/opt/eros/lib -Wl,--dynamic-linker=/opt/eros/lib/ld-linux-aarch64.so.1")
set(CMAKE_SHARED_LINKER_FLAGS "-L/usr/lib/gcc-cross/aarch64-linux-gnu/13 -L/usr/aarch64-linux-gnu/lib -L/usr/lib/aarch64-linux-gnu -lstdc++ -lgcc -lm")
