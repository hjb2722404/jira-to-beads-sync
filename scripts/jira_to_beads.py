#!/usr/bin/env python3
"""
JIRA to Beads Sync Script

从 JIRA 拉取任务列表，用户交互式选择后同步到 beads。

配置文件默认路径: <项目目录>/.claude/jira-config.json
如果不存在，脚本会输出配置模板引导用户创建。

Usage:
    # 默认方式（从 .claude/jira-config.json 读取配置）
    python jira_to_beads.py

    # 指定配置文件
    python jira_to_beads.py --config /path/to/config.json

    # 命令行覆盖 JQL
    python jira_to_beads.py --jql "project = PROJ AND statusCategory != Done"
"""

import argparse
import base64
import json
import os
import subprocess
import sys
import urllib.request
import urllib.error
import urllib.parse
import ssl
from typing import Dict, List, Optional, Any

DEFAULT_CONFIG_PATH = ".claude/jira-config.json"
DEFAULT_JQL = "statusCategory != Done AND assignee = currentUser() ORDER BY priority DESC, created ASC"

CONFIG_TEMPLATE = """{{
  "jira_url": "https://your-jira-server.com",
  "auth_type": "basic",
  "auth": {{
    "username": "your-username",
    "password": "your-password"
  }},
  "jql": "",
  "validate_ssl": false
}}

配置说明:
  jira_url     - JIRA 服务器地址
  auth_type    - 认证方式: basic / api_token / bearer
  auth         - 认证凭据
                  basic:     {{"username": "...", "password": "..."}}
                  api_token: {{"email": "...", "token": "..."}}
                  bearer:    {{"token": "..."}}
  jql          - JQL 查询语句，为空时使用默认值: {default_jql}
  validate_ssl - 是否验证 SSL 证书，自建服务器通常设为 false
  project_dir  - beads 项目目录（可选，默认为当前目录）
"""


class JiraClient:
    """JIRA REST API Client (兼容 JIRA Server 8.x 和 Cloud)"""

    def __init__(self, base_url: str, auth_type: str, auth_creds: Dict[str, str], validate_ssl: bool = True):
        self.base_url = base_url.rstrip('/')
        self.auth_type = auth_type
        self.auth_creds = auth_creds
        self.api_version = "2"
        self.validate_ssl = validate_ssl

    def _get_auth_header(self) -> str:
        if self.auth_type == "basic":
            credentials = f"{self.auth_creds['username']}:{self.auth_creds['password']}"
            encoded = base64.b64encode(credentials.encode()).decode()
            return f"Basic {encoded}"
        elif self.auth_type == "api_token":
            credentials = f"{self.auth_creds['email']}:{self.auth_creds['token']}"
            encoded = base64.b64encode(credentials.encode()).decode()
            return f"Basic {encoded}"
        elif self.auth_type == "bearer":
            return f"Bearer {self.auth_creds['token']}"
        else:
            raise ValueError(f"Unsupported auth type: {self.auth_type}")

    def _get_ssl_context(self):
        if not self.validate_ssl:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            return ctx
        return None

    def search_issues(self, jql: str, fields: Optional[List[str]] = None, max_results: int = 100) -> List[Dict]:
        """使用 JQL 搜索 JIRA 问题（兼容 Server 和 Cloud）"""
        all_issues = []
        start_at = 0

        while True:
            params = urllib.parse.urlencode({
                "jql": jql,
                "maxResults": max_results,
                "startAt": start_at
            })
            if fields:
                params += "&" + urllib.parse.urlencode({"fields": fields}, doseq=True)

            url = f"{self.base_url}/rest/api/{self.api_version}/search?{params}"
            headers = {
                "Authorization": self._get_auth_header(),
                "Accept": "application/json",
            }

            req = urllib.request.Request(url, headers=headers, method="GET")

            try:
                with urllib.request.urlopen(req, timeout=30, context=self._get_ssl_context()) as response:
                    result = json.loads(response.read().decode())
            except urllib.error.HTTPError as e:
                error_body = e.read().decode()
                raise Exception(f"HTTP Error {e.code}: {error_body}")
            except Exception as e:
                raise Exception(f"Request failed: {str(e)}")

            issues = result.get("issues", [])
            all_issues.extend(issues)
            total = result.get("total", 0)

            start_at += len(issues)
            if start_at >= total or len(issues) == 0:
                break

        return all_issues

    def get_comments(self, issue_key: str) -> List[Dict]:
        """获取 JIRA 问题的评论"""
        url = f"{self.base_url}/rest/api/{self.api_version}/issue/{issue_key}/comment"
        headers = {
            "Authorization": self._get_auth_header(),
            "Accept": "application/json",
        }
        req = urllib.request.Request(url, headers=headers, method="GET")

        try:
            with urllib.request.urlopen(req, timeout=30, context=self._get_ssl_context()) as response:
                result = json.loads(response.read().decode())
                return result.get("comments", [])
        except urllib.error.HTTPError as e:
            error_body = e.read().decode()
            raise Exception(f"HTTP Error {e.code}: {error_body}")
        except Exception as e:
            raise Exception(f"Failed to get comments: {str(e)}")


class BeadsClient:
    """Beads CLI Client"""

    def __init__(self, project_dir: Optional[str] = None):
        self.project_dir = project_dir or os.getcwd()

    def _run_command(self, args: List[str]) -> Dict:
        cmd = ["bd"] + args + ["--json"]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=self.project_dir,
                check=True
            )
            if result.stdout and result.stdout.strip():
                return json.loads(result.stdout)
            return {}
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr or e.stdout or ""
            raise Exception(f"Beads command failed: {error_msg}")
        except json.JSONDecodeError as e:
            raise Exception(f"Failed to parse beads output: {e}")

    def create_issue(self, title: str, issue_type: str = "task", priority: int = 2,
                     description: str = "", external_ref: Optional[str] = None,
                     metadata: Optional[Dict] = None) -> Dict:
        args = ["create", title, "-t", issue_type, "-p", str(priority), "-d", description]
        if external_ref:
            args.extend(["--external-ref", external_ref])
        return self._run_command(args)

    def update_issue(self, issue_id: str, priority: Optional[int] = None,
                     external_ref: Optional[str] = None,
                     description: Optional[str] = None) -> Dict:
        args = ["update", issue_id]
        if priority is not None:
            args.extend(["--priority", str(priority)])
        if external_ref:
            args.extend(["--external-ref", external_ref])
        if description is not None:
            args.extend(["--description", description])
        return self._run_command(args)

    def list_issues(self) -> List[Dict]:
        result = self._run_command(["list"])
        return result if isinstance(result, list) else []

    def mark_done(self, issue_id: str) -> Dict:
        return self._run_command(["done", issue_id])

    def list_comments(self, issue_id: str) -> List[Dict]:
        result = self._run_command(["comments", issue_id])
        return result if isinstance(result, list) else []

    def add_comment(self, issue_id: str, comment: str) -> Dict:
        return self._run_command(["comments", "add", issue_id, comment])


def load_config(config_path: str) -> Dict[str, Any]:
    """加载配置文件"""
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def resolve_config_path(args_config: Optional[str]) -> str:
    """解析配置文件路径，默认为 .claude/jira-config.json"""
    if args_config:
        return args_config
    cwd_config = os.path.join(os.getcwd(), DEFAULT_CONFIG_PATH)
    if os.path.exists(cwd_config):
        return cwd_config
    return cwd_config  # 返回默认路径，即使不存在（由调用方处理）


def print_issue_table(issues: List[Dict]) -> None:
    """以表格形式打印 JIRA 任务列表"""
    if not issues:
        print("没有找到任何任务。")
        return

    # 计算列宽
    key_width = max(len(i.get("key", "")) for i in issues) + 2
    status_width = max(len(i.get("fields", {}).get("status", {}).get("name", "")) for i in issues) + 2
    type_width = max(len(i.get("fields", {}).get("issuetype", {}).get("name", "")) for i in issues) + 2
    priority_width = max(
        len(i.get("fields", {}).get("priority", {}).get("name", "")) if i.get("fields", {}).get("priority") else 4
        for i in issues
    ) + 2
    num_width = len(str(len(issues))) + 2

    # 表头
    header = (
        f"{'#'.rjust(num_width)} "
        f"{'Key'.ljust(key_width)} "
        f"{'Status'.ljust(status_width)} "
        f"{'Priority'.ljust(priority_width)} "
        f"{'Type'.ljust(type_width)} "
        f"Summary"
    )
    separator = "-" * len(header)

    print(f"\n{header}")
    print(separator)

    for idx, issue in enumerate(issues, 1):
        fields = issue.get("fields", {})
        key = issue.get("key", "")
        summary = fields.get("summary", "Untitled")
        status = fields.get("status", {}).get("name", "Unknown")
        priority = fields.get("priority", {}).get("name", "") if fields.get("priority") else "None"
        issuetype = fields.get("issuetype", {}).get("name", "Task")

        # 截断过长的摘要
        max_summary_len = 80
        if len(summary) > max_summary_len:
            summary = summary[:max_summary_len - 3] + "..."

        print(
            f"{str(idx).rjust(num_width)} "
            f"{key.ljust(key_width)} "
            f"{status.ljust(status_width)} "
            f"{priority.ljust(priority_width)} "
            f"{issuetype.ljust(type_width)} "
            f"{summary}"
        )

    print(separator)
    print(f"共 {len(issues)} 个任务\n")


def parse_selection(selection: str, max_idx: int) -> List[int]:
    """解析用户输入的选择，支持: 1, 3, 5-8, all"""
    selection = selection.strip().lower()
    if selection in ("all", "a", "*"):
        return list(range(1, max_idx + 1))

    indices = []
    parts = [p.strip() for p in selection.split(",")]
    for part in parts:
        if "-" in part:
            try:
                start, end = part.split("-", 1)
                start_idx = int(start.strip())
                end_idx = int(end.strip())
                if start_idx < 1 or end_idx > max_idx or start_idx > end_idx:
                    print(f"无效范围: {part}，有效范围为 1-{max_idx}")
                    return []
                indices.extend(range(start_idx, end_idx + 1))
            except (ValueError, IndexError):
                print(f"无效范围格式: {part}，请使用如 3-7")
                return []
        else:
            try:
                idx = int(part)
                if idx < 1 or idx > max_idx:
                    print(f"无效序号: {idx}，有效范围为 1-{max_idx}")
                    return []
                indices.append(idx)
            except ValueError:
                print(f"无效输入: {part}")
                return []

    return sorted(set(indices))


def main():
    parser = argparse.ArgumentParser(
        description="从 JIRA 拉取任务，交互式选择后同步到 beads"
    )
    parser.add_argument("--config", help=f"配置文件路径（默认: {DEFAULT_CONFIG_PATH}）")
    parser.add_argument("--jql", help="JQL 查询语句（覆盖配置文件中的 jql）")
    parser.add_argument("--dry-run", action="store_true", help="预览模式，不实际写入 beads")
    parser.add_argument("--all", action="store_true", help="跳过选择，同步全部任务")

    args = parser.parse_args()

    # ── 1. 加载配置 ──
    config_path = resolve_config_path(args.config)

    if not os.path.exists(config_path):
        print(f"配置文件不存在: {config_path}")
        print(f"\n请创建配置文件，内容如下:\n")
        print(CONFIG_TEMPLATE.format(default_jql=DEFAULT_JQL))
        sys.exit(1)

    try:
        config = load_config(config_path)
    except (json.JSONDecodeError, IOError) as e:
        print(f"配置文件格式错误: {e}")
        sys.exit(1)

    # 验证必填字段
    if not config.get("jira_url"):
        print("ERROR: 配置文件缺少 jira_url 字段")
        sys.exit(1)

    auth = config.get("auth", {})
    auth_type = config.get("auth_type", "basic")
    if auth_type == "basic":
        if not auth.get("username") or not auth.get("password"):
            print("ERROR: basic 认证需要 username 和 password")
            sys.exit(1)
    elif auth_type == "api_token":
        if not auth.get("email") or not auth.get("token"):
            print("ERROR: api_token 认证需要 email 和 token")
            sys.exit(1)
    elif auth_type == "bearer":
        if not auth.get("token"):
            print("ERROR: bearer 认证需要 token")
            sys.exit(1)

    # ── 2. 确定 JQL ──
    jql = args.jql or config.get("jql", "") or DEFAULT_JQL

    # ── 3. 拉取 JIRA 任务 ──
    print(f"JIRA 服务器: {config['jira_url']}")
    print(f"JQL: {jql}")
    print(f"配置文件: {config_path}")

    jira = JiraClient(
        base_url=config["jira_url"],
        auth_type=auth_type,
        auth_creds=auth,
        validate_ssl=config.get("validate_ssl", True)
    )

    fields = [
        "summary", "description", "priority", "issuetype",
        "status", "assignee", "reporter", "created", "updated",
        "attachment"
    ]

    print("\n正在从 JIRA 拉取任务...")
    try:
        jira_issues = jira.search_issues(jql, fields=fields)
    except Exception as e:
        print(f"ERROR: 拉取 JIRA 任务失败: {e}")
        sys.exit(1)

    if not jira_issues:
        print("没有找到匹配的任务。")
        sys.exit(0)

    print(f"找到 {len(jira_issues)} 个任务。\n")

    # ── 4. 展示任务列表 ──
    print_issue_table(jira_issues)

    # ── 5. 用户选择要同步的任务 ──
    if args.all:
        selected_indices = list(range(1, len(jira_issues) + 1))
        print(f"(--all 模式) 已选择全部 {len(selected_indices)} 个任务\n")
    else:
        print("请选择要同步到 beads 的任务:")
        print("  输入序号，如: 1 3 5")
        print("  输入范围，如: 1-3")
        print("  输入 all 同步全部")
        print("  输入 q 取消")
        print()

        try:
            selection = input("你的选择: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n已取消。")
            sys.exit(0)

        if selection.lower() in ("q", "quit", "exit", "cancel"):
            print("已取消。")
            sys.exit(0)

        selected_indices = parse_selection(selection, len(jira_issues))
        if not selected_indices:
            print("未选择任何任务。")
            sys.exit(0)

        print(f"\n已选择 {len(selected_indices)} 个任务。\n")

    selected_issues = [jira_issues[i - 1] for i in selected_indices]

    # ── 6. 同步到 beads ──
    project_dir = config.get("project_dir") or os.getcwd()
    beads = BeadsClient(project_dir)

    PRIORITY_MAP = {"Highest": 0, "High": 1, "Medium": 2, "Low": 3, "Lowest": 4}
    TYPE_MAP = {"Bug": "bug", "Story": "feature", "Task": "task", "Sub-task": "task", "Epic": "epic"}

    # 获取已有 beads 任务用于去重
    try:
        beads_issues = beads.list_issues()
    except Exception as e:
        print(f"WARNING: 无法读取 beads 任务列表: {e}")
        beads_issues = []

    # 建立 external_ref 索引
    existing_refs = set()
    for bi in beads_issues:
        ref = bi.get("external_ref", "")
        if ref:
            existing_refs.add(ref)

    stats = {"created": 0, "updated": 0, "skipped": 0, "errors": []}

    for issue in selected_issues:
        key = issue.get("key")
        fields = issue.get("fields", {})
        title = fields.get("summary", "Untitled")
        external_ref = f"jira-{key}"
        priority = PRIORITY_MAP.get(
            fields.get("priority", {}).get("name", "Medium") if fields.get("priority") else "Medium", 2
        )
        issue_type = TYPE_MAP.get(fields.get("issuetype", {}).get("name", "Task"), "task")

        # 构建描述
        description_parts = []
        desc = fields.get("description", "")
        if desc:
            if isinstance(desc, dict):
                texts = []

                def traverse(node):
                    if isinstance(node, dict):
                        if node.get("type") == "text":
                            texts.append(node.get("text", ""))
                        elif node.get("type") == "image":
                            attrs = node.get("attrs", {})
                            src = attrs.get("src", "")
                            alt = attrs.get("alt", "")
                            if src:
                                if alt:
                                    texts.append(f"![{alt}]({src})")
                                else:
                                    texts.append(f"![image]({src})")
                        for child in node.get("content", []):
                            traverse(child)
                    elif isinstance(node, list):
                        for child in node:
                            traverse(child)
                traverse(desc)
                description_parts.append("\n".join(texts))
            else:
                description_parts.append(str(desc))

        description_parts.append(f"\n---\nJIRA: {key}")
        description_parts.append(f"Status: {fields.get('status', {}).get('name', 'Unknown')}")
        assignee = fields.get("assignee", {})
        if assignee:
            description_parts.append(f"Assignee: {assignee.get('displayName', 'Unassigned')}")
        description_parts.append(f"Created: {fields.get('created', '')}")

        attachments = fields.get("attachment", [])
        if attachments:
            description_parts.append(f"\n---")
            description_parts.append(f"**Attachments ({len(attachments)}):**")
            for att in attachments:
                att_filename = att.get("filename", "unknown")
                att_url = att.get("content", "")
                att_size = att.get("size", 0)
                if att_size > 1024 * 1024:
                    size_str = f"{att_size / (1024 * 1024):.1f} MB"
                elif att_size > 1024:
                    size_str = f"{att_size / 1024:.1f} KB"
                else:
                    size_str = f"{att_size} B"
                if att_url:
                    description_parts.append(f"- [{att_filename}]({att_url}) ({size_str})")
                else:
                    description_parts.append(f"- {att_filename} ({size_str})")

        description = "\n".join(description_parts)

        jira_comments = []
        try:
            jira_comments = jira.get_comments(key)
        except Exception as e:
            print(f"  [警告] 获取评论失败 {key}: {e}")

        if args.dry_run:
            if external_ref in existing_refs:
                print(f"[DRY RUN] 更新: {key} - {title}")
            else:
                print(f"[DRY RUN] 新建: {key} - {title}")
            stats["updated" if external_ref in existing_refs else "created"] += 1
            continue

        try:
            if external_ref in existing_refs:
                # 找到对应的 beads issue id
                beads_id = None
                for bi in beads_issues:
                    if bi.get("external_ref") == external_ref:
                        beads_id = bi.get("id")
                        break

                if beads_id:
                    beads.update_issue(issue_id=beads_id, priority=priority, external_ref=external_ref, description=description)
                    print(f"  [更新] {key} -> {beads_id}: {title}")
                    stats["updated"] += 1
                    if jira_comments:
                        try:
                            beads_comments = beads.list_comments(beads_id)
                            beads_comment_bodies = {c.get("body", "") for c in beads_comments}
                            new_comments = 0
                            for comment in jira_comments:
                                author = comment.get("author", {}).get("displayName", "Unknown")
                                created = comment.get("created", "")[:10]
                                body = comment.get("body", "")
                                if isinstance(body, dict):
                                    body_texts = []
                                    def traverse_c(node):
                                        if isinstance(node, dict):
                                            if node.get("type") == "text":
                                                body_texts.append(node.get("text", ""))
                                            for child in node.get("content", []):
                                                traverse_c(child)
                                        elif isinstance(node, list):
                                            for child in node:
                                                traverse_c(child)
                                    traverse_c(body)
                                    body = "\n".join(body_texts)
                                comment_text = f"[JIRA:{author} {created}] {body}"
                                if body and comment_text not in beads_comment_bodies:
                                    beads.add_comment(beads_id, comment_text)
                                    new_comments += 1
                            if new_comments > 0:
                                print(f"    + 同步了 {new_comments} 条新评论")
                        except Exception as e:
                            print(f"    [警告] 评论同步失败: {e}")
                else:
                    print(f"  [跳过] {key}: 找到引用但无对应 beads 记录")
                    stats["skipped"] += 1
            else:
                result = beads.create_issue(
                    title=title,
                    issue_type=issue_type,
                    priority=priority,
                    description=description,
                    external_ref=external_ref
                )
                beads_id = result.get("id", "?")
                print(f"  [新建] {key} -> {beads_id}: {title}")
                stats["created"] += 1
                if jira_comments:
                    try:
                        synced_comments = 0
                        for comment in jira_comments:
                            author = comment.get("author", {}).get("displayName", "Unknown")
                            created = comment.get("created", "")[:10]
                            body = comment.get("body", "")
                            if isinstance(body, dict):
                                body_texts = []
                                def traverse_c(node):
                                    if isinstance(node, dict):
                                        if node.get("type") == "text":
                                            body_texts.append(node.get("text", ""))
                                        for child in node.get("content", []):
                                            traverse_c(child)
                                    elif isinstance(node, list):
                                        for child in node:
                                            traverse_c(child)
                                traverse_c(body)
                                body = "\n".join(body_texts)
                            comment_text = f"[JIRA:{author} {created}] {body}"
                            if body:
                                beads.add_comment(beads_id, comment_text)
                                synced_comments += 1
                        if synced_comments > 0:
                            print(f"    + 同步了 {synced_comments} 条评论")
                    except Exception as e:
                        print(f"    [警告] 评论同步失败: {e}")
        except Exception as e:
            error_msg = f"{key}: {e}"
            stats["errors"].append(error_msg)
            print(f"  [错误] {error_msg}")

    # ── 7. 检查 JIRA 中已不存在的任务并标记为完成 ──
    synced_external_refs = {f"jira-{issue.get('key')}" for issue in selected_issues}
    for bi in beads_issues:
        ref = bi.get("external_ref", "")
        if ref.startswith("jira-") and ref not in synced_external_refs:
            beads_id = bi.get("id")
            try:
                beads.mark_done(beads_id)
                print(f"  [已关闭] {ref} (JIRA中已不存在)")
                stats["closed"] = stats.get("closed", 0) + 1
            except Exception as e:
                print(f"  [关闭失败] {ref}: {e}")
                stats["errors"].append(f"{ref}: {e}")

    # ── 8. 输出汇总 ──
    print("\n" + "=" * 50)
    print("同步完成")
    print("=" * 50)
    print(f"  新建: {stats['created']}")
    print(f"  更新: {stats['updated']}")
    print(f"  跳过: {stats['skipped']}")
    print(f"  已关闭: {stats.get('closed', 0)}")

    if stats["errors"]:
        print(f"\n错误 ({len(stats['errors'])}):")
        for err in stats["errors"]:
            print(f"  - {err}")
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
