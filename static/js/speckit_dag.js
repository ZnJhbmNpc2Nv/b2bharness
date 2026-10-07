/**
 * Corporate Spec-Kit Provenance Engine & Lineage DAG Visualizer ("Откуда что родилось")
 * Pure Vanilla JavaScript & SVG - Zero external dependencies.
 */
class SpecKitDAG {
  constructor(options = {}) {
    this.container = null;
    this.api = null;
    this.specId = null;
    this.graphData = { nodes: [], edges: [] };
    this.layoutNodes = new Map(); // id -> { x, y, width, height, node }
    this.selectedNodeId = null;
    this.onSelectNode = options.onSelectNode || null;

    this.colTitles = [
      'Col 1: Intent & Constitution',
      'Col 2: Requirements (REQ-xxx)',
      'Col 3: Clarifications (CLAR-xxx)',
      'Col 4: Tasks (TASK-xxx)',
      'Col 5: Tests & Code Artifacts'
    ];

    this.typeIcons = {
      INTENT: '🎯',
      CONSTITUTION: '📜',
      REQUIREMENT: '📋',
      CLARIFICATION: '❓',
      TASK: '⚙️',
      TEST: '🧪',
      CODE: '📦'
    };

    this.typeColors = {
      INTENT: '#8b5cf6',
      CONSTITUTION: '#f59e0b',
      REQUIREMENT: '#06b6d4',
      CLARIFICATION: '#f43f5e',
      TASK: '#3b82f6',
      TEST: '#10b981',
      CODE: '#a855f7'
    };

    this.zoomScale = 1.0;
  }

  init(container, api, specId) {
    this.container = typeof container === 'string' ? document.querySelector(container) : container;
    this.api = api;
    this.specId = specId;
  }

  setSpecId(specId) {
    this.specId = specId;
    this.selectedNodeId = null;
  }

  async loadAndRender(specId = null) {
    if (specId) this.specId = specId;
    if (!this.container) return;

    this.container.innerHTML = `
      <div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--text-dim);gap:10px;">
        <span style="font-size:20px;animation:spin 1s linear infinite;">⚙️</span>
        <span>Calculating corporate provenance graph...</span>
      </div>
    `;

    try {
      this.graphData = await this.api.getLineage(this.specId);
      this.render();
    } catch (err) {
      this.container.innerHTML = `
        <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;color:#fda4af;gap:8px;">
          <span style="font-size:24px;">⚠️</span>
          <span>Failed to load lineage DAG: ${this._escapeHtml(err.message)}</span>
        </div>
      `;
    }
  }

  _getColumnIndex(node) {
    const type = (node.node_type || '').toUpperCase();
    if (type === 'INTENT' || type === 'CONSTITUTION') return 0;
    if (type === 'REQUIREMENT') return 1;
    if (type === 'CLARIFICATION') return 2;
    if (type === 'TASK') return 3;
    if (type === 'TEST' || type === 'CODE') return 4;
    return 1;
  }

  _escapeHtml(text) {
    if (text === null || text === undefined) return '';
    return String(text)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  render() {
    if (!this.container) return;
    this.container.innerHTML = '';

    const nodes = this.graphData.nodes || [];
    const edges = this.graphData.edges || [];

    if (nodes.length === 0) {
      this.container.innerHTML = `
        <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;color:var(--text-dim);gap:8px;">
          <span style="font-size:32px;">🕸️</span>
          <span>No lineage graph nodes found for specification "${this._escapeHtml(this.specId)}".</span>
        </div>
      `;
      return;
    }

    // 1. Arrange nodes by column
    const cols = [[], [], [], [], []];
    nodes.forEach(n => {
      const colIdx = this._getColumnIndex(n);
      cols[colIdx].push(n);
    });

    // Sort nodes in each column alphabetically or logically
    cols.forEach(col => {
      col.sort((a, b) => (a.entity_id || a.id).localeCompare(b.entity_id || b.id));
    });

    // 2. Compute Layout Positions
    const nodeW = 210;
    const nodeH = 68;
    const colGap = 85;
    const rowGap = 24;
    const padX = 40;
    const padY = 70;

    const maxRows = Math.max(...cols.map(c => c.length), 1);
    const canvasWidth = padX * 2 + 5 * nodeW + 4 * colGap;
    const canvasHeight = Math.max(padY * 2 + maxRows * (nodeH + rowGap), 560);

    this.layoutNodes.clear();

    cols.forEach((colList, colIdx) => {
      const colX = padX + colIdx * (nodeW + colGap);
      const totalColHeight = colList.length * nodeH + Math.max(0, colList.length - 1) * rowGap;
      const startY = padY + Math.max(0, (canvasHeight - padY * 2 - totalColHeight) / 2);

      colList.forEach((node, rowIdx) => {
        const y = startY + rowIdx * (nodeH + rowGap);
        this.layoutNodes.set(node.id, {
          x: colX,
          y: y,
          width: nodeW,
          height: nodeH,
          node: node
        });
      });
    });

    // 3. Create SVG element
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('class', 'dag-svg');
    svg.setAttribute('viewBox', `0 0 ${canvasWidth} ${canvasHeight}`);
    svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');
    svg.style.width = '100%';
    svg.style.height = '100%';
    svg.style.userSelect = 'none';

    // SVG Defs: Markers and filters
    const defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
    defs.innerHTML = `
      <!-- Arrowheads -->
      <marker id="arrow-default" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
        <path d="M 0 1 L 9 5 L 0 9 z" fill="#334155" />
      </marker>
      <marker id="arrow-ancestor" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
        <path d="M 0 1 L 9 5 L 0 9 z" fill="#38bdf8" />
      </marker>
      <marker id="arrow-descendant" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
        <path d="M 0 1 L 9 5 L 0 9 z" fill="#34d399" />
      </marker>

      <!-- Glow Filters -->
      <filter id="glow-cyan" x="-20%" y="-20%" width="140%" height="140%">
        <feGaussianBlur stdDeviation="3" result="blur" />
        <feComposite in="SourceGraphic" in2="blur" operator="over" />
      </filter>
      <filter id="glow-green" x="-20%" y="-20%" width="140%" height="140%">
        <feGaussianBlur stdDeviation="3" result="blur" />
        <feComposite in="SourceGraphic" in2="blur" operator="over" />
      </filter>
    `;
    svg.appendChild(defs);

    // 4. Draw Column Headers / Guide Rails
    const headerGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    headerGroup.setAttribute('class', 'dag-column-headers');
    for (let c = 0; c < 5; c++) {
      const colX = padX + c * (nodeW + colGap);
      
      // Column title
      const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      text.setAttribute('x', colX + nodeW / 2);
      text.setAttribute('y', 36);
      text.setAttribute('text-anchor', 'middle');
      text.setAttribute('fill', '#64748b');
      text.setAttribute('font-size', '11');
      text.setAttribute('font-weight', '700');
      text.setAttribute('letter-spacing', '0.04em');
      text.setAttribute('text-transform', 'uppercase');
      text.textContent = this.colTitles[c];
      headerGroup.appendChild(text);

      // Subtle guide line
      const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      line.setAttribute('x1', colX + nodeW / 2);
      line.setAttribute('y1', 48);
      line.setAttribute('x2', colX + nodeW / 2);
      line.setAttribute('y2', canvasHeight - 20);
      line.setAttribute('stroke', 'rgba(255, 255, 255, 0.03)');
      line.setAttribute('stroke-dasharray', '4, 4');
      headerGroup.appendChild(line);
    }
    svg.appendChild(headerGroup);

    // 5. Draw Edges Group
    const edgesGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    edgesGroup.setAttribute('class', 'dag-edges-layer');

    edges.forEach(edge => {
      const fromPos = this.layoutNodes.get(edge.from_node_id);
      const toPos = this.layoutNodes.get(edge.to_node_id);
      if (!fromPos || !toPos) return;

      const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      const edgeId = edge.id;
      path.setAttribute('id', `dag-edge-${edgeId}`);
      path.setAttribute('class', 'dag-edge');
      path.setAttribute('data-edge-id', edgeId);
      path.setAttribute('data-from', edge.from_node_id);
      path.setAttribute('data-to', edge.to_node_id);
      path.setAttribute('marker-end', 'url(#arrow-default)');

      // Cubic Bezier curve points
      const x1 = fromPos.x + fromPos.width;
      const y1 = fromPos.y + fromPos.height / 2;
      const x2 = toPos.x;
      const y2 = toPos.y + toPos.height / 2;

      let d;
      const dx = Math.abs(x2 - x1);
      if (x2 > x1) {
        const cx1 = x1 + Math.max(dx * 0.45, 30);
        const cy1 = y1;
        const cx2 = x2 - Math.max(dx * 0.45, 30);
        const cy2 = y2;
        d = `M ${x1} ${y1} C ${cx1} ${cy1}, ${cx2} ${cy2}, ${x2} ${y2}`;
      } else {
        // Fallback for same column or backwards edge
        const curveOffset = 40;
        d = `M ${x1} ${y1} C ${x1 + curveOffset} ${y1 - 30}, ${x2 - curveOffset} ${y2 - 30}, ${x2} ${y2}`;
      }

      path.setAttribute('d', d);

      // Tooltip title for relation
      const title = document.createElementNS('http://www.w3.org/2000/svg', 'title');
      title.textContent = `${edge.relation || 'LINK'}: ${edge.from_node_id} ➜ ${edge.to_node_id}`;
      path.appendChild(title);

      edgesGroup.appendChild(path);
    });
    svg.appendChild(edgesGroup);

    // 6. Draw Nodes Group
    const nodesGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    nodesGroup.setAttribute('class', 'dag-nodes-layer');

    this.layoutNodes.forEach((pos, nodeId) => {
      const node = pos.node;
      const type = (node.node_type || 'UNKNOWN').toUpperCase();
      const icon = this.typeIcons[type] || '📌';
      const accentColor = this.typeColors[type] || '#06b6d4';

      const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      g.setAttribute('id', `dag-node-${nodeId}`);
      g.setAttribute('class', 'dag-node');
      g.setAttribute('transform', `translate(${pos.x}, ${pos.y})`);
      g.setAttribute('data-node-id', nodeId);
      g.style.cursor = 'pointer';

      // Rect box
      const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
      rect.setAttribute('width', pos.width);
      rect.setAttribute('height', pos.height);
      rect.setAttribute('rx', '8');
      rect.setAttribute('ry', '8');
      rect.setAttribute('fill', '#111827');
      rect.setAttribute('stroke', '#1f293d');
      rect.setAttribute('stroke-width', '1.5');
      g.appendChild(rect);

      // Left Accent stripe
      const stripe = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
      stripe.setAttribute('x', '0');
      stripe.setAttribute('y', '0');
      stripe.setAttribute('width', '5');
      stripe.setAttribute('height', pos.height);
      stripe.setAttribute('rx', '3');
      stripe.setAttribute('fill', accentColor);
      g.appendChild(stripe);

      // Type Badge / Icon
      const iconText = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      iconText.setAttribute('x', '16');
      iconText.setAttribute('y', '26');
      iconText.setAttribute('font-size', '14');
      iconText.textContent = icon;
      g.appendChild(iconText);

      // Node Entity ID or Type Pill
      const typePill = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      typePill.setAttribute('x', '38');
      typePill.setAttribute('y', '25');
      typePill.setAttribute('fill', accentColor);
      typePill.setAttribute('font-size', '11');
      typePill.setAttribute('font-weight', '700');
      typePill.setAttribute('letter-spacing', '0.04em');
      typePill.setAttribute('font-family', 'ui-monospace, monospace');
      
      const entityLabel = (node.entity_id || node.id).toUpperCase();
      typePill.textContent = entityLabel.length > 18 ? entityLabel.slice(0, 16) + '..' : entityLabel;
      g.appendChild(typePill);

      // Label / Description text (truncated)
      const labelText = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      labelText.setAttribute('x', '16');
      labelText.setAttribute('y', '48');
      labelText.setAttribute('fill', '#e2e8f0');
      labelText.setAttribute('font-size', '12');
      labelText.setAttribute('font-weight', '500');

      let cleanLabel = (node.label || node.id);
      // Remove entity ID prefix if already shown in pill
      if (cleanLabel.startsWith(`${node.entity_id}: `)) {
        cleanLabel = cleanLabel.substring(`${node.entity_id}: `.length);
      }
      if (cleanLabel.length > 25) {
        cleanLabel = cleanLabel.slice(0, 23) + '...';
      }
      labelText.textContent = cleanLabel;
      g.appendChild(labelText);

      // Click event for interactive provenance inspection
      g.addEventListener('click', (e) => {
        e.stopPropagation();
        this.selectNode(nodeId);
      });

      // Hover tooltip
      const titleEl = document.createElementNS('http://www.w3.org/2000/svg', 'title');
      titleEl.textContent = `[${type}] ${node.label || node.id}\nClick to trace provenance ("Откуда что родилось")`;
      g.appendChild(titleEl);

      nodesGroup.appendChild(g);
    });
    svg.appendChild(nodesGroup);

    // Background click to clear selection
    svg.addEventListener('click', () => {
      this.resetSelection();
    });

    this.container.appendChild(svg);
  }

  async selectNode(nodeId) {
    if (!nodeId || !this.api) return;
    this.selectedNodeId = nodeId;

    // Reset visual highlights first
    this._clearHighlightStyles();

    // Mark clicked node as active
    const activeEl = document.getElementById(`dag-node-${nodeId}`);
    if (activeEl) {
      activeEl.classList.add('active');
    }

    try {
      // Call backend API trace
      const traceData = await this.api.traceNode(this.specId, nodeId);
      this.applyTraceHighlights(traceData, nodeId);

      if (typeof this.onSelectNode === 'function') {
        this.onSelectNode(nodeId, traceData);
      }
    } catch (err) {
      console.error('[DAG Trace Error]', err);
    }
  }

  applyTraceHighlights(traceData, targetNodeId) {
    if (!traceData) return;

    const ancestorNodes = traceData.ancestor_nodes || [];
    const descendantNodes = traceData.descendant_nodes || [];
    const ancestorEdgeIds = new Set(traceData.ancestor_edge_ids || []);
    const descendantEdgeIds = new Set(traceData.descendant_edge_ids || []);

    // 1. Highlight Ancestors in Glowing Cyan ("Откуда что родилось")
    ancestorNodes.forEach(n => {
      const el = document.getElementById(`dag-node-${n.id}`);
      if (el) el.classList.add('highlight-ancestor');
    });

    // 2. Highlight Descendants in Glowing Emerald ("Импакт / Наследники")
    descendantNodes.forEach(n => {
      const el = document.getElementById(`dag-node-${n.id}`);
      if (el) el.classList.add('highlight-descendant');
    });

    // 3. Highlight Edges
    const edges = this.graphData.edges || [];
    edges.forEach(edge => {
      const edgeEl = document.getElementById(`dag-edge-${edge.id}`);
      if (!edgeEl) return;

      if (ancestorEdgeIds.has(edge.id)) {
        edgeEl.classList.add('highlight-ancestor');
        edgeEl.setAttribute('marker-end', 'url(#arrow-ancestor)');
      } else if (descendantEdgeIds.has(edge.id)) {
        edgeEl.classList.add('highlight-descendant');
        edgeEl.setAttribute('marker-end', 'url(#arrow-descendant)');
      } else {
        edgeEl.style.opacity = '0.25';
      }
    });

    // Dim non-related nodes slightly to accentuate the provenance path
    const activeIds = new Set([
      targetNodeId,
      ...ancestorNodes.map(n => n.id),
      ...descendantNodes.map(n => n.id)
    ]);

    this.layoutNodes.forEach((_, nId) => {
      const el = document.getElementById(`dag-node-${nId}`);
      if (el && !activeIds.has(nId)) {
        el.style.opacity = '0.35';
      }
    });
  }

  _clearHighlightStyles() {
    // Reset all nodes
    this.layoutNodes.forEach((_, nId) => {
      const el = document.getElementById(`dag-node-${nId}`);
      if (el) {
        el.classList.remove('active', 'highlight-ancestor', 'highlight-descendant');
        el.style.opacity = '1';
      }
    });

    // Reset all edges
    (this.graphData.edges || []).forEach(edge => {
      const edgeEl = document.getElementById(`dag-edge-${edge.id}`);
      if (edgeEl) {
        edgeEl.classList.remove('highlight-ancestor', 'highlight-descendant');
        edgeEl.setAttribute('marker-end', 'url(#arrow-default)');
        edgeEl.style.opacity = '1';
      }
    });
  }

  resetSelection() {
    this.selectedNodeId = null;
    this._clearHighlightStyles();
    if (typeof this.onSelectNode === 'function') {
      this.onSelectNode(null, null);
    }
  }
}

// Global exposure
window.SpecKitDAG = SpecKitDAG;
