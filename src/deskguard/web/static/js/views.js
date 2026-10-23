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
export async function renderDashboard(root) {
  clear(root);
  root.append(pageHeader('Painel', 'Indicadores calculados a partir das execuções realmente registradas no banco local.'));

  let stats;
  try {
    stats = await api.dashboard();
  } catch (error) {
    root.append(emptyState(`Não foi possível carregar os indicadores: ${error.message}`));
    return;
  }

  const kpis = h('div', { class: 'kpi-grid' }, [
    kpi('Execuções registradas', stats.total_executions, 'Histórico completo do banco local'),
    kpi('Execuções em 24h', stats.executions_24h, 'Atividade recente'),
    kpi(
      'Desvios confirmados',
      stats.confirmed_issues,
      'Etapas com falha confirmada ou alerta',
      stats.confirmed_issues > 0 ? 'fail' : 'ok',
    ),
    kpi(
      'Verificações inconclusivas',
      stats.inconclusive_checks,
      'Requerem nova coleta com permissão adequada',
      stats.inconclusive_checks > 0 ? 'unknown' : 'ok',
    ),
  ]);
  root.append(kpis);

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

  const recent = await api.executions({ limit: 8 });
  const recentTable = recent.executions.length
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
            recent.executions.map((execution) =>
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

function kpi(label, value, hint, tone) {
  return h('div', { class: `kpi${tone ? ` is-${tone}` : ''}` }, [
    h('div', { class: 'kpi-label', text: label }),
    h('div', { class: 'kpi-value', text: String(value ?? 0) }),
    hint ? h('div', { class: 'kpi-hint', text: hint }) : null,
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
