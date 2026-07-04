import sys
from pathlib import Path
import json

# Ensure project root is on sys.path so `src` imports resolve when running as a script
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.utils.config import get_config
from src.models.state import NarrativeState


def main():
    cfg = get_config()
    state_path = Path(cfg.memory_dir) / 'narrative_state.json'
    if not state_path.exists():
        print('No narrative_state.json found; run pipeline first')
        return

    with open(state_path, 'r', encoding='utf-8') as f:
        state_dict = json.load(f)
    state = NarrativeState.from_dict(state_dict)

    # Build a simple JSON graph inline (avoid importing engine module directly)
    nodes = []
    edges = []
    for cid, cdata in state.characters.items():
        name = None
        if hasattr(cdata, 'current') and cdata.current is not None:
            name = getattr(cdata.current, 'value', None)
        elif isinstance(cdata, dict):
            name = (cdata.get('current') or {}).get('value')
        nodes.append({'id': cid, 'label': name or cid, 'type': 'character'})

    for rid, rdata in state.relationships.items():
        parts = rid.split('::')
        if len(parts) != 2:
            continue
        a, b = parts
        # Try dict-like access first, fall back to object attribute access
        label = 'UNKNOWN'
        try:
            label = (rdata.get('relationship_label') or {}).get('current', {}).get('value', 'UNKNOWN')
        except Exception:
            try:
                label = getattr(rdata.current, 'value', 'UNKNOWN') if getattr(rdata, 'current', None) else 'UNKNOWN'
            except Exception:
                label = 'UNKNOWN'
        edges.append({'id': rid, 'source': a, 'target': b, 'label': label})

    graph = {'nodes': nodes, 'edges': edges}
    out = Path(cfg.memory_dir) / 'narrative_graph.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(graph, f, indent=2, ensure_ascii=False)
    print('Graph saved to', out)


if __name__ == '__main__':
    main()
