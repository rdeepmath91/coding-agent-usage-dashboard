// Minimal color mode handler — respects system preference
(function() {
  const html = document.documentElement;
  const mq = window.matchMedia('(prefers-color-scheme: dark)');
  html.classList.toggle('dark', mq.matches);
  mq.addEventListener('change', e => html.classList.toggle('dark', e.matches));
})();