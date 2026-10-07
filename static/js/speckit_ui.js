/**
 * Corporate Spec-Kit Master UI Controller & Interaction Engine
 * Zero external dependencies; Pure Vanilla ES6+ DOM Lifecycle.
 */
class SpecKitUI {
  constructor() {
    this.api = window.speckitApi || new SpecKitApi();
    this.dag = null;

    this.currentSpecId = 'proj-airgap-gateway';
    this.projects = [];
    this.requirements = [];
    this.clarifications = [];
    this.tasks = [];
    this.matrixData = null;
    this.auditLog = [];

    this.reqFilterCategory = 'ALL';
    this.reqSearchQuery = '';
    this.clarFilter = 'ALL';
    this.auditSearchQuery = '';

    this.editingReq = null;
    this.pipeline = new PipelineController(this);
  }

  async init() {
    this.dag = new SpecKitDAG({
      onSelectNode: (nodeId, traceData) => this.handleDagNodeSelected(nodeId, traceData)
    });
    this.dag.init('#dag-canvas-container', this.api, this.currentSpecId);

    this._bindNavEvents();
    this._bindModalEvents();
    this._bindActionEvents();

    await this.loadProjects();
    await this.refreshAllData();
    await this.pipeline.init();
  }

  /* ---------------- TOAST NOTIFICATIONS ---------------- */

  showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    
    const icon = type === 'success' ? '✅' : type === 'error' ? '❌' : 'ℹ️';
    toast.innerHTML = `
      <span style="font-size:16px;">${icon}</span>
      <span style="flex:1;">${this._escape(message)}</span>
    `;

    container.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateX(100%)';
      setTimeout(() => toast.remove(), 300);
    }, 3500);
  }

  _escape(str) {
    if (str === null || str === undefined) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  /* ---------------- DATA LOADING & REFRESH ---------------- */

  async loadProjects() {
    try {
      this.projects = await this.api.getProjects();
      const select = document.getElementById('project-select');
      if (select) {
        select.innerHTML = '';
        this.projects.forEach(p => {
          const opt = document.createElement('option');
          opt.value = p.id;
          opt.textContent = `${p.id} - ${p.title}`;
          if (p.id === this.currentSpecId) opt.selected = true;
          select.appendChild(opt);
        });

        // Ensure currentSpecId is valid
        if (!this.projects.some(p => p.id === this.currentSpecId) && this.projects.length > 0) {
          this.currentSpecId = this.projects[0].id;
          select.value = this.currentSpecId;
        }
      }
    } catch (err) {
      this.showToast(`Failed to load projects: ${err.message}`, 'error');
    }
  }

  async switchProject(specId) {
    this.currentSpecId = specId;
    this.dag.setSpecId(specId);
    await this.refreshAllData();
    this.showToast(`Switched active specification to: ${specId}`, 'info');
  }

  async refreshAllData() {
    try {
      // Parallel fetch for speed
      const [reqs, clars, tasks, matrix, audit] = await Promise.all([
        this.api.getRequirements(this.currentSpecId),
        this.api.getClarifications(this.currentSpecId),
        this.api.getTasks(this.currentSpecId),
        this.api.getMatrix(this.currentSpecId),
        this.api.getAudit(this.currentSpecId)
      ]);

      this.requirements = reqs;
      this.clarifications = clars;
      this.tasks = tasks;
      this.matrixData = matrix;
      this.auditLog = audit;

      this.updateKpiRibbon();
      this.renderRequirementsTab();
      this.renderClarificationsTab();
      this.renderMatrixTab();
      this.renderAuditTab();

      // Refresh DAG
      await this.dag.loadAndRender(this.currentSpecId);
      this.resetDagInspector();
    } catch (err) {
      console.error('[RefreshAllData Error]', err);
      this.showToast(`Error syncing spec data: ${err.message}`, 'error');
    }
  }

  /* ---------------- KPI RIBBON ---------------- */

  updateKpiRibbon() {
    const totalReqs = this.requirements.length;
    const acceptedReqs = this.requirements.filter(r => r.status === 'ACCEPTED').length;

    const totalClars = this.clarifications.length;
    const resolvedClars = this.clarifications.filter(c => c.status === 'RESOLVED').length;
    const openClars = totalClars - resolvedClars;

    const totalTasks = this.tasks.length;
    const doneTasks = this.tasks.filter(t => t.status === 'DONE').length;

    const coveragePct = this.matrixData ? this.matrixData.overall_coverage_pct : 0;

    // Set KPI Values
    const kpiCov = document.getElementById('kpi-coverage-val');
    const kpiCovBar = document.getElementById('kpi-coverage-bar');
    if (kpiCov) kpiCov.textContent = `${coveragePct}%`;
    if (kpiCovBar) kpiCovBar.style.width = `${coveragePct}%`;

    const kpiReqs = document.getElementById('kpi-reqs-val');
    const kpiReqsSub = document.getElementById('kpi-reqs-sub');
    if (kpiReqs) kpiReqs.textContent = totalReqs;
    if (kpiReqsSub) kpiReqsSub.textContent = `${acceptedReqs} accepted, ${totalReqs - acceptedReqs} proposed`;

    const kpiClars = document.getElementById('kpi-clars-val');
    const kpiClarsSub = document.getElementById('kpi-clars-sub');
    if (kpiClars) kpiClars.textContent = openClars;
    if (kpiClarsSub) kpiClarsSub.textContent = `${resolvedClars} resolved of ${totalClars} total`;

    const kpiTasks = document.getElementById('kpi-tasks-val');
    const kpiTasksSub = document.getElementById('kpi-tasks-sub');
    if (kpiTasks) kpiTasks.textContent = totalTasks;
    if (kpiTasksSub) kpiTasksSub.textContent = `${doneTasks} completed (${totalTasks > 0 ? Math.round((doneTasks/totalTasks)*100) : 0}%)`;
  }

  /* ---------------- TAB NAVIGATION ---------------- */

  _bindNavEvents() {
    const tabs = document.querySelectorAll('.nav-tab');
    tabs.forEach(tab => {
      tab.addEventListener('click', () => {
        tabs.forEach(t => t.classList.remove('active'));
        tab.classList.add('active');

        const targetId = tab.getAttribute('data-tab');
        document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
        const pane = document.getElementById(targetId);
        if (pane) pane.classList.add('active');

        // Re-fit DAG if switching back to it
        if (targetId === 'tab-dag' && this.dag) {
          this.dag.render();
        }
        if (targetId === 'tab-pipeline' && this.pipeline) {
          this.pipeline.loadPipelines();
        }
      });
    });

    const projectSelect = document.getElementById('project-select');
    if (projectSelect) {
      projectSelect.addEventListener('change', (e) => {
        this.switchProject(e.target.value);
      });
    }

    const btnNewProject = document.getElementById('btn-new-project');
    if (btnNewProject) {
      btnNewProject.addEventListener('click', () => this.openModal('modal-create-project'));
    }
  }

  /* ---------------- TAB 1: DAG PROVENANCE & INSPECTOR ---------------- */

  handleDagNodeSelected(nodeId, traceData) {
    const inspector = document.getElementById('dag-inspector-panel');
    if (!inspector) return;

    if (!nodeId || !traceData) {
      this.resetDagInspector();
      return;
    }

    const target = traceData.target_node;
    if (!target) return;

    const ancestors = traceData.ancestor_nodes || [];
    const descendants = traceData.descendant_nodes || [];

    let metaInfo = {};
    try {
      metaInfo = JSON.parse(target.meta_json || '{}');
    } catch (_) {}

    const typeIcons = {
      INTENT: '🎯',
      CONSTITUTION: '📜',
      REQUIREMENT: '📋',
      CLARIFICATION: '❓',
      TASK: '⚙️',
      TEST: '🧪',
      CODE: '📦'
    };

    const icon = typeIcons[target.node_type] || '📌';

    let ancestorsHtml = '<p style="color:var(--text-dim);font-size:12px;">Root origin (No ancestors)</p>';
    if (ancestors.length > 0) {
      ancestorsHtml = ancestors.map(a => `
        <span class="trace-pill trace-ancestor" onclick="speckitUI.dag.selectNode('${this._escape(a.id)}')">
          ${typeIcons[a.node_type] || ''} ${this._escape(a.entity_id || a.id)}
        </span>
      `).join('');
    }

    let descendantsHtml = '<p style="color:var(--text-dim);font-size:12px;">Terminal leaf (No downstream impact)</p>';
    if (descendants.length > 0) {
      descendantsHtml = descendants.map(d => `
        <span class="trace-pill trace-descendant" onclick="speckitUI.dag.selectNode('${this._escape(d.id)}')">
          ${typeIcons[d.node_type] || ''} ${this._escape(d.entity_id || d.id)}
        </span>
      `).join('');
    }

    // Quick action link based on type
    let jumpAction = '';
    if (target.node_type === 'REQUIREMENT') {
      jumpAction = `<button class="btn btn-secondary btn-sm" onclick="speckitUI.jumpToRequirement('${this._escape(target.entity_id)}')">📋 View Requirement</button>`;
    } else if (target.node_type === 'CLARIFICATION') {
      jumpAction = `<button class="btn btn-secondary btn-sm" onclick="speckitUI.jumpToClarification('${this._escape(target.entity_id)}')">❓ View Clarification</button>`;
    } else if (target.node_type === 'TASK') {
      jumpAction = `<button class="btn btn-secondary btn-sm" onclick="speckitUI.jumpToMatrix()">📊 View in Matrix</button>`;
    }

    inspector.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:12px;">
        <span class="badge badge-cyan">${icon} ${this._escape(target.node_type)}</span>
        <button class="btn btn-secondary btn-sm" onclick="speckitUI.dag.resetSelection()">✕ Clear</button>
      </div>

      <h3 style="font-size:15px;font-weight:700;color:#fff;margin-bottom:6px;word-break:break-all;">
        ${this._escape(target.entity_id || target.id)}
      </h3>
      <p style="font-size:13px;color:var(--text-muted);margin-bottom:14px;">
        ${this._escape(target.label)}
      </p>

      ${jumpAction ? `<div style="margin-bottom:14px;">${jumpAction}</div>` : ''}

      <div style="margin-bottom:16px;">
        <h5 style="font-size:11px;font-weight:700;text-transform:uppercase;color:#38bdf8;letter-spacing:0.05em;margin-bottom:6px;">
          🌐 Откуда что родилось (${ancestors.length} Ancestors)
        </h5>
        <div style="display:flex;flex-wrap:wrap;">
          ${ancestorsHtml}
        </div>
      </div>

      <div style="margin-bottom:16px;">
        <h5 style="font-size:11px;font-weight:700;text-transform:uppercase;color:#34d399;letter-spacing:0.05em;margin-bottom:6px;">
          ⚡ Импакт / Наследники (${descendants.length} Downstream)
        </h5>
        <div style="display:flex;flex-wrap:wrap;">
          ${descendantsHtml}
        </div>
      </div>

      <div style="background:rgba(0,0,0,0.3);padding:10px;border-radius:6px;font-family:var(--font-mono);font-size:11px;color:var(--text-dim);">
        <div style="font-weight:bold;margin-bottom:4px;color:var(--text-muted);">METADATA:</div>
        <pre style="white-space:pre-wrap;margin:0;">${this._escape(JSON.stringify(metaInfo, null, 2))}</pre>
      </div>
    `;
  }

  resetDagInspector() {
    const inspector = document.getElementById('dag-inspector-panel');
    if (!inspector) return;
    inspector.innerHTML = `
      <div style="text-align:center;padding:30px 10px;color:var(--text-dim);">
        <div style="font-size:28px;margin-bottom:8px;">🎯</div>
        <h4 style="font-size:13px;color:var(--text-muted);margin-bottom:6px;">Provenance Inspector</h4>
        <p style="font-size:12px;line-height:1.4;">
          Click any node in the SVG graph to inspect its complete origin chain (<span style="color:#38bdf8;">Откуда что родилось</span>) and downstream impact (<span style="color:#34d399;">Импакт / Наследники</span>).
        </p>
      </div>
    `;
  }

  jumpToRequirement(reqId) {
    document.querySelector('.nav-tab[data-tab="tab-reqs"]').click();
    this.reqSearchQuery = reqId;
    const searchInput = document.getElementById('req-search-input');
    if (searchInput) searchInput.value = reqId;
    this.renderRequirementsTab();
  }

  jumpToClarification(clarId) {
    document.querySelector('.nav-tab[data-tab="tab-clars"]').click();
  }

  jumpToMatrix() {
    document.querySelector('.nav-tab[data-tab="tab-matrix"]').click();
  }

  /* ---------------- TAB 2: REQUIREMENTS & DIFFS ---------------- */

  renderRequirementsTab() {
    const container = document.getElementById('requirements-list');
    if (!container) return;

    let filtered = this.requirements.filter(r => {
      const matchCat = this.reqFilterCategory === 'ALL' || r.category === this.reqFilterCategory;
      const q = this.reqSearchQuery.toLowerCase();
      const matchSearch = !q ||
        r.id.toLowerCase().includes(q) ||
        r.title.toLowerCase().includes(q) ||
        r.description.toLowerCase().includes(q) ||
        (r.rationale && r.rationale.toLowerCase().includes(q));
      return matchCat && matchSearch;
    });

    if (filtered.length === 0) {
      container.innerHTML = `
        <div class="card" style="text-align:center;padding:40px;color:var(--text-dim);">
          <div style="font-size:32px;margin-bottom:10px;">📋</div>
          <p>No requirements match the selected category or search filter.</p>
        </div>
      `;
      return;
    }

    container.innerHTML = filtered.map(r => {
      const criteria = Array.isArray(r.acceptance_criteria) ? r.acceptance_criteria : [];
      const criteriaHtml = criteria.map(c => `
        <li style="margin-bottom:4px;color:var(--text-muted);font-size:12px;line-height:1.4;">
          <span style="color:var(--cyan);margin-right:6px;">✔</span>${this._escape(c)}
        </li>
      `).join('');

      const catBadgeClass = r.category === 'SECURITY' ? 'badge-rose' :
                            r.category === 'COMPLIANCE' ? 'badge-amber' :
                            r.category === 'PERFORMANCE' ? 'badge-purple' : 'badge-cyan';

      return `
        <div class="card" style="margin-bottom:16px;" id="card-${this._escape(r.id)}">
          <div class="card-header">
            <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
              <span class="badge ${catBadgeClass}">${this._escape(r.category)}</span>
              <span style="font-family:var(--font-mono);font-weight:700;color:var(--cyan);">${this._escape(r.id)}</span>
              <span class="badge badge-purple">v${r.current_version}</span>
              <span class="badge badge-${r.status === 'ACCEPTED' ? 'green' : 'amber'}">${this._escape(r.status)}</span>
              <span class="card-title" style="margin-left:6px;">${this._escape(r.title)}</span>
            </div>
            <div style="display:flex;gap:6px;">
              <button class="btn btn-secondary btn-sm" onclick="speckitUI.openDiffInspector('${this._escape(r.id)}')">
                📜 Revisions (${r.current_version})
              </button>
              <button class="btn btn-secondary btn-sm" onclick="speckitUI.openEditReqModal('${this._escape(r.id)}')">
                ✏️ Edit
              </button>
              <button class="btn btn-secondary btn-sm" onclick="speckitUI.openClarifyForReq('${this._escape(r.id)}')">
                ❓ Clarify
              </button>
              <button class="btn btn-secondary btn-sm" onclick="speckitUI.openTaskForReq('${this._escape(r.id)}')">
                ⚙️ Add Task
              </button>
              <button class="btn btn-secondary btn-sm" style="color:#c084fc;" onclick="speckitUI.aiDecomposeTasks('${this._escape(r.id)}')">
                🤖 AI Tasks
              </button>
            </div>
          </div>

          <div style="margin-bottom:12px;">
            <p style="font-size:13px;line-height:1.5;color:#e2e8f0;margin-bottom:10px;">
              ${this._escape(r.description)}
            </p>
            ${r.rationale ? `
              <div style="background:rgba(255,255,255,0.02);padding:8px 12px;border-left:3px solid var(--purple);border-radius:0 6px 6px 0;margin-bottom:10px;">
                <span style="font-size:11px;font-weight:700;color:var(--purple);text-transform:uppercase;">Rationale: </span>
                <span style="font-size:12px;color:var(--text-muted);">${this._escape(r.rationale)}</span>
              </div>
            ` : ''}
          </div>

          ${criteria.length > 0 ? `
            <div style="margin-top:10px;padding-top:10px;border-top:1px solid var(--border-subtle);">
              <div style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text-dim);margin-bottom:6px;letter-spacing:0.04em;">
                Acceptance Criteria (${criteria.length}):
              </div>
              <ul style="list-style:none;padding-left:4px;">
                ${criteriaHtml}
              </ul>
            </div>
          ` : ''}

          <div style="display:flex;justify-content:space-between;align-items:center;margin-top:12px;padding-top:8px;border-top:1px solid rgba(255,255,255,0.04);font-size:11px;color:var(--text-dim);">
            <div>Author: <span style="color:var(--text-muted);">${this._escape(r.created_by)} (${this._escape(r.created_role)})</span></div>
            <div>Updated: ${new Date(r.updated_at || r.created_at).toLocaleString()}</div>
          </div>
        </div>
      `;
    }).join('');
  }

  /* ---------------- TAB 3: CLARIFICATION LOOP ---------------- */

  renderClarificationsTab() {
    const container = document.getElementById('clarifications-list');
    if (!container) return;

    let filtered = this.clarifications.filter(c => {
      if (this.clarFilter === 'OPEN') return c.status === 'OPEN';
      if (this.clarFilter === 'RESOLVED') return c.status === 'RESOLVED';
      return true;
    });

    if (filtered.length === 0) {
      container.innerHTML = `
        <div class="card" style="text-align:center;padding:40px;color:var(--text-dim);">
          <div style="font-size:32px;margin-bottom:10px;">❓</div>
          <p>No clarifications found for the current filter.</p>
        </div>
      `;
      return;
    }

    container.innerHTML = filtered.map(c => {
      const isResolved = c.status === 'RESOLVED';
      return `
        <div class="clar-card" id="clar-${this._escape(c.id)}">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
            <div style="display:flex;align-items:center;gap:8px;">
              <span class="badge ${isResolved ? 'badge-green' : 'badge-amber'}">${this._escape(c.status)}</span>
              <span style="font-family:var(--font-mono);font-weight:700;color:var(--cyan);font-size:12px;">${this._escape(c.id)}</span>
              ${c.req_id ? `<span class="badge badge-purple" style="cursor:pointer;" onclick="speckitUI.jumpToRequirement('${this._escape(c.req_id)}')">Linked: ${this._escape(c.req_id)}</span>` : '<span class="badge badge-cyan">Spec-Wide</span>'}
            </div>
            <div style="font-size:11px;color:var(--text-dim);">
              Asked by: <span style="color:var(--text-muted);">${this._escape(c.asked_by)} (${this._escape(c.asked_role)})</span>
            </div>
          </div>

          <div class="clar-question">
            ${this._escape(c.question)}
          </div>

          ${isResolved ? `
            <div class="clar-answer">
              <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;font-size:11px;color:var(--green);">
                <span>✔ Resolution by ${this._escape(c.answered_by)} (${this._escape(c.answered_role)})</span>
                <span>${new Date(c.resolved_at || c.created_at).toLocaleString()}</span>
              </div>
              <div style="color:#e2e8f0;font-size:13px;line-height:1.5;">
                ${this._escape(c.answer)}
              </div>
            </div>
            <div style="display:flex;justify-content:flex-end;margin-top:10px;gap:8px;">
              <button class="btn btn-secondary btn-sm" onclick="speckitUI.foldClarificationIntoReq('${this._escape(c.id)}')">
                🔄 Fold into Requirement
              </button>
            </div>
          ` : `
            <div style="display:flex;justify-content:flex-end;margin-top:12px;gap:8px;">
              <button class="btn btn-primary btn-sm" onclick="speckitUI.openResolveClarModal('${this._escape(c.id)}')">
                ✍️ Resolve & Answer
              </button>
            </div>
          `}
        </div>
      `;
    }).join('');
  }

  foldClarificationIntoReq(clarId) {
    const clar = this.clarifications.find(c => c.id === clarId);
    if (!clar || !clar.req_id) {
      this.showToast('This clarification is not linked to a specific requirement.', 'error');
      return;
    }

    const req = this.requirements.find(r => r.id === clar.req_id);
    if (!req) {
      this.showToast(`Requirement ${clar.req_id} not found`, 'error');
      return;
    }

    // Open edit modal and augment description
    this.openEditReqModal(req.id);

    const descInput = document.getElementById('edit-req-description');
    const justInput = document.getElementById('edit-req-justification');

    if (descInput) {
      descInput.value = `${descInput.value}\n\n[Clarification ${clar.id} Resolution]: ${clar.answer}`;
      // Trigger live diff update
      this.updateEditReqLiveDiff();
    }
    if (justInput) {
      justInput.value = `Folded clarification ${clar.id} into specification`;
    }

    this.showToast(`Folded resolution from ${clar.id} into ${req.id} draft`, 'success');
  }

  /* ---------------- TAB 4: TRACEABILITY MATRIX (RTM) ---------------- */

  renderMatrixTab() {
    const container = document.getElementById('matrix-table-container');
    const orphanContainer = document.getElementById('orphan-reqs-alert');
    if (!container || !this.matrixData) return;

    const orphans = this.matrixData.orphan_requirements || [];
    if (orphanContainer) {
      if (orphans.length > 0) {
        orphanContainer.style.display = 'flex';
        orphanContainer.innerHTML = `
          <span style="font-size:20px;">⚠️</span>
          <div style="flex:1;">
            <strong>Orphan Requirements Detected (${orphans.length}):</strong>
            The following requirements have 0 associated implementation tasks:
            <span style="font-family:var(--font-mono);font-weight:bold;margin-left:6px;">
              ${orphans.map(o => `<span class="badge badge-amber" style="cursor:pointer;" onclick="speckitUI.jumpToRequirement('${o}')">${o}</span>`).join(' ')}
            </span>
          </div>
        `;
      } else {
        orphanContainer.style.display = 'none';
      }
    }

    const rows = this.matrixData.matrix || [];
    if (rows.length === 0) {
      container.innerHTML = `<div style="text-align:center;padding:30px;color:var(--text-dim);">No requirements available in matrix.</div>`;
      return;
    }

    container.innerHTML = `
      <table class="data-table">
        <thead>
          <tr>
            <th>Req ID & Title</th>
            <th>Cat / Ver</th>
            <th>Clarifications</th>
            <th>Tasks & Assignees</th>
            <th>Test Cases</th>
            <th>Code Targets</th>
            <th>Coverage</th>
          </tr>
        </thead>
        <tbody>
          ${rows.map(row => {
            const tasksHtml = row.tasks.length > 0
              ? row.tasks.map(t => {
                  const statusClass = t.status === 'DONE' ? 'badge-green' : t.status === 'IN_PROGRESS' ? 'badge-amber' : 'badge-cyan';
                  return `
                    <div style="margin-bottom:4px;display:flex;align-items:center;gap:6px;">
                      <span class="badge ${statusClass}">${t.status}</span>
                      <span style="font-size:12px;">${this._escape(t.id)}: ${this._escape(t.title)}</span>
                      <span style="font-size:11px;color:var(--text-dim);">(${this._escape(t.assignee)})</span>
                    </div>
                  `;
                }).join('')
              : '<span style="color:#fda4af;font-size:12px;">⚠️ No tasks (Orphan)</span>';

            const clarsHtml = row.clarifications.length > 0
              ? row.clarifications.map(c => `
                  <span class="badge ${c.status === 'RESOLVED' ? 'badge-green' : 'badge-amber'}" title="${this._escape(c.question)}">
                    ${this._escape(c.id)} (${c.status})
                  </span>
                `).join(' ')
              : '<span style="color:var(--text-dim);font-size:12px;">—</span>';

            const testsHtml = row.tests.length > 0
              ? row.tests.map(t => `<span class="badge badge-purple" style="font-family:var(--font-mono);">${this._escape(t)}</span>`).join(' ')
              : '<span style="color:var(--text-dim);font-size:12px;">—</span>';

            const codeHtml = row.code_targets.length > 0
              ? row.code_targets.map(c => `<div style="font-family:var(--font-mono);font-size:11px;color:var(--cyan);">${this._escape(c)}</div>`).join('')
              : '<span style="color:var(--text-dim);font-size:12px;">—</span>';

            return `
              <tr>
                <td>
                  <div style="font-family:var(--font-mono);font-weight:700;color:var(--cyan);cursor:pointer;" onclick="speckitUI.jumpToRequirement('${this._escape(row.req_id)}')">
                    ${this._escape(row.req_id)}
                  </div>
                  <div style="font-size:12px;color:var(--text-muted);">${this._escape(row.title)}</div>
                </td>
                <td>
                  <span class="badge badge-cyan">${this._escape(row.category)}</span>
                  <div style="font-size:11px;color:var(--text-dim);margin-top:2px;">v${row.version}</div>
                </td>
                <td>${clarsHtml}</td>
                <td>${tasksHtml}</td>
                <td>${testsHtml}</td>
                <td>${codeHtml}</td>
                <td>
                  <div style="display:flex;align-items:center;gap:8px;">
                    <span style="font-weight:700;font-family:var(--font-mono);font-size:12px;color:${row.coverage_pct === 100 ? 'var(--green)' : 'var(--amber)'};">
                      ${row.coverage_pct}%
                    </span>
                    <div class="progress-track" style="width:70px;">
                      <div class="progress-bar" style="width:${row.coverage_pct}%;"></div>
                    </div>
                  </div>
                </td>
              </tr>
            `;
          }).join('')}
        </tbody>
      </table>
    `;
  }

  /* ---------------- TAB 5: AUDIT & CHANGE HISTORY ---------------- */

  renderAuditTab() {
    const container = document.getElementById('audit-table-container');
    if (!container) return;

    let filtered = this.auditLog.filter(item => {
      const q = this.auditSearchQuery.toLowerCase();
      if (!q) return true;
      return (
        item.entity_type.toLowerCase().includes(q) ||
        item.entity_id.toLowerCase().includes(q) ||
        item.action.toLowerCase().includes(q) ||
        item.actor_name.toLowerCase().includes(q) ||
        item.details.toLowerCase().includes(q)
      );
    });

    if (filtered.length === 0) {
      container.innerHTML = `<div style="text-align:center;padding:30px;color:var(--text-dim);">No audit events matching query.</div>`;
      return;
    }

    container.innerHTML = `
      <table class="data-table">
        <thead>
          <tr>
            <th>Timestamp</th>
            <th>Entity Type</th>
            <th>Entity ID</th>
            <th>Action</th>
            <th>Actor & Role</th>
            <th>Details</th>
            <th>Diff</th>
          </tr>
        </thead>
        <tbody>
          ${filtered.map(entry => {
            const actionBadge = entry.action === 'CREATED' ? 'badge-green' :
                                entry.action === 'MODIFIED' ? 'badge-amber' :
                                entry.action === 'RESOLVED' ? 'badge-cyan' : 'badge-purple';

            const canDiff = entry.entity_type === 'REQUIREMENT';

            return `
              <tr>
                <td style="font-family:var(--font-mono);font-size:11px;color:var(--text-dim);white-space:nowrap;">
                  ${new Date(entry.timestamp).toLocaleString()}
                </td>
                <td><span class="badge badge-cyan">${this._escape(entry.entity_type)}</span></td>
                <td style="font-family:var(--font-mono);font-weight:600;">${this._escape(entry.entity_id)}</td>
                <td><span class="badge ${actionBadge}">${this._escape(entry.action)}</span></td>
                <td>
                  <div style="font-size:12px;color:#fff;">${this._escape(entry.actor_name)}</div>
                  <div style="font-size:11px;color:var(--text-dim);">${this._escape(entry.actor_role)}</div>
                </td>
                <td style="font-size:12px;color:var(--text-muted);max-width:320px;">${this._escape(entry.details)}</td>
                <td>
                  ${canDiff ? `
                    <button class="btn btn-secondary btn-sm" onclick="speckitUI.openDiffInspector('${this._escape(entry.entity_id)}')">
                      📜 Diff
                    </button>
                  ` : '—'}
                </td>
              </tr>
            `;
          }).join('')}
        </tbody>
      </table>
    `;
  }

  /* ---------------- TAB 6: CORPORATE EXPORT & AI SETTINGS ---------------- */

  async exportMarkdownBundle() {
    try {
      this.showToast('Generating Corporate Spec-Kit Markdown Bundle...', 'info');
      const res = await this.api.exportMarkdown(this.currentSpecId);
      this.showToast(`Markdown bundle generated at: ${res.directory} (${res.files.length} files)`, 'success');
      alert(`Spec-Kit Bundle exported successfully!\n\nTarget directory: ${res.directory}\n\nFiles generated:\n${res.files.map(f => ' - ' + f).join('\n')}`);
    } catch (err) {
      this.showToast(`Export failed: ${err.message}`, 'error');
    }
  }

  downloadHtmlDossier() {
    const url = this.api.getExportHtmlUrl(this.currentSpecId);
    window.open(url, '_blank');
    this.showToast('Downloading standalone HTML specification dossier...', 'success');
  }

  async loadSettings() {
    try {
      const cfg = await this.api.getSettings();
      const endpoint = document.getElementById('setting-ai-endpoint');
      const key = document.getElementById('setting-ai-key');
      const model = document.getElementById('setting-ai-model');
      if (endpoint) endpoint.value = cfg.ai_endpoint || '';
      if (key) key.value = cfg.ai_api_key || '';
      if (model) model.value = cfg.ai_model || 'claude-3-7-sonnet';
    } catch (err) {
      console.warn('Could not load AI settings:', err);
    }
  }

  async saveSettings() {
    const endpoint = document.getElementById('setting-ai-endpoint').value.trim();
    const key = document.getElementById('setting-ai-key').value.trim();
    const model = document.getElementById('setting-ai-model').value.trim();

    try {
      await this.api.saveSettings({
        ai_endpoint: endpoint,
        ai_api_key: key,
        ai_model: model
      });
      this.showToast('Corporate AI bridge configuration saved!', 'success');
    } catch (err) {
      this.showToast(`Failed to save settings: ${err.message}`, 'error');
    }
  }

  /* ---------------- MODALS & FORMS ---------------- */

  openModal(modalId) {
    const el = document.getElementById(modalId);
    if (el) el.classList.add('open');
  }

  closeModal(modalId) {
    const el = document.getElementById(modalId);
    if (el) el.classList.remove('open');
  }

  _bindModalEvents() {
    // Backdrop click to close
    document.querySelectorAll('.modal-overlay').forEach(overlay => {
      overlay.addEventListener('click', (e) => {
        if (e.target === overlay) {
          overlay.classList.remove('open');
        }
      });
    });

    // Close buttons inside modals
    document.querySelectorAll('.modal-close-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const modal = e.target.closest('.modal-overlay');
        if (modal) modal.classList.remove('open');
      });
    });
  }

  _bindActionEvents() {
    // Category filters in Reqs tab
    document.querySelectorAll('.filter-pill-cat').forEach(pill => {
      pill.addEventListener('click', () => {
        document.querySelectorAll('.filter-pill-cat').forEach(p => p.classList.remove('active'));
        pill.classList.add('active');
        this.reqFilterCategory = pill.getAttribute('data-cat') || 'ALL';
        this.renderRequirementsTab();
      });
    });

    // Search inputs
    const reqSearch = document.getElementById('req-search-input');
    if (reqSearch) {
      reqSearch.addEventListener('input', (e) => {
        this.reqSearchQuery = e.target.value;
        this.renderRequirementsTab();
      });
    }

    const auditSearch = document.getElementById('audit-search-input');
    if (auditSearch) {
      auditSearch.addEventListener('input', (e) => {
        this.auditSearchQuery = e.target.value;
        this.renderAuditTab();
      });
    }

    // Clarification filters
    document.querySelectorAll('.filter-pill-clar').forEach(pill => {
      pill.addEventListener('click', () => {
        document.querySelectorAll('.filter-pill-clar').forEach(p => p.classList.remove('active'));
        pill.classList.add('active');
        this.clarFilter = pill.getAttribute('data-status') || 'ALL';
        this.renderClarificationsTab();
      });
    });

    // Form Submissions
    this._bindFormSubmissions();
  }

  _bindFormSubmissions() {
    // 1. Create Requirement Form
    const createReqForm = document.getElementById('form-create-req');
    if (createReqForm) {
      createReqForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        await this.handleCreateRequirement();
      });
    }

    // 2. Edit Requirement Form
    const editReqForm = document.getElementById('form-edit-req');
    if (editReqForm) {
      editReqForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        await this.handleUpdateRequirement();
      });
    }

    // 3. Ask Clarification Form
    const clarForm = document.getElementById('form-ask-clar');
    if (clarForm) {
      clarForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        await this.handleAskClarification();
      });
    }

    // 4. Resolve Clarification Form
    const resolveClarForm = document.getElementById('form-resolve-clar');
    if (resolveClarForm) {
      resolveClarForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        await this.handleResolveClarification();
      });
    }

    // 5. Create Task Form
    const taskForm = document.getElementById('form-create-task');
    if (taskForm) {
      taskForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        await this.handleCreateTask();
      });
    }

    // 6. Create Project Form
    const projForm = document.getElementById('form-create-project');
    if (projForm) {
      projForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        await this.handleCreateProject();
      });
    }
  }

  /* ---------------- REQUIREMENT CRUD ---------------- */

  openCreateReqModal() {
    const list = document.getElementById('create-req-criteria-list');
    if (list) {
      list.innerHTML = `
        <div class="criteria-item">
          <input type="text" class="form-input criteria-input" placeholder="e.g. Given a client without cert, when TLS handshake occurs, then reject." />
          <button type="button" class="btn btn-secondary btn-sm" onclick="this.parentElement.remove()">✕</button>
        </div>
      `;
    }
    this.openModal('modal-create-req');
  }

  addCriteriaField(containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;
    const item = document.createElement('div');
    item.className = 'criteria-item';
    item.innerHTML = `
      <input type="text" class="form-input criteria-input" placeholder="Acceptance criteria rule (Given/When/Then)..." />
      <button type="button" class="btn btn-secondary btn-sm" onclick="this.parentElement.remove()">✕</button>
    `;
    container.appendChild(item);
  }

  async handleCreateRequirement() {
    const title = document.getElementById('create-req-title').value.trim();
    const category = document.getElementById('create-req-category').value;
    const description = document.getElementById('create-req-description').value.trim();
    const rationale = document.getElementById('create-req-rationale').value.trim();
    const authorName = document.getElementById('create-req-author-name').value.trim();
    const authorRole = document.getElementById('create-req-author-role').value.trim();
    const justification = document.getElementById('create-req-justification').value.trim();

    const criteriaInputs = document.querySelectorAll('#create-req-criteria-list .criteria-input');
    const criteria = Array.from(criteriaInputs).map(i => i.value.trim()).filter(Boolean);

    try {
      await this.api.createRequirement({
        spec_id: this.currentSpecId,
        title,
        category,
        description,
        rationale,
        acceptance_criteria: criteria,
        author_name: authorName,
        author_role: authorRole,
        justification
      });

      this.closeModal('modal-create-req');
      this.showToast(`Requirement "${title}" created successfully!`, 'success');
      await this.refreshAllData();
    } catch (err) {
      this.showToast(`Failed to create requirement: ${err.message}`, 'error');
    }
  }

  openEditReqModal(reqId) {
    const req = this.requirements.find(r => r.id === reqId);
    if (!req) return;
    this.editingReq = req;

    document.getElementById('edit-req-id').value = req.id;
    document.getElementById('edit-req-title').value = req.title;
    document.getElementById('edit-req-category').value = req.category;
    document.getElementById('edit-req-status').value = req.status;
    document.getElementById('edit-req-description').value = req.description;
    document.getElementById('edit-req-rationale').value = req.rationale || '';
    document.getElementById('edit-req-justification').value = '';

    const list = document.getElementById('edit-req-criteria-list');
    list.innerHTML = '';
    const crit = Array.isArray(req.acceptance_criteria) ? req.acceptance_criteria : [];
    crit.forEach(c => {
      const item = document.createElement('div');
      item.className = 'criteria-item';
      item.innerHTML = `
        <input type="text" class="form-input criteria-input" value="${this._escape(c)}" />
        <button type="button" class="btn btn-secondary btn-sm" onclick="this.parentElement.remove(); speckitUI.updateEditReqLiveDiff();">✕</button>
      `;
      list.appendChild(item);
    });

    this.updateEditReqLiveDiff();

    // Bind real-time input change for live diff calculation
    ['edit-req-title', 'edit-req-category', 'edit-req-description', 'edit-req-rationale'].forEach(id => {
      const el = document.getElementById(id);
      if (el) {
        el.oninput = () => this.updateEditReqLiveDiff();
      }
    });

    this.openModal('modal-edit-req');
  }

  updateEditReqLiveDiff() {
    if (!this.editingReq) return;
    const diffContainer = document.getElementById('edit-req-live-diff');
    if (!diffContainer) return;

    const oldSnapshot = `Title: ${this.editingReq.title}\nCategory: ${this.editingReq.category}\nDesc: ${this.editingReq.description}\nRationale: ${this.editingReq.rationale || ''}\nCriteria:\n` + (this.editingReq.acceptance_criteria || []).map(c => `- ${c}`).join('\n');

    const newTitle = document.getElementById('edit-req-title').value;
    const newCat = document.getElementById('edit-req-category').value;
    const newDesc = document.getElementById('edit-req-description').value;
    const newRat = document.getElementById('edit-req-rationale').value;
    const criteriaInputs = document.querySelectorAll('#edit-req-criteria-list .criteria-input');
    const newCrit = Array.from(criteriaInputs).map(i => i.value.trim()).filter(Boolean);

    const newSnapshot = `Title: ${newTitle}\nCategory: ${newCat}\nDesc: ${newDesc}\nRationale: ${newRat}\nCriteria:\n` + newCrit.map(c => `- ${c}`).join('\n');

    diffContainer.innerHTML = this.renderDiffLines(oldSnapshot, newSnapshot);
  }

  async handleUpdateRequirement() {
    if (!this.editingReq) return;
    const reqId = this.editingReq.id;

    const title = document.getElementById('edit-req-title').value.trim();
    const category = document.getElementById('edit-req-category').value;
    const status = document.getElementById('edit-req-status').value;
    const description = document.getElementById('edit-req-description').value.trim();
    const rationale = document.getElementById('edit-req-rationale').value.trim();
    const authorName = document.getElementById('edit-req-author-name').value.trim();
    const authorRole = document.getElementById('edit-req-author-role').value.trim();
    const justification = document.getElementById('edit-req-justification').value.trim();

    if (!justification) {
      alert('Corporate Audit requires an explanation / justification for all specification revisions.');
      return;
    }

    const criteriaInputs = document.querySelectorAll('#edit-req-criteria-list .criteria-input');
    const criteria = Array.from(criteriaInputs).map(i => i.value.trim()).filter(Boolean);

    try {
      await this.api.updateRequirement(reqId, {
        title,
        category,
        status,
        description,
        rationale,
        acceptance_criteria: criteria,
        author_name: authorName,
        author_role: authorRole,
        justification
      });

      this.closeModal('modal-edit-req');
      this.showToast(`Requirement ${reqId} updated to v${this.editingReq.current_version + 1}!`, 'success');
      await this.refreshAllData();
    } catch (err) {
      this.showToast(`Failed to update requirement: ${err.message}`, 'error');
    }
  }

  /* ---------------- DIFF INSPECTOR MODAL ---------------- */

  async openDiffInspector(reqId) {
    try {
      const revs = await this.api.getRevisions(reqId);
      const req = this.requirements.find(r => r.id === reqId) || { title: reqId };

      document.getElementById('diff-modal-req-title').textContent = `${reqId}: ${req.title}`;
      const revSelect1 = document.getElementById('diff-select-v1');
      const revSelect2 = document.getElementById('diff-select-v2');

      if (revSelect1 && revSelect2) {
        revSelect1.innerHTML = '';
        revSelect2.innerHTML = '';

        revs.forEach((r, idx) => {
          const opt1 = document.createElement('option');
          opt1.value = r.version;
          opt1.textContent = `v${r.version} (${r.author_name} - ${r.change_type})`;

          const opt2 = document.createElement('option');
          opt2.value = r.version;
          opt2.textContent = `v${r.version} (${r.author_name} - ${r.change_type})`;

          revSelect1.appendChild(opt1);
          revSelect2.appendChild(opt2);
        });

        // Default: v1 vs latest vN
        revSelect1.value = revs[0] ? revs[0].version : '1';
        revSelect2.value = revs.length > 1 ? revs[revs.length - 1].version : revSelect1.value;

        const updateDiffView = () => {
          const v1 = parseInt(revSelect1.value, 10);
          const v2 = parseInt(revSelect2.value, 10);
          const rev1 = revs.find(r => r.version === v1);
          const rev2 = revs.find(r => r.version === v2);

          const snap1 = rev1 ? `Title: ${rev1.title}\nCategory: ${rev1.category}\nDesc: ${rev1.description}\nRationale: ${rev1.rationale}\nCriteria:\n` + (rev1.acceptance_criteria || []).map(c => `- ${c}`).join('\n') : '';
          const snap2 = rev2 ? `Title: ${rev2.title}\nCategory: ${rev2.category}\nDesc: ${rev2.description}\nRationale: ${rev2.rationale}\nCriteria:\n` + (rev2.acceptance_criteria || []).map(c => `- ${c}`).join('\n') : '';

          const display = document.getElementById('diff-content-view');
          if (display) {
            display.innerHTML = this.renderDiffLines(snap1, snap2);
          }

          const meta = document.getElementById('diff-meta-info');
          if (meta && rev2) {
            meta.innerHTML = `
              <div style="font-size:12px;color:var(--text-muted);margin-bottom:8px;">
                <strong>v${rev2.version} Change Justification:</strong> "${this._escape(rev2.justification || 'Initial creation')}"
                by <span style="color:#fff;">${this._escape(rev2.author_name)} (${this._escape(rev2.author_role)})</span>
                at ${new Date(rev2.timestamp).toLocaleString()}
              </div>
            `;
          }
        };

        revSelect1.onchange = updateDiffView;
        revSelect2.onchange = updateDiffView;
        updateDiffView();
      }

      this.openModal('modal-diff-inspector');
    } catch (err) {
      this.showToast(`Failed to load revisions: ${err.message}`, 'error');
    }
  }

  renderDiffLines(oldText, newText) {
    if (oldText === newText) {
      return `<div style="padding:16px;color:var(--text-dim);text-align:center;">No changes between selected versions.</div>`;
    }

    const oldLines = oldText.split('\n');
    const newLines = newText.split('\n');

    let html = '<div class="diff-unified-wrapper">';
    let i = 0, j = 0;

    while (i < oldLines.length || j < newLines.length) {
      const l1 = oldLines[i];
      const l2 = newLines[j];

      if (l1 === l2) {
        html += `<div class="diff-unified-line ctx"><span style="user-select:none;margin-right:10px;color:#475569;"> </span>${this._escape(l1)}</div>`;
        i++;
        j++;
      } else {
        if (l1 !== undefined && (l2 === undefined || !newLines.slice(j).includes(l1))) {
          html += `<div class="diff-unified-line del"><span style="user-select:none;margin-right:10px;font-weight:bold;">-</span>${this._escape(l1)}</div>`;
          i++;
        } else if (l2 !== undefined) {
          html += `<div class="diff-unified-line add"><span style="user-select:none;margin-right:10px;font-weight:bold;">+</span>${this._escape(l2)}</div>`;
          j++;
        } else {
          i++;
          j++;
        }
      }
    }

    html += '</div>';
    return html;
  }

  /* ---------------- CLARIFICATION ACTIONS ---------------- */

  openClarifyForReq(reqId) {
    this.populateReqDropdown('ask-clar-req-select', reqId);
    this.openModal('modal-ask-clar');
  }

  openAskClarModal() {
    this.populateReqDropdown('ask-clar-req-select', null);
    this.openModal('modal-ask-clar');
  }

  populateReqDropdown(selectId, selectedId = null) {
    const select = document.getElementById(selectId);
    if (!select) return;
    select.innerHTML = '<option value="">-- Spec-Wide Question (No linked req) --</option>';
    this.requirements.forEach(r => {
      const opt = document.createElement('option');
      opt.value = r.id;
      opt.textContent = `${r.id} - ${r.title}`;
      if (r.id === selectedId) opt.selected = true;
      select.appendChild(opt);
    });
  }

  async handleAskClarification() {
    const reqId = document.getElementById('ask-clar-req-select').value || null;
    const question = document.getElementById('ask-clar-question').value.trim();
    const askedBy = document.getElementById('ask-clar-author-name').value.trim();
    const askedRole = document.getElementById('ask-clar-author-role').value.trim();

    try {
      await this.api.addClarification({
        spec_id: this.currentSpecId,
        req_id: reqId,
        question,
        asked_by: askedBy,
        asked_role: askedRole
      });

      this.closeModal('modal-ask-clar');
      this.showToast('Question submitted to Spec-Kit Clarification Loop!', 'success');
      await this.refreshAllData();
    } catch (err) {
      this.showToast(`Failed to ask clarification: ${err.message}`, 'error');
    }
  }

  openResolveClarModal(clarId) {
    const clar = this.clarifications.find(c => c.id === clarId);
    if (!clar) return;

    document.getElementById('resolve-clar-id').value = clar.id;
    document.getElementById('resolve-clar-question-text').textContent = clar.question;
    document.getElementById('resolve-clar-answer').value = '';

    this.openModal('modal-resolve-clar');
  }

  async handleResolveClarification() {
    const clarId = document.getElementById('resolve-clar-id').value;
    const answer = document.getElementById('resolve-clar-answer').value.trim();
    const answeredBy = document.getElementById('resolve-clar-author-name').value.trim();
    const answeredRole = document.getElementById('resolve-clar-author-role').value.trim();

    try {
      await this.api.resolveClarification(clarId, {
        answer,
        answered_by: answeredBy,
        answered_role: answeredRole
      });

      this.closeModal('modal-resolve-clar');
      this.showToast(`Clarification ${clarId} successfully resolved!`, 'success');
      await this.refreshAllData();
    } catch (err) {
      this.showToast(`Failed to resolve clarification: ${err.message}`, 'error');
    }
  }

  /* ---------------- TASK ACTIONS ---------------- */

  openTaskForReq(reqId) {
    this.populateReqDropdown('create-task-req-select', reqId);
    this.openModal('modal-create-task');
  }

  async handleCreateTask() {
    const reqId = document.getElementById('create-task-req-select').value;
    const title = document.getElementById('create-task-title').value.trim();
    const description = document.getElementById('create-task-description').value.trim();
    const assignee = document.getElementById('create-task-assignee').value.trim();
    const testCaseId = document.getElementById('create-task-test-case').value.trim();
    const codeTargets = document.getElementById('create-task-code-target').value.trim();

    if (!reqId) {
      alert('Please select a parent Requirement to link this Task to.');
      return;
    }

    try {
      await this.api.createTask({
        spec_id: this.currentSpecId,
        req_id: reqId,
        title,
        description,
        assignee: assignee || 'Unassigned',
        test_case_id: testCaseId,
        code_targets: codeTargets
      });

      this.closeModal('modal-create-task');
      this.showToast(`Task "${title}" created and linked to ${reqId}!`, 'success');
      await this.refreshAllData();
    } catch (err) {
      this.showToast(`Failed to create task: ${err.message}`, 'error');
    }
  }

  /* ---------------- PROJECT ACTIONS ---------------- */

  async handleCreateProject() {
    const id = document.getElementById('create-project-id').value.trim();
    const title = document.getElementById('create-project-title').value.trim();
    const intent = document.getElementById('create-project-intent').value.trim();
    const constitution = document.getElementById('create-project-constitution').value.trim();

    try {
      const proj = await this.api.createProject({ id, title, intent, constitution });
      this.closeModal('modal-create-project');
      this.showToast(`New Specification Project "${title}" created!`, 'success');
      await this.loadProjects();
      await this.switchProject(proj.id);
    } catch (err) {
      this.showToast(`Failed to create project: ${err.message}`, 'error');
    }
  }

  /* ---------------- AI ASSIST ACTIONS ---------------- */

  async aiSuggestClarifications() {
    const title = document.getElementById('edit-req-title').value.trim();
    const description = document.getElementById('edit-req-description').value.trim();
    const rationale = document.getElementById('edit-req-rationale').value.trim();

    this.showToast('Querying AI for clarification suggestions...', 'info');
    try {
      const res = await this.api.aiClarify({ title, description, rationale });
      const suggestions = res.suggestions || [];
      if (suggestions.length === 0) {
        this.showToast('No clarification ambiguities detected by AI model.', 'info');
        return;
      }

      const q = prompt(`AI Model suggested these clarification points:\n\n` + suggestions.map((s, idx) => `${idx+1}. ${s}`).join('\n\n') + `\n\nType the number of a suggestion to auto-ask it as a Clarification question:`);
      const selectedIdx = parseInt(q, 10) - 1;
      if (selectedIdx >= 0 && selectedIdx < suggestions.length) {
        await this.api.addClarification({
          spec_id: this.currentSpecId,
          req_id: this.editingReq ? this.editingReq.id : null,
          question: suggestions[selectedIdx],
          asked_by: 'Corporate AI Assistant',
          asked_role: 'Spec-Kit AI'
        });
        this.showToast('AI question added to Clarification Loop!', 'success');
        await this.refreshAllData();
      }
    } catch (err) {
      this.showToast(`AI query error: ${err.message}`, 'error');
    }
  }

  async aiDecomposeTasks(reqId) {
    const req = this.requirements.find(r => r.id === reqId);
    if (!req) return;

    this.showToast(`AI is decomposing tasks for ${reqId}...`, 'info');
    try {
      const res = await this.api.aiTasks({
        req_id: reqId,
        title: req.title,
        description: req.description
      });
      const generated = res.tasks || [];
      if (generated.length === 0) {
        this.showToast('AI returned no decomposed tasks.', 'info');
        return;
      }

      if (confirm(`AI decomposed ${generated.length} tasks for ${reqId}:\n\n` + generated.map(t => `• ${t.title} [${t.test_case_id || 'no test'}]`).join('\n') + `\n\nAutomatically create all these tasks in Spec-Kit?`)) {
        for (const t of generated) {
          await this.api.createTask({
            spec_id: this.currentSpecId,
            req_id: reqId,
            title: t.title,
            description: t.description,
            assignee: t.assignee || 'Dev Team',
            test_case_id: t.test_case_id || '',
            code_targets: t.code_targets || ''
          });
        }
        this.showToast(`Successfully created ${generated.length} tasks from AI!`, 'success');
        await this.refreshAllData();
      }
    } catch (err) {
      this.showToast(`AI Task decomposition failed: ${err.message}`, 'error');
    }
  }
}

/**
 * B2B-Harness Multi-Agent Pipeline Controller
 * Manages 7-stage state machine, interactive DAG progress ribbon, HITL gates, and artifact inspection.
 */
class PipelineController {
  constructor(ui) {
    this.ui = ui;
    this.api = ui.api;
    this.currentPipelineId = null;
    this.currentPipeline = null;
    this.activeSubtab = 'cockpit';

    this.stages = [
      { id: 'PRE_SDD', num: '1', title: 'PRE-SDD', art: 'discovery.md', desc: 'AST Vibe Discovery' },
      { id: 'SDD_INTENT', num: '2', title: 'SDD-INTENT', art: 'intent.md', desc: 'Goals & Constraints' },
      { id: 'SDD_SPEC', num: '3', title: 'SDD-SPEC', art: 'spec.md', desc: 'Immutable ASVS Spec' },
      { id: 'SDD_PLAN', num: '4', title: 'SDD-PLAN', art: 'plan.md', desc: 'Traceable Decomposition' },
      { id: 'SDD_DEV', num: '5', title: 'SDD-DEV', art: 'dev_log.md', desc: 'TDD Codegen & SAST' },
      { id: 'POST_SDD', num: '6', title: 'POST-SDD', art: 'plan_corrections.md', desc: 'Self-Healing Loop (Max 3)' },
      { id: 'AB_TEST', num: '7', title: 'A/B-TEST', art: 'test_log.md', desc: 'Equivalence & Seals' },
    ];
  }

  async init() {
    this.renderStageCards();
    await this.loadPipelines();
  }

  renderStageCards() {
    const track = document.getElementById('pipeline-stages-track');
    if (!track) return;

    track.innerHTML = '';
    const currentStage = this.currentPipeline ? this.currentPipeline.current_stage : '';
    const currentStatus = this.currentPipeline ? this.currentPipeline.status : '';

    this.stages.forEach((st, idx) => {
      const card = document.createElement('div');
      card.className = 'stage-step-card';
      card.id = `stage-card-${st.id}`;

      let badgeHtml = '<span class="badge" style="background:rgba(255,255,255,0.06); color:var(--text-dim);">PENDING</span>';
      
      const currentIdx = this.stages.findIndex(s => s.id === currentStage);
      if (currentIdx !== -1) {
        if (idx < currentIdx || (idx === currentIdx && currentStatus === 'COMPLETED')) {
          card.classList.add('completed');
          badgeHtml = '<span class="badge badge-green">COMPLETED ✓</span>';
        } else if (idx === currentIdx) {
          if (currentStatus === 'AWAITING_HUMAN') {
            card.classList.add('awaiting');
            badgeHtml = '<span class="badge" style="background:rgba(245,158,11,0.2); color:var(--amber);">AWAITING HITL ⚠️</span>';
          } else if (currentStatus === 'RUNNING') {
            card.classList.add('running');
            badgeHtml = '<span class="badge badge-blue">RUNNING ⚡</span>';
          } else {
            card.classList.add('active');
            badgeHtml = `<span class="badge badge-purple">${currentStatus}</span>`;
          }
        }
      }

      card.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <span style="font-weight:700; font-size:12px; color:#fff;">${st.num}. ${st.title}</span>
          ${badgeHtml}
        </div>
        <div style="font-size:11px; color:var(--text-muted); margin-top:2px;">${st.desc}</div>
        <div style="font-size:10px; color:var(--cyan); font-family:var(--font-mono); margin-top:4px;">📄 ${st.art}</div>
      `;

      card.addEventListener('click', () => {
        this.selectStage(st);
      });

      track.appendChild(card);
    });
  }

  selectStage(stage) {
    this.switchSubtab('artifacts');
    const select = document.getElementById('pipe-artifact-select');
    if (select) {
      select.value = stage.art;
      this.loadArtifact(stage.art);
    }
  }

  switchSubtab(subtabId) {
    this.activeSubtab = subtabId;
    document.querySelectorAll('.subtab-btn').forEach(btn => {
      btn.classList.toggle('active', btn.getAttribute('data-pipe-subtab') === subtabId);
    });
    document.querySelectorAll('.pipe-subtab-pane').forEach(pane => {
      pane.style.display = 'none';
    });
    const activePane = document.getElementById(`pipe-subtab-${subtabId}`);
    if (activePane) activePane.style.display = 'block';

    if (subtabId === 'artifacts') {
      const select = document.getElementById('pipe-artifact-select');
      if (select) this.loadArtifact(select.value);
    } else if (subtabId === 'a2a') {
      this.loadMessages();
    } else if (subtabId === 'snapshots') {
      this.renderSnapshots();
    }
  }

  async loadPipelines() {
    try {
      const pipelines = await this.api.getPipelines();
      const select = document.getElementById('pipe-select');
      if (select) {
        select.innerHTML = '<option value="">-- Выберите задачу / прогон --</option>';
        pipelines.forEach(p => {
          const opt = document.createElement('option');
          opt.value = p.pipeline_id;
          opt.textContent = `${p.pipeline_id} - ${p.project_name} [${p.current_stage}: ${p.status}]`;
          if (p.pipeline_id === this.currentPipelineId) opt.selected = true;
          select.appendChild(opt);
        });

        if (!this.currentPipelineId && pipelines.length > 0) {
          this.currentPipelineId = pipelines[0].pipeline_id;
          select.value = this.currentPipelineId;
          await this.loadCurrentPipelineState();
        } else if (this.currentPipelineId) {
          await this.loadCurrentPipelineState();
        }
      }
    } catch (err) {
      console.error('loadPipelines error:', err);
    }
  }

  async onSelect(pipeId) {
    this.currentPipelineId = pipeId;
    if (pipeId) {
      await this.loadCurrentPipelineState();
    } else {
      this.currentPipeline = null;
      this.updateControls();
      this.renderStageCards();
    }
  }

  async loadCurrentPipelineState() {
    if (!this.currentPipelineId) return;
    try {
      const state = await this.api.getPipelineState(this.currentPipelineId);
      this.currentPipeline = state;
      this.updateControls();
      this.renderStageCards();
      this.renderMetrics();
      this.checkHitlGate();
      if (this.activeSubtab === 'artifacts') {
        const select = document.getElementById('pipe-artifact-select');
        if (select) this.loadArtifact(select.value);
      } else if (this.activeSubtab === 'a2a') {
        this.loadMessages();
      } else if (this.activeSubtab === 'snapshots') {
        this.renderSnapshots();
      }
    } catch (err) {
      this.ui.showToast(`Ошибка загрузки состояния конвейера: ${err.message}`, 'error');
    }
  }

  updateControls() {
    const badge = document.getElementById('pipe-status-badge');
    const btnStep = document.getElementById('btn-pipe-step');
    const btnRun = document.getElementById('btn-pipe-run');

    if (!this.currentPipeline) {
      if (badge) {
        badge.textContent = 'НЕТ АКТИВНОГО ПРОГОНА';
        badge.className = 'badge badge-purple';
      }
      if (btnStep) btnStep.disabled = true;
      if (btnRun) btnRun.disabled = true;
      return;
    }

    const { status, current_stage } = this.currentPipeline;
    if (badge) {
      badge.textContent = `${current_stage} | ${status}`;
      badge.className = status === 'COMPLETED' ? 'badge badge-green' :
                        status === 'RUNNING' ? 'badge badge-blue' :
                        status === 'AWAITING_HUMAN' ? 'badge' : 'badge badge-purple';
      if (status === 'AWAITING_HUMAN') {
        badge.style.background = 'rgba(245, 158, 11, 0.2)';
        badge.style.color = 'var(--amber)';
      } else {
        badge.style.background = '';
        badge.style.color = '';
      }
    }

    const isIdle = status !== 'COMPLETED' && status !== 'FAILED' && status !== 'RUNNING';
    if (btnStep) btnStep.disabled = !isIdle;
    if (btnRun) btnRun.disabled = !isIdle || status === 'AWAITING_HUMAN';
  }

  renderMetrics() {
    const box = document.getElementById('pipe-details-box');
    if (!box || !this.currentPipeline) return;

    const p = this.currentPipeline;
    box.innerHTML = `
      <div style="display:grid; grid-template-columns:1fr 1fr; gap:10px;">
        <div style="background:rgba(0,0,0,0.25); padding:10px; border-radius:6px;">
          <span style="color:var(--text-dim); display:block; font-size:11px;">ID Конвейера:</span>
          <span style="font-family:var(--font-mono); color:var(--cyan); font-weight:700;">${p.pipeline_id}</span>
        </div>
        <div style="background:rgba(0,0,0,0.25); padding:10px; border-radius:6px;">
          <span style="color:var(--text-dim); display:block; font-size:11px;">Проект:</span>
          <span style="font-weight:600; color:#fff;">${this.ui._escape(p.project_name)}</span>
        </div>
      </div>

      <div style="display:grid; grid-template-columns:repeat(3, 1fr); gap:10px;">
        <div style="background:rgba(0,0,0,0.25); padding:10px; border-radius:6px;">
          <span style="color:var(--text-dim); display:block; font-size:11px;">Текущий этап:</span>
          <span style="font-weight:700; color:var(--purple);">${p.current_stage}</span>
        </div>
        <div style="background:rgba(0,0,0,0.25); padding:10px; border-radius:6px;">
          <span style="color:var(--text-dim); display:block; font-size:11px;">Итерация / Циклы:</span>
          <span style="font-weight:700; color:#fff;">Iter ${p.current_iteration} (Loop ${p.loop_count}/3)</span>
        </div>
        <div style="background:rgba(0,0,0,0.25); padding:10px; border-radius:6px;">
          <span style="color:var(--text-dim); display:block; font-size:11px;">A2A Сообщений:</span>
          <span style="font-weight:700; color:var(--green);">${p.messages_count || 0} конвертов</span>
        </div>
      </div>

      <div style="background:rgba(0,0,0,0.25); padding:10px; border-radius:6px;">
        <span style="color:var(--text-dim); display:block; font-size:11px;">Хранилище артефактов:</span>
        <span style="font-family:var(--font-mono); color:var(--text-muted); font-size:12px;">${this.ui._escape(p.storage_dir)}</span>
      </div>

      <div style="background:rgba(0,0,0,0.25); padding:10px; border-radius:6px;">
        <span style="color:var(--text-dim); display:block; font-size:11px;">Входное намерение (Intent / Vibe):</span>
        <div style="font-size:12px; color:#cbd5e1; margin-top:4px; max-height:100px; overflow-y:auto; white-space:pre-wrap;">${this.ui._escape(p.initial_idea || 'Авто-обнаружение из файлов')}</div>
      </div>
    `;
  }

  checkHitlGate() {
    const banner = document.getElementById('pipe-hitl-banner');
    if (!banner) return;

    if (this.currentPipeline && this.currentPipeline.status === 'AWAITING_HUMAN' && this.currentPipeline.pending_gate) {
      const gate = this.currentPipeline.pending_gate;
      const titleEl = document.getElementById('hitl-banner-title');
      const promptEl = document.getElementById('hitl-banner-prompt');
      if (titleEl) titleEl.textContent = `Требуется решение инженера (Gate: ${gate.gate_type} на ${gate.stage})`;
      if (promptEl) promptEl.textContent = gate.prompt || 'Требуется подтверждение для перехода на следующий этап.';
      banner.style.display = 'block';
    } else {
      banner.style.display = 'none';
    }
  }

  async onStartSubmit(e) {
    e.preventDefault();
    const name = document.getElementById('pipe-input-name').value;
    const path = document.getElementById('pipe-input-path').value;
    const idea = document.getElementById('pipe-input-idea').value;
    const hitl = document.getElementById('pipe-check-hitl').checked;

    try {
      this.ui.showToast('Инициализация конвейера B2B-Harness...', 'info');
      const res = await this.api.startPipeline({
        project_name: name,
        input_path: path,
        initial_idea: idea,
        require_hitl_intent: hitl
      });

      this.currentPipelineId = res.pipeline_id;
      this.currentPipeline = res.state;
      this.ui.showToast(`Конвейер ${res.pipeline_id} успешно создан!`, 'success');
      await this.loadPipelines();
    } catch (err) {
      this.ui.showToast(`Ошибка запуска: ${err.message}`, 'error');
    }
  }

  async step() {
    if (!this.currentPipelineId) return;
    try {
      this.ui.showToast('Выполнение шага конвейера...', 'info');
      const res = await this.api.stepPipeline(this.currentPipelineId);
      this.currentPipeline = res.state;
      this.updateControls();
      this.renderStageCards();
      this.renderMetrics();
      this.checkHitlGate();
      this.ui.showToast(`Шаг выполнен: ${res.result.stage || 'OK'} (${res.result.status})`, 'success');
    } catch (err) {
      this.ui.showToast(`Ошибка выполнения шага: ${err.message}`, 'error');
    }
  }

  async runAuto() {
    if (!this.currentPipelineId) return;
    try {
      this.ui.showToast('Запущен 1-Click Auto-Run конвейера...', 'info');
      const res = await this.api.runPipeline(this.currentPipelineId);
      this.currentPipeline = res.state;
      this.updateControls();
      this.renderStageCards();
      this.renderMetrics();
      this.checkHitlGate();
      this.ui.showToast(`Конвейер остановлен: статус ${res.state.status}`, res.state.status === 'COMPLETED' ? 'success' : 'info');
    } catch (err) {
      this.ui.showToast(`Ошибка авто-выполнения: ${err.message}`, 'error');
    }
  }

  async resolveGate(decision) {
    if (!this.currentPipelineId) return;
    const clarifications = document.getElementById('hitl-input-clarifications').value;
    try {
      this.ui.showToast('Отправка решения в HITL Gate...', 'info');
      const res = await this.api.resolvePipelineGate(this.currentPipelineId, {
        decision: decision,
        expert_name: 'Lead Architect',
        expert_role: 'Spec Auditor',
        rationale: 'Approved via Spec-Kit Cockpit',
        clarifications: clarifications
      });

      this.currentPipeline = res.state;
      this.updateControls();
      this.renderStageCards();
      this.renderMetrics();
      this.checkHitlGate();
      this.ui.showToast('HITL Gate утвержден, конвейер продолжен!', 'success');
    } catch (err) {
      this.ui.showToast(`Ошибка HITL: ${err.message}`, 'error');
    }
  }

  async loadArtifact(name) {
    if (!this.currentPipelineId || !name) return;
    const viewer = document.getElementById('pipe-artifact-viewer');
    if (!viewer) return;
    viewer.textContent = 'Загрузка содержимого артефакта...';
    try {
      const art = await this.api.getPipelineArtifact(this.currentPipelineId, name);
      viewer.textContent = art.content || 'Файл пуст или еще не сгенерирован.';
    } catch (err) {
      viewer.textContent = `Артефакт '${name}' еще не сгенерирован на текущем этапе конвейера.`;
    }
  }

  copyArtifact() {
    const viewer = document.getElementById('pipe-artifact-viewer');
    if (!viewer) return;
    navigator.clipboard.writeText(viewer.textContent)
      .then(() => this.ui.showToast('Артефакт скопирован в буфер обмена!', 'success'))
      .catch(() => this.ui.showToast('Не удалось скопировать', 'error'));
  }

  async loadMessages() {
    if (!this.currentPipelineId) return;
    const tbody = document.getElementById('pipe-messages-tbody');
    if (!tbody) return;
    try {
      const msgs = await this.api.getPipelineMessages(this.currentPipelineId);
      if (msgs.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: var(--text-dim); padding: 24px;">Нет сообщений</td></tr>';
        return;
      }
      tbody.innerHTML = '';
      msgs.forEach(m => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td style="font-family:var(--font-mono); font-size:11px; color:var(--cyan);">${this.ui._escape(m.trace_id)}</td>
          <td><span class="badge badge-purple">${this.ui._escape(m.step_id)}</span></td>
          <td>${m.iteration}</td>
          <td><b style="color:#fff;">${this.ui._escape(m.sender_role)}</b></td>
          <td>${this.ui._escape(m.recipient_role)}</td>
          <td><span class="badge ${m.status === 'APPROVED' ? 'badge-green' : 'badge-blue'}">${this.ui._escape(m.status)}</span></td>
          <td style="font-size:11px; color:var(--text-dim);">${this.ui._escape(m.timestamp)}</td>
        `;
        tbody.appendChild(tr);
      });
    } catch (err) {
      tbody.innerHTML = `<tr><td colspan="7" style="color:var(--rose); padding:16px;">Ошибка: ${err.message}</td></tr>`;
    }
  }

  renderSnapshots() {
    const tbody = document.getElementById('pipe-snapshots-tbody');
    if (!tbody || !this.currentPipeline) return;
    const snaps = this.currentPipeline.snapshots || [];
    if (snaps.length === 0) {
      tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: var(--text-dim); padding: 24px;">Нет снимков</td></tr>';
      return;
    }
    tbody.innerHTML = '';
    snaps.forEach(s => {
      const tr = document.createElement('tr');
      const inStr = JSON.stringify(s.input_artifacts || {});
      const outStr = JSON.stringify(s.output_artifacts || {});
      tr.innerHTML = `
        <td><span class="badge badge-purple">${this.ui._escape(s.stage)}</span></td>
        <td>${s.iteration}</td>
        <td><span class="badge ${s.status === 'COMPLETED' ? 'badge-green' : 'badge-blue'}">${this.ui._escape(s.status)}</span></td>
        <td style="font-family:var(--font-mono); font-size:11px; max-width:200px; overflow:hidden; text-overflow:ellipsis;">${this.ui._escape(inStr)}</td>
        <td style="font-family:var(--font-mono); font-size:11px; max-width:200px; overflow:hidden; text-overflow:ellipsis; color:var(--green);">${this.ui._escape(outStr)}</td>
        <td style="color:var(--rose);">${this.ui._escape(s.error_message || '-')}</td>
        <td style="font-size:11px; color:var(--text-dim);">${this.ui._escape(s.updated_at || s.created_at)}</td>
      `;
      tbody.appendChild(tr);
    });
  }

  showNewModal() {
    this.switchSubtab('cockpit');
    const inputName = document.getElementById('pipe-input-name');
    if (inputName) inputName.focus();
  }

  async refresh() {
    await this.loadPipelines();
    this.ui.showToast('Состояние конвейера обновлено', 'info');
  }
}

// Global initialization
window.speckitUI = new SpecKitUI();
document.addEventListener('DOMContentLoaded', () => {
  window.speckitUI.init();
});
