// Utilitários de interface: construção de elementos, rótulos de status e
// avisos temporários. Nenhum dado é interpretado como HTML vindo da API.

export function h(tag, attrs = {}, children = []) {
  const el = document.createElement(tag);
  Object.entries(attrs || {}).forEach(([key, value]) => {
    if (value === null || value === undefined || value === false) return;
    if (key === 'class') {
      el.className = value;
    } else if (key === 'text') {
      el.textContent = String(value);
    } else if (key === 'dataset') {
      Object.assign(el.dataset, value);
    } else if (key.startsWith('on') && typeof value === 'function') {
      el.addEventListener(key.slice(2).toLowerCase(), value);
    } else if (value === true) {
      el.setAttribute(key, '');
    } else {
      el.setAttribute(key, String(value));
    }
  });
  const list = Array.isArray(children) ? children : [children];
  list.forEach((child) => {
    if (child === null || child === undefined || child === false) return;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  });
  return el;
}

export function clear(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
}

export const STATUS_META = {
  pass: { label: 'Aprovado', tone: 'ok' },
  fail: { label: 'Falha confirmada', tone: 'fail' },
  warn: { label: 'Alerta', tone: 'warn' },
  inconclusive: { label: 'Inconclusivo', tone: 'unknown' },
  not_applicable: { label: 'Não aplicável', tone: 'muted' },
  skipped: { label: 'Ignorado', tone: 'muted' },
};

export const OUTCOME_META = {
  healthy: { label: 'Sem desvios', tone: 'ok' },
  issues_found: { label: 'Desvios confirmados', tone: 'fail' },
  inconclusive: { label: 'Inconclusivo', tone: 'unknown' },
  error: { label: 'Erro na execução', tone: 'fail' },
};

export const EXECUTION_STATUS_META = {
  queued: { label: 'Na fila', tone: 'muted' },
  running: { label: 'Em execução', tone: 'info' },
  completed: { label: 'Concluída', tone: 'ok' },
  failed: { label: 'Falhou', tone: 'fail' },
  cancelled: { label: 'Cancelada', tone: 'muted' },
};

export const SEVERITY_META = {
  info: { label: 'Informativo', tone: 'muted' },
  low: { label: 'Baixa', tone: 'info' },
  medium: { label: 'Média', tone: 'warn' },
  high: { label: 'Alta', tone: 'fail' },
  critical: { label: 'Crítica', tone: 'fail' },
};

export function statusBadge(status) {
  const meta = STATUS_META[status] || { label: status || '—', tone: 'muted' };
  return h('span', { class: `badge ${meta.tone}`, text: meta.label });
}

export function outcomeBadge(outcome) {
  const meta = OUTCOME_META[outcome] || { label: outcome || '—', tone: 'muted' };
  return h('span', { class: `badge ${meta.tone}`, text: meta.label });
}

export function executionStatusBadge(status) {
  const meta = EXECUTION_STATUS_META[status] || { label: status || '—', tone: 'muted' };
  return h('span', { class: `badge ${meta.tone}`, text: meta.label });
}

export function severityBadge(severity) {
  const meta = SEVERITY_META[severity] || { label: severity || '—', tone: 'muted' };
  return h('span', { class: `badge ${meta.tone}`, text: meta.label });
}

export function formatDateTime(iso) {
  if (!iso) return '—';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString('pt-BR');
}

export function formatDuration(ms) {
  if (ms === null || ms === undefined) return '—';
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
}

export function toast(message, tone = 'info') {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const element = h('div', { class: `toast ${tone === 'info' ? '' : tone}`.trim(), text: message });
  container.appendChild(element);
  window.setTimeout(() => element.remove(), 6000);
}

export function pageHeader(title, description, extra) {
  return h('div', { class: 'page-header' }, [
    h('h1', { text: title }),
    description ? h('p', { text: description }) : null,
    extra || null,
  ]);
}

export function emptyState(message) {
  return h('p', { class: 'empty', text: message });
}

export function card(title, children, headerExtra) {
  const body = [];
  if (title) {
    body.push(
      h('div', { class: 'card-header' }, [h('h2', { text: title }), headerExtra || null]),
    );
  }
  const list = Array.isArray(children) ? children : [children];
  return h('section', { class: 'card' }, body.concat(list));
}

export function definitionList(entries) {
  const nodes = [];
  entries.forEach(([term, value]) => {
    nodes.push(h('dt', { text: term }));
    nodes.push(h('dd', {}, value instanceof Node ? value : String(value ?? '—')));
  });
  return h('dl', { class: 'kv' }, nodes);
}

export function jsonBlock(value) {
  return h('pre', { class: 'evidence', text: JSON.stringify(value, null, 2) });
}

export async function copyToClipboard(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch (error) {
    const area = h('textarea', { text, style: 'position:fixed;left:-9999px;' });
    document.body.appendChild(area);
    area.select();
    const ok = document.execCommand('copy');
    area.remove();
    return ok;
  }
}
