// Roteador da interface do DeskGuard (roteamento por hash).
// As rotas são resolvidas sem recarregar a página, o que mantém a API local
// protegida pelas mesmas regras de origem e CSRF.

import { api } from './api.js';
import { h, toast } from './ui.js';
import {
  renderAudit,
  renderCatalog,
  renderDashboard,
  renderExecutionDetail,
  renderHistory,
  renderProcedureDetail,
  renderReport,
  renderSettings,
} from './views.js';

const root = document.getElementById('app');

const NAV_MAP = {
  dashboard: 'dashboard',
  catalog: 'catalog',
  history: 'history',
  audit: 'audit',
  settings: 'settings',
};

function parseHash() {
  const raw = window.location.hash.replace(/^#\/?/, '');
  const [path] = raw.split('?');
  const parts = path.split('/').filter(Boolean);
  return { parts, raw };
}

function markActiveNav(section) {
  document.querySelectorAll('.nav a').forEach((link) => {
    const route = link.dataset.route;
    if (route === section) {
      link.setAttribute('aria-current', 'page');
    } else {
      link.removeAttribute('aria-current');
    }
  });
}

async function router() {
  const { parts } = parseHash();
  const [section, argument] = parts;

  if (!section) {
    window.location.hash = '#/dashboard';
    return;
  }

  const target = NAV_MAP[section] || section;
  markActiveNav(target);

  // Garantir limpeza total do container e estado anterior ao trocar de aba
  root.replaceChildren(
    h('div', { class: 'card skeleton', style: 'padding: 40px; text-align: center;' }, [
      h('p', { text: 'Carregando seção...' })
    ])
  );

  try {
    if (section === 'dashboard') {
      await renderDashboard(root);
    } else if (section === 'catalog' && argument) {
      await renderProcedureDetail(root, decodeURIComponent(argument));
    } else if (section === 'catalog') {
      await renderCatalog(root);
    } else if (section === 'history' && argument) {
      await renderExecutionDetail(root, decodeURIComponent(argument));
    } else if (section === 'history') {
      await renderHistory(root);
    } else if (section === 'report' && argument) {
      await renderReport(root, decodeURIComponent(argument));
    } else if (section === 'audit') {
      await renderAudit(root);
    } else if (section === 'settings') {
      await renderSettings(root);
    } else {
      await renderDashboard(root);
    }
  } catch (error) {
    root.replaceChildren(
      h('div', { class: 'card' }, [
        h('h2', { text: 'Erro ao carregar a tela' }),
        h('p', { text: error.message }),
      ]),
    );
    toast(`Erro ao carregar a tela: ${error.message}`, 'error');
  }
}

async function bootstrap() {
  try {
    const health = await api.health();
    const version = document.getElementById('app-version');
    if (version) version.textContent = health.version;
  } catch (error) {
    toast(`Não foi possível falar com a API local: ${error.message}`, 'error');
  }
  window.addEventListener('hashchange', router);
  await router();
}

bootstrap();
