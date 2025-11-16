#!/usr/bin/env python3
"""Fix all indentation issues in app.py"""

with open('app.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

result = []
i = 0
in_function = False
base_indent = 0

while i < len(lines):
    line = lines[i]
    stripped = line.strip()
    leading = len(line) - len(line.lstrip())
    
    # Track if we're in register_routes
    if 'def register_routes(app):' in line:
        base_indent = 4
        result.append(line)
        i += 1
        continue
    
    if base_indent == 4 and stripped.startswith('def create_app'):
        base_indent = 0
        result.append(line)
        i += 1
        continue
    
    if base_indent == 0:
        result.append(line)
        i += 1
        continue
    
    # We're inside register_routes (base_indent == 4)
    # Check if this is a function definition
    if stripped.startswith('def ') and not stripped.startswith('def register_routes'):
        in_function = True
        if leading != 4:
            result.append('    ' + line.lstrip())
        else:
            result.append(line)
        i += 1
        continue
    
    # Check if this is a decorator
    if stripped.startswith('@'):
        in_function = False
        if leading != 4:
            result.append('    ' + line.lstrip())
        else:
            result.append(line)
        i += 1
        continue
    
    # If we're inside a function
    if in_function:
        # Check for control structures
        if stripped.startswith('if ') or stripped.startswith('elif ') or stripped.startswith('else:') or stripped.startswith('try:') or stripped.startswith('except') or stripped.startswith('finally:'):
            # Control structure - should be at function body level (8 spaces)
            if leading < 8:
                result.append('        ' + line.lstrip())
            else:
                result.append(line)
            i += 1
            continue
        
        # Check if this line should be indented more (it's after an if/else/try/except)
        # Look back to see if previous non-empty line was a control structure
        j = i - 1
        prev_control = False
        prev_indent = 0
        while j >= 0:
            prev_line = lines[j]
            prev_stripped = prev_line.strip()
            if prev_stripped:
                prev_indent = len(prev_line) - len(prev_line.lstrip())
                if prev_stripped.endswith(':') and (prev_stripped.startswith('if ') or prev_stripped.startswith('elif ') or prev_stripped.startswith('else') or prev_stripped.startswith('try') or prev_stripped.startswith('except') or prev_stripped.startswith('finally')):
                    prev_control = True
                break
            j -= 1
        
        # If previous line was a control structure, this line should be indented more
        if prev_control and leading == prev_indent:
            # This line should be indented 4 more spaces
            result.append(' ' * (prev_indent + 4) + line.lstrip())
        elif leading < 8 and stripped and not stripped.startswith('#'):
            # Line with content that's not properly indented
            result.append('        ' + line.lstrip())
        else:
            result.append(line)
    else:
        # Not in function, but in register_routes - should have 4 spaces
        if leading < 4 and stripped:
            result.append('    ' + line.lstrip())
        else:
            result.append(line)
    
    i += 1

with open('app.py', 'w', encoding='utf-8') as f:
    f.writelines(result)

print("Fixed all indentation issues")

