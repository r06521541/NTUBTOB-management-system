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
    const battingOrderKey = `${prefix}${actorId}:game-${gameId}:batting-order`;
    const emptyCoarse = () => ({players: {}, coaches: []});
    const emptyFine = () => ({positions: {}, coaches: []});
    const emptyBattingOrder = () => ({slots: {}});

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
    let battingOrder = readState(battingOrderKey, emptyBattingOrder);

    function save() {
        sessionStorage.setItem(coarseKey, JSON.stringify(coarse));
        sessionStorage.setItem(fineKey, JSON.stringify(fine));
        sessionStorage.setItem(battingOrderKey, JSON.stringify(battingOrder));
    }

    function allStoredIds() {
        return new Set([
            ...Object.keys(coarse.players || {}),
            ...(coarse.coaches || []),
            ...Object.values(fine.positions || {}),
            ...(fine.coaches || []),
            ...Object.values(battingOrder.slots || {}),
        ].filter(Boolean));
    }

    function showStale() {
        const stale = [...allStoredIds()].filter((id) => !candidateById.has(id));
        const panel = document.getElementById("lineup-stale");
        if (!panel) return stale;
        panel.hidden = stale.length === 0;
        const staleList = document.getElementById("lineup-stale-list");
        if (staleList) {
            staleList.textContent = stale.length
                ? `失效識別碼：${stale.join("、")}`
                : "";
        }
        return stale;
    }

    function name(id) {
        if (!id) return "";
        const candidate = candidateById.get(id);
        if (!candidate) return `已失效 ${id}`;
        return `${candidate.name}${candidate.member_number !== null && candidate.member_number !== undefined ? ` #${candidate.member_number}` : ""}`;
    }

    function plainName(id) {
        const candidate = candidateById.get(id);
        return candidate ? candidate.name : `已失效 ${id}`;
    }

    function assignedPosition(id) {
        return Object.entries(fine.positions || {}).find(
            (entry) => entry[1] === id
        )?.[0] || "";
    }

    function assignedBattingSlot(id) {
        return Object.entries(battingOrder.slots || {}).find(
            (entry) => entry[1] === id
        )?.[0] || "";
    }

    function replyLabel(reply) {
        return ({3: "晚到", 4: "早走", 2: "不到", 5: "不確定"})[reply] || "";
    }

    function summaryName(id) {
        return name(id);
    }

    function fineEligible(candidate) {
        return candidate?.reply === 1 || candidate?.reply === 4;
    }

    function coarseName(id) {
        const candidate = candidateById.get(id);
        if (!candidate) return plainName(id);
        const annotation = replyLabel(candidate.reply);
        return `${candidate.name}${annotation ? `（${annotation}）` : ""}`;
    }

    function statusRank(candidate) {
        return ({1: 0, 5: 1, 3: 2, 4: 3})[candidate?.reply] ?? 4;
    }

    function coarseSummary() {
        const labels = {
            pitcher: "投手",
            catcher: "捕手",
            infield: "內野",
            outfield: "外野",
        };
        const lines = [
            `教練：${(coarse.coaches || []).map(coarseName).join("、") || "—"}`,
        ];
        Object.entries(labels).forEach(([value, label]) => {
            const people = Object.entries(coarse.players || {})
                .filter((entry) => entry[1] === value)
                .sort((left, right) => {
                    return statusRank(candidateById.get(left[0])) - statusRank(candidateById.get(right[0]));
                })
                .map((entry) => coarseName(entry[0]));
            lines.push(`${label}：${people.join("、") || "—"}`);
        });
        const grouped = new Set([
            ...Object.keys(coarse.players || {}),
            ...(coarse.coaches || []),
        ]);
        const ungrouped = candidates
            .filter((candidate) => [1, 3, 4].includes(candidate.reply))
            .filter((candidate) => !grouped.has(candidate.id))
            .sort((left, right) => statusRank(left) - statusRank(right))
            .map((candidate) => coarseName(candidate.id));
        if (ungrouped.length) {
            lines.push(`尚未分組：${ungrouped.join("、")}`);
        }
        return lines.join("\n");
    }

    function battingOrderSummary() {
        const lines = [];
        for (let slot = 1; slot <= 9; slot += 1) {
            const id = battingOrder.slots?.[String(slot)];
            const position = assignedPosition(id);
            const annotation = replyLabel(candidateById.get(id)?.reply);
            lines.push(`${slot}棒：${id ? `${summaryName(id)}（${position}${annotation ? `・${annotation}` : ""}）` : "—"}`);
        }
        const battingIds = new Set(Object.values(battingOrder.slots || {}));
        const nonBattingPitcher = fine.positions?.DH ? fine.positions?.P : "";
        const waiting = Object.entries(fine.positions || {})
            .filter(([, id]) => {
                return id && id !== nonBattingPitcher && !battingIds.has(id);
            })
            .map(([position, id]) => {
                const annotation = replyLabel(candidateById.get(id)?.reply);
                return `${summaryName(id)}（${position}${annotation ? `・${annotation}` : ""}）`;
            });
        if (waiting.length) {
            lines.push(`尚未排入打序：${waiting.join("、")}`);
        }
        if (nonBattingPitcher) {
            const annotation = replyLabel(candidateById.get(nonBattingPitcher)?.reply);
            lines.push(`投手：${summaryName(nonBattingPitcher)}${annotation ? `（${annotation}）` : ""}`);
        }
        const assignedIds = new Set(Object.values(fine.positions || {}));
        const reserves = candidates
            .filter((candidate) => candidate.reply !== 2)
            .filter((candidate) => !assignedIds.has(candidate.id))
            .sort((left, right) => statusRank(left) - statusRank(right))
            .map((candidate) => {
                const annotation = replyLabel(candidate.reply);
                return `${name(candidate.id)}${annotation ? `（${annotation}）` : ""}`;
            });
        if (reserves.length) {
            lines.push(`預備球員：${reserves.join("、")}`);
        }
        return lines.join("\n");
    }

    function fineSummary() {
        return `先發打序：\n${battingOrderSummary()}`;
    }

    function refresh() {
        Object.keys(fine.positions || {}).forEach((position) => {
            if (!fineEligible(candidateById.get(fine.positions[position]))) {
                delete fine.positions[position];
            }
        });
        document.querySelectorAll("[data-coarse-role]").forEach((button) => {
            const id = button.dataset.candidateId;
            button.setAttribute(
                "aria-pressed",
                String(coarse.players?.[id] === button.dataset.coarseRole)
            );
        });
        document.querySelectorAll("[data-coarse-coach]").forEach((button) => {
            button.setAttribute(
                "aria-pressed",
                String((coarse.coaches || []).includes(button.dataset.coarseCoach))
            );
        });
        document.querySelectorAll("select[data-fine-position]").forEach((select) => {
            const selected = fine.positions?.[select.dataset.finePosition] || "";
            [...select.options].forEach((option) => {
                if (!option.value) return;
                const position = assignedPosition(option.value);
                option.textContent = `${plainName(option.value)}${position ? `（目前：${position}）` : ""}`;
            });
            select.value = selected;
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
        document.querySelectorAll("[data-field-player]").forEach((node) => {
            const id = fine.positions?.[node.dataset.fieldPlayer];
            const candidate = candidateById.get(id);
            node.textContent = candidate ? candidate.name : "點選安排";
        });
        document.querySelectorAll("[data-field-number]").forEach((node) => {
            const id = fine.positions?.[node.dataset.fieldNumber];
            const candidate = candidateById.get(id);
            node.textContent = candidate?.member_number !== null && candidate?.member_number !== undefined
                ? `#${candidate.member_number}`
                : "";
        });
        document.querySelectorAll("[data-field-status]").forEach((node) => {
            const id = fine.positions?.[node.dataset.fieldStatus];
            const candidate = candidateById.get(id);
            node.textContent = candidate?.reply === 4 ? "↗" : "";
            node.setAttribute("aria-label", candidate?.reply === 4 ? "早走" : "");
        });
        document.querySelectorAll("[data-batting-order]").forEach((select) => {
            const slot = select.dataset.battingOrder;
            const assignedIds = new Set(Object.values(fine.positions || {}));
            if (fine.positions?.DH && fine.positions?.P) {
                assignedIds.delete(fine.positions.P);
            }
            const current = battingOrder.slots?.[slot] || "";
            if (current && !assignedIds.has(current)) {
                delete battingOrder.slots[slot];
            }
            select.replaceChildren(new Option("未安排", ""));
            const battingCandidates = candidates.filter((candidate) => {
                const position = assignedPosition(candidate.id);
                return position && assignedIds.has(candidate.id) && fineEligible(candidate);
            });
            const unassignedBatters = battingCandidates.filter(
                (candidate) => !assignedBattingSlot(candidate.id)
            );
            const assignedBatters = battingCandidates.filter((candidate) =>
                assignedBattingSlot(candidate.id)
            );
            function appendBattingCandidate(candidate) {
                const position = assignedPosition(candidate.id);
                const battingSlot = assignedBattingSlot(candidate.id);
                const replyAnnotation = replyLabel(candidate.reply);
                const annotation = battingSlot
                    ? `${position}・第 ${battingSlot} 棒${replyAnnotation ? `・${replyAnnotation}` : ""}`
                    : `${position}${replyAnnotation ? `・${replyAnnotation}` : ""}`;
                select.add(new Option(`${candidate.name}（${annotation}）`, candidate.id));
            }
            unassignedBatters.forEach(appendBattingCandidate);
            if (assignedBatters.length) {
                const separator = new Option("──────── 以下已排入打序 ────────", "");
                separator.disabled = true;
                separator.dataset.battingSeparator = "true";
                select.add(separator);
            }
            assignedBatters.forEach(appendBattingCandidate);
            select.value = battingOrder.slots?.[slot] || "";
            select.closest(".portal-batting-slot")?.classList.toggle(
                "is-unassigned",
                !select.value
            );
            const visiblePlayer = document.querySelector(
                `[data-batting-player="${slot}"]`
            );
            if (visiblePlayer) {
                const selectedId = battingOrder.slots?.[slot] || "";
                const selectedCandidate = candidateById.get(selectedId);
                const selectedNumber = selectedCandidate?.member_number;
                const replyAnnotation = replyLabel(selectedCandidate?.reply);
                visiblePlayer.textContent = selectedCandidate
                    ? `${selectedCandidate.name}${selectedNumber !== null && selectedNumber !== undefined ? ` #${selectedNumber}` : ""}（${assignedPosition(selectedId)}${replyAnnotation ? `・${replyAnnotation}` : ""}）`
                    : "未安排";
            }
        });
        const nonBattingPitcher = fine.positions?.DH ? fine.positions?.P : "";
        const nonBattingPitcherCard = document.getElementById(
            "non-batting-pitcher"
        );
        if (nonBattingPitcherCard) {
            nonBattingPitcherCard.hidden = !nonBattingPitcher;
            const pitcherName = nonBattingPitcherCard.querySelector(
                "[data-non-batting-pitcher]"
            );
            if (pitcherName) {
                pitcherName.textContent = nonBattingPitcher
                    ? name(nonBattingPitcher)
                    : "未安排";
            }
        }
        document.getElementById("coarse-summary").textContent = coarseSummary();
        document.getElementById("fine-summary").textContent = fineSummary();
        save();
        showStale();
    }

    const dropdownMenu = document.getElementById("lineup-dropdown-menu");
    const fieldLayout = root.querySelector(".portal-field-layout");

    function closeFieldDropdown() {
        if (!dropdownMenu) return;
        dropdownMenu.hidden = true;
        dropdownMenu.innerHTML = "";
    }

    function assignFinePosition(position, selected) {
        fine.positions = fine.positions || {};
        Object.keys(fine.positions).forEach((otherPosition) => {
            if (fine.positions[otherPosition] === selected) {
                delete fine.positions[otherPosition];
            }
        });
        if (selected) fine.positions[position] = selected;
        else delete fine.positions[position];
        refresh();
        return true;
    }

    function openFieldDropdown(targetPosition, anchor) {
        if (!dropdownMenu || !fieldLayout) return;
        const rect = anchor.getBoundingClientRect();
        const containerRect = fieldLayout.getBoundingClientRect();
        const top = rect.bottom - containerRect.top + 8;
        const left = rect.left - containerRect.left;
        dropdownMenu.style.top = `${top}px`;
        dropdownMenu.style.left = `${left}px`;
        dropdownMenu.hidden = false;
        dropdownMenu.innerHTML = "";

        const eligibleCandidates = candidates.filter(fineEligible);
        const unassignedCandidates = eligibleCandidates.filter(
            (candidate) => !assignedPosition(candidate.id)
        );
        const assignedCandidates = eligibleCandidates.filter((candidate) =>
            assignedPosition(candidate.id)
        );

        function appendCandidate(candidate) {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "portal-dropdown-item";
            const currentPosition = assignedPosition(candidate.id);
            const replyAnnotation = replyLabel(candidate.reply);
            button.textContent = `${candidate.name}${currentPosition ? `（${currentPosition}${replyAnnotation ? `・${replyAnnotation}` : ""}）` : replyAnnotation ? `（${replyAnnotation}）` : ""}`;
            button.addEventListener("click", () => {
                closeFieldDropdown();
                assignFinePosition(targetPosition, candidate.id);
            });
            dropdownMenu.appendChild(button);
        }

        unassignedCandidates.forEach(appendCandidate);
        if (unassignedCandidates.length && assignedCandidates.length) {
            const separator = document.createElement("div");
            separator.className = "portal-dropdown-separator";
            separator.setAttribute("role", "separator");
            separator.setAttribute("aria-label", "以下球員已有守位");
            dropdownMenu.appendChild(separator);
        }
        assignedCandidates.forEach(appendCandidate);
    }

    function activateFieldPosition(position, node) {
        if (fine.positions?.[position]) {
            closeFieldDropdown();
            assignFinePosition(position, "");
            return;
        }
        openFieldDropdown(position, node);
    }

    document.addEventListener("click", (event) => {
        if (!dropdownMenu) return;
        if (
            dropdownMenu.hidden ||
            dropdownMenu.contains(event.target) ||
            event.target.closest("[data-field-position][data-fine-position]")
        ) {
            return;
        }
        closeFieldDropdown();
    });

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            closeFieldDropdown();
        }
    });

    document.querySelectorAll("[data-field-position][data-fine-position]").forEach((node) => {
        const position = node.dataset.finePosition;
        node.addEventListener("click", () => activateFieldPosition(position, node));
        node.addEventListener("keydown", (event) => {
            if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                activateFieldPosition(position, node);
            }
        });
    });

    document.querySelectorAll("[data-coarse-role]").forEach((button) => {
        button.addEventListener("click", () => {
            const id = button.dataset.candidateId;
            const role = button.dataset.coarseRole;
            const current = coarse.players?.[id];
            if (current === role) {
                delete coarse.players[id];
            } else {
                coarse.players = coarse.players || {};
                coarse.players[id] = role;
            }
            refresh();
        });
    });
    document.querySelectorAll("[data-coarse-coach]").forEach((button) => {
        button.addEventListener("click", () => {
            const id = button.dataset.coarseCoach;
            const checked = (coarse.coaches || []).includes(id);
            coarse.coaches = (coarse.coaches || []).filter((value) => value !== id);
            if (!checked) {
                coarse.coaches.push(id);
            }
            refresh();
        });
    });
    document.querySelectorAll("[data-fine-position]").forEach((select) => {
        select.addEventListener("change", () => {
            const position = select.dataset.finePosition;
            const selected = select.value;
            if (!assignFinePosition(position, selected)) {
                select.value = fine.positions?.[position] || "";
            }
        });
    });
    document.querySelectorAll("[data-batting-order]").forEach((select) => {
        select.addEventListener("change", () => {
            const slot = select.dataset.battingOrder;
            const selected = select.value;
            Object.keys(battingOrder.slots || {}).forEach((otherSlot) => {
                if (battingOrder.slots[otherSlot] === selected && otherSlot !== slot) {
                    delete battingOrder.slots[otherSlot];
                }
            });
            if (selected) battingOrder.slots[slot] = selected;
            else delete battingOrder.slots[slot];
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
        battingOrder = emptyBattingOrder();
        refresh();
    });
    document.getElementById("clear-all-lineups").addEventListener("click", () => {
        coarse = emptyCoarse();
        fine = emptyFine();
        battingOrder = emptyBattingOrder();
        refresh();
    });
    const removeStaleButton = document.getElementById("remove-stale");
    if (removeStaleButton) {
        removeStaleButton.addEventListener("click", () => {
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
    }
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
