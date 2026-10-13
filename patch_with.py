with open("src/clave/training/sample.py", "r") as f:
    content = f.read()

import re

old_block = """    with zipfile.ZipFile(path, "r") as z:
        with z.open("frames.npy") as f:"""

new_block = """    with zipfile.ZipFile(path, "r") as z, z.open("frames.npy") as f:"""

if old_block in content:
    content = content.replace(old_block, new_block)
else:
    print("Old block not found!")

with open("src/clave/training/sample.py", "w") as f:
    f.write(content)
