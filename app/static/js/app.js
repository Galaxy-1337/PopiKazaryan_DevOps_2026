/* Веб-интерфейс «Конференция»: работа с API из браузера. */
'use strict';

const API = '/api/v1';
let state = { conferences: [], sections: [], participants: [] };

/* ------------------------------------------------------------------ */
/* Вспомогательные функции                                            */
/* ------------------------------------------------------------------ */
async function api(path, options = {}) {
  const response = await fetch(`${API}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
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
  const box = document.getElementById('toast');
  box.textContent = message;
  box.classList.toggle('error', isError);
  box.hidden = false;
  clearTimeout(box._timer);
  box._timer = setTimeout(() => { box.hidden = true; }, 4200);
}

function badge(value, titles = {}) {
  const title = titles[value] || value;
  return `<span class="badge ${value}">${title}</span>`;
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
document.querySelectorAll('.tab').forEach((tab) => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach((t) => t.classList.remove('is-active'));
    document.querySelectorAll('.panel').forEach((p) => p.classList.remove('is-active'));
    tab.classList.add('is-active');
    document.getElementById(`panel-${tab.dataset.tab}`).classList.add('is-active');
    if (tab.dataset.tab === 'dashboard') loadReport();
    if (tab.dataset.tab === 'applications') loadApplications();
    if (tab.dataset.tab === 'finance') loadFees();
    if (tab.dataset.tab === 'invitations') loadInvitations();
    if (tab.dataset.tab === 'hotel') loadHotel();
    if (tab.dataset.tab === 'theses') loadTheses();
  });
});

/* ------------------------------------------------------------------ */
/* Служебный адрес проверки работоспособности                         */
/* ------------------------------------------------------------------ */
async function loadHealth() {
  const box = document.getElementById('health');
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
/* Сводка                                                             */
/* ------------------------------------------------------------------ */
async function loadReport() {
  const select = document.getElementById('report-conference');
  if (!state.conferences.length) {
    const data = await api('/conferences?limit=200');
    state.conferences = data.items;
    select.innerHTML = data.items
      .map((c) => `<option value="${c.id}">${esc(c.title)}</option>`).join('');
  }
  const id = select.value || state.conferences[0]?.id;
  if (!id) return;

  const report = await api(`/reports/conference/${id}`);
  const money = (v) => new Intl.NumberFormat('ru-RU', {
    style: 'currency', currency: 'RUB', maximumFractionDigits: 0,
  }).format(Number(v));

  const cards = [
    ['Заявок всего', report.applications_total],
    ['Участников', report.participants_total],
    ['Оргвзносы начислено', money(report.fees_total_amount)],
    ['Оргвзносы оплачено', money(report.fees_paid_amount)],
    ['Тезисов', report.theses_total],
    ['Броней гостиницы', report.hotel_bookings_total],
    ['Гостей к размещению', report.hotel_guests_total],
  ];
  document.getElementById('report-cards').innerHTML = cards
    .map(([k, v]) => `<div class="card"><div class="k">${k}</div><div class="v">${v}</div></div>`)
    .join('');

  const block = (title, map, titles) => {
    const rows = Object.entries(map || {})
      .map(([k, v]) => `<li>${titles[k] || k}: <strong>${v}</strong></li>`).join('') || '<li>нет данных</li>';
    return `<div class="breakdown"><h4>${title}</h4><ul>${rows}</ul></div>`;
  };
  document.getElementById('report-breakdown').innerHTML = [
    block('Заявки', report.applications_by_status, APP_STATUS),
    block('Оргвзносы', report.fees_by_status, FEE_STATUS),
    block('Приглашения', report.invitations_by_status, INV_STATUS),
    block('Гостиница', report.hotel_by_status, HOTEL_STATUS),
    block('Тезисы', report.theses_by_status, THESIS_STATUS),
  ].join('');
}

/* ------------------------------------------------------------------ */
/* Справочники для формы заявки                                       */
/* ------------------------------------------------------------------ */
function fillSelect(elementId, items, labelOf, emptyLabel) {
  const select = document.getElementById(elementId);
  if (!items.length) {
    select.innerHTML = `<option value="">${esc(emptyLabel)}</option>`;
    select.disabled = true;
    return false;
  }
  select.disabled = false;
  select.innerHTML = items.map((item) => `<option value="${item.id}">${esc(labelOf(item))}</option>`).join('');
  return true;
}

async function loadDictionaries() {
  if (!state.conferences.length) {
    const data = await api('/conferences?limit=200');
    state.conferences = data.items;
  }

  const sections = (await api('/sections?limit=200')).items;
  const participants = (await api('/participants?limit=200')).items;
  state.sections = sections;
  state.participants = participants;

  const hasSections = fillSelect(
    'app-section',
    sections,
    (s) => `${s.title} (свободно ${s.free_seats})`,
    'Нет секций — создайте конференцию с секциями',
  );
  const hasParticipants = fillSelect(
    'app-participant',
    participants,
    (p) => `${p.full_name} — ${p.email}`,
    'Нет участников — добавьте участника',
  );

  const note = document.getElementById('dict-warning');
  if (hasSections && hasParticipants) {
    note.hidden = true;
    note.textContent = '';
    return;
  }

  const missing = [!hasSections ? 'секции' : null, !hasParticipants ? 'участники' : null]
    .filter(Boolean)
    .join(' и ');
  note.hidden = false;
  note.textContent =
    `Заявку создать нельзя: в базе нет данных (${missing}). `
    + `Конференций: ${state.conferences.length}, секций: ${sections.length}, участников: ${participants.length}. `
    + 'Если база пуста, остановите сервер (Ctrl+C), удалите файл data/conference.db и запустите приложение снова — '
    + 'демонстрационные данные создадутся автоматически (SEED_DEMO_DATA=true).';
  toast(`Нет данных для выбора: ${missing}`, true);
}

async function loadApplications() {
  const status = document.getElementById('app-status-filter').value;
  const query = status ? `&status=${status}` : '';
  const data = await api(`/applications?limit=100${query}`);
  const body = document.getElementById('apps-body');
  if (!data.items.length) {
    body.innerHTML = '<tr><td colspan="8" class="empty">Заявок нет</td></tr>';
    return;
  }

  const name = (id) => esc(state.participants.find((p) => p.id === id)?.full_name || `#${id}`);
  const section = (id) => esc(state.sections.find((s) => s.id === id)?.title || `#${id}`);

  body.innerHTML = data.items.map((a) => {
    const actions = [];
    if (a.status === 'draft') {
      actions.push(`<button class="small ok" data-act="submit" data-id="${a.id}">Подать</button>`);
    }
    if (a.status === 'submitted') {
      actions.push(`<button class="small ok" data-act="accept" data-id="${a.id}">Принять</button>`);
      actions.push(`<button class="small danger" data-act="reject" data-id="${a.id}">Отклонить</button>`);
    }
    if (a.status === 'draft' || a.status === 'submitted' || a.status === 'accepted') {
      actions.push(`<button class="small" data-act="withdraw" data-id="${a.id}">Отозвать</button>`);
    }
    if (a.status === 'accepted') {
      actions.push(`<button class="small" data-act="thesis" data-id="${a.id}">Тезисы</button>`);
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
      <td><div class="actions">${actions.join('')}</div></td>
    </tr>`;
  }).join('');
}

/* ------------------------------------------------------------------ */
/* Оргвзносы                                                          */
/* ------------------------------------------------------------------ */
async function loadFees() {
  const status = document.getElementById('fee-status-filter').value;
  const query = status ? `&status=${status}` : '';
  const data = await api(`/fees?limit=100${query}`);
  const body = document.getElementById('fees-body');
  if (!data.items.length) {
    body.innerHTML = '<tr><td colspan="7" class="empty">Оргвзносов нет</td></tr>';
    return;
  }
  body.innerHTML = data.items.map((f) => {
    const actions = [];
    if (f.status === 'pending') {
      actions.push(`<button class="small ok" data-act="pay" data-id="${f.id}">Оплатить</button>`);
    }
    if (f.status === 'paid') {
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
  const status = document.getElementById('inv-status-filter').value;
  const query = status ? `&status=${status}` : '';
  const data = await api(`/invitations?limit=100${query}`);
  const body = document.getElementById('inv-body');
  if (!data.items.length) {
    body.innerHTML = '<tr><td colspan="6" class="empty">Приглашений нет</td></tr>';
    return;
  }
  body.innerHTML = data.items.map((i) => {
    const actions = (i.status === 'queued' || i.status === 'failed')
      ? `<button class="small ok" data-act="send" data-id="${i.id}">Отправить</button>
         <button class="small danger" data-act="send-fail" data-id="${i.id}">Смоделировать ошибку</button>`
      : '—';
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
  const status = document.getElementById('hotel-status-filter').value;
  const query = status ? `&status=${status}` : '';
  const data = await api(`/hotel-bookings?limit=100${query}`);
  const body = document.getElementById('hotel-body');
  if (!data.items.length) {
    body.innerHTML = '<tr><td colspan="9" class="empty">Броней нет</td></tr>';
    return;
  }
  body.innerHTML = data.items.map((b) => {
    const actions = b.status === 'requested'
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
/* Тезисы                                                             */
/* ------------------------------------------------------------------ */
async function loadTheses() {
  const data = await api('/theses?limit=100');
  const body = document.getElementById('theses-body');
  if (!data.items.length) {
    body.innerHTML = '<tr><td colspan="7" class="empty">Тезисов нет</td></tr>';
    return;
  }
  body.innerHTML = data.items.map((t) => {
    const actions = ['submitted', 'under_review', 'revision'].includes(t.status)
      ? `<button class="small ok" data-act="review-ok" data-id="${t.id}">Принять (8)</button>
         <button class="small danger" data-act="review-bad" data-id="${t.id}">Отклонить (4)</button>`
      : '—';
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
        method: 'POST', body: JSON.stringify({ accept: true, comment: 'Принято через веб-интерфейс' }),
      });
    }
    if (act === 'reject') {
      await api(`/applications/${id}/decision`, {
        method: 'POST', body: JSON.stringify({ accept: false, comment: 'Не соответствует тематике' }),
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
        body: JSON.stringify({ reviewer_name: 'Кузнецова О. Д.', score: 8, accepted: true, comment: 'Тезисы соответствуют требованиям' }),
      });
    }
    if (act === 'review-bad') {
      await api(`/theses/${id}/review`, {
        method: 'POST',
        body: JSON.stringify({ reviewer_name: 'Кузнецова О. Д.', score: 4, accepted: false, comment: 'Недостаточная проработка' }),
      });
    }
    if (act === 'thesis') {
      const title = prompt('Название тезисов:', 'Тезисы доклада');
      if (!title) return;
      await api(`/applications/${id}/theses`, {
        method: 'POST',
        body: JSON.stringify({
          title,
          abstract: 'Краткое описание доклада объёмом не менее пятидесяти символов для проверки правила валидации.',
          file_name: 'thesis.pdf',
          file_size_kb: 150,
        }),
      });
    }
    if (act === 'hotel') {
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
    const active = document.querySelector('.tab.is-active').dataset.tab;
    if (active === 'applications') {
      // Обновляем и таблицу, и справочники: число свободных мест в секциях
      // меняется при подаче, принятии, отклонении и отзыве заявок.
      await loadApplications();
      await loadDictionaries();
    }
    if (active === 'finance') loadFees();
    if (active === 'invitations') loadInvitations();
    if (active === 'hotel') loadHotel();
    if (active === 'theses') loadTheses();
  } catch (error) {
    const details = error.details ? ` (${error.details.map((d) => d.field).join(', ')})` : '';
    toast(`${error.code}: ${error.message}${details}`, true);
  }
});

/* ------------------------------------------------------------------ */
/* Форма создания заявки                                              */
/* ------------------------------------------------------------------ */
document.getElementById('app-create-toggle').addEventListener('click', () => {
  const form = document.getElementById('app-create-form');
  form.hidden = !form.hidden;
});

document.getElementById('app-create-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  try {
    const conference = state.conferences[0];
    const application = await api('/applications', {
      method: 'POST',
      body: JSON.stringify({
        conference_id: conference.id,
        section_id: Number(document.getElementById('app-section').value),
        participant_id: Number(document.getElementById('app-participant').value),
        topic: document.getElementById('app-topic').value,
        annotation: document.getElementById('app-annotation').value || null,
        format: document.getElementById('app-format').value,
        needs_hotel: document.getElementById('app-hotel').checked,
      }),
    });
    toast(`Создана заявка №${application.id} (черновик)`);
    event.target.reset();
    await loadApplications();
    await loadDictionaries();
  } catch (error) {
    toast(`${error.code}: ${error.message}`, true);
  }
});

document.getElementById('report-refresh').addEventListener('click', loadReport);
document.getElementById('report-conference').addEventListener('change', loadReport);
document.getElementById('apps-refresh').addEventListener('click', loadApplications);
document.getElementById('app-status-filter').addEventListener('change', loadApplications);
document.getElementById('fees-refresh').addEventListener('click', loadFees);
document.getElementById('fee-status-filter').addEventListener('change', loadFees);
document.getElementById('inv-refresh').addEventListener('click', loadInvitations);
document.getElementById('inv-status-filter').addEventListener('change', loadInvitations);
document.getElementById('hotel-refresh').addEventListener('click', loadHotel);
document.getElementById('hotel-status-filter').addEventListener('change', loadHotel);
document.getElementById('theses-refresh').addEventListener('click', loadTheses);

/* ------------------------------------------------------------------ */
/* Старт                                                              */
/* ------------------------------------------------------------------ */
(async function init() {
  loadHealth();
  try {
    await loadReport();
    await loadDictionaries();
    await loadApplications();
  } catch (error) {
    toast(`${error.code}: ${error.message}`, true);
  }
})();
