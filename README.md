# PVE 原生 MASQUERADE Full Cone NAT

目标：按 [task.md](task.md)，仅修改 PVE `7.0.14-23-pve` 内核，使 IPv4 TCP/UDP MASQUERADE 支持 EIM/EIF，保留现有用户态规则。

**当前状态：提交 `47b1400` 已通过启用 17 项、关闭 13 项启动测试，下载工件已复核。完整 PVE Debian 包正在构建，尚无通过全部验证的安装包。** 实际状态以 [本轮 Actions](https://github.com/lilu0826/pve-fullcone-nat/actions/runs/42227692753) 和 [验证记录](docs/validation-status.md) 为准；PVE 实机和独立公网环境尚未验收。

已锁定准确的 PVE 打包提交、内核子模块提交、ZFS 子模块提交和参考补丁提交；已核对用户提供的宿主机版本、MODVERSIONS 和模块 vermagic。参考实现不能直接作为本项目的自动入站处理实现：它没有隔离普通 SNAT 映射，而且 fully-random 路径不保证 EIM。

仓库包含三段式内核补丁、固定源码获取/应用脚本、完整 PVE 打包流程，以及实际启动内核的 TCP/UDP 回归测试。初期源码报告保留为历史记录，当前实现与验证状态见设计和测试文档。

- [源码审查、阻断原因与替代设计](docs/source-review.md)
- [实际验证记录与后续验收要求](docs/validation-status.md)
- [固定源码与补丁摘要](sources.lock.json)
- [宿主机已确认信息](docs/host-baseline.md)
- [只读宿主机信息采集脚本](scripts/collect-host-info.sh)
- [本地参考材料校验脚本](scripts/verify-references.py)
- [实现设计、映射寿命与冲突优先级](docs/design.md)
- [并存安装与回滚](docs/install-and-rollback.md)
- [GitHub Actions](https://github.com/lilu0826/pve-fullcone-nat/actions/workflows/kernel.yml)

补丁顺序：`0001-sonic-984.patch` → `0002-sonic-987.patch` → `0003-pve-native-fullcone.patch`。前两份是锁定参考补丁在目标 PVE 源码上的重排，第三份负责仅 IPv4 MASQUERADE 自动启用及入站路径。没有 985/986，没有用户态 NAT 修改。补丁输入、结果和文件 SHA-256 见 `patches/manifest.json`。

Actions 先启动精简测试配置的同源内核，分别测试 Kconfig 开/关；测试通过后才使用 PVE 配置构建完整 Debian 包。精简测试内核不作为安装包交付。构建失败也保留日志，没有部署步骤。

`.research/` 是被 Git 忽略的本地研究缓存，其中的原始参考补丁**不是**已适配的交付补丁。不要在生产 PVE 主机上应用它们或替换 `.ko`。
