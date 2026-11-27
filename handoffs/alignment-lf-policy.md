# 对齐分支换行修复

Windows 工作树的自动换行转换曾触发两个历史 A1 JSON 的字节检查。`.gitattributes` 为文本规定 `eol=lf`，并将 NPZ 保持为二进制。`verify_alignment_integrity.py` 从各基线提交读取 Git blob 比较原始内容，另外检查当前工作树的属性和实际检出字节。

使用 `git -c core.autocrlf=true worktree add --detach <复核目录> 145b59cc55a29cc0ae3dfdb25173cdbf1c0492ad` 创建独立检出后执行检查。核对 54 个文本文件的 LF 检出、历史 A1 JSON、原规则归档、三个核心模块、版本锁及 M1 判据，并重新运行 M1、A1 九项回归、A1 上界与历史 1850 元候选 `dt=0.05/0.01`。全部通过，上界及候选逐敌记录与历史一致。完整进程合计约 38.4 秒，包含逐文件 Git 校验启动开销。[运行回执](alignment-lf-verification.json)

此前[发布失败记录](history/alignment-integrity-failure-2026-11-27.json)与[字节恢复回执](alignment-integrity-recovery.json)保留原始口径。这里比对仓库 blob 的 SHA-256，历史交接记录中的本机原始字节哈希仍按当次工作树解释。
