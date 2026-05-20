figma.showUI(__html__, { width: 360, height: 300 });

figma.ui.onmessage = async (msg) => {
  if (msg.type !== 'update-nodes') return;

  const { reportData, nodeMap } = msg;

  // Load all fonts used by target nodes before touching characters
  const fontSet = new Set();
  for (const entry of Object.values(nodeMap)) {
    if (entry.source === 'semrush' || entry.source === 'google_ads') continue;
    const nodeId = entry.node_id;
    const node = figma.getNodeById(nodeId);
    if (!node || node.type !== 'TEXT') continue;
    if (node.characters.length > 0) {
      try {
        node.getRangeAllFontNames(0, node.characters.length)
          .forEach(f => fontSet.add(JSON.stringify(f)));
      } catch (e) {
        if (node.fontName !== figma.mixed) fontSet.add(JSON.stringify(node.fontName));
      }
    } else if (node.fontName !== figma.mixed) {
      fontSet.add(JSON.stringify(node.fontName));
    }
  }
  for (const f of fontSet) {
    await figma.loadFontAsync(JSON.parse(f));
  }

  // Push values to text nodes
  let updated = 0, skipped = 0;
  const errors = [];

  for (const [field, entry] of Object.entries(nodeMap)) {
    if (entry.source === 'semrush' || entry.source === 'google_ads') {
      skipped++;
      continue;
    }
    const value = reportData[field];
    if (value === undefined) { skipped++; continue; }

    const node = figma.getNodeById(entry.node_id);
    if (!node || node.type !== 'TEXT') {
      errors.push(field);
      continue;
    }
    try {
      node.characters = String(value);
      updated++;
    } catch (e) {
      errors.push(field + ': ' + e.message);
    }
  }

  figma.ui.postMessage({ type: 'done', updated, skipped, errors });
};
