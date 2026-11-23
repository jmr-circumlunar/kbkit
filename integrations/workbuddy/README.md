# WorkBuddy 连接器

kbkit 通过 WorkBuddy 的 CLI + Skill 运行。WorkBuddy 5.0.0 及以上提供托管 Python，连接器安装 kbkit 的自包含 zipapp。首次点击连接时安装程序只写入本机的连接器目录。Skill 在首次使用时确认知识库路径，定时维护的调度与授权保存在 WorkBuddy。kbkit 自身使用的是本地 CLI，无需第三方账号或服务凭证。 [WorkBuddy 连接器规范](https://open.workbuddy.cn/docs/connector)

## 分发方式

GitHub `main` 是源码上游。建议在自己名下创建 Gitee 镜像用于境内下载。GitHub 和 Gitee 使用同一提交和标签，两个站点的 Release 上传同一个 `kbkit.pyz`。只推送 Git 提交和标签时，仍需分别上传 Release 附件。 [Gitee 镜像推送说明](https://help.gitee.com/questions/GitHub%E4%BB%93%E5%BA%93%E5%BF%AB%E9%80%9F%E5%AF%BC%E5%85%A5Gitee%E5%8F%8A%E5%90%8C%E6%AD%A5%E6%9B%B4%E6%96%B0) · [Gitee Release 附件](https://help.gitee.com/repository/release/create)

配置镜像后，WorkBuddy 安装程序先试 Gitee，再试 GitHub。两边都校验随连接器固定的 SHA-256 和字节数，校验失败时尝试另一来源。安装过程使用托管 Python 直接下载检查过的运行包。两边提供同一份内容即可，安装端无需 Git 或包仓库。断开连接只移除本机连接状态，已下载的运行包和用户知识库仍可保留。

## 手动发布

1. 首次发布使用 `connector-meta.json` 中的版本。后续提交 WorkBuddy 更新前递增该文件的 `version`，并提交当期代码和连接器文件。连接器版本单独维护，`release.json` 同时记录真实的 kbkit 版本与 Git SHA。同一个连接器版本的正式包只发布一次。
2. 从干净的 `main` 提交构建。首次还未配置镜像时可省略 `--mirror-url`。

   ```text
   python scripts/build_workbuddy.py
   ```

   接入镜像时，从发布页复制实际可匿名下载 `kbkit.pyz` 的长期 HTTPS 地址。

   ```text
   python scripts/build_workbuddy.py --mirror-url "https://<镜像附件的实际下载地址>"
   ```

   如果 Gitee 只在上传后才生成附件地址，先构建一次并上传生成的 `kbkit.pyz`。再用同一提交和实际镜像地址生成最终连接器 ZIP，确认运行包 SHA-256 与第一次上传一致。

3. 在 `release.json` 的 `commit` 创建并手动推送 `tag` 指定的标签，例如 `workbuddy-v1.0.0`。GitHub 发行版使用该标签，附件名为 `kbkit.pyz`。Gitee 镜像可配置为单独的 `gitee` remote，只推送 `main` 与对应标签。把同一个 `kbkit.pyz` 放到两个发行版。确认下载地址公开后，在本地运行 `python scripts/build_workbuddy.py --verify-sources`，逐一校验已填入的来源。
4. 在具备资质的 [WorkBuddy 开放平台](https://open.workbuddy.cn/) 账号下创建连接器，类型选 CLI，标识使用 `circumlunar-kbkit`。在提交市场审核前，用未安装该连接器的客户端做一次连接，检查查询、维护和断开连接。连接器上线后，在同一条目上传递增版本的 ZIP，提审通过后手动发布。Git 推送不会触发 WorkBuddy 审核或发布。 [WorkBuddy 开放平台流程](https://open.workbuddy.cn/docs)

生成文件位于 `dist/workbuddy/<连接器版本>/`。上传给 WorkBuddy 的文件是 `kbkit-workbuddy-<连接器版本>.zip`，发布站点的下载附件是 `kbkit.pyz`，构建记录是 `release.json`。元信息、安装器、图标和 Skill 在本目录维护。构建器生成 `cli.json`，把同一提交的校验值和下载地址写入安装配置。

## 上架前的客户端验收

- 在托管 Python 下运行安装，确认准备完成后可查询指定的本地 Markdown 库。特别验证 CLI 使用本地就绪状态而不打开 OAuth 页面。
- 用仅国内镜像可访问的网络安装，再用仅 GitHub 可访问的网络验证回退。
- 准备不同连接器版本，验证 WorkBuddy 的版本检查会重新安装并保留库路径和数据。断开连接后状态应变为未连接，原库仍可读。
