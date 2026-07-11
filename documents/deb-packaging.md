# EROS Debian Packaging

EROS Forge 提供的 Debian 包构建插件，支持自动架构检测和多平台打包。

## 快速开始

### 1. 在 BUILD.bazel 中引入

```python
load("@eros_forge//bazel:deb.bzl", "pkg_eros_deb")

pkg_eros_deb(
    name = "my_package_deb",
    package_name = "my-package",
    data = ":my_data_tar",
    description = "My package description",
    maintainer = "Team <team@example.com>",
)
```

### 2. 构建 deb 包

`pkg_eros_deb` 生成**单个** `pkg_deb` 目标，其架构根据目标平台的 cpu 约束自动选择
（`x86_64` -> `amd64`，`arm64` -> `arm64`），无需也**不会**生成多余的 `_amd64`/`_arm64`
目标污染 `bazel query //...`。

```bash
# 构建 x86_64 (amd64) 架构
bazel build --config=linux_x86_64 //:my_package_deb

# 构建 arm64 架构
bazel build --config=linux_arm64 //:my_package_deb

# 交叉编译到 ARM64（同样得到 arm64 deb）
bazel build --config=linux_x86_64_cross_arm64 //:my_package_deb

# 指定版本号
bazel build --config=linux_x86_64 //:my_package_deb --define=DEB_VERSION=1.2.3
# 或通过环境变量（需 bazelrc 的 build --action_env=DEB_VERSION，Forge 已默认提供）
DEB_VERSION=1.2.3 bazel build --config=linux_x86_64 //:my_package_deb
```

如需在一个 workspace 中显式生成多个架构的 deb 目标，使用
`pkg_eros_deb_multiarch`，它会为每个架构生成一个带 `manual` 标签的 `pkg_deb`
（如 `my_package_deb_amd64`、`my_package_deb_arm64`）：

```python
pkg_eros_deb_multiarch(
    name = "my_package_deb",
    package_name = "my-package",
    data = ":my_data_tar",
    description = "My package description",
    maintainer = "Team <team@example.com>",
    architectures = ["amd64", "arm64"],
)
# bazel build //:my_package_deb_arm64 --config=linux_arm64
```

## 完整示例

### 示例 1：打包动态库

```python
load("@eros_forge//bazel:deb.bzl", "pkg_eros_deb", "pkg_eros_tar")

# 准备数据文件（自动提取 output_group）
pkg_eros_tar(
    name = "my_package_data",
    srcs = ["//include/cytoskeleton/module"],
    output_group = "dynamic_library",
    package_dir = "/opt/eros/lib",
    strip_prefix = "include/cytoskeleton/module",  # 剥离路径前缀
)

# 创建 deb 包
pkg_eros_deb(
    name = "my_package_deb",
    package_name = "my-package",
    data = ":my_package_data",
    description = "My awesome package",
    maintainer = "EROS Team <team@example.com>",
    homepage = "https://example.com",
    section = "libs",
    priority = "optional",
    depends = ["libc6"],
)
```

### 示例 2：打包可执行文件

```python
load("@eros_forge//bazel:deb.bzl", "pkg_eros_deb", "pkg_eros_tar")

# 准备数据文件
pkg_eros_tar(
    name = "my_app_data",
    srcs = [":my_executable"],
    package_dir = "/opt/eros/bin",
)

# 创建 deb 包
pkg_eros_deb(
    name = "my_app_deb",
    package_name = "my-application",
    data = ":my_app_data",
    description = "My application",
    maintainer = "EROS Team <team@example.com>",
    section = "utils",
    priority = "optional",
    depends = ["my-library"],
)
```

## 参数说明

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `name` | string | 是 | - | 规则名称 |
| `package_name` | string | 是 | - | deb 包名称 |
| `data` | label | 是 | - | pkg_tar 目标 |
| `description` | string | 是 | - | 包描述 |
| `maintainer` | string | 是 | - | 维护者信息 |
| `version` | string | 否 | - | 版本号，可被 `--define=DEB_VERSION` 覆盖 |
| `homepage` | string | 否 | "https://example.com" | 主页 URL |
| `section` | string | 否 | "libs" | Debian 分类 |
| `priority` | string | 否 | "optional" | 优先级 |
| `depends` | list | 否 | - | 依赖包列表 |
| `preinst` | label | 否 | - | 安装前脚本 |
| `postinst` | label | 否 | - | 安装后脚本 |
| `prerm` | label | 否 | - | 卸载前脚本 |
| `postrm` | label | 否 | - | 卸载后脚本 |

## pkg_eros_tar

用于打包文件并自动提取指定 `output_group` 的宏。

### 使用示例

```python
load("@eros_forge//bazel:deb.bzl", "pkg_eros_tar")

# 示例 1：提取动态库并打包
pkg_eros_tar(
    name = "my_data",
    srcs = ["//include/cytoskeleton/module"],
    output_group = "dynamic_library",  # 提取动态库
    package_dir = "/opt/eros/lib",
    strip_prefix = "include/cytoskeleton/module",  # 剥离路径前缀
)

# 示例 2：直接打包可执行文件
pkg_eros_tar(
    name = "my_app",
    srcs = [":hello_cytoskeleton"],
    package_dir = "/opt/eros/bin",
)
```

### 参数说明

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `name` | string | 是 | - | 规则名称 |
| `srcs` | list | 是 | - | 源文件标签列表 |
| `output_group` | string | 是 | - | 要提取的 output_group |
| `package_dir` | string | 否 | - | 包内目标目录 |
| `extension` | string | 否 | "tar.gz" | 压缩格式 |
| `mode` | string | 否 | "0755" | 默认文件权限 |
| `strip_prefix` | string | 否 | "." | 路径前缀剥离 |
| `modes` | dict | 否 | - | 特定文件权限 |
| `owner` | string | 否 | - | 默认所有者 (uid:gid) |
| `symlinks` | dict | 否 | - | 符号链接定义 |

支持所有 `pkg_tar` 的参数。

## 版本控制

版本号优先级（从高到低）：

1. `version` 参数显式指定
2. `DEB_VERSION` 环境变量（需 bazelrc 的 `build --action_env=DEB_VERSION`，Forge 已默认提供）
3. `--define=DEB_VERSION=x.x.x` 命令行参数
4. 默认值 `0.1.0`

> 注意：环境变量路径不纳入 Bazel action 缓存键，仅修改 `DEB_VERSION` 可能不会重新触发
> 构建。需要确定性、缓存正确的版本控制时，优先使用 `--define=DEB_VERSION=x.x.x`
>（define 变更会使配置失效）或显式传入 `version = ...`。

## 工作原理

`pkg_eros_deb` 宏会自动：

1. 创建版本文件生成规则（`eros_deb_version`，按上述优先级解析版本）
2. 创建**单个** `pkg_deb` 规则，其 `architecture` 通过 `select()` 根据目标平台的
   `@platforms//cpu` 约束自动选择（`x86_64` -> `amd64`，`arm64` -> `arm64`，
   其他 -> `all`）

生成的目标：

- `//:<name>` - 自动选择架构的单个 deb 包

`pkg_eros_deb_multiarch` 宏会自动：

1. 创建版本文件生成规则
2. 为 `architectures` 列表中的每个架构创建一个带 `manual` 标签的 `pkg_deb`
   （如 `//:<name>_amd64`、`//:<name>_arm64`）
3. 创建一个 `<name>` filegroup 汇总所有架构目标

`pkg_eros_tar` 宏会自动：

1. 创建内部 `filegroup` 提取指定的 `output_group`
2. 创建 `pkg_tar` 打包文件
