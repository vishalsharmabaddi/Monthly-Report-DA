"""
Shared helper: client selection and per-client file path resolution.

Each client lives in its own subfolder:
  clients/{name}/config.json        — settings (ga4_property_id, figma_token, etc.)
  clients/{name}/node_map.json      — Figma node ID mappings
  clients/{name}/token.json         — Google OAuth token (auto-saved)
  clients/{name}/oauth_client.json  — Google OAuth2 client key
  clients/{name}/report_data.json   — intermediate GA4 output (debug)
  clients/{name}/nodes_output.txt   — Figma node dump for manual mapping
"""
import json
import os
import sys


def list_clients() -> list[str]:
    """Return sorted client names — one subfolder per client inside clients/."""
    if not os.path.exists('clients'):
        return []
    names = []
    for entry in os.scandir('clients'):
        if entry.is_dir() and not entry.name.startswith('_'):
            names.append(entry.name)
    return sorted(names)


def resolve_client(arg: str | None = None) -> str:
    """
    Return the client name to use.
    - If arg given and valid, return it.
    - If only one client exists, return it automatically.
    - Otherwise show a numbered menu.
    """
    clients = list_clients()
    if not clients:
        print("ERROR: No clients found in clients/ folder.")
        print("Create clients/{name}.json with ga4_property_id, figma_token, etc.")
        sys.exit(1)

    if arg:
        if arg in clients:
            return arg
        print(f"ERROR: Client '{arg}' not found.")
        print(f"Available: {', '.join(clients)}")
        sys.exit(1)

    if len(clients) == 1:
        return clients[0]

    print("Select client:")
    for i, name in enumerate(clients, 1):
        print(f"  {i}. {name}")
    choice = input("Enter number: ").strip()
    try:
        return clients[int(choice) - 1]
    except (ValueError, IndexError):
        print("Invalid choice.")
        sys.exit(1)


def get_paths(client: str) -> dict:
    """Return all file paths for the given client."""
    base = os.path.join('clients', client)
    return {
        'config':        os.path.join(base, 'config.json'),
        'node_map':      os.path.join(base, 'node_map.json'),
        'token':         os.path.join(base, 'token.json'),
        'oauth_client':  os.path.join(base, 'oauth_client.json'),
        'report_data':   os.path.join(base, 'report_data.json'),
        'nodes_output':  os.path.join(base, 'nodes_output.txt'),
    }


def load_config(client: str) -> dict:
    paths = get_paths(client)
    with open(paths['config']) as f:
        return json.load(f)


def load_node_map(client: str) -> dict:
    paths = get_paths(client)
    if not os.path.exists(paths['node_map']):
        return {}
    with open(paths['node_map']) as f:
        return json.load(f)
