// Microsoft AI 365 - Client-side enhancements

// ===== Theme =====
function toggleTheme() {
  const body = document.body;
  const next = body.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
  body.setAttribute('data-theme', next);
  try { localStorage.setItem('ai365-theme', next); } catch(e) {}
}

// Restore theme on load (runs before DOMContentLoaded to avoid flash)
(function() {
  try {
    const saved = localStorage.getItem('ai365-theme');
    if (saved) document.body.setAttribute('data-theme', saved);
  } catch(e) {}
})();

// ===== Filter (mutually exclusive: category | tag | all) =====
function setFilter(type, value) {
  const key = type === 'all' ? 'all' : `${type}:${value}`;
  try { localStorage.setItem('ai365-filter', key); } catch(e) {}

  const isAll = type === 'all';
  const isTag = type === 'tag';
  const isCat = type === 'category';

  // Top nav active state — only highlight when filtering by category (or "all")
  document.querySelectorAll('.cat-nav a[data-filter]').forEach(a => {
    const active = !isTag && (isAll ? a.dataset.filter === 'all' : a.dataset.filter === value);
    a.classList.toggle('active', active);
  });

  // Sidebar tag pill active state
  document.querySelectorAll('.tag-pill[data-tag]').forEach(p => {
    p.classList.toggle('active', isTag && p.dataset.tag === value);
  });

  const matches = el => {
    if (isAll) return true;
    if (isTag) {
      const tags = (el.dataset.tags || '').split('|').filter(Boolean);
      return tags.includes(value);
    }
    if (isCat) {
      return el.dataset.category === value;
    }
    return true;
  };

  document.querySelectorAll('.story[data-category]').forEach(el => {
    el.style.display = matches(el) ? '' : 'none';
  });

  const featured = document.querySelector('.featured[data-category]');
  if (featured) {
    featured.style.display = matches(featured) ? '' : 'none';
  }

  // "No results" message per stories-grid
  document.querySelectorAll('.stories-grid').forEach(grid => {
    const visible = [...grid.querySelectorAll('.story')].filter(s => s.style.display !== 'none').length;
    let msg = grid.querySelector('.filter-empty');
    if (!msg) {
      msg = document.createElement('p');
      msg.className = 'filter-empty empty-state';
      msg.style.gridColumn = '1 / -1';
      grid.appendChild(msg);
    }
    msg.textContent = isTag
      ? `#${value} に一致する記事はありません。`
      : 'このカテゴリーの記事はありません。';
    msg.style.display = (!isAll && visible === 0) ? '' : 'none';
  });
}

// ===== New Article Tracking =====
let seenUrls = new Set();

function loadSeenUrls() {
  try {
    const raw = localStorage.getItem('ai365-seen-urls');
    const parsed = raw ? JSON.parse(raw) : [];
    seenUrls = new Set(parsed);
  } catch(e) {
    seenUrls = new Set();
  }
}

function saveSeenUrls() {
  try {
    localStorage.setItem('ai365-seen-urls', JSON.stringify([...seenUrls]));
  } catch(e) {}
}

function markSeen(url) {
  seenUrls.add(url);
  saveSeenUrls();
  const el = document.querySelector(`.story[data-url="${CSS.escape(url)}"], .featured[data-url="${CSS.escape(url)}"]`);
  if (el) el.classList.remove('is-new');
  updateReadBtn();
}

function markAllRead() {
  document.querySelectorAll('.is-new[data-url]').forEach(el => {
    seenUrls.add(el.dataset.url);
    el.classList.remove('is-new');
  });
  saveSeenUrls();
  updateReadBtn();
}

function updateReadBtn() {
  const count = document.querySelectorAll('.is-new').length;
  const btn = document.getElementById('mark-all-read');
  if (!btn) return;
  btn.textContent = `✓ ${count}件 既読にする`;
  btn.style.display = count > 0 ? '' : 'none';
}

function initNewArticles() {
  loadSeenUrls();

  // Collect current page URLs for pruning
  const currentUrls = new Set(
    [...document.querySelectorAll('[data-url]')].map(el => el.dataset.url)
  );
  // Prune seen set to only URLs present on this page (prevents unbounded growth)
  seenUrls = new Set([...seenUrls].filter(url => currentUrls.has(url)));
  saveSeenUrls();

  // Mark unseen articles
  document.querySelectorAll('[data-url]').forEach(el => {
    if (!seenUrls.has(el.dataset.url)) {
      el.classList.add('is-new');
    }
  });

  // Mark as seen on headline click
  document.querySelectorAll('.story-headline a, .featured-headline a').forEach(a => {
    a.addEventListener('click', () => {
      const article = a.closest('[data-url]');
      if (article) markSeen(article.dataset.url);
    });
  });

  // Mark all read button
  const btn = document.getElementById('mark-all-read');
  if (btn) btn.addEventListener('click', markAllRead);

  updateReadBtn();
}

// ===== Init =====
document.addEventListener('DOMContentLoaded', () => {
  initNewArticles();

  // Category nav → filter by category (data-filter="all" treated as type "all")
  const nav = document.querySelector('.cat-nav');
  if (nav) {
    nav.addEventListener('click', e => {
      const a = e.target.closest('a[data-filter]');
      if (!a) return;
      e.preventDefault();
      const v = a.dataset.filter;
      if (v === 'all') {
        setFilter('all');
      } else {
        setFilter('category', v);
      }
    });
  }

  // Sidebar tag pills → filter by tag, click again on active tag to clear
  document.addEventListener('click', e => {
    const pill = e.target.closest('.tag-pill[data-tag]');
    if (!pill) return;
    e.preventDefault();
    if (pill.classList.contains('active')) {
      setFilter('all');
    } else {
      setFilter('tag', pill.dataset.tag);
    }
  });

  // Restore saved filter
  try {
    const saved = localStorage.getItem('ai365-filter');
    if (saved) {
      if (saved === 'all') {
        setFilter('all');
      } else {
        const idx = saved.indexOf(':');
        if (idx > 0) {
          const type = saved.slice(0, idx);
          const value = saved.slice(idx + 1);
          if (type === 'category' || type === 'tag') {
            setFilter(type, value);
          }
        }
      }
    }
  } catch(e) {}
});
