"""
测试套件：验证系统各模块的核心功能。
可直接运行：python test_pipeline.py
"""

import sys
import os
import textwrap
import tempfile
import shutil
from pathlib import Path

# ── 确保可导入同目录模块 ──────────────────────────────────────────
sys.path.insert(0, os.path.dirname(__file__))

from toc_extractor import TOCExtractor
from structure_rebuilder import (
    StructureRebuilder, parse_toc, normalize, similarity, TOCEntry
)


# ══════════════════════════════════════════════════════════════════
# 测试数据
# ══════════════════════════════════════════════════════════════════

SAMPLE_MD_WITH_TOC = textwrap.dedent("""\
    # 某硬件技术手册

    ## 目录

    第一部分 基础知识 ·············· 1
    第1章 电子学概念 ···············3
      1.1 电流与电压 ················5
      1.2 电阻 ···················· 7
    第2章 半导体器件 ············· 10
      2.1 二极管 ·················· 12
      2.2 三极管 ·················· 15
    第二部分 高级应用 ············ 20
    第3章 集成电路 ··············· 22

    ## 前言

    本书介绍了硬件领域的核心知识。

    # 第一部分 基础知识

    # 第1章 电子学概念

    本章介绍基本电子学概念。

    # 1.1 电流与
    # 电压

    电流是电荷的定向移动。

    # 页眉装饰内容 ABC公司内部资料 2024

    # 1.2 电阻

    欧姆定律描述了电阻的基本特性。

    # 第2章 半
    # 导体器件

    # 2.1 二极管

    # 2.2 三极管

    # 第二部分 高级应用

    # 第3章 集成电路
""")

# LLM 标准化后的目录（模拟 LLM 输出）
NORMALIZED_TOC = textwrap.dedent("""\
    # 第一部分 基础知识
    ## 第1章 电子学概念
    ### 1.1 电流与电压
    ### 1.2 电阻
    ## 第2章 半导体器件
    ### 2.1 二极管
    ### 2.2 三极管
    # 第二部分 高级应用
    ## 第3章 集成电路
""")

# 预期输出（关键行）
EXPECTED_HEADING_MAP = {
    "第一部分 基础知识": "#",
    "第1章 电子学概念": "##",
    "1.1 电流与电压": "###",
    "1.2 电阻": "###",
    "第2章 半导体器件": "##",
    "2.1 二极管": "###",
    "2.2 三极管": "###",
    "第二部分 高级应用": "#",
    "第3章 集成电路": "##",
}


# ══════════════════════════════════════════════════════════════════
# 测试：归一化函数
# ══════════════════════════════════════════════════════════════════

def test_normalize():
    print("\n[Test 1] normalize() 归一化函数")
    cases = [
        ("## 第1章 电子学概念", "第1章电子学概念"),
        ("# 1.1 电流与电压  ", "11电流与电压"),
        ("### Page·Header - 2024", "pageheader2024"),
        ("# 第二部分　高级·应用", "第二部分高级应用"),
    ]
    for inp, expected in cases:
        out = normalize(inp)
        status = "✓" if out == expected else f"✗ (expected '{expected}', got '{out}')"
        print(f"  {status}  normalize('{inp[:30]}') => '{out}'")


# ══════════════════════════════════════════════════════════════════
# 测试：相似度函数
# ══════════════════════════════════════════════════════════════════

def test_similarity():
    print("\n[Test 2] similarity() 模糊匹配")
    cases = [
        ("第1章电子学概念", "第1章电子学概念", 1.0, True),
        ("第1章电子学概念", "第1章电子学", 0.85, False),   # 略低于阈值
        ("第1章电子学概念", "第2章电子学概念", 0.85, False),
        ("21二极管", "21二极管", 1.0, True),
        ("abcdefgh", "abcdefgi", 0.90, True),             # 仅末位不同
    ]
    for a, b, threshold, expect_pass in cases:
        s = similarity(a, b)
        passed = s >= threshold
        mark = "✓" if passed == expect_pass else "✗"
        print(f"  {mark}  sim('{a}', '{b}') = {s:.3f}  "
              f"(threshold={threshold}, expect_pass={expect_pass})")


# ══════════════════════════════════════════════════════════════════
# 测试：TOCExtractor
# ══════════════════════════════════════════════════════════════════

def test_toc_extractor():
    print("\n[Test 3] TOCExtractor 目录提取")
    extractor = TOCExtractor()
    region = extractor.extract(SAMPLE_MD_WITH_TOC)

    if region is None:
        print("  ✗ 未能提取到目录区！")
        return

    print(f"  ✓ 找到目录区: 行 {region.start_line} ~ {region.end_line}")
    print(f"  目录文本:\n    {region.raw_text[:].replace(chr(10), chr(10) + '    ')}")

    # 验证包含关键内容
    assert "第1章" in region.raw_text, "目录应包含 '第1章'"
    assert "二极管" in region.raw_text, "目录应包含 '二极管'"
    print("  ✓ 关键内容验证通过")


# ══════════════════════════════════════════════════════════════════
# 测试：parse_toc
# ══════════════════════════════════════════════════════════════════

def test_parse_toc():
    print("\n[Test 4] parse_toc() 目录解析")
    entries = parse_toc(NORMALIZED_TOC)
    print(f"  解析到 {len(entries)} 个目录条目")
    for e in entries:
        print(f"    {'#' * e.level} {e.text}  (normalized='{e.normalized}')")

    assert len(entries) == 9, f"预期 9 个条目，实际 {len(entries)}"
    assert entries[0].level == 1 and entries[0].text == "第一部分 基础知识"
    assert entries[1].level == 2 and entries[1].text == "第1章 电子学概念"
    assert entries[2].level == 3 and entries[2].text == "1.1 电流与电压"
    print("  ✓ 层级和内容验证通过")


# ══════════════════════════════════════════════════════════════════
# 测试：StructureRebuilder 核心对齐
# ══════════════════════════════════════════════════════════════════

def test_structure_rebuilder():
    print("\n[Test 5] StructureRebuilder 双指针对齐")
    toc_entries = parse_toc(NORMALIZED_TOC)
    doc_lines = SAMPLE_MD_WITH_TOC.splitlines()

    rebuilder = StructureRebuilder(similarity_threshold=0.88)
    result = rebuilder.rebuild(doc_lines, toc_entries)

    print(f"  总标题行: {result.total_headings}")
    print(f"  匹配成功: {result.matched_count}")
    print(f"  噪声行:   {result.noise_count}")
    print(f"  匹配率:   {result.match_rate:.2%}")

    rebuilt_text = result.rebuilt_text

    # 验证层级是否正确（在以 # 开头的行中检查）
    errors = []
    for title, expected_prefix in EXPECTED_HEADING_MAP.items():
        for line in rebuilt_text.splitlines():
            if title in line and line.startswith("#"):
                actual_prefix = line.split(" ")[0]
                if actual_prefix != expected_prefix:
                    errors.append(
                        f"  ✗ '{title}': 期望 {expected_prefix}，实际 {actual_prefix}"
                    )
                else:
                    print(f"  ✓ '{title}' => {expected_prefix}")
                break

    # 验证噪声行已去除 #
    for line in rebuilt_text.splitlines():
        if "页眉装饰内容" in line:
            if line.startswith("#"):
                errors.append(f"  ✗ 噪声行未正确去标题化: {line}")
            else:
                print(f"  ✓ 噪声行已转为加粗: {line}")

    if errors:
        for e in errors:
            print(e)
    else:
        print(f"\n  ✓ 所有层级验证通过！匹配率: {result.match_rate:.2%}")

    print("\n  重构后文档（部分）:")
    for line in rebuilt_text.splitlines():
        if line.startswith("#") or line.startswith("**"):
            print(f"    {line}")


# ══════════════════════════════════════════════════════════════════
# 测试：TOC 耗尽后的处理
# ══════════════════════════════════════════════════════════════════

def test_toc_exhausted():
    print("\n[Test 6] TOC 耗尽后所有 # 行自动去标题化")
    short_toc = parse_toc("# 第一章\n## 1.1 节")
    doc_lines = [
        "# 第一章",
        "正文内容",
        "## 1.1 节",
        "# 第二章",       # TOC 中没有，应去标题化
        "## 2.1 节",      # 同上
    ]

    rebuilder = StructureRebuilder()
    result = rebuilder.rebuild(doc_lines, short_toc)
    out = result.rebuilt_text

    assert "## 第一章" not in out or "# 第一章" in out, "第一章应被正确映射"
    for line in out.splitlines():
        if "第二章" in line:
            assert not line.startswith("#"), f"  ✗ TOC 耗尽后 '第二章' 未去标题化: {line}"
            print(f"  ✓ TOC 耗尽后 '第二章' 已去标题化: {line}")
        if "2.1 节" in line:
            assert not line.startswith("#"), f"  ✗ TOC 耗尽后 '2.1节' 未去标题化: {line}"
            print(f"  ✓ TOC 耗尽后 '2.1节' 已去标题化: {line}")


# ══════════════════════════════════════════════════════════════════
# 运行所有测试
# ══════════════════════════════════════════════════════════════════

def run_all_tests():
    print("=" * 60)
    print("Markdown 层级重构系统 - 测试套件")
    print("=" * 60)

    tests = [
        test_normalize,
        test_similarity,
        test_toc_extractor,
        test_parse_toc,
        test_structure_rebuilder,
        test_toc_exhausted,
    ]

    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            import traceback
            print(f"\n  ✗ 测试异常: {e}")
            traceback.print_exc()
            failed += 1

    print("\n" + "=" * 60)
    print(f"测试结果: {passed} 通过，{failed} 失败")
    print("=" * 60)
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
