import urllib.request
import json

token = 'figd_aPM5MvdKLwZS40rEPTyk2atlD_Nb8BnuwFa7YCZq'
file_key = '0ZRlbRlTVTpKpzFdwMiy0P'

req = urllib.request.Request(
    f'https://api.figma.com/v1/files/{file_key}',
    headers={'X-Figma-Token': token}
)
with urllib.request.urlopen(req) as res:
    data = json.loads(res.read())

text_nodes = []

def find_text(node):
    if node.get('type') == 'TEXT':
        text_nodes.append({
            'id': node.get('id'),
            'name': node.get('name'),
            'characters': node.get('characters', '')
        })
    for child in node.get('children', []):
        find_text(child)

find_text(data['document'])

import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('C:\\Users\\Lenovo\\Desktop\\Report monthly dy\\nodes_output.txt', 'w', encoding='utf-8') as f:
    for n in text_nodes:
        chars = n['characters'].replace(' ', ' ').replace('\n', ' ').strip()
        f.write(f"{n['id']} | {n['name']} | {repr(chars)}\n")
    f.write(f'\nTotal text nodes: {len(text_nodes)}\n')

print(f"Done! Total text nodes found: {len(text_nodes)}")
print("Output saved to nodes_output.txt")
