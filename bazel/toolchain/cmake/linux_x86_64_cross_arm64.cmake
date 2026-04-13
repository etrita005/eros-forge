# CMake toolchain file for cross-compilation from x86_64 to ARM64
# Host: x86_64-linux-gnu
# Target: aarch64-linux-gnu

set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR aarch64)

# Cross-compiler
set(CMAKE_C_COMPILER /usr/bin/aarch64-linux-gnu-gcc)
set(CMAKE_CXX_COMPILER /usr/bin/aarch64-linux-gnu-g++)

# Assembler - use gcc as assembler driver with -B flag to find correct tools
set(CMAKE_ASM_COMPILER /usr/bin/aarch64-linux-gnu-gcc)

# Other tools
set(CMAKE_AR /usr/bin/aarch64-linux-gnu-ar)
set(CMAKE_LINKER /usr/bin/aarch64-linux-gnu-ld)
set(CMAKE_NM /usr/bin/aarch64-linux-gnu-nm)
set(CMAKE_OBJCOPY /usr/bin/aarch64-linux-gnu-objcopy)
set(CMAKE_OBJDUMP /usr/bin/aarch64-linux-gnu-objdump)
set(CMAKE_RANLIB /usr/bin/aarch64-linux-gnu-ranlib)
set(CMAKE_STRIP /usr/bin/aarch64-linux-gnu-strip)

# Compiler flags to use correct assembler and tools
set(CMAKE_C_FLAGS "-B/usr/bin/aarch64-linux-gnu-")
set(CMAKE_CXX_FLAGS "-B/usr/bin/aarch64-linux-gnu-")
set(CMAKE_ASM_FLAGS "-B/usr/bin/aarch64-linux-gnu-")

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
