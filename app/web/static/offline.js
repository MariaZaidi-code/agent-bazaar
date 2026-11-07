(function () {
  var status = document.getElementById("offline-status");
  var retry = document.getElementById("offline-retry");

  function updateStatus() {
    if (!status) return;
    status.textContent = navigator.onLine
      ? "Connection restored. Try again to continue."
      : "Waiting for a connection.";
  }

  if (retry) {
    retry.addEventListener("click", function () {
      if (!navigator.onLine) {
        updateStatus();
        return;
      }
      window.location.reload();
    });
  }

  window.addEventListener("online", updateStatus);
  window.addEventListener("offline", updateStatus);
  updateStatus();
})();
