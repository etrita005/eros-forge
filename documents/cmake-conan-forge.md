# cmake_conan_forge 技术文档

## 概述

`cmake_conan_forge` 是 EROS 项目中用于构建 CMake 项目并集成 Conan 依赖管理的 Bazel 规则。它使用预定义的 Conan profile，自动匹配 Bazel 配置，支持原生编译和交叉编译。

## 设计目标

1. **Bazel 工具链集成**：使用预定义的 Conan profile，与 Bazel 配置自动匹配
2. **Conan 依赖管理**：自动运行 `conan install` 获取依赖
3. **交叉编译支持**：支持 x86_64 到 ARM64 的交叉编译
4. **使用 Conan Preset**：直接使用 Conan 生成的 CMake preset 进行构建

## 架构

```
cmake_conan_forge (宏)
    ├── conan_install (规则) - 运行 conan install，使用预定义 profile
    └── cmake_build (规则) - 使用 Conan preset 执行 CMake 构建
```

## 规则详解

### 1. cmake_conan_forge (宏)

用户入口宏，创建完整的构建流程。

#### 参数

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `name` | string | 是 | 规则名称 |
| `conanfile` | label | 是 | conanfile.txt 或 conanfile.py 文件 |
| `cmake_lists` | label | 是 | CMakeLists.txt 文件 |
| `srcs` | label_list | 是 | 源文件列表 |
| `target_name` | string | 是 | CMake 目标名称 |

#### 使用示例

```python
load("@eros_forge//bazel:cmake_conan_forge.bzl", "cmake_conan_forge")

cmake_conan_forge(
    name = "hello",
    conanfile = "conanfile.txt",
    cmake_lists = "CMakeLists.txt",
    srcs = glob(["src/**/*.cpp", "src/**/*.h"]),
    target_name = "hello",
)
```

### 2. conan_install (规则)

运行 `conan install` 获取依赖并生成 CMake 配置文件。

#### 功能

1. 根据目标平台选择预定义的 Conan profile
2. 运行 `conan install` 安装依赖
3. 生成 CMake 工具链和 preset 文件

#### 预定义 Profile

Profile 文件位于 `eros/forge/bazel/toolchain/conan/`：

| Profile 文件 | 用途 |
|-------------|------|
| `linux_x86_64_release.profile` | x86_64 原生编译 Release |
| `linux_x86_64_debug.profile` | x86_64 原生编译 Debug |
| `linux_arm64_release.profile` | ARM64 原生编译 Release |
| `linux_arm64_debug.profile` | ARM64 原生编译 Debug |
| `linux_x86_64_cross_arm64_host_release.profile` | x86_64→ARM64 交叉编译 host Release |
| `linux_x86_64_cross_arm64_host_debug.profile` | x86_64→ARM64 交叉编译 host Debug |
| `linux_arm64_cross_arm64_host_release.profile` | ARM64→ARM64 交叉编译 host Release |
| `linux_arm64_cross_arm64_host_debug.profile` | ARM64→ARM64 交叉编译 host Debug |

#### Profile 配置示例（交叉编译）

```ini
# Host profile for ARM64 -> ARM64 cross-compilation (with custom glibc)

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
```

### 3. cmake_build (规则)

使用 Conan 生成的 preset 执行 CMake 构建。

#### 构建流程

1. 创建符号链接到 Conan 生成的文件
2. 使用 Conan preset 配置项目
3. 运行 CMake 构建
4. 复制可执行文件

#### 构建命令

```bash
# 配置（使用 Conan preset）
cmake --preset conan-release -B "$BUILD_DIR" -DCMAKE_FIND_ROOT_PATH:PATH="$CONAN_OUTPUT_DIR"

# 构建
cmake --build "$BUILD_DIR" --target "$TARGET_NAME" -j10
```

## 平台配置

### 支持的平台配置

| 配置名称 | 说明 |
|----------|------|
| `linux_x86_64` | x86_64 原生编译 |
| `linux_arm64` | ARM64 原生编译 |
| `linux_x86_64_cross_arm64` | x86_64 交叉编译到 ARM64 |
| `linux_arm64_cross_arm64` | ARM64 交叉编译到 ARM64（使用自定义 glibc） |

### Profile 选择逻辑

```python
host_profile = select({
    "@eros_forge//bazel/toolchain:linux_x86_64_cross_arm64": "@eros_forge//bazel/toolchain/conan:linux_x86_64_cross_arm64_host_release",
    "@eros_forge//bazel/toolchain:linux_arm64_cross_arm64": "@eros_forge//bazel/toolchain/conan:linux_arm64_cross_arm64_host_release",
    "@eros_forge//bazel/toolchain:linux_arm64": "@eros_forge//bazel/toolchain/conan:linux_arm64_release",
    "//conditions:default": "@eros_forge//bazel/toolchain/conan:linux_x86_64_release",
})
```

## CMakeLists.txt 编写指南

使用 `cmake_conan_forge` 时，CMakeLists.txt 可以非常简洁：

```cmake
cmake_minimum_required(VERSION 3.16)
project(my_project VERSION 1.0)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# 直接使用 find_package，Conan 依赖会自动配置
find_package(fmt REQUIRED)

# 添加共享库
add_library(mylib SHARED mylib.cpp)
target_link_libraries(mylib PUBLIC fmt::fmt)

# 添加可执行文件
add_executable(my_app main.cpp)
target_link_libraries(my_app PRIVATE mylib)
```

## 交叉编译原理

### CMAKE_FIND_ROOT_PATH_MODE 设置

| 变量 | 值 | 说明 |
|------|-----|------|
| `CMAKE_FIND_ROOT_PATH_MODE_PROGRAM` | NEVER | 程序在宿主机查找 |
| `CMAKE_FIND_ROOT_PATH_MODE_LIBRARY` | ONLY | 库只在目标机查找 |
| `CMAKE_FIND_ROOT_PATH_MODE_INCLUDE` | ONLY | 头文件只在目标机查找 |
| `CMAKE_FIND_ROOT_PATH_MODE_PACKAGE` | ONLY (默认) | CMake 包只在目标机查找 |

### Conan 包查找

由于 `CMAKE_FIND_ROOT_PATH_MODE_PACKAGE` 默认为 `ONLY`，需要将 Conan 输出目录添加到 `CMAKE_FIND_ROOT_PATH`：

```bash
cmake --preset conan-release -B "$BUILD_DIR" -DCMAKE_FIND_ROOT_PATH:PATH="$CONAN_OUTPUT_DIR"
```

## 配置一致性

### Bazel 与 Conan Profile 配置对应

| 配置项 | Bazel | Conan Profile |
|--------|-------|---------------|
| C++ 标准 | `--cxxopt=-std=c++20` | `compiler.cppstd=gnu20` |
| Release 模式 | `-O3 -DNDEBUG -g` | `build_type=Release` |
| Debug 模式 | `-g -O0` + asan/ubsan | `build_type=Debug` |

## 构建命令

### 原生编译

```bash
# ARM64 原生编译
bazel build //:hello --config=linux_arm64

# x86_64 原生编译
bazel build //:hello --config=linux_x86_64
```

### 交叉编译

```bash
# 交叉编译到 ARM64（使用自定义 glibc）
bazel build //:hello --config=linux_arm64_cross_arm64 --config=release

# x86_64 交叉编译到 ARM64
bazel build //:hello --config=linux_x86_64_cross_arm64 --config=release
```

## 常见问题

### 1. Conan 找不到包

**问题**：交叉编译时 CMake 无法找到 Conan 安装的包。

**解决方案**：通过 `-DCMAKE_FIND_ROOT_PATH:PATH="$CONAN_OUTPUT_DIR"` 将 Conan 输出目录添加到查找路径。

### 2. C++ 标准不一致

**问题**：Conan profile 和 Bazel 的 C++ 标准设置不一致。

**解决方案**：确保 Conan profile 中的 `compiler.cppstd` 与 Bazel 的 `--cxxopt` 设置一致（当前都是 C++20）。

### 3. glibc 版本不匹配

**问题**：目标机的 glibc 版本低于宿主机。

**解决方案**：使用交叉编译配置，链接到 `/opt/eros/lib` 中的自定义 glibc。

## 文件结构

```
project/
├── BUILD.bazel          # Bazel 构建文件
├── CMakeLists.txt       # CMake 配置
├── conanfile.txt        # Conan 依赖声明
├── main.cpp             # 源代码
├── mylib.cpp            # 共享库源代码
├── mylib.h              # 共享库头文件
└── MODULE.bazel         # Bazel 模块配置
```

## 依赖

- Bazel >= 6.0
- CMake >= 3.16
- Conan 2.x
- GCC 13 (aarch64-linux-gnu-gcc 用于交叉编译)
