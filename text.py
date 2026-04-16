import os
import re
from collections import defaultdict
def clean_description(text):
    if not text:
        return ""
    
    # --- 优化点解析 ---
    # 1. [A-Z0-9一二三四五六七八九十]+ : 将 A-Z 加入并允许一个或多个字符。
    # 2. 这里的字符类涵盖了 AA, A.1, 1.1, 一, 十二 等所有组合。
    # 3. \s* 允许在“表”和“AA.1”之间，以及编号内部存在空格。
    
    pattern = (
        r"^("
        r"(图|表|Figure|Table|Fig)\s*[A-Z0-9一二三四五六七八九十.\s（）\(\)-]+" # 关键词+复合编号
        r"|"
        r"[a-z][\)）]|\([a-z][\)）]" # 子图编号如 a) 或 (a)
        r")"
        r"[.。:：\s]*" # 结尾分隔符
    )
    
    last_text = ""
    cleaned_text = text.strip()
    
    while last_text != cleaned_text:
        last_text = cleaned_text
        # 使用 IGNORECASE 确保能够匹配 figure/Figure, table/Table
        cleaned_text = re.sub(pattern, "", cleaned_text, flags=re.IGNORECASE).strip()
    
    return cleaned_text
def extract_table_logic_v4():
    # 你的路径保持不变
    path = "/mnt/nfs_dev/zah/data/book/Standand/GB／T 13915-2013 冲压件角度公差.pdf/tables" 
    
    if not os.path.exists(path):
        print(f"路径不存在: {path}")
        return

    files = os.listdir(path)
    
    txt_map = defaultdict(list)
    jpg_files = []

    # 1. 提取文件并分组
    for f in files:
        if f.endswith('.txt'):
            # 保持原有的前缀提取逻辑
            prefix = "_".join(f.split('_')[:-4])
            txt_map[prefix].append(f)
        elif f.endswith('.jpg'):
            prefix = "_".join(f.split('_')[:-4])
            jpg_files.append({
                "prefix": prefix,
                "name": f
            })

    jpg_files.sort(key=lambda x: [int(c) if c.isdigit() else c for c in re.split(r'(\d+)', x['name'])])

    results = []
    # 记忆变量
    last_full_title = "未知标题"

    # 3. 顺序处理
    for item in jpg_files:
        prefix = item["prefix"]
        jpg_name = item["name"]
        
        current_txt_title = ""
        is_continued = False
        
        matched_txts = txt_map.get(prefix, [])
        
        # 对该组内的 txt 也做一个排序，确保取到最合适的
        matched_txts.sort()
        
        for txt_name in matched_txts:
            txt_path = os.path.join(path, txt_name)
            try:
                with open(txt_path, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if content.startswith('表'):
                        # 增强健壮性：处理 “（续）” 或 “续表”
                        if "续" in content:
                            is_continued = True
                        else:
                            current_txt_title = content
                            last_full_title = content
                        break
            except Exception:
                continue

        # 4. 标题判定
        if is_continued:
            # 还原标题：如果是续表，则使用记忆中最近的一个主标题
            final_title = last_full_title
        elif current_txt_title:
            current_txt_title = clean_description(current_txt_title)
            final_title = current_txt_title
            last_full_title = final_title
        else:
            # 如果这组文件没有任何“表”字开头的 txt，说明可能是表格中间的内容
            final_title = f"{last_full_title} (关联)"

        results.append((jpg_name, final_title))

    # 5. 输出
    print(f"{'图片文件名':<60} | {'解析出的标题'}")
    print("-" * 100)
    for img, title in results:
        print(f"{img:<60} | {title}")

if __name__ == "__main__":
    extract_table_logic_v4()