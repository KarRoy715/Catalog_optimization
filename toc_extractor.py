import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TOCRegion:
    """目录区域信息"""
    raw_text: str           # 原始目录文本
    start_line: int         # 目录起始行号（相对整个文档）
    end_line: int           # 目录结束行号（含）
    toc_lines: list = field(default_factory=list)  # 原始目录行列表


# ── 目录边界检测规则 ──────────────────────────────────────────────
_TOC_HEADER_PATTERNS = [
    r'^#{1,3}\s*(目\s*录|contents?|table\s+of\s+contents?|index)\s*$',
    r'^(目\s*录|contents?|table\s+of\s+contents?)\s*$',
]

_TOC_ENTRY_PATTERNS = [
    r'[·\.\-–—\s]{2,}\d+\s*$',       # 点线 + 页码
    r'\s+\d{1,4}\s*$',                # 末尾空格+数字
    r'^#{1,6}.*\d{1,4}\s*$',          # # 开头行末尾有数字
    # 常见 Markdown 自动目录（无“目录”标题也能命中）
    r'^\s*[-*+]\s+\[[^\]]+\]\([^)]+\)\s*$',          # - [标题](#anchor)
    r'^\s*\d+[\.\)]\s+\[[^\]]+\]\([^)]+\)\s*$',      # 1. [标题](#anchor)
    # 目录中常见的“章/节/部分”行有时缺失页码（OCR/抽取丢失），但仍应视为目录条目
    r'^\s*#{0,6}\s*(第[零一二三四五六七八九十百千\d]+章)\b.*$',        # 第11章 xxx（可无页码）
    r'^\s*#{0,6}\s*(第[零一二三四五六七八九十百千\d]+[节篇部分])\b.*$', # 第1节/第一部分…
    r'^\s*#{0,6}\s*[Cc]hapter\s+\d+\b.*$',                              # Chapter 11 ...
    # 纯数字编号条目（有时页码缺失）
    r'^\s*#{0,6}\s*\d+(?:\.\d+){1,6}\s*\S.*$',                          # 3.6.2 xxx（可无页码）
    r'^\s*#{0,6}\s*\d+\s*[\.\)]\s*\S.*$',                               # 1) xxx / 1. xxx
    # 中文序号条目（可能无页码）
    r'^\s*#{0,6}\s*[一二三四五六七八九十]+、\s*\S.*$',                   # 二、常用一般资料 (98)
    r'^\s*#{0,6}\s*（[一二三四五六七八九十]+）\s*\S.*$',                 # （一）压铸的优点
    # 目录里的常见非编号条目（可能无页码）
    r'^\s*#{0,6}\s*(前\s*言|序\s*言|引\s*言|后\s*记|致\s*谢|结\s*语|附\s*录)\s*.*$',
    r'^\s*#{0,6}\s*(参考文献|索引|参考资料)\s*.*$',
    r'^\s*#{0,6}\s*(preface|introduction|appendix|bibliography|references|index)\b.*$',
]

_BODY_START_PATTERNS = [
    r'^#{1,3}\s*(第[零一二三四五六七八九十百千\d]+[章节篇部分])',
    r'^#{1,3}\s*[Cc]hapter\s+\d',
    r'^#{1,3}\s*\d+[\.\、]\s*\S',
    r'^#{1,3}\s*(前\s*言|[Pp]reface|[Ii]ntroduction)', 
    r'^(前\s*言|[Pp]reface|[Ii]ntroduction)\s*$',
]

_TOC_HEADER_RE = [re.compile(p, re.IGNORECASE) for p in _TOC_HEADER_PATTERNS]
_TOC_ENTRY_RE  = [re.compile(p) for p in _TOC_ENTRY_PATTERNS]
_BODY_START_RE = [re.compile(p, re.IGNORECASE) for p in _BODY_START_PATTERNS]


def _is_toc_header(line: str) -> bool:
    stripped = line.strip()
    return any(r.match(stripped) for r in _TOC_HEADER_RE)

def _is_markdown_heading(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    # 允许 "## 标题" / "#标题" 两种风格
    return bool(re.match(r"^#{1,6}\s*\S", stripped))

def _is_fence(line: str) -> bool:
    return bool(re.match(r"^\s*```", line))

def _has_page_hint(line: str) -> bool:
    """
    目录条目的页码/页码提示（包含括号页码、纯数字页码、点线引导等）。
    用于区分“目录区”与正文中被拆成多行的标题块。
    """
    s = line.strip()
    if not s:
        return False
    if re.search(r"[·\.\-–—\s]{2,}\d+\s*$", s):  # 点线 + 页码
        return True
    if re.search(r"\(\s*\d{1,4}\s*\)\s*$", s):   # (118)
        return True
    if re.search(r"\s+\d{1,4}\s*$", s):          # 末尾空格+页码
        return True
    return False

def _is_backmatter_marker(line: str) -> bool:
    """
    目录中的“末尾标记”（参考文献/索引等）。其后出现的无页码标题通常已经进入正文，不应继续吞。
    """
    s = re.sub(r"^#{1,6}\s*", "", line.strip())
    if not s:
        return False
    return bool(re.search(r"(参考文献|索引|bibliography|references|index)\b", s, flags=re.IGNORECASE))


def _is_toc_entry(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    return any(r.search(stripped) for r in _TOC_ENTRY_RE)

def _is_strong_toc_entry(line: str) -> bool:
    """
    “强目录条目”：更像目录而不像正文标题的行。
    用于启发式搜索的起点判断，避免在正文里误起一段“伪目录”。
    """
    if not _is_toc_entry(line):
        return False
    s = line.strip()
    # Markdown 链接型目录
    if re.match(r'^\s*([-*+]|\d+[\.\)])\s+\[[^\]]+\]\([^)]+\)\s*$', s):
        return True
    # 带页码/点线提示的目录
    return _has_page_hint(line)


def _is_body_start(line: str) -> bool:
    stripped = line.strip()
    return any(r.match(stripped) for r in _BODY_START_RE)


class TOCExtractor:
    """
    从 Markdown 文档中定位并提取目录区域。
    """

    def __init__(self,
                 max_blank_lines: int = 2,
                 min_entry_count: int = 3,
                 search_limit: int = 800,
                 max_numeric_depth: int = 3):
        self.max_blank_lines = max_blank_lines
        self.min_entry_count = min_entry_count
        self.search_limit = search_limit
        self.max_numeric_depth = max_numeric_depth

    # ── 公开接口 ─────────────────────────────────────────────────

    def extract(self, md_content: str, build_if_missing: bool = True) -> Optional[TOCRegion]:
        lines = md_content.splitlines()
        region = self._find_by_header(lines)
        if region is None:
            region = self._find_by_heuristic(lines)
        if region is None and build_if_missing:
            region = self._build_from_headings(lines)
        if region is not None:
            region = self._limit_depth(region)
        return region

    # ── 私有方法 ─────────────────────────────────────────────────

    def _trim_region(self, lines: list[str], start: int, end: int) -> TOCRegion:
        """修剪尾部空行并封装结果"""
        while end > start and not lines[end].strip():
            end -= 1

        # 若尾部被误吞进正文，通常表现为：后段很少再出现“页码提示”，
        # 因此优先回退到最后一个带页码提示/参考文献索引等标记的条目。
        last_strong = -1
        for k in range(end, start - 1, -1):
            line = lines[k]
            if _is_toc_entry(line) and (_has_page_hint(line) or _is_backmatter_marker(line)):
                last_strong = k
                break
        if last_strong != -1 and last_strong < end:
            end = last_strong
            while end > start and not lines[end].strip():
                end -= 1
        
        target_lines = lines[start: end + 1]
        return TOCRegion(
            raw_text="\n".join(target_lines),
            start_line=start,
            end_line=end,
            toc_lines=target_lines,
        )

    def _numeric_depth(self, line: str) -> int:
        """
        返回以数字编号开头的层级深度：
          - "1 标题" -> 1
          - "1.2 标题" -> 2
          - "1.2.3 标题" -> 3
          - "1.2.3.4 标题" -> 4
        不匹配则返回 0（不参与裁剪）。
        """
        s = line.strip()
        # 常见：1.2.3 / 1.2 / 1.2.3.4（后面允许空格或直接接标题）
        m = re.match(r"^(\d+(?:\.\d+){0,10})\b", s)
        if not m:
            return 0
        return m.group(1).count(".") + 1

    def _limit_depth(self, region: TOCRegion) -> Optional[TOCRegion]:
        """
        将目录最低层级限制为 x.x.x（默认 3 层）。
        若条目编号超过该层级（例如 1.2.3.4），则忽略该条目行。
        """
        if self.max_numeric_depth <= 0:
            return region

        kept: list[str] = []
        for line in region.toc_lines:
            depth = self._numeric_depth(line)
            if depth and depth > self.max_numeric_depth:
                continue
            kept.append(line)

        # 如果过滤后条目过少，认为该目录不可用（让上游走兜底/或返回 None）
        kept_entry_count = sum(1 for l in kept if _is_toc_entry(l))
        if kept_entry_count < self.min_entry_count:
            return None

        region.toc_lines = kept
        region.raw_text = "\n".join(kept)
        return region

    def _find_by_header(self, lines: list[str]) -> Optional[TOCRegion]:
        limit = min(len(lines), self.search_limit)
        toc_start = None

        for i in range(limit):
            if _is_toc_header(lines[i]):
                toc_start = i
                break

        if toc_start is None:
            return None

        end_line = toc_start
        blank_run = 0
        entry_count = 0
        non_entry_run = 0
        heading_no_page_run = 0
        last_entry_with_page = toc_start
        backmatter_seen = False
        recent_entry_has_page: list[bool] = []

        for j in range(toc_start + 1, len(lines)):
            line = lines[j]
            stripped = line.strip()

            if not stripped:
                blank_run += 1
                if blank_run > self.max_blank_lines:
                    break
                continue

            # 优化点：遇到正文标识且该行不是条目特征，立即切断
            if _is_body_start(line) and not _is_toc_entry(line):
                break
            # 目录结束的常见形态：目录条目后出现新的 Markdown 标题（如“主要观点/正文/摘要”等）
            # 该标题通常不带页码/点线，因此不应被当作目录条目吞进去。
            if entry_count >= self.min_entry_count and _is_markdown_heading(line) and not _is_toc_entry(line):
                break
            # 若目录已经出现“参考文献/索引”等尾部标记，则其后的无页码标题通常是正文开头
            if backmatter_seen and _is_markdown_heading(line) and not _has_page_hint(line):
                break

            blank_run = 0
            if _is_toc_entry(line):
                entry_count += 1
                non_entry_run = 0
                has_page = _has_page_hint(line)
                recent_entry_has_page.append(has_page)
                if len(recent_entry_has_page) > 40:
                    recent_entry_has_page.pop(0)

                if has_page:
                    last_entry_with_page = j
                    heading_no_page_run = 0
                elif _is_markdown_heading(line):
                    heading_no_page_run += 1
                else:
                    heading_no_page_run = 0
                if _is_backmatter_marker(line):
                    backmatter_seen = True
                end_line = j

                # 若最近一段目录条目几乎都不带页码提示，通常说明已经进入正文（标题/段落块）
                if entry_count >= max(self.min_entry_count, 30) and len(recent_entry_has_page) >= 30:
                    page_ratio = sum(recent_entry_has_page) / len(recent_entry_has_page)
                    if page_ratio < 0.15:
                        end_line = last_entry_with_page
                        break
                continue
            else:
                non_entry_run += 1
                heading_no_page_run = 0

            # 目录区域内部允许少量“非条目行”（例如目录中混入的空白/分隔/扫描噪声）。
            # 但若已经看到足够多的条目后，连续出现多行“非条目”，通常意味着进入正文段落，应截断。
            if entry_count >= self.min_entry_count and non_entry_run >= 2:
                break

            # 若出现连续多行“像目录标题但没有页码提示”的 Markdown 标题，常见于正文的拆行标题块。
            # 此时将结束行回退到最后一个带页码提示的条目，避免把正文开头吞进目录。
            if entry_count >= self.min_entry_count and heading_no_page_run >= 3:
                end_line = last_entry_with_page
                break
            
            end_line = j

        if entry_count < self.min_entry_count:
            return None

        return self._trim_region(lines, toc_start, end_line)

    def _find_by_heuristic(self, lines: list[str]) -> Optional[TOCRegion]:
        limit = min(len(lines), self.search_limit)
        best_start, best_end, best_count = -1, -1, 0

        i = 0
        while i < limit:
            if _is_strong_toc_entry(lines[i]):
                j = i
                count = 0
                blank_run = 0
                last_valid_j = i
                non_entry_run = 0
                heading_no_page_run = 0
                last_entry_with_page = i
                backmatter_seen = False
                recent_entry_has_page: list[bool] = []
                
                while j < limit:
                    line = lines[j]
                    stripped = line.strip()

                    if not stripped:
                        blank_run += 1
                        if blank_run > self.max_blank_lines: break
                    elif _is_body_start(line) and not _is_toc_entry(line):
                        break
                    elif count >= self.min_entry_count and _is_markdown_heading(line) and not _is_toc_entry(line):
                        break
                    elif backmatter_seen and _is_markdown_heading(line) and not _has_page_hint(line):
                        break
                    elif _is_toc_entry(line):
                        count += 1
                        blank_run = 0
                        last_valid_j = j
                        non_entry_run = 0
                        has_page = _has_page_hint(line)
                        recent_entry_has_page.append(has_page)
                        if len(recent_entry_has_page) > 40:
                            recent_entry_has_page.pop(0)

                        if has_page:
                            last_entry_with_page = j
                            heading_no_page_run = 0
                        elif _is_markdown_heading(line):
                            heading_no_page_run += 1
                        else:
                            heading_no_page_run = 0
                        if _is_backmatter_marker(line):
                            backmatter_seen = True

                        if count >= max(self.min_entry_count, 30) and len(recent_entry_has_page) >= 30:
                            page_ratio = sum(recent_entry_has_page) / len(recent_entry_has_page)
                            if page_ratio < 0.15:
                                last_valid_j = last_entry_with_page
                                break
                    else:
                        blank_run = 0
                        non_entry_run += 1
                        if count >= self.min_entry_count and non_entry_run >= 2:
                            break
                        if count >= self.min_entry_count and heading_no_page_run >= 3:
                            last_valid_j = last_entry_with_page
                            break
                    j += 1

                if count >= self.min_entry_count and count > best_count:
                    best_start, best_end, best_count = i, last_valid_j, count
                i = j
            else:
                i += 1

        if best_start == -1:
            return None

        return self._trim_region(lines, best_start, best_end)

    def _build_from_headings(self, lines: list[str]) -> Optional[TOCRegion]:
        """
        当文档里没有显式目录时，从正文标题自动生成一个“目录文本”。
        仅用于提供给后续 LLM/对齐模块作为 TOC 输入，不会回写到原文。
        """
        in_code_block = False
        headings: list[tuple[int, str]] = []

        for line in lines:
            if _is_fence(line):
                in_code_block = not in_code_block
                continue
            if in_code_block:
                continue

            m = re.match(r"^(#{1,6})\s*(.+?)\s*$", line.strip())
            if not m:
                continue

            level = len(m.group(1))
            title = m.group(2).strip().strip("#").strip()
            if not title:
                continue

            # 跳过“目录/contents”这种标题本身（避免把它当作正文结构）
            if re.fullmatch(r"(目\s*录|contents?|table\s+of\s+contents?)", title, flags=re.IGNORECASE):
                continue

            headings.append((level, title))

        if len(headings) < self.min_entry_count:
            return None

        min_level = min(lv for lv, _ in headings)
        toc_lines: list[str] = []
        for lv, title in headings:
            norm_lv = max(1, min(6, 1 + (lv - min_level)))
            toc_lines.append(f"{'#' * norm_lv} {title}")

        return TOCRegion(
            raw_text="\n".join(toc_lines),
            start_line=-1,
            end_line=-1,
            toc_lines=toc_lines,
        )