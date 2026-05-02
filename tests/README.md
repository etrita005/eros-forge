# EROS Forge 测试用例集合

## 概述

本测试集合用于验证 EROS Forge 构建系统的各项功能，包括：
- 平台配置（原生编译和交叉编译）
- 构建模式（Debug 和 Release）
- Sanitizer 支持（ASan、TSan、MSan、UBSan）
- CMake 集成
- Conan 集成
- 跨模块依赖消费（静态库、动态库、头文件）

**测试统计**:
- 测试项目数：3
- 测试用例总数：48
- 自动化检查：制品结果验证 + 编译选项验证

详细测试用例清单请参考：[TEST_CASES.md](TEST_CASES.md)

## 测试项目

### 1. Bazel9 C++ 简单项目测试
- 位置：`tests/bazel_simple/`
- 测试内容：纯 Bazel C++ 项目的构建和验证
- 测试用例数：16 (4 个平台配置 + 2 个构建模式 + 4 个 Sanitizer + 4 个依赖消费)
- 验证项：制品结果、编译选项
- 依赖消费测试：`consumer/` 子目录验证导出的静态库、动态库和头文件可被其他模块消费

### 2. Bazel9 + CMake 项目测试
- 位置：`tests/bazel_cmake/`
- 测试内容：使用 cmake_forge 宏构建 CMake 项目
- 测试用例数：16 (4 个平台配置 + 2 个构建模式 + 4 个 Sanitizer + 4 个依赖消费)
- 验证项：制品结果、编译选项、CMake 集成
- 依赖消费测试：`consumer/` 子目录验证 CMake 构建的库可被其他模块消费

### 3. Bazel9 + CMake + Conan 项目测试
- 位置：`tests/bazel_cmake_conan/`
- 测试内容：使用 cmake_conan_forge 宏构建带 Conan 依赖的项目
- 测试用例数：16 (4 个平台配置 + 2 个构建模式 + 4 个 Sanitizer + 4 个依赖消费)
- 验证项：制品结果、编译选项、CMake 集成、Conan 依赖
- 依赖消费测试：`consumer/` 子目录验证 CMake+Conan 构建的库可被其他模块消费

## 测试配置

### 平台配置
- `--config=linux_x86_64`: x86_64 原生编译
- `--config=linux_arm64`: ARM64 原生编译
- `--config=linux_x86_64_cross_arm64`: 交叉编译（x86_64 -> ARM64）
- `--config=linux_arm64_cross_arm64`: 交叉编译（ARM64 -> ARM64，自定义 glibc）

### 构建模式
- `--config=debug`: 调试模式（无优化，包含调试信息）
- `--config=release`: 发布模式（-O3 优化，符号分离）

### Sanitizer 配置
- `--config=tsan_test`: ThreadSanitizer（测试专用）
- `--config=tsan`: ThreadSanitizer（构建专用）
- `--config=msan`: MemorySanitizer
- `--config=no_sanitizer`: 禁用 Sanitizer

## 环境要求

### 必需工具
- Bazel 9.0 或更高版本
- GCC 13 或更高版本
- Python 3.8 或更高版本
- CMake 3.16 或更高版本（用于 CMake 项目测试）
- Conan 2.0 或更高版本（用于 Conan 项目测试）

### 交叉编译环境
- aarch64-linux-gnu-gcc
- aarch64-linux-gnu-g++
- 自定义 glibc（可选）

## 运行测试

### 前置准备

在运行测试之前，请确保：
1. 已安装所有必需工具（见环境要求章节）
2. 已设置交叉编译工具链（如需测试交叉编译）
3. 已安装自定义 glibc 到 `/opt/eros/lib`（如需测试交叉编译）

### 运行所有测试
```bash
cd eros/forge/tests
python3 test_runner.py --all
```

### 运行指定测试
```bash
# 运行 Bazel 简单项目测试
python3 test_runner.py --test bazel_simple

# 运行 CMake 项目测试
python3 test_runner.py --test bazel_cmake

# 运行 CMake + Conan 项目测试
python3 test_runner.py --test bazel_cmake_conan
```

### 运行指定配置测试
```bash
# 只测试平台配置
python3 test_runner.py --test bazel_simple --config platform

# 只测试构建模式
python3 test_runner.py --test bazel_simple --config build_mode

# 只测试 Sanitizer
python3 test_runner.py --test bazel_simple --config sanitizer

# 只测试依赖消费
python3 test_runner.py --test bazel_simple --config dependency
```

### 单独运行测试脚本
```bash
# 进入测试项目目录
cd eros/forge/tests/bazel_simple

# 运行平台配置测试
./test_configs/test_platform_configs.sh

# 运行构建模式测试
./test_configs/test_build_modes.sh

# 运行 Sanitizer 测试
./test_configs/test_sanitizers.sh

# 运行依赖消费测试
./test_configs/test_dependency_consumption.sh
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
   - 验证消费者二进制架构和执行结果

### 测试输出

测试执行时会输出：
- 当前测试项目名称
- 测试配置信息
- 构建命令和输出
- 验证结果（✓/✗）
- 测试通过/失败状态

示例输出：
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

## 测试验证内容

### 制品结果验证
每个测试都会验证以下制品结果：

1. **二进制文件基础验证**
   - 文件是否存在且可执行
   - 文件架构是否正确（x86_64 或 aarch64）
   - 文件大小是否合理
   - 文件权限是否正确

2. **平台配置相关验证**
   - 原生编译：验证架构正确
   - 交叉编译：验证动态链接器和 RUNPATH 设置

3. **构建模式相关验证**
   - Debug 模式：验证包含调试符号，Sanitizer 启用
   - Release 模式：验证符号分离，优化级别正确

4. **Sanitizer 相关验证**
   - 验证 Sanitizer 符号是否存在
   - 验证 Sanitizer 功能是否正常

5. **依赖库验证**
   - 验证动态库依赖是否正确
   - 验证共享库是否正确链接

6. **运行时验证**
   - 原生编译：程序能够正常运行
   - 交叉编译：验证架构和链接器配置

详细验证函数实现请参考：[test_utils.py](test_utils.py)

### 编译选项验证
每个测试都会验证以下编译选项：

1. **平台配置编译选项验证**
   - 编译器路径是否正确
   - 目标架构标志是否正确
   - 交叉编译链接标志是否正确

2. **构建模式编译选项验证**
   - Debug 模式：-g, -O0/-Og, Sanitizer 标志
   - Release 模式：-O3, -DNDEBUG, 符号分离标志

3. **Sanitizer 编译选项验证**
   - 验证 -fsanitize 标志是否正确

4. **C++ 标准验证**
   - 所有配置必须使用 C++20 标准

详细验证函数实现请参考：[test_utils.py](test_utils.py)

## 测试结果解读

### 成功标志
- 所有构建命令成功完成
- 二进制文件架构正确
- 交叉编译的动态链接器和 RUNPATH 正确设置
- Release 模式符号分离
- Sanitizer 正确启用
- 程序能够正常运行

### 失败排查
1. **构建失败**
   - 检查 Bazel 版本是否正确
   - 检查工具链是否正确安装
   - 检查环境变量设置

2. **架构不匹配**
   - 检查平台配置是否正确
   - 检查交叉编译工具链是否正确安装

3. **动态链接器错误**
   - 检查自定义 glibc 是否正确安装
   - 检查工具链配置中的链接器路径

4. **Sanitizer 未启用**
   - 检查编译选项是否正确传递
   - 检查是否与其他 Sanitizer 冲突

## 测试报告

测试完成后会生成详细的测试报告，包括：
- 测试执行时间
- 测试通过/失败数量
- 失败测试的详细错误信息
- 构建日志

报告位置：`tests/reports/test_report_<timestamp>.txt`

## 持续集成

可以将测试集合集成到 CI/CD 流程中：

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
          # 安装 Bazel 9.0
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

## 贡献指南

### 添加新测试
1. 在对应测试项目目录下添加测试脚本
2. 更新 test_runner.py 以支持新测试
3. 更新 README.md 文档

### 修改现有测试
1. 修改对应的测试脚本
2. 确保测试仍然通过
3. 更新相关文档

## 文档索引

本测试集合包含以下文档：

| 文档 | 描述 |
|------|------|
| [README.md](README.md) | 测试概述（当前文档） |
| [TEST_GUIDE.md](TEST_GUIDE.md) | **完整测试指南**（包含所有测试用例、环境配置、运行方法、验证说明） |

**推荐阅读**:
- **快速了解**: 阅读本 README.md
- **完整指南**: 阅读 [TEST_GUIDE.md](TEST_GUIDE.md) - 包含所有详细信息

## 许可证

本测试集合遵循 EROS 项目的许可证协议。
