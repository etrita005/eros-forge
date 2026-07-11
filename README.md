# EROS Forge - 统一构建系统

Forge 是 EROS 项目的统一构建系统，基于 Bazel 9.0，提供跨平台编译、交叉编译工具链管理和统一的构建配置。

## 目录

- [快速开始](#快速开始)
- [环境初始化](#环境初始化)
- [构建配置](#构建配置)
- [交叉编译](#交叉编译)
- [部署与运行](#部署与运行)
- [CMake 集成](#cmake-集成)
- [工具链配置](#工具链配置)
- [Sanitizer 支持](#sanitizer-支持)

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
# 原生编译（自动检测宿主机架构：x86_64 主机 -> linux_x86_64，arm64 主机 -> linux_arm64）
bazel build //:all --config=auto

# 等价地，显式指定平台
bazel build //:all --config=linux_x86_64

# 使用 release 配置编译（优化级别 -O3，符号分离）
bazel build //:all --config=auto --config=release

# 交叉编译到 ARM64
bazel build //:all --config=linux_x86_64_cross_arm64
```

`--config=auto` 通过 Bazel 平台约束（`@platforms//cpu`）自动匹配宿主机架构，并选择
对应的原生 CMake 工具链 / Conan profile，无需显式指定 `--config=linux_<arch>`。交叉
编译场景仍需使用显式的 `linux_*_cross_arm64` 配置。

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

| 配置                                  | 说明              | 宿主机     | 目标机     |
| ----------------------------------- | --------------- | ------- | ------- |
| `--config=auto`                     | 原生编译，自动检测宿主机架构  | 宿主机    | 宿主机    |
| `--config=linux_x86_64`             | x86\_64 原生编译    | x86\_64 | x86\_64 |
| `--config=linux_arm64`              | ARM64 原生编译      | arm64   | arm64   |
| `--config=linux_x86_64_cross_arm64` | 交叉编译            | x86\_64 | arm64   |
| `--config=linux_arm64_cross_arm64`  | 交叉编译（自定义 glibc） | arm64   | arm64   |

### 构建模式

| 模式                 | 说明   | 优化级别          |
| ------------------ | ---- | ------------- |
| `--config=debug`   | 调试模式 | 无优化，包含调试信息    |
| `--config=release` | 发布模式 | `-O3` 优化，符号分离 |

### 组合使用示例

```bash
# 在 x86_64 主机上交叉编译 ARM64 release 版本
bazel build //:my_app --config=linux_x86_64_cross_arm64 --config=release

# 在 x86_64 主机上编译本地 debug 版本
bazel build //:my_app --config=linux_x86_64 --config=debug

# 在 ARM64 主机上编译本地 release 版本
bazel build //:my_app --config=linux_arm64 --config=release

# 在 ARM64 主机上交叉编译（使用自定义 glibc）
bazel build //:my_app --config=linux_arm64_cross_arm64 --config=release
```

## 交叉编译

### 交叉编译 ARM64

使用 `--config=linux_x86_64_cross_arm64` 或 `--config=linux_arm64_cross_arm64` 配置进行交叉编译：

```bash
# 从 x86_64 主机交叉编译到 ARM64
bazel build //:all --config=linux_x86_64_cross_arm64

# 从 ARM64 主机交叉编译到 ARM64（使用自定义 glibc）
bazel build //:all --config=linux_arm64_cross_arm64

# 编译特定目标
bazel build //src:my_app --config=linux_x86_64_cross_arm64
```

### 自动嵌入动态链接器和库搜索路径

交叉编译配置会自动配置以下链接参数（已内置到工具链）：

1. **动态链接器**：`/opt/eros/lib/ld-linux-aarch64.so.1`
   - 指定程序运行时使用的动态链接器路径
2. **运行时库搜索路径（RUNPATH）**：`/opt/eros/lib`
   - 指定程序运行时搜索共享库的路径
   - 程序会自动在此路径下查找依赖的 `.so` 文件
3. **必需的系统库**：
   - `-lstdc++`：C++ 标准库
   - `-lgcc`：GCC 运行时库
   - `-lm`：数学库

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

**在目标机上创建** **`/opt/eros/lib`** **目录并复制必要的动态库**：

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

#### Sanitizer 运行时库（用于测试和调试）

如果程序使用 Sanitizer（ASan、UBSan、TSan），需要复制相应的动态库：

```bash
# Sanitizer 库
libasan.so.4           # AddressSanitizer
libubsan.so.0          # UndefinedBehaviorSanitizer
libtsan.so.0           # ThreadSanitizer
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

# 复制 Sanitizer 库（用于测试和调试）
scp /usr/lib/aarch64-linux-gnu/libasan.so* \
    /usr/lib/aarch64-linux-gnu/libubsan.so* \
    /usr/lib/aarch64-linux-gnu/libtsan.so* \
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

# 如果程序使用 Sanitizer，需要设置 LD_LIBRARY_PATH
LD_LIBRARY_PATH=/opt/eros/lib:$LD_LIBRARY_PATH ./my_app
```

**注意**：

- 由于程序已经嵌入了动态链接器和库搜索路径，无需额外配置即可运行
- 使用 Sanitizer 的程序需要设置 `LD_LIBRARY_PATH=/opt/eros/lib` 以找到 sanitizer 动态库

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
├── BUILD.bazel              # 工具链定义、平台、config_setting
├── cc_toolchain_config.bzl  # cc_toolchain_config 规则实现
├── eros_cc_toolchains.bzl   # 表驱动的 cc_toolchain 宏（按 config_key 实例化）
├── toolchain_data.bzl       # 【自动生成】单一配置表（编译器路径/GCC 版本/sysroot/三元组）
├── generate_files.py        # 单一事实来源：生成 toolchain_data.bzl / conan/*.profile / cmake/*.cmake
├── host_tools.bzl           # module_extension：把宿主编译器/binutils 声明为 cc action 输入
├── cmake/                   # 【自动生成】CMake 工具链文件（linux_*.cmake）
└── conan/                   # 【自动生成】Conan profile（*.profile）
```

> 所有编译器路径、GCC 版本（13）、部署前缀（`/opt/eros`）、目标三元组都在
> `generate_files.py` 中定义**一次**，由其生成 `toolchain_data.bzl`、Conan profile
> 和 CMake 工具链文件。修改工具链时编辑 `generate_files.py` 后重新运行
> `python3 bazel/toolchain/generate_files.py` 即可，无需手工同步多份文件。

### 工具链配置详情

#### 1. 平台定义（BUILD.bazel）

定义两个平台：

- `linux_x86_64_platform`：x86\_64 原生平台
- `linux_arm64_platform`：ARM64 原生/交叉编译平台

#### 2. 工具链配置（cc\_toolchain\_config.bzl）

配置以下内容：

- **编译器路径**：gcc, g++, ld, ar 等工具的路径
- **头文件路径**：C++ 标准库和系统头文件的搜索路径
- **编译特性**：
  - `c++20`：启用 C++20 标准
  - `supports_pic`：支持位置无关代码
  - `supports_dynamic_linker`：支持动态链接器配置
  - `separate_debug_info`：支持符号分离
  - `static_link_cpp_runtimes`：支持静态链接 C++ 运行时

#### 3. 交叉编译链接选项（已内置到工具链）

```python
extra_link_flags = [
    # 库搜索路径
    "-L/usr/lib/gcc/aarch64-linux-gnu/13",
    "-L/usr/aarch64-linux-gnu/lib",
    "-L/usr/lib/aarch64-linux-gnu",
    # 必需的系统库
    "-lstdc++",
    "-lgcc",
    "-lm",
    # 目标机运行时配置
    "-Wl,--rpath=/opt/eros/lib",
    "-Wl,--dynamic-linker=/opt/eros/lib/ld-linux-aarch64.so.1",
]
```

#### 4. Bazel 配置（bazelrc）

定义构建配置：

```bazel
# 平台配置
build:linux_x86_64 --platforms=@eros_forge//bazel/toolchain:linux_x86_64_platform
build:linux_arm64 --platforms=@eros_forge//bazel/toolchain:linux_arm64_platform

# 交叉编译配置
build:linux_x86_64_cross_arm64 --platforms=@eros_forge//bazel/toolchain:linux_arm64_platform
build:linux_x86_64_cross_arm64 --extra_toolchains=@eros_forge//bazel/toolchain:cc-toolchain-x86_64-to-arm64

build:linux_arm64_cross_arm64 --platforms=@eros_forge//bazel/toolchain:linux_arm64_platform
build:linux_arm64_cross_arm64 --extra_toolchains=@eros_forge//bazel/toolchain:cc-toolchain-arm64-to-arm64

# 发布版本配置
build:release --compilation_mode=opt
build:release --copt=-O3
build:release --copt=-DNDEBUG
build:release --copt=-g
build:release --features=separate_debug_info
```

### 自定义工具链

工具链由 `generate_files.py` 中的 `CONFIGS` 表驱动。如需添加新工具链（如 RISC-V）：

1. 在 `bazel/toolchain/generate_files.py` 的 `CONFIGS` 中添加一个新条目（编译器前缀、
   目标三元组、sysroot、builtin_includes、动态链接器等）。
2. 运行 `python3 bazel/toolchain/generate_files.py` 重新生成 `toolchain_data.bzl`、
   Conan profile 和 CMake 工具链文件。
3. 在 `bazel/toolchain/BUILD.bazel` 中用 `eros_cc_toolchain` 宏实例化新工具链
   （传入 `config_key` 指向新表条目，以及 `exec_compatible_with` / `target_compatible_with`）。
4. 在 `MODULE.bazel` 的 `register_toolchains(...)` 中注册新工具链。
5. 在 `bazel/bazelrc` 中添加对应的 `--config=linux_x86_64_cross_riscv64` 配置。

例如在 `BUILD.bazel` 中：

```python
eros_cc_toolchain(
    name = "cc-toolchain-riscv64-cross",
    toolchain_name = "cc-toolchain-x86_64-to-riscv64",
    config_key = "linux_x86_64_cross_riscv64",  # CONFIGS 中的新 key
    exec_compatible_with = ["@platforms//os:linux", "@platforms//cpu:x86_64"],
    target_compatible_with = ["@platforms//os:linux", "@platforms//cpu:riscv64"],
    host_tools = "@eros_host_tools//:cross_riscv64_all",
)
```

然后在 `bazelrc` 中添加配置：

```bazel
build:linux_x86_64_cross_riscv64 --platforms=@eros_forge//bazel/toolchain:linux_riscv64_cross_platform
build:linux_x86_64_cross_riscv64 --extra_toolchains=@eros_forge//bazel/toolchain:cc-toolchain-x86_64-to-riscv64
```

## Sanitizer 支持

Forge 工具链内置了以下 Sanitizer 支持，用于检测内存错误和数据竞争。

### 默认行为

Debug 模式（`--config=debug`）仅启用调试编译（`-g -O0`），**不**默认启用任何
Sanitizer。Sanitizer 与 Debug 解耦，需要时显式叠加 `--config=asan` / `--config=ubsan`
等（各 sanitizer 配置本身已设置 `compilation_mode=dbg`，因此 `--config=asan` 即可
独立使用）。

这意味着：

- Debug 构建默认不含 Sanitizer 插桩，便于纯净调试
- 需要内存/线程/未定义行为检测时显式选择对应 `--config=<sanitizer>`
- `--config=no_sanitizer` 可显式禁用所有 Sanitizer（用于性能测试基线）

### 可用的 Sanitizer 配置

| 配置                      | Sanitizer       | 检测内容           |
| ----------------------- | --------------- | -------------- |
| `--config=asan`         | AddressSanitizer | 内存错误（缓冲区溢出、use-after-free 等） |
| `--config=ubsan`        | UndefinedBehaviorSanitizer | 未定义行为（整数溢出、空指针等） |
| `--config=tsan`         | ThreadSanitizer | 数据竞争、死锁 |
| `--config=msan`         | MemorySanitizer | 未初始化内存读取（通常需 Clang） |
| `--config=no_sanitizer` | 无               | 禁用所有 Sanitizer |

> ASan 与 TSan/MSan 互斥；ASan + UBSan 可组合。各配置在 bazelrc 中通过
> `--features=-<san>` 显式互斥，避免错误组合。

### 使用示例

```bash
# Debug 构建（无 Sanitizer）
bazel build //:my_app --config=linux_x86_64 --config=debug

# 在 Debug 基础上叠加 AddressSanitizer
bazel build //:my_app --config=linux_x86_64 --config=asan

# ThreadSanitizer（自身已为 dbg 模式）
bazel build //:my_app --config=linux_x86_64 --config=tsan

# 性能测试时禁用 Sanitizer
bazel build //:my_app --config=linux_x86_64 --config=no_sanitizer
```

### 注意事项

1. **ASan 和 TSan 互斥**：不能同时使用
2. **MSan 要求**：所有代码（包括依赖库）都必须使用 MSan 编译
3. **性能影响**：Sanitizer 会显著降低程序性能（通常 2-10 倍）
4. **内存开销**：ASan 会增加 2-3 倍内存使用
5. **推荐场景**：
   - 开发阶段：`--config=debug`（纯净调试），需要时叠加 `--config=asan`
   - 并发测试：`--config=tsan`
   - 性能测试：`--config=no_sanitizer`

### Sanitizer 输出示例

**AddressSanitizer 检测到的内存错误：**

```
==12345==ERROR: AddressSanitizer: heap-buffer-overflow
READ of size 4 at 0x6020000001f0 thread T0
    #0 0x401234 in foo() /path/to/file.cpp:10:5
    #1 0x401567 in main /path/to/main.cpp:20:5
```

**ThreadSanitizer 检测到的数据竞争：**

```
==================
WARNING: ThreadSanitizer: data race (pid=12345)
  Read of size 4 at 0x7b0400000000 by thread T1:
    #0 foo() /path/to/file.cpp:10:5

  Previous write of size 4 at 0x7b0400000000 by thread T0:
    #0 bar() /path/to/file.cpp:20:5
==================
```

## 常见问题

### Q: 为什么交叉编译时需要自定义 glibc？

A: 目标机可能使用较旧版本的 glibc。使用自定义 glibc 可以确保程序在目标机上兼容运行，避免版本不匹配问题。

### Q: 如何在不使用自定义 glibc 的情况下交叉编译？

A: 如果目标机的 glibc 版本与宿主机兼容，可以使用原生编译配置 `--config=linux_arm64`，无需交叉编译。

### Q: 编译失败，提示找不到头文件？

A: 检查是否正确安装了交叉编译工具链，以及工具链配置中的 `cxx_builtin_include_directories` 是否正确。

### Q: 程序在目标机上运行时报错 "No such file or directory"？

A: 这通常是因为动态链接器路径不正确。使用 `readelf -l` 检查程序的 INTERP 段，确保动态链接器路径正确。

### Q: Release 模式下的符号分离是什么？

A: Release 模式启用了 `separate_debug_info` 特性，会在编译时生成独立的调试符号文件，减小发布二进制的体积，同时保留调试能力。

## CMake 集成

Forge 提供了 `cmake_forge` 宏，用于在 Bazel 中构建 CMake 项目，并自动根据 Bazel 配置选择正确的 CMake toolchain 文件。

### 支持的配置

| 配置                                  | CMake Toolchain 文件               | 说明                   |
| ----------------------------------- | -------------------------------- | -------------------- |
| `--config=linux_x86_64`             | `linux_x86_64.cmake`             | x86\_64 原生编译         |
| `--config=linux_arm64`              | `linux_arm64.cmake`              | ARM64 原生编译           |
| `--config=linux_x86_64_cross_arm64` | `linux_x86_64_cross_arm64.cmake` | x86\_64 到 ARM64 交叉编译 |
| `--config=linux_arm64_cross_arm64`  | `linux_arm64_cross_arm64.cmake`  | ARM64 到 ARM64 交叉编译   |

### 使用方法

在你的项目 `MODULE.bazel` 中添加：

```python
# MODULE.bazel
bazel_dep(name = "eros_forge", version = "0.1.0")
bazel_dep(name = "rules_foreign_cc", version = "0.15.1")
```

在 `BUILD.bazel` 中使用 `cmake_forge`：

```python
load("@eros_forge//bazel:cmake_forge.bzl", "cmake_forge")

filegroup(
    name = "src_files",
    srcs = glob(["*.cpp", "CMakeLists.txt"]),
)

cmake_forge(
    name = "hello_world_cmake",
    lib_source = ":src_files",
    out_binaries = ["hello_cmake"],
    cache_entries = {
        "CMAKE_BUILD_TYPE": "Release",
    },
)
```

### 构建示例

```bash
# x86_64 原生编译
bazel build //:hello_world_cmake --config=linux_x86_64

# 交叉编译到 ARM64
bazel build //:hello_world_cmake --config=linux_x86_64_cross_arm64

# 验证生成的二进制文件架构
file bazel-bin/hello_world_cmake/bin/hello_cmake
```

### CMake Toolchain 文件

Forge 根据 Bazel 配置自动选择对应的 CMake toolchain 文件，位于 `bazel/toolchain/cmake/`：

```
bazel/toolchain/cmake/
├── BUILD.bazel
├── linux_x86_64.cmake              # x86_64 原生编译
├── linux_arm64.cmake               # ARM64 原生编译
├── linux_x86_64_cross_arm64.cmake  # 交叉编译（x86_64 -> ARM64）
└── linux_arm64_cross_arm64.cmake   # 交叉编译（ARM64 -> ARM64）
```

每个 toolchain 文件定义了：

- `CMAKE_SYSTEM_NAME` 和 `CMAKE_SYSTEM_PROCESSOR`：目标系统信息
- `CMAKE_C_COMPILER` 和 `CMAKE_CXX_COMPILER`：编译器路径
- `CMAKE_ASM_COMPILER`：汇编器配置
- `CMAKE_FIND_ROOT_PATH_MODE_*`：交叉编译查找模式
- 链接器标志和库搜索路径

### 工作原理

1. `cmake_forge` 宏根据 `--config` 参数通过 `select()` 选择对应的 toolchain 文件
2. 将 toolchain 文件路径通过 `CMAKE_TOOLCHAIN_FILE` 传递给 CMake
3. CMake 使用指定的 toolchain 进行编译，确保与 Bazel 的编译配置一致

### 注意事项

1. **交叉编译器路径**：确保交叉编译工具链已安装（如 `gcc-aarch64-linux-gnu`）
2. **汇编器配置**：交叉编译 toolchain 文件使用 `-B` 标志确保找到正确的汇编器
3. **库依赖**：交叉编译的程序需要目标机上有兼容的 glibc 版本

## 参考资源

- [Bazel 官方文档](https://bazel.build/)
- [Bazel C++ Toolchain 配置](https://bazel.build/extending/cc-toolchain)
- [GCC 交叉编译指南](https://gcc.gnu.org/onlinedocs/gccint/Configure-Terms.html)
- [Glibc 交叉编译](https://sourceware.org/glibc/wiki/Testing/Builds)
- [rules\_foreign\_cc 文档](https://github.com/bazelbuild/rules_foreign_cc)

