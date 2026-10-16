# Forge 技术设计

本文说明 Forge 的模块、配置流和制品契约。产品要求见[需求](requirements.md)，API 用法见 [CMake](cmake-forge.md)、[CMake/Conan](cmake-conan-forge.md)和[打包](deb-packaging.md)，验证方法见[测试设计](test-design.md)。

## 1 模块与数据流

```text
受控工具环境 + 源码 + 平台/模式 + 包级锁
                     |
             配置归一化、环境校验
                     |
       +-------------+------------------+
       |             |                  |
   Bazel C++    rules_foreign_cc    ConanInstall
       |          CMake构建        完整依赖快照
       |             |                  |
       |             |              CMakeBuild
       +-------------+------------------+
                     |
           CcInfo / 安装映射 / 符号
                     |
             运行闭包、tar/deb、测试包
                     |
               CI归档与目标执行
```

| 入口 | 职责 |
| --- | --- |
| [MODULE.bazel](../MODULE.bazel) | 模块依赖、工具仓库和四套 C++ 工具链注册 |
| [bazelrc](../bazel/bazelrc) | 平台、模式、sanitizer、版本环境变量 |
| [config](../bazel/config/) | build setting、有效配置校验和选择函数 |
| [toolchain](../bazel/toolchain/) | 工具发现、身份清单、环境验证、配置生成 |
| [cmake_forge.bzl](../bazel/cmake_forge.bzl) | Foreign-CC 构建及严格安装导出 |
| [cmake_conan_forge.bzl](../bazel/cmake_conan_forge.bzl) | Conan 快照、CMake action 和 `CcInfo` |
| [tools](../bazel/tools/) | Conan/CMake 驱动、快照部署、锁更新 |
| [runtime.bzl](../bazel/runtime.bzl) | 原生包装规则、安装映射和运行闭包 aspect |
| [deb.bzl](../bazel/deb.bzl)、[packaging](../bazel/packaging/) | 布局、闭包/架构校验、包与符号归档 |

## 2 平台与配置

`//bazel/config:preset` 取 `auto` 或四种平台预设。`auto` 按受支持的执行 CPU 选择原生构建；显式预设同时约束执行 CPU 和目标平台。多配置规则同步设置平台与该 setting。

`//bazel/config:sanitizer` 取 `none|asan|ubsan|tsan|asan_ubsan`。归一化函数结合 setting、启用/禁用 features 校验有效集合。ASan 与 UBSan 的两种请求顺序得到组合语义；不兼容组合和 MSan 在分析/配置阶段拒绝。

Debug 不隐式启用 sanitizer。Release 使用优化和 `-g`，默认请求 `separate_debug_info`；显式禁用该 feature 可关闭独立符号交付。C++ 运行库链接策略由 `static_cpp_runtime` 控制。

[generate_files.py](../bazel/toolchain/generate_files.py)集中生成平台数据、CMake toolchain 和 Conan profiles。`--check` 只核对生成结果，不写文件。

<a id="toolchains"></a>

## 3 工具与 SDK

工具仓库 `@eros_host_tools` 提供 `env_manifest`、`all_tools`、`native_all` 和 `cross_arm64_all`。环境清单记录实际工具版本/摘要、GCC 支持文件、头文件与库、Python/Conan/CMake 安装、SDK 状态和支持的预设；实际文件也作为输入声明。

环境验证目标为 `//bazel/toolchain:validate_environment`。内容或版本不匹配时报错。环境升级必须产生相应新身份，不能只改一个版本标签。

| 用途 | 工具选择 |
| --- | --- |
| 原生目标和执行工具 | 宿主 GCC 13 与原生 binutils |
| ARM64 交叉目标 | `/usr/bin/aarch64-linux-gnu-gcc-13`、`g++-13` 和同前缀 binutils |
| Conan host | 目标库的平台、模式、PIC、插桩和调试配置 |
| Conan build | 执行机器的原生配置，不继承目标 sanitizer |
| 符号提取 | 目标库使用目标 binutils，build-context 工具使用原生 binutils |

交叉预设使用系统交叉编译器的默认头文件、sysroot 和链接搜索路径。CMake 将 `/usr/aarch64-linux-gnu`、`/opt/eros` 作为查找根；没有把 `CMAKE_SYSROOT` 设置为 `/opt/eros`。交叉 ELF 解释器为 `/opt/eros/lib/ld-linux-aarch64.so.1`，运行库路径包含 `/opt/eros/lib`。

这些路径不等于完整 SDK 绑定证明。清单记录编译器实际搜索目录与运行库身份；SDK 存在时校验对应内容，缺失时标记运行身份未验证并允许构建层检查。满足发布要求仍需确认目标头文件、链接库、加载器和部署 glibc 来自匹配 SDK，并在目标环境运行。

## 4 Conan 锁与快照

`cmake_conan_forge` 的普通构建必须提供 `lockfile`。`conan_install` 接收配方、锁、附属输入、host/build profiles，以及声明的来源配置或缓存归档。

1. 在 action 私有目录中创建 `HOME` 和 `CONAN_HOME`，固定工具入口与 Python 路径。
2. 使用严格锁和 `--build=missing` 获取匹配包或构建缺失包，不启用部分锁回退。
3. 将环境、编译/链接 flags 与符号要求纳入包身份，并校验配方没有抹除必要维度。
4. 物化 host/build 包文件、相对 SONAME 链和可迁移生成元数据，记录 recipe revision、package ID、package revision 和文件摘要。
5. 删除私有 Conan home。下游只读取声明的快照，不访问用户缓存。

快照保留 build-context 包供构建工具使用，目标安装树只纳入 host-context 包。配方源码快照保留实际源码、patch 和相关生成头文件，不归档 CMake 缓存、编译对象或 Conan 环境脚本。

配方锁不固定全部二进制内容。HTTP 来源的二进制身份按声明的来源元数据校验；输入缓存归档由其内容参与身份。源码索引提供锁定配方的源码构建路径。不能把未约束的服务端二进制选择当作安全缓存输入。

锁更新由 `//bazel/tools:conan_lock_update` 在普通构建外显式执行。它不继承用户 remotes，调用者指定 `--file-remote` 或 `--remote NAME=URL`，必要时指定 profiles。更新后评审并提交锁和导出接口。

## 5 CMake 构建与导出

`cmake_forge` 使用 `rules_foreign_cc` 执行 CMake，再统一安装导出。flags overlay 是目标配置的数据依赖；执行工具属于 exec 配置，不能用 exec transition 生成目标 ABI flags。

`cmake_conan_forge` 依次组织 ConanInstall 和独立 CMakeBuild。CMake 在隔离源码/构建目录配置，加载目标 toolchain 和快照元数据，构建后通过 `cmake --install` 写入声明的安装树。目标快照加入受控查找根，不放开任意宿主包搜索来补齐交叉依赖。

所有 `.cmake`、源码、头文件、模板、脚本和配方附属文件均须声明。安装路径精确匹配 `exports`，不按 basename 搜索。程序、archive、共享库和头文件按声明类型/权限校验；架构检查属于相应的运行/打包校验路径，不把文件格式检查称为架构验证。

`exports` 在分析阶段定义公开接口：

| 字段 | 内容 |
| --- | --- |
| `headers`、`includes`、`defines` | 公开编译接口 |
| `libraries` | 逻辑库及 `static`、`pic_static`、`shared` 备选路径 |
| `linkopts` | 必要传递链接项 |
| `binaries` | 实际安装的程序 |
| `runtime_files` | 显式插件/资源运行根 |

`CcInfo` 必须在分析阶段构造。执行阶段生成和验证已声明文件，不动态扩展依赖图。静态/PIC/共享形式属于同一逻辑库的选择关系；维护者显式列出静态传递库。版本化共享库的 `shared` 路径使用运行 SONAME 文件名。

完整安装树保留 SONAME 相对链接；单个 `.exports` 文件副本可解引用安装链接。`cmake_build` 不是 executable rule；程序为普通真实文件，纯库目标不提供占位程序。

`try_compile` 不执行探测程序；`try_run` 需要有效目标探测值或实际 executor。静态探测不能代替真正的可执行链接和目标运行验收。

## 6 Provider 与运行闭包

| 接口 | 作用 |
| --- | --- |
| `CcInfo` | 编译和链接信息，供原生 Bazel 消费者使用 |
| `DefaultInfo`/runfiles | 默认文件与运行数据 |
| `ErosInstallInfo` | `entries` 安装映射及 `manifests` 来源记录 |
| `ErosDebugInfo` | 符号文件集合和身份清单 |
| `eros_debug_info` 输出组 | 显式收集业务与传递依赖符号 |

`eros_cc_binary`、`eros_cc_library` 组合原生 C++ 语义与安装/符号输出。运行 aspect 沿 `deps`/`data` 收集映射、runfiles 和必要库。`eros_install_map` 定义非默认目标路径，CMake 的 `runtime_files` 定义同一目标的插件/资源根。

闭包从程序、显式插件和资源出发，按 `DT_NEEDED` 与相对 RUNPATH 解析依赖，裁剪未选择的共享备选。不能仅靠 ELF 扫描发现 `dlopen` 插件。每个共享库层级需要自己的加载路径。

```text
/opt/eros/lib/                  受控部署运行库
/opt/eros/<package>/bin/        程序
/opt/eros/<package>/lib/        私有共享库和插件
/opt/eros/<package>/share/      资源
```

闭包检查拒绝缺失私有依赖、冲突映射、悬空/越界链接。内容和归一化权限相同的重复文件去重，保留必要 SONAME 关系。不同包的私有目录不构成同进程多版本 ABI 隔离保证。

## 7 打包与多配置

`pkg_eros_tar` 和 `eros_test_package` 消费运行闭包并进行布局和依赖检查。`pkg_eros_deb` 接受 tar，校验归档安全及 ELF 与架构字段的一致性；任意外部 tar 不会因此自动获得完整运行闭包保证。

版本优先级为非空属性、声明的 `DEB_VERSION` action 环境、define、`0.1.0`。x86_64 映射 `amd64`，ARM64 映射 `arm64`；未知 CPU 报错。`all` 显式声明，不能包含目标 ELF。

`pkg_eros_deb_multiarch` 用 split transition 设置每个分支的真实平台和 Forge preset，分别构建 payload。输出名区分预设，保留分支身份；不支持的执行工具链或分支输入导致失败。ARM64 原生与 ARM64 交叉分支属于两种配置，不是两个 CPU 架构。

## 8 调试与缓存

独立符号流程为保留链接输入、提取 `.debug`、对发布副本去调试节、写入 debuglink/build ID 与摘要关联。静态 archive 保留后续链接需要的 DWARF，并提供独立调试副本。缺失符号或不完整 split-DWARF skeleton 不满足独立归档契约。

符号包和测试包保留源文件清单、源码映射、环境/锁/配置身份，校验错配和摘要损坏。CI 负责保存并用于实际目标 core 分析。

自定义 action 使用 `no-remote-exec`，允许符合输入/输出契约的缓存结果复用。工具文件、清单、源码、锁、导出描述和配置均是输入。Foreign-CC 的工具/环境边界须结合实际 action 图审查；独立机器上的缓存命中和迁移测试才是跨机验收证据。

## 9 执行与验证边界

Forge 导出测试闭包和入口说明，不负责设备调度或在构建机运行交叉程序。原生运行、解包运行、干净目标安装、跨机缓存命中是不同验证范围。

测试 runner 每次调用创建独立 output base，关闭服务器不删除缓存。逐文件工具输入和沙箱会消耗 inode；执行者需归档所需证据并用 `bazel clean --expunge` 回收明确属于该次任务的目录。CPU 并行度预算不代替文件系统容量管理。

执行状态、失败命令和证据以每次生成的报告为准。缺少 SDK、目标机器、独立缓存或 CI 环境的范围必须明确为 BLOCKED，不以配置文本、构建退出零或文件存在替代实际行为验收。
