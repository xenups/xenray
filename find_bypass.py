import os

path = r"c:\Users\Xenups\Desktop\gorzer\pub\xenray\GorzRay-main\gorzray.py"

with open(path, 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "bypass" in line:
        print(f"Line {i+1}: {line.strip()}")
