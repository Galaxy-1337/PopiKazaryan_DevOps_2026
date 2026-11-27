/* Веб-интерфейс «Конференция»: работа с API из браузера.
   Разделы и действия ограничены ролью текущего пользователя: роль и права
   переданы сервером в data-атрибутах тега body. Сервер, в свою очередь,
   проверяет права на каждом запросе, поэтому интерфейс — только удобство,
   а не защита. */
'use strict';

const API = '/api/v1';
const state = { conferences: [], sections: [], participants: [] };

/* Роль текущего пользователя (задана сервером при отрисовке страницы). */
const IS_ADMIN = document.body.dataset.admin === 'true';
const PERMISSIONS = new Set(
  (document.body.dataset.permissions || '').split(',').map((item) => item.trim()).filter(Boolean),
);

function can(permission) {
  return PERMISSIONS.has(permission);
}

function element(id) {
  return document.getElementById(id);
}

/* ------------------------------------------------------------------ */
/* Вспомогательные функции                                            */
/* ------------------------------------------------------------------ */
async function api(path, options = {}) {
  const response = await fetch(`${API}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    credentials: 'same-origin',
    ...options,
  });

  if (response.status === 401) {
    window.location.href = '/login';
    throw new Error('Требуется вход в систему');
  }

  const text = await response.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch (error) {
    data = null;
  }
  if (!response.ok) {
    const message = data?.error?.message || `HTTP ${response.status}`;
    const failure = new Error(message);
    failure.code = data?.error?.code || 'unknown_error';
    failure.details = data?.error?.details;
    throw failure;
  }
  return data;
}

function toast(message, isError = false) {
  const box = element('toast');
  if (!box) return;
  box.textContent = message;
  box.classList.toggle('error', isError);
  box.hidden = false;
  clearTimeout(box._timer);
  box._timer = setTimeout(() => { box.hidden = true; }, 4200);
}

function badge(value, titles = {}) {
  return `<span class="badge ${value}">${titles[value] || value}</span>`;
}

function esc(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;');
}

const APP_STATUS = {
  draft: 'черновик', submitted: 'подана', accepted: 'принята',
  rejected: 'отклонена', withdrawn: 'отозвана',
};
const FEE_STATUS = {
  pending: 'начислен', paid: 'оплачен', refunded: 'возвращён', cancelled: 'отменён',
};
const INV_STATUS = {
  queued: 'в очереди', sent: 'отправлено', delivered: 'доставлено',
  failed: 'ошибка', cancelled: 'отменено',
};
const HOTEL_STATUS = {
  requested: 'запрошена', confirmed: 'подтверждена', checked_in: 'заселён',
  cancelled: 'отменена', expired: 'истекла',
};
const THESIS_STATUS = {
  draft: 'черновик', submitted: 'на рецензии', under_review: 'на рецензии',
  accepted: 'приняты', revision: 'на доработку', rejected: 'отклонены',
};

/* Число колонок в таблицах: у администратора и участника набор столбцов разный. */
const APP_COLUMNS = IS_ADMIN ? 8 : 7;
const FEE_COLUMNS = 7;
const HOTEL_COLUMNS = 9;
const THESIS_COLUMNS = 7;
const PARTICIPANT_COLUMNS = 5;

/* ------------------------------------------------------------------ */
/* Навигация                                                          */
/* ------------------------------------------------------------------ */
const panelLoaders = {
  dashboard: () => loadReport(),
  applications: () => loadApplications(),
  finance: () => loadFees(),
  invitations: () => loadInvitations(),
  hotel: () => loadHotel(),
  participants: () => loadParticipants(),
  theses: () => loadTheses(),
};

document.querySelectorAll('.tab').forEach((tab) => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach((item) => item.classList.remove('is-active'));
    document.querySelectorAll('.panel').forEach((item) => item.classList.remove('is-active'));
    tab.classList.add('is-active');
    const panel = element(`panel-${tab.dataset.tab}`);
    if (panel) panel.classList.add('is-active');
    const loader = panelLoaders[tab.dataset.tab];
    if (loader) {
      Promise.resolve(loader()).catch((error) => toast(`${error.code}: ${error.message}`, true));
    }
  });
});

/* ------------------------------------------------------------------ */
/* Служебный адрес проверки работоспособности (только администратор)   */
/* ------------------------------------------------------------------ */
async function loadHealth() {
  const box = element('health');
  if (!box) return;
  try {
    // /health закрыт для участника, поэтому вызывается только у администратора.
    const response = await fetch('/health', { credentials: 'same-origin' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    box.textContent = `v${data.version} · БД: ${data.database} · ${data.app_env}`;
    box.className = `status ${data.status === 'ok' ? 'ok' : 'bad'}`;
  } catch (error) {
    box.textContent = 'сервис недоступен';
    box.className = 'status bad';
  }
}

/* ------------------------------------------------------------------ */
/* Сводка (только администратор)                                      */
/* ------------------------------------------------------------------ */
async function loadReport() {
  const block = element('report-cards');
  if (!block) return;                      // раздел недоступен этой роли

  const select = element('report-conference');
  if (!state.conferences.length) {
    state.conferences = (await api('/conferences?limit=200')).items;
    select.innerHTML = state.conferences
      .map((c) => `<option value="${c.id}">${esc(c.title)}</option>`).join('');
  }
  const id = select.value || state.conferences[0]?.id;
  if (!id) return;

  const report = await api(`/reports/conference/${id}`);
  const money = (value) => new Intl.NumberFormat('ru-RU', {
    style: 'currency', currency: 'RUB', maximumFractionDigits: 0,
  }).format(Number(value));

  const cards = [
    ['Заявок всего', report.applications_total],
    ['Участников', report.participants_total],
    ['Оргвзносы начислено', money(report.fees_total_amount)],
    ['Оргвзносы оплачено', money(report.fees_paid_amount)],
    ['Тезисов', report.theses_total],
    ['Броней гостиницы', report.hotel_bookings_total],
    ['Гостей к размещению', report.hotel_guests_total],
  ];
  block.innerHTML = cards
    .map(([key, value]) => `<div class="card"><div class="k">${key}</div><div class="v">${value}</div></div>`)
    .join('');

  const breakdown = (title, map, titles) => {
    const rows = Object.entries(map || {})
      .map(([key, value]) => `<li>${titles[key] || key}: <strong>${value}</strong></li>`)
      .join('') || '<li>нет данных</li>';
    return `<div class="breakdown"><h4>${title}</h4><ul>${rows}</ul></div>`;
  };
  element('report-breakdown').innerHTML = [
    breakdown('Заявки', report.applications_by_status, APP_STATUS),
    breakdown('Оргвзносы', report.fees_by_status, FEE_STATUS),
    breakdown('Приглашения', report.invitations_by_status, INV_STATUS),
    breakdown('Гостиница', report.hotel_by_status, HOTEL_STATUS),
    breakdown('Тезисы', report.theses_by_status, THESIS_STATUS),
  ].join('');
}

/* ------------------------------------------------------------------ */
/* Справочники для формы заявки (форма есть только у участника)       */
/* ------------------------------------------------------------------ */
function fillSelect(elementId, items, labelOf, emptyLabel) {
  const select = element(elementId);
  if (!select) return true;                // поля нет в интерфейсе этой роли
  if (!items.length) {
    select.innerHTML = `<option value="">${esc(emptyLabel)}</option>`;
    select.disabled = true;
    return false;
  }
  select.disabled = false;
  select.innerHTML = items
    .map((item) => `<option value="${item.id}">${esc(labelOf(item))}</option>`).join('');
  return true;
}

async function loadDictionaries() {
  if (!state.conferences.length) {
    state.conferences = (await api('/conferences?limit=200')).items;
  }
  state.sections = (await api('/sections?limit=200')).items;

  const hasSections = fillSelect(
    'app-section',
    state.sections,
    (s) => `${s.title} (свободно ${s.free_seats})`,
    'Нет секций — обратитесь к администратору',
  );

  if (!hasSections) {
    toast('Нет ни одной секции: заявку создать нельзя', true);
  }
}

/* ------------------------------------------------------------------ */
/* Заявки                                                             */
/* ------------------------------------------------------------------ */
async function loadApplications() {
  const status = element('app-status-filter').value;
  const query = status ? `&status=${status}` : '';
  const data = await api(`/applications?limit=100${query}`);
  const body = element('apps-body');

  if (!data.items.length) {
    const empty = IS_ADMIN ? 'Заявок нет' : 'У вас пока нет заявок';
    body.innerHTML = `<tr><td colspan="${APP_COLUMNS}" class="empty">${empty}</td></tr>`;
    return;
  }

  const section = (id) => esc(
    state.sections.find((s) => s.id === id)?.title || `секция #${id}`);
  const name = (id) => esc(
    state.participants.find((p) => p.id === id)?.full_name || `участник #${id}`);

  body.innerHTML = data.items.map((a) => {
    // Участнику сервер отдаёт только заявки, поданные из его учётной записи,
    // поэтому все строки в его списке — «свои».
    const own = !IS_ADMIN;
    const actions = [];

    if (IS_ADMIN) {
      // Администратор только решает судьбу поданной заявки.
      if (a.status === 'submitted') {
        actions.push(`<button class="small ok" data-act="accept" data-id="${a.id}">Принять</button>`);
        actions.push(`<button class="small danger" data-act="reject" data-id="${a.id}">Отклонить</button>`);
      }
    } else if (own) {
      // Участник распоряжается только своим черновиком.
      if (a.status === 'draft') {
        actions.push(`<button class="small ok" data-act="submit" data-id="${a.id}">Подать</button>`);
      }
      if (['draft', 'submitted', 'accepted'].includes(a.status)) {
        actions.push(`<button class="small" data-act="withdraw" data-id="${a.id}">Отозвать</button>`);
      }
      if (a.status === 'accepted') {
        actions.push(`<button class="small" data-act="thesis" data-id="${a.id}">Тезисы</button>`);
        actions.push(`<button class="small" data-act="hotel" data-id="${a.id}">Гостиница</button>`);
      }
    }

    const cells = [
      a.id,
      esc(a.topic),
      IS_ADMIN ? name(a.participant_id) : null,
      section(a.section_id),
      a.format,
      badge(a.status, APP_STATUS),
      a.needs_hotel ? 'да' : 'нет',
      `<div class="actions">${actions.join('') || '—'}</div>`,
    ].filter((cell) => cell !== null);

    return `<tr>${cells.map((cell) => `<td>${cell}</td>`).join('')}</tr>`;
  }).join('');
}

/* ------------------------------------------------------------------ */
/* Оргвзносы                                                          */
/* ------------------------------------------------------------------ */
async function loadFees() {
  const status = element('fee-status-filter').value;
  const query = status ? `&status=${status}` : '';
  const data = await api(`/fees?limit=100${query}`);
  const body = element('fees-body');
  if (!data.items.length) {
    const empty = IS_ADMIN ? 'Оргвзносов нет' : 'Начислений по вашим заявкам нет';
    body.innerHTML = `<tr><td colspan="${FEE_COLUMNS}" class="empty">${empty}</td></tr>`;
    return;
  }
  body.innerHTML = data.items.map((f) => {
    const actions = [];
    // Администратор оргвзносы только наблюдает: действий ему не предлагается.
    // Платит и возвращает взнос участник — по своей заявке.
    if (!IS_ADMIN) {
      if (f.status === 'pending' && can('fee:pay_own')) {
        actions.push(`<button class="small ok" data-act="pay" data-id="${f.id}">Оплатить</button>`);
      }
      // Возврат возможен только по своей отозванной или отклонённой заявке —
      // это правило предметной области.
      if (f.status === 'paid' && ['withdrawn', 'rejected'].includes(f.application_status)) {
        actions.push(`<button class="small danger" data-act="refund" data-id="${f.id}">Вернуть</button>`);
      }
    }
    return `<tr>
      <td>${f.id}</td><td>${f.application_id}</td>
      <td>${Number(f.amount).toFixed(2)}</td><td>${f.currency}</td>
      <td>${badge(f.status, FEE_STATUS)}</td>
      <td>${esc(f.payment_reference || '—')}</td>
      <td><div class="actions">${actions.join('') || '—'}</div></td>
    </tr>`;
  }).join('');
}

/* ------------------------------------------------------------------ */
/* Приглашения (только администратор)                                 */
/* ------------------------------------------------------------------ */
async function loadInvitations() {
  const body = element('inv-body');
  if (!body) return;
  const status = element('inv-status-filter').value;
  const query = status ? `&status=${status}` : '';
  const data = await api(`/invitations?limit=100${query}`);
  if (!data.items.length) {
    body.innerHTML = '<tr><td colspan="6" class="empty">Приглашений нет</td></tr>';
    return;
  }
  body.innerHTML = data.items.map((i) => {
    let actions = '—';
    if (i.status === 'queued' || i.status === 'failed') {
      actions = `<button class="small ok" data-act="send" data-id="${i.id}">Отправить</button>
                 <button class="small danger" data-act="send-fail" data-id="${i.id}">Ошибка</button>`;
    }
    return `<tr>
      <td>${i.id}</td><td>${i.application_id}</td><td>${esc(i.subject)}</td>
      <td>${badge(i.status, INV_STATUS)}</td><td>${i.attempts}</td>
      <td><div class="actions">${actions}</div></td>
    </tr>`;
  }).join('');
}

/* ------------------------------------------------------------------ */
/* Гостиница                                                          */
/* ------------------------------------------------------------------ */
async function loadHotel() {
  const status = element('hotel-status-filter').value;
  const query = status ? `&status=${status}` : '';
  const data = await api(`/hotel-bookings?limit=100${query}`);
  const body = element('hotel-body');
  if (!data.items.length) {
    const empty = IS_ADMIN ? 'Броней нет' : 'Запросов гостиницы по вашим заявкам нет';
    body.innerHTML = `<tr><td colspan="${HOTEL_COLUMNS}" class="empty">${empty}</td></tr>`;
    return;
  }
  body.innerHTML = data.items.map((b) => {
    let actions = '—';
    // Участник только наблюдает: статус меняет администратор.
    if (IS_ADMIN && b.status === 'requested') {
      actions = `<button class="small ok" data-act="confirm" data-id="${b.id}">Подтвердить</button>
                 <button class="small danger" data-act="reject-hotel" data-id="${b.id}">Отклонить</button>`;
    }
    return `<tr>
      <td>${b.id}</td><td>${b.application_id}</td><td>${esc(b.hotel_name)}</td>
      <td>${b.check_in}</td><td>${b.check_out}</td><td>${b.nights}</td><td>${b.guests_count}</td>
      <td>${badge(b.status, HOTEL_STATUS)}</td>
      <td><div class="actions">${actions}</div></td>
    </tr>`;
  }).join('');
}

/* ------------------------------------------------------------------ */
/* Участники (только администратор)                                   */
/* ------------------------------------------------------------------ */
async function loadParticipants() {
  const body = element('participants-body');
  if (!body) return;
  const search = element('participant-search')?.value || '';
  const query = search ? `&search=${encodeURIComponent(search)}` : '';
  const data = await api(`/participants?limit=200${query}`);
  if (!data.items.length) {
    body.innerHTML = `<tr><td colspan="${PARTICIPANT_COLUMNS}" class="empty">Участников не найдено</td></tr>`;
    return;
  }
  body.innerHTML = data.items.map((p) => `<tr>
      <td>${p.id}</td><td>${esc(p.full_name)}</td><td>${esc(p.email)}</td>
      <td>${esc(p.organization || '—')}</td><td>${esc(p.city || '—')}</td>
    </tr>`).join('');
}

/* ------------------------------------------------------------------ */
/* Тезисы                                                             */
/* ------------------------------------------------------------------ */
async function loadTheses() {
  const data = await api('/theses?limit=100');
  const body = element('theses-body');
  if (!data.items.length) {
    const empty = IS_ADMIN ? 'Тезисов на оценивание нет' : 'Вы ещё не подавали тезисов';
    body.innerHTML = `<tr><td colspan="${THESIS_COLUMNS}" class="empty">${empty}</td></tr>`;
    return;
  }
  body.innerHTML = data.items.map((t) => {
    let actions = '—';
    // Оценку выставляет только администратор.
    if (IS_ADMIN && ['submitted', 'under_review', 'revision'].includes(t.status)) {
      actions = `<button class="small ok" data-act="review-ok" data-id="${t.id}">Принять (8)</button>
                 <button class="small danger" data-act="review-bad" data-id="${t.id}">Отклонить (4)</button>`;
    }
    return `<tr>
      <td>${t.id}</td><td>${t.application_id}</td><td>${esc(t.title)}</td>
      <td>${badge(t.status, THESIS_STATUS)}</td>
      <td>${esc(t.reviewer_name || '—')}</td><td>${t.review_score ?? '—'}</td>
      <td><div class="actions">${actions}</div></td>
    </tr>`;
  }).join('');
}

/* ------------------------------------------------------------------ */
/* Действия                                                           */
/* ------------------------------------------------------------------ */
document.addEventListener('click', async (event) => {
  const button = event.target.closest('button[data-act]');
  if (!button) return;
  const { act, id } = button.dataset;

  try {
    if (act === 'submit') await api(`/applications/${id}/submit`, { method: 'POST' });
    if (act === 'accept') {
      await api(`/applications/${id}/decision`, {
        method: 'POST',
        body: JSON.stringify({ accept: true, comment: 'Принято через веб-интерфейс' }),
      });
    }
    if (act === 'reject') {
      await api(`/applications/${id}/decision`, {
        method: 'POST',
        body: JSON.stringify({ accept: false, comment: 'Не соответствует тематике' }),
      });
    }
    if (act === 'withdraw') await api(`/applications/${id}/withdraw`, { method: 'POST' });
    if (act === 'pay') {
      await api(`/fees/${id}/pay`, {
        method: 'POST', body: JSON.stringify({ payment_reference: `PAY-${Date.now()}` }),
      });
    }
    if (act === 'refund') {
      await api(`/fees/${id}/refund`, {
        method: 'POST', body: JSON.stringify({ reason: 'Заявка отозвана или отклонена' }),
      });
    }
    if (act === 'send') await api(`/invitations/${id}/send?success=true`, { method: 'POST' });
    if (act === 'send-fail') {
      await api(`/invitations/${id}/send?success=false&error=SMTP%20timeout`, { method: 'POST' });
    }
    if (act === 'confirm') await api(`/hotel-bookings/${id}/confirm`, { method: 'POST' });
    if (act === 'reject-hotel') {
      await api(`/hotel-bookings/${id}/reject`, {
        method: 'POST', body: JSON.stringify({ reason: 'Нет свободных мест в гостинице' }),
      });
    }
    if (act === 'review-ok') {
      await api(`/theses/${id}/review`, {
        method: 'POST',
        body: JSON.stringify({
          reviewer_name: 'Администратор', score: 8, accepted: true,
          comment: 'Тезисы соответствуют требованиям',
        }),
      });
    }
    if (act === 'review-bad') {
      await api(`/theses/${id}/review`, {
        method: 'POST',
        body: JSON.stringify({
          reviewer_name: 'Администратор', score: 4, accepted: false,
          comment: 'Недостаточная проработка',
        }),
      });
    }
    if (act === 'thesis') {
      const title = prompt('Название тезисов:', 'Тезисы доклада');
      if (!title) return;
      await api(`/applications/${id}/theses`, {
        method: 'POST',
        body: JSON.stringify({
          title,
          abstract: 'Краткое описание доклада объёмом не менее пятидесяти символов '
            + 'для проверки правила валидации.',
          file_name: 'thesis.pdf',
          file_size_kb: 150,
        }),
      });
    }
    if (act === 'hotel') {
      if (!state.conferences.length) {
        state.conferences = (await api('/conferences?limit=200')).items;
      }
      const conference = state.conferences[0];
      const booking = await api('/hotel-bookings', {
        method: 'POST',
        body: JSON.stringify({
          application_id: Number(id),
          hotel_name: 'Гостиница «Семёновская»',
          room_type: 'standard',
          guests_count: 1,
          check_in: conference.starts_on,
          check_out: conference.ends_on,
        }),
      });
      toast(`Создан запрос №${booking.id}, срок подтверждения ${booking.confirmation_deadline}`);
    }

    toast('Операция выполнена');
    const active = document.querySelector('.tab.is-active')?.dataset.tab;
    const loader = panelLoaders[active];
    if (loader) {
      await loader();
      if (active === 'applications') await loadDictionaries();
    }
  } catch (error) {
    const details = error.details ? ` (${error.details.map((d) => d.field).join(', ')})` : '';
    toast(`${error.code}: ${error.message}${details}`, true);
  }
});

/* ------------------------------------------------------------------ */
/* Форма создания заявки (только участник)                            */
/* ------------------------------------------------------------------ */
element('app-create-toggle')?.addEventListener('click', () => {
  const form = element('app-create-form');
  form.hidden = !form.hidden;
});

element('app-create-form')?.addEventListener('submit', async (event) => {
  event.preventDefault();
  try {
    if (!state.conferences.length) {
      state.conferences = (await api('/conferences?limit=200')).items;
    }
    // Участник указывает свои ФИО и почту сам — они сохраняются в профиле.
    // Чужого участника подставить нельзя: сервер берёт его из сессии.
    const payload = {
      conference_id: state.conferences[0].id,
      section_id: Number(element('app-section').value),
      topic: element('app-topic').value,
      annotation: element('app-annotation').value || null,
      format: element('app-format').value,
      needs_hotel: element('app-hotel').checked,
      full_name: element('app-full-name').value,
      email: element('app-email').value,
      organization: element('app-organization').value || null,
      city: element('app-city').value || null,
    };

    const application = await api('/applications', {
      method: 'POST', body: JSON.stringify(payload),
    });
    toast(`Создан черновик заявки №${application.id}: подайте его или отзовите`);
    element('app-topic').value = '';
    element('app-annotation').value = '';
    element('app-hotel').checked = false;
    await loadApplications();
    await loadDictionaries();
  } catch (error) {
    toast(`${error.code}: ${error.message}`, true);
  }
});

/* ------------------------------------------------------------------ */
/* Кнопки обновления                                                  */
/* ------------------------------------------------------------------ */
function bind(id, handler) {
  element(id)?.addEventListener('click', () => {
    // Кнопки «Обновить» перезапрашивают данные. Короткое сообщение показывает,
    // что нажатие сработало: иначе при неизменных данных кнопка выглядит мёртвой.
    Promise.resolve(handler())
      .then(() => toast('Данные обновлены'))
      .catch((error) => toast(`${error.code}: ${error.message}`, true));
  });
}

function bindChange(id, handler) {
  element(id)?.addEventListener('change', () => {
    Promise.resolve(handler()).catch((error) => toast(`${error.code}: ${error.message}`, true));
  });
}

bind('report-refresh', loadReport);
bindChange('report-conference', loadReport);
bind('apps-refresh', loadApplications);
bindChange('app-status-filter', loadApplications);
bind('fees-refresh', loadFees);
bindChange('fee-status-filter', loadFees);
bind('inv-refresh', loadInvitations);
bindChange('inv-status-filter', loadInvitations);
bind('hotel-refresh', loadHotel);
bindChange('hotel-status-filter', loadHotel);
bind('participants-refresh', loadParticipants);
bind('theses-refresh', loadTheses);

element('participant-search')?.addEventListener('input', () => {
  loadParticipants().catch(() => {});
});

/* ------------------------------------------------------------------ */
/* Старт                                                              */
/* ------------------------------------------------------------------ */
(async function init() {
  if (IS_ADMIN) loadHealth();
  const firstTab = document.querySelector('.tab.is-active')?.dataset.tab || 'applications';
  const loader = panelLoaders[firstTab];
  try {
    if (loader) await loader();
    if (!IS_ADMIN) await loadDictionaries();
  } catch (error) {
    toast(`${error.code || 'error'}: ${error.message}`, true);
  }
})();
