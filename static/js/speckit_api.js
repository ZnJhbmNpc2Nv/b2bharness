/**
 * Corporate Spec-Kit REST API Client
 * Zero external dependencies; uses native window.fetch with robust error handling.
 */
class SpecKitApi {
  constructor(baseUrl = '') {
    this.baseUrl = baseUrl.replace(/\/+$/, '');
  }

  async _request(endpoint, options = {}) {
    const url = `${this.baseUrl}${endpoint}`;
    const headers = {
      'Content-Type': 'application/json',
      ...(options.headers || {})
    };

    try {
      const response = await fetch(url, {
        ...options,
        headers
      });

      if (!response.ok) {
        let errDetails = `HTTP ${response.status} ${response.statusText}`;
        try {
          const errJson = await response.json();
          if (errJson && errJson.error) {
            errDetails = errJson.error;
          }
        } catch (_) {
          // Response body wasn't JSON
        }
        throw new Error(errDetails);
      }

      // Check if response is empty or non-JSON (e.g. file download)
      const contentType = response.headers.get('content-type') || '';
      if (contentType.includes('application/json')) {
        return await response.json();
      }
      return await response.text();
    } catch (err) {
      console.error(`[SpecKitApi Error] ${options.method || 'GET'} ${url}:`, err);
      throw err;
    }
  }

  /* ---------------- PROJECTS ---------------- */

  async getProjects() {
    const data = await this._request('/api/projects');
    return data.projects || [];
  }

  async getProject(id) {
    return await this._request(`/api/projects/${encodeURIComponent(id)}`);
  }

  async createProject(data) {
    return await this._request('/api/projects', {
      method: 'POST',
      body: JSON.stringify(data)
    });
  }

  /* ---------------- REQUIREMENTS ---------------- */

  async getRequirements(specId) {
    const query = specId ? `?spec_id=${encodeURIComponent(specId)}` : '';
    const data = await this._request(`/api/requirements${query}`);
    return data.requirements || [];
  }

  async getRequirement(id) {
    return await this._request(`/api/requirements/${encodeURIComponent(id)}`);
  }

  async createRequirement(data) {
    return await this._request('/api/requirements', {
      method: 'POST',
      body: JSON.stringify(data)
    });
  }

  async updateRequirement(id, data) {
    return await this._request(`/api/requirements/${encodeURIComponent(id)}`, {
      method: 'PUT',
      body: JSON.stringify(data)
    });
  }

  async getRevisions(id) {
    const data = await this._request(`/api/requirements/${encodeURIComponent(id)}/revisions`);
    return data.revisions || [];
  }

  /* ---------------- CLARIFICATIONS ---------------- */

  async getClarifications(specId) {
    const query = specId ? `?spec_id=${encodeURIComponent(specId)}` : '';
    const data = await this._request(`/api/clarifications${query}`);
    return data.clarifications || [];
  }

  async addClarification(data) {
    return await this._request('/api/clarifications', {
      method: 'POST',
      body: JSON.stringify(data)
    });
  }

  async resolveClarification(id, data) {
    return await this._request(`/api/clarifications/${encodeURIComponent(id)}/resolve`, {
      method: 'POST',
      body: JSON.stringify(data)
    });
  }

  /* ---------------- TASKS ---------------- */

  async getTasks(specId) {
    const query = specId ? `?spec_id=${encodeURIComponent(specId)}` : '';
    const data = await this._request(`/api/tasks${query}`);
    return data.tasks || [];
  }

  async createTask(data) {
    return await this._request('/api/tasks', {
      method: 'POST',
      body: JSON.stringify(data)
    });
  }

  async updateTaskStatus(id, status, actorName = 'Developer', actorRole = 'Dev') {
    return await this._request(`/api/tasks/${encodeURIComponent(id)}/status`, {
      method: 'POST',
      body: JSON.stringify({
        status,
        actor_name: actorName,
        actor_role: actorRole
      })
    });
  }

  /* ---------------- LINEAGE & DAG ---------------- */

  async getLineage(specId) {
    const query = specId ? `?spec_id=${encodeURIComponent(specId)}` : '';
    return await this._request(`/api/lineage${query}`);
  }

  async traceNode(specId, nodeId) {
    const query = `?spec_id=${encodeURIComponent(specId)}&node_id=${encodeURIComponent(nodeId)}`;
    return await this._request(`/api/lineage/trace${query}`);
  }

  /* ---------------- MATRIX (RTM) ---------------- */

  async getMatrix(specId) {
    const query = specId ? `?spec_id=${encodeURIComponent(specId)}` : '';
    return await this._request(`/api/matrix${query}`);
  }

  /* ---------------- AUDIT LEDGER ---------------- */

  async getAudit(specId) {
    const query = specId ? `?spec_id=${encodeURIComponent(specId)}` : '';
    const data = await this._request(`/api/audit${query}`);
    return data.audit_log || [];
  }

  /* ---------------- CORPORATE EXPORT ---------------- */

  async exportMarkdown(specId) {
    const query = specId ? `?spec_id=${encodeURIComponent(specId)}` : '';
    return await this._request(`/api/export/markdown${query}`);
  }

  getExportHtmlUrl(specId) {
    const query = specId ? `?spec_id=${encodeURIComponent(specId)}` : '';
    return `${this.baseUrl}/api/export/html${query}`;
  }

  /* ---------------- AI ASSISTANT & SETTINGS ---------------- */

  async aiClarify(data) {
    return await this._request('/api/ai/clarify', {
      method: 'POST',
      body: JSON.stringify(data)
    });
  }

  async aiTasks(data) {
    return await this._request('/api/ai/tasks', {
      method: 'POST',
      body: JSON.stringify(data)
    });
  }

  async getSettings() {
    return await this._request('/api/settings');
  }

  async saveSettings(data) {
    return await this._request('/api/settings', {
      method: 'POST',
      body: JSON.stringify(data)
    });
  }
}

// Global instance for browser usage
window.SpecKitApi = SpecKitApi;
window.speckitApi = new SpecKitApi();
