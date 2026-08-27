(() => {
  const dialog = document.querySelector("[data-dashboard-reply-dialog]");
  const forms = document.querySelectorAll("[data-dashboard-reply-form]");
  if (!dialog || forms.length === 0) return;

  const gameLabel = dialog.querySelector("[data-dashboard-reply-game]");
  const statusLabel = dialog.querySelector("[data-dashboard-reply-status]");
  const cancelButton = dialog.querySelector("[data-dashboard-reply-cancel]");
  const confirmButton = dialog.querySelector("[data-dashboard-reply-confirm]");
  if (!gameLabel || !statusLabel || !cancelButton || !confirmButton) return;
  let pending = null;
  let confirmedSubmission = null;

  const restoreFocus = (initiator) => {
    if (initiator && typeof initiator.focus === "function") initiator.focus();
  };

  const clearPending = (shouldRestoreFocus) => {
    const initiator = pending ? pending.submitter : null;
    pending = null;
    dialog.removeAttribute("data-fallback-open");
    if (shouldRestoreFocus) restoreFocus(initiator);
  };

  const closeDialog = (shouldRestoreFocus = true) => {
    if (typeof dialog.close === "function" && dialog.open) {
      dialog.close();
    } else {
      dialog.removeAttribute("open");
    }
    clearPending(shouldRestoreFocus);
  };

  const openDialog = (form, submitter) => {
    pending = { form, submitter };
    gameLabel.textContent = form.dataset.gameLabel || "這場賽事";
    statusLabel.textContent =
      submitter.dataset.replyLabel || submitter.textContent.trim();
    if (typeof dialog.showModal === "function") {
      dialog.showModal();
    } else {
      dialog.setAttribute("open", "");
      dialog.setAttribute("data-fallback-open", "true");
    }
    confirmButton.focus();
  };

  forms.forEach((form) => {
    form.addEventListener("submit", (event) => {
      const submitter = event.submitter;
      if (
        confirmedSubmission &&
        confirmedSubmission.form === form &&
        confirmedSubmission.submitter === submitter
      ) {
        return;
      }
      event.preventDefault();
      if (!submitter || pending) return;
      openDialog(form, submitter);
    });
  });

  cancelButton.addEventListener("click", () => closeDialog());
  dialog.addEventListener("cancel", (event) => {
    event.preventDefault();
    closeDialog();
  });
  dialog.addEventListener("close", () => {
    if (pending) clearPending(true);
  });
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) closeDialog();
  });
  document.addEventListener("keydown", (event) => {
    if (!dialog.hasAttribute("data-fallback-open")) return;
    if (event.key === "Escape") {
      event.preventDefault();
      closeDialog();
    } else if (event.key === "Tab") {
      const movingBackward =
        event.shiftKey && document.activeElement === cancelButton;
      const movingForward =
        !event.shiftKey && document.activeElement === confirmButton;
      if (movingBackward || movingForward) {
        event.preventDefault();
        (movingBackward ? confirmButton : cancelButton).focus();
      }
    }
  });

  confirmButton.addEventListener("click", () => {
    if (!pending || confirmedSubmission) return;
    const { form, submitter } = pending;
    closeDialog(false);
    confirmedSubmission = { form, submitter };
    try {
      form.requestSubmit(submitter);
    } finally {
      confirmedSubmission = null;
    }
  });

  forms.forEach((form) => {
    form.querySelectorAll('button[type="submit"][name="reply"]').forEach((button) => {
      button.disabled = false;
    });
  });
})();
