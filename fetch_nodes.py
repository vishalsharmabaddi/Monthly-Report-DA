"""
Fetches all Figma text nodes and auto-maps them to report_data fields.

Flow:
  1. Fetch complete file tree from Figma REST API
  2. Walk tree → collect every TEXT node with its parent-frame path
  3. If report_data.json exists → content-match nodes to fields
       Unique match  → written to node_map.json automatically
       Ambiguous/miss → written to nodes_output.txt for Claude to review
  4. Print summary: "Auto-mapped: 45/68. Needs review: 3"

Run this ONLY when the Figma template structure changes.
For new months / new clients on the same template, run_report.py skips this step.
"""
import json
import os
import sys
import urllib.request


# ── Figma fetch ───────────────────────────────────────────────────────────────

def fetch_document(file_key: str, token: str) -> dict:
    req = urllib.request.Request(
        f'https://api.figma.com/v1/files/{file_key}',
        headers={'X-Figma-Token': token}
    )
    with urllib.request.urlopen(req) as res:
        return json.loads(res.read())['document']


def walk_nodes(node: dict, parent_path: list = None, result: list = None) -> list:
    """Recursively collect all TEXT nodes with their parent-frame path."""
    if parent_path is None:
        parent_path = []
    if result is None:
        result = []

    node_type = node.get('type', '')

    if node_type == 'TEXT':
        result.append({
            'id':          node.get('id'),
            'name':        node.get('name', ''),
            'characters':  node.get('characters', ''),
            'parent_path': parent_path[:],
        })
        return result

    # Frames / groups extend the path for their children
    if node_type in ('FRAME', 'GROUP', 'SECTION', 'COMPONENT', 'INSTANCE', 'COMPONENT_SET'):
        child_path = parent_path + [node.get('name', '')]
    else:
        child_path = parent_path

    for child in node.get('children', []):
        walk_nodes(child, child_path, result)

    return result


# ── Matching logic ─────────────────────────────────────────────────────────────

# Words that don't help disambiguate — strip these when building keyword set
_SKIP_PARTS = {'ua', 'ga4', 'conv', 'heading', 'block', 'report', 'rate'}


def _keywords(field_name: str) -> list[str]:
    """Extract meaningful keywords from a field name."""
    return [p for p in field_name.lower().split('_') if p not in _SKIP_PARTS]


def _path_score(field_name: str, parent_path: list[str]) -> int:
    """How many field keywords appear in the parent-frame path string."""
    path_str = ' '.join(parent_path).lower()
    return sum(1 for kw in _keywords(field_name) if kw in path_str)


def auto_match(
    all_nodes: list[dict],
    report_data: dict,
    existing_map: dict,
) -> tuple[dict, list[str]]:
    """
    Returns (new_node_map, unmatched_fields).

    Strategy:
      - source=semrush/google_ads entries are always kept from existing_map.
      - For each report_data field: find Figma nodes whose characters == value.
        * 1 candidate  → direct map
        * N candidates → pick best by parent-path keyword score (must be uniquely best)
        * 0 candidates or tie → add to unmatched
    """
    # Build value → nodes lookup
    by_value: dict[str, list[dict]] = {}
    for node in all_nodes:
        ch = node['characters']
        by_value.setdefault(ch, []).append(node)

    new_map: dict = {}
    unmatched: list[str] = []

    # 1. Preserve manual-source fields unchanged
    for field, entry in existing_map.items():
        if entry.get('source') in ('semrush', 'google_ads'):
            new_map[field] = entry

    # 2. Match each report_data field
    for field, value in report_data.items():
        if field in new_map:
            continue  # already handled (manual source)
        if not value:
            unmatched.append(field)
            continue

        candidates = by_value.get(value, [])

        if len(candidates) == 0:
            unmatched.append(field)

        elif len(candidates) == 1:
            node = candidates[0]
            entry = _build_entry(field, node['id'], existing_map)
            new_map[field] = entry

        else:
            # Multiple nodes share the same text — use parent-path context
            scored = sorted(
                candidates,
                key=lambda n: _path_score(field, n['parent_path']),
                reverse=True,
            )
            best_score  = _path_score(field, scored[0]['parent_path'])
            second_score = _path_score(field, scored[1]['parent_path'])

            if best_score > 0 and best_score > second_score:
                entry = _build_entry(field, scored[0]['id'], existing_map)
                new_map[field] = entry
            else:
                unmatched.append(field)

    return new_map, unmatched


def _build_entry(field: str, node_id: str, existing_map: dict) -> dict:
    """Build a node_map entry, preserving type/template metadata if we have it."""
    existing = existing_map.get(field, {})
    entry = dict(existing)       # copy all metadata (type, template, source…)
    entry['node_id'] = node_id   # update just the ID
    if 'type' not in entry:
        entry['type'] = 'simple'
    return entry


# ── Output helpers ─────────────────────────────────────────────────────────────

def write_nodes_txt(all_nodes: list[dict], unmatched_fields: list[str],
                    report_data: dict):
    """Write nodes_output.txt — full dump + highlighted unmatched section."""
    sys.stdout.reconfigure(encoding='utf-8')

    with open('nodes_output.txt', 'w', encoding='utf-8') as f:
        # Section 1: fields that need manual mapping
        if unmatched_fields:
            f.write("=" * 60 + "\n")
            f.write("UNMATCHED FIELDS — needs manual mapping\n")
            f.write("=" * 60 + "\n")
            for field in unmatched_fields:
                expected = report_data.get(field, '<not in report_data>')
                f.write(f"  {field}  (value: {repr(expected)})\n")
            f.write("\n")

        # Section 2: all text nodes with path context
        f.write("=" * 60 + "\n")
        f.write(f"ALL TEXT NODES ({len(all_nodes)} total)\n")
        f.write("=" * 60 + "\n")
        for n in all_nodes:
            chars = n['characters'].replace('\n', ' ').strip()
            path  = ' > '.join(n['parent_path']) if n['parent_path'] else '(root)'
            f.write(f"{n['id']} | {repr(chars)} | {path}\n")

        f.write(f"\nTotal: {len(all_nodes)}\n")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    # Config
    with open('config.json') as f:
        cfg = json.load(f)
    token    = cfg['figma_token']
    file_key = cfg['figma_file_key']

    print(f"Fetching Figma file {file_key}...")
    document  = fetch_document(file_key, token)
    all_nodes = walk_nodes(document)
    print(f"Found {len(all_nodes)} text nodes.")

    # Can't auto-match without report_data
    if not os.path.exists('report_data.json'):
        print()
        print("report_data.json not found — cannot auto-match node content.")
        print("Run:  py fetch_ga4.py")
        print("Then: py fetch_nodes.py")
        print()
        write_nodes_txt(all_nodes, [], {})
        print(f"All {len(all_nodes)} nodes saved to nodes_output.txt")
        return

    with open('report_data.json') as f:
        report_data = json.load(f)

    existing_map = {}
    if os.path.exists('node_map.json'):
        with open('node_map.json') as f:
            existing_map = json.load(f)

    print("Auto-matching by content...")
    new_map, unmatched = auto_match(all_nodes, report_data, existing_map)

    # Save updated node_map
    with open('node_map.json', 'w') as f:
        json.dump(new_map, f, indent=2)

    # Count manual-source entries (semrush etc.) — they're not "auto-matched"
    manual_count = sum(
        1 for e in new_map.values()
        if e.get('source') in ('semrush', 'google_ads')
    )
    auto_count = len(new_map) - manual_count
    total_ga4  = len(report_data)

    print()
    print(f"  Auto-matched : {auto_count} / {total_ga4} fields")
    if manual_count:
        print(f"  Manual fields: {manual_count} (semrush / google_ads — kept as-is)")
    if unmatched:
        print(f"  Needs review : {len(unmatched)} fields")
        for f in unmatched:
            print(f"    - {f}")
    print()

    write_nodes_txt(all_nodes, unmatched, report_data)

    if unmatched:
        print("nodes_output.txt updated with unmatched fields at the top.")
        print()
        print("  >> Tell Claude:")
        print('     "Map these unmatched fields using nodes_output.txt"')
        print("     Claude will update node_map.json for the remaining fields.")
        print()
        print("  Then run:  py run_report.py")
    else:
        print("All fields matched! node_map.json is ready.")
        print("Run: py run_report.py")


if __name__ == '__main__':
    main()
