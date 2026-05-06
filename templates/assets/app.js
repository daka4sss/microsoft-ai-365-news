// Microsoft AI 365 - Client-side enhancements

function toggleTheme() {
  const body = document.body;
  const next = body.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
  body.setAttribute('data-theme', next);
  try { localStorage.setItem('ai365-theme', next); } catch(e) {}
}

// Restore theme on load
(function() {
  try {
    const saved = localStorage.getItem('ai365-theme');
    if (saved) document.body.setAttribute('data-theme', saved);
  } catch(e) {}
})();
