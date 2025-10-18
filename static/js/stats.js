// static/js/stats.js - จัดการโหลดข้อมูลและเรนเดอร์หน้าสถิติ
document.addEventListener("DOMContentLoaded", () => {
  // ค้นหา element สำคัญ
  const form = document.getElementById("stats-filter-form");
  const startInput = document.getElementById("filter-start");
  const endInput = document.getElementById("filter-end");
  const oaInput = document.getElementById("filter-oa");
  const refreshBtn = document.getElementById("stats-refresh-btn");
  const clearBtn = document.getElementById("stats-clear-btn");
  const rangeDisplay = document.getElementById("stats-range-display");
  const customersTodayEl = document.getElementById("kpi-customers-today");
  const activeCustomersEl = document.getElementById("kpi-active-customers");
  const blockedCustomersEl = document.getElementById("kpi-blocked-customers");
  const oaTbody = document.getElementById("stats-oa-tbody");
  const adminTbody = document.getElementById("stats-admin-tbody");
  const oaCountLabel = document.getElementById("stats-oa-count");
  const adminCountLabel = document.getElementById("stats-admin-count");

  const toastContainer = document.querySelector(".toast-container");
  let loading = false;

  // แปลงค่า number ให้อ่านง่าย
  const formatNumber = (value) => {
    if (value === null || value === undefined) return "-";
    return Number(value).toLocaleString("en-US");
  };

  // แสดง Toast แจ้ง error แบบสั้น ๆ
  const showErrorToast = (message) => {
    if (!toastContainer || typeof bootstrap === "undefined") {
      console.error(message);
      return;
    }
    const toastEl = document.createElement("div");
    toastEl.className = "toast align-items-center text-bg-danger border-0";
    toastEl.setAttribute("role", "alert");
    toastEl.setAttribute("aria-live", "assertive");
    toastEl.setAttribute("aria-atomic", "true");
    toastEl.innerHTML = `
      <div class="d-flex">
        <div class="toast-body">${message}</div>
        <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
      </div>
    `;
    toastContainer.appendChild(toastEl);
    const toast = new bootstrap.Toast(toastEl, { delay: 4000 });
    toast.show();
    toastEl.addEventListener("hidden.bs.toast", () => toastEl.remove());
  };

  // ดึงค่าจากฟอร์มแล้วคืน URLSearchParams
  const buildParams = (includeOa) => {
    const params = new URLSearchParams();
    const startValue = startInput.value;
    const endValue = endInput.value;
    const oaValue = oaInput.value;

    if (startValue) {
      const startDate = new Date(startValue);
      if (!Number.isNaN(startDate.valueOf())) {
        params.set("start", startDate.toISOString());
      }
    }

    if (endValue) {
      const endDate = new Date(endValue);
      if (!Number.isNaN(endDate.valueOf())) {
        params.set("end", endDate.toISOString());
      }
    }

    if (includeOa && oaValue) {
      params.set("oa_id", oaValue);
    }

    return params;
  };

  // สร้างแถว Loading สำหรับตาราง
  const setTableLoading = (tbody) => {
    tbody.innerHTML = `
      <tr class="loading-row">
        <td colspan="3" class="text-center py-4">กำลังโหลด...</td>
      </tr>
    `;
  };

  const updateRangeDisplay = (range) => {
    if (!range || !range.start || !range.end) {
      rangeDisplay.textContent = "";
      return;
    }
    try {
      const startDate = new Date(range.start);
      const endDate = new Date(range.end);
      const formatter = new Intl.DateTimeFormat("th-TH", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      });
      const startText = formatter.format(startDate);
      const endText = formatter.format(endDate);
      rangeDisplay.textContent = `${startText} → ${endText} (${range.tz || "Asia/Bangkok"})`;
    } catch (_error) {
      rangeDisplay.textContent = "";
    }
  };

  // อัปเดตตาราง OA
  const renderOaTable = (rows) => {
    if (!rows || rows.length === 0) {
      oaTbody.innerHTML = `
        <tr>
          <td colspan="3" class="text-center text-muted py-4">ยังไม่มีข้อมูล</td>
        </tr>
      `;
      oaCountLabel.textContent = "0 รายการ";
      return;
    }

    const html = rows
      .map(
        (row) => `
        <tr>
          <td>${row.oa_name ? row.oa_name : row.oa_id ?? "-"}</td>
          <td class="text-end">${formatNumber(row.unique_customers_inbound)}</td>
          <td class="text-end">${formatNumber(row.inbound_messages)}</td>
        </tr>
      `
      )
      .join("");
    oaTbody.innerHTML = html;
    oaCountLabel.textContent = `${rows.length} รายการ`;
  };

  // อัปเดตตาราง Admin
  const renderAdminTable = (rows) => {
    if (!rows || rows.length === 0) {
      adminTbody.innerHTML = `
        <tr>
          <td colspan="3" class="text-center text-muted py-4">ยังไม่มีข้อมูล</td>
        </tr>
      `;
      adminCountLabel.textContent = "0 รายการ";
      return;
    }

    const html = rows
      .map(
        (row) => `
        <tr>
          <td>${row.admin_email ? row.admin_email : row.admin_user_id ?? "-"}</td>
          <td class="text-end">${formatNumber(row.unique_customers_replied)}</td>
          <td class="text-end">${formatNumber(row.outbound_messages)}</td>
        </tr>
      `
      )
      .join("");
    adminTbody.innerHTML = html;
    adminCountLabel.textContent = `${rows.length} รายการ`;
  };

  // ตั้งค่าปุ่มกับ KPI ให้พร้อมเมื่อกำลังโหลด
  const setLoading = (state) => {
    loading = state;
    refreshBtn.disabled = state;
    if (state) {
      refreshBtn.innerHTML = `<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>กำลังโหลด`;
      customersTodayEl.textContent = "…";
      activeCustomersEl.textContent = "…";
      blockedCustomersEl.textContent = "…";
      setTableLoading(oaTbody);
      setTableLoading(adminTbody);
    } else {
      refreshBtn.innerHTML = `<i class="bi bi-arrow-repeat me-1"></i> รีเฟรช`;
    }
  };

  // เรียก API ทั้งสามพร้อมกัน
  const fetchStats = async () => {
    if (loading) return;
    setLoading(true);

    const summaryParams = buildParams(true);
    const rangeParams = buildParams(false);
    const adminParams = buildParams(true);

    const summaryQuery = summaryParams.toString();
    const rangeQuery = rangeParams.toString();
    const adminQuery = adminParams.toString();

    const summaryUrl = summaryQuery.length > 0 ? `/stats/api/summary?${summaryQuery}` : "/stats/api/summary";
    const oaUrl = rangeQuery.length > 0 ? `/stats/api/by-oa?${rangeQuery}` : "/stats/api/by-oa";
    const adminUrl = adminQuery.length > 0 ? `/stats/api/by-admin?${adminQuery}` : "/stats/api/by-admin";

    try {
      const [summaryRes, oaRes, adminRes] = await Promise.all([
        fetch(summaryUrl),
        fetch(oaUrl),
        fetch(adminUrl),
      ]);

      if (!summaryRes.ok) {
        const detail = await summaryRes.json().catch(() => ({}));
        throw new Error(detail.error || "ไม่สามารถโหลดข้อมูลสรุปได้");
      }
      if (!oaRes.ok) {
        const detail = await oaRes.json().catch(() => ({}));
        throw new Error(detail.error || "ไม่สามารถโหลดข้อมูล OA ได้");
      }
      if (!adminRes.ok) {
        const detail = await adminRes.json().catch(() => ({}));
        throw new Error(detail.error || "ไม่สามารถโหลดข้อมูลแอดมินได้");
      }

      const summaryData = await summaryRes.json();
      const oaData = await oaRes.json();
      const adminData = await adminRes.json();

      customersTodayEl.textContent = formatNumber(summaryData.kpis?.customers_today);
      activeCustomersEl.textContent = formatNumber(summaryData.kpis?.active_customers_today);
      blockedCustomersEl.textContent = formatNumber(summaryData.kpis?.blocked_customers);
      updateRangeDisplay(summaryData.range);

      renderOaTable(Array.isArray(oaData) ? oaData : []);
      renderAdminTable(Array.isArray(adminData) ? adminData : []);
    } catch (error) {
      console.error(error);
      showErrorToast(error.message || "เกิดข้อผิดพลาดที่ไม่ทราบสาเหตุ");
      renderOaTable([]);
      renderAdminTable([]);
    } finally {
      setLoading(false);
    }
  };

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    fetchStats();
  });

  clearBtn.addEventListener("click", () => {
    startInput.value = "";
    endInput.value = "";
    oaInput.value = "";
    fetchStats();
  });

  fetchStats();
});
