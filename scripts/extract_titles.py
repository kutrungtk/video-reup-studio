"""
Extract Titles — Lấy tiêu đề video từ folder hiện tại.
Bỏ ngày tháng (YYYY-MM-DD_) và _edited, giữ hashtags.

Cách dùng: Copy file này vào folder chứa video, double-click chạy.
Output: titles.txt trong cùng folder.
"""

import os
import re

VIDEO_EXTS = {'.mp4', '.mkv', '.avi', '.webm', '.mov', '.flv'}


def extract_title(filename: str) -> str:
    name, ext = os.path.splitext(filename)
    if ext.lower() not in VIDEO_EXTS:
        return ""
    # Bỏ date prefix: 2026-05-26_
    name = re.sub(r'^\d{4}-\d{2}-\d{2}_', '', name)
    # Bỏ _edited suffix
    name = re.sub(r'_edited$', '', name)
    return name.strip()


def main():
    folder = os.path.dirname(os.path.abspath(__file__))
    files = sorted(os.listdir(folder))
    titles = []

    for f in files:
        title = extract_title(f)
        if title:
            titles.append(title)

    if not titles:
        print("⚠ Không tìm thấy video nào trong folder này")
        input("Enter để đóng...")
        return

    output = os.path.join(folder, "titles.txt")
    with open(output, 'w', encoding='utf-8') as f:
        for t in titles:
            f.write(t + '\n')

    print(f"✅ Đã lấy {len(titles)} tiêu đề → titles.txt")
    for i, t in enumerate(titles, 1):
        print(f"  {i}. {t}")
    input("\nEnter để đóng...")


if __name__ == "__main__":
    main()
