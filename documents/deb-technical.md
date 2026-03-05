# pkg_eros_deb 技术文档

## 架构设计

### 核心组件

```
pkg_eros_deb (macro)
├── eros_deb_version (rule)
│   └── 生成版本文件
├── pkg_deb (amd64)
│   └── x86_64 架构 deb 包
├── pkg_deb (arm64)
│   └── ARM64 架构 deb 包
└── native.alias
    └── 根据平台自动选择
```

### 架构检测机制

使用 Bazel 的 `select()` 和平台约束实现自动架构选择：

```python
native.alias(
    name = name,
    actual = select({
        "@platforms//cpu:x86_64": name + "_amd64",
        "@platforms//cpu:arm64": name + "_arm64",
        "//conditions:default": name + "_amd64",
    }),
)
```

平台配置通过 `.bazelrc` 中的 `--platforms` 参数指定：

```bash
build:x86_64 --platforms=@eros_forge//bazel/toolchain:linux_x86_64
build:arm64  --platforms=@eros_forge//bazel/toolchain:linux_arm64
```

## 版本生成规则

### eros_deb_version

自定义规则用于生成版本文件，支持三种优先级：

1. **显式版本** - 通过 `version` 属性指定
2. **命令行定义** - 通过 `--define=DEB_VERSION=x.x.x`
3. **默认版本** - `0.1.0`

实现代码：

```python
def _eros_deb_version_impl(ctx):
    output = ctx.actions.declare_file(ctx.attr.name + ".txt")

    if ctx.attr.version:
        version = ctx.attr.version
    else:
        define_version = ctx.var.get("DEB_VERSION", "")
        version = define_version if define_version else "0.1.0"

    ctx.actions.write(output = output, content = version)
    return [DefaultInfo(files = depset([output]))]
```

## 宏展开逻辑

`pkg_eros_deb` 宏展开后生成以下规则：

```python
# 1. 版本文件规则
eros_deb_version(
    name = "<name>_version",
    version = <version>,
)

# 2. amd64 deb 包
pkg_deb(
    name = "<name>_amd64",
    architecture = "amd64",
    version_file = ":<name>_version",
    ...
)

# 3. arm64 deb 包
pkg_deb(
    name = "<name>_arm64",
    architecture = "arm64",
    version_file = ":<name>_version",
    ...
)

# 4. 平台选择别名
alias(
    name = "<name>",
    actual = select({...}),
)
```

## 依赖关系

### 外部依赖

- `@rules_pkg//pkg:deb.bzl` - Debian 包构建规则
- `@platforms//cpu:*` - 平台约束定义

### 模块配置

在 `MODULE.bazel` 中声明：

```python
bazel_dep(name = "rules_pkg", version = "1.0.1")
```

## 构建流程

### 构建命令执行流程

```
bazel build --config=arm64 //:my_deb
                │
                ▼
        解析 --platforms=@eros_forge//bazel/toolchain:linux_arm64
                │
                ▼
        平台约束匹配 @platforms//cpu:arm64
                │
                ▼
        alias 选择 //:my_deb_arm64
                │
                ▼
        构建 arm64 架构的 deb 包
```

## 扩展接口

### 支持的 pkg_deb 参数

`pkg_eros_deb` 透传以下参数到 `pkg_deb`：

- 脚本：`preinst`, `postinst`, `prerm`, `postrm`
- 依赖：`depends`, `suggests`, `enhances`, `breaks`, `conflicts`, `replaces`, `provides`, `recommends`
- 配置：`conffiles`
- 其他：`built_using` 等

### 添加新架构支持

如需支持新架构（如 `riscv64`）：

1. 在 `pkg_eros_deb` 中添加新的 `pkg_deb` 规则
2. 更新 `select()` 语句添加新平台映射
3. 在 `bazelrc` 中添加对应的 `--platforms` 配置

## 注意事项

1. **平台检测** - 依赖 `--platforms` 参数，仅 `--cpu` 不足以触发正确的架构选择
2. **版本缓存** - Bazel 会缓存版本文件，修改 `--define=DEB_VERSION` 后需要 `--nocache` 或 `bazel clean`
3. **标签可见性** - 架构特定的目标（`_amd64`, `_arm64`）标记为 `manual`，避免被通配符构建
