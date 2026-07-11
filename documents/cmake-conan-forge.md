# cmake_conan_forge 技术文档

## 概述

`cmake_conan_forge` 是 EROS 项目中用于构建 CMake 项目并集成 Conan 依赖管理的 Bazel 规则。它使用预定义的 Conan profile，自动匹配 Bazel 配置，支持原生编译和交叉编译。

## 设计目标

1. **Bazel 工具链集成**：使用预定义的 Conan profile，与 Bazel 配置自动匹配
2. **Conan 依赖管理**：自动运行 `conan install` 获取依赖
3. **交叉编译支持**：支持 x86_64 到 ARM64 的交叉编译
4. **Conan 工具链集成**：直接使用 Conan 生成的 `conan_toolchain.cmake` 进行构建

## 架构

```
cmake_conan_forge (宏)
    ├── conan_install (规则) - 运行 conan install，使用预定义 profile
    └── cmake_build (规则) - 使用 Conan 工具链执行 CMake 构建
        └── [cc_library] - 当提供 hdrs 时，自动生成 cc_library 包装器
```

## 规则详解

### 1. cmake_conan_forge (宏)

用户入口宏，创建完整的构建流程。

#### 参数

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `name` | string | 是 | - | 规则名称 |
| `conanfile` | label | 是 | - | conanfile.txt 或 conanfile.py 文件 |
| `cmake_lists` | label | 是 | - | CMakeLists.txt 文件 |
| `srcs` | label_list | 是 | - | 源文件列表 |
| `target_name` | string | 否 | 与 `name` 相同 | CMake 目标名称 |
| `out_binary` | string | 否 | 见下方说明 | 输出二进制文件名（有库输出时默认为空，否则默认与 target_name 相同）|
| `out_static_libs` | string_list | 否 | `[]` | 静态库输出列表（如 `["libmylib.a"]`）|
| `out_shared_libs` | string_list | 否 | `[]` | 共享库输出列表（如 `["libmylib.so"]`）|
| `hdrs` | label_list | 否 | `None` | 头文件列表，用于 cc_library 包装器 |
| `includes` | string_list | 否 | `None` | 包含路径列表，用于 cc_library 包装器 |
| `out_headers` | string | 否 | `""` | 头文件输出目录名（通过 kwargs 传递）|
| `linkopts` | string_list | 否 | `[]` | 链接选项（通过 kwargs 传递）|
| `visibility` | list | 否 | `["//visibility:public"]` | 可见性（通过 kwargs 传递）|

#### cc_library 包装器

当提供 `hdrs` 参数时，宏会自动创建一个 `cc_library` 包装器：

- 内部的 `cmake_build` 规则名称为 `_{name}_cmake`，可见性为 private
- 外部的 `cc_library` 依赖内部的 `cmake_build`，使用提供的 `hdrs` 和 `includes`
- 这样其他 Bazel 目标可以像使用普通 `cc_library` 一样依赖此规则

当不提供 `hdrs` 时，`cmake_build` 规则直接使用 `name` 作为规则名。

#### 使用示例

**构建可执行文件：**

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

**构建库（带 cc_library 包装器）：**

```python
cmake_conan_forge(
    name = "mylib",
    conanfile = "conanfile.txt",
    cmake_lists = "CMakeLists.txt",
    srcs = glob(["src/**/*.cpp", "src/**/*.h"]),
    target_name = "mylib",
    out_static_libs = ["libmylib.a"],
    out_shared_libs = ["libmylib.so"],
    hdrs = glob(["include/**/*.h"]),
    includes = ["include"],
)
```

**构建带链接选项的库：**

```python
cmake_conan_forge(
    name = "mylib",
    conanfile = "conanfile.txt",
    cmake_lists = "CMakeLists.txt",
    srcs = glob(["src/**/*.cpp", "src/**/*.h"]),
    target_name = "mylib",
    out_static_libs = ["libmylib.a"],
    linkopts = ["-lpthread"],
)
```

### 2. conan_install (规则)

运行 `conan install` 获取依赖并生成 CMake 配置文件。

#### 属性

| 属性 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `conanfile` | label | 是 | conanfile.txt 或 conanfile.py 文件 |
| `host_profile` | label | 是 | Conan host profile 文件 |
| `build_profile` | label | 是 | Conan build profile 文件 |

#### 功能

1. 根据目标平台选择预定义的 Conan profile（host 和 build 分开选择）
2. 运行 `conan install --profile:host=... --profile:build=... --build=missing` 安装依赖
3. 生成 CMake 工具链文件（`conan_toolchain.cmake`）和 preset 文件

#### 预定义 Profile

Profile 文件位于 `eros/forge/bazel/toolchain/conan/`：

**原生编译 Profile：**

| Profile 文件 | 用途 |
|-------------|------|
| `linux_x86_64_release.profile` | x86_64 原生编译 Release |
| `linux_x86_64_debug.profile` | x86_64 原生编译 Debug |
| `linux_x86_64_build_release.profile` | x86_64 原生编译 Build Release |
| `linux_x86_64_tsan.profile` | x86_64 原生编译 ThreadSanitizer |
| `linux_x86_64_msan.profile` | x86_64 原生编译 MemorySanitizer |
| `linux_x86_64_asan.profile` | x86_64 原生编译 AddressSanitizer |
| `linux_arm64_release.profile` | ARM64 原生编译 Release |
| `linux_arm64_debug.profile` | ARM64 原生编译 Debug |
| `linux_arm64_build_release.profile` | ARM64 原生编译 Build Release |
| `linux_arm64_tsan.profile` | ARM64 原生编译 ThreadSanitizer |
| `linux_arm64_msan.profile` | ARM64 原生编译 MemorySanitizer |
| `linux_arm64_asan.profile` | ARM64 原生编译 AddressSanitizer |

**交叉编译 Profile（x86_64 → ARM64）：**

| Profile 文件 | 用途 |
|-------------|------|
| `linux_x86_64_cross_arm64_host_release.profile` | x86_64→ARM64 交叉编译 host Release |
| `linux_x86_64_cross_arm64_host_debug.profile` | x86_64→ARM64 交叉编译 host Debug |
| `linux_x86_64_cross_arm64_build_release.profile` | x86_64→ARM64 交叉编译 build Release |
| `linux_x86_64_cross_arm64_build_debug.profile` | x86_64→ARM64 交叉编译 build Debug |
| `linux_x86_64_cross_arm64_tsan.profile` | x86_64→ARM64 交叉编译 ThreadSanitizer |
| `linux_x86_64_cross_arm64_msan.profile` | x86_64→ARM64 交叉编译 MemorySanitizer |
| `linux_x86_64_cross_arm64_asan.profile` | x86_64→ARM64 交叉编译 AddressSanitizer |

**交叉编译 Profile（ARM64 → ARM64，使用自定义 glibc）：**

| Profile 文件 | 用途 |
|-------------|------|
| `linux_arm64_cross_arm64_host_release.profile` | ARM64→ARM64 交叉编译 host Release |
| `linux_arm64_cross_arm64_host_debug.profile` | ARM64→ARM64 交叉编译 host Debug |
| `linux_arm64_cross_arm64_build_release.profile` | ARM64→ARM64 交叉编译 build Release |
| `linux_arm64_cross_arm64_build_debug.profile` | ARM64→ARM64 交叉编译 build Debug |
| `linux_arm64_cross_arm64_tsan.profile` | ARM64→ARM64 交叉编译 ThreadSanitizer |
| `linux_arm64_cross_arm64_msan.profile` | ARM64→ARM64 交叉编译 MemorySanitizer |
| `linux_arm64_cross_arm64_asan.profile` | ARM64→ARM64 交叉编译 AddressSanitizer |

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

使用 Conan 生成的工具链执行 CMake 构建。

#### 属性

| 属性 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `conan_deps` | label | 是 | - | conan_install 规则的标签 |
| `cmake_lists` | label | 是 | - | CMakeLists.txt 文件 |
| `srcs` | label_list | 否 | `[]` | 源文件列表 |
| `target_name` | string | 是 | - | CMake 目标名称 |
| `out_binary` | string | 否 | `""` | 输出二进制文件名 |
| `out_static_libs` | string_list | 否 | `[]` | 静态库输出列表 |
| `out_shared_libs` | string_list | 否 | `[]` | 共享库输出列表 |
| `out_headers` | string | 否 | `""` | 头文件输出目录名 |
| `linkopts` | string_list | 否 | `[]` | 链接选项 |
| `strip_binary` | bool | 否 | `False` | 是否 strip 二进制文件（由宏自动选择）|
| `strip_tool` | string | 否 | `""` | strip 工具路径（交叉编译时使用 aarch64-linux-gnu-strip）|
| `cmake_preset` | string | 否 | `"conan-release"` | CMake preset 名称（由宏自动选择）|

#### 构建流程

1. 创建符号链接到 Conan 生成的文件（包括 `CMakePresets.json` 和 `ConanPresets.json`）
2. 使用 Conan 工具链直接配置项目（不使用 `--preset`）
3. 运行 CMake 构建
4. 复制可执行文件、静态库、共享库和头文件
5. 在 Release 模式下 strip 二进制文件
6. 清理符号链接和临时文件

#### 构建命令

```bash
# 配置（使用 Conan 工具链，不使用 --preset）
cmake -S "$SOURCE_DIR" -B "$BUILD_DIR" \
    -DCMAKE_TOOLCHAIN_FILE="$CONAN_OUTPUT_DIR/conan_toolchain.cmake" \
    -DCMAKE_BUILD_TYPE="$CMAKE_BUILD_TYPE" \
    -DCMAKE_POLICY_DEFAULT_CMP0091=NEW \
    -G "Unix Makefiles" \
    -DCMAKE_FIND_ROOT_PATH:PATH="$CONAN_OUTPUT_DIR"

# 构建
cmake --build "$BUILD_DIR" -j10
```

#### CcInfo 提供者

当 `out_static_libs` 或 `out_shared_libs` 非空时，`cmake_build` 规则会提供 `CcInfo`，使其他 Bazel 目标可以链接这些库。`CcInfo` 包含：

- **linking_context**：包含所有静态库（`.a`）和共享库（`.so`）的链接信息，以及 `linkopts` 中的链接选项
- **compilation_context**：当 `out_headers` 非空时，包含头文件目录信息

## 平台配置

### 支持的平台配置

下表列出的"配置组合"是实际可用的 bazelrc `--config` 组合（平台配置可与构建模式 /
sanitizer 配置叠加）。注意：`linux_x86_64_asan` 等是内部 `config_setting` 名称
（用于 select() 匹配），**不是** bazelrc 配置；用户应使用 `--config=linux_x86_64
--config=asan` 这样的组合。

| 平台配置 | 构建模式 / Sanitizer 组合 | 说明 |
|----------|---------------------------|------|
| `--config=linux_x86_64` | （默认 Release） | x86_64 原生编译 |
| `--config=linux_x86_64` | `--config=debug` | x86_64 原生编译 Debug |
| `--config=linux_x86_64` | `--config=asan` | x86_64 原生编译 AddressSanitizer |
| `--config=linux_x86_64` | `--config=tsan` | x86_64 原生编译 ThreadSanitizer |
| `--config=linux_x86_64` | `--config=msan` | x86_64 原生编译 MemorySanitizer（需 Clang） |
| `--config=linux_arm64` | （默认 Release / `--config=debug` / `--config=asan` / ...） | ARM64 原生编译 |
| `--config=linux_x86_64_cross_arm64` | （默认 Release / `--config=debug` / `--config=asan` / ...） | x86_64 交叉编译到 ARM64 |
| `--config=linux_arm64_cross_arm64` | （默认 Release / `--config=debug` / `--config=asan` / ...） | ARM64 交叉编译到 ARM64（自定义 glibc）|

> Conan 的 sanitizer profile 由 `generate_files.py` 生成，覆盖 asan / tsan / msan
> （见 `SANITIZERS`）。**ubsan 暂无 Conan profile**（`cmake_conan_forge` 也无对应
> select 分支）；如需 ubsan，请在 `generate_files.py` 的 `SANITIZERS` 中补充并在
> `cmake_conan_forge.bzl` 的 select 中加入对应分支。

### Profile 选择逻辑

#### host_profile 选择

```python
host_profile = select({
    # ARM64 sanitizer profiles
    "@eros_forge//bazel/toolchain:linux_arm64_tsan": "@eros_forge//bazel/toolchain/conan:linux_arm64_tsan",
    "@eros_forge//bazel/toolchain:linux_arm64_msan": "@eros_forge//bazel/toolchain/conan:linux_arm64_msan",
    "@eros_forge//bazel/toolchain:linux_arm64_asan": "@eros_forge//bazel/toolchain/conan:linux_arm64_asan",
    # ARM64 cross ARM64 sanitizer profiles
    "@eros_forge//bazel/toolchain:linux_arm64_cross_arm64_tsan": "@eros_forge//bazel/toolchain/conan:linux_arm64_cross_arm64_tsan",
    "@eros_forge//bazel/toolchain:linux_arm64_cross_arm64_msan": "@eros_forge//bazel/toolchain/conan:linux_arm64_cross_arm64_msan",
    "@eros_forge//bazel/toolchain:linux_arm64_cross_arm64_asan": "@eros_forge//bazel/toolchain/conan:linux_arm64_cross_arm64_asan",
    # x86_64 sanitizer profiles
    "@eros_forge//bazel/toolchain:linux_x86_64_tsan": "@eros_forge//bazel/toolchain/conan:linux_x86_64_tsan",
    "@eros_forge//bazel/toolchain:linux_x86_64_msan": "@eros_forge//bazel/toolchain/conan:linux_x86_64_msan",
    "@eros_forge//bazel/toolchain:linux_x86_64_asan": "@eros_forge//bazel/toolchain/conan:linux_x86_64_asan",
    # x86_64 cross ARM64 sanitizer profiles
    "@eros_forge//bazel/toolchain:linux_x86_64_cross_arm64_tsan": "@eros_forge//bazel/toolchain/conan:linux_x86_64_cross_arm64_tsan",
    "@eros_forge//bazel/toolchain:linux_x86_64_cross_arm64_msan": "@eros_forge//bazel/toolchain/conan:linux_x86_64_cross_arm64_msan",
    "@eros_forge//bazel/toolchain:linux_x86_64_cross_arm64_asan": "@eros_forge//bazel/toolchain/conan:linux_x86_64_cross_arm64_asan",
    # Cross-compilation host profiles
    "@eros_forge//bazel/toolchain:linux_x86_64_cross_arm64_debug": "@eros_forge//bazel/toolchain/conan:linux_x86_64_cross_arm64_host_debug",
    "@eros_forge//bazel/toolchain:linux_x86_64_cross_arm64": "@eros_forge//bazel/toolchain/conan:linux_x86_64_cross_arm64_host_release",
    "@eros_forge//bazel/toolchain:linux_arm64_cross_arm64_debug": "@eros_forge//bazel/toolchain/conan:linux_arm64_cross_arm64_host_debug",
    "@eros_forge//bazel/toolchain:linux_arm64_cross_arm64": "@eros_forge//bazel/toolchain/conan:linux_arm64_cross_arm64_host_release",
    # Native profiles
    "@eros_forge//bazel/toolchain:linux_arm64_debug": "@eros_forge//bazel/toolchain/conan:linux_arm64_debug",
    "@eros_forge//bazel/toolchain:linux_arm64": "@eros_forge//bazel/toolchain/conan:linux_arm64_release",
    "@eros_forge//bazel/toolchain:linux_x86_64_debug": "@eros_forge//bazel/toolchain/conan:linux_x86_64_debug",
    "//conditions:default": "@eros_forge//bazel/toolchain/conan:linux_x86_64_release",
})
```

#### build_profile 选择

```python
build_profile = select({
    # ARM64 sanitizer profiles (build = host for native)
    "@eros_forge//bazel/toolchain:linux_arm64_tsan": "@eros_forge//bazel/toolchain/conan:linux_arm64_tsan",
    "@eros_forge//bazel/toolchain:linux_arm64_msan": "@eros_forge//bazel/toolchain/conan:linux_arm64_msan",
    "@eros_forge//bazel/toolchain:linux_arm64_asan": "@eros_forge//bazel/toolchain/conan:linux_arm64_asan",
    # ARM64 cross ARM64 (build uses native ARM64 sanitizer profiles)
    "@eros_forge//bazel/toolchain:linux_arm64_cross_arm64_tsan": "@eros_forge//bazel/toolchain/conan:linux_arm64_tsan",
    "@eros_forge//bazel/toolchain:linux_arm64_cross_arm64_msan": "@eros_forge//bazel/toolchain/conan:linux_arm64_msan",
    "@eros_forge//bazel/toolchain:linux_arm64_cross_arm64_asan": "@eros_forge//bazel/toolchain/conan:linux_arm64_asan",
    # x86_64 sanitizer profiles (build = host for native)
    "@eros_forge//bazel/toolchain:linux_x86_64_tsan": "@eros_forge//bazel/toolchain/conan:linux_x86_64_tsan",
    "@eros_forge//bazel/toolchain:linux_x86_64_msan": "@eros_forge//bazel/toolchain/conan:linux_x86_64_msan",
    "@eros_forge//bazel/toolchain:linux_x86_64_asan": "@eros_forge//bazel/toolchain/conan:linux_x86_64_asan",
    # x86_64 cross ARM64 (build uses native x86_64 sanitizer profiles)
    "@eros_forge//bazel/toolchain:linux_x86_64_cross_arm64_tsan": "@eros_forge//bazel/toolchain/conan:linux_x86_64_tsan",
    "@eros_forge//bazel/toolchain:linux_x86_64_cross_arm64_msan": "@eros_forge//bazel/toolchain/conan:linux_x86_64_msan",
    "@eros_forge//bazel/toolchain:linux_x86_64_cross_arm64_asan": "@eros_forge//bazel/toolchain/conan:linux_x86_64_asan",
    # Cross-compilation build profiles
    "@eros_forge//bazel/toolchain:linux_x86_64_cross_arm64_debug": "@eros_forge//bazel/toolchain/conan:linux_x86_64_cross_arm64_build_debug",
    "@eros_forge//bazel/toolchain:linux_x86_64_cross_arm64": "@eros_forge//bazel/toolchain/conan:linux_x86_64_cross_arm64_build_release",
    "@eros_forge//bazel/toolchain:linux_arm64_cross_arm64_debug": "@eros_forge//bazel/toolchain/conan:linux_arm64_cross_arm64_build_debug",
    "@eros_forge//bazel/toolchain:linux_arm64_cross_arm64": "@eros_forge//bazel/toolchain/conan:linux_arm64_cross_arm64_build_release",
    # Native build profiles
    "@eros_forge//bazel/toolchain:linux_arm64_debug": "@eros_forge//bazel/toolchain/conan:linux_arm64_debug",
    "@eros_forge//bazel/toolchain:linux_arm64": "@eros_forge//bazel/toolchain/conan:linux_arm64_build_release",
    "@eros_forge//bazel/toolchain:linux_x86_64_debug": "@eros_forge//bazel/toolchain/conan:linux_x86_64_debug",
    "//conditions:default": "@eros_forge//bazel/toolchain/conan:linux_x86_64_build_release",
})
```

#### strip_tool 选择

```python
strip_tool = select({
    "@eros_forge//bazel/toolchain:linux_x86_64_cross_arm64": "aarch64-linux-gnu-strip",
    "@eros_forge//bazel/toolchain:linux_arm64_cross_arm64": "aarch64-linux-gnu-strip",
    "//conditions:default": "strip",
})
```

#### strip_binary 选择

```python
strip_binary = select({
    "@eros_forge//bazel/toolchain:tsan": False,
    "@eros_forge//bazel/toolchain:msan": False,
    "@eros_forge//bazel/toolchain:asan": False,
    "@eros_forge//bazel/toolchain:cmake_debug": False,
    "//conditions:default": True,
})
```

#### cmake_preset 选择

```python
cmake_preset = select({
    "@eros_forge//bazel/toolchain:tsan": "conan-debug",
    "@eros_forge//bazel/toolchain:msan": "conan-debug",
    "@eros_forge//bazel/toolchain:asan": "conan-debug",
    "@eros_forge//bazel/toolchain:cmake_debug": "conan-debug",
    "//conditions:default": "conan-release",
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
cmake -S "$SOURCE_DIR" -B "$BUILD_DIR" \
    -DCMAKE_TOOLCHAIN_FILE="$CONAN_OUTPUT_DIR/conan_toolchain.cmake" \
    -DCMAKE_BUILD_TYPE="$CMAKE_BUILD_TYPE" \
    -DCMAKE_POLICY_DEFAULT_CMP0091=NEW \
    -G "Unix Makefiles" \
    -DCMAKE_FIND_ROOT_PATH:PATH="$CONAN_OUTPUT_DIR"
```

## 配置一致性

### Bazel 与 Conan Profile 配置对应

| 配置项 | Bazel | Conan Profile |
|--------|-------|---------------|
| C++ 标准 | `--cxxopt=-std=c++20` | `compiler.cppstd=gnu20` |
| Release 模式 | `--config=release`（`-O3 -DNDEBUG -g`） | `build_type=Release` |
| Debug 模式 | `--config=debug`（`-g -O0`） | `build_type=Debug` |
| Sanitizer | `--config=linux_x86_64 --config=asan`（或 `tsan`/`msan`） | 对应 sanitizer profile |

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

### Sanitizer 构建

```bash
# AddressSanitizer（平台配置 + sanitizer 配置组合）
bazel build //:hello --config=linux_x86_64 --config=asan

# ThreadSanitizer
bazel build //:hello --config=linux_x86_64 --config=tsan

# MemorySanitizer（通常需 Clang，GCC 支持有限）
bazel build //:hello --config=linux_x86_64 --config=msan

# UndefinedBehaviorSanitizer（注意：Conan 暂无 ubsan profile，见上文说明）
bazel build //:hello --config=linux_x86_64 --config=ubsan
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

### 4. Sanitizer 构建时 strip 失败

**问题**：使用 sanitizer 构建时，strip 工具可能移除 sanitizer 需要的符号。

**解决方案**：sanitizer 配置下自动禁用 strip（`strip_binary=False`）。

### 5. 共享库符号链接问题

**问题**：构建的共享库可能是符号链接（如 `libmylib.so -> libmylib.so.1.0`）。

**解决方案**：构建脚本会自动解析符号链接并复制实际文件。

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

- Bazel 9.0（使用 bzlmod；项目依赖 `MODULE.bazel` 而非 `WORKSPACE`）
- CMake >= 3.16
- Conan 2.x
- GCC 13 (aarch64-linux-gnu-gcc 用于交叉编译)
