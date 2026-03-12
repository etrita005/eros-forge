# cmake_forge 技术文档

## 概述

`cmake_forge` 是 EROS 项目中用于构建纯 CMake 项目（无 Conan 依赖）的 Bazel 规则。它基于 `rules_foreign_cc` 的 `cmake` 规则，提供了与 EROS 工具链的集成。

## 设计目标

1. **简化使用**：提供简洁的 API 来构建 CMake 项目
2. **工具链集成**：自动选择正确的 CMake 工具链文件
3. **构建类型支持**：支持 Debug 和 Release 构建模式

## 与 cmake_conan_forge 的区别

| 特性 | cmake_forge | cmake_conan_forge |
|------|-------------|-------------------|
| 依赖管理 | 无 | Conan |
| 底层实现 | rules_foreign_cc | 自定义规则 |
| 交叉编译 | 依赖工具链文件 | 完全支持 |
| 适用场景 | 简单 CMake 项目 | 需要 Conan 依赖的项目 |

## 架构

```
cmake_forge (宏)
    ├── native.filegroup - 选择工具链文件
    ├── cmake (_{name}_release) - Release 构建目标
    ├── cmake (_{name}_debug) - Debug 构建目标
    └── native.alias - 根据 --config 选择实际目标
```

## 规则详解

### cmake_forge (宏)

用户入口宏，创建 CMake 构建目标。

#### 参数

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `name` | string | 是 | 规则名称 |
| `cache_entries` | dict | 否 | CMake 缓存变量 |
| `generate_crosstool_file` | bool | 否 | 是否生成交叉编译工具文件 |
| `data` | label_list | 否 | 额外的数据依赖 |
| `**kwargs` | - | 否 | 传递给 cmake 规则的其他参数 |

#### 使用示例

```python
load("@eros_forge//bazel:cmake_forge.bzl", "cmake_forge")

cmake_forge(
    name = "my_lib",
    lib_name = "mylib",
    lib_source = ":srcs",
    out_static_libs = ["libmylib.a"],
    cache_entries = {
        "BUILD_SHARED_LIBS": "OFF",
    },
)
```

### 工具链文件选择

`cmake_forge` 使用 `select` 根据平台配置选择正确的工具链文件：

```python
native.filegroup(
    name = "_{}_toolchain_file".format(name),
    srcs = select({
        "@eros_forge//bazel/toolchain:linux_x86_64": ["@eros_forge//bazel/toolchain/cmake:linux_x86_64.cmake"],
        "@eros_forge//bazel/toolchain:linux_arm64": ["@eros_forge//bazel/toolchain/cmake:linux_arm64.cmake"],
        "@eros_forge//bazel/toolchain:linux_x86_64_cross_arm64": ["@eros_forge//bazel/toolchain/cmake:linux_x86_64_cross_arm64.cmake"],
        "@eros_forge//bazel/toolchain:linux_arm64_cross_arm64": ["@eros_forge//bazel/toolchain/cmake:linux_arm64_cross_arm64.cmake"],
        "//conditions:default": [],
    }),
)
```

### 构建类型支持

由于 `rules_foreign_cc` 的 `cache_entries` 不支持 `select`，使用 alias + select 来支持 Debug 和 Release 模式：

```python
# Release 目标
cmake(
    name = "_{}_release".format(name),
    cache_entries = {
        "CMAKE_BUILD_TYPE": "Release",
        "CMAKE_TOOLCHAIN_FILE": "$(location :_{}_toolchain_file)".format(name),
    } | cache_entries,
    ...
)

# Debug 目标
cmake(
    name = "_{}_debug".format(name),
    cache_entries = {
        "CMAKE_BUILD_TYPE": "Debug",
        "CMAKE_TOOLCHAIN_FILE": "$(location :_{}_toolchain_file)".format(name),
    } | cache_entries,
    ...
)

# Alias 根据 --config=debug/release 选择实际目标
native.alias(
    name = name,
    actual = select({
        "@eros_forge//bazel/toolchain:cmake_debug": "_{}_debug".format(name),
        "//conditions:default": "_{}_release".format(name),
    }),
    ...
)
```

使用 `--config=debug` 或 `--config=release` 来选择构建类型：

```bash
# Release 模式（默认）
bazel build //:my_lib --config=linux_arm64

# Debug 模式
bazel build //:my_lib --config=linux_arm64 --config=debug
```

## 平台配置

### 支持的平台配置

| 配置名称 | 说明 |
|----------|------|
| `linux_x86_64` | x86_64 原生编译 |
| `linux_arm64` | ARM64 原生编译 |
| `linux_x86_64_cross_arm64` | x86_64 交叉编译到 ARM64 |
| `linux_arm64_cross_arm64` | ARM64 交叉编译到 ARM64 |

## 工具链文件

工具链文件位于 `eros/forge/bazel/toolchain/cmake/` 目录：

### linux_x86_64.cmake

```cmake
set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR x86_64)

set(CMAKE_C_COMPILER "/usr/bin/gcc")
set(CMAKE_CXX_COMPILER "/usr/bin/g++")
```

### linux_arm64.cmake

```cmake
set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR aarch64)

set(CMAKE_C_COMPILER "/usr/bin/gcc")
set(CMAKE_CXX_COMPILER "/usr/bin/g++")
```

### linux_x86_64_cross_arm64.cmake / linux_arm64_cross_arm64.cmake

```cmake
set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR aarch64)

set(CMAKE_C_COMPILER "/usr/bin/aarch64-linux-gnu-gcc")
set(CMAKE_CXX_COMPILER "/usr/bin/aarch64-linux-gnu-g++")

set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)

set(CMAKE_FIND_ROOT_PATH "/usr/aarch64-linux-gnu")

set(CMAKE_EXE_LINKER_FLAGS "-L/usr/lib/gcc/aarch64-linux-gnu/13 -L/usr/aarch64-linux-gnu/lib -Wl,--rpath=/opt/eros/lib -Wl,--dynamic-linker=/opt/eros/lib/ld-linux-aarch64.so.1")
```

## 构建命令

### 原生编译

```bash
# ARM64 原生编译（Release 模式，默认）
bazel build //:my_lib --config=linux_arm64

# ARM64 原生编译（Debug 模式）
bazel build //:my_lib --config=linux_arm64 --config=debug

# x86_64 原生编译
bazel build //:my_lib --config=linux_x86_64
```

### 交叉编译

```bash
# 交叉编译到 ARM64（Release 模式）
bazel build //:my_lib --config=linux_arm64_cross_arm64 --config=release

# 交叉编译到 ARM64（Debug 模式）
bazel build //:my_lib --config=linux_arm64_cross_arm64 --config=debug
```

## 常见参数

### lib_name

CMake 项目的库名称。

### lib_source

源代码文件组，通常使用 `glob` 或 `filegroup`。

```python
filegroup(
    name = "srcs",
    srcs = glob(["src/**/*.cpp", "include/**/*.h"]),
)

cmake_forge(
    name = "my_lib",
    lib_name = "mylib",
    lib_source = ":srcs",
)
```

### out_static_libs / out_shared_libs

指定输出的库文件。

```python
cmake_forge(
    name = "my_lib",
    lib_name = "mylib",
    lib_source = ":srcs",
    out_static_libs = ["libmylib.a"],
    out_shared_libs = ["libmylib.so"],
)
```

### out_binaries

指定输出的可执行文件。

```python
cmake_forge(
    name = "my_app",
    lib_name = "myapp",
    lib_source = ":srcs",
    out_binaries = ["myapp"],
)
```

## 限制

1. **cache_entries 不支持 select**：如果需要根据平台设置不同的 CMake 变量，需要创建多个目标
2. **交叉编译依赖 rules_foreign_cc**：某些复杂的交叉编译场景可能需要使用 `cmake_conan_forge`
3. **无依赖管理**：不集成 Conan，需要手动管理依赖

## 与 rules_foreign_cc 的关系

`cmake_forge` 是 `rules_foreign_cc` 的 `cmake` 规则的封装，主要添加了：

1. 自动工具链文件选择
2. 构建类型分离（Debug/Release）
3. EROS 平台配置集成

底层仍然使用 `rules_foreign_cc` 的实现：

```python
load("@rules_foreign_cc//foreign_cc:cmake.bzl", "cmake")
```

## 最佳实践

### 1. 使用 filegroup 组织源代码

```python
filegroup(
    name = "srcs",
    srcs = glob([
        "src/**/*.cpp",
        "src/**/*.h",
        "include/**/*.h",
    ]),
    visibility = ["//visibility:private"],
)

cmake_forge(
    name = "my_lib",
    lib_name = "mylib",
    lib_source = ":srcs",
    out_static_libs = ["libmylib.a"],
    visibility = ["//visibility:public"],
)
```

### 2. 使用 cache_entries 配置 CMake

```python
cmake_forge(
    name = "my_lib",
    lib_name = "mylib",
    lib_source = ":srcs",
    cache_entries = {
        "BUILD_SHARED_LIBS": "OFF",
        "ENABLE_TESTS": "OFF",
        "MY_FEATURE": "ON",
    },
    out_static_libs = ["libmylib.a"],
)
```

### 3. 添加依赖

```python
cmake_forge(
    name = "my_lib",
    lib_name = "mylib",
    lib_source = ":srcs",
    data = [
        "@some_external_lib//:headers",
    ],
    out_static_libs = ["libmylib.a"],
)
```

## 故障排除

### 1. 找不到工具链文件

**问题**：构建时报错找不到工具链文件。

**解决方案**：确保在 MODULE.bazel 中正确引用了 eros_forge：

```python
bazel_dep(name = "eros_forge", repo_name = "eros_forge")
local_path_override(
    module_name = "eros_forge",
    path = "//eros/forge",
)
```

### 2. 交叉编译链接错误

**问题**：交叉编译时链接到宿主机库。

**解决方案**：检查工具链文件中的 `CMAKE_FIND_ROOT_PATH` 设置，确保使用目标机的库路径。

### 3. 构建类型不生效

**问题**：Debug 构建没有生成调试符号。

**解决方案**：使用 `--config=debug` 来选择 Debug 模式：

```bash
bazel build //:my_lib --config=linux_arm64 --config=debug
```
