import argparse
import json
import os
import sys
from typing import Any, Iterable

from requests.exceptions import HTTPError
from todoist_api_python.api import TodoistAPI


def parse_labels(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    labels = [label.strip() for label in raw.split(",")]
    labels = [label for label in labels if label]
    return labels or None


def user_priority_to_api(priority: int | None) -> int | None:
    if priority is None:
        return None
    return 5 - priority


def api_priority_to_user(priority: Any) -> Any:
    if isinstance(priority, int) and 1 <= priority <= 4:
        return 5 - priority
    return priority


def flatten_paged(result: Any) -> list[Any]:
    if result is None:
        return []
    if isinstance(result, list):
        if result and isinstance(result[0], list):
            flat: list[Any] = []
            for page in result:
                flat.extend(page)
            return flat
        return result

    if isinstance(result, Iterable) and not isinstance(result, (str, bytes, dict)):
        flat = []
        for item in result:
            if isinstance(item, list):
                flat.extend(item)
            else:
                flat.append(item)
        return flat

    return [result]


def to_dict(obj: Any) -> dict[str, Any]:
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    for method_name in ("to_dict", "model_dump", "dict"):
        method = getattr(obj, method_name, None)
        if callable(method):
            try:
                value = method()
                if isinstance(value, dict):
                    return value
            except Exception:
                pass
    data = getattr(obj, "__dict__", None)
    if isinstance(data, dict):
        return {k: v for k, v in data.items() if not k.startswith("_")}
    return {"value": str(obj)}


def print_json(data: Any) -> None:
    print(json.dumps(data, indent=2, default=str))


def require_token(args: argparse.Namespace) -> str:
    token = args.token or os.getenv("TODOIST_API_TOKEN")
    if not token:
        raise SystemExit(
            "Missing API token. Pass --token or set TODOIST_API_TOKEN in your environment."
        )
    return token


def task_list(api: TodoistAPI, args: argparse.Namespace) -> Any:
    kwargs: dict[str, Any] = {}
    if args.project_id:
        kwargs["project_id"] = args.project_id
    if args.label:
        kwargs["label"] = args.label
    if args.limit:
        kwargs["limit"] = args.limit

    tasks = flatten_paged(api.get_tasks(**kwargs))
    if args.json:
        return [to_dict(task) for task in tasks]
    if not tasks:
        return "No tasks found."

    lines = []
    for task in tasks:
        tid = getattr(task, "id", "")
        content = getattr(task, "content", "")
        priority = api_priority_to_user(getattr(task, "priority", ""))
        due = getattr(task, "due", None)
        due_text = ""
        if due is not None:
            due_text = (
                getattr(due, "string", None)
                or getattr(due, "date", None)
                or getattr(due, "datetime", None)
                or str(due)
            )
        suffix = f" | p{priority}" if priority else ""
        if due_text:
            suffix += f" | due: {due_text}"
        lines.append(f"{tid}\t{content}{suffix}")
    return "\n".join(lines)


def task_get(api: TodoistAPI, args: argparse.Namespace) -> Any:
    task = api.get_task(args.task_id)
    if args.json:
        return to_dict(task)
    tid = getattr(task, "id", "")
    content = getattr(task, "content", "")
    description = getattr(task, "description", "")
    return f"{tid}\t{content}\n{description}".strip()


def task_add(api: TodoistAPI, args: argparse.Namespace) -> Any:
    kwargs: dict[str, Any] = {
        "content": args.content,
    }
    if args.project_id:
        kwargs["project_id"] = args.project_id
    if args.description:
        kwargs["description"] = args.description
    if args.due_string:
        kwargs["due_string"] = args.due_string
    if args.priority is not None:
        kwargs["priority"] = user_priority_to_api(args.priority)
    labels = parse_labels(args.labels)
    if labels:
        kwargs["labels"] = labels
    task = api.add_task(**kwargs)
    return to_dict(task) if args.json else f"Created task {getattr(task, 'id', '')}"


def task_update(api: TodoistAPI, args: argparse.Namespace) -> Any:
    kwargs: dict[str, Any] = {}
    if args.content is not None:
        kwargs["content"] = args.content
    if args.description is not None:
        kwargs["description"] = args.description
    if args.due_string is not None:
        kwargs["due_string"] = args.due_string
    if args.priority is not None:
        kwargs["priority"] = user_priority_to_api(args.priority)
    if args.labels is not None:
        kwargs["labels"] = parse_labels(args.labels) or []
    if not kwargs:
        raise SystemExit("No fields provided to update.")
    task = api.update_task(args.task_id, **kwargs)
    return to_dict(task) if args.json else f"Updated task {args.task_id}"


def task_complete(api: TodoistAPI, args: argparse.Namespace) -> Any:
    if hasattr(api, "complete_task"):
        api.complete_task(args.task_id)
    else:
        api.close_task(args.task_id)
    return {"status": "ok", "task_id": args.task_id} if args.json else f"Completed task {args.task_id}"


def task_delete(api: TodoistAPI, args: argparse.Namespace) -> Any:
    api.delete_task(args.task_id)
    return {"status": "ok", "task_id": args.task_id} if args.json else f"Deleted task {args.task_id}"


def project_list(api: TodoistAPI, args: argparse.Namespace) -> Any:
    projects = flatten_paged(api.get_projects())
    if args.json:
        return [to_dict(project) for project in projects]
    if not projects:
        return "No projects found."
    return "\n".join(
        f"{getattr(project, 'id', '')}\t{getattr(project, 'name', '')}" for project in projects
    )


def project_add(api: TodoistAPI, args: argparse.Namespace) -> Any:
    project = api.add_project(name=args.name)
    return to_dict(project) if args.json else f"Created project {getattr(project, 'id', '')}"


def project_update(api: TodoistAPI, args: argparse.Namespace) -> Any:
    project = api.update_project(args.project_id, name=args.name)
    return to_dict(project) if args.json else f"Updated project {args.project_id}"


def comment_list(api: TodoistAPI, args: argparse.Namespace) -> Any:
    comments = flatten_paged(api.get_comments(task_id=args.task_id))
    if args.json:
        return [to_dict(comment) for comment in comments]
    if not comments:
        return "No comments found."
    return "\n".join(
        f"{getattr(comment, 'id', '')}\t{getattr(comment, 'content', '')}" for comment in comments
    )


def comment_add(api: TodoistAPI, args: argparse.Namespace) -> Any:
    comment = api.add_comment(task_id=args.task_id, content=args.content)
    return to_dict(comment) if args.json else f"Created comment {getattr(comment, 'id', '')}"


def label_list(api: TodoistAPI, args: argparse.Namespace) -> Any:
    labels = flatten_paged(api.get_labels())
    if args.json:
        return [to_dict(label) for label in labels]
    if not labels:
        return "No labels found."
    return "\n".join(f"{getattr(label, 'id', '')}\t{getattr(label, 'name', '')}" for label in labels)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="todoist", description="Todoist CLI powered by todoist-api-python.")
    parser.add_argument("--token", help="Todoist API token. Defaults to TODOIST_API_TOKEN env var.")
    parser.add_argument("--json", action="store_true", help="Print output as JSON.")

    resources = parser.add_subparsers(dest="resource", required=True)

    tasks = resources.add_parser("tasks", help="Manage tasks.")
    task_cmds = tasks.add_subparsers(dest="action", required=True)

    task_list_p = task_cmds.add_parser("list", help="List active tasks.")
    task_list_p.add_argument("--project-id")
    task_list_p.add_argument("--label", help="Filter by label name.")
    task_list_p.add_argument("--limit", type=int, help="Max items per page (1-200).")
    task_list_p.set_defaults(handler=task_list)

    task_get_p = task_cmds.add_parser("get", help="Get a task.")
    task_get_p.add_argument("task_id")
    task_get_p.set_defaults(handler=task_get)

    task_add_p = task_cmds.add_parser("add", help="Create a task.")
    task_add_p.add_argument("content")
    task_add_p.add_argument("--project-id")
    task_add_p.add_argument("--description")
    task_add_p.add_argument("--due-string")
    task_add_p.add_argument(
        "--priority",
        type=int,
        choices=[1, 2, 3, 4],
        help="Priority value where p1 is highest and p4 is lowest.",
    )
    task_add_p.add_argument("--labels", help="Comma-separated labels.")
    task_add_p.set_defaults(handler=task_add)

    task_up_p = task_cmds.add_parser("update", help="Update a task.")
    task_up_p.add_argument("task_id")
    task_up_p.add_argument("--content")
    task_up_p.add_argument("--description")
    task_up_p.add_argument("--due-string")
    task_up_p.add_argument(
        "--priority",
        type=int,
        choices=[1, 2, 3, 4],
        help="Priority value where p1 is highest and p4 is lowest.",
    )
    task_up_p.add_argument("--labels", help="Comma-separated labels. Use empty string to clear.")
    task_up_p.set_defaults(handler=task_update)

    task_complete_p = task_cmds.add_parser("complete", help="Complete a task.")
    task_complete_p.add_argument("task_id")
    task_complete_p.set_defaults(handler=task_complete)

    task_delete_p = task_cmds.add_parser("delete", help="Delete a task.")
    task_delete_p.add_argument("task_id")
    task_delete_p.set_defaults(handler=task_delete)

    projects = resources.add_parser("projects", help="Manage projects.")
    project_cmds = projects.add_subparsers(dest="action", required=True)

    project_list_p = project_cmds.add_parser("list", help="List projects.")
    project_list_p.set_defaults(handler=project_list)

    project_add_p = project_cmds.add_parser("add", help="Create a project.")
    project_add_p.add_argument("name")
    project_add_p.set_defaults(handler=project_add)

    project_up_p = project_cmds.add_parser("update", help="Update a project name.")
    project_up_p.add_argument("project_id")
    project_up_p.add_argument("name")
    project_up_p.set_defaults(handler=project_update)

    comments = resources.add_parser("comments", help="Manage comments.")
    comment_cmds = comments.add_subparsers(dest="action", required=True)

    comment_list_p = comment_cmds.add_parser("list", help="List comments for a task.")
    comment_list_p.add_argument("--task-id", required=True)
    comment_list_p.set_defaults(handler=comment_list)

    comment_add_p = comment_cmds.add_parser("add", help="Add comment to a task.")
    comment_add_p.add_argument("--task-id", required=True)
    comment_add_p.add_argument("content")
    comment_add_p.set_defaults(handler=comment_add)

    labels = resources.add_parser("labels", help="List labels.")
    label_cmds = labels.add_subparsers(dest="action", required=True)
    label_list_p = label_cmds.add_parser("list", help="List labels.")
    label_list_p.set_defaults(handler=label_list)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        token = require_token(args)
        with TodoistAPI(token) as api:
            result = args.handler(api, args)
        if args.json:
            print_json(result)
        elif result is not None:
            print(result)
        return 0
    except HTTPError as err:
        response = getattr(err, "response", None)
        status = getattr(response, "status_code", "unknown")
        text = getattr(response, "text", "") if response is not None else str(err)
        print(f"Todoist API error (status {status}): {text}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
    except Exception as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
