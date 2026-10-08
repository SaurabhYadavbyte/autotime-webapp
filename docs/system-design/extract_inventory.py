"""Extract documentation facts statically, without importing or connecting to the app."""
import ast
import json
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def literal(node, fallback=None):
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError):
        return fallback if fallback is not None else ast.unparse(node)


def call_name(node):
    return ast.unparse(node.func) if isinstance(node, ast.Call) else ""


tables = []
for cls in ast.parse((ROOT / "models.py").read_text()).body:
    if not isinstance(cls, ast.ClassDef):
        continue
    table = {"model": cls.name, "table": re.sub(r"(?<!^)(?=[A-Z])", "_", cls.name).lower(),
             "line": cls.lineno, "columns": [], "constraints": [], "indexes": []}
    for stmt in cls.body:
        if not isinstance(stmt, ast.Assign) or not isinstance(stmt.targets[0], ast.Name):
            continue
        name, val = stmt.targets[0].id, stmt.value
        if name == "__tablename__":
            table["table"] = literal(val)
        if name == "__table_args__":
            for entry in val.elts:
                if not isinstance(entry, ast.Call):
                    continue
                opts = {k.arg: literal(k.value) for k in entry.keywords}
                args = [literal(arg) for arg in entry.args]
                if call_name(entry) == "db.UniqueConstraint":
                    table["constraints"].append({"name": opts.get("name"), "columns": args})
                elif call_name(entry) == "db.Index":
                    table["indexes"].append({"name": args[0], "columns": args[1:]})
        if call_name(val) != "db.Column":
            continue
        opts = {k.arg: literal(k.value) for k in val.keywords}
        col = {"name": name, "type": ast.unparse(val.args[0]).replace("db.", ""),
               "pk": opts.get("primary_key", False), "nullable": opts.get("nullable", not opts.get("primary_key", False)),
               "unique": opts.get("unique", False), "default": opts.get("default"), "line": stmt.lineno}
        for arg in val.args[1:]:
            if call_name(arg) == "db.ForeignKey":
                col["references"] = literal(arg.args[0])
                col["ondelete"] = next((literal(k.value) for k in arg.keywords if k.arg == "ondelete"), "NO ACTION")
        table["columns"].append(col)
        if opts.get("index"):
            table["indexes"].append({"name": f"ix_{table['table']}_{name}", "columns": [name]})
    tables.append(table)

routes = []
for file in [ROOT / "app.py", *sorted((ROOT / "routes").glob("*.py"))]:
    tree = ast.parse(file.read_text())
    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in func.decorator_list:
            if not isinstance(dec, ast.Call) or call_name(dec) not in {"main_bp.route", "app.get"}:
                continue
            opts = {k.arg: literal(k.value) for k in dec.keywords}
            decorators = [ast.unparse(d) for d in func.decorator_list if isinstance(d, ast.Name)]
            role = next((d.replace("login_required_", "") for d in decorators if d.startswith("login_required_")), None)
            if not role:
                role = "authenticated role (internal check)" if func.name in {
                    "settings", "update_profile", "verify_email_update", "settings_change_password",
                    "delete_account_page", "delete_account_send_otp", "verify_delete_account_page", "delete_account_confirm"
                } else "public / staged session"
            fields = {"form": set(), "args": set(), "files": set()}
            for node in ast.walk(func):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.args:
                    source = ast.unparse(node.func.value)
                    for kind in fields:
                        if source == f"request.{kind}" and isinstance(node.args[0], ast.Constant):
                            fields[kind].add(str(node.args[0].value))
                elif isinstance(node, ast.Subscript):
                    for kind in fields:
                        if ast.unparse(node.value) == f"request.{kind}" and isinstance(node.slice, ast.Constant):
                            fields[kind].add(str(node.slice.value))
            body = ast.unparse(func)
            returns = "JSON" if "jsonify(" in body else "file / redirect" if "send_file(" in body else "HTML / redirect"
            routes.append({"path": literal(dec.args[0]), "methods": opts.get("methods", ["GET"]),
                           "function": func.name, "role": role, "response": returns,
                           "inputs": {k: sorted(v) for k, v in fields.items()},
                           "source": file.relative_to(ROOT).as_posix(), "line": dec.lineno})

revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
inventory = {"revision": revision, "tables": tables, "routes": sorted(routes, key=lambda r: r["path"])}
(HERE / "inventory.json").write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")
print(f"Extracted {len(tables)} tables, {sum(len(t['columns']) for t in tables)} columns and {len(routes)} routes; no app import or database access.")
