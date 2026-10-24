(function () {
  "use strict";

  document.body.dataset.preview = "true";

  document.addEventListener("click", function (event) {
    const docsLink = event.target.closest('a[href="/docs"]');
    if (!docsLink) return;
    event.preventDefault();
    const trigger = document.querySelector('[data-open-modal="docs-modal"]');
    if (trigger) trigger.click();
  });
})();
