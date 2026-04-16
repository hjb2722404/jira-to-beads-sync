# JIRA to Beads Sync

将 JIRA 任务同步到 [Beads](https://github.com/beads/beads) 的 Python 脚本，支持图片、附件和评论同步。

## 功能特性

- **任务同步**：JIRA 问题同步到 Beads，包含优先级和类型映射
- **图片嵌入**：JIRA ADF 格式图片以 Markdown 格式嵌入描述中
- **附件链接**：JIRA 附件显示为可下载链接
- **评论同步**：JIRA 评论同步到 Beads 原生评论系统（增量同步）
- **自动关闭**：JIRA 中删除的任务自动在 Beads 中标记为完成
- **多种认证**：支持 Basic Auth、API Token 和 Bearer Token

## 环境要求

- Python 3.7+
- [Beads CLI](https://github.com/beads/beads)（`bd`命令）已安装并初始化
- JIRA 账号（需有 API 访问权限）

## 安装

```bash
# 克隆仓库
git clone https://github.com/hjb2722404/jira-to-beads-sync.git
cd jira-to-beads-sync

# 安装 Python 依赖（如需要）
pip install -r requirements.txt  # 基础使用时不需要
```

## 配置

在项目目录下创建配置文件 `.claude/jira-config.json`：

```json
{
  "jira_url": "https://your-jira-server.com",
  "auth_type": "basic",
  "auth": {
    "username": "your-username",
    "password": "your-password"
  },
  "jql": "statusCategory != Done AND assignee = currentUser() ORDER BY priority DESC, created ASC",
  "validate_ssl": false,
  "project_dir": "/path/to/beads/project"
}
```

### 配置字段说明

| 字段 | 必填 | 说明 |
|------|------|------|
| `jira_url` | 是 | JIRA 服务器地址 |
| `auth_type` | 是 | 认证方式：`basic`、`api_token` 或 `bearer` |
| `auth` | 是 | 认证凭据（格式取决于 auth_type） |
| `jql` | 否 | JQL 查询语句（默认查询当前用户未完成的任务） |
| `validate_ssl` | 否 | 是否验证 SSL 证书（默认：true） |
| `project_dir` | 否 | Beads 项目目录（默认：当前目录） |

### 认证方式

```json
// Basic Auth
{"username": "...", "password": "..."}

// API Token（适用于 JIRA Cloud）
{"email": "...", "token": "..."}

// Bearer Token
{"token": "..."}
```

## 使用方法

```bash
# 默认用法（从 .claude/jira-config.json 读取配置）
python scripts/jira_to_beads.py

# 指定配置文件
python scripts/jira_to_beads.py --config /path/to/config.json

# 覆盖 JQL
python scripts/jira_to_beads.py --jql "project = PROJ AND statusCategory != Done"

# 同步全部任务（跳过选择）
python scripts/jira_to_beads.py --all

# 预览模式（不实际写入）
python scripts/jira_to_beads.py --dry-run
```

### 交互式选择

```
# 选择单个任务
1 3 5

# 选择范围
1-3

# 全部选择
all

# 取消
q
```

## 优先级映射

| JIRA 优先级 | Beads 优先级 |
|-------------|-------------|
| Highest | 0 (Critical) |
| High | 1 (High) |
| Medium | 2 (Normal) |
| Low | 3 (Low) |
| Lowest | 4 (Trivial) |

## 问题类型映射

| JIRA 类型 | Beads 类型 |
|-----------|-----------|
| Bug | bug |
| Story | feature |
| Task | task |
| Sub-task | task |
| Epic | epic |

## 同步行为

### 新建任务
- 在 Beads 中创建，包含完整描述、附件和评论

### 已有任务（通过 `external_ref` 匹配）
- 更新：优先级、描述
- 增量评论同步：仅新增的 JIRA 评论会添加到 Beads

### 已删除任务
- 在 Beads 中存在但在 JIRA 中不存在的任务会被标记为完成

## 许可证

MIT
