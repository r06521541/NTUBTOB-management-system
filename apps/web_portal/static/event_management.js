(() => {
  const dialog = document.querySelector("[data-event-confirm-dialog]");
  const forms = document.querySelectorAll("form[data-event-confirm]");
  if (!dialog || forms.length === 0) return;
  const message = dialog.querySelector("[data-event-confirm-message]");
  const cancel = dialog.querySelector("[data-event-confirm-cancel]");
  const confirm = dialog.querySelector("[data-event-confirm-submit]");
  if (!message || !cancel || !confirm) return;
  let pending = null;
  let confirmed = null;
  forms.forEach((form) => {
    if (form.querySelector('input[name="request_id"]')) return;
    const input = document.createElement("input");
    input.type = "hidden";
    input.name = "request_id";
    input.value =
      typeof crypto.randomUUID === "function"
        ? crypto.randomUUID()
        : Array.from(crypto.getRandomValues(new Uint8Array(16)), (value) =>
            value.toString(16).padStart(2, "0"),
          ).join("");
    form.appendChild(input);
  });
  const close = (restore = true) => {
    const submitter = pending && pending.submitter;
    if (typeof dialog.close === "function" && dialog.open) dialog.close();
    else dialog.removeAttribute("open");
    dialog.removeAttribute("data-fallback-open");
    pending = null;
    if (restore && submitter && typeof submitter.focus === "function") submitter.focus();
  };
  forms.forEach((form) => form.addEventListener("submit", (event) => {
    if (confirmed && confirmed.form === form && confirmed.submitter === event.submitter) return;
    event.preventDefault();
    if (!event.submitter || pending) return;
    pending = { form, submitter: event.submitter };
    message.textContent = form.dataset.eventConfirm || "請確認這次操作。";
    if (typeof dialog.showModal === "function") dialog.showModal();
    else { dialog.setAttribute("open", ""); dialog.setAttribute("data-fallback-open", "true"); }
    confirm.focus();
  }));
  cancel.addEventListener("click", () => close());
  dialog.addEventListener("cancel", (event) => { event.preventDefault(); close(); });
  dialog.addEventListener("click", (event) => { if (event.target === dialog) close(); });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && dialog.hasAttribute("data-fallback-open")) { event.preventDefault(); close(); }
  });
  confirm.addEventListener("click", () => {
    if (!pending || confirmed) return;
    const submission = pending;
    close(false);
    confirmed = submission;
    try { submission.form.requestSubmit(submission.submitter); } finally { confirmed = null; }
  });
  forms.forEach((form) => form.querySelectorAll('button[type="submit"]').forEach((button) => { button.disabled = false; }));
})();
