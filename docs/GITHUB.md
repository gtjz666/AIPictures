# GitHub 个人仓库创建与权限

当前项目仓库：https://github.com/gtjz666/AIPictures 。以下创建步骤供后续参考；已创建的仓库无需重复创建。

你的需求“任何人能查看，别人不能 push / merge”对应个人账号下的 Public 公开仓库，且不邀请 Collaborator。Private 私有仓库无法向所有人开放查看。

1. 访问 https://github.com/signup 创建个人账号（如果已有则直接登录），使用自己的邮箱并完成验证。
2. 访问 https://github.com/new ，Owner 选自己，Repository name 填 AIPictures。
3. Visibility 选 Public。因为本地已有 README 和 .gitignore，网页上不要初始化 README、.gitignore 或 License。
4. 点击 Create repository。不要在 Settings → Collaborators 添加人，也不要授予第三方 App 写入权限。
5. 别人可以查看、克隆、fork 或提交 Pull Request，但没有你的仓库写权限，不能直接 push 或合并 PR。公开也意味着代码可被复制，不能限制为只能在网页阅读。
6. 上传可使用 GitHub Desktop：File → Add local repository，选择桌面 AIPictures；若提示不是仓库，选择创建仓库，确认目录就是现有 AIPictures，避免再次嵌套文件夹。Review changes 中仅包含源码、文档和启动脚本；不要包含 data、.venv、模型或任何凭据。提交后 Publish repository，取消 Keep this code private。
7. 后续需要写权限再去 Settings → Collaborators → Add people。个人仓库 Collaborator 会获得写权限；如果只邀请少数人查看私有源码且保持只读，应考虑组织仓库的 Read 角色。

账号和远程仓库由所有者创建，源码通过 Git 推送。未添加软件许可证，后续选择授权方式后再添加。

官方参考：
- https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-new-repository
- https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/repository-access-and-collaboration/permission-levels-for-a-personal-account-repository
