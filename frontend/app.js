const form = document.querySelector('#search-form');
const input = document.querySelector('#search-query');
const button = document.querySelector('#search-button');
const buttonLabel = document.querySelector('#button-label');
const status = document.querySelector('#status');
const copiedPanel = document.querySelector('#copied-panel');
const copiedUrl = document.querySelector('#copied-url');

function setLoading(loading) {
  button.disabled = loading;
  buttonLabel.textContent = loading ? '検索中...' : '検索する';
}

function textElement(tag, className, text) {
  const element = document.createElement(tag);
  element.className = className;
  element.textContent = text;
  return element;
}

function showError(message) {
  status.replaceChildren(textElement('div', 'error', message));
}

function renderResults(payload) {
  if (!payload.results.length) {
    const empty = document.createElement('div');
    empty.className = 'empty-state';
    empty.append(textElement('div', 'empty-icon', '⌕'), textElement('h2', '', '検索結果が見つかりませんでした'), textElement('p', '', '別の検索語をお試しください。'));
    status.replaceChildren(empty);
    return;
  }

  const heading = document.createElement('div');
  heading.className = 'results-heading';
  heading.append(textElement('h2', '', '検索結果'), textElement('span', 'results-count', `${payload.results.length}件`));
  const grid = document.createElement('div');
  grid.className = 'grid';
  payload.results.forEach((result, index) => grid.appendChild(createCard(result, index < 3)));
  status.replaceChildren(heading, grid);
}

function createCard(result, eager) {
  const card = document.createElement('article');
  card.className = 'card';
  card.tabIndex = 0;
  card.setAttribute('role', 'button');
  card.setAttribute('aria-label', `${result.title} のURLをコピー`);
  const image = document.createElement('img');
  image.className = 'thumb';
  image.alt = '';
  image.loading = eager ? 'eager' : 'lazy';
  image.src = result.thumbnailUrl || '';
  if (!result.thumbnailUrl) image.style.visibility = 'hidden';
  const body = document.createElement('div');
  body.className = 'card-body';
  body.appendChild(textElement('p', 'card-title', result.title));
  const meta = document.createElement('div');
  meta.className = 'meta';
  [result.views, result.added, result.duration].filter(Boolean).forEach((value) => meta.appendChild(textElement('span', '', value)));
  body.appendChild(meta);
  if (result.uploader) body.appendChild(textElement('p', 'meta', result.uploader));
  body.appendChild(textElement('p', 'copy-hint', 'クリックしてURLをコピー'));
  card.append(image, body);
  const copy = () => copyUrl(result.url);
  card.addEventListener('click', copy);
  card.addEventListener('keydown', (event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); copy(); } });
  return card;
}

async function copyUrl(url) {
  try {
    if (navigator.clipboard && window.isSecureContext) await navigator.clipboard.writeText(url);
    else {
      const textarea = document.createElement('textarea');
      textarea.value = url;
      textarea.style.position = 'fixed';
      textarea.style.opacity = '0';
      document.body.appendChild(textarea);
      textarea.select();
      if (!document.execCommand('copy')) throw new Error('copy failed');
      textarea.remove();
    }
    copiedUrl.textContent = url;
    copiedPanel.hidden = false;
    copiedPanel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  } catch {
    showError('自動コピーできませんでした。表示されたURLを手動でコピーしてください。');
  }
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const query = input.value.trim();
  if (!query) return;
  setLoading(true);
  copiedPanel.hidden = true;
  try {
    const response = await fetch(`/api/search?${new URLSearchParams({ query, page: '1' })}`);
    const contentType = response.headers.get('content-type') || '';
    const responseText = await response.text();
    let payload = null;
    if (contentType.includes('application/json')) {
      try { payload = JSON.parse(responseText); } catch { payload = null; }
    }
    if (!payload) {
      const statusText = response.status ? `（HTTP ${response.status}）` : '';
      throw new Error(`検索サーバーが一時的に応答できません。時間を置いて再試行してください。${statusText}`);
    }
    if (!response.ok) throw new Error(payload.detail || '検索結果を取得できませんでした。');
    renderResults(payload);
  } catch (error) {
    showError(error.message || '検索中にエラーが発生しました。');
  } finally {
    setLoading(false);
  }
});
