"use strict";
const last = Date.parse(document.body.dataset.lastCheck);
function showFreshness() {
  document.getElementById("stale").hidden = Number.isFinite(last) && Date.now() - last < 300000;
}
showFreshness();
setInterval(showFreshness, 10000);

const controlButtons = ["start-control", "stop-control", "reset-control"]
  .map(id => document.getElementById(id)).filter(Boolean);
const controlMessage = document.getElementById("control-message");
const tokenMeta = document.querySelector('meta[name="summit-control-token"]');
if (controlButtons.length && controlMessage && tokenMeta) {
  const initialDisabled = new Map(controlButtons.map(button => [button, button.disabled]));
  async function applyControl(action) {
    if (action === "reset" && !confirm("Archive this competition and create a fresh READY event? Previous history will remain available.")) return;
    controlButtons.forEach(button => { button.disabled = true; });
    controlMessage.textContent = `${action[0].toUpperCase()}${action.slice(1)} in progress…`;
    try {
      const response = await fetch("/api/control", {
        method: "POST",
        headers: {"Content-Type":"application/json", "X-Summit-Control-Token":tokenMeta.content},
        body: JSON.stringify({action}),
      });
      let payload = {};
      try { payload = await response.json(); } catch (_) { payload = {}; }
      if (!response.ok) throw new Error(payload.error || `Control request failed (${response.status})`);
      controlMessage.textContent = `Competition is now ${payload.state || "updated"}.`;
      location.reload();
    } catch (error) {
      controlMessage.textContent = error.message || "Control request failed.";
      controlButtons.forEach(button => { button.disabled = initialDisabled.get(button); });
    }
  }
  controlButtons.forEach(button => button.addEventListener("click", event => {
    event.preventDefault();
    return applyControl((button.dataset && button.dataset.action) || button.id.replace("-control", ""));
  }));
}

const table = document.getElementById("history-table");
if (table) {
  const rows = Array.from(table.tBodies[0].rows);
  const search = document.getElementById("search");
  const status = document.getElementById("status-filter");
  const previous = document.getElementById("previous");
  const next = document.getElementById("next");
  const params = new URLSearchParams(location.search);
  search.value = params.get("q") || "";
  status.value = ["PASS", "DOWN", "FAIL", "INVALID"].includes(params.get("status")) ? params.get("status") : "";
  let page = Math.max(1, parseInt(params.get("page"), 10) || 1);
  let specific = params.get("check") || "";
  const pageSize = 50;
  function render() {
    const q = search.value.trim().toLowerCase();
    const matching = rows.filter(row => (!status.value || row.dataset.status === status.value) &&
      (!specific || row.dataset.check === specific) && (!q || row.textContent.toLowerCase().includes(q)));
    const pages = Math.max(1, Math.ceil(matching.length / pageSize));
    page = Math.max(1, Math.min(page, pages));
    rows.forEach(row => { row.hidden = true; });
    matching.slice((page - 1) * pageSize, page * pageSize).forEach(row => { row.hidden = false; });
    previous.disabled = page <= 1;
    next.disabled = page >= pages;
    document.getElementById("empty-results").hidden = matching.length !== 0;
    document.getElementById("page-summary").textContent = matching.length ?
      `${(page-1)*pageSize+1}–${Math.min(page*pageSize, matching.length)} of ${matching.length} matching checks · page ${page} of ${pages}` : "0 matching checks";
    const query = new URLSearchParams();
    if (search.value) query.set("q", search.value);
    if (status.value) query.set("status", status.value);
    if (specific) query.set("check", specific);
    if (page > 1) query.set("page", String(page));
    history.replaceState(null, "", location.pathname + (query.size ? "?" + query.toString() : ""));
  }
  search.addEventListener("input", () => {page=1;specific="";render();});
  status.addEventListener("change", () => {page=1;specific="";render();});
  previous.addEventListener("click", () => {page--;render();});
  next.addEventListener("click", () => {page++;render();});
  render();
}
