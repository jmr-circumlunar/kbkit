# WorkBuddy 连接器

kbkit 通过 WorkBuddy 的 CLI + Skill 运行。WorkBuddy 5.0.0 及以上提供托管 Python。首次连接时，安装器从 GitHub Release 下载自包含的 `kbkit.pyz`，校验 SHA-256 和字节数，再写入本机的连接器目录。Skill 在首次使用时确认知识库路径。定时维护的调度与授权保存在 WorkBuddy。kbkit 使用本地 CLI，无需第三方账号或服务凭证。 [WorkBuddy 连接器规范](https://open.workbuddy.cn/docs/connector)

## 下载安装包并提审

1. 从 [kbkit 的 GitHub Releases](https://github.com/jmr-circumlunar/kbkit/releases) 找到所需的 `workbuddy-v*` 版本，下载 Assets 中的 `kbkit-workbuddy-<版本>.zip`。同一 Release 提供 `kbkit.pyz` 作为安装器下载的运行包，以及 `release.json` 作为版本和校验记录。
2. 在完成资质认证的 WorkBuddy 开放平台账号下创建连接器，类型选 CLI，标识使用 `circumlunar-kbkit`，上传连接器 ZIP。更新时继续使用同一条目。 [WorkBuddy 开放平台](https://open.workbuddy.cn/)
3. 在 WorkBuddy 客户端验证首次连接、知识库查询和断开连接，然后提审。审核通过后在开放平台发布。断开连接只移除本机连接状态，知识库和运行包仍可保留。 [WorkBuddy 发布规则](https://open.workbuddy.cn/docs/connector)

## 维护和发布新版本

GitHub `main` 维护同一套核心 CLI 与 WorkBuddy 适配。连接器的元信息、安装器、图标和 Skill 位于本目录，构建器根据选定提交生成 `cli.json`。核心包版本来自代码，连接器版本来自 `connector-meta.json`，构建记录分别保存两者及完整 Git SHA。

1. 准备交给 WorkBuddy 审核的更新时，递增 `connector-meta.json` 中的版本，将相关修改和版本号一起提交并推送到 GitHub `main`。日常改动会通过构建检查。
2. 在通过验收的提交创建并推送对应标签。以 `workbuddy-v1.0.1` 为例。

   ```sh
   git tag -a workbuddy-v1.0.1 <已验收提交的SHA> -m "kbkit for WorkBuddy 1.0.1"
   git push origin refs/tags/workbuddy-v1.0.1
   ```

3. GitHub Actions 从该标签构建并测试 ZIP 和 CLI，发布到同名 GitHub Release，再检查公开下载与校验值。每个已发布的版本使用自己的标签和附件。WorkBuddy 审核、上架由维护者在开放平台完成。

可用 `python scripts/build_workbuddy.py` 在干净的 Git 提交上重现打包，产物位于 `dist/workbuddy/<连接器版本>/`。需要检查已发布的运行包时，在本地执行 `python scripts/build_workbuddy.py --verify-sources`。

## 上架前的客户端验收

- 使用 WorkBuddy 托管 Python 完成首次连接，确认就绪后能查询指定的本地 Markdown 库。认证使用本机就绪状态。
- 在目标网络验证 GitHub Release 附件可以匿名下载。
- 在客户端升级到新连接器版本，确认自动重新安装后原有库路径和数据可用。
