with open(r'src\utils\link_parser.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Remove lines 585-623 (indices 584-623 in 0-indexed)
new_lines = lines[:584] + lines[623:]

with open(r'src\utils\link_parser.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print("Removed unreachable code from link_parser.py")
