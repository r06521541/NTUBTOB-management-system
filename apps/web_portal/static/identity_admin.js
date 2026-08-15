(() => {
    "use strict";

    const root = document.getElementById("identity-admin-root");
    if (!root || typeof HTMLDialogElement === "undefined") return;

    root.querySelectorAll('form[method="post"]').forEach((form, index) => {
        const submit = form.querySelector('button[type="submit"], button:not([type])');
        if (!submit) return;
        const label = submit.textContent.trim() || "開啟操作";
        const dialog = document.createElement("dialog");
        dialog.className = "portal-action-dialog";
        dialog.setAttribute("aria-labelledby", `identity-dialog-title-${index}`);

        const heading = document.createElement("h3");
        heading.id = `identity-dialog-title-${index}`;
        heading.textContent = label;
        const cancel = document.createElement("button");
        cancel.type = "button";
        cancel.className = "portal-button portal-button-secondary";
        cancel.textContent = "取消";
        cancel.addEventListener("click", () => dialog.close());

        const trigger = document.createElement("button");
        trigger.type = "button";
        trigger.className = "portal-button portal-button-secondary portal-dialog-trigger";
        trigger.textContent = label;
        trigger.disabled = submit.disabled;
        trigger.addEventListener("click", () => dialog.showModal());

        form.before(trigger);
        form.replaceWith(dialog);
        dialog.append(heading, form, cancel);
    });
})();
