(() => {
    "use strict";

    const prefix = "ntubtob-lineup-v1:";
    const identityMarker = `${prefix}identity`;
    const currentIdentity = document.body.dataset.lineupIdentity || "";

    function clearLineups() {
        Object.keys(sessionStorage)
            .filter((key) => key.startsWith(prefix))
            .forEach((key) => sessionStorage.removeItem(key));
    }

    document.querySelectorAll("[data-clear-lineup-storage]").forEach((form) => {
        form.addEventListener("submit", clearLineups);
    });

    if (currentIdentity) {
        const previousIdentity = sessionStorage.getItem(identityMarker);
        if (previousIdentity && previousIdentity !== currentIdentity) {
            clearLineups();
        }
        sessionStorage.setItem(identityMarker, currentIdentity);
    }

    const root = document.getElementById("lineup-lab");
    if (!root) return;

    const candidates = JSON.parse(
        document.getElementById("lineup-candidates").textContent
    );
    const candidateById = new Map(candidates.map((item) => [item.id, item]));
    const gameId = root.dataset.gameId;
    const actorId = root.dataset.actorPersonId;
    const coarseKey = `${prefix}${actorId}:game-${gameId}:coarse`;
    const fineKey = `${prefix}${actorId}:game-${gameId}:fine`;
    const emptyCoarse = () => ({players: {}, coaches: []});
    const emptyFine = () => ({positions: {}, coaches: []});

    function readState(key, fallback) {
        try {
            const parsed = JSON.parse(sessionStorage.getItem(key));
            return parsed && typeof parsed === "object" ? parsed : fallback();
        } catch (_error) {
            return fallback();
        }
    }

    let coarse = readState(coarseKey, emptyCoarse);
    let fine = readState(fineKey, emptyFine);

    function save() {
        sessionStorage.setItem(coarseKey, JSON.stringify(coarse));
        sessionStorage.setItem(fineKey, JSON.stringify(fine));
    }

    function allStoredIds() {
        return new Set([
            ...Object.keys(coarse.players || {}),
            ...(coarse.coaches || []),
            ...Object.values(fine.positions || {}),
            ...(fine.coaches || []),
        ].filter(Boolean));
    }

    function showStale() {
        const stale = [...allStoredIds()].filter((id) => !candidateById.has(id));
        const panel = document.getElementById("lineup-stale");
        panel.hidden = stale.length === 0;
        document.getElementById("lineup-stale-list").textContent = stale.length
            ? `失效識別碼：${stale.join("、")}`
            : "";
        return stale;
    }

    function name(id) {
        if (!id) return "";
        return candidateById.get(id)?.name || `已失效 ${id}`;
    }

    function coarseSummary() {
        const labels = {
            pitcher: "投手",
            catcher: "捕手",
            infield: "內野",
            outfield: "外野",
        };
        const lines = [
            `教練：${(coarse.coaches || []).map(name).join("、") || "—"}`,
        ];
        Object.entries(labels).forEach(([value, label]) => {
            const people = Object.entries(coarse.players || {})
                .filter((entry) => entry[1] === value)
                .map((entry) => name(entry[0]));
            lines.push(`${label}：${people.join("、") || "—"}`);
        });
        return lines.join("\n");
    }

    function fineSummary() {
        const order = ["P", "C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH"];
        const lines = order.map(
            (position) => `${position}：${name(fine.positions?.[position]) || "—"}`
        );
        lines.push(`教練：${(fine.coaches || []).map(name).join("、") || "—"}`);
        return lines.join("\n");
    }

    function refresh() {
        document.querySelectorAll("[data-coarse-player]").forEach((select) => {
            select.value = coarse.players?.[select.dataset.coarsePlayer] || "";
        });
        document.querySelectorAll("[data-coarse-coach]").forEach((checkbox) => {
            checkbox.checked = (coarse.coaches || []).includes(
                checkbox.dataset.coarseCoach
            );
        });
        document.querySelectorAll("[data-fine-position]").forEach((select) => {
            select.value = fine.positions?.[select.dataset.finePosition] || "";
        });
        document.querySelectorAll("[data-fine-coach]").forEach((checkbox) => {
            checkbox.checked = (fine.coaches || []).includes(
                checkbox.dataset.fineCoach
            );
        });
        document.querySelectorAll("[data-field-position]").forEach((node) => {
            const id = fine.positions?.[node.dataset.fieldPosition];
            node.classList.toggle("is-filled", Boolean(id));
            node.setAttribute(
                "aria-label",
                `${node.dataset.fieldPosition}：${id ? name(id) : "未安排"}`
            );
        });
        document.getElementById("coarse-summary").textContent = coarseSummary();
        document.getElementById("fine-summary").textContent = fineSummary();
        showStale();
        save();
    }

    document.querySelectorAll("[data-coarse-player]").forEach((select) => {
        select.addEventListener("change", () => {
            const id = select.dataset.coarsePlayer;
            if (select.value) coarse.players[id] = select.value;
            else delete coarse.players[id];
            refresh();
        });
    });
    document.querySelectorAll("[data-coarse-coach]").forEach((checkbox) => {
        checkbox.addEventListener("change", () => {
            const id = checkbox.dataset.coarseCoach;
            coarse.coaches = (coarse.coaches || []).filter((value) => value !== id);
            if (checkbox.checked) coarse.coaches.push(id);
            refresh();
        });
    });
    document.querySelectorAll("[data-fine-position]").forEach((select) => {
        select.addEventListener("change", () => {
            const position = select.dataset.finePosition;
            const selected = select.value;
            const displaced = fine.positions?.[position];
            if (
                selected &&
                displaced &&
                selected !== displaced &&
                !window.confirm(`以 ${name(selected)} 取代 ${name(displaced)}？`)
            ) {
                select.value = displaced;
                return;
            }
            Object.keys(fine.positions || {}).forEach((otherPosition) => {
                if (fine.positions[otherPosition] === selected) {
                    delete fine.positions[otherPosition];
                }
            });
            if (selected) fine.positions[position] = selected;
            else delete fine.positions[position];
            refresh();
        });
    });
    document.querySelectorAll("[data-fine-coach]").forEach((checkbox) => {
        checkbox.addEventListener("change", () => {
            const id = checkbox.dataset.fineCoach;
            fine.coaches = (fine.coaches || []).filter((value) => value !== id);
            if (checkbox.checked) fine.coaches.push(id);
            refresh();
        });
    });
    document.querySelectorAll("[data-lineup-mode]").forEach((button) => {
        button.addEventListener("click", () => {
            const fineMode = button.dataset.lineupMode === "fine";
            document.getElementById("coarse-lineup").hidden = fineMode;
            document.getElementById("fine-lineup").hidden = !fineMode;
            document.querySelectorAll("[data-lineup-mode]").forEach((item) => {
                item.setAttribute(
                    "aria-pressed",
                    String(item.dataset.lineupMode === button.dataset.lineupMode)
                );
            });
        });
    });
    document.getElementById("reset-coarse").addEventListener("click", () => {
        coarse = emptyCoarse();
        refresh();
    });
    document.getElementById("reset-fine").addEventListener("click", () => {
        fine = emptyFine();
        refresh();
    });
    document.getElementById("clear-all-lineups").addEventListener("click", () => {
        coarse = emptyCoarse();
        fine = emptyFine();
        refresh();
    });
    document.getElementById("remove-stale").addEventListener("click", () => {
        const stale = new Set(showStale());
        Object.keys(coarse.players || {}).forEach((id) => {
            if (stale.has(id)) delete coarse.players[id];
        });
        coarse.coaches = (coarse.coaches || []).filter((id) => !stale.has(id));
        Object.keys(fine.positions || {}).forEach((position) => {
            if (stale.has(fine.positions[position])) delete fine.positions[position];
        });
        fine.coaches = (fine.coaches || []).filter((id) => !stale.has(id));
        refresh();
    });
    document.querySelectorAll("[data-copy-summary]").forEach((button) => {
        button.addEventListener("click", async () => {
            const summary = button.dataset.copySummary === "fine"
                ? fineSummary()
                : coarseSummary();
            try {
                await navigator.clipboard.writeText(summary);
                button.textContent = "已複製";
            } catch (_error) {
                button.textContent = "瀏覽器不允許複製";
            }
        });
    });
    refresh();
})();
