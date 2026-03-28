(function () {
    "use strict";

    // ── Element references ───────────────────────────────────────────────────
    const draftTextarea   = document.getElementById("message-draft");
    const charCounter     = document.getElementById("char-counter");
    const improveBtn      = document.getElementById("improve-btn");
    const broadcastForm   = document.getElementById("broadcast-form");

    const modal           = document.getElementById("improve-modal");
    const modalCloseBtn   = document.getElementById("modal-close-btn");
    const originalText    = document.getElementById("original-text");
    const improvedText    = document.getElementById("improved-text");
    const improvedEditor  = document.getElementById("improved-editor");

    const acceptBtn       = document.getElementById("accept-btn");
    const editBtn         = document.getElementById("edit-btn");
    const saveEditBtn     = document.getElementById("save-edit-btn");
    const rejectBtn       = document.getElementById("reject-btn");

    const spinnerOverlay  = document.getElementById("spinner-overlay");
    const toast           = document.getElementById("toast");
    const toastMsg        = document.getElementById("toast-msg");

    // ── State ────────────────────────────────────────────────────────────────
    let currentImproved = "";
    let currentLanguage = "ar";
    let toastTimer;

    // ── Character counter ────────────────────────────────────────────────────
    function updateCharCount() {
        charCounter.textContent = draftTextarea.value.length;
    }

    draftTextarea.addEventListener("input", updateCharCount);

    // ── Spinner helpers ──────────────────────────────────────────────────────
    function showSpinner() {
        spinnerOverlay.hidden = false;
        improveBtn.disabled = true;
    }

    function hideSpinner() {
        spinnerOverlay.hidden = true;
        improveBtn.disabled = false;
    }

    // ── Toast helper ─────────────────────────────────────────────────────────
    function showToast(msg) {
        toastMsg.textContent = msg;
        toast.classList.remove("hidden");
        clearTimeout(toastTimer);
        toastTimer = setTimeout(function () { toast.classList.add("hidden"); }, 4000);
    }

    // ── Modal helpers ────────────────────────────────────────────────────────
    function openModal() {
        modal.hidden = false;
        modalCloseBtn.focus();
    }

    function closeModal() {
        modal.hidden = true;
        resetModalEditMode();
        draftTextarea.focus();
    }

    function resetModalEditMode() {
        improvedText.hidden    = false;
        improvedEditor.hidden  = true;
        editBtn.hidden         = false;
        saveEditBtn.hidden     = true;
    }

    // ── Direction helper ─────────────────────────────────────────────────────
    function applyPanelDirection(lang) {
        const dir = lang === "ar" ? "rtl" : "ltr";
        originalText.setAttribute("dir", dir);
        improvedText.setAttribute("dir", dir);
        improvedEditor.setAttribute("dir", dir);
    }

    // ── Improve API call ─────────────────────────────────────────────────────
    async function requestImprovement() {
        const draft = draftTextarea.value.trim();

        if (!draft) {
            showToast("⚠️ الرجاء كتابة رسالة أولاً قبل طلب التحسين.");
            return;
        }
        if (draft.length > 2000) {
            showToast("⚠️ الرسالة تتجاوز 2000 حرف. يرجى تقصيرها.");
            return;
        }

        showSpinner();

        try {
            const response = await fetch("/broadcast/improve", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ message: draft }),
            });

            if (!response.ok) {
                let detail = "فشل تحسين الرسالة. حاولي مرة أخرى.";
                try {
                    const errData = await response.json();
                    if (errData && errData.detail) detail = errData.detail;
                } catch (_) { /* ignore */ }
                showToast("⚠️ " + detail);
                return;
            }

            const data = await response.json();

            if (
                typeof data.original !== "string" ||
                typeof data.improved !== "string" ||
                typeof data.language !== "string"
            ) {
                showToast("⚠️ استجابة غير متوقعة من الخادم.");
                return;
            }

            currentImproved = data.improved;
            currentLanguage = data.language;

            originalText.textContent = data.original;
            improvedText.textContent = data.improved;
            improvedEditor.value     = data.improved;

            applyPanelDirection(data.language);
            resetModalEditMode();
            openModal();

        } catch (_) {
            showToast("⚠️ خطأ في الاتصال بالخادم. تحققي من الإنترنت وأعيدي المحاولة.");
        } finally {
            hideSpinner();
        }
    }

    improveBtn.addEventListener("click", requestImprovement);

    // ── Modal close ──────────────────────────────────────────────────────────
    modalCloseBtn.addEventListener("click", closeModal);

    modal.addEventListener("click", function (e) {
        if (e.target === modal) closeModal();
    });

    document.addEventListener("keydown", function (e) {
        if (e.key === "Escape" && !modal.hidden) closeModal();
    });

    // ── Accept ───────────────────────────────────────────────────────────────
    acceptBtn.addEventListener("click", function () {
        const finalText = improvedEditor.hidden
            ? currentImproved
            : improvedEditor.value.trim() || currentImproved;
        draftTextarea.value = finalText;
        updateCharCount();
        closeModal();
    });

    // ── Edit ─────────────────────────────────────────────────────────────────
    editBtn.addEventListener("click", function () {
        improvedText.hidden   = true;
        improvedEditor.hidden = false;
        editBtn.hidden        = true;
        saveEditBtn.hidden    = false;
        improvedEditor.focus();
    });

    // ── Save edit ────────────────────────────────────────────────────────────
    saveEditBtn.addEventListener("click", function () {
        const edited = improvedEditor.value.trim();
        if (!edited) {
            showToast("⚠️ لا يمكن حفظ نص فارغ.");
            return;
        }
        currentImproved          = edited;
        improvedText.textContent = edited;
        improvedText.hidden      = false;
        improvedEditor.hidden    = true;
        editBtn.hidden           = false;
        saveEditBtn.hidden       = true;
    });

    // ── Reject ───────────────────────────────────────────────────────────────
    rejectBtn.addEventListener("click", closeModal);

    // ── Broadcast form submit ─────────────────────────────────────────────────
    broadcastForm.addEventListener("submit", async function (e) {
        e.preventDefault();

        const draft = draftTextarea.value.trim();
        if (!draft) {
            showToast("⚠️ الرجاء كتابة رسالة قبل الإرسال.");
            return;
        }

        const segment   = document.getElementById("segment-select").value;
        const submitBtn = broadcastForm.querySelector("[type=submit]");
        submitBtn.disabled = true;

        try {
            const response = await fetch("/broadcast/send", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ message: draft, segment: segment }),
            });

            if (!response.ok) {
                let detail = "فشل إرسال الرسالة. حاولي مرة أخرى.";
                try {
                    const errData = await response.json();
                    if (errData && errData.detail) detail = errData.detail;
                } catch (_) { /* ignore */ }
                showToast("⚠️ " + detail);
            } else {
                draftTextarea.value = "";
                updateCharCount();
                showToast("✅ تم إرسال الرسالة بنجاح");
            }
        } catch (_) {
            showToast("⚠️ خطأ في الاتصال بالخادم.");
        } finally {
            submitBtn.disabled = false;
        }
    });

}());
