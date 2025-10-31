(() => {
  const config = window.quickRepliesConfig;
  if (!config) {
    return;
  }

  const oaListEl = document.getElementById("qr-oa-list");
  const newForm = document.getElementById("new-reply-form");
  const newFormSubmitBtn = newForm ? newForm.querySelector('button[type="submit"]') : null;
  const newScopeSelect = document.getElementById("new-line-account");
  const repliesContainer = document.getElementById("qr-replies-container");
  const emptyStateEl = document.getElementById("qr-empty-state");
  const emptyMessageEl = emptyStateEl ? emptyStateEl.querySelector("p") : null;
  const countBadge = document.getElementById("qr-count-badge");
  const listTitle = document.getElementById("qr-list-title");
  const listSubtitle = document.getElementById("qr-list-subtitle");
  const feedbackEl = document.getElementById("qr-feedback");
  const toastContainer = document.querySelector(".toast-container");

  const accounts = Array.isArray(config.accounts) ? config.accounts : [];
  const accountMap = new Map(accounts.map((account) => [String(account.id), account.name]));
  const globalKey = "global";
  const defaultEmptyMessage = emptyMessageEl ? emptyMessageEl.textContent : "";

  let currentKey =
    config.selectedAccountId !== null && config.selectedAccountId !== undefined
      ? String(config.selectedAccountId)
      : globalKey;

  function clearFeedback() {
    if (!feedbackEl) {
      return;
    }
    feedbackEl.classList.add("d-none");
    feedbackEl.classList.remove("alert-success", "alert-danger", "alert-warning", "alert-info");
    feedbackEl.textContent = "";
  }

  function showFeedback(message, type = "success") {
    if (feedbackEl) {
      feedbackEl.classList.remove("d-none");
      feedbackEl.classList.remove("alert-success", "alert-danger", "alert-warning", "alert-info");
      feedbackEl.classList.add(`alert-${type}`);
      feedbackEl.textContent = message;
    }
    showToast(type, message);
  }

  function showToast(type, message) {
    if (!toastContainer || !window.bootstrap) {
      return;
    }

    const icons = {
      success: "bi-check-circle-fill text-success",
      warning: "bi-exclamation-triangle-fill text-warning",
      danger: "bi-x-octagon-fill text-danger",
      info: "bi-info-circle-fill text-info",
    };

    const toast = document.createElement("div");
    toast.className = "toast app-toast";
    toast.setAttribute("role", "alert");
    toast.setAttribute("aria-live", "assertive");
    toast.setAttribute("aria-atomic", "true");
    toast.innerHTML = `
      <div class="toast-header">
        <i class="bi ${icons[type] || icons.info} me-2"></i>
        <strong class="me-auto">Notification</strong>
        <small>just now</small>
        <button type="button" class="btn-close" data-bs-dismiss="toast" aria-label="Close"></button>
      </div>
      <div class="toast-body">
        ${message}
      </div>
    `;

    toastContainer.appendChild(toast);
    const bsToast = new bootstrap.Toast(toast, { delay: 5000 });
    toast.addEventListener("hidden.bs.toast", () => toast.remove());
    bsToast.show();
  }

  function setLoadingState(isLoading) {
    if (!emptyStateEl || !emptyMessageEl) {
      return;
    }
    if (isLoading) {
      emptyStateEl.classList.remove("d-none");
      emptyMessageEl.textContent = "กำลังโหลดข้อมูล...";
    } else {
      emptyMessageEl.textContent = defaultEmptyMessage;
    }
  }

  function buildScopeOptions(selectEl, selectedValue) {
    if (!selectEl) {
      return;
    }
    selectEl.innerHTML = "";

    const globalOption = document.createElement("option");
    globalOption.value = "__None";
    globalOption.textContent = "Global (ทุก OA)";
    if (selectedValue === "__None") {
      globalOption.selected = true;
    }
    selectEl.appendChild(globalOption);

    accounts.forEach((account) => {
      const option = document.createElement("option");
      option.value = String(account.id);
      option.textContent = account.name;
      if (selectedValue === String(account.id)) {
        option.selected = true;
      }
      selectEl.appendChild(option);
    });
  }

  function syncNewFormScope() {
    if (!newScopeSelect) {
      return;
    }
    const defaultValue = currentKey === globalKey ? "__None" : currentKey;
    const exists = Array.from(newScopeSelect.options).some(
      (option) => option.value === defaultValue
    );
    if (exists) {
      newScopeSelect.value = defaultValue;
    }
  }

  function updateListHeadings() {
    if (!listTitle || !listSubtitle) {
      return;
    }
    if (currentKey === globalKey) {
      listTitle.textContent = "รายการ Quick Replies (Global)";
      listSubtitle.textContent = "รายการทั้งหมดที่ใช้ได้กับทุก OA";
    } else {
      const name = accountMap.get(currentKey) || "Line OA";
      listTitle.textContent = `รายการ Quick Replies - ${name}`;
      listSubtitle.textContent = "รวม Quick Reply ของ OA นี้ และ Global ที่ใช้ร่วมกัน";
    }
  }

  function getScopeLabel(reply) {
    if (reply.is_global || reply.line_account_id === null || reply.line_account_id === undefined) {
      return "Global - ใช้ได้ทุก OA";
    }
    const name = accountMap.get(String(reply.line_account_id));
    return name ? `เฉพาะ OA: ${name}` : "เฉพาะ OA ที่ระบุ";
  }

  function createReplyForm(reply) {
    const form = document.createElement("form");
    form.className = "qr-reply-item";
    form.dataset.replyId = String(reply.id);

    const csrfInput = document.createElement("input");
    csrfInput.type = "hidden";
    csrfInput.name = "csrf_token";
    csrfInput.value = config.csrfToken;
    form.appendChild(csrfInput);

    const fieldsWrapper = document.createElement("div");
    fieldsWrapper.className = "qr-reply-fields";
    form.appendChild(fieldsWrapper);

    const shortcutField = document.createElement("div");
    shortcutField.className = "qr-field";
    fieldsWrapper.appendChild(shortcutField);

    const shortcutLabel = document.createElement("label");
    shortcutLabel.className = "form-label";
    shortcutLabel.textContent = "Shortcut";
    shortcutLabel.setAttribute("for", `shortcut-${reply.id}`);
    shortcutField.appendChild(shortcutLabel);

    const shortcutInput = document.createElement("input");
    shortcutInput.type = "text";
    shortcutInput.className = "form-control form-control-sm";
    shortcutInput.id = `shortcut-${reply.id}`;
    shortcutInput.name = "shortcut";
    shortcutInput.required = true;
    shortcutInput.maxLength = 50;
    shortcutInput.value = reply.shortcut || "";
    shortcutField.appendChild(shortcutInput);

    const messageField = document.createElement("div");
    messageField.className = "qr-field";
    fieldsWrapper.appendChild(messageField);

    const messageLabel = document.createElement("label");
    messageLabel.className = "form-label";
    messageLabel.textContent = "Message";
    messageLabel.setAttribute("for", `message-${reply.id}`);
    messageField.appendChild(messageLabel);

    const messageInput = document.createElement("textarea");
    messageInput.className = "form-control form-control-sm";
    messageInput.id = `message-${reply.id}`;
    messageInput.name = "message";
    messageInput.rows = 3;
    messageInput.required = true;
    messageInput.value = reply.message || "";
    messageField.appendChild(messageInput);

    const scopeField = document.createElement("div");
    scopeField.className = "qr-field";
    fieldsWrapper.appendChild(scopeField);

    const scopeLabel = document.createElement("label");
    scopeLabel.className = "form-label";
    scopeLabel.textContent = "ใช้งานกับ";
    scopeLabel.setAttribute("for", `line_account-${reply.id}`);
    scopeField.appendChild(scopeLabel);

    const scopeSelect = document.createElement("select");
    scopeSelect.className = "form-select form-select-sm";
    scopeSelect.id = `line_account-${reply.id}`;
    scopeSelect.name = "line_account";
    scopeField.appendChild(scopeSelect);
    buildScopeOptions(
      scopeSelect,
      reply.line_account_id === null || reply.line_account_id === undefined
        ? "__None"
        : String(reply.line_account_id)
    );

    const footer = document.createElement("div");
    footer.className = "qr-reply-footer";
    form.appendChild(footer);

    const meta = document.createElement("span");
    meta.className = "qr-reply-meta";
    meta.textContent = getScopeLabel(reply);
    footer.appendChild(meta);

    const buttonGroup = document.createElement("div");
    buttonGroup.className = "btn-group";
    footer.appendChild(buttonGroup);

    const saveBtn = document.createElement("button");
    saveBtn.type = "submit";
    saveBtn.className = "btn btn-success btn-sm";
    saveBtn.innerHTML = '<i class="bi bi-check2 me-1"></i>บันทึก';
    buttonGroup.appendChild(saveBtn);

    const deleteBtn = document.createElement("button");
    deleteBtn.type = "button";
    deleteBtn.className = "btn btn-outline-danger btn-sm";
    deleteBtn.setAttribute("data-action", "delete");
    deleteBtn.innerHTML = '<i class="bi bi-trash me-1"></i>ลบ';
    buttonGroup.appendChild(deleteBtn);

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      await handleUpdate(reply.id, form, saveBtn);
    });

    deleteBtn.addEventListener("click", async () => {
      await handleDelete(reply.id, deleteBtn);
    });

    return form;
  }

  function updateCountBadge(total) {
    if (!countBadge) {
      return;
    }
    countBadge.textContent = `${total} รายการ`;
  }

  function groupReplies(replies) {
    if (currentKey === globalKey) {
      return {
        global: replies.filter(
          (reply) => reply.line_account_id === null || reply.line_account_id === undefined
        ),
        local: [],
      };
    }

    const globalReplies = [];
    const localReplies = [];
    replies.forEach((reply) => {
      if (reply.line_account_id === null || reply.line_account_id === undefined) {
        globalReplies.push(reply);
      } else if (String(reply.line_account_id) === currentKey) {
        localReplies.push(reply);
      }
    });
    return { global: globalReplies, local: localReplies };
  }

  function renderReplies(replies) {
    clearFeedback();
    repliesContainer.innerHTML = "";

    const { global: globalReplies, local: localReplies } = groupReplies(replies);
    const total = globalReplies.length + localReplies.length;
    updateCountBadge(total);

    if (total === 0) {
      if (emptyStateEl) {
        emptyStateEl.classList.remove("d-none");
      }
      return;
    }

    if (emptyStateEl) {
      emptyStateEl.classList.add("d-none");
    }

    const addSection = (title, items) => {
      if (!items.length) {
        return;
      }
      const section = document.createElement("div");
      section.className = "qr-reply-section";
      if (title) {
        const heading = document.createElement("div");
        heading.className = "qr-section-title";
        heading.textContent = title;
        section.appendChild(heading);
      }
      items.forEach((item) => section.appendChild(createReplyForm(item)));
      repliesContainer.appendChild(section);
    };

    if (globalReplies.length && currentKey !== globalKey) {
      addSection("Global (ใช้ได้ทุก OA)", globalReplies);
    } else if (currentKey === globalKey) {
      addSection("", globalReplies);
    }

    addSection(accountMap.get(currentKey) || "รายการของ OA นี้", localReplies);
  }

  async function fetchReplies() {
    setLoadingState(true);
    try {
      const params = new URLSearchParams();
      if (currentKey === globalKey) {
        params.set("only_global", "1");
      } else {
        params.set("oa_id", currentKey);
      }

      const response = await fetch(`${config.routes.data}?${params.toString()}`, {
        method: "GET",
        headers: {
          Accept: "application/json",
        },
        credentials: "same-origin",
      });

      if (!response.ok) {
        throw new Error("ไม่สามารถโหลดข้อมูลได้");
      }
      const payload = await response.json();
      renderReplies(Array.isArray(payload.replies) ? payload.replies : []);
    } catch (error) {
      console.error(error);
      showFeedback(error.message || "เกิดข้อผิดพลาดในการโหลดข้อมูล", "danger");
      repliesContainer.innerHTML = "";
      updateCountBadge(0);
      if (emptyStateEl) {
        emptyStateEl.classList.remove("d-none");
      }
    } finally {
      setLoadingState(false);
    }
  }

  async function handleUpdate(id, form, saveBtn) {
    clearFeedback();
    const url = `${config.routes.edit}${id}`;

    const formData = new FormData(form);
    if (saveBtn) {
      saveBtn.disabled = true;
      saveBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>กำลังบันทึก...';
    }

    try {
      const response = await fetch(url, {
        method: "POST",
        headers: {
          Accept: "application/json",
          "X-Requested-With": "XMLHttpRequest",
        },
        body: formData,
        credentials: "same-origin",
      });

      const payload = await response.json();
      if (!response.ok || !payload.success) {
        const errorMessages = payload.errors
          ? Object.values(payload.errors).flat().join(" / ")
          : payload.message || "บันทึกไม่สำเร็จ";
        throw new Error(errorMessages);
      }

      showFeedback(payload.message || "บันทึกสำเร็จ", "success");
      await fetchReplies();
    } catch (error) {
      console.error(error);
      showFeedback(error.message || "ไม่สามารถบันทึกข้อมูลได้", "danger");
    } finally {
      if (saveBtn) {
        saveBtn.disabled = false;
        saveBtn.innerHTML = '<i class="bi bi-check2 me-1"></i>บันทึก';
      }
    }
  }

  async function handleDelete(id, deleteBtn) {
    if (!window.confirm("ต้องการลบ Quick Reply นี้หรือไม่?")) {
      return;
    }
    clearFeedback();
    const url = `${config.routes.delete}${id}`;

    const formData = new FormData();
    formData.append("csrf_token", config.csrfToken);

    if (deleteBtn) {
      deleteBtn.disabled = true;
      deleteBtn.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';
    }

    try {
      const response = await fetch(url, {
        method: "POST",
        headers: {
          Accept: "application/json",
          "X-Requested-With": "XMLHttpRequest",
        },
        body: formData,
        credentials: "same-origin",
      });

      const payload = await response.json();
      if (!response.ok || !payload.success) {
        throw new Error(payload.message || "ไม่สามารถลบข้อมูลได้");
      }

      showFeedback(payload.message || "ลบสำเร็จ", "success");
      await fetchReplies();
    } catch (error) {
      console.error(error);
      showFeedback(error.message || "ไม่สามารถลบข้อมูลได้", "danger");
    } finally {
      if (deleteBtn) {
        deleteBtn.disabled = false;
        deleteBtn.innerHTML = '<i class="bi bi-trash me-1"></i>ลบ';
      }
    }
  }

  async function handleNewFormSubmit(event) {
    event.preventDefault();
    clearFeedback();

    const formData = new FormData(newForm);
    if (newFormSubmitBtn) {
      newFormSubmitBtn.disabled = true;
      newFormSubmitBtn.innerHTML =
        '<span class="spinner-border spinner-border-sm me-2"></span>กำลังบันทึก...';
    }

    try {
      const response = await fetch(config.routes.add, {
        method: "POST",
        headers: {
          Accept: "application/json",
          "X-Requested-With": "XMLHttpRequest",
        },
        body: formData,
        credentials: "same-origin",
      });

      const payload = await response.json();
      if (!response.ok || !payload.success) {
        const errorMessages = payload.errors
          ? Object.values(payload.errors).flat().join(" / ")
          : payload.message || "เพิ่ม Quick Reply ไม่สำเร็จ";
        throw new Error(errorMessages);
      }

      showFeedback(payload.message || "เพิ่ม Quick Reply สำเร็จ", "success");
      newForm.reset();
      syncNewFormScope();
      await fetchReplies();
    } catch (error) {
      console.error(error);
      showFeedback(error.message || "เพิ่ม Quick Reply ไม่สำเร็จ", "danger");
    } finally {
      if (newFormSubmitBtn) {
        newFormSubmitBtn.disabled = false;
        newFormSubmitBtn.innerHTML = '<i class="bi bi-plus-circle me-2"></i>บันทึก Quick Reply';
      }
    }
  }

  function handleOASelection(event) {
    const button = event.target.closest(".qr-oa-item");
    if (!button || !oaListEl.contains(button)) {
      return;
    }
    if (button.classList.contains("active")) {
      return;
    }

    oaListEl.querySelectorAll(".qr-oa-item.active").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    currentKey = button.dataset.oaKey || globalKey;
    updateListHeadings();
    syncNewFormScope();
    fetchReplies();
  }

  if (oaListEl) {
    oaListEl.addEventListener("click", handleOASelection);
  }

  if (newForm) {
    newForm.addEventListener("submit", handleNewFormSubmit);
  }

  updateListHeadings();
  syncNewFormScope();
  fetchReplies();
})();
