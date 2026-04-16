---
name: jira-to-beads-sync
description: 从 JIRA 拉取任务列表，用户交互式选择后同步到 beads。默认读取 .claude/jira-config.json 配置文件。兼容 JIRA Server 和 Cloud。
---

# JIRA to Beads Sync

从 JIRA 拉取任务，用户选择后同步到 beads 任务数据库。

## When to Use

- 用户说"从 jira 同步任务"、"同步 jira 到 beads"
- 需要将 JIRA 中的任务导入到 beads 进行跟踪

## Prerequisites

1. **JIRA 账号**（需要有 API 访问权限）
2. **Beads CLI** (`bd`) 已安装且项目已初始化
3. **Python 3.7+**

## 工作流程

### 1. 检查配置文件

脚本默认读取当前项目目录下的 `.claude/jira-config.json`。

如果配置文件不存在，脚本会输出配置模板并退出，引导用户创建。

### 2. 配置文件格式

```json
{
  "jira_url": "https://your-jira-server.com",
  "auth_type": "basic",
  "auth": {
    "username": "your-username",
    "password": "your-password"
  },
  "jql": "project = XMKFB AND statusCategory != Done AND assignee = currentUser() ORDER BY priority DESC, created ASC",
  "validate_ssl": false,
  "project_dir": "/path/to/beads/project"
}
```

**字段说明:**

| 字段 | 必填 | 说明 |
|------|------|------|
| `jira_url` | 是 | JIRA 服务器地址 |
| `auth_type` | 是 | 认证方式: `basic` / `api_token` / `bearer` |
| `auth` | 是 | 认证凭据，格式取决于 auth_type |
| `jql` | 否 | JQL 查询语句，为空时使用默认值 |
| `validate_ssl` | 否 | 是否验证 SSL 证书，默认 true（自建服务器通常设为 false） |
| `project_dir` | 否 | beads 项目目录，默认为当前目录 |

**认证方式:**

| auth_type | auth 格式 |
|-----------|-----------|
| `basic` | `{"username": "...", "password": "..."}` |
| `api_token` | `{"email": "...", "token": "..."}` |
| `bearer` | `{"token": "..."}` |

**JQL 默认值:** `statusCategory != Done AND assignee = currentUser() ORDER BY priority DESC, created ASC`

即拉取当前用户所有未完成的任务。

### 3. 拉取并展示任务

脚本用配置中的 JQL 从 JIRA 拉取任务，以表格形式展示：

```
# Key           Status  Priority  Type   Summary
-  -----------------------------------------------------
1  XMKFB-29097  处理中  重要      故障   根据项目清单创建项目，部分字段没有自动填充
2  XMKFB-29107  新建    重要      子任务 前-接口路由调整
3  XMKFB-29120  新建    重要      故事   【重庆网信】智控H5部分展示优化
```

### 4. 用户选择

用户通过输入序号选择要同步的任务：

```
请选择要同步到 beads 的任务:
  输入序号，如: 1 3 5
  输入范围，如: 1-3
  输入 all 同步全部
  输入 q 取消
```

支持的输入格式：
- 单个序号: `1`
- 多个序号: `1 3 5` 或 `1, 3, 5`
- 范围: `1-3`
- 混合: `1, 3-5`
- 全部: `all`
- 取消: `q`

### 5. 同步到 beads

选中的任务被同步到 beads。已有任务（通过 `external_ref` 匹配）会更新，新任务会创建。

## 执行脚本

脚本位于技能目录下，**必须使用完整路径**运行（不要用相对路径，否则在其他项目中会找不到）：

```bash
python {skill_dir}/scripts/jira_to_beads.py [选项]
```

## 命令行参数

| 参数 | 说明 |
|------|------|
| `--config PATH` | 配置文件路径（默认: `.claude/jira-config.json`） |
| `--jql "..."` | 覆盖配置文件中的 JQL |
| `--all` | 跳过选择，同步全部任务 |
| `--dry-run` | 预览模式，不实际写入 beads |

## 映射规则

| JIRA 优先级 | Beads 优先级 |
|-------------|-------------|
| Highest     | 0 (Critical) |
| High        | 1 (High) |
| Medium      | 2 (Normal) |
| Low         | 3 (Low) |
| Lowest      | 4 (Trivial) |

| JIRA 类型 | Beads 类型 |
|-----------|-----------|
| Bug       | bug |
| Story     | feature |
| Task      | task |
| Sub-task  | task |
| Epic      | epic |

## 常见问题

### 配置文件不存在
脚本会输出配置模板，复制到 `.claude/jira-config.json` 并填入实际值即可。

### SSL 证书错误
自建 JIRA 服务器通常使用自签名证书，设置 `"validate_ssl": false`。

### 中文 JQL 状态名报错
JIRA Server 8.x 的中文状态名在 URL 编码时可能不兼容，建议使用 `statusCategory` 代替具体状态名：
- `statusCategory != Done` 代替 `status != Done`
- `statusCategory = new` 代替 `status = 新建`
