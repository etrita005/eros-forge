# Bazel 9 + Forge + CMake 构建第三方库最佳实践

本文档介绍如何使用 Bazel 9 + EROS Forge + CMake 构建第三方 C/C++ 库。

## 概述

EROS Forge 的 `cmake_forge` 规则简化了 CMake 项目的集成：
- 自动处理 CMake 工具链配置
- 支持跨平台编译（Linux x86_64, ARM64）
- 统一的构建接口
- 与 Bazel 原生规则无缝集成

## 核心组件

### 1. `cmake_forge` 规则

位置：`@eros_forge//bazel:cmake_forge.bzl`

**关键参数**：
- `lib_source`: 包含源码的 filegroup label
- `lib_name`: 要构建的库名称
- `out_shared_libs`: 输出的共享库列表
- `cache_entries`: CMake 缓存配置
- `env`: 环境变量

### 2. 第三方库仓库结构

```
thirdparty/
└── your_library/
    ├── MODULE.bazel              # Bazel 模块定义
    ├── BUILD.bazel               # 构建规则
    ├── extensions.bzl            # 仓库扩展（可选）
    └── cmake/
        └── library_options.bzl   # CMake 配置选项
```

## 实现方案

### 方案 A: 使用 repository_rule（推荐）

适用于：Git 仓库包含子模块或需要自定义处理的场景

**extensions.bzl**:
```python
def _library_source_impl(rctx):
    # Clone source code (including submodules)
    result = rctx.execute(["git", "clone", "--recurse-submodules", "<repository_url>", "."])
    if result.return_code != 0:
        fail("Failed to clone repository")

    # Submodules may ship their own BUILD/BUILD.bazel files, which conflict with
    # Bazel's package boundary (glob skips directories containing a BUILD file).
    # RENAME them to a backup extension instead of deleting, so user/valid BUILD
    # files are never lost and the change is reversible/auditable. Only rename
    # BUILD files inside vendored subdirectories, not the project's own.
    rctx.execute([
        "bash", "-c",
        "find . -path ./.git -prune -o \\( -name BUILD -o -name BUILD.bazel \\) -type f -print0 "
        "| while IFS= read -r -d '' f; do mv \"$f\" \"$f.bak\"; done",
    ])

    # Create BUILD file with :all filegroup
    rctx.file("BUILD.bazel", """package(default_visibility = ["//visibility:public"])
filegroup(name = "all", srcs = glob(["**/*"], exclude = ["**/.git/**", "**/.github/**", "**/*.pyc", "**/__pycache__/**"]))
""")

library_source = repository_rule(implementation = _library_source_impl, attrs = {})

def _library_ext_impl(module_ctx):
    library_source(name = "library_source")

library_ext = module_extension(implementation = _library_ext_impl)
```

**MODULE.bazel**:
```python
module(
    name = "your_library_vendor",
    version = "1.0.0",
    compatibility_level = 1,
)

bazel_dep(name = "rules_cc", version = "0.2.14")
bazel_dep(name = "platforms", version = "1.0.0")
bazel_dep(name = "rules_foreign_cc", version = "0.15.1")

bazel_dep(name = "eros_forge")
local_path_override(
    module_name = "eros_forge",
    path = "../../forge",
)

# Use extension to import source code
library = use_extension("//:extensions.bzl", "library_ext")
use_repo(library, "library_source")
```

**BUILD.bazel**:
```python
load("@eros_forge//bazel:cmake_forge.bzl", "cmake_forge")
load("//:cmake/library_options.bzl", "LIBRARY_CMAKE_OPTIONS")

cmake_forge(
    name = "library",
    lib_source = "@library_source//:all",
    lib_name = "library_core",
    out_shared_libs = ["liblibrary_core.so"],
    cache_entries = LIBRARY_CMAKE_OPTIONS,
    visibility = ["//visibility:public"],
)
```

### 方案 B: 使用本地源码

适用于：源码已在本地目录的场景

**MODULE.bazel**:
```python
module(
    name = "your_library_vendor",
    version = "1.0.0",
    compatibility_level = 1,
)

bazel_dep(name = "eros_forge")
local_path_override(
    module_name = "eros_forge",
    path = "../../forge",
)
```

**BUILD.bazel**:
```python
load("@eros_forge//bazel:cmake_forge.bzl", "cmake_forge")

filegroup(
    name = "source_files",
    srcs = glob(
        ["**/*.cpp", "**/*.h", "**/*.hpp", "CMakeLists.txt"],
        exclude = ["**/BUILD", "**/BUILD.bazel"],
    ),
    visibility = ["//visibility:private"],
)

cmake_forge(
    name = "library",
    lib_source = ":source_files",
    lib_name = "library_core",
    out_shared_libs = ["liblibrary_core.so"],
    visibility = ["//visibility:public"],
)
```

## 关键技术点

### 1. 处理子模块的 BUILD 文件

**问题**：如果 Git 仓库包含子模块，且子模块有 `BUILD.bazel` 文件，Bazel 的 `glob` 会跳过这些目录。

**解决方案**：在 `repository_rule` 中把子目录的 BUILD 文件**重命名**为 `.bak`
（而不是 `find ... -delete`），避免误删用户源码中有效的 BUILD 文件，且便于审计恢复：

```python
rctx.execute([
    "bash", "-c",
    "find . -path ./.git -prune -o \\( -name BUILD -o -name BUILD.bazel \\) -type f -print0 "
    "| while IFS= read -r -d '' f; do mv \"$f\" \"$f.bak\"; done",
])
```

> 只处理 vendored 子目录中的 BUILD 文件；不要删除项目自身的 BUILD 文件。

### 2. 为什么不能用 `git_repository`

在 bzlmod 中，`git_repository` 的限制：
- 不执行 `git submodule update`（需用 `git clone --recurse-submodules`）
- 无法处理已提交子模块代码但保留 `BUILD.bazel` 的仓库
- Bazel 的 `glob` 会跳过有 `BUILD.bazel` 的子目录

**必须使用 `repository_rule`** 来：
- 完全控制 clone 过程（含子模块）
- 重命名（而非删除）冲突的 BUILD 文件
- 创建统一的 filegroup

### 3. CMake 配置选项

**cmake/library_options.bzl**:
```python
LIBRARY_CMAKE_OPTIONS = {
    "BUILD_SHARED_LIBS": "ON",
    "BUILD_TESTING": "OFF",
    # 注意：CMAKE_BUILD_TYPE 由 cmake_forge 宏通过 --config=debug/release 控制，
    # 在 cache_entries 中设置会被覆盖。此处不设置 CMAKE_BUILD_TYPE。
    # 其他库特定选项
}
```

### 4. 跨平台编译

使用 `--config` 参数选择目标平台：
```bash
# Linux x86_64
bazel build //:library --config=linux_x86_64

# Linux ARM64
bazel build //:library --config=linux_arm64

# Cross-compile from x86_64 to ARM64
bazel build //:library --config=linux_x86_64_cross_arm64
```

## 使用第三方库

在应用的 `MODULE.bazel` 中：
```python
module(
    name = "your_application",
    version = "1.0.0",
)

bazel_dep(name = "your_library_vendor")
local_path_override(
    module_name = "your_library_vendor",
    path = "../thirdparty/your_library",
)

bazel_dep(name = "eros_forge")
local_path_override(
    module_name = "eros_forge",
    path = "../forge",
)
```

**BUILD.bazel**:
```python
cc_binary(
    name = "app",
    srcs = ["main.cpp"],
    deps = [
        "@your_library_vendor//:library",
    ],
)
```

## 常见问题

### Q: 为什么需要创建 `:all` filegroup？

A: `cmake_forge` 的 `lib_source` 参数需要 Bazel label。filegroup 提供统一的源码引用点。

### Q: 如何处理 Protobuf 等依赖？

A: 在 `cache_entries` 中指定系统路径：
```python
cache_entries = {
    "Protobuf_PROTOC_EXECUTABLE": "/usr/bin/protoc",
    "Protobuf_INCLUDE_DIR": "/usr/include",
}
```

### Q: 运行时找不到共享库怎么办？

A: 设置 `LD_LIBRARY_PATH`：
```bash
export LD_LIBRARY_PATH=bazel-bin/library/lib:$LD_LIBRARY_PATH
```

## 完整示例

参考以下示例项目：
- `eros/thirdparty/eclipse-ecal-vendor/` - eCAL 中间件集成
- `eros/playground/hello_cmake/` - 简单 CMake 项目
- `eros/playground/hello_eclipse_ecal/` - 使用 eCAL 的应用

## 总结

**最佳实践要点**：
1. 使用 `repository_rule` + `module_extension` 导入外部源码
2. 删除子目录的 BUILD 文件避免冲突
3. 创建 `:all` filegroup 统一引用源码
4. 使用 `cmake_forge` 简化 CMake 构建
5. 通过 `cache_entries` 配置 CMake 选项
6. 使用 `--config` 进行跨平台编译

这种方案提供了：
- ✅ 灵活的源码管理
- ✅ 干净的 Bazel 集成
- ✅ 可复用的构建配置
- ✅ 跨平台支持
