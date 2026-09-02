"""
GET / — the mobile web page (Phase 6, SOURCE_OF_TRUTH Section 6 "Option B").

The page is a single self-contained HTML string (inline CSS + vanilla JS —
no build tools, no frameworks) served directly by FastAPI. The phone's
browser IS the app: open http://<server-ip>:8000, pick a PDF or image, tap
Print. The accept list mirrors the categories registered in
app/processors — new formats update both.

How the upload works (worth reading slowly — this is HTTP from the browser's
point of view):
  1. <input type="file"> lets the user pick a file; JS gets a File object.
  2. FormData() wraps it into a multipart/form-data body — the exact same
     format curl sent in our Phase 4 tests (field name must be "file",
     matching app/api/print.py's parameter).
  3. fetch("/print", { method: "POST", body: formData }) sends it.
     Note: we deliberately do NOT set Content-Type — the browser must add
     the multipart boundary itself; setting it manually breaks the request.
  4. The response is the JSON from POST /print, which we display.
"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, Response

router = APIRouter()

FAVICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg"
     viewBox="0 0 512 512" width="512" height="512"
     role="img" aria-labelledby="ps-title ps-desc">
  <title id="ps-title">PrinterService</title>
  <desc id="ps-desc">A smartphone feeding into a printer printing a Wi-Fi page.</desc>
  <g id="printerservice-mark" transform="translate(256 256) scale(1.15) translate(-256 -256)">
    <rect id="body" x="112" y="197" width="288" height="174" rx="30" fill="#24272E"/>
    <rect id="page" x="194" y="325" width="124" height="120" rx="10" fill="#FFD84D"
          stroke="#1A1C20" stroke-width="9"/>
    <rect id="output-slot" x="188" y="319" width="136" height="14" rx="7" fill="#FFFFFF"/>
    <g id="wifi" fill="none" stroke="#00AEEF" stroke-width="8" stroke-linecap="round">
      <path d="M 228.4 399.4 A 39 39 0 0 1 283.6 399.4"/>
      <path d="M 236.9 407.9 A 27 27 0 0 1 275.1 407.9"/>
      <path d="M 245.4 416.4 A 15 15 0 0 1 266.6 416.4"/>
    </g>
    <circle id="wifi-dot" cx="256" cy="427" r="6.5" fill="#00AEEF"/>
    <rect id="input-slot" x="184" y="207" width="144" height="22" rx="11" fill="#FFFFFF"/>
    <g id="phone">
      <rect x="204" y="67" width="104" height="160" rx="26" fill="#E6007E"/>
      <rect x="216" y="81" width="80" height="112" rx="13" fill="#FFFFFF"/>
      <rect x="236" y="207" width="40" height="6" rx="3" fill="#FFFFFF"/>
    </g>
    <rect id="input-slot-lip" x="184" y="221" width="144" height="8" fill="#24272E"/>
    <circle id="led" cx="350" cy="267" r="9" fill="#00AEEF"/>
  </g>
</svg>"""

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<link rel="alternate icon" type="image/svg+xml" href="/favicon.ico">
<title>Printer Service</title>
<style>
  body   { font-family: system-ui, sans-serif; background: #f0f4f8;
           margin: 0; display: flex; min-height: 100vh;
           align-items: center; justify-content: center; }
  .card  { background: #fff; border-radius: 12px; padding: 24px;
           margin: 16px; max-width: 380px; width: 100%;
           box-shadow: 0 2px 10px rgba(0,0,0,.12); }
  .header{ display: flex; align-items: center; gap: 10px; margin-bottom: 4px; }
  .header img { width: 32px; height: 32px; }
  h1     { font-size: 1.3rem; margin: 0; }
  p.sub  { color: #667; margin: 0 0 18px; font-size: .9rem; }
  input[type=file] { width: 100%; margin-bottom: 14px; }
  input[type=password] { width: 100%; margin-bottom: 14px; padding: 8px;
           box-sizing: border-box; border: 1px solid #ccd; border-radius: 6px; }
  button { width: 100%; padding: 14px; font-size: 1.05rem;
           border: 0; border-radius: 8px; background: #2563eb;
           color: #fff; font-weight: 600; }
  button:disabled { background: #93b4f5; }
  #result{ margin-top: 14px; font-size: .92rem; white-space: pre-wrap;
           word-break: break-word; }
  .ok    { color: #166534; }
  .err   { color: #b91c1c; }
  .opt   { display: block; text-align: left; font-size: .85rem;
           color: #445; margin-bottom: 10px; }
  .opt input, .opt select { width: 100%; margin-top: 4px; padding: 8px;
           box-sizing: border-box; border: 1px solid #ccd;
           border-radius: 6px; background: #fff; }
</style>
</head>
<body>
<div class="card">
  <div class="header">
    <img src="/favicon.svg" alt="PrinterService Logo">
    <h1>Printer Service</h1>
  </div>
  <p class="sub">Pick a PDF, image, Office, or text file and send it to the printer.</p>

  <input type="file" id="file"
         accept=".pdf,.jpg,.jpeg,.png,.webp,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.odt,.ods,.odp,.txt,.csv">
  <input type="password" id="pin" placeholder="PIN (only if the server set one)">
  <button id="printBtn" onclick="sendPrint()">Print</button>
  <div id="result"></div>
  <button id="retryBtn" onclick="retryJob()"
          style="display:none; margin-top:10px; background:#16a34a;">
    🔁 Retry failed job
  </button>

  <details style="margin-top:14px;">
    <summary style="cursor:pointer; font-size:.85rem; color:#667;">
      Print options
    </summary>
    <label class="opt">Copies
      <input type="number" id="copies" min="1" max="99" value="1">
    </label>
    <label class="opt">Pages
      <input type="text" id="pages" placeholder="all — or 1-3,5 or odd/even">
    </label>
    <label class="opt">Paper
      <select id="paper">
        <option value="">Printer default</option>
        <option value="a4">A4</option>
        <option value="letter">Letter (short bond)</option>
        <option value="long-bond">Long bond (8.5×13)</option>
        <option value="legal">Legal</option>
        <option value="a3">A3</option>
        <option value="a5">A5</option>
      </select>
    </label>
    <label class="opt">Color
      <select id="colorMode">
        <option value="color">Color</option>
        <option value="monochrome">Black &amp; white</option>
      </select>
    </label>
  </details>

  <!-- Scan section (docs/SCAN_PLAN.md §6/Phase 3): the JS below renders
       this ONLY when GET /scanners reports a scanner. On a scanner-less
       setup it stays hidden and the page is exactly the print-only one. -->
  <div id="scanSection" style="display:none; margin-top:14px;">
    <p class="sub" style="margin-bottom:8px;">
      📇 Scanner detected: <span id="scanName"></span>
    </p>
    <button id="scanBtn" onclick="startScan()">Scan</button>
    <div id="scanResult" style="margin-top:10px; font-size:.92rem;
         white-space:pre-wrap; word-break:break-word;"></div>
  </div>
</div>

<script>
const btn = document.getElementById("printBtn");
const resultDiv = document.getElementById("result");
const retryBtn = document.getElementById("retryBtn");

// Client-side convenience only — the server re-checks everything
// (extension allowlist + magic bytes) and never trusts the browser.
const OK_TYPES = [
  ".pdf", ".jpg", ".jpeg", ".png", ".webp",
  ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
  ".odt", ".ods", ".odp",
  ".txt", ".csv",
];

let failedJobId = null;

function show(text, cls) {
  resultDiv.textContent = text;
  resultDiv.className = cls || "";
}

function retryControls(visible) {
  retryBtn.style.display = visible ? "block" : "none";
}

// Re-print a failed job from its stored upload (p14) — no re-upload
// needed. Resumes polling as if the job had just been queued.
async function retryJob() {
  if (!failedJobId) { return; }
  const pin = document.getElementById("pin").value.trim();
  const headers = pin ? { "X-API-PIN": pin } : {};
  retryControls(false);
  show("🔁 Retrying job " + failedJobId + "…", "ok");
  try {
    const response = await fetch("/jobs/" + failedJobId + "/retry",
                                 { method: "POST", headers });
    const data = await response.json();
    if (response.ok) {
      poll(failedJobId, 0);
    } else {
      show("❌ Retry refused: " + (data.detail || response.status), "err");
    }
  } catch (networkError) {
    show("❌ Could not reach the server. Are you on the same Wi-Fi?",
         "err");
  }
}

async function sendPrint() {
  const fileInput = document.getElementById("file");
  const file = fileInput.files[0];

  if (!file) { show("Pick a file first.", "err"); return; }
  if (!OK_TYPES.some(ext => file.name.toLowerCase().endsWith(ext))) {
    show("That file type isn't supported yet — PDF, images, Office "
         + "documents, or TXT/CSV.", "err");
    return;
  }

  // Basic client-side size check for instant feedback; the server enforces
  // the real limit (never trust the client — Section 8 of the docs).
  btn.disabled = true;
  show("Sending " + file.name + " (" +
       (file.size / 1e6).toFixed(1) + " MB)…");

  try {
    const body = new FormData();
    body.append("file", file);            // field name must be "file"

    // Print options (Phase 7) — all optional; empty fields mean defaults.
    body.append("copies", document.getElementById("copies").value || "1");
    body.append("pages", document.getElementById("pages").value.trim());
    body.append("paper", document.getElementById("paper").value);
    body.append("color_mode", document.getElementById("colorMode").value);

    // Send the PIN header only if the user typed one; the server ignores
    // it entirely when no PIN is configured (auth disabled).
    const pin = document.getElementById("pin").value.trim();
    const headers = pin ? { "X-API-PIN": pin } : {};

    const response = await fetch("/print", { method: "POST", body, headers });
    const data = await response.json();

    if (response.ok) {
      show("📨 Queued!\\njob id: " + data.job_id + "\\nchecking status…", "ok");
      poll(data.job_id, 0);
    } else if (response.status === 401) {
      show("❌ Wrong PIN.", "err");
    } else {
      // The server answered with a problem (415 not-a-PDF, 413 too big, …)
      show("❌ Server said: " + (data.detail || response.status), "err");
    }
  } catch (networkError) {
    // fetch only throws on network-level failures: server down, Wi-Fi off,
    // firewall drop. This is the "silently hangs" case in Section 14.
    show("❌ Could not reach the server. Are you on the same Wi-Fi?",
         "err");
  } finally {
    btn.disabled = false;
  }
}

// Poll the job until it's done or failed — this is the "is my print
// finished yet?" loop the Section 11 API was designed for.
async function poll(jobId, attempt) {
  if (attempt > 60) {  // ~2 minutes; spooler can be slow with big files
    show("⏳ Still not confirmed after 2 min. Check GET /jobs/" + jobId +
         " or the printer's queue.", "ok");
    return;
  }
  try {
    const pin = document.getElementById("pin").value.trim();
    const headers = pin ? { "X-API-PIN": pin } : {};
    const response = await fetch("/jobs/" + jobId, { headers });
    if (!response.ok) {
      show("❌ Lost track of job " + jobId + " (HTTP " + response.status + ")",
           "err");
      return;
    }
    const job = await response.json();
    if (job.status === "done") {
      retryControls(false);
      show("🖨️ Printed to " + (job.printer || "printer") + "!\\njob " + jobId,
           "ok");
      return;
    }
    if (job.status === "failed") {
      failedJobId = jobId;
      retryControls(true);
      show("❌ Print failed: " + (job.error || "unknown reason") +
           "\\nYou can retry it from the stored copy.", "err");
      return;
    }
    if (job.status === "cancelled") {
      retryControls(false);
      show("Job " + jobId + " was cancelled.", "err");
      return;
    }
    show("⏳ status: " + job.status, "ok");
    setTimeout(() => poll(jobId, attempt + 1), 2000);
  } catch (networkError) {
    // One dropped poll shouldn't end monitoring — keep trying.
    setTimeout(() => poll(jobId, attempt + 1), 3000);
  }
}

// Scan feature (docs/SCAN_PLAN.md §6/Phase 3): ask the server ONCE whether
// this printer setup can scan at all. No scanner (or the feature disabled)
// → the section never renders and the page stays the familiar print-only
// one. Detection failure must never break the page, hence the catch.
(async function checkScanner() {
  try {
    const response = await fetch("/scanners");
    if (!response.ok) { return; }
    const info = await response.json();
    if (!info.available || !info.devices.length) { return; }
    document.getElementById("scanName").textContent =
      info.devices[0].name || "scanner";
    document.getElementById("scanSection").style.display = "block";
  } catch (e) {
    // Stay print-only (SCAN_PLAN §3: detection is never load-bearing).
  }
})();

// The Scan button: POST /scan, then poll the job the same way print does.
// The button stays disabled while a scan is in flight — the flatbed can
// only do one page at a time, so a second tap would just hit a busy
// scanner (WIA_ERROR_BUSY) instead of queueing usefully.
const scanBtn = document.getElementById("scanBtn");
const scanResult = document.getElementById("scanResult");
let scanInFlight = false;

function scanShow(text, cls) {
  scanResult.textContent = text;
  scanResult.className = cls || "";
}

async function startScan() {
  if (scanInFlight) { return; }
  scanInFlight = true;
  scanBtn.disabled = true;
  scanShow("📨 Starting scan…", "ok");
  const pin = document.getElementById("pin").value.trim();
  const headers = pin ? { "X-API-PIN": pin } : {};
  try {
    const response = await fetch("/scan", { method: "POST", headers });
    const data = await response.json();
    if (response.ok) {
      scanShow("📨 Scan queued — the flatbed is working. Checking status…", "ok");
      pollScan(data.job_id, 0);
    } else if (response.status === 401) {
      scanInFlight = false;
      scanBtn.disabled = false;
      scanShow("❌ Wrong PIN.", "err");
    } else {
      scanInFlight = false;
      scanBtn.disabled = false;
      scanShow("❌ Server said: " + (data.detail || response.status), "err");
    }
  } catch (networkError) {
    scanInFlight = false;
    scanBtn.disabled = false;
    scanShow("❌ Could not reach the server. Are you on the same Wi-Fi?", "err");
  }
}

// Poll a scan job until it's done — mirrors print's poll() (SCAN_PLAN §6
// is explicit: reuse the existing polling pattern, don't invent a new one).
async function pollScan(jobId, attempt) {
  if (attempt > 75) {  // ~2.5 min; scans take 40-60 s (spike S2) + print load
    scanInFlight = false;
    scanBtn.disabled = false;
    scanShow("⏳ Still not confirmed after ~2.5 min. Check /scan/jobs/" + jobId +
             " for the current status.", "ok");
    return;
  }
  try {
    const pin = document.getElementById("pin").value.trim();
    const headers = pin ? { "X-API-PIN": pin } : {};
    const response = await fetch("/scan/jobs/" + jobId, { headers });
    if (!response.ok) {
      scanInFlight = false;
      scanBtn.disabled = false;
      scanShow("❌ Lost track of scan job " + jobId + " (HTTP " +
               response.status + ")", "err");
      return;
    }
    const job = await response.json();
    if (job.status === "done") {
      scanInFlight = false;
      scanBtn.disabled = false;
      // The link is built from the server-issued job id (a UUID hex) —
      // nothing from the server goes into innerHTML, and the download
      // endpoint is the only thing it ever points at.
      scanResult.className = "ok";
      scanResult.innerHTML = "✅ Scan ready — " +
        '<a href="/scan/jobs/' + jobId + '/download">View / Download</a>' +
        " (job " + jobId + ")";
      return;
    }
    if (job.status === "failed") {
      scanInFlight = false;
      scanBtn.disabled = false;
      scanShow("❌ Scan failed: " + (job.error || "unknown reason"), "err");
      return;
    }
    if (job.status === "cancelled") {
      scanInFlight = false;
      scanBtn.disabled = false;
      scanShow("Scan job " + jobId + " was cancelled.", "err");
      return;
    }
    scanShow("⏳ status: " + job.status, "ok");
    setTimeout(() => pollScan(jobId, attempt + 1), 2000);
  } catch (networkError) {
    // One dropped poll shouldn't end monitoring — keep trying.
    setTimeout(() => pollScan(jobId, attempt + 1), 3000);
  }
}
</script>
</body>
</html>"""


@router.get("/", response_class=HTMLResponse)
def index():
    """Serve the upload page. Opening the server's URL on the phone IS the app."""
    return PAGE


@router.get("/favicon.svg", include_in_schema=False)
@router.get("/favicon.ico", include_in_schema=False)
def favicon():
    """Serve the SVG icon for browser tabs."""
    return Response(content=FAVICON_SVG, media_type="image/svg+xml")

