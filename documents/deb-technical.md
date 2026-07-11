# pkg_eros_deb 技术文档

## 架构设计

### 核心组件

```
pkg_eros_deb (macro)
├── eros_deb_version (rule)
│   └── 生成版本文件（优先级：version 属性 > DEB_VERSION 环境变量 > --define > 默认值）
└── pkg_deb (single, architecture = select({@platforms//cpu:...}))
    └── 根据目标平台 cpu 约束自动选择 amd64 / arm64 / all
```

### 架构检测机制

宏生成**单个** `pkg_deb` 目标，其 `architecture` 属性是一个 `select()`，根据目标
平台的 `@platforms//cpu` 约束选择架构，不再为每个架构生成独立目标：

```python
def _eros_deb_architecture(architecture):
    if architecture:
        return architecture  # 显式指定时直接使用
    return select({
        "@platforms//cpu:x86_64": "amd64",
        "@platforms//cpu:arm64": "arm64",
        "//conditions:default": "all",
    })

pkg_deb(
    name = name,
    architecture = _eros_deb_architecture(architecture),
    ...
)
```

> 架构仅由 CPU 决定（glibc 变体不影响 deb 架构），因此只匹配 `@platforms//cpu`，
> 不匹配自定义的 `glibc_type` 约束。

平台配置通过 `.bazelrc` 中的 `--platforms` 参数指定（配置名与 bazelrc 一致）：

```bash
build:linux_x86_64 --platforms=@eros_forge//bazel/toolchain:linux_x86_64_platform
build:linux_arm64  --platforms=@eros_forge//bazel/toolchain:linux_arm64_platform
```

## 版本生成规则

### eros_deb_version

自定义规则用于生成版本文件，支持四种优先级（从高到低）：

1. **显式版本** - 通过 `version` 属性指定
2. **环境变量** - `DEB_VERSION`（需 bazelrc 的 `build --action_env=DEB_VERSION`，
   Forge 已默认提供）
3. **命令行定义** - 通过 `--define=DEB_VERSION=x.x.x`
4. **默认版本** - `0.1.0`

Bazel 9 移除了普通规则分析期的 `ctx.os.environ` 访问，因此环境变量在 action 执行期
读取（`use_default_shell_env = True` 使 action 能看到继承的 `DEB_VERSION`）：

```python
def _eros_deb_version_impl(ctx):
    output = ctx.actions.declare_file(ctx.attr.name + ".txt")
    attr_version = ctx.attr.version
    define_version = ctx.var.get("DEB_VERSION", "")
    ctx.actions.run_shell(
        outputs = [output],
        arguments = [attr_version, define_version, output.path],
        command = """
set -eu
ATTR_VERSION="$1"; DEFINE_VERSION="$2"; OUTPUT="$3"
if [ -n "$ATTR_VERSION" ]; then VERSION="$ATTR_VERSION"
elif [ -n "${DEB_VERSION:-}" ]; then VERSION="$DEB_VERSION"
elif [ -n "$DEFINE_VERSION" ]; then VERSION="$DEFINE_VERSION"
else VERSION="0.1.0"; fi
printf '%s' "$VERSION" > "$OUTPUT"
""",
        use_default_shell_env = True,
    )
    return [DefaultInfo(files = depset([output]))]
```

> 注意：环境变量路径不纳入 Bazel action 缓存键，仅修改 `DEB_VERSION` 可能不会重新
> 触发构建。需要确定性版本控制时优先使用 `--define=DEB_VERSION=x.x.x`。

## 宏展开逻辑

`pkg_eros_deb` 宏展开后生成以下规则：

```python
# 1. 版本文件规则
eros_deb_version(
    name = "<name>_version",
    version = <version>,
)

# 2. 单个 deb 包（架构由平台约束自动选择）
pkg_deb(
    name = "<name>",
    architecture = select({
        "@platforms//cpu:x86_64": "amd64",
        "@platforms//cpu:arm64": "arm64",
        "//conditions:default": "all",
    }),
    version_file = ":<name>_version",
    ...
)
```

如需在一个 workspace 中显式生成多个架构目标，使用 `pkg_eros_deb_multiarch`，
它会生成 `<name>_amd64`、`<name>_arm64`（均带 `manual` 标签）和一个汇总 filegroup
`<name>`。

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
bazel build --config=linux_arm64 //:my_deb
                 │
                 ▼
         解析 --platforms=@eros_forge//bazel/toolchain:linux_arm64_platform
                 │
                 ▼
         平台约束匹配 @platforms//cpu:arm64
                 │
                 ▼
         pkg_deb 的 architecture select() 选中 "arm64"
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

如需支持新架构（如 `riscv64`），在 `_eros_deb_architecture` 的 `select()` 中添加新的
cpu 映射即可（deb 架构仅由 CPU 决定）：

```python
return select({
    "@platforms//cpu:x86_64": "amd64",
    "@platforms//cpu:arm64": "arm64",
    "@platforms//cpu:riscv64": "riscv64",
    "//conditions:default": "all",
})
```

若需同时显式构建多个架构，使用 `pkg_eros_deb_multiarch(..., architectures = [...])`。

## 注意事项

1. **平台检测** - 依赖 `--platforms` 参数，仅 `--cpu` 不足以触发正确的架构选择
2. **版本缓存** - `--define=DEB_VERSION` 变更会使配置失效并重新生成版本文件；
   而 `DEB_VERSION` 环境变量不纳入 action 缓存键，仅修改它可能不会重建，需要
   `bazel clean` 或改用 `--define`
3. **目标整洁** - `pkg_eros_deb` 只生成单个目标，不会在 `bazel query //...` 中
   出现多余的 `_amd64`/`_arm64` 目标；多架构需求用 `pkg_eros_deb_multiarch`（其
   per-arch 目标带 `manual` 标签，被通配符排除）
