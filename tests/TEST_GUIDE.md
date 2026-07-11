# EROS Forge 测试用例完整指南

> 本文档是 EROS Forge 测试集合的完整指南，包含测试用例清单、环境配置、运行方法和验证说明。

---

## 目录

1. [概述](#概述)
2. [测试用例总览](#测试用例总览)
3. [环境配置](#环境配置)
4. [测试项目详情](#测试项目详情)
5. [运行测试](#运行测试)
6. [验证检查](#验证检查)
7. [故障排查](#故障排查)
8. [常见问题](#常见问题)
9. [附录](#附录)

---

## 概述

### 测试集合简介

EROS Forge 测试集合用于验证 EROS Forge 构建系统的各项功能，包括：

- ✅ 平台配置（原生编译和交叉编译）
- ✅ 构建模式（Debug 和 Release）
- ✅ Sanitizer 支持（TSan、MSan）
- ✅ CMake 集成
- ✅ Conan 集成
- ✅ 跨模块依赖消费（静态库、动态库、头文件）

### 测试统计

| 项目 | 数量 |
|------|------|
| 测试项目数 | 3 |
| 测试用例总数 | 48 |
| 自动化检查类型 | 2（制品结果验证 + 编译选项验证） |
| 平台配置 | 4 |
| 构建模式 | 2 |
| Sanitizer 配置 | 4 |
| 依赖消费测试 | 4 |

### 测试项目

| 项目名称 | 位置 | 描述 | 用例数 |
|---------|------|------|--------|
| **Bazel9 C++ 简单项目** | `tests/bazel_simple/` | 纯 Bazel C++ 项目 | 16 |
| **Bazel9 + CMake 项目** | `tests/bazel_cmake/` | 使用 cmake_forge 宏构建 | 16 |
| **Bazel9 + CMake + Conan 项目** | `tests/bazel_cmake_conan/` | 使用 cmake_conan_forge 宏 + Conan 依赖 | 16 |

---

## 测试用例总览

### 测试用例编号规则

- **BP**: Bazel Platform (Bazel 平台配置测试)
- **BM**: Bazel Build Mode (Bazel 构建模式测试)
- **BS**: Bazel Sanitizer (Bazel Sanitizer 测试)
- **BC**: Bazel CMake (Bazel+CMake 测试)
- **BCC**: Bazel CMake Conan (Bazel+CMake+Conan 测试)
- **DC**: Dependency Consumption (跨模块依赖消费测试)

### 完整测试用例列表

#### 1. Bazel9 C++ 简单项目 (16 个用例)

**平台配置测试 (4 个)**:
- BP-001: `--config=linux_x86_64` - x86_64 原生编译
- BP-002: `--config=linux_arm64` - ARM64 原生编译
- BP-003: `--config=linux_x86_64_cross_arm64` - x86_64 交叉编译到 ARM64
- BP-004: `--config=linux_arm64_cross_arm64` - ARM64 交叉编译（自定义 glibc）

**构建模式测试 (2 个)**:
- BM-001: `--config=debug` - Debug 模式构建
- BM-002: `--config=release` - Release 模式构建

**Sanitizer 测试 (4 个)**:
- BS-001: `--config=asan` - AddressSanitizer
- BS-002: `--config=ubsan` - UndefinedBehaviorSanitizer
- BS-003: `--config=tsan` - ThreadSanitizer
- BS-004: `--config=msan` - MemorySanitizer（GCC 支持有限，需 Clang）

**依赖消费测试 (4 个)**:
- DC-BP-001: `--config=linux_x86_64` - 消费静态库和动态库（x86_64）
- DC-BP-002: `--config=linux_arm64` - 消费静态库和动态库（ARM64）
- DC-BP-003: `--config=linux_x86_64_cross_arm64` - 消费静态库和动态库（交叉编译）
- DC-BP-004: `--config=linux_arm64_cross_arm64` - 消费静态库和动态库（自定义 glibc）

#### 2. Bazel9 + CMake 项目 (16 个用例)

**平台配置测试 (4 个)**:
- BC-001: `--config=linux_x86_64` - x86_64 原生编译
- BC-002: `--config=linux_arm64` - ARM64 原生编译
- BC-003: `--config=linux_x86_64_cross_arm64` - x86_64 交叉编译到 ARM64
- BC-004: `--config=linux_arm64_cross_arm64` - ARM64 交叉编译（自定义 glibc）

**构建模式测试 (2 个)**:
- BC-BM-001: `--config=debug` - Debug 模式构建
- BC-BM-002: `--config=release` - Release 模式构建

**Sanitizer 测试 (4 个)**:
- BC-BS-001: `--config=asan` - AddressSanitizer
- BC-BS-002: `--config=ubsan` - UndefinedBehaviorSanitizer
- BC-BS-003: `--config=tsan` - ThreadSanitizer
- BC-BS-004: `--config=msan` - MemorySanitizer（GCC 支持有限，需 Clang）

**依赖消费测试 (4 个)**:
- DC-BC-001: `--config=linux_x86_64` - 消费 CMake 构建的库（x86_64）
- DC-BC-002: `--config=linux_arm64` - 消费 CMake 构建的库（ARM64）
- DC-BC-003: `--config=linux_x86_64_cross_arm64` - 消费 CMake 构建的库（交叉编译）
- DC-BC-004: `--config=linux_arm64_cross_arm64` - 消费 CMake 构建的库（自定义 glibc）

#### 3. Bazel9 + CMake + Conan 项目 (16 个用例)

**平台配置测试 (4 个)**:
- BCC-001: `--config=linux_x86_64` - x86_64 原生编译
- BCC-002: `--config=linux_arm64` - ARM64 原生编译
- BCC-003: `--config=linux_x86_64_cross_arm64` - x86_64 交叉编译到 ARM64
- BCC-004: `--config=linux_arm64_cross_arm64` - ARM64 交叉编译（自定义 glibc）

**构建模式测试 (2 个)**:
- BCC-BM-001: `--config=debug` - Debug 模式构建
- BCC-BM-002: `--config=release` - Release 模式构建

**Sanitizer 测试 (4 个)**:
- BCC-BS-001: `--config=asan` - AddressSanitizer
- BCC-BS-002: `--config=ubsan` - UndefinedBehaviorSanitizer
- BCC-BS-003: `--config=tsan` - ThreadSanitizer
- BCC-BS-004: `--config=msan` - MemorySanitizer（GCC 支持有限，需 Clang）

> 注：`cmake_conan_forge` 的 Conan sanitizer profile 仅覆盖 asan/tsan（见
> `generate_files.py` 的 `SANITIZERS`），ubsan/msan 在 Conan 测试中跳过。

**依赖消费测试 (4 个)**:
- DC-BCC-001: `--config=linux_x86_64` - 消费 CMake+Conan 构建的库（x86_64）
- DC-BCC-002: `--config=linux_arm64` - 消费 CMake+Conan 构建的库（ARM64）
- DC-BCC-003: `--config=linux_x86_64_cross_arm64` - 消费 CMake+Conan 构建的库（交叉编译）
- DC-BCC-004: `--config=linux_arm64_cross_arm64` - 消费 CMake+Conan 构建的库（自定义 glibc）

### 测试覆盖矩阵

| 测试类型 | 平台配置 | 构建模式 | Sanitizer | CMake | Conan | 依赖消费 |
|---------|:-------:|:-------:|:---------:|:-----:|:-----:|:-------:|
| bazel_simple | ✅ 4 个 | ✅ 2 个 | ✅ 4 个 | ❌ | ❌ | ✅ 4 个 |
| bazel_cmake | ✅ 4 个 | ✅ 2 个 | ✅ 4 个 | ✅ | ❌ | ✅ 4 个 |
| bazel_cmake_conan | ✅ 4 个 | ✅ 2 个 | ✅ 4 个 | ✅ | ✅ | ✅ 4 个 |

---

## 环境配置

### 基础环境要求

#### 必需工具

| 工具 | 最低版本 | 验证命令 | 用途 |
|------|---------|---------|------|
| Bazel | 9.0 | `bazel --version` | 构建系统 |
| GCC | 13 | `gcc --version` | 编译器 |
| G++ | 13 | `g++ --version` | C++ 编译器 |
| Python | 3.8 | `python3 --version` | 测试脚本 |
| CMake | 3.16 | `cmake --version` | CMake 项目测试 |
| Conan | 2.0 | `conan --version` | Conan 项目测试 |

#### 安装指南（Ubuntu/Debian）

```bash
# 更新包列表
sudo apt-get update

# 安装基础工具
sudo apt-get install -y gcc-13 g++-13 python3 cmake

# 安装 Bazel 9.0
wget https://github.com/bazelbuild/bazel/releases/download/9.0.0/bazel-9.0.0-installer-linux-x86_64.sh
chmod +x bazel-9.0.0-installer-linux-x86_64.sh
sudo ./bazel-9.0.0-installer-linux-x86_64.sh

# 验证 Bazel 安装
bazel --version

# 安装 Conan
pip3 install conan

# 验证 Conan 安装
conan --version
```

### 交叉编译环境

#### 交叉编译工具链

```bash
# 安装 ARM64 交叉编译工具链
sudo apt-get install -y gcc-aarch64-linux-gnu g++-aarch64-linux-gnu

# 验证工具链
aarch64-linux-gnu-gcc --version
aarch64-linux-gnu-g++ --version
```

#### 自定义 glibc（可选）

用于测试 `--config=linux_arm64_cross_arm64` 配置：

```bash
# 创建目标目录
sudo mkdir -p /opt/eros/lib
sudo mkdir -p /opt/eros/include

# 安装自定义 glibc（从 EROS SDK 复制）
sudo cp /path/to/eros/lib/ld-linux-aarch64.so.1 /opt/eros/lib/
sudo cp /path/to/eros/lib/libc.so.6 /opt/eros/lib/
sudo cp /path/to/eros/lib/libstdc++.so.6 /opt/eros/lib/

# 设置权限
sudo chmod 755 /opt/eros/lib/*

# 验证安装
ls -la /opt/eros/lib/
```

### 环境变量设置

```bash
# 设置交叉编译工具链路径（可选）
export CROSS_COMPILE=aarch64-linux-gnu-
export CC=aarch64-linux-gnu-gcc
export CXX=aarch64-linux-gnu-g++

# 设置 EROS 根目录（用于交叉编译）
export EROS_ROOT=/opt/eros

# 添加到 ~/.bashrc 以永久生效
echo 'export CROSS_COMPILE=aarch64-linux-gnu-' >> ~/.bashrc
echo 'export CC=aarch64-linux-gnu-gcc' >> ~/.bashrc
echo 'export CXX=aarch64-linux-gnu-g++' >> ~/.bashrc
echo 'export EROS_ROOT=/opt/eros' >> ~/.bashrc
source ~/.bashrc
```

### 环境验证脚本

```bash
#!/bin/bash
# 验证测试环境是否就绪

echo "=== 验证基础工具 ==="
echo "Bazel 版本：$(bazel --version | head -n1)"
echo "GCC 版本：$(gcc --version | head -n1)"
echo "G++ 版本：$(g++ --version | head -n1)"
echo "Python 版本：$(python3 --version)"
echo "CMake 版本：$(cmake --version | head -n1)"
echo "Conan 版本：$(conan --version)"

echo ""
echo "=== 验证交叉编译工具链 ==="
if command -v aarch64-linux-gnu-gcc &> /dev/null; then
    echo "✓ aarch64-linux-gnu-gcc 已安装"
else
    echo "✗ aarch64-linux-gnu-gcc 未安装"
fi

if command -v aarch64-linux-gnu-g++ &> /dev/null; then
    echo "✓ aarch64-linux-gnu-g++ 已安装"
else
    echo "✗ aarch64-linux-gnu-g++ 未安装"
fi

echo ""
echo "=== 验证自定义 glibc ==="
if [ -d "/opt/eros/lib" ]; then
    echo "✓ /opt/eros/lib 目录存在"
    ls -la /opt/eros/lib/
else
    echo "✗ /opt/eros/lib 目录不存在（仅影响交叉编译测试）"
fi
```

---

## 测试项目详情

### 1. Bazel9 C++ 简单项目

**位置**: `tests/bazel_simple/`

**项目描述**: 纯 Bazel C++ 项目，验证基础构建功能

**项目文件**:
```
bazel_simple/
├── main.cpp              # 主程序源文件
├── BUILD.bazel           # Bazel 构建配置
├── MODULE.bazel          # Bazel 模块配置
├── .bazelrc              # Bazel 运行时配置
├── .bazelignore          # 忽略 consumer 子目录
├── lib/                  # 库源文件
│   ├── math_utils.h      # 数学工具库头文件
│   └── math_utils.cpp    # 数学工具库源文件
├── consumer/             # 依赖消费测试项目
│   ├── main.cpp          # 消费者主程序
│   ├── BUILD.bazel       # 消费者构建配置
│   ├── MODULE.bazel      # 消费者模块配置
│   └── .bazelrc          # 消费者 Bazel 配置
└── test_configs/         # 测试脚本目录
    ├── test_platform_configs.sh   # 平台配置测试
    ├── test_build_modes.sh        # 构建模式测试
    ├── test_sanitizers.sh         # Sanitizer 测试
    └── test_dependency_consumption.sh  # 依赖消费测试
```

**测试脚本**:
- `test_platform_configs.sh`: 测试 4 种平台配置
- `test_build_modes.sh`: 测试 Debug/Release 构建模式
- `test_sanitizers.sh`: 测试 4 种 Sanitizer 配置
- `test_dependency_consumption.sh`: 测试跨模块依赖消费（静态库 + 动态库 + 头文件）

**验证项**:
- ✓ 二进制架构检查
- ✓ 动态链接器检查（交叉编译）
- ✓ RUNPATH 检查（交叉编译）
- ✓ 依赖库检查
- ✓ 程序运行检查
- ✓ C++ 标准验证
- ✓ 编译标志验证

### 2. Bazel9 + CMake 项目

**位置**: `tests/bazel_cmake/`

**项目描述**: 使用 cmake_forge 宏构建的 CMake 项目，验证 CMake 集成

**项目文件**:
```
bazel_cmake/
├── main.cpp              # 主程序源文件
├── CMakeLists.txt        # CMake 构建配置
├── BUILD.bazel           # Bazel 构建配置（使用 cmake_forge）
├── MODULE.bazel          # Bazel 模块配置
├── .bazelrc              # Bazel 运行时配置
├── .bazelignore          # 忽略 consumer 子目录
├── lib/                  # 库源文件
│   ├── math_utils.h      # 数学工具库头文件
│   └── math_utils.cpp    # 数学工具库源文件
├── consumer/             # 依赖消费测试项目
│   ├── main.cpp          # 消费者主程序
│   ├── BUILD.bazel       # 消费者构建配置
│   ├── MODULE.bazel      # 消费者模块配置
│   └── .bazelrc          # 消费者 Bazel 配置
└── test_configs/         # 测试脚本目录
    ├── test_platform_configs.sh
    ├── test_build_modes.sh
    ├── test_sanitizers.sh
    └── test_dependency_consumption.sh
```

**测试脚本**:
- `test_platform_configs.sh`: 测试 4 种平台配置（验证 CMake 工具链）
- `test_build_modes.sh`: 测试 Debug/Release 构建模式
- `test_sanitizers.sh`: 测试 4 种 Sanitizer 配置
- `test_dependency_consumption.sh`: 测试跨模块依赖消费（验证 CMake 构建的库可被其他模块消费）

**验证项**:
- ✓ 包含所有 Bazel 简单项目的验证项
- ✓ CMake 工具链配置验证
- ✓ 共享库生成验证

### 3. Bazel9 + CMake + Conan 项目

**位置**: `tests/bazel_cmake_conan/`

**项目描述**: 使用 cmake_conan_forge 宏构建的带 Conan 依赖的项目，验证 Conan 集成

**项目文件**:
```
bazel_cmake_conan/
├── main.cpp              # 主程序源文件
├── mylib.h               # 库头文件
├── mylib.cpp             # 库源文件
├── CMakeLists.txt        # CMake 构建配置
├── conanfile.txt         # Conan 依赖配置
├── BUILD.bazel           # Bazel 构建配置（使用 cmake_conan_forge）
├── MODULE.bazel          # Bazel 模块配置
├── .bazelrc              # Bazel 运行时配置
├── .bazelignore          # 忽略 consumer 子目录
├── consumer/             # 依赖消费测试项目
│   ├── main.cpp          # 消费者主程序
│   ├── BUILD.bazel       # 消费者构建配置
│   ├── MODULE.bazel      # 消费者模块配置
│   └── .bazelrc          # 消费者 Bazel 配置
└── test_configs/         # 测试脚本目录
    ├── test_platform_configs.sh
    ├── test_build_modes.sh
    ├── test_sanitizers.sh
    └── test_dependency_consumption.sh
```

**测试脚本**:
- `test_platform_configs.sh`: 测试 4 种平台配置（验证 Conan 依赖解析）
- `test_build_modes.sh`: 测试 Debug/Release 构建模式（验证 Conan 包模式）
- `test_sanitizers.sh`: 测试 4 种 Sanitizer 配置（验证 Conan 包兼容性）
- `test_dependency_consumption.sh`: 测试跨模块依赖消费（验证 CMake+Conan 构建的库可被其他模块消费）

**验证项**:
- ✓ 包含所有 Bazel+CMake 项目的验证项
- ✓ Conan 依赖解析验证
- ✓ Conan 包模式验证（Debug/Release）
- ✓ Conan 包 Sanitizer 兼容性验证

---

## 运行测试

### 快速开始

#### 最小化测试（仅验证基础功能）

```bash
# 进入测试目录
cd eros/forge/tests

# 运行 Bazel 简单项目的基础测试（仅平台配置）
python3 test_runner.py --test bazel_simple --config platform

# 查看测试报告
cat reports/test_report_*.txt
```

#### 完整测试（所有项目、所有配置）

```bash
# 运行所有测试
python3 test_runner.py --all

# 生成详细报告
python3 test_runner.py --all --report detailed_report.txt
```

### 使用 test_runner.py

#### 命令语法

```bash
python3 test_runner.py [选项]
```

#### 可用选项

| 选项 | 简写 | 描述 | 示例 |
|------|------|------|------|
| `--all` | `-a` | 运行所有测试 | `python3 test_runner.py --all` |
| `--test` | `-t` | 运行指定测试项目 | `python3 test_runner.py --test bazel_simple` |
| `--config` | `-c` | 运行指定配置类别 | `python3 test_runner.py --test bazel_simple --config platform` |
| `--filter` | | 只运行名称含该子串的测试 | `python3 test_runner.py --all --filter platform` |
| `--jobs` | | 跨项目并行（各项目独立 Bazel workspace） | `python3 test_runner.py --all --jobs 3` |
| `--report` | `-r` | 生成测试报告 | `python3 test_runner.py --all --report report.txt` |
| `--help` | `-h` | 显示帮助信息 | `python3 test_runner.py --help` |

> `--config` 可选值：`platform`、`build_mode`、`sanitizer`、`dependency`、`deb`。

#### 使用示例

```bash
# 运行所有测试
python3 test_runner.py --all

# 运行单个测试项目
python3 test_runner.py --test bazel_simple

# 运行特定配置测试
python3 test_runner.py --test bazel_cmake --config platform

# 运行并生成报告
python3 test_runner.py --all --report test_report.txt

# 详细模式运行
python3 test_runner.py --test bazel_cmake_conan --verbose
```

### 直接运行测试脚本

#### 平台配置测试

```bash
cd eros/forge/tests/bazel_simple

# 运行所有平台配置测试
./test_configs/test_platform_configs.sh

# 运行特定配置测试
./test_configs/test_platform_configs.sh linux_x86_64
./test_configs/test_platform_configs.sh linux_arm64
./test_configs/test_platform_configs.sh linux_x86_64_cross_arm64
./test_configs/test_platform_configs.sh linux_arm64_cross_arm64
```

#### 构建模式测试

```bash
cd eros/forge/tests/bazel_simple

# 运行所有构建模式测试
./test_configs/test_build_modes.sh

# 运行特定构建模式测试
./test_configs/test_build_modes.sh debug
./test_configs/test_build_modes.sh release
```

#### Sanitizer 测试

```bash
cd eros/forge/tests/bazel_simple

# 运行所有 Sanitizer 测试
./test_configs/test_sanitizers.sh

# 运行特定 Sanitizer 测试（脚本接受 sanitizer 名作为参数）
./test_configs/test_sanitizers.sh linux_x86_64
```

#### 依赖消费测试

```bash
cd eros/forge/tests/bazel_simple

# 运行所有依赖消费测试
./test_configs/test_dependency_consumption.sh

# 运行特定配置的依赖消费测试
./test_configs/test_dependency_consumption.sh linux_x86_64
./test_configs/test_dependency_consumption.sh linux_arm64
./test_configs/test_dependency_consumption.sh linux_x86_64_cross_arm64
./test_configs/test_dependency_consumption.sh linux_arm64_cross_arm64
```

### 测试执行流程

测试 runner 会按以下顺序执行测试：

1. **平台配置测试**
   - 清理构建缓存
   - 使用不同平台配置构建项目
   - 验证生成的二进制文件
   - 运行程序（如适用）

2. **构建模式测试**
   - 清理构建缓存
   - 使用 debug/release 模式构建
   - 验证编译选项和符号信息
   - 运行程序

3. **Sanitizer 测试**
   - 清理构建缓存
   - 使用不同 Sanitizer 配置构建
   - 验证 Sanitizer 插桩
   - 运行程序（如适用）

4. **依赖消费测试**
   - 在 consumer/ 子目录中构建消费者项目
   - 验证消费者项目能正确链接库文件和头文件
   - 验证消费者二进制架构正确
   - 验证消费者二进制执行成功（原生编译）
   - 验证动态链接器和 RUNPATH（交叉编译）

### 测试输出示例

```
=========================================
测试项目：bazel_simple
=========================================

=========================================
测试类别：平台配置
=========================================

=========================================
测试配置：linux_x86_64
=========================================
构建命令：bazel build //:hello --config=linux_x86_64 --subcommands
✓ 架构检查通过：x86_64
✓ 依赖检查通过
✓ 程序运行成功
测试通过：linux_x86_64
```

### 测试报告

测试完成后会生成详细的测试报告，包括：
- 测试执行时间
- 测试通过/失败数量
- 失败测试的详细错误信息
- 构建日志

**报告位置**: `tests/reports/test_report_<timestamp>.txt`

**查看报告**:
```bash
# 查看最新报告
cat reports/test_report_*.txt | tail -n 100

# 查看测试统计
grep "测试统计" reports/test_report_*.txt

# 查看失败测试
grep "✗" reports/test_report_*.txt
```

---

## 验证检查

### 制品结果验证

所有测试用例均包含以下自动化检查：

#### 1. 二进制架构检查

验证生成的二进制文件架构是否与目标平台一致。

**检查方法**:
```bash
file bazel-bin/hello
```

**期望输出**:
- x86_64: `hello: ELF 64-bit LSB executable, x86-64, ...`
- aarch64: `hello: ELF 64-bit LSB executable, ARM aarch64, ...`

**验证函数**: `check_binary_arch()`

#### 2. 动态链接器检查（交叉编译）

验证交叉编译的二进制文件使用正确的动态链接器。

**检查方法**:
```bash
readelf -l bazel-bin/hello | grep interpreter
```

**期望输出**:
```
[Requesting program interpreter: /opt/eros/lib/ld-linux-aarch64.so.1]
```

**验证函数**: `check_dynamic_linker()`

#### 3. RUNPATH 检查（交叉编译）

验证交叉编译的二进制文件包含正确的 RUNPATH。

**检查方法**:
```bash
readelf -d bazel-bin/hello | grep RUNPATH
```

**期望输出**:
```
0x000000000000001d (RUNPATH)            Library runpath: [/opt/eros/lib]
```

**验证函数**: `check_runpath()`

#### 4. 依赖库检查

验证二进制文件依赖的库是否正确。

**检查方法**:
```bash
# 原生编译
ldd bazel-bin/hello

# 交叉编译
aarch64-linux-gnu-objdump -p bazel-bin/hello | grep NEEDED
```

**验证函数**: `check_dependencies()`

#### 5. 共享库检查

验证是否生成了共享库（适用于 CMake 项目）。

**检查方法**:
```bash
find bazel-bin -name "libmylib.so" -type f
```

**验证函数**: `check_shared_library()`

#### 6. 运行检查

验证二进制文件是否可以正常运行。

**检查方法**:
```bash
./bazel-bin/hello
```

**期望输出**:
```
Hello from EROS Forge!
```

**验证函数**: `run_binary()`

### 编译选项验证

所有测试用例均包含以下编译选项检查：

#### 1. C++ 标准检查

验证是否使用了 C++20 标准。

**检查方法**:
```bash
grep "\-std=c++20" build.log
```

**验证函数**: `check_cpp_standard()`

#### 2. 编译器路径检查

验证使用正确的编译器路径。

**检查方法**:
```bash
grep "aarch64-linux-gnu-gcc" build.log
```

**验证函数**: `check_compiler_path()`

#### 3. 交叉编译标志检查

验证交叉编译时是否使用了正确的工具链。

**检查方法**:
```bash
# 检查编译器路径和目标标志
grep "aarch64-linux-gnu-gcc" build.log
grep "\-target aarch64-linux-gnu" build.log
```

**验证函数**: `check_cross_compile_flags()`

#### 4. 构建模式检查

验证构建模式相关的编译标志。

**Debug 模式检查**:
```bash
grep "\-g" build.log          # 调试信息
grep "\-O0" build.log         # 无优化
grep "\-DDEBUG" build.log     # DEBUG 宏
```

**Release 模式检查**:
```bash
grep "\-O3" build.log         # 优化级别
grep "\-DNDEBUG" build.log    # NDEBUG 宏
grep "\-s" build.log          # 符号分离
```

**验证函数**: `check_debug_flags()`, `check_release_flags()`

#### 5. Sanitizer 检查

验证 Sanitizer 编译标志。

**TSan 检查**:
```bash
grep "\-fsanitize=thread" build.log
```

**MSan 检查**:
```bash
grep "\-fsanitize=memory" build.log
```

**验证函数**: `check_sanitizer_flags()`

---

## 故障排查

### 常见问题及解决方案

#### 1. Bazel 版本不匹配

**错误**: `ERROR: Bazel 8.x is not compatible with this workspace`

**解决方案**:
```bash
# 检查 Bazel 版本
bazel --version

# 安装正确的 Bazel 版本
wget https://github.com/bazelbuild/bazel/releases/download/9.0.0/bazel-9.0.0-installer-linux-x86_64.sh
sudo ./bazel-9.0.0-installer-linux-x86_64.sh
```

#### 2. 交叉编译工具链未找到

**错误**: `error: unable to find aarch64-linux-gnu-gcc`

**解决方案**:
```bash
# 安装交叉编译工具链
sudo apt-get install -y gcc-aarch64-linux-gnu g++-aarch64-linux-gnu

# 验证安装
aarch64-linux-gnu-gcc --version
```

#### 3. 自定义 glibc 未找到

**错误**: `/opt/eros/lib/ld-linux-aarch64.so.1: not found`

**解决方案**:
```bash
# 检查目录是否存在
ls -la /opt/eros/lib/

# 如果不存在，需要安装 EROS SDK 或创建符号链接
sudo mkdir -p /opt/eros/lib
# 从 EROS SDK 复制 glibc 文件
```

#### 4. Conan 依赖解析失败

**错误**: `ERROR: Unable to resolve package`

**解决方案**:
```bash
# 更新 Conan 配置
conan profile detect

# 清理 Conan 缓存
conan cache clean

# 重新安装依赖
cd eros/forge/tests/bazel_cmake_conan
conan install . --build=missing
```

#### 5. 测试脚无执行权限

**错误**: `Permission denied`

**解决方案**:
```bash
# 添加执行权限
chmod +x eros/forge/tests/bazel_simple/test_configs/*.sh
```

#### 6. Python 依赖缺失

**错误**: `ModuleNotFoundError: No module named 'xxx'`

**解决方案**:
```bash
# test_utils.py 只使用标准库，不需要额外依赖
# 如果修改了脚本需要安装依赖：
pip3 install -r requirements.txt
```

### 获取详细日志

```bash
# 使用 verbose 模式运行测试
python3 test_runner.py --test bazel_simple --verbose

# 查看 Bazel 详细输出
bazel build //:hello --config=linux_x86_64 --subcommands --verbose_failures

# 保存构建日志
bazel build //:hello --config=linux_x86_64 2>&1 | tee build.log
```

---

## 常见问题

### Q1: 为什么交叉编译测试失败？

**A**: 交叉编译测试需要安装交叉编译工具链和自定义 glibc。请确保：
1. 已安装 `gcc-aarch64-linux-gnu` 和 `g++-aarch64-linux-gnu`
2. 已设置 `/opt/eros/lib` 目录并包含必要的 glibc 文件
3. Bazel 工具链配置正确

### Q2: 如何跳过某些测试？

**A**: 可以使用 `--config` 参数指定只运行特定类别的测试：

```bash
# 只运行平台配置测试
python3 test_runner.py --test bazel_simple --config platform

# 只运行构建模式测试
python3 test_runner.py --test bazel_simple --config build_mode
```

### Q3: 测试运行需要多长时间？

**A**: 取决于硬件配置：
- 完整测试（所有项目）：约 10-20 分钟
- 单个项目测试：约 3-5 分钟
- 单个配置测试：约 30 秒 -1 分钟

### Q4: 如何查看测试覆盖率？

**A**: 当前测试主要验证构建功能和制品正确性，不统计代码覆盖率。如需代码覆盖率，可以使用 Bazel 的覆盖率工具：

```bash
bazel coverage //:hello --config=linux_x86_64
```

### Q5: 测试失败后如何清理？

**A**: 测试会自动清理构建缓存，但也可以手动清理：

```bash
# 清理 Bazel 缓存
bazel clean

# 清理测试报告
rm -rf eros/forge/tests/reports/*

# 清理 Conan 缓存（如适用）
conan cache clean
```

### Q6: 如何在 CI/CD 中使用这些测试？

**A**: 参考以下 GitHub Actions 示例：

```yaml
# .github/workflows/test.yml
name: EROS Forge Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Setup Bazel
        run: |
          wget https://github.com/bazelbuild/bazel/releases/download/9.0.0/bazel-9.0.0-installer-linux-x86_64.sh
          chmod +x bazel-9.0.0-installer-linux-x86_64.sh
          sudo ./bazel-9.0.0-installer-linux-x86_64.sh
      
      - name: Install Cross Compiler
        run: |
          sudo apt-get update
          sudo apt-get install -y gcc-aarch64-linux-gnu g++-aarch64-linux-gnu
      
      - name: Run Tests
        run: |
          cd eros/forge/tests
          python3 test_runner.py --all --report report.txt
      
      - name: Upload Report
        uses: actions/upload-artifact@v3
        with:
          name: test-report
          path: eros/forge/tests/reports/
```

### Q7: 测试报告在哪里？

**A**: 测试报告保存在 `eros/forge/tests/reports/` 目录下，文件名包含时间戳：

```
reports/
├── test_report_20260411_143022.txt
├── test_report_20260411_151534.txt
└── ...
```

---

## 附录

### 附录 A: 测试配置详解

#### 平台配置

| 配置名称 | Bazel 配置 | 描述 | 目标架构 | 交叉编译 |
|---------|-----------|------|---------|---------|
| linux_x86_64 | `--config=linux_x86_64` | x86_64 原生编译 | x86_64 | 否 |
| linux_arm64 | `--config=linux_arm64` | ARM64 原生编译 | aarch64 | 否 |
| linux_x86_64_cross_arm64 | `--config=linux_x86_64_cross_arm64` | x86_64 交叉编译到 ARM64 | aarch64 | 是 |
| linux_arm64_cross_arm64 | `--config=linux_arm64_cross_arm64` | ARM64 交叉编译（自定义 glibc） | aarch64 | 是 |

#### 构建模式

| 配置名称 | Bazel 配置 | 优化级别 | 调试信息 | 宏定义 |
|---------|-----------|---------|---------|--------|
| debug | `--config=debug` | -O0 | 是 (-g) | DEBUG |
| release | `--config=release` | -O3 | 否（符号分离） | NDEBUG |

#### Sanitizer 配置

| 配置名称 | Bazel 配置 | Sanitizer 类型 | 编译标志 | 用途 |
|---------|-----------|---------------|---------|------|
| asan | `--config=asan` | AddressSanitizer | -fsanitize=address | 检测内存错误 |
| ubsan | `--config=ubsan` | UndefinedBehaviorSanitizer | -fsanitize=undefined | 检测未定义行为 |
| tsan | `--config=tsan` | ThreadSanitizer | -fsanitize=thread | 检测数据竞争 |
| msan | `--config=msan` | MemorySanitizer | -fsanitize=memory | 检测未初始化内存（需 Clang） |
| no_sanitizer | `--config=no_sanitizer` | 无 | 无 | 性能测试基线 |

> Sanitizer 与平台配置叠加使用，例如 `--config=linux_x86_64 --config=asan`。

### 附录 B: 快速命令参考

#### 运行测试

```bash
# 运行所有测试
python3 test_runner.py --all

# 运行单个项目测试
python3 test_runner.py --test bazel_simple
python3 test_runner.py --test bazel_cmake
python3 test_runner.py --test bazel_cmake_conan

# 运行特定配置测试
python3 test_runner.py --test bazel_simple --config platform
python3 test_runner.py --test bazel_simple --config build_mode
python3 test_runner.py --test bazel_simple --config sanitizer
python3 test_runner.py --test bazel_simple --config dependency

# 生成测试报告
python3 test_runner.py --all --report report.txt
```

#### 直接运行脚本

```bash
# Bazel 简单项目
cd bazel_simple
./test_configs/test_platform_configs.sh
./test_configs/test_build_modes.sh
./test_configs/test_sanitizers.sh
./test_configs/test_dependency_consumption.sh

# Bazel + CMake 项目
cd bazel_cmake
./test_configs/test_platform_configs.sh
./test_configs/test_build_modes.sh
./test_configs/test_sanitizers.sh
./test_configs/test_dependency_consumption.sh

# Bazel + CMake + Conan 项目
cd bazel_cmake_conan
./test_configs/test_platform_configs.sh
./test_configs/test_build_modes.sh
./test_configs/test_sanitizers.sh
./test_configs/test_dependency_consumption.sh
```

### 附录 C: 相关文档

| 文档 | 描述 |
|------|------|
| [test_utils.py](test_utils.py) | 测试工具函数实现 |
| [test_runner.py](test_runner.py) | 测试运行器实现 |
| [README.md](README.md) | 测试概述 |

---

**文档版本**: 1.1
**最后更新**: 2026-05-03
**维护者**: EROS Forge Team
