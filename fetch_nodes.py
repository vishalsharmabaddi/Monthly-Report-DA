"""
Fetches all Figma text nodes and auto-maps them to report_data fields.

Flow:
  1. Fetch complete file tree from Figma REST API
  2. Walk tree → collect every TEXT node with its parent-frame path
  3. If report_data exists → content-match nodes to fields
       Unique match  → written to node_map automatically
       Ambiguous/miss → written to nodes_output.txt for Claude to review
  4. Print summary: "Auto-mapped: 45/68. Needs review: 3"

Usage:
  py fetch_nodes.py                — shows client selector menu
  py fetch_nodes.py makesure       — runs for a specific client

Run this ONLY when the Figma template structure changes.
For new months on the same template, run_report.py skips this step.
"""
import json
import os
import sys
import urllib.request
from client_utils import resolve_client, get_paths, load_config, load_node_map


# ── Figma fetch ───────────────────────────────────────────────────────────────

def fetch_document(file_key: str, token: str) -> dict:
    import time
    req = urllib.request.Request(
        f'https://api.figma.com/v1/files/{file_key}',
        headers={'X-Figma-Token': token}
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req) as res:
                return json.loads(res.read())['document']
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = 60 * (attempt + 1)
                print(f"  Rate limited by Figma. Waiting {wait}s before retry ({attempt+1}/3)...")
                time.sleep(wait)
            else:
                raise
    raise RuntimeError("Figma API rate limit exceeded after 3 retries. Wait a few minutes and try again.")


def walk_nodes(node: dict, parent_path: list = None, result: list = None) -> list:
    """Recursively collect all TEXT nodes with their parent-frame path."""
    if parent_path is None:
        parent_path = []
    if result is None:
        result = []

    node_type = node.get('type', '')

    if node_type == 'TEXT':
        bbox = node.get('absoluteBoundingBox', {})
        result.append({
            'id':          node.get('id'),
            'name':        node.get('name', ''),
            'characters':  node.get('characters', ''),
            'parent_path': parent_path[:],
            'x':           round(bbox.get('x', 0)),
            'y':           round(bbox.get('y', 0)),
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

# Section headers that mark the start of manually-managed sections
_MANUAL_SECTION_MARKERS = {'Google Ads Performance', 'Google Ads'}


def _keywords(field_name: str) -> list[str]:
    """Extract meaningful keywords from a field name."""
    return [p for p in field_name.lower().split('_') if p not in _SKIP_PARTS]


def _path_score(field_name: str, parent_path: list[str]) -> int:
    """How many field keywords appear in the parent-frame path string."""
    path_str = ' '.join(parent_path).lower()
    return sum(1 for kw in _keywords(field_name) if kw in path_str)


def _detect_ga4_boundary(all_nodes: list[dict]) -> float:
    """
    Find the y-coordinate where manual sections (Google Ads etc.) begin.
    Any node at or below this y is excluded from GA4 auto-matching.
    Returns inf if no marker found (no exclusion zone applied).
    """
    boundary = float('inf')
    for node in all_nodes:
        for marker in _MANUAL_SECTION_MARKERS:
            if marker in node.get('characters', ''):
                boundary = min(boundary, node['y'])
    return boundary


def _is_risky_value(value: str) -> bool:
    """
    True for short numeric values or dash — these commonly appear in multiple
    sections and risk false matches when there is no path-score confirmation.
    Safe to auto-match only when path_score > 0 or value is a longer string.
    """
    v = value.strip()
    if not v or v == '-':
        return True
    digits = v.replace(',', '')
    return digits.isdigit() and len(digits) <= 3


def auto_match(
    all_nodes: list[dict],
    report_data: dict,
    existing_map: dict,
) -> tuple[dict, list[str]]:
    """
    Returns (new_node_map, unmatched_fields).

    Strategy:
      - source=semrush/google_ads entries are always kept from existing_map.
      - Nodes in the Google Ads section (below detected y-boundary) are excluded.
      - For each report_data field: find Figma nodes whose characters == value.
        * 1 candidate + safe value  → direct map
        * 1 candidate + risky value → need path_score > 0, else unmatched
        * N candidates → pick best by parent-path keyword score (must be uniquely best)
        * 0 candidates or tie → add to unmatched
    """
    # Layer 1: detect where manual sections start and exclude those nodes
    ga4_boundary = _detect_ga4_boundary(all_nodes)

    # Build value → nodes lookup (GA4 zone only — exclude manual sections)
    by_value: dict[str, list[dict]] = {}
    for node in all_nodes:
        if node.get('y', 0) >= ga4_boundary:
            continue  # skip Google Ads / manual section nodes
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
            score = _path_score(field, node['parent_path'])
            # Layer 2: risky short values need path confirmation to avoid
            # coincidental matches in SEMrush or other non-GA4 sections
            if score > 0 or not _is_risky_value(value):
                entry = _build_entry(field, node['id'], existing_map)
                new_map[field] = entry
            else:
                unmatched.append(field)

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
                    report_data: dict, output_path: str = 'nodes_output.txt'):
    """Write nodes_output file — full dump + highlighted unmatched section."""
    sys.stdout.reconfigure(encoding='utf-8')

    with open(output_path, 'w', encoding='utf-8') as f:
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
            f.write(f"{n['id']} | x={n.get('x',0)} y={n.get('y',0)} | {repr(chars)} | {path}\n")

        f.write(f"\nTotal: {len(all_nodes)}\n")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    client = resolve_client(sys.argv[1] if len(sys.argv) > 1 else None)
    paths  = get_paths(client)
    cfg    = load_config(client)

    token    = cfg['figma_token']
    file_key = cfg['figma_file_key']

    print(f"Client : {cfg['client_name']}")
    print(f"Fetching Figma file {file_key}...")
    document  = fetch_document(file_key, token)
    all_nodes = walk_nodes(document)
    print(f"Found {len(all_nodes)} text nodes.")

    # Can't auto-match without report_data
    if not os.path.exists(paths['report_data']):
        print()
        print("report_data not found — cannot auto-match node content.")
        print(f"Run:  py run_report.py {client}  (or fetch_ga4.py directly)")
        print()
        write_nodes_txt(all_nodes, [], {}, paths['nodes_output'])
        print(f"All {len(all_nodes)} nodes saved to {paths['nodes_output']}")
        return

    with open(paths['report_data']) as f:
        report_data = json.load(f)

    existing_map = load_node_map(client)

    print("Auto-matching by content...")
    new_map, unmatched = auto_match(all_nodes, report_data, existing_map)

    # Save updated node_map to client file
    with open(paths['node_map'], 'w') as f:
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
        for field in unmatched:
            print(f"    - {field}")
    print()

    write_nodes_txt(all_nodes, unmatched, report_data, paths['nodes_output'])

    if unmatched:
        print(f"{paths['nodes_output']} updated with unmatched fields at the top.")
        print()
        nodes_path = paths['nodes_output']
        node_map_path = paths['node_map']
        report_path = paths['report_data']
        print("  >> Copy-paste this prompt to Claude:")
        print()
        print(f'  Read these 3 files: "{nodes_path}", "{node_map_path}", "{report_path}".')
        print(f'  The top section of nodes_output.txt lists UNMATCHED FIELDS with their expected values.')
        print(f'  The bottom section lists ALL TEXT NODES in format: "nodeId | x=N y=N | \'content\' | framePath"')
        print(f'  For each unmatched field: find the node whose content matches the field\'s expected value.')
        print(f'  If no exact match, use the frame path context (section name, position) to identify the correct node.')
        print(f'  Add each resolved field to "{node_map_path}" in format: {{"field_name": {{"node_id": "12:34"}}}}')
        print(f'  Do NOT remove or change any existing entries in node_map.json.')
        print(f'  Reply with a summary of how many fields you mapped and which ones could not be resolved.')
        print()
        print(f"  Then run:  py run_report.py {client}")
    else:
        print(f"All fields matched! {paths['node_map']} is ready.")
        print(f"Run: py run_report.py {client}")


if __name__ == '__main__':
    main()
