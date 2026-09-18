/* Веб-интерфейс «Конференция»: работа с API из браузера.
   Разделы и действия ограничены ролью текущего пользователя: права переданы
   сервером в data-атрибутах тега body. */
'use strict';

const API = '/api/v1';
const state = { conferences: [], sections: [], participants: [] };

/* Права текущего пользователя (заданы сервером при отрисовке страницы). */
const PERMISSIONS = new Set(
  (document.body.dataset.permissions || '').split(',').map((item) => item.trim()).filter(Boolean),
);
const PARTICIPANT_ID = document.body.dataset.participantId || '';

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
  const data = text ? JSON.parse(text) : null;
  if (!response.ok) {
    const error = new Error(data?.error?.message || `HTTP ${response.status}`);
    error.code = data?.error?.code || 'unknown_error';
    error.details = data?.error?.details;
    throw error;
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
/* Служебный адрес проверки работоспособности                         */
/* ------------------------------------------------------------------ */
async function loadHealth() {
  const box = element('health');
  if (!box) return;
  try {
    const response = await fetch('/health');
    const data = await response.json();
    box.textContent = `v${data.version} · БД: ${data.database} · ${data.app_env}`;
    box.className = `status ${data.status === 'ok' ? 'ok' : 'bad'}`;
  } catch (error) {
    box.textContent = 'сервис недоступен';
    box.className = 'status bad';
  }
}

/* ------------------------------------------------------------------ */
/* Сводка (только организатор)                                        */
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
/* Справочники для формы заявки                                       */
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

  // Список участников нужен только организатору: остальные подают заявку от себя.
  if (can('participant:manage')) {
    state.participants = (await api('/participants?limit=200')).items;
  }

  const hasSections = fillSelect(
    'app-section',
    state.sections,
    (s) => `${s.title} (свободно ${s.free_seats})`,
    'Нет секций — создайте конференцию с секциями',
  );
  const hasParticipants = can('participant:manage')
    ? fillSelect(
        'app-participant',
        state.participants,
        (p) => `${p.full_name} — ${p.email}`,
        'Нет участников — добавьте участника',
      )
    : true;

  const note = element('dict-warning');
  if (!note) return;
  if (hasSections && hasParticipants) {
    note.hidden = true;
    note.textContent = '';
    return;
  }
  const missing = [!hasSections ? 'секции' : null, !hasParticipants ? 'участники' : null]
    .filter(Boolean).join(' и ');
  note.hidden = false;
  note.textContent =
    `Заявку создать нельзя: в базе нет данных (${missing}). `
    + 'Если база пуста, остановите сервер, удалите файл data/conference.db и запустите '
    + 'приложение снова — демонстрационные данные создадутся автоматически.';
  toast(`Нет данных для выбора: ${missing}`, true);
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
    const empty = can('report:read') ? 'Заявок нет' : 'У вас пока нет заявок';
    body.innerHTML = `<tr><td colspan="8" class="empty">${empty}</td></tr>`;
    return;
  }

  const name = (id) => esc(
    state.participants.find((p) => p.id === id)?.full_name || `участник #${id}`);
  const section = (id) => esc(
    state.sections.find((s) => s.id === id)?.title || `секция #${id}`);

  body.innerHTML = data.items.map((a) => {
    const own = String(a.participant_id) === String(PARTICIPANT_ID);
    const mine = own || can('application:decide');
    const actions = [];
    if (can('application:create') && mine) {
      if (a.status === 'draft') {
        actions.push(`<button class="small ok" data-act="submit" data-id="${a.id}">Подать</button>`);
      }
      if (a.status === 'draft' || a.status === 'submitted' || a.status === 'accepted') {
        actions.push(`<button class="small" data-act="withdraw" data-id="${a.id}">Отозвать</button>`);
      }
    }
    if (can('application:decide') && a.status === 'submitted') {
      actions.push(`<button class="small ok" data-act="accept" data-id="${a.id}">Принять</button>`);
      actions.push(`<button class="small danger" data-act="reject" data-id="${a.id}">Отклонить</button>`);
    }
    if (can('thesis:submit_own') && a.status === 'accepted' && mine) {
      actions.push(`<button class="small" data-act="thesis" data-id="${a.id}">Тезисы</button>`);
    }
    if (can('hotel:request_own') && a.status === 'accepted' && mine) {
      actions.push(`<button class="small" data-act="hotel" data-id="${a.id}">Гостиница</button>`);
    }
    return `<tr>
      <td>${a.id}</td>
      <td>${esc(a.topic)}</td>
      <td>${name(a.participant_id)}</td>
      <td>${section(a.section_id)}</td>
      <td>${a.format}</td>
      <td>${badge(a.status, APP_STATUS)}</td>
      <td>${a.needs_hotel ? 'да' : 'нет'}</td>
      <td><div class="actions">${actions.join('') || '—'}</div></td>
    </tr>`;
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
    const empty = can('fee:manage') ? 'Оргвзносов нет' : 'Начислений по вашим заявкам нет';
    body.innerHTML = `<tr><td colspan="7" class="empty">${empty}</td></tr>`;
    return;
  }
  body.innerHTML = data.items.map((f) => {
    const actions = [];
    if (f.status === 'pending' && (can('fee:pay_own') || can('fee:manage'))) {
      actions.push(`<button class="small ok" data-act="pay" data-id="${f.id}">Оплатить</button>`);
    }
    if (f.status === 'paid' && can('fee:manage')) {
      actions.push(`<button class="small danger" data-act="refund" data-id="${f.id}">Вернуть</button>`);
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
/* Приглашения                                                        */
/* ------------------------------------------------------------------ */
async function loadInvitations() {
  const status = element('inv-status-filter').value;
  const query = status ? `&status=${status}` : '';
  const data = await api(`/invitations?limit=100${query}`);
  const body = element('inv-body');
  if (!data.items.length) {
    const empty = can('invitation:manage')
      ? 'Приглашений нет'
      : 'Вам ещё не направляли приглашений';
    body.innerHTML = `<tr><td colspan="6" class="empty">${empty}</td></tr>`;
    return;
  }
  body.innerHTML = data.items.map((i) => {
    let actions = '—';
    if (can('invitation:manage') && (i.status === 'queued' || i.status === 'failed')) {
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
    const empty = can('hotel:manage') ? 'Броней нет' : 'Броней по вашим заявкам нет';
    body.innerHTML = `<tr><td colspan="9" class="empty">${empty}</td></tr>`;
    return;
  }
  body.innerHTML = data.items.map((b) => {
    const actions = (b.status === 'requested' && can('hotel:manage'))
      ? `<button class="small ok" data-act="confirm" data-id="${b.id}">Подтвердить</button>`
      : '—';
    return `<tr>
      <td>${b.id}</td><td>${b.application_id}</td><td>${esc(b.hotel_name)}</td>
      <td>${b.check_in}</td><td>${b.check_out}</td><td>${b.nights}</td><td>${b.guests_count}</td>
      <td>${badge(b.status, HOTEL_STATUS)}</td>
      <td><div class="actions">${actions}</div></td>
    </tr>`;
  }).join('');
}

/* ------------------------------------------------------------------ */
/* Участники (только организатор)                                     */
/* ------------------------------------------------------------------ */
async function loadParticipants() {
  const search = element('participant-search')?.value || '';
  const query = search ? `&search=${encodeURIComponent(search)}` : '';
  const data = await api(`/participants?limit=200${query}`);
  const body = element('participants-body');
  if (!body) return;
  if (!data.items.length) {
    body.innerHTML = '<tr><td colspan="6" class="empty">Участников не найдено</td></tr>';
    return;
  }
  body.innerHTML = data.items.map((p) => `<tr>
      <td>${p.id}</td><td>${esc(p.full_name)}</td><td>${esc(p.email)}</td>
      <td>${esc(p.organization || '—')}</td><td>${esc(p.city || '—')}</td><td>${p.role}</td>
    </tr>`).join('');
}

/* ------------------------------------------------------------------ */
/* Тезисы                                                             */
/* ------------------------------------------------------------------ */
async function loadTheses() {
  const data = await api('/theses?limit=100');
  const body = element('theses-body');
  if (!data.items.length) {
    const empty = can('thesis:review') ? 'Тезисов на рецензию нет' : 'Вы ещё не подавали тезисов';
    body.innerHTML = `<tr><td colspan="7" class="empty">${empty}</td></tr>`;
    return;
  }
  body.innerHTML = data.items.map((t) => {
    let actions = '—';
    if (can('thesis:review') && ['submitted', 'under_review', 'revision'].includes(t.status)) {
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
        method: 'POST', body: JSON.stringify({ reason: 'Участник отказался от участия' }),
      });
    }
    if (act === 'send') await api(`/invitations/${id}/send?success=true`, { method: 'POST' });
    if (act === 'send-fail') {
      await api(`/invitations/${id}/send?success=false&error=SMTP%20timeout`, { method: 'POST' });
    }
    if (act === 'confirm') await api(`/hotel-bookings/${id}/confirm`, { method: 'POST' });
    if (act === 'review-ok') {
      await api(`/theses/${id}/review`, {
        method: 'POST',
        body: JSON.stringify({
          reviewer_name: 'Кузнецова О. Д.', score: 8, accepted: true,
          comment: 'Тезисы соответствуют требованиям',
        }),
      });
    }
    if (act === 'review-bad') {
      await api(`/theses/${id}/review`, {
        method: 'POST',
        body: JSON.stringify({
          reviewer_name: 'Кузнецова О. Д.', score: 4, accepted: false,
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
      toast(`Создана бронь №${booking.id}, срок подтверждения ${booking.confirmation_deadline}`);
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
/* Форма создания заявки                                              */
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
    const payload = {
      conference_id: state.conferences[0].id,
      section_id: Number(element('app-section').value),
      topic: element('app-topic').value,
      annotation: element('app-annotation').value || null,
      format: element('app-format').value,
      needs_hotel: element('app-hotel').checked,
      // Организатор выбирает участника, остальные подают заявку от своего имени.
      participant_id: can('participant:manage')
        ? Number(element('app-participant').value)
        : Number(PARTICIPANT_ID),
    };

    const application = await api('/applications', {
      method: 'POST', body: JSON.stringify(payload),
    });
    toast(`Создана заявка №${application.id} (черновик)`);
    event.target.reset();
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
    Promise.resolve(handler()).catch((error) => toast(`${error.code}: ${error.message}`, true));
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
  loadHealth();
  const firstTab = document.querySelector('.tab.is-active')?.dataset.tab || 'dashboard';
  const loader = panelLoaders[firstTab];
  try {
    if (loader) await loader();
    if (can('application:create')) await loadDictionaries();
  } catch (error) {
    toast(`${error.code || 'error'}: ${error.message}`, true);
  }
})();
