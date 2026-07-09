(function () {
  function syncLoadingClass() {
    var hasHomeLoader = !!document.querySelector('.home-loading-shell');
    var dashboardContainer = document.querySelector('#dashboard-container');
    if (dashboardContainer) {
      dashboardContainer.classList.toggle('app-loading-home', hasHomeLoader);
    }
  }

  var observer = new MutationObserver(syncLoadingClass);

  function start() {
    syncLoadingClass();
    observer.observe(document.documentElement, {
      childList: true,
      subtree: true,
      attributes: false
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start, { once: true });
  } else {
    start();
  }
})();
