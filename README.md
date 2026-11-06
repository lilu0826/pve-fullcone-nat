# PVE 原生 MASQUERADE Full Cone NAT

目标：按 [task.md](task.md)，仅修改 PVE `7.0.14-23-pve` 内核，使 IPv4 TCP/UDP MASQUERADE 支持 EIM/EIF，保留现有用户态规则。

**当前状态：源码研究发现阻断问题，尚未实现、编译或通过验收。没有可安装的 Full Cone 内核包。**

已锁定准确的 PVE 打包提交、内核子模块提交、ZFS 子模块提交和参考补丁提交；已核对用户提供的宿主机版本、MODVERSIONS 和模块 vermagic。参考实现不能直接作为本项目的自动入站处理实现：它没有隔离普通 SNAT 映射，而且 fully-random 路径不保证 EIM。

遵循任务第 10 节的停止条件，当前不提供未经验证的内核补丁、构建工作流或安装命令。

- [源码审查、阻断原因与替代设计](docs/source-review.md)
- [实际验证记录与后续验收要求](docs/validation-status.md)
- [固定源码与补丁摘要](sources.lock.json)
- [宿主机已确认信息](docs/host-baseline.md)
- [只读宿主机信息采集脚本](scripts/collect-host-info.sh)
- [本地参考材料校验脚本](scripts/verify-references.py)

`.research/` 是被 Git 忽略的本地研究缓存，其中的原始参考补丁**不是**已适配的交付补丁。不要在生产 PVE 主机上应用它们或替换 `.ko`。
