import base64, os

b64 = """UEsDBBQAAAAIAAAAPwBhXUk6TwEAAI8EAAATAAAAW0NvbnRlbnRfVHlwZXNdLnhtbK2Uy27CMBBF"""

# Read the base64 file and decode back to binary
script_dir = os.path.dirname(os.path.abspath(__file__))
b64_path = os.path.join(script_dir, 'expenses_b64.txt')
db_path = os.path.join(script_dir, 'expenses.db')

with open(b64_path, 'r') as f:
    data = base64.b64decode(f.read())
with open(db_path, 'wb') as f:
    f.write(data)
print(f'Written {len(data)} bytes to {db_path}')
os.remove(b64_path)
