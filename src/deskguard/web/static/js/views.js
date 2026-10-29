// Views da interface do DeskGuard.
// Cada view recebe o elemento raiz e desenha a sua tela.

import { api, downloadBlob, exportReport } from './api.js';
import {
  card,
  clear,
  copyToClipboard,
  definitionList,
  emptyState,
  executionStatusBadge,
  formatDateTime,
  formatDuration,
  h,
  jsonBlock,
  outcomeBadge,
  pageHeader,
  severityBadge,
  statusBadge,
  toast,
} from './ui.js';

// ---------------------------------------------------------------- utilidades
function procedureBadges(spec) {
  const badges = [];
  badges.push(
    spec.read_only
      ? h('span', { class: 'badge ok', text: 'Somente leitura' })
      : h('span', { class: 'badge fail', text: 'Altera o sistema' }),
  );
  badges.push(
    spec.privilege === 'elevated'
      ? h('span', { class: 'badge warn', text: 'Pode exigir elevação' })
      : h('span', { class: 'badge muted', text: 'Privilégio de usuário' }),
  );
  if (spec.source_mode === 'demo') {
    badges.push(h('span', { class: 'badge info', text: 'Demonstração' }));
  }
  return h('div', { class: 'proc-meta' }, badges);
}

function renderTechnicalTables(tables) {
  if (!tables || tables.length === 0) return null;
  return h(
    'div',
    { class: 'technical-view' },
    tables.map((table) =>
      h('div', { class: 'technical-table' }, [
        h('h4', { text: table.title }),
        h('div', { class: 'table-wrap' }, [
          h('table', {}, [
            h('thead', {}, h('tr', {}, table.columns.map((column) => h('th', { scope: 'col', text: column })))),
            h(
              'tbody',
              {},
              (table.rows || []).map((row) => h('tr', {}, row.map((cell) => h('td', { text: cell })))),
            ),
          ]),
        ]),
      ]),
    ),
  );
}

function rawDetails(evidence) {
  if (!evidence || !Object.keys(evidence).length) return null;
  return h('details', { class: 'accordion' }, [
    h('summary', { text: 'Dados Brutos (Dev)' }),
    jsonBlock(evidence),
  ]);
}

function renderStepResults(steps) {
  if (!steps || steps.length === 0) {
    return emptyState('Nenhuma verificação foi registrada nesta execução.');
  }
  return h(
    'div',
    {},
    steps.map((step) =>
      h('div', { class: 'result-block' }, [
        h('div', { class: 'result-head' }, [
          h('span', { class: 'result-title', text: step.title }),
          h('span', { class: 'badge-row' }, [
            statusBadge(step.status),
            step.severity && step.severity !== 'info' ? severityBadge(step.severity) : null,
            step.simulated ? h('span', { class: 'badge info', text: 'Simulado' }) : null,
          ]),
        ]),
        h('p', { class: 'result-message', text: step.message }),
        step.error_code
          ? h('p', { class: 'result-message' }, [
              h('code', { text: step.error_code }),
            ])
          : null,
        step.remediation
          ? h('p', { class: 'result-message' }, [h('strong', { text: 'Recomendação: ' }), step.remediation])
          : null,
        renderTechnicalTables(step.technical_sections),
        rawDetails(step.evidence),
      ]),
    ),
  );
}

async function waitForExecution(executionId, onUpdate) {
  let attempt = 0;
  for (;;) {
    const execution = await api.execution(executionId);
    if (onUpdate) onUpdate(execution);
    if (execution.status !== 'queued' && execution.status !== 'running') {
      return execution;
    }
    attempt += 1;
    if (attempt > 300) {
      throw new Error('Tempo esgotado aguardando a conclusão da execução.');
    }
    await new Promise((resolve) => window.setTimeout(resolve, 600));
  }
}

// ------------------------------------------------------------------- painel
function openKpiModal(title, contentElements) {
  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  const modal = document.createElement('div');
  modal.className = 'modal';
  
  const header = document.createElement('div');
  header.className = 'modal-header';
  header.innerHTML = `<h3>${title}</h3>`;
  const closeBtn = document.createElement('button');
  closeBtn.className = 'btn small ghost';
  closeBtn.textContent = '✕';
  closeBtn.onclick = () => document.body.removeChild(overlay);
  header.appendChild(closeBtn);
  
  const body = document.createElement('div');
  body.className = 'modal-body';
  contentElements.forEach(el => body.appendChild(el));
  
  const footer = document.createElement('div');
  footer.className = 'modal-footer';
  const okBtn = document.createElement('button');
  okBtn.className = 'btn primary small';
  okBtn.textContent = 'Fechar';
  okBtn.onclick = () => document.body.removeChild(overlay);
  footer.appendChild(okBtn);
  
  modal.appendChild(header);
  modal.appendChild(body);
  modal.appendChild(footer);
  overlay.appendChild(modal);
  document.body.appendChild(overlay);
  
  overlay.onclick = (e) => {
    if (e.target === overlay) document.body.removeChild(overlay);
  };
}

export async function renderDashboard(root) {
  clear(root);
  root.append(pageHeader('Painel de Controle', 'Monitoramento em tempo real de endpoints Windows e indicadores operacionais.'));

  let stats;
  let recentExecs;
  try {
    [stats, recentExecs] = await Promise.all([
      api.dashboard(),
      api.executions({ limit: 50 })
    ]);
  } catch (error) {
    root.append(emptyState(`Não foi possível carregar os indicadores: ${error.message}`));
    return;
  }

  const kpis = h('div', { class: 'kpi-grid' }, [
    kpi('Execuções registradas', stats.total_executions, 'Histórico completo local', '', async () => {
      const list = recentExecs.executions || [];
      const content = list.length ? h('div', { class: 'table-wrap' }, [
        h('table', {}, [
          h('thead', {}, h('tr', {}, [h('th', { text: 'Procedimento' }), h('th', { text: 'Data' }), h('th', { text: 'Status' })])),
          h('tbody', {}, list.map(ex => h('tr', {}, [
            h('td', {}, [h('a', { href: `#/history/${ex.id}`, text: ex.procedure_title, onclick: () => document.querySelector('.modal-overlay')?.remove() })]),
            h('td', { text: formatDateTime(ex.started_at) }),
            h('td', {}, outcomeBadge(ex.outcome))
          ])))
        ])
      ]) : emptyState('Nenhuma execução registrada.');
      openKpiModal('Todas as Execuções Registradas', [content]);
    }),
    kpi('Execuções em 24h', stats.executions_24h, 'Atividade recente', '', async () => {
      const now = Date.now();
      const recent24 = (recentExecs.executions || []).filter(ex => now - new Date(ex.started_at).getTime() < 86400000);
      const content = recent24.length ? h('div', { class: 'table-wrap' }, [
        h('table', {}, [
          h('thead', {}, h('tr', {}, [h('th', { text: 'Procedimento' }), h('th', { text: 'Data' }), h('th', { text: 'Resultado' })])),
          h('tbody', {}, recent24.map(ex => h('tr', {}, [
            h('td', {}, [h('a', { href: `#/history/${ex.id}`, text: ex.procedure_title, onclick: () => document.querySelector('.modal-overlay')?.remove() })]),
            h('td', { text: formatDateTime(ex.started_at) }),
            h('td', {}, outcomeBadge(ex.outcome))
          ])))
        ])
      ]) : emptyState('Nenhuma execução nas últimas 24 horas.');
      openKpiModal('Execuções nas Últimas 24h', [content]);
    }),
    kpi(
      'Desvios confirmados',
      stats.confirmed_issues,
      'Etapas com falha ou alerta',
      stats.confirmed_issues > 0 ? 'fail' : 'ok',
      async () => {
        const issues = (recentExecs.executions || []).filter(ex => ex.outcome === 'issues_found' || ex.outcome === 'error');
        const content = issues.length ? h('div', { class: 'table-wrap' }, [
          h('table', {}, [
            h('thead', {}, h('tr', {}, [h('th', { text: 'Procedimento' }), h('th', { text: 'Data' }), h('th', { text: 'Resumo' })])),
            h('tbody', {}, issues.map(ex => h('tr', {}, [
              h('td', {}, [h('a', { href: `#/history/${ex.id}`, text: ex.procedure_title, onclick: () => document.querySelector('.modal-overlay')?.remove() })]),
              h('td', { text: formatDateTime(ex.started_at) }),
              h('td', { text: ex.summary || 'Desvio identificado' })
            ])))
          ])
        ]) : emptyState('Nenhum desvio confirmado registrado.');
        openKpiModal('Desvios Confirmados Detalhados', [content]);
      }
    ),
    kpi(
      'Verificações inconclusivas',
      stats.inconclusive_checks,
      'Requerem nova coleta',
      stats.inconclusive_checks > 0 ? 'unknown' : 'ok',
      async () => {
        const inc = (recentExecs.executions || []).filter(ex => ex.outcome === 'inconclusive');
        const content = inc.length ? h('div', { class: 'table-wrap' }, [
          h('table', {}, [
            h('thead', {}, h('tr', {}, [h('th', { text: 'Procedimento' }), h('th', { text: 'Data' }), h('th', { text: 'Mensagem' })])),
            h('tbody', {}, inc.map(ex => h('tr', {}, [
              h('td', {}, [h('a', { href: `#/history/${ex.id}`, text: ex.procedure_title, onclick: () => document.querySelector('.modal-overlay')?.remove() })]),
              h('td', { text: formatDateTime(ex.started_at) }),
              h('td', { text: ex.summary || 'Inconclusivo' })
            ])))
          ])
        ]) : emptyState('Nenhuma verificação inconclusiva.');
        openKpiModal('Verificações Inconclusivas Detalhadas', [content]);
      }
    ),
  ]);
  root.append(kpis);

  // Seção de Gráficos com Chart.js (Rosca e Linha)
  const chartGrid = h('div', { class: 'dashboard-grid-charts' }, [
    h('div', { class: 'chart-card' }, [
      h('h3', { text: 'Desvios Confirmados por Severidade' }),
      h('div', { class: 'chart-container' }, [h('canvas', { id: 'severityChart' })])
    ]),
    h('div', { class: 'chart-card' }, [
      h('h3', { text: 'Execuções Recentes (Tendência)' }),
      h('div', { class: 'chart-container' }, [h('canvas', { id: 'trendChart' })])
    ])
  ]);
  root.append(chartGrid);

  // Inicializar Gráficos Chart.js após o elemento estar no DOM
  setTimeout(() => {
    try {
      const sevCtx = document.getElementById('severityChart')?.getContext('2d');
      if (sevCtx) {
        const sevData = stats.by_severity || { info: 0, warn: 0, fail: 0 };
        new Chart(sevCtx, {
          type: 'doughnut',
          data: {
            labels: Object.keys(sevData),
            datasets: [{
              data: Object.values(sevData),
              backgroundColor: ['#22d3ee', '#fbbf24', '#f87171', '#c084fc'],
              borderWidth: 0
            }]
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: { position: 'bottom', labels: { color: '#9ca3af', font: { family: 'Inter', size: 12 } } }
            }
          }
        });
      }

      const trendCtx = document.getElementById('trendChart')?.getContext('2d');
      if (trendCtx) {
        // Agrupar execuções por dia recente
        const countsByDay = {};
        (recentExecs.executions || []).forEach(ex => {
          const day = (ex.started_at || '').split('T')[0];
          if (day) countsByDay[day] = (countsByDay[day] || 0) + 1;
        });
        const days = Object.keys(countsByDay).sort().slice(-7);
        const counts = days.map(d => countsByDay[d]);

        new Chart(trendCtx, {
          type: 'line',
          data: {
            labels: days.length ? days : ['Hoje'],
            datasets: [{
              label: 'Execuções',
              data: counts.length ? counts : [stats.total_executions || 0],
              borderColor: '#22d3ee',
              backgroundColor: 'rgba(34, 211, 238, 0.1)',
              fill: true,
              tension: 0.3
            }]
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: { display: false }
            },
            scales: {
              x: { ticks: { color: '#9ca3af' }, grid: { color: '#1f2937' } },
              y: { ticks: { color: '#9ca3af' }, grid: { color: '#1f2937' } }
            }
          }
        });
      }
    } catch (err) {
      console.error('Erro ao renderizar gráficos:', err);
    }
  }, 50);

  // Criar cards de AD com skeleton loader imediato para performance de inicialização
  const accountCardContainer = card('Minha Conta', h('div', { class: 'skeleton', style: 'height: 120px;' }, [h('p', { text: 'Carregando conta...' })]));
  const trustCardContainer = card('Confiança do Domínio', h('div', { class: 'skeleton', style: 'height: 120px;' }, [h('p', { text: 'Carregando confiança...' })]));

  root.append(
    h('div', { class: 'detail-grid' }, [
      accountCardContainer,
      trustCardContainer,
    ]),
  );

  // Carregar AD em segundo plano (assíncrono) para o painel abrir instantaneamente
  (async () => {
    let selfStatus = null;
    let selfStatusError = null;
    try {
      selfStatus = await api.adSelfStatus();
    } catch (error) {
      selfStatusError = error.message;
    }
    accountCardContainer.replaceWith(card('Minha Conta', renderSelfAccount(selfStatus, selfStatusError)));
    trustCardContainer.replaceWith(card('Confiança do Domínio', renderDomainTrust(selfStatus, selfStatusError)));
  })();

  const bySeverity = Object.entries(stats.by_severity || {});
  const severityRows = bySeverity.length
    ? h('table', {}, [
        h('caption', { text: 'Severidade dos desvios confirmados' }),
        h('thead', {}, h('tr', {}, [h('th', { scope: 'col', text: 'Severidade' }), h('th', { scope: 'col', text: 'Ocorrências' })])),
        h(
          'tbody',
          {},
          bySeverity.map(([severity, count]) =>
            h('tr', {}, [h('td', {}, severityBadge(severity)), h('td', { text: String(count) })]),
          ),
        ),
      ])
    : emptyState('Nenhum desvio confirmado registrado até o momento.');

  const procRows = (stats.by_procedure || []).length
    ? h('table', {}, [
        h('caption', { text: 'Procedimentos executados' }),
        h('thead', {}, h('tr', {}, [h('th', { scope: 'col', text: 'Procedimento' }), h('th', { scope: 'col', text: 'Execuções' })])),
        h(
          'tbody',
          {},
          stats.by_procedure.map((item) =>
            h('tr', {}, [
              h('td', { text: item.title || item.procedure_id }),
              h('td', { text: String(item.executions) }),
            ]),
          ),
        ),
      ])
    : emptyState('Nenhuma execução registrada até o momento.');

  root.append(
    h('div', { class: 'detail-grid' }, [
      card('Desvios por severidade', severityRows),
      card('Procedimentos executados', procRows),
    ]),
  );

  const recentTable = (recentExecs.executions || []).length
    ? h('div', { class: 'table-wrap' }, [
        h('table', {}, [
          h('caption', { text: 'Últimas execuções' }),
          h('thead', {}, h('tr', {}, [
            h('th', { scope: 'col', text: 'Procedimento' }),
            h('th', { scope: 'col', text: 'Início' }),
            h('th', { scope: 'col', text: 'Duração' }),
            h('th', { scope: 'col', text: 'Resultado' }),
            h('th', { scope: 'col', text: 'Origem' }),
          ])),
          h(
            'tbody',
            {},
            (recentExecs.executions || []).slice(0, 8).map((execution) =>
              h('tr', {}, [
                h('td', {}, [
                  h('a', { href: `#/history/${execution.id}`, text: execution.procedure_title }),
                ]),
                h('td', { text: formatDateTime(execution.started_at) }),
                h('td', { text: formatDuration(execution.duration_ms) }),
                h('td', {}, outcomeBadge(execution.outcome)),
                h('td', { text: execution.mode === 'demo' ? 'Simulado' : 'Real' }),
              ]),
            ),
          ),
        ]),
      ])
    : emptyState('Nenhuma execução registrada até o momento.');

  root.append(card('Últimas execuções', recentTable));
}

function kpi(label, value, hint, tone, onClick) {
  const el = h('div', { class: `kpi${tone ? ` is-${tone}` : ''}` }, [
    h('div', { class: 'kpi-label', text: label }),
    h('div', { class: 'kpi-value', text: String(value ?? 0) }),
    hint ? h('div', { class: 'kpi-hint', text: hint }) : null,
  ]);
  if (onClick) {
    el.style.cursor = 'pointer';
    el.onclick = onClick;
  }
  return el;
}

function adStatusTone(status) {
  if (status === 'pass') return 'ok';
  if (status === 'warn') return 'warn';
  if (status === 'fail') return 'fail';
  return 'unknown';
}

function renderSelfAccount(selfStatus, error) {
  if (error) {
    return h('div', {}, [
      h('p', { class: 'result-message', text: `Não foi possível carregar o diagnóstico AD: ${error}` }),
      h('p', { class: 'badge warn', text: 'Módulo RSAT ActiveDirectory ausente ou tempo limite esgotado.' })
    ]);
  }
  if (!selfStatus) {
    return h('div', {}, [
      h('p', { class: 'loading', text: 'Carregando diagnóstico da conta...' }),
      h('p', { class: 'badge muted', text: 'Se demorar mais de 5 segundos, a consulta será abortada.' })
    ]);
  }
  const account = selfStatus.account || {};
  const username = account.username || selfStatus.username || '—';
  const domain = account.user_domain || '—';
  const enabled = account.enabled === true ? 'Ativa' : account.enabled === false ? 'Desabilitada' : 'Não verificado';
  const locked = account.locked_out === true ? 'Bloqueada' : account.locked_out === false ? 'Desbloqueada' : 'Não verificado';
  const password = account.password_expired === true ? 'Expirada' : account.password_expired === false ? 'Válida' : 'Não verificado';
  let expiration = 'Sem expiração definida';
  if (account.account_expiration_date) {
    expiration = account.account_expiration_date;
    if (account.days_until_expiration !== null && account.days_until_expiration !== undefined) {
      expiration = `${account.account_expiration_date} (${account.days_until_expiration} dia(s) para expirar)`;
    }
    if (account.days_until_expiration !== null && account.days_until_expiration < 0) {
      expiration = `${account.account_expiration_date} (expirada)`;
    }
  }
  return definitionList([
    ['Usuário', username],
    ['Domínio', domain],
    ['Status', h('span', { class: `badge ${adStatusTone(account.status)}`, text: enabled })],
    ['Bloqueio', locked],
    ['Senha', password],
    ['Expiração da conta', expiration],
    ['Último logon', account.last_logon_date || '—'],
    ['Mensagem', account.message || '—'],
  ]);
}

function renderDomainTrust(selfStatus, error) {
  if (error) {
    return h('div', {}, [
      h('p', { class: 'result-message', text: `Não foi possível carregar o diagnóstico AD: ${error}` }),
      h('p', { class: 'badge warn', text: 'Verificação de confiança ignorada por falha ou timeout.' })
    ]);
  }
  if (!selfStatus) {
    return h('div', {}, [
      h('p', { class: 'loading', text: 'Carregando confiança do domínio...' }),
      h('p', { class: 'badge muted', text: 'Aguardando resposta da API (máximo 5s)...' })
    ]);
  }
  const trust = selfStatus.domain_trust || {};
  let label = 'Não verificado';
  if (trust.status === 'pass') label = 'OK';
  else if (trust.status === 'warn') label = 'Alerta';
  else if (trust.status === 'fail') label = 'Falha';
  else if (trust.status === 'inconclusive') label = 'Inconclusivo';
  return definitionList([
    ['Situação', h('span', { class: `badge ${adStatusTone(trust.status)}`, text: label })],
    ['Domínio verificado', trust.domain || '—'],
    ['Test-ComputerSecureChannel', trust.ok === true ? 'True' : trust.ok === false ? 'False' : '—'],
    ['Mensagem', trust.message || '—'],
    ['Reparo', trust.status === 'warn' ? 'Exige privilégios de administrador' : '—'],
  ]);
}

// ----------------------------------------------------------------- catálogo
export async function renderCatalog(root) {
  clear(root);
  root.append(pageHeader('Catálogo de procedimentos', 'Cada procedimento declara o que verifica, o que exige e o que pode alterar.'));

  let data;
  try {
    data = await api.procedures();
  } catch (error) {
    root.append(emptyState(`Não foi possível carregar o catálogo: ${error.message}`));
    return;
  }

  let activeCategory = 'all';
  let search = '';

  const grid = h('div', { class: 'proc-grid' });
  const filters = h('div', { class: 'category-filters' });

  function applyFilters() {
    const normalized = search.trim().toLowerCase();
    const visible = data.procedures.filter((spec) => {
      const categoryOk = activeCategory === 'all' || spec.category === activeCategory;
      const textOk =
        !normalized ||
        spec.title.toLowerCase().includes(normalized) ||
        spec.summary.toLowerCase().includes(normalized) ||
        spec.tags.some((tag) => tag.toLowerCase().includes(normalized));
      return categoryOk && textOk;
    });

    clear(grid);
    if (!visible.length) {
      grid.append(emptyState('Nenhum procedimento corresponde aos filtros aplicados.'));
      return;
    }
    visible.forEach((spec) => {
      grid.append(
        h('article', { class: 'proc-card' }, [
          h('h3', { text: spec.title }),
          h('p', { class: 'proc-summary', text: spec.summary }),
          procedureBadges(spec),
          h('div', { class: 'proc-footer' }, [
            h('span', { text: `${spec.steps.length} verificação(ões)` }),
            h('a', { class: 'btn', href: `#/catalog/${encodeURIComponent(spec.id)}`, text: 'Abrir' }),
          ]),
        ]),
      );
    });
  }

  const categoryNames = ['all'].concat(data.categories.map((category) => category.id));
  categoryNames.forEach((categoryId) => {
    const label =
      categoryId === 'all'
        ? 'Todas'
        : (data.categories.find((item) => item.id === categoryId) || {}).label || categoryId;
    const button = h('button', {
      class: 'chip',
      type: 'button',
      'aria-pressed': categoryId === activeCategory ? 'true' : 'false',
      text: label,
      onclick: () => {
        activeCategory = categoryId;
        filters.querySelectorAll('.chip').forEach((chip) => chip.setAttribute('aria-pressed', 'false'));
        button.setAttribute('aria-pressed', 'true');
        applyFilters();
      },
    });
    filters.append(button);
  });

  const searchInput = h('input', {
    type: 'search',
    placeholder: 'Buscar por nome, descrição ou etiqueta',
    'aria-label': 'Buscar procedimentos',
    oninput: (event) => {
      search = event.target.value;
      applyFilters();
    },
  });

  root.append(h('div', { class: 'toolbar' }, [searchInput]));
  root.append(filters);
  root.append(grid);
  applyFilters();
}

// ------------------------------------------------------- detalhe do procedimento
export async function renderProcedureDetail(root, procedureId) {
  clear(root);
  root.append(pageHeader('Carregando procedimento…', ''));

  let spec;
  try {
    spec = await api.procedure(procedureId);
  } catch (error) {
    clear(root);
    root.append(pageHeader('Procedimento não encontrado', error.message));
    return;
  }

  clear(root);
  root.append(
    h('div', { class: 'breadcrumb' }, [
      h('a', { href: '#/catalog', text: 'Catálogo' }),
      ' / ',
      spec.title,
    ]),
  );
  root.append(pageHeader(spec.title, spec.summary));
  root.append(
    h('div', { class: 'proc-meta', style: 'margin-bottom:16px' }, [
      procedureBadges(spec),
      h('span', { class: 'badge muted', text: spec.category }),
      h('span', { class: 'badge muted', text: `v${spec.version}` }),
    ]),
  );

  const paramsForm = h('div', {});
  spec.params.forEach((param) => {
    let input;
    if (param.type === 'boolean') {
      input = h('input', { type: 'checkbox', id: `param-${param.name}` });
      if (param.default) input.checked = true;
      paramsForm.append(
        h('div', { class: 'field check-field' }, [
          input,
          h('div', {}, [
            h('label', { for: `param-${param.name}`, text: param.label }),
            param.help_text ? h('small', { text: param.help_text }) : null,
          ]),
        ]),
      );
      return;
    }
    if (param.type === 'enum') {
      input = h(
        'select',
        { id: `param-${param.name}` },
        param.choices.map((choice) => h('option', { value: choice, text: choice })),
      );
    } else {
      input = h('input', { type: 'text', id: `param-${param.name}`, value: param.default ?? '' });
    }
    paramsForm.append(
      h('div', { class: 'field' }, [
        h('label', { for: `param-${param.name}`, text: param.label }),
        input,
        param.help_text ? h('small', { text: param.help_text }) : null,
      ]),
    );
  });
  if (!spec.params.length) {
    paramsForm.append(h('p', { class: 'loading', text: 'Este procedimento não recebe parâmetros.' }));
  }

  const resultsContainer = h('div', { id: 'exec-results' });

  function collectParams() {
    const values = {};
    spec.params.forEach((param) => {
      const element = document.getElementById(`param-${param.name}`);
      if (!element) return;
      if (param.type === 'boolean') {
        values[param.name] = element.checked;
      } else if (param.type === 'integer') {
        values[param.name] = element.value === '' ? null : Number(element.value);
      } else {
        values[param.name] = element.value;
      }
    });
    return values;
  }

  async function execute(mode) {
    clear(resultsContainer);
    resultsContainer.append(h('p', { class: 'loading', text: 'Executando coleta…' }));
    runButton.disabled = true;
    demoButton.disabled = true;
    try {
      const accepted = await api.run(spec.id, collectParams(), mode, false);
      const execution = await waitForExecution(accepted.execution_id);
      clear(resultsContainer);
      resultsContainer.append(
        card('Resultado da execução', [
          h('div', { class: 'badge-row', style: 'margin-bottom:10px' }, [
            executionStatusBadge(execution.status),
            outcomeBadge(execution.outcome),
            execution.mode === 'demo'
              ? h('span', { class: 'badge info', text: 'Dados simulados' })
              : h('span', { class: 'badge muted', text: 'Dados reais' }),
          ]),
          h('p', { class: 'loading', text: execution.summary || '' }),
          renderStepResults(execution.steps),
          h('div', { class: 'report-actions' }, [
            h('button', {
              class: 'primary',
              type: 'button',
              text: 'Gerar relatório técnico',
              onclick: () => {
                window.location.hash = `#/report/${execution.id}`;
              },
            }),
          ]),
        ]),
      );
      toast('Execução concluída.', 'success');
    } catch (error) {
      clear(resultsContainer);
      resultsContainer.append(emptyState(`Falha ao executar: ${error.message}`));
      toast(`Falha ao executar: ${error.message}`, 'error');
    } finally {
      runButton.disabled = false;
      demoButton.disabled = false;
    }
  }

  const runButton = h('button', {
    class: 'primary',
    type: 'button',
    text: 'Executar verificação',
    onclick: () => execute('live'),
  });
  const demoButton = h('button', {
    type: 'button',
    text: 'Executar em modo demonstração',
    onclick: () => execute('demo'),
  });

  root.append(
    h('div', { class: 'detail-grid' }, [
      h('div', {}, [
        card('Descrição', h('p', { text: spec.description })),
        card(
          'Verificações realizadas',
          h(
            'ol',
            { class: 'steps-list' },
            spec.steps.map((step) =>
              h('li', {}, [
                h('div', {}, [
                  h('div', { class: 'step-title', text: step.title }),
                  h('div', { class: 'step-desc', text: step.description }),
                ]),
              ]),
            ),
          ),
        ),
        card('Parâmetros', paramsForm),
        card('Executar', [h('div', { class: 'report-actions' }, [runButton, demoButton])]),
        resultsContainer,
      ]),
      h('div', {}, [
        card('Pré-requisitos', h('ul', { class: 'detail-list' }, spec.prerequisites.map((item) => h('li', { text: item })))),
        card('Observações de risco', h('ul', { class: 'detail-list' }, spec.risk_notes.map((item) => h('li', { text: item })))),
        card('Resultados esperados', h('ul', { class: 'detail-list' }, spec.expected_outcomes.map((item) => h('li', { text: item })))),
        card('Metadados', definitionList([
          ['Identificador', h('code', { text: spec.id })],
          ['Versão', spec.version],
          ['Categoria', spec.category],
          ['Capacidade', spec.capability === 'read_only' ? 'Somente leitura' : 'Altera o sistema'],
          ['Privilégio', spec.privilege === 'elevated' ? 'Pode exigir elevação' : 'Usuário padrão'],
        ])),
      ]),
    ]),
  );
}

// ------------------------------------------------------------------ histórico
export async function renderHistory(root) {
  clear(root);
  root.append(pageHeader('Histórico de execuções', 'Busca por procedimento, identificador ou resumo do resultado.'));

  const tableContainer = h('div', {});
  const state = { query: '', status: '', outcome: '', mode: '' };

  async function refresh() {
    clear(tableContainer);
    tableContainer.append(h('p', { class: 'loading', text: 'Carregando execuções…' }));
    let data;
    try {
      data = await api.executions({
        query: state.query,
        status: state.status,
        outcome: state.outcome,
        mode: state.mode,
        limit: 100,
      });
    } catch (error) {
      clear(tableContainer);
      tableContainer.append(emptyState(`Não foi possível carregar o histórico: ${error.message}`));
      return;
    }
    clear(tableContainer);
    if (!data.executions.length) {
      tableContainer.append(emptyState('Nenhuma execução encontrada com os filtros aplicados.'));
      return;
    }
    tableContainer.append(
      h('div', { class: 'table-wrap' }, [
        h('table', {}, [
          h('caption', { text: `${data.total} execução(ões) encontrada(s)` }),
          h('thead', {}, h('tr', {}, [
            h('th', { scope: 'col', text: 'Procedimento' }),
            h('th', { scope: 'col', text: 'Início' }),
            h('th', { scope: 'col', text: 'Duração' }),
            h('th', { scope: 'col', text: 'Situação' }),
            h('th', { scope: 'col', text: 'Resultado' }),
            h('th', { scope: 'col', text: 'Origem' }),
            h('th', { scope: 'col', text: 'Ações' }),
          ])),
          h(
            'tbody',
            {},
            data.executions.map((execution) =>
              h('tr', {}, [
                h('td', { text: execution.procedure_title }),
                h('td', { text: formatDateTime(execution.started_at) }),
                h('td', { text: formatDuration(execution.duration_ms) }),
                h('td', {}, executionStatusBadge(execution.status)),
                h('td', {}, outcomeBadge(execution.outcome)),
                h('td', { text: execution.mode === 'demo' ? 'Simulado' : 'Real' }),
                h('td', {}, [
                  h('a', { class: 'btn small', href: `#/history/${execution.id}`, text: 'Detalhe' }),
                  ' ',
                  h('a', { class: 'btn small', href: `#/report/${execution.id}`, text: 'Relatório' }),
                ]),
              ]),
            ),
          ),
        ]),
      ]),
    );
  }

  const searchInput = h('input', {
    type: 'search',
    placeholder: 'Buscar por procedimento, resumo ou ID',
    'aria-label': 'Buscar no histórico',
    oninput: (event) => {
      state.query = event.target.value;
      window.clearTimeout(searchInput._timer);
      searchInput._timer = window.setTimeout(refresh, 250);
    },
  });

  const statusFilter = h(
    'select',
    {
      'aria-label': 'Filtrar por situação',
      style: 'max-width:200px',
      onchange: (event) => {
        state.status = event.target.value;
        refresh();
      },
    },
    [
      h('option', { value: '', text: 'Todas as situações' }),
      h('option', { value: 'completed', text: 'Concluídas' }),
      h('option', { value: 'failed', text: 'Com falha' }),
      h('option', { value: 'running', text: 'Em execução' }),
    ],
  );

  const outcomeFilter = h(
    'select',
    {
      'aria-label': 'Filtrar por resultado',
      style: 'max-width:200px',
      onchange: (event) => {
        state.outcome = event.target.value;
        refresh();
      },
    },
    [
      h('option', { value: '', text: 'Todos os resultados' }),
      h('option', { value: 'healthy', text: 'Sem desvios' }),
      h('option', { value: 'issues_found', text: 'Desvios confirmados' }),
      h('option', { value: 'inconclusive', text: 'Inconclusivas' }),
      h('option', { value: 'error', text: 'Erro na execução' }),
    ],
  );

  const modeFilter = h(
    'select',
    {
      'aria-label': 'Filtrar por origem dos dados',
      style: 'max-width:220px',
      onchange: (event) => {
        state.mode = event.target.value;
        refresh();
      },
    },
    [
      h('option', { value: '', text: 'Todas as origens' }),
      h('option', { value: 'live', text: 'Dados reais' }),
      h('option', { value: 'demo', text: 'Dados simulados' }),
    ],
  );

  root.append(h('div', { class: 'toolbar' }, [searchInput, statusFilter, outcomeFilter, modeFilter]));
  root.append(tableContainer);
  await refresh();
}

// ------------------------------------------------------------ detalhe da execução
export async function renderExecutionDetail(root, executionId) {
  clear(root);
  root.append(pageHeader('Carregando execução…', ''));

  let execution;
  try {
    execution = await api.execution(executionId);
  } catch (error) {
    clear(root);
    root.append(pageHeader('Execução não encontrada', error.message));
    return;
  }

  clear(root);
  root.append(
    h('div', { class: 'breadcrumb' }, [h('a', { href: '#/history', text: 'Histórico' }), ' / ', execution.procedure_title]),
  );
  root.append(pageHeader(execution.procedure_title, execution.summary || ''));

  root.append(
    card('Execução', [
      h('div', { class: 'badge-row', style: 'margin-bottom:12px' }, [
        executionStatusBadge(execution.status),
        outcomeBadge(execution.outcome),
        execution.mode === 'demo'
          ? h('span', { class: 'badge info', text: 'Dados simulados' })
          : h('span', { class: 'badge muted', text: 'Dados reais' }),
      ]),
      definitionList([
        ['Identificador', h('code', { text: execution.id })],
        ['Procedimento', h('code', { text: `${execution.procedure_id} v${execution.procedure_version}` })],
        ['Início', formatDateTime(execution.started_at)],
        ['Término', formatDateTime(execution.finished_at)],
        ['Duração', formatDuration(execution.duration_ms)],
        ['Executado por', execution.actor],
        ['Versão da ferramenta', execution.tool_version],
        ['Confirmação concedida', execution.approval_granted ? 'Sim' : 'Não'],
        execution.error ? ['Erro', execution.error] : null,
      ].filter(Boolean)),
      h('div', { class: 'report-actions', style: 'margin-top:14px' }, [
        h('a', { class: 'primary btn', href: `#/report/${execution.id}`, text: 'Gerar relatório técnico' }),
      ]),
    ]),
  );

  root.append(card('Verificações realizadas', renderStepResults(execution.steps)));
}

// ------------------------------------------------------------------ relatório
export async function renderReport(root, executionId) {
  clear(root);
  root.append(pageHeader('Carregando relatório…', ''));

  let report;
  try {
    report = await api.report(executionId);
  } catch (error) {
    clear(root);
    root.append(pageHeader('Relatório indisponível', error.message));
    return;
  }

  clear(root);
  root.append(
    h('div', { class: 'breadcrumb' }, [h('a', { href: `#/history/${executionId}`, text: 'Voltar à execução' })]),
  );
  root.append(
    pageHeader(
      'Relatório técnico',
      'Resumo para o chamado e visão técnica em tabelas. O JSON bruto fica recolhido em Dados Brutos (Dev).',
    ),
  );

  const presentation = report.presentation || { summary: {}, sections: [] };
  const summary = presentation.summary || {};
  const counts = summary.counts || {};

  root.append(
    card('Resumo (N1)', [
      h('div', { class: 'badge-row', style: 'margin-bottom:10px' }, [
        outcomeBadge(summary.outcome),
        summary.mode === 'demo'
          ? h('span', { class: 'badge info', text: 'Dados simulados' })
          : h('span', { class: 'badge muted', text: 'Dados reais' }),
      ]),
      h('p', { class: 'report-summary', text: summary.text || 'Resumo não disponível.' }),
      h('p', {
        class: 'report-counts',
        text: `${counts.total || 0} verificação(ões): ${counts.passed || 0} aprovada(s), ${counts.confirmed || 0} desvio(s) confirmado(s), ${counts.inconclusive || 0} inconclusiva(s).`,
      }),
    ]),
  );

  const sections = presentation.sections || [];
  const technicalContent = sections.length
    ? h(
        'div',
        { class: 'report-sections' },
        sections.map((section) =>
          h('section', { class: 'report-section' }, [
            h('h3', { text: section.title }),
            h('div', { class: 'badge-row' }, [
              statusBadge(section.status),
              section.severity && section.severity !== 'info' ? severityBadge(section.severity) : null,
            ]),
            h('p', { class: 'report-message', text: section.message || '' }),
            section.remediation
              ? h('p', { class: 'report-message' }, [h('strong', { text: 'Recomendação: ' }), section.remediation])
              : null,
            renderTechnicalTables(section.tables),
            rawDetails(section.raw_evidence),
          ]),
        ),
      )
    : emptyState('Nenhum resultado observado.');

  root.append(card('Visão técnica (N2/N3)', technicalContent));

  const copyMarkdown = report.copy_markdown || report.markdown || '';
  const textarea = h('textarea', {
    id: 'report-content',
    rows: 26,
    'aria-label': 'Conteúdo editável do relatório técnico (sem dados brutos)',
  });
  textarea.value = copyMarkdown;

  async function download(format) {
    try {
      const edited = textarea.value !== copyMarkdown;
      const { blob, filename } = await exportReport(executionId, format, edited ? textarea.value : null);
      downloadBlob(blob, filename);
      toast('Relatório exportado.', 'success');
    } catch (error) {
      toast(`Não foi possível exportar o relatório: ${error.message}`, 'error');
    }
  }

  root.append(
    card('Ações e edição', [
      h('div', { class: 'report-actions' }, [
        h('button', {
          class: 'primary',
          type: 'button',
          text: 'Copiar relatório',
          onclick: async () => {
            const ok = await copyToClipboard(textarea.value);
            toast(ok ? 'Resumo e tabelas copiados para a área de transferência.' : 'Não foi possível copiar.', ok ? 'success' : 'error');
          },
        }),
        h('button', { type: 'button', text: 'Baixar .md', onclick: () => download('markdown') }),
        h('button', { type: 'button', text: 'Baixar .txt', onclick: () => download('text') }),
      ]),
      h('details', { class: 'accordion' }, [
        h('summary', { text: 'Editar relatório (Markdown, sem dados brutos)' }),
        textarea,
      ]),
    ]),
  );

  root.append(
    card('Observações do gerador', [
      h('ul', { class: 'detail-list' }, [
        h('li', { text: 'O relatório descreve apenas as verificações implementadas e efetivamente executadas.' }),
        h('li', { text: 'Uma verificação inconclusiva é descrita como inconclusiva, nunca como aprovação.' }),
        h('li', { text: 'Nenhuma ação modificadora foi executada por este procedimento.' }),
        h('li', { text: 'As edições feitas no campo acima não alteram o registro original da execução.' }),
      ]),
    ]),
  );
}

// ------------------------------------------------------------------- auditoria
export async function renderAudit(root) {
  clear(root);
  root.append(pageHeader('Trilha de auditoria', 'Registro append-only das ações realizadas pela plataforma.'));

  const container = h('div', {});
  const state = { query: '' };

  async function refresh() {
    clear(container);
    container.append(h('p', { class: 'loading', text: 'Carregando registros…' }));
    let data;
    try {
      data = await api.audit({ query: state.query, limit: 200 });
    } catch (error) {
      clear(container);
      container.append(emptyState(`Não foi possível carregar a auditoria: ${error.message}`));
      return;
    }
    clear(container);
    if (!data.events.length) {
      container.append(emptyState('Nenhum evento de auditoria registrado.'));
      return;
    }
    container.append(
      h('div', { class: 'table-wrap' }, [
        h('table', {}, [
          h('caption', { text: `${data.count} evento(s) registrado(s)` }),
          h('thead', {}, h('tr', {}, [
            h('th', { scope: 'col', text: 'Data e hora' }),
            h('th', { scope: 'col', text: 'Ação' }),
            h('th', { scope: 'col', text: 'Alvo' }),
            h('th', { scope: 'col', text: 'Resultado' }),
            h('th', { scope: 'col', text: 'Origem' }),
            h('th', { scope: 'col', text: 'Aprovação' }),
            h('th', { scope: 'col', text: 'Execução' }),
          ])),
          h(
            'tbody',
            {},
            data.events.map((event) =>
              h('tr', {}, [
                h('td', { text: formatDateTime(event.occurred_at) }),
                h('td', { text: event.action }),
                h('td', { text: event.target || '—' }),
                h('td', { text: event.outcome }),
                h('td', { text: event.mode === 'demo' ? 'Simulado' : 'Real' }),
                h('td', { text: event.approval_granted ? 'Sim' : 'Não' }),
                h('td', {}, [
                  event.execution_id
                    ? h('a', { href: `#/history/${event.execution_id}`, text: event.execution_id.slice(0, 8) })
                    : '—',
                ]),
              ]),
            ),
          ),
        ]),
      ]),
    );
  }

  const searchInput = h('input', {
    type: 'search',
    placeholder: 'Buscar por ação, alvo ou execução',
    'aria-label': 'Buscar na auditoria',
    oninput: (event) => {
      state.query = event.target.value;
      window.clearTimeout(searchInput._timer);
      searchInput._timer = window.setTimeout(refresh, 250);
    },
  });

  root.append(h('div', { class: 'toolbar' }, [searchInput]));
  root.append(container);
  await refresh();
}

// -------------------------------------------------------------- configurações
export async function renderSettings(root) {
  clear(root);
  root.append(pageHeader('Configurações e permissões', 'Estado efetivo da instalação local.'));

  let settings;
  let health;
  try {
    [settings, health] = await Promise.all([api.settings(), api.health()]);
  } catch (error) {
    root.append(emptyState(`Não foi possível carregar as configurações: ${error.message}`));
    return;
  }

  root.append(
    h('div', { class: 'detail-grid' }, [
      card(
        'Configuração efetiva',
        definitionList([
          ['Diretório de dados', h('code', { text: settings.settings.data_dir })],
          ['Banco de dados', h('code', { text: settings.settings.database_path })],
          ['Endereço local', h('code', { text: `${settings.settings.host}:${settings.settings.port}` })],
          ['Modo padrão', settings.settings.mode === 'demo' ? 'Demonstração' : 'Dados reais'],
          ['Tempo limite por coleta', `${settings.settings.request_timeout_s}s`],
          ['Execuções simultâneas', String(settings.settings.max_concurrent_executions)],
        ]),
      ),
      card(
        'Permissões do processo',
        [
          definitionList([
            ['Privilégio administrativo', settings.privilege.is_admin === null ? 'Indeterminado' : settings.privilege.is_admin ? 'Concedido' : 'Não concedido'],
            ['PowerShell', health.powershell_available ? 'Disponível' : 'Não encontrado'],
            ['Janela nativa', settings.desktop && settings.desktop.available ? `Disponível (${settings.desktop.backend})` : 'Indisponível — a interface abre no navegador'],
            ['Versão do DeskGuard', health.version],
            ['Python', health.python],
            ['Sistema', health.platform],
          ]),
          h('p', { class: 'loading', text: settings.privilege.description }),
        ],
      ),
    ]),
  );

  root.append(
    card(
      'Catálogo',
      definitionList([
        ['Procedimentos disponíveis', String(settings.catalog.count)],
        ['Categorias', settings.catalog.categories.join(', ') || '—'],
      ]),
    ),
  );

  const allowlist = settings.allowlist || { targets: [], path: null };
  const listaDestinos = h('ul', { class: 'detail-list' });
  if (!allowlist.targets || !allowlist.targets.length) {
    listaDestinos.append(
      h('li', {
        text:
          'Nenhum destino autorizado. As sondagens de rede testam apenas o ' +
          'localhost e o gateway padrão do próprio endpoint.',
      }),
    );
  } else {
    allowlist.targets.forEach((alvo) => {
      const portas = (alvo.ports || []).join(', ') || '—';
      const descricao = alvo.description ? ` — ${alvo.description}` : '';
      listaDestinos.append(
        h('li', {
          text: `${alvo.host} (portas: ${portas}; ICMP: ${alvo.ping ? 'sim' : 'não'})${descricao}`,
        }),
      );
    });
  }
  if (allowlist.warnings && allowlist.warnings.length) {
    allowlist.warnings.forEach((aviso) => {
      listaDestinos.append(h('li', { text: `Atenção: ${aviso}` }));
    });
  }

  root.append(
    card(
      'Destinos autorizados para sondagens de rede',
      [
        definitionList([
          ['Arquivo', h('code', { text: allowlist.path || '—' })],
          ['Situação', allowlist.available ? 'Carregado' : 'Inexistente ou inválido'],
          ['Destinos autorizados', String((allowlist.targets || []).length)],
        ]),
        listaDestinos,
        h('p', {
          class: 'loading',
          text:
            'As sondagens de rede só atingem destinos listados aqui. A lista é ' +
            'gerenciada pela linha de comando (deskguard targets).',
        }),
      ],
    ),
  );

  root.append(
    card('Segurança da API local', [
      h('ul', { class: 'detail-list' }, [
        h('li', { text: 'A API escuta somente em 127.0.0.1 e recusa cabeçalhos Host não locais.' }),
        h('li', { text: 'Operações que alteram estado exigem o token anti-CSRF emitido pela própria página.' }),
        h('li', { text: 'Não existe endpoint de execução de comandos: só são aceitos procedimentos do catálogo.' }),
        h('li', { text: 'Procedimentos com capacidade de alteração exigem aprovação explícita e são registrados na auditoria.' }),
        h('li', { text: 'Parâmetros não declarados no procedimento são rejeitados antes da execução.' }),
        h('li', { text: 'Destinos de rede fora da lista de autorizados são recusados com erro 422 antes de qualquer coleta.' }),
      ]),
    ]),
  );
}

// --------------------------------------------------------------------------
// Módulo G - Auto-Remediação
// --------------------------------------------------------------------------

async function loadRemediationActions() {
  try {
    const res = await api.get('/api/remediation/actions');
    return res.actions || [];
  } catch (err) {
    console.error(err);
    return [];
  }
}

function renderRemediationModal(action, onConfirm) {
  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  
  const modal = document.createElement('div');
  modal.className = 'modal';
  modal.innerHTML = `
    <div class="modal-header">
      <h3>Confirmação de Remediação</h3>
    </div>
    <div class="modal-body">
      <p class="modal-warning">⚠️ Esta ação irá alterar o sistema.</p>
      <p><strong>Ação:</strong> ${action.title}</p>
      <p><strong>Descrição:</strong> ${action.description}</p>
      <p class="modal-risk">Nível de risco: <span class="badge">${action.risk_level}</span></p>
      <p>Tem certeza que deseja continuar?</p>
    </div>
    <div class="modal-footer">
      <button class="btn btn-ghost" id="remed-cancel">Cancelar</button>
      <button class="btn btn-primary" id="remed-confirm">Confirmar e Executar</button>
    </div>
  `;
  
  overlay.appendChild(modal);
  document.body.appendChild(overlay);
  
  modal.querySelector('#remed-cancel').onclick = () => document.body.removeChild(overlay);
  modal.querySelector('#remed-confirm').onclick = async () => {
    modal.querySelector('#remed-confirm').disabled = true;
    modal.querySelector('#remed-confirm').textContent = 'Executando...';
    try {
      await onConfirm();
      document.body.removeChild(overlay);
      showToast('Remediação executada com sucesso', 'ok');
    } catch (err) {
      modal.querySelector('#remed-confirm').disabled = false;
      modal.querySelector('#remed-confirm').textContent = 'Confirmar e Executar';
      showToast('Erro ao executar remediação: ' + err.message, 'fail');
    }
  };
}


async function handleRestartSpooler(executionId) {
  const actions = await loadRemediationActions();
  const action = actions.find(a => a.action_id === 'remediate.restart_spooler');
  if (!action) {
    showToast('Ação não disponível', 'warn');
    return;
  }
  
  renderRemediationModal(action, async () => {
    await api.post('/api/remediation/execute', {
      action_id: action.action_id,
      approved: true
    });
    // Recarregar após remediação
    setTimeout(() => window.location.hash = '#/history', 1500);
  });
}
