"""复核对齐交付的 Git 内容、规则锁和 M1 判据，输出 JSON 回执。"""

import argparse
import ast
import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parent
ALIGNMENT = "ed4a19a985c6ab4d977da2abc56bd5c405f901a1"
A1 = "91c7a8a514edab0a4e5b1c98ce3993443a144415"
T12 = "40d0a920b8677d5cc4f2f5f7bf7552ffc5a81378"
T11 = "09577be19375b24a3f0d80905f042e8392386d44"
MODELING = "0563c1d721bd807e9976ae7698a4fd40fdbb0b13"
CORE = ("geometry.py", "coverage.py", "simulate.py")
ARCHIVE = "docs/sim_rules_T1.1.md"
RULES = "modeling/rules.md"


def git(*args):
    """在仓库内运行只读 Git 命令，返回未经文本解码的字节。"""
    return subprocess.check_output(["git", *args], cwd=ROOT)


def blob(ref, path):
    """读指定提交中的文件内容，绕过工作树换行转换。"""
    return git("cat-file", "blob", f"{ref}:{path}")


def paths_at(ref, *prefixes):
    """列出指定提交中的路径，按 NUL 分隔以支持空格。"""
    raw = git("ls-tree", "-r", "--name-only", "-z", ref, "--", *prefixes)
    return [path.decode("utf-8") for path in raw.split(b"\0") if path]


def require(condition, message):
    """判据不满足时保留说明，Python 优化模式下也执行检查。"""
    if not condition:
        raise ValueError(message)


def assignment(tree, name):
    """从源码 AST 读取指定的字面量常量。"""
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise ValueError(f"缺少常量：{name}")


def check(ref):
    """比较 ref 与各原始交付版本，返回可复核的基线与哈希。"""
    require(git("rev-parse", "HEAD").strip() == git("rev-parse", ref).strip(),
            "请在待检查提交的检出目录执行，以便同时验证 LF 属性")
    require(not git("status", "--porcelain", "--untracked-files=no"), "受跟踪文件有未提交改动")
    for name in ("results/a1-candidate.json", "results/a1-verification.json"):
        require(blob(ref, name) == blob(A1, name), f"历史 A1 blob 变化：{name}")

    proof = json.loads(blob(ALIGNMENT, "handoffs/rules-archive-proof.json"))
    require(blob(ref, ARCHIVE) == blob(T12, RULES) == blob(T11, RULES), "归档规则 blob 变化")
    archive_sha = hashlib.sha256(blob(ref, ARCHIVE)).hexdigest()
    require(archive_sha == proof["LF归一化SHA256"], "归档规则的 Git 内容哈希变化")

    core_sha = {}
    for name in CORE:
        require(blob(ref, name) == blob(T11, name) == blob(T12, name), f"核心 blob 变化：{name}")
        core_sha[name] = hashlib.sha256(blob(ref, name)).hexdigest()

    # 这一小 PR 只改换行策略和检查器，原验证脚本与证据都按 Git 字节锁定。
    receipt = json.loads(blob(ALIGNMENT, "handoffs/team-rules-alignment.json"))
    evidence = [*receipt["文件SHA256"], "validate_t12.py", "verify_a1.py",
                "test_a1_verification.py", "a1_bounds.py"]
    for name in evidence:
        require(blob(ref, name) == blob(ALIGNMENT, name), f"既有交付 blob 变化：{name}")
    reviews = paths_at(MODELING, "modeling/reviews")
    for name in reviews:
        require(blob(ref, name) == blob(MODELING, name), f"Hermes 原审核 blob 变化：{name}")

    before, after = (ast.parse(blob(commit, "validate_t12.py")) for commit in (T12, ref))
    functions = [{node.name: ast.dump(node) for node in tree.body if isinstance(node, ast.FunctionDef)}
                 for tree in (before, after)]
    for name in ("_analytic", "_convergence", "_no_towers", "_full_coverage"):
        require(functions[0][name] == functions[1][name], f"M1 判据变化：{name}")
    locks = assignment(before, "BASELINE_LF")
    locks[ARCHIVE] = locks.pop(RULES)
    require(locks == assignment(after, "BASELINE_LF"), "版本锁发生变化")
    for name in (*CORE, ARCHIVE):
        require(hashlib.sha256(blob(ref, name)).hexdigest() == locks[name], f"版本锁不匹配：{name}")
    for name in ("COVERAGE_TOL_M", "A1_WAVE"):
        require(assignment(before, name) == assignment(after, name), f"容差或输入变化：{name}")

    # 单独验证 checkout 的 eol 属性和实际换行；历史证据始终用仓库 blob 比较。
    text_paths = [name for name in paths_at(ref) if Path(name).suffix in {".py", ".md", ".json", ".txt", ".csv"}]
    for name in text_paths:
        require(git("check-attr", "eol", "--", name).strip().endswith(b": lf"), f"缺少 LF 属性：{name}")
        require((ROOT / name).read_bytes() == blob(ref, name), f"工作树未按 LF 检出：{name}")
    return {"检查提交": git("rev-parse", ref).decode().strip(), "核心模块Git内容SHA256": core_sha,
            "归档Git内容SHA256": archive_sha, "原始交付Git文件数": len(evidence),
            "Hermes历史审核文件数": len(reviews), "LF检出文件数": len(text_paths),
            "旧A1及规则归档blob一致": True, "M1判据与容差一致": True}


def main():
    """接收待验证提交和可选回执路径，失败时保留错误并返回非零。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", default="HEAD", help="当前工作树检出的待验证提交")
    parser.add_argument("--output", type=Path, help="可选的 JSON 回执路径")
    args = parser.parse_args()
    try:
        report = {"通过": True, **check(args.ref)}
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        report = {"通过": False, "失败项": str(exc)}
    output = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    print(output, end="")
    return 0 if report["通过"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
