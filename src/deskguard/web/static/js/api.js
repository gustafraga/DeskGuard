// Cliente da API local do DeskGuard.
// Todas as operações que alteram estado enviam o token anti-CSRF emitido
// pela própria página, evitando que outra origem acione a API local.

const csrfMeta = document.querySelector('meta[name="deskguard-csrf"]');
const CSRF_TOKEN = csrfMeta ? csrfMeta.content : '';

function buildQuery(params) {
  if (!params) return '';
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') return;
    search.append(key, String(value));
  });
  const query = search.toString();
  return query ? `?${query}` : '';
}

async function request(path, options = {}) {
  const method = (options.method || 'GET').toUpperCase();
  const headers = { Accept: 'application/json', ...(options.headers || {}) };
  let body = options.body;

  if (method !== 'GET' && method !== 'HEAD') {
    headers['X-DeskGuard-CSRF'] = CSRF_TOKEN;
    if (body !== undefined && typeof body !== 'string') {
      headers['Content-Type'] = 'application/json';
      body = JSON.stringify(body);
    }
  }

  const response = await fetch(path, { ...options, method, headers, body });
  const contentType = response.headers.get('content-type') || '';
  let payload = null;
  if (contentType.includes('application/json')) {
    payload = await response.json();
  } else {
    payload = await response.text();
  }

  if (!response.ok) {
    const detail =
      payload && typeof payload === 'object' && payload.detail
        ? payload.detail
        : `Erro HTTP ${response.status}`;
    throw new Error(detail);
  }
  return payload;
}

export const api = {
  health: () => request('/api/health'),
  dashboard: () => request('/api/dashboard'),
  settings: () => request('/api/settings'),
  procedures: () => request('/api/procedures'),
  procedure: (id) => request(`/api/procedures/${encodeURIComponent(id)}`),
  executions: (params) => request(`/api/executions${buildQuery(params)}`),
  execution: (id) => request(`/api/executions/${encodeURIComponent(id)}`),
  run: (procedureId, params, mode, approved) =>
    request('/api/executions', {
      method: 'POST',
      body: {
        procedure_id: procedureId,
        params: params || {},
        mode: mode || 'live',
        approved: Boolean(approved),
      },
    }),
  report: (id) => request(`/api/executions/${encodeURIComponent(id)}/report`),
  audit: (params) => request(`/api/audit${buildQuery(params)}`),
};

// Exportação de relatório: precisa do corpo bruto para montar o download.
export async function exportReport(executionId, format, editedText) {
  const response = await fetch(
    `/api/executions/${encodeURIComponent(executionId)}/report/export`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-DeskGuard-CSRF': CSRF_TOKEN,
      },
      body: JSON.stringify({ format, edited_text: editedText || null }),
    },
  );
  if (!response.ok) {
    let detail = `Erro HTTP ${response.status}`;
    try {
      const payload = await response.json();
      detail = payload.detail || detail;
    } catch (error) {
      /* mantém a mensagem padrão */
    }
    throw new Error(detail);
  }
  const blob = await response.blob();
  const disposition = response.headers.get('content-disposition') || '';
  const match = disposition.match(/filename="([^"]+)"/);
  const filename = match ? match[1] : `deskguard-${executionId.slice(0, 8)}.${format === 'text' ? 'txt' : 'md'}`;
  return { blob, filename };
}

export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
