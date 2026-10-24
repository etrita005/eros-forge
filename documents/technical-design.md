# Forge 技术设计

本文说明 Forge 的模块、配置流和制品契约。产品要求见[需求](requirements.md)，API 用法见 [CMake](cmake-forge.md)、[CMake/Conan](cmake-conan-forge.md)和[打包](deb-packaging.md)，验证方法见[测试设计](test-design.md)。

本机 Linux/amd64 构建镜像与 `forge-bazel`、`forge-shell` 已接入；它们是本地锁定的开发入口，不是可远程获取的官方多架构镜像，也不等于下述发布和验收要求均已满足。实际交付范围及待办见第 10 节。

## 1 模块与数据流

```text
固定平台镜像 + 宿主 Bazel 入口 / 交互 shell
                     |
          容器内 Bazel 客户端与服务端
                     |
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
                  CI归档
                     |
       独立目标环境执行，不由构建容器替代
```

| 入口 | 职责 |
| --- | --- |
| [本地镜像锁](../docker/image.lock.json)；官方发布清单（待实现） | 本地锁定 Linux/amd64 镜像 ID、工具环境与缺失的 SDK；目标发布要求按执行架构提供可获取的平台镜像摘要 |
| [forge-bazel](../forge-bazel) / [forge-shell](../forge-shell) | 本机核验镜像与环境、挂载工作区、复用容器并透传 Bazel 参数或进入交互 shell；完整入口契约仍待验收 |
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

构建镜像按执行 CPU 选择，不按目标 CPU 选择。本地仅有已构建并锁定的 x86_64 镜像，可承载原生 x86_64 和交叉 ARM64 的构建层验证；`Dockerfile.arm64` 是独立的 ARM64 候选配方，尚无已构建/验收的 ARM64 镜像或锁。启用 Docker `--platform` 或 binfmt/QEMU 仿真不会自动扩展 Forge 构建执行平台的支持矩阵，本身也不构成目标运行证据；CI 在匹配目标设备或模拟器上的实际执行仍按 D17 单独验收。

<a id="toolchains"></a>

## 3 构建环境、工具与 SDK

### 3.1 镜像交付与发布身份

目标官方环境采用预构建 OCI 镜像，以 Docker 为标准运行时。完整交付应让开发与 CI 按发布清单获取相同执行架构的镜像，不在普通构建中执行 Dockerfile、安装工具或追踪浮动标签。目前仅有本地已构建镜像，不具备远程获取能力。

| 交付项 | 设计约束 |
| --- | --- |
| 构建配方 | 固定基础镜像摘要、系统包版本及可重取来源、工具归档摘要、Python 传递依赖；SDK 存在时固定其来源与摘要 |
| 平台镜像 | 分别发布 Linux x86_64、ARM64 镜像；以具体平台 manifest 摘要选择，不能只记录多架构标签或索引摘要 |
| 发布清单 | 关联执行平台、最终镜像摘要、工具环境基线、SDK 身份/缺失状态及支持的宿主与运行时条件；升级需显式评审 |
| 工具布局 | 固定编译器、binutils、Bazel、CMake、Conan、Python 和辅助工具的安装路径；构建用户不能修改工具或 SDK 安装目录 |
| 验收工具 | 所选验收范围需要的 Git、打包检查工具、GDB、Conan 测试服务等也固定版本及依赖，不以运行时 bootstrap 最新候选补齐官方环境 |

完整发布基线需在镜像发布时生成并与最终平台摘要关联。当前本地锁记录实际镜像 ID、工具环境摘要和 SDK 缺失身份，`docker/verify_environment.py` 在入口每次调用前重新采集并与该锁比较；不能把每次重新采集的身份自动当成可信基线。正式发布仍需可获取的平台摘要、工具来源和升级审核。

目前启动入口要求本地标签 `eros-forge-builder:local` 所指镜像 ID 和架构与锁一致；镜像缺失、环境不匹配或 Docker 不可用时失败，不自动拉取、重建或回退裸机。复用容器会核对镜像、用户、工作区/实例标签、绑定挂载、HOME 与必要环境、host 网络及基本安全选项；不匹配则拒绝继续使用。完整受支持宿主/运行时矩阵和恶意容器注入等仍未验收。镜像版本回退只能显式选择已评审清单，不能在原容器内降级软件。

<a id="local-image-baseline"></a>

#### 本地镜像构建与基线更新

`Dockerfile.amd64` 使用清华 Ubuntu APT 镜像安装 x86_64/ARM64 交叉工具；`Dockerfile.arm64` 使用清华 `ubuntu-ports` 镜像提供 ARM64 原生/同 CPU 目标工具链所需安装布局。两者各自固定 Ubuntu 基础平台摘要、Bazel 9.0.0 架构专属可执行文件的 SHA256 和 Python 依赖哈希锁。APT 镜像上的包候选及下载可用性不能仅凭配方视为可重建的官方发布基线。宿主安装 Python 3、Docker 并准备源码；在 Forge 根目录按需构建已验证的 amd64 镜像：

```bash
docker build --platform linux/amd64 -f Dockerfile.amd64 -t eros-forge-builder:local .
# 仅在宿主 loopback 代理必需时替换上一行：
docker build --platform linux/amd64 -f Dockerfile.amd64 --network=host \
  --build-arg HTTP_PROXY=http://127.0.0.1:7890 \
  --build-arg HTTPS_PROXY=http://127.0.0.1:7890 \
  --build-arg http_proxy=http://127.0.0.1:7890 \
  --build-arg https_proxy=http://127.0.0.1:7890 \
  -t eros-forge-builder:local .
docker image inspect eros-forge-builder:local --format '{{.Id}} {{.Os}}/{{.Architecture}}'
```

构建参数只为 Dockerfile 中的下载步骤提供代理；基础镜像由 Docker daemon 拉取，Docker Hub 不可达时需单独配置 daemon 代理。代理设置与凭据都不写入镜像。

ARM64 候选配方应在**原生 Linux/arm64 Docker host** 执行 `docker build --platform linux/arm64 -f Dockerfile.arm64 -t eros-forge-builder:arm64-candidate .`，再独立验证工具、四种 preset 中 ARM64 对应的两种配置及示例/验收。当前 amd64 Docker daemon 没有 ARM64 binfmt/构建执行能力：拉取固定 ARM64 基础镜像成功，但运行其 `/usr/bin/true` 返回 `exec format error`，因此此处没有 ARM64 镜像 ID、环境基线或构建/测试 PASS。静态 Dockerfile 检查在此 amd64 builder 上会因基础镜像为 arm64 报平台不匹配，不能替代原生验收。OrbStack 中 host 网络与 macOS `127.0.0.1` 的代理可达性也需单独验证。

当前本地 ID 为 `sha256:81230a0b49d2e588491e1652164ad4c4aba853605366c306e73492a2883b1e30`，`docker/image.lock.json` 中 `environment_sha256` 为 `c5266612ed9cb4c94f39619e75d0c50d0b20f3fd3fdb8e2a9b4445020ada7f17`、`sdk_id` 为 `missing:/opt/eros`。这里锁定的是本机镜像 **ID**，不是可供远端拉取的平台 manifest digest；标签变化不能自动更新锁。需更新镜像时先检查新 ID、架构、配方来源，再从新镜像重新采集实际环境/SDK 身份。采集必须在容器可写 `/tmp` 下执行，因为 Conan 工具探测会在那里创建临时 home；以下命令不依赖旧锁，也不写源码：

```bash
docker run --rm --platform linux/amd64 --user "$(id -u):$(id -g)" \
  --mount "type=bind,src=$PWD,dst=$PWD,readonly" \
  --env "FORGE_SOURCE=$PWD" --workdir /tmp \
  eros-forge-builder:local python3 -c 'import json, sys
import os
from pathlib import Path
root = Path(os.environ["FORGE_SOURCE"])
sys.path.insert(0, str(root / "bazel/toolchain"))
import environment
manifest, _ = environment.capture(
    json.loads((root / "bazel/toolchain/environment_spec.json").read_text()), None, None)
print(manifest["environment_sha256"], manifest["sdk"]["id"])'
```

评审三个值后显式更新锁中的 `image`、`environment_sha256`、`sdk_id`，再用入口复验构建；锁未更新时入口拒绝新镜像。独立临时容器只用于采集，日常入口按 UID/GID 运行持久容器、通过 `--network=host` 访问宿主 loopback 代理，按需透传 `HTTP_PROXY`/`HTTPS_PROXY`/`NO_PROXY`。不要把本地更新写成 registry 发布或 ARM64 原生环境交付。

### 3.2 入口与配置边界

本地两个入口位于 Forge 根目录，共享 `forge_container.py` 的镜像选择、挂载、校验和状态管理逻辑；以下表格同时列出现行入口与应验收的语义。

| 入口 | 行为 |
| --- | --- |
| `./forge-bazel` | 可执行程序，无需 `source`；将 Bazel 启动选项、子命令、目标和参数作为 argv 透传给容器内 `bazel`；完整标准流/信号等价性仍需 TC-ENTRY 取证 |
| `./forge-shell` | 进入同一本机镜像和调用工作目录，容器内直接使用镜像中的 `bazel`，也可运行现有 Python 验收工具；不接受额外参数 |

宿主需 Python 3、Docker 和源码，不需安装 Bazel、CMake、Conan 或 SDK。Bazel 客户端、服务端、repository rule、工具发现及所有构建 action 均在容器内执行；Bazel 规则不调用 Docker，也不递归调用宿主包装入口。

平台、模式、sanitizer 和版本配置继续使用共享 `bazelrc`、build settings 与现有规则。入口不另设 `--arch`、`--mode` 等业务参数，不改写编译器 flags、Conan profiles 或多架构 transitions。Bazel `--jobs` 与 `--define=forge_jobs=N` 仍分别控制外层 action 和内部构建并行度，不由入口混为一个参数。

调用工作区而非 Forge 安装目录决定目标和 rc 解析。Forge 根模块的入口示例使用 `./forge-bazel --bazelrc=bazel/bazelrc build ...`；示例工作区在 `examples/` 通过其 `.bazelrc` 导入共享 rc，调用 `../forge-bazel build --config=debug //01-minimal-app:app`。shell 中进入相同目录后直接使用 `bazel`（Forge 根仍须显式 `--bazelrc=bazel/bazelrc`）。从子目录调用时保留对应工作目录。两种入口不隐式导入宿主用户 rc 或覆盖用户提供的启动选项。

入口只逐次透传 `DEB_VERSION` 与大小写两种代理变量 `HTTP_PROXY`、`HTTPS_PROXY`、`NO_PROXY`，不继承整个宿主环境；影响构建的值仍须声明到 Bazel 输入。交互 shell 修改配置后的调用只与具有相同有效环境的宿主调用比较。

入口使用 `docker exec --interactive`，仅在标准输入与输出均为终端时分配 TTY，将环境诊断写向 stderr；`--` 后的参数仍交给 Bazel。每次 exec 记录单独的容器 PID，宿主转发 SIGINT/SIGTERM 给该 PID；非 TTY 管道中断及同容器另一 shell 存活已由本地入口测试覆盖，TTY、复杂子进程及完整信号/退出码矩阵仍待 TC-ENTRY-02 验收。`bazel run` 在容器内运行程序；入口不自动运行交叉产物或提供仿真器。

### 3.3 容器与构建状态生命周期

本地入口已采用按工作区复用长驻容器、通过 `exec` 发起调用的模型。默认实例连续调用可复用容器内 Bazel 服务端及磁盘状态；每条命令结束不销毁容器。CI 的同镜像作业模式是目标要求，尚无实际 CI 验收。

状态命名空间由规范化工作区身份、执行平台镜像摘要、调用用户身份和实例标识共同确定。默认实例标识稳定，不按每次调用随机生成。Debug/Release 等构建变体仍由 Bazel 配置隔离，切换不要求清缓存。

同一实例的容器创建需要互斥，Bazel 请求按其服务端锁串行。本地入口以工作区级锁拒绝同一源码工作区的第二个运行中实例，避免不同实例争用 `bazel-bin` 等链接；需要并行构建请使用独立 checkout。不同工作区或环境版本不得共用活动 output base；允许共享的下载/磁盘/远程缓存须符合各自并发与身份契约，不能把整个 Bazel 状态目录当成通用共享缓存。未来如需同 checkout 真正并行，须另行隔离输出链接及报告并完成验收。

显式 `--bazelrc` 必须位于已声明挂载中；本地入口进一步要求 `--output_base`、`--output_user_root` 位于当前实例的状态目录，以免覆盖另一工作区/实例的构建状态。入口保留参数，不静默忽略或重写到另一目录。挂载外路径或冲突使用应明确诊断，不能通过扩大到整个宿主文件系统来伪装透明。

普通调用结束保留服务端；显式 `bazel shutdown` 仅结束对应服务端，不删除缓存。容器异常退出后只恢复已核验归属和环境身份的状态，不复用未完成的半成品。停止与清理操作只作用于明确归属的非活动实例，先保留所需证据；不得隐式 prune 全部容器或共享缓存。磁盘字节、inode 和历史 output base 均需有保留与回收策略。

### 3.4 工作区、权限与宿主条件

| 对象 | 挂载与权限约束 |
| --- | --- |
| 源码与模块布局 | 本地入口挂载 Forge 根与调用工作区，保留两者之间的路径关系；任意额外本地依赖及消费工作区拓扑仍须单独验收 |
| Git/Repo 元数据 | 保留 `.git` 引用可达的实际 Git 元数据；当前 Repo checkout 的元数据在 `eros/.repo/projects/forge.git`，仅挂载 `forge/` 不足；优先只读暴露必要元数据 |
| HOME 与构建状态 | 实例状态位于调用者 `~/.cache/eros-forge/<key>`，其 home/tmp 可写，`/tmp/kilo` 映射到实例 tmp；不挂载宿主整个 HOME、系统工具目录或用户 Conan 工作缓存 |
| 生成文件 | 映射调用者 UID/GID 或提供经验证的等价归属方案，使调用者能读取、修改和删除；正常构建不要求容器 root |

普通构建不修改源码、配方锁或模块锁。Bazel 输出链接和报告目录需明确定位；完全只读工作区必须另行验证输出链接、锁策略和报告路径，不能仅设置只读 bind mount 就宣称支持。显式 Conan 锁更新仍是独立维护操作，只允许写入选定的锁文件，不作为构建前置步骤。现有测试使用的 `/tmp/kilo` 等临时路径需在容器内准备为调用用户可写目录，不能依赖宿主偶然存在。

支持范围以声明的 Linux 执行架构、Docker 版本/模式、宿主内核与安全策略组合为准，不自动承诺 Docker Desktop、任意远程 daemon 或仿真执行环境兼容。容器内继续使用明确且验收过的 Bazel 沙箱策略；不能因为外层有 Docker 就关闭沙箱。宿主不满足必要条件时报告原因，不静默降级。

普通构建不使用 `--privileged`，不挂载 Docker socket。GDB/ptrace 等额外权限仅属于明确选择的调试验收配置，记录最小能力及安全策略差异；Sanitizer 的地址空间、宿主内核限制仍须单独取证。

镜像拉取、Bazel 模块获取和声明的 Conan 来源可能需要网络。固定输入不等于离线可用；离线能力需预置全部声明输入并独立验证。代理、证书和凭据按需最小注入，凭据不写入镜像、制品或日志，不通过挂载用户 Conan home 传递来源配置。

### 3.5 现有工具发现与校验

工具仓库 `@eros_host_tools` 提供 `env_manifest`、`all_tools`、`native_all` 和 `cross_arm64_all`。环境清单记录实际工具版本/摘要、GCC 支持文件、头文件与库、Python/Conan/CMake 安装、SDK 状态和支持的预设；实际文件也作为输入声明。

环境验证目标为 `//bazel/toolchain:validate_environment`。内容或版本不匹配时报错。环境升级必须产生相应新身份，不能只改一个版本标签。

当前实现发现已安装工具，而非获取固定工具链；[environment_spec.json](../bazel/toolchain/environment_spec.json) 精确约束 Bazel/CMake/Conan，但只约束 GCC/Python 主版本。因此镜像发布仍需锁定实际系统包和支持库。环境采集当前无条件探测原生与 ARM64 交叉工具链，首版镜像须满足两者，不能仅为原生示例省略交叉驱动。采集代码使用 `hashlib.file_digest`，实际 Python 需至少 3.11；PATH 中的解释器与 action 使用的 `/usr/bin/python3` 必须保持一致。

| 用途 | 工具选择 |
| --- | --- |
| 原生目标和执行工具 | 构建容器执行架构对应的 GCC 13 与原生 binutils |
| ARM64 交叉目标 | `/usr/bin/aarch64-linux-gnu-gcc-13`、`g++-13` 和同前缀 binutils |
| Conan host | 目标库的平台、模式、PIC、插桩和调试配置 |
| Conan build | 执行机器的原生配置，不继承目标 sanitizer |
| 符号提取 | 目标库使用目标 binutils，build-context 工具使用原生 binutils |

### 3.6 SDK 与发布边界

交叉预设使用系统交叉编译器的默认头文件、sysroot 和链接搜索路径。CMake 将 `/usr/aarch64-linux-gnu`、`/opt/eros` 作为查找根；没有把 `CMAKE_SYSROOT` 设置为 `/opt/eros`。交叉 ELF 解释器为 `/opt/eros/lib/ld-linux-aarch64.so.1`，运行库路径包含 `/opt/eros/lib`。

这些路径不等于完整 SDK 绑定证明。清单记录编译器实际搜索目录与运行库身份；SDK 存在时校验对应内容，缺失时标记运行身份未验证并允许构建层检查。满足发布要求仍需确认目标头文件、链接库、加载器和部署 glibc 来自匹配 SDK，并在目标环境运行。

容器化只固化现有工具布局，不由入口隐式注入 `--sysroot`、替换 glibc 或放宽校验。建立完整目标 SDK 属于单独的工具链契约变更。当前整个 `/opt/eros` 参与 SDK 身份采集，不作为可变的包安装测试目录；安装/卸载验收应使用独立目标环境。没有 SDK 的镜像须明确记录缺失状态，不能用空目录或加载器路径冒充完整 SDK。

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

平台镜像摘要用于环境获取和追踪，不会自动进入 Bazel action key。相关工具、SDK 和环境差异仍必须经声明输入影响对应 action 及 Conan 变体身份；按镜像划分本地状态也不能替代正确失效测试。合法升级需要在可访问旧缓存的条件下验证三条构建路径，不只证明新目录里执行了一次冷构建。

构建记录需关联实际平台镜像摘要、发布基线、采集到的环境/SDK 身份、源码提交与未提交内容摘要、依赖锁、有效配置及产物/符号。平台摘要由宿主入口或 CI 根据实际运行镜像核验，不接受用户随意设置的版本字符串作为证明。固定镜像不固定源码；发布仍使用固定提交/归档及子模块，不以 Repo 浮动分支名称代替源码身份。

## 9 执行与验证边界

Forge 导出测试闭包和入口说明，不负责设备调度或在构建机运行交叉程序。原生运行、解包运行、干净目标安装、跨机缓存命中是不同验证范围。

验收 runner 每次调用创建独立 output base，这不适用于普通开发入口的服务端复用策略。容器接入时须检查所有子 Bazel 调用继承该隔离设置，避免辅助 verifier 落回默认 output base。关闭服务器不删除缓存；逐文件工具输入和沙箱会消耗 inode，执行者需归档所需证据并用 `bazel clean --expunge` 回收明确属于该次任务的目录。CPU 并行度预算不代替文件系统容量管理。

本地容器 shell 可以直接调用现有验收 runner、unit tests 和 `examples/check.py`（在 `examples/` 中运行 `python3 check.py`），不将它们替换为 `bazel test //...`；仓库包含故意失败的目标，统一入口也不默认执行全仓通配构建。此处描述命令可调用，不声称套件已在本镜像全部通过。原生/交叉 scope 必须显式选择，不能因设置交叉 preset 就直接执行现有全部运行用例。

执行状态、失败命令和证据以每次生成的报告为准。缺少 SDK、目标机器、独立缓存或 CI 环境的范围必须明确为 BLOCKED，不以配置文本、构建退出零或文件存在替代实际行为验收。

当前部分 SDK 替换、跨机缓存及目标执行 scope 是未接通外部执行的 BLOCKED 占位；新增镜像不会自动启用它们。非 strict runner 退出零可以包含 BLOCKED，官方验收门禁需使用明确的适用 scope 和 `--strict`，并核对报告完整性。入口透传退出码，不把阻塞、失败或中断改写成成功。

## 10 本机交付与后续发布边界

本机 linux/amd64 镜像已构建并以 ID 锁定；`forge-bazel` 和 `forge-shell` 已提供持久非 root 容器入口。`examples/check.py` 在该容器中验证了示例 01–04 的 Debug/Release 八次原生运行、锁和用户缓存审计；现有 runner 的 TC-ENV-01/local、TC-ENV-02/local、TC-DEP-05/local 严格模式通过。`docker/image.lock.json` 是本机环境基线，不是远程镜像发布清单或 CI 通过证明；不得仅据此认定新容器矩阵或目标部署已通过。

| 后续事项 | 当前边界 |
| --- | --- |
| 匹配目标 SDK 的内容与来源 | 当前 `sdk_id=missing:/opt/eros`，交叉构建至多形成构建/ELF 证据；编译与部署 glibc/loader 匹配、目标运行及发布仍需单独取证，不降低 D02 |
| 官方可获取镜像与升级 | 当前只锁本地 Linux/amd64 镜像 ID，无 registry、ARM64 原生镜像或完整可重建发布清单；APT 包精确来源和多架构平台摘要需审核 |
| 环境/入口验收 | 独立入口单测/本机 Docker 集成测试覆盖镜像 ID 拒绝、复用容器挂载检查、服务端复用、单 PID 中断与工具篡改拒绝；同一 checkout 多实例并行被主动拒绝。TC-ENV-05..07、TC-ENTRY-01..05、TC-CI-03 仍未完整接入 runner，复杂信号/并发契约、CI 与独立机器缓存不宣称 PASS |
| 支持的宿主与权限 | 本地 Linux/amd64、可用 Docker、Python 3 和源码；持久容器使用调用者 UID/GID 与 host 网络，无 Docker socket/privileged；Docker 版本、内核、沙箱和调试权限矩阵仍需验收 |

后续发布工作仍应补足可获取镜像、匹配 SDK、ARM64 执行环境和测试证据，不能以本地容器可用替代完整四预设或目标交付要求。
