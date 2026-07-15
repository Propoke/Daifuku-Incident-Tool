const API = "/api/mobile";

function getCookie(name) {
  const match = document.cookie.match(new RegExp("(^| )" + name + "=([^;]+)"));
  return match ? decodeURIComponent(match[2]) : null;
}

async function api(path, options = {}) {
  const opts = {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  };
  if (options.method && options.method !== "GET") {
    opts.headers["X-CSRFToken"] = getCookie("csrftoken");
  }
  const resp = await fetch(API + path, opts);
  let data = null;
  try {
    data = await resp.json();
  } catch (e) {
    /* no body */
  }
  if (!resp.ok) {
    const message = (data && (data.detail || JSON.stringify(data))) || `Request failed (${resp.status})`;
    throw new Error(message);
  }
  return data;
}

const app = document.getElementById("app");

function escapeHtml(s) {
  const div = document.createElement("div");
  div.textContent = s == null ? "" : String(s);
  return div.innerHTML;
}

// --- Screens ---

async function showTickets() {
  setActiveTab("tickets");
  app.innerHTML = `<p class="muted">Loading tickets&hellip;</p>`;
  try {
    const tickets = await api("/workorders/mine/");
    if (!tickets.length) {
      app.innerHTML = `<p class="muted">No open tickets assigned to you.</p>`;
      return;
    }
    app.innerHTML = tickets
      .map(
        (t) => `
      <div class="card" data-id="${t.id}">
        <h3>${escapeHtml(t.title)}</h3>
        <div class="muted">${escapeHtml(t.asset_tag)} &middot; ${escapeHtml(t.status)} &middot; ${escapeHtml(t.priority)}</div>
      </div>`
      )
      .join("");
    app.querySelectorAll(".card").forEach((el) => {
      el.addEventListener("click", () => showTicketDetail(el.dataset.id));
    });
  } catch (e) {
    app.innerHTML = `<p class="error">${escapeHtml(e.message)}</p>`;
  }
}

async function showTicketDetail(id) {
  app.innerHTML = `<p class="muted">Loading&hellip;</p>`;
  try {
    const t = await api(`/workorders/${id}/`);
    renderTicketDetail(t);
  } catch (e) {
    app.innerHTML = `<p class="error">${escapeHtml(e.message)}</p>`;
  }
}

function renderTicketDetail(t) {
  const statuses = ["OPEN", "IN_PROGRESS", "ON_HOLD", "COMPLETED", "CLOSED"];
  app.innerHTML = `
    <a href="#" class="back-link" id="back-to-tickets">&larr; My tickets</a>
    <div class="card">
      <h3>${escapeHtml(t.title)}</h3>
      <div class="muted">${escapeHtml(t.asset_tag)} &mdash; ${escapeHtml(t.asset_name)}</div>
      <p>${escapeHtml(t.description || "")}</p>
      <p class="muted">Status: <strong>${escapeHtml(t.status)}</strong> &middot; Priority: ${escapeHtml(t.priority)}</p>
    </div>
    <div class="card">
      <h3>Update status</h3>
      <select id="status-select">
        ${statuses.map((s) => `<option value="${s}" ${s === t.status ? "selected" : ""}>${s}</option>`).join("")}
      </select>
      <button id="status-submit">Update</button>
      <p id="status-msg"></p>
    </div>
    <div class="card">
      <h3>Book a part onto this ticket</h3>
      <button id="scan-for-ticket">Scan barcode</button>
    </div>
    <div class="card">
      <h3>Comments</h3>
      <div id="comments-list" class="muted">Loading&hellip;</div>
      <textarea id="comment-body" placeholder="Leave a note for the next shift on this ticket&hellip;"></textarea>
      <button id="comment-submit">Post comment</button>
      <p id="comment-msg"></p>
    </div>
  `;
  document.getElementById("back-to-tickets").addEventListener("click", (e) => {
    e.preventDefault();
    showTickets();
  });
  document.getElementById("status-submit").addEventListener("click", async () => {
    const status = document.getElementById("status-select").value;
    const msg = document.getElementById("status-msg");
    try {
      const updated = await api(`/workorders/${t.id}/status/`, {
        method: "POST",
        body: JSON.stringify({ status }),
      });
      msg.innerHTML = `<span class="success">Updated.</span>`;
      t.status = updated.status;
    } catch (e) {
      msg.innerHTML = `<span class="error">${escapeHtml(e.message)}</span>`;
    }
  });
  document.getElementById("scan-for-ticket").addEventListener("click", () => showScan(t));
  document.getElementById("comment-submit").addEventListener("click", () => postComment(t));
  loadComments(t);
}

async function loadComments(ticket) {
  const listEl = document.getElementById("comments-list");
  try {
    const comments = await api(`/workorders/${ticket.id}/comments/`);
    listEl.innerHTML = comments.length
      ? comments
          .map(
            (c) => `
      <p><strong>${escapeHtml(c.author_username || "unknown")}</strong>
        <span class="muted">${escapeHtml(new Date(c.created_at).toLocaleString())}</span><br>
        ${escapeHtml(c.body)}</p>`
          )
          .join("")
      : `<p class="muted">No comments yet.</p>`;
  } catch (e) {
    listEl.innerHTML = `<p class="error">${escapeHtml(e.message)}</p>`;
  }
}

async function postComment(ticket) {
  const bodyEl = document.getElementById("comment-body");
  const msg = document.getElementById("comment-msg");
  const body = bodyEl.value.trim();
  if (!body) return;
  try {
    await api(`/workorders/${ticket.id}/comments/`, {
      method: "POST",
      body: JSON.stringify({ body }),
    });
    bodyEl.value = "";
    msg.innerHTML = `<span class="success">Posted.</span>`;
    loadComments(ticket);
  } catch (e) {
    msg.innerHTML = `<span class="error">${escapeHtml(e.message)}</span>`;
  }
}

async function showScan(ticket, mode = "part") {
  setActiveTab(ticket ? null : "scan");
  // A ticket-scoped scan is always for booking a part onto that ticket -
  // the asset-scan mode only makes sense from the standalone Scan tab,
  // where there's no ticket in play to book a part against.
  const showModeToggle = !ticket;
  app.innerHTML = `
    ${ticket ? `<a href="#" class="back-link" id="back-to-ticket">&larr; Back to ticket</a>` : ""}
    ${
      showModeToggle
        ? `
    <div class="card">
      <button id="mode-part" class="${mode === "part" ? "" : "secondary"}">Scan a part</button>
      <button id="mode-asset" class="${mode === "asset" ? "" : "secondary"}">Scan an asset</button>
    </div>`
        : ""
    }
    <div class="card">
      <h3>${mode === "asset" ? "Scan an asset tag" : "Scan a part barcode"}</h3>
      <video id="scan-video" autoplay playsinline muted></video>
      <p id="scan-status" class="muted">Starting camera&hellip;</p>
      <p class="muted">Camera scanning not working? Enter the code by hand:</p>
      <input id="manual-code" placeholder="${mode === "asset" ? "Asset tag" : "Barcode or SKU"}">
      <button id="manual-submit">Look up</button>
    </div>
    <div id="scan-result"></div>
  `;
  if (ticket) {
    document.getElementById("back-to-ticket").addEventListener("click", (e) => {
      e.preventDefault();
      renderTicketDetail(ticket);
    });
  }
  if (showModeToggle) {
    document.getElementById("mode-part").addEventListener("click", () => showScan(null, "part"));
    document.getElementById("mode-asset").addEventListener("click", () => showScan(null, "asset"));
  }
  document.getElementById("manual-submit").addEventListener("click", () => {
    const code = document.getElementById("manual-code").value.trim();
    if (code) handleScannedCode(code, ticket, mode);
  });

  startCameraScan(ticket, mode);
}

function handleScannedCode(code, ticket, mode) {
  if (mode === "asset") {
    lookupAsset(code);
  } else {
    lookupPart(code, ticket);
  }
}

let activeStream = null;

async function startCameraScan(ticket, mode) {
  const statusEl = document.getElementById("scan-status");
  if (!("BarcodeDetector" in window)) {
    statusEl.textContent = "Camera scanning isn't supported in this browser - use manual entry below.";
    return;
  }
  try {
    activeStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
  } catch (e) {
    statusEl.textContent = "Camera access denied or unavailable - use manual entry below.";
    return;
  }
  const video = document.getElementById("scan-video");
  video.srcObject = activeStream;
  statusEl.textContent = "Point the camera at a barcode.";

  const detector = new window.BarcodeDetector();
  let stopped = false;
  const loop = async () => {
    if (stopped) return;
    try {
      const codes = await detector.detect(video);
      if (codes.length) {
        stopped = true;
        stopCameraScan();
        handleScannedCode(codes[0].rawValue, ticket, mode);
        return;
      }
    } catch (e) {
      /* keep trying */
    }
    requestAnimationFrame(loop);
  };
  requestAnimationFrame(loop);
}

function stopCameraScan() {
  if (activeStream) {
    activeStream.getTracks().forEach((tr) => tr.stop());
    activeStream = null;
  }
}

async function lookupAsset(code) {
  const resultEl = document.getElementById("scan-result");
  resultEl.innerHTML = `<p class="muted">Looking up ${escapeHtml(code)}&hellip;</p>`;
  try {
    const asset = await api(`/assets/lookup/?code=${encodeURIComponent(code)}`);
    // Hands off to the existing site-scoped asset history page (Django
    // template, not part of the SPA) rather than building a second
    // asset-detail screen - it already renders tickets, configuration
    // history, permits/incidents, and the change log.
    window.location.href = `/reports/assets/${asset.id}/history/`;
  } catch (e) {
    resultEl.innerHTML = `<p class="error">${escapeHtml(e.message)}</p>`;
  }
}

async function lookupPart(code, ticket) {
  const resultEl = document.getElementById("scan-result");
  resultEl.innerHTML = `<p class="muted">Looking up ${escapeHtml(code)}&hellip;</p>`;
  try {
    const part = await api(`/spareparts/lookup/?code=${encodeURIComponent(code)}`);
    renderPartResult(part, ticket);
  } catch (e) {
    resultEl.innerHTML = `<p class="error">${escapeHtml(e.message)}</p>`;
  }
}

function renderPartResult(part, ticket) {
  const resultEl = document.getElementById("scan-result");
  if (!part.stock_levels.length) {
    resultEl.innerHTML = `
      <div class="card">
        <h3>${escapeHtml(part.sku)}</h3>
        <p>${escapeHtml(part.description)}</p>
        <p class="muted">No stock at any of your accessible sites.</p>
      </div>`;
    return;
  }
  resultEl.innerHTML = `
    <div class="card">
      <h3>${escapeHtml(part.sku)}</h3>
      <p>${escapeHtml(part.description)}</p>
      ${
        ticket
          ? `
      <select id="location-select">
        ${part.stock_levels
          .map(
            (sl) =>
              `<option value="${sl.id}">${escapeHtml(sl.location_name)} (${escapeHtml(sl.site)}) &mdash; ${sl.quantity_available} available</option>`
          )
          .join("")}
      </select>
      <input id="quantity-input" type="number" min="1" value="1">
      <button id="book-part">Book onto ${escapeHtml(ticket.title)}</button>
      <p id="book-msg"></p>`
          : part.stock_levels
              .map((sl) => `<p class="muted">${escapeHtml(sl.location_name)} (${escapeHtml(sl.site)}): ${sl.quantity_on_hand} on hand</p>`)
              .join("")
      }
    </div>`;

  if (ticket) {
    document.getElementById("book-part").addEventListener("click", async () => {
      const stockLocationId = document.getElementById("location-select").value;
      const quantity = parseInt(document.getElementById("quantity-input").value, 10) || 1;
      const msg = document.getElementById("book-msg");
      try {
        await api(`/workorders/${ticket.id}/consume-part/`, {
          method: "POST",
          body: JSON.stringify({ code: part.barcode || part.sku, stock_location_id: stockLocationId, quantity }),
        });
        msg.innerHTML = `<span class="success">Booked ${quantity}x ${escapeHtml(part.sku)} onto this ticket.</span>`;
      } catch (e) {
        msg.innerHTML = `<span class="error">${escapeHtml(e.message)}</span>`;
      }
    });
  }
}

function setActiveTab(name) {
  document.querySelectorAll("nav.tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
}

document.getElementById("tab-tickets").addEventListener("click", () => showTickets());
document.getElementById("tab-scan").addEventListener("click", () => showScan(null));

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/app/sw.js");
}

showTickets();
