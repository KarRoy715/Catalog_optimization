from pathlib import Path
import re
import os

input_dir = Path("/mnt/nfs_dev/zah/data/book")
files = sorted([f for f in input_dir.rglob("*.md") if 'debug' not in f.parts])
print(files)


def has_chinese_char(text):
    """
    检测字符串中是否包含中文字符
    原理：检查字符的 Unicode 编码是否在常用汉字范围内
    """
    for char in text:
        if '\u4e00' <= char <= '\u9fff':
            return True
    return False

def is_english_file(filename):
    """
    判断文件是否为英文文件
    规则：文件名中不存在任何中文字符，即为英文文件
    """
    # 1. 获取文件名主体（去除后缀）
    # 兼容处理：如果输入是字符串路径，先转为 Path 对象
    if isinstance(filename, str):
        p = Path(filename)
    else:
        p = filename
    
    name_without_ext = p.stem
    
    # 2. 核心逻辑：如果没有中文字符，就认为是英文文件
    # 如果检测函数返回 False (无中文)，则 is_english 为 True
    return not has_chinese_char(name_without_ext)

def extract_toc_robust(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    start_idx = -1
    for i, line in enumerate(lines):
        clean_line = line.strip().replace(" ", "")
        if re.search(r'^#*目录$', clean_line) or re.search(r'^#*CONTENTS$', clean_line, re.I) or re.search(r'^#*目 录$', clean_line):
            start_idx = i
            break
            
    if start_idx == -1: return "False", None, None, file_path

    # --- 阶段 1: 采样前 5-8 行有效标题作为锚点集合 ---
    anchor_set = []
    anchor_clean_set = []
    scan_limit = 8 # 稍微多扫几行以确保抓到核心标题
    found_count = 0
    
    for i in range(start_idx + 1, int(len(lines)*0.2)):
        line_content = lines[i].strip().replace("#", "").strip()
        if not line_content: continue

        pure_title = re.sub(r'\s+\d+$', '', line_content).strip()
        anchor_clean_set.append(pure_title.replace(" ", "") )
        
        # if pure_title in anchor_set or pure_title in anchor_clean_set:
        #     return anchor_set
        
        anchor_set.append(pure_title)
        found_count += 1
            
        if found_count >= scan_limit or i > start_idx + 20: # 找到5个或扫描超过20行就停止
            break
    # anchor_clean_set =  [item.replace(" ", "") for item in anchor_set]
    end_start_idx = i + 1

    # --- 阶段 2: 寻找终点 ---
    end_idx = -1
    i = end_start_idx
    limit = int(len(lines) * 0.2)
    
    while i < limit:
        line_raw = lines[i].strip()
        clean_content = line_raw.replace("#", "").strip().replace(" ", "")
        
        # 1. 检查是否匹配锚点集合 (正文标题重现)
        is_anchor_match = clean_content and any(clean_content.lower() in anchor.lower() for anchor in anchor_set)
        is_anchor_clean_match = clean_content and any(clean_content.lower() in anchor.lower() for anchor in anchor_clean_set)
        is_match = any(clean_content == anchor.replace(" ", "") for anchor in anchor_set)
        has_page_num = re.search(r'\s\d+$', line_raw)
    
        if (is_anchor_match and not has_page_num) or(is_anchor_clean_match and not has_page_num) or  is_match:
            end_idx = i
            break
    
        # 2. 兜底逻辑：贪婪匹配参考文献
        # 匹配规则：去掉符号、数字、标点后，内容等于“参考文献”等
        # 使用 re.sub 去掉非中文字符和非英文字母
        simplified_content = re.sub(r'[^\u4e00-\u9fa5a-zA-Z]', '', clean_content)
        is_ref_header = re.match(r'^(参考?文献|Bibliography|References)$', simplified_content, re.IGNORECASE)
    
        if is_ref_header:
            # 初始标记为当前行
            end_idx = i + 1
            
            # 开启贪婪探测模式：向后查找 50 行
            look_ahead_idx = i + 1
            while look_ahead_idx < min(i + 51, limit):
                next_line = lines[look_ahead_idx].strip()
                next_clean = next_line.replace("#", "").strip().replace(" ", "")
                next_simplified = re.sub(r'[^\u4e00-\u9fa5a-zA-Z]', '', next_clean)
                
                # 如果在 50 行内又发现了一个独立的“参考文献”行
                if re.match(r'^(参考?文献|Bibliography|References)$', next_simplified, re.IGNORECASE):
                    end_idx = look_ahead_idx + 1
                    # 重置 i 到新发现的位置，以便外层循环能继续从这里开始下一次 50 行的探测
                    i = look_ahead_idx 
                    # 更新 look_ahead_idx 重新开始算 50 行
                    look_ahead_idx = i + 1
                    continue
                
                look_ahead_idx += 1
            
            # 探测结束，跳出外层循环
            break
        
        i += 1

    # --- 阶段 3: 返回截取结果 ---
    if end_idx != -1:
        # 如果是分行标题，end_idx 可能是标题的第二行，视情况可以向上调1行
        return lines[start_idx:end_idx], start_idx, end_idx, file_path
    else:
        # 极端情况兜底：取目录开始后的300行
        return "False", None, None
    

def auto_detect_hierarchy(md_content):
    # 1. 预定义可能的特征提取正则 (按优先级排序)
    feature_patterns = [
        r'第[一二三四五六七八九十\d]+篇',
        r'第[一二三四五六七八九十\d]+章',
        r'第[一二三四五六七八九十\d]+节',
        r'第[一二三四五六七八九十\d]+单元',
        r'第[一二三四五六七八九十\d]+部分',
        
        r'(?:单元|任务|项目)[一二三四五六七八九十\d]+', # 单元、任务

        r'\d+\.\d+\.\d+', # 1.1.1
        r'\d+\.\d+',      # 1.1
        r'\d+[\.．]\s*',       # 1. (带点),后面有无空格都可以，全角半角都支持
        r'^[一二三四五六七八九十]+、', # 一、
        r'^\d+\s',        # 1 (空格)
        r'^\(\d+\)',      # (1)
        r'^\([一二三四五六七八九十]+\)' # (一)
    ]

    level_queue = [] # 存储本篇文档发现的特征指纹
    output_lines = []
    
    for line in md_content:
        raw_content = line.strip()
        raw_content = raw_content.lstrip('#')
        raw_content = raw_content.strip()
        if not raw_content: continue
        
        # 移除行首旧的 # 和行尾页码
        clean_text = re.sub(r'^#+\s*', '', raw_content)
        clean_text = re.sub(r'[\.\…]{2,}', '', clean_text)
        pattern = r'\s*\(\d+\)\s*$|\s+\d+$'
        clean_text = re.sub(pattern, '', clean_text, flags=re.MULTILINE)
        
        current_fingerprint = None
        
        # 匹配特征
        for p in feature_patterns:
            match = re.search(p, clean_text)
            if match:
                # 修改部分：先标准化分隔符，再提取特征
                # 将匹配到的文本中的 '.' 或 '、' 及其后的空格统一为 '. '
                normalized_match = re.sub(r'[\.、]\s*', '. ', match.group())
                
                # 提取纯特征，忽略具体数字
                current_fingerprint = re.sub(r'\d+', '\\\\d', normalized_match)
                current_fingerprint = re.sub(r'[一二三四五六七八九十]+', 'CN', current_fingerprint)
                break
        
        if current_fingerprint:
            # 如果是新特征，加入层级队列
            if current_fingerprint not in level_queue:
                level_queue.append(current_fingerprint)
            
            # 计算当前层级 (Index 从 0 开始，所以 +1)
            depth = level_queue.index(current_fingerprint) + 1
            output_lines.append(f"{'#' * depth} {clean_text}")
        else:
            # 如果没匹配到任何特征，视为普通文本或维持原样
            if clean_text == "参考文献" or clean_text.lower() == "bibliography" or clean_text.lower() == "references":
                output_lines.append(f"{'#' * 1} {clean_text}")
            else:
                output_lines.append(raw_content)
            
    return "\n".join(output_lines)



# 调用示例
false_md = []
toc_list = []
for i in range(len(files)):
    if not (is_english_file(files[i])):
        toc_blocks, start_idx, end_idx, file_path = extract_toc_robust(files[i])
        if toc_blocks == "False":
            false_md.append(files[i])
        else:
            if toc_blocks == "False":
                false_md.append(files[i]) 
            else:
                toc_blocks = [block for block in toc_blocks if len(block) <= 50]
                print(f"------------------------{i}--------------------------")
                print(toc_blocks)
                toc_list.append((toc_blocks, start_idx, end_idx, file_path))
    else:
        pass
        # TODO：处理英文
print(false_md)


# def rewrite_md(processwd_toc, start_idx, end_idx, file_path):
#     with open(file_path, 'r', encoding='utf-8') as f:
#         lines = f.readlines()
#         for line in lines

        

processed_toc_list = []
for idx, toc in enumerate(toc_list):
    toc_content, start_idx, end_idx, file_path = toc
    processed_toc = auto_detect_hierarchy(toc_content)
    processed_toc_list.append((processed_toc, start_idx, end_idx, file_path))
for idx, item in enumerate(processed_toc_list):
    processwd_toc, start_idx, end_idx, file_path = item
    rewrite_md(processwd_toc, start_idx, end_idx, file_path)



# with open("output_result.txt", "w", encoding="utf-8") as f:
#     for idx, toc in enumerate(toc_list):
#         toc_content, start_idx, end_idx = toc
#         output = auto_detect_hierarchy(toc_content)
        
#         # 2. 打印到控制台 (保持原本的显示效果)
#         print(f"-------------------------------{idx}------------------------")
#         print(output)
#         print("*"*100)
        
#         # 3. 同时写入到文件 (关键步骤：加上 file=f)
#         print(f"-------------------------------{idx}------------------------", file=f)
#         print(output, file=f)
#         print("*"*100, file=f)
# 
# print("✅ 数据已成功保存到 output_result.txt")