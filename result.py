from pathlib import Path
from pyzbar import pyzbar
import cv2
import numpy as np
from pyzbar.pyzbar import decode
from PIL import Image
import json
import re
from datetime import datetime
import requests
import base64
import os
from collections import defaultdict


# ── 输入文件 ──────────────────────────────────────────────────────────────────
input_dir = Path("/mnt/nfs_dev/zah/data/book/Standand")
files = sorted([f for f in input_dir.rglob("*.md") if 'debug' not in f.parts])


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def is_barcode_or_qr(image_path):
    """存在二维码或条形码"""
    img = Image.open(image_path)
    codes = pyzbar.decode(img)
    return len(codes) > 0


def is_blank(img_path):
    """存在空白图片"""
    img = cv2.imread(str(img_path), cv2.IMREAD_GRAYSCALE)
    std_dev = np.std(img)
    return std_dev < 5  # 阈值可调，5通常能过滤掉几乎纯白的图


def call_multimodal_llm(img_path, above_context, below_context):
    """调用部署的 Qwen3.5 模型生成图片描述"""
    api_url = "https://f5.infer.nanhu.zhejianglab.org/nanhuinfer/qwen3.5-397-2-94720/v1/chat/completions"
    api_key = "sk-1241422052882210816"

    def encode_image(path):
        try:
            with open(path, "rb") as image_file:
                return base64.b64encode(image_file.read()).decode('utf-8')
        except Exception:
            return None

    base64_image = encode_image(img_path)
    if not base64_image:
        return "错误：找不到图片文件"

    extension = Path(img_path).suffix.lower().replace('.', '')
    extension = 'jpeg' if extension in ['jpg', 'jpeg'] else 'png'

    prompt = f"参考上下文：\n上文：{above_context}\n下文：{below_context}\n任务：用不超过15个字描述图片，直接输出内容,也不要加示意图等文字。"

    payload = {
        "model": "Qwen3.5-397B-A17B",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/{extension};base64,{base64_image}"}
                    }
                ]
            }
        ],
        "max_tokens": 2000,
        "temperature": 0.1
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    try:
        response = requests.post(api_url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        res_data = response.json()

        message = res_data.get('choices', [{}])[0].get('message', {})
        content = message.get('content')
        if not content:
            content = message.get('reasoning_content', "")

        if not content:
            print(f"    [Warning] 模型未返回有效文字: {res_data}")
            return "图片描述解析失败"

        clean_res = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL)
        clean_res = clean_res.replace("\n", "").replace('"', '').replace('。', '').strip()

        return clean_res if clean_res else "描述生成为空"

    except Exception as e:
        print(f"    [LLM Error] 调用失败: {e}")
        return "图片描述获取失败"


def clean_description(text):
    if not text:
        return ""

    pattern = (
        r"^("
        r"(图|表|Figure|Table|Fig)\s*[A-Z0-9一二三四五六七八九十.\s（）\(\)-]+"
        r"|"
        r"[a-z][\)）]|\([a-z][\)）]"
        r")"
        r"[.。:：\s]*"
    )

    last_text = ""
    cleaned_text = text.strip()

    while last_text != cleaned_text:
        last_text = cleaned_text
        cleaned_text = re.sub(pattern, "", cleaned_text, flags=re.IGNORECASE).strip()

    return cleaned_text


def remove_latex_formulas(text):
    """去除文本中的 LaTeX 公式"""
    if not text:
        return ""

    text = re.sub(r'\$\$(.*?)\$\$', '', text, flags=re.DOTALL)
    text = re.sub(r'\\\[(.*?)\\\]', '', text, flags=re.DOTALL)
    text = re.sub(r'\$(?!\$)([^\$]+?)\$(?!\$)', '', text)
    text = re.sub(r'\s+', ' ', text).strip()

    return text


def clean_html_block(context_lines):
    html_pattern = r"<details.*?>\s*<summary><code>(.*?)</code></summary>.*?</details>"
    temp_text = "\n".join(context_lines)
    cleaned_text = re.sub(html_pattern, r"\1", temp_text, flags=re.DOTALL)
    return cleaned_text.strip()


def extract_table_logic(path):
    if not os.path.exists(path):
        print(f"路径不存在: {path}")
        return []

    files = os.listdir(path)
    txt_map = defaultdict(list)
    jpg_files = []

    for f in files:
        if f.endswith('.txt'):
            prefix = "_".join(f.split('_')[:-4])
            txt_map[prefix].append(f)
        elif f.endswith('.jpg'):
            prefix = "_".join(f.split('_')[:-4])
            jpg_files.append({"prefix": prefix, "name": f})

    jpg_files.sort(key=lambda x: [int(c) if c.isdigit() else c for c in re.split(r'(\d+)', x['name'])])

    final_data_list = []
    last_full_title = "未知表格标题"

    for item in jpg_files:
        prefix = item["prefix"]
        jpg_name = item["name"]

        current_txt_title = ""
        is_continued = False
        matched_txts = txt_map.get(prefix, [])
        matched_txts.sort()

        for txt_name in matched_txts:
            txt_path = os.path.join(path, txt_name)
            try:
                with open(txt_path, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if content.startswith('表'):
                        if "续" in content:
                            is_continued = True
                        else:
                            current_txt_title = content
                        break
            except Exception:
                continue

        if is_continued:
            final_title = last_full_title
        elif current_txt_title:
            final_title = clean_description(current_txt_title)
            final_title = remove_latex_formulas(final_title)
            last_full_title = final_title
        else:
            final_title = last_full_title

        table_dict = {
            "figure_name": jpg_name,
            "relative_path": f"tables/{jpg_name}",  # 修复：原代码此处缺少逗号
            "category": "tables",
            "description": final_title
        }
        final_data_list.append(table_dict)

    return final_data_list


# ── 主处理逻辑 ────────────────────────────────────────────────────────────────

def process_markdown_files(files):
    for file_path in files:
        file_path = Path(file_path)
        if not file_path.exists():
            continue

        print(f"\n>>> 正在处理文档: {file_path.name}")

        parent_dir = file_path.parent
        md_content = file_path.read_text(encoding='utf-8')

        md_metadata = {
            "source_file": file_path.parent,
            "processed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "images": []
        }

        figures_dir = parent_dir / "figures"
        txt_map = {}
        if figures_dir.exists():
            for t in figures_dir.glob("*.txt"):
                prefix = t.name.split("whxy")[0]
                txt_map[prefix] = t

        print(f"  正在扫描目录: {figures_dir}...")

        for img_file in figures_dir.glob("*.jpg"):
            if is_barcode_or_qr(img_file) or is_blank(img_file):
                continue

            prefix = img_file.name.split("whxy")[0]

            img_entry = {
                "figure_name": str(img_file.name),
                "relative_path": f"figures/{img_file.name}",
                "category": "figures",
                "description": "",
                "description_source": "",
                "status": ""
            }

            # 策略 A: 从 txt_map 匹配描述
            found_valid_txt = False
            if prefix in txt_map:
                try:
                    raw_desc = txt_map[prefix].read_text(encoding='utf-8').strip()
                    desc = clean_description(raw_desc)
                    desc = remove_latex_formulas(desc)

                    if len(desc) >= 3:
                        img_entry.update({
                            "description": desc,
                            "description_source": "txt_file",
                            "status": "success"
                        })
                        found_valid_txt = True
                    else:
                        print(f"    [跳过] {img_file.name} 的文本描述太短 ('{desc}')，将尝试 LLM 生成")
                except Exception as e:
                    img_entry["status"] = f"error_reading_txt: {str(e)}"

            # 策略 B: 从 MD 提取上下文并调用 LLM
            if not found_valid_txt:
                imgfile_name = str(img_file.name)
                search_pattern = rf"!\[.*?\]\([^)]*figures/{re.escape(imgfile_name)}\)"
                match = re.search(search_pattern, md_content)

                if match:
                    pos = match.start()
                    lines = md_content.splitlines()
                    current_line_idx = md_content[:pos].count('\n')

                    above_context = lines[max(0, current_line_idx - 3): current_line_idx]
                    below_context = lines[current_line_idx + 1: min(len(lines), current_line_idx + 4)]
                    above_context = clean_html_block(above_context)
                    below_context = clean_html_block(below_context)

                    generated_desc = call_multimodal_llm(img_file, above_context, below_context)

                    img_entry.update({
                        "description": generated_desc,
                        "description_source": "llm_generated",
                        "context_snapshot": {"above_context": above_context, "below_context": below_context},
                        "status": "generated"
                    })
                    print(f"    [LLM] 已参考上下文为 {img_file.name} 生成描述")
                else:
                    img_entry["status"] = "orphan_file_not_in_md"
                    print(f"    [注意] {img_file.name} 在 MD 中未发现引用")

            md_metadata["images"].append(img_entry)

        tables_path = parent_dir / "tables"
        tables_metadata = extract_table_logic(tables_path)
        md_metadata["tables"] = tables_metadata

        json_out = str(parent_dir / f"{file_path.stem}_metadata.json")
        with open(json_out, 'w', encoding='utf-8') as f:
            json.dump(md_metadata, f, ensure_ascii=False, indent=2, default=str)
        print(f">>> 处理完成，元数据已写入: {json_out}")


# ── 入口 ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    process_markdown_files(files)
