# EROS Forge - 统一构建系统

Forge 是 EROS 项目的统一构建系统，基于 Bazel 9.0，提供跨平台编译、交叉编译工具链管理和统一的构建配置。

## 目录

- [快速开始](#快速开始)
- [环境初始化](#环境初始化)
- [构建配置](#构建配置)
- [交叉编译](#交叉编译)
- [部署与运行](#部署与运行)
- [工具链配置](#工具链配置)

## 快速开始

### 在项目中集成 Forge

在你的项目 `MODULE.bazel` 中添加：

```python
# MODULE.bazel
local_path_override(
    module_name = "eros_forge",
    path = "/path/to/eros/forge",
)

bazel_dep(name = "eros_forge", version = "0.1.0")
```

然后在项目的 `.bazelrc` 中导入 Forge 配置：

```bash
# .bazelrc
try-import %workspace%/../../forge/bazel/bazelrc
```

### 基本构建命令

```bash
# 编译项目
bazel build //:all

# 使用 release 配置编译（优化级别 -O3）
bazel build //:all --config=release

# 交叉编译到 ARM64
bazel build //:all --config=cross_arm64
```

## 环境初始化

### 1. 安装 Bazel 9.0

#### Ubuntu/Debian

```bash
# 添加 Bazel 官方 APT 仓库
curl -fsSL https://bazel.build/bazel-release.pub.gpg | gpg --dearmor > bazel.gpg
sudo mv bazel.gpg /etc/apt/trusted.gpg.d/
echo "deb [arch=amd64] https://storage.googleapis.com/bazel-apt stable jdk1.8" | sudo tee /etc/apt/sources.list.d/bazel.list

# 安装 Bazel
sudo apt update && sudo apt install bazel-9.0.0
sudo ln -sf /usr/bin/bazel-9.0.0 /usr/local/bin/bazel

# 验证安装
bazel --version
```

#### macOS

```bash
# 使用 Homebrew 安装
brew install bazel@9

# 验证安装
bazel --version
```

#### 使用 Bazelisk（推荐）

Bazelisk 是 Bazel 的启动器，会自动下载和管理 Bazel 版本：

```bash
# macOS
brew install bazelisk

# Linux
wget https://github.com/bazelbuild/bazelisk/releases/latest/download/bazelisk-linux-amd64
chmod +x bazelisk-linux-amd64
sudo mv bazelisk-linux-amd64 /usr/local/bin/bazel

# 验证安装
bazel --version
```

### 2. 安装交叉编译工具链（ARM64）

#### Ubuntu/Debian

```bash
# 安装 AArch64 交叉编译工具链
sudo apt update
sudo apt install gcc-aarch64-linux-gnu g++-aarch64-linux-gnu binutils-aarch64-linux-gnu

# 验证安装
aarch64-linux-gnu-gcc --version
aarch64-linux-gnu-g++ --version
```

#### macOS

```bash
# 使用 Homebrew 安装交叉编译工具链
brew install aarch64-elf-gcc aarch64-elf-binutils

# 或者使用更完整的工具链
brew install osx-cross/aarch64-embedded/gcc-aarch64-embedded
```

#### 自定义 Glibc（可选）

如果目标机的 glibc 版本较低（如 Ubuntu 18.04 的 glibc 2.27），需要在宿主机安装对应版本的 glibc：

```bash
# 下载并安装 glibc 2.27 for ARM64
cd /tmp
wget https://ftp.gnu.org/gnu/glibc/glibc-2.27.tar.gz
tar xzf glibc-2.27.tar.gz
cd glibc-2.27

# 交叉编译并安装到 /opt/eros
mkdir build-arm64 && cd build-arm64
../configure --host=aarch64-linux-gnu --prefix=/opt/eros \
    --build=x86_64-linux-gnu \
    CC=aarch64-linux-gnu-gcc \
    CXX=aarch64-linux-gnu-g++

make -j$(nproc)
sudo make install

# 验证安装
ls -la /opt/eros/lib/ld-linux-aarch64.so.1
```

**注意**：Forge 的交叉编译配置会自动使用 `/opt/eros/lib` 作为自定义 glibc 路径。

### 3. 验证环境

```bash
# 检查 Bazel 版本
bazel --version  # 应该显示 bazel 9.0.x

# 检查交叉编译工具链
aarch64-linux-gnu-gcc --version
aarch64-linux-gnu-g++ --version

# 检查 glibc（如果安装了自定义版本）
/opt/eros/lib/libc.so.6  # 应该显示 glibc 版本信息
```

## 构建配置

### 平台配置

Forge 提供以下构建配置：

| 配置 | 说明 | 使用场景 |
|------|------|----------|
| `--config=x86_64` | x86_64 原生编译 | 在 x86_64 主机上编译 x86_64 程序 |
| `--config=arm64` | ARM64 原生编译 | 在 ARM64 主机上编译 ARM64 程序 |
| `--config=cross_arm64` | 交叉编译到 ARM64 | 在 x86_64 主机上编译 ARM64 程序 |

### 构建模式

| 模式 | 说明 | 优化级别 |
|------|------|----------|
| `--config=debug` | 调试模式 | 无优化，包含调试信息 |
| `--config=release` | 发布模式 | `-O3` 优化，禁用断言 |

### 组合使用示例

```bash
# 在 x86_64 主机上交叉编译 ARM64 release 版本
bazel build //:my_app --config=cross_arm64 --config=release

# 在 x86_64 主机上编译本地 debug 版本
bazel build //:my_app --config=x86_64 --config=debug

# 在 ARM64 主机上编译本地 release 版本
bazel build //:my_app --config=arm64 --config=release
```

## 交叉编译

### 交叉编译 ARM64

使用 `--config=cross_arm64` 配置进行交叉编译：

```bash
# 编译项目
bazel build //:all --config=cross_arm64

# 编译特定目标
bazel build //src:my_app --config=cross_arm64
```

### 自动嵌入动态链接器和库搜索路径

`--config=cross_arm64` 配置会自动配置以下链接参数：

1. **动态链接器**：`/opt/eros/lib/ld-linux-aarch64.so.1`
   - 指定程序运行时使用的动态链接器路径
   - 通过 `--linkopt=-Wl,--dynamic-linker=/opt/eros/lib/ld-linux-aarch64.so.1` 设置

2. **运行时库搜索路径（RUNPATH）**：`/opt/eros/lib`
   - 指定程序运行时搜索共享库的路径
   - 通过 `--linkopt=-Wl,--rpath=/opt/eros/lib` 设置
   - 程序会自动在此路径下查找依赖的 `.so` 文件

这意味着：
- 编译的程序会自动使用指定的动态链接器
- 运行时会自动从 `/opt/eros/lib` 查找共享库
- 无需手动指定 `LD_LIBRARY_PATH` 或使用 `patchelf`

### 验证编译结果

使用 `readelf` 验证动态链接器和库搜索路径是否正确设置：

```bash
# 检查动态链接器
readelf -p .interp bazel-bin/my_app | grep interp

# 输出应该显示：
# [     0]  /opt/eros/lib/ld-linux-aarch64.so.1

# 检查运行时库搜索路径
readelf -d bazel-bin/my_app | grep -E "(RPATH|RUNPATH)"

# 输出应该显示：
# 0x000000000000001d (RUNPATH)            Library runpath: [/opt/eros/lib]
```

### 为什么需要自定义 glibc？

目标机可能使用较旧版本的 glibc（如 Ubuntu 18.04 的 glibc 2.27），而宿主机使用较新版本（如 Ubuntu 24.04 的 glibc 2.39）。直接使用宿主机的 glibc 编译会导致：

- 程序在目标机上无法运行（glibc 版本不兼容）
- 出现类似 `GLIBC_2.28 not found` 的错误

通过使用自定义 glibc 并嵌入到程序中，可以确保：
- 程序使用与目标机兼容的 glibc 版本
- 无需在目标机上安装额外的库
- 提高程序的可移植性和可靠性

## 部署与运行

### 1. 准备目标机环境

**在目标机上创建 `/opt/eros/lib` 目录并复制必要的动态库**：

交叉编译完成后，需要将以下动态库复制到目标机的 `/opt/eros/lib` 目录：

#### 必需的 glibc 库文件

```bash
# 基本系统库
libc.so.6              # C 标准库
libm.so.6              # 数学库
libpthread.so.0        # POSIX 线程库
libdl.so.2             # 动态加载库
librt.so.1             # 实时库
ld-linux-aarch64.so.1  # 动态链接器（必需）
```

#### 必需的编译器运行时库

```bash
# C++ 运行时库
libstdc++.so.6         # C++ 标准库（需要较新版本，支持 GLIBCXX_3.4.30+）
libgcc_s.so.1          # GCC 运行时库
```

#### 复制示例

```bash
# 在目标机上创建目录
ssh user@target-board "sudo mkdir -p /opt/eros/lib"

# 从宿主机复制库文件到目标机
# 注意：libstdc++ 需要较新版本以支持 C++20 特性
scp /usr/aarch64-linux-gnu/lib/ld-linux-aarch64.so.1 \
    /usr/aarch64-linux-gnu/lib/libc.so.6 \
    /usr/aarch64-linux-gnu/lib/libm.so.6 \
    /usr/aarch64-linux-gnu/lib/libpthread.so.0 \
    /usr/aarch64-linux-gnu/lib/libdl.so.2 \
    /usr/aarch64-linux-gnu/lib/librt.so.1 \
    /usr/lib/aarch64-linux-gnu/libstdc++.so.6.0.33 \
    /usr/lib/aarch64-linux-gnu/libgcc_s.so.1 \
    user@target-board:/opt/eros/lib/

# 在目标机上创建 libstdc++.so.6 符号链接
ssh user@target-board "cd /opt/eros/lib && ln -sf libstdc++.so.6.0.33 libstdc++.so.6"

# 设置正确的权限
ssh user@target-board "chmod 755 /opt/eros/lib/*.so*"
```

**注意**：
- 库文件路径可能因发行版而异，请根据实际情况调整
- 确保复制的库版本与目标机兼容
- **libstdc++ 版本要求**：如果程序使用 C++20 特性，需要 libstdc++.so.6.0.30 或更高版本
- 可以使用 `strings /usr/lib/aarch64-linux-gnu/libstdc++.so.6 | grep GLIBCXX` 查看支持的版本
- 如果目标机已有兼容版本的库，可以跳过相应步骤
- **静态链接优势**：使用 `linkstatic = True` 编译的程序，Boost 等第三方库已静态链接，无需额外复制

### 2. 传输程序到目标机

```bash
# 使用 scp 传输
scp bazel-bin/my_app user@target-board:/opt/apps/

# 或使用 rsync
rsync -avz bazel-bin/my_app user@target-board:/opt/apps/
```

### 3. 在目标机上运行

```bash
# SSH 登录到目标机
ssh user@target-board

# 进入程序目录
cd /opt/apps

# 赋予执行权限
chmod +x my_app

# 运行程序
./my_app
```

**注意**：由于程序已经嵌入了动态链接器和库搜索路径，无需额外配置即可运行。

### 4. 验证程序信息

```bash
# 检查程序架构
file my_app
# 输出应该显示：ELF 64-bit LSB executable, ARM aarch64

# 检查依赖的共享库
ldd my_app
# 显示程序依赖的所有共享库

# 检查动态链接器
readelf -l my_app | grep INTERP
# 显示程序使用的动态链接器路径
```

### 5. 故障排查

如果程序无法运行，检查以下信息：

```bash
# 检查 glibc 版本
/lib/ld-linux-aarch64.so.1 --version

# 检查程序需要的符号
readelf -s my_app | grep GLIBC

# 使用 strace 跟踪程序执行
strace ./my_app
```

## 工具链配置

### 工具链架构

Forge 的工具链配置位于 `bazel/toolchain/` 目录：

```
bazel/toolchain/
├── BUILD.bazel              # 工具链定义
├── cc_toolchain_config.bzl  # 工具链配置规则
└── bazelrc                  # Bazel 配置
```

### 工具链配置详情

#### 1. 平台定义（BUILD.bazel）

定义三个平台：

- `linux_x86_64`：x86_64 原生平台
- `linux_arm64`：ARM64 原生平台
- `linux_arm64_cross`：ARM64 交叉编译平台

#### 2. 工具链配置（cc_toolchain_config.bzl）

配置以下内容：

- **编译器路径**：gcc, g++, ld, ar 等工具的路径
- **头文件路径**：C++ 标准库和系统头文件的搜索路径
- **编译特性**：
  - `c++20`：启用 C++20 标准
  - `supports_pic`：支持位置无关代码
  - `supports_dynamic_linker`：支持动态链接器配置

#### 3. Bazel 配置（bazelrc）

定义构建配置：

```bazel
# 平台配置
build:x86_64 --platforms=@eros_forge//bazel/toolchain:linux_x86_64
build:arm64 --platforms=@eros_forge//bazel/toolchain:linux_arm64
build:cross_arm64 --platforms=@eros_forge//bazel/toolchain:linux_arm64_cross

# 交叉编译链接参数
build:cross_arm64 --linkopt=-Wl,--rpath=/opt/eros/lib
build:cross_arm64 --linkopt=-Wl,--dynamic-linker=/opt/eros/lib/ld-linux-aarch64.so.1

# 发布版本配置
build:release --compilation_mode=opt
build:release --copt=-O3
build:release --copt=-DNDEBUG
```

### 自定义工具链

如果需要添加新的工具链（如 RISC-V），在 `BUILD.bazel` 中添加：

```python
cc_toolchain_config(
    name = "linux_riscv64_config",
    cpu = "riscv64",
    compiler = "gcc",
    target_system_name = "riscv64-linux-gnu",
    target_libc = "glibc_2.27",
    abi_version = "riscv64",
    abi_libc_version = "2.27",
    toolchain_identifier = "riscv64-linux-gnu-toolchain",
    host_system_name = "x86_64-linux-gnu",
    gcc_path = "/usr/bin/riscv64-linux-gnu-gcc",
    gxx_path = "/usr/bin/riscv64-linux-gnu-g++",
    # ... 其他配置
)

cc_toolchain(
    name = "cc-toolchain-riscv64",
    toolchain_config = ":linux_riscv64_config",
    # ...
)

toolchain(
    name = "cc-toolchain-riscv64-linux-cross",
    exec_compatible_with = [
        "@platforms//os:linux",
        "@platforms//cpu:x86_64",
    ],
    target_compatible_with = [
        "@platforms//os:linux",
        "@platforms//cpu:riscv64",
    ],
    toolchain = ":cc-toolchain-riscv64",
    toolchain_type = "@rules_cc//cc:toolchain_type",
)
```

然后在 `bazelrc` 中添加配置：

```bazel
build:cross_riscv64 --platforms=@eros_forge//bazel/toolchain:linux_riscv64_cross
build:cross_riscv64 --linkopt=-Wl,--rpath=/opt/eros/lib
build:cross_riscv64 --linkopt=-Wl,--dynamic-linker=/opt/eros/lib/ld-linux-riscv64-lp64d.so.1
```

## 常见问题

### Q: 为什么交叉编译时需要自定义 glibc？

A: 目标机可能使用较旧版本的 glibc。使用自定义 glibc 可以确保程序在目标机上兼容运行，避免版本不匹配问题。

### Q: 如何在不使用自定义 glibc 的情况下交叉编译？

A: 如果目标机的 glibc 版本与宿主机兼容，可以修改 `bazelrc` 中的 `--linkopt` 参数，使用系统默认的 glibc 路径。

### Q: 编译失败，提示找不到头文件？

A: 检查是否正确安装了交叉编译工具链，以及工具链配置中的 `cxx_builtin_include_directories` 是否正确。

### Q: 程序在目标机上运行时报错 "No such file or directory"？

A: 这通常是因为动态链接器路径不正确。使用 `readelf -l` 检查程序的 INTERP 段，确保动态链接器路径正确。

## 参考资源

- [Bazel 官方文档](https://bazel.build/)
- [Bazel C++ Toolchain 配置](https://bazel.build/extending/cc-toolchain)
- [GCC 交叉编译指南](https://gcc.gnu.org/onlinedocs/gccint/Configure-Terms.html)
- [Glibc 交叉编译](https://sourceware.org/glibc/wiki/Testing/Builds)
