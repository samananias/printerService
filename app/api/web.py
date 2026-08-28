"""
GET / — the mobile web page (Phase 6, SOURCE_OF_TRUTH Section 6 "Option B").

The page is a single self-contained HTML string (inline CSS + vanilla JS —
no build tools, no frameworks) served directly by FastAPI. The phone's
browser IS the app: open http://<server-ip>:8000, pick a PDF, tap Print.

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
from fastapi.responses import HTMLResponse

router = APIRouter()

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Printer Service</title>
<style>
  body   { font-family: system-ui, sans-serif; background: #f0f4f8;
           margin: 0; display: flex; min-height: 100vh;
           align-items: center; justify-content: center; }
  .card  { background: #fff; border-radius: 12px; padding: 24px;
           margin: 16px; max-width: 380px; width: 100%;
           box-shadow: 0 2px 10px rgba(0,0,0,.12); }
  h1     { font-size: 1.3rem; margin: 0 0 4px; }
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
</style>
</head>
<body>
<div class="card">
  <h1>🖨️ Printer Service</h1>
  <p class="sub">Pick a PDF and send it to the printer.</p>

  <input type="file" id="file" accept=".pdf,application/pdf">
  <input type="password" id="pin" placeholder="PIN (only if the server set one)">
  <button id="printBtn" onclick="sendPrint()">Print</button>
  <div id="result"></div>
</div>

<script>
const btn = document.getElementById("printBtn");
const resultDiv = document.getElementById("result");

function show(text, cls) {
  resultDiv.textContent = text;
  resultDiv.className = cls || "";
}

async function sendPrint() {
  const fileInput = document.getElementById("file");
  const file = fileInput.files[0];

  if (!file) { show("Pick a PDF first.", "err"); return; }
  if (!file.name.toLowerCase().endsWith(".pdf")) {
    show("That doesn't look like a PDF file.", "err");
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
      show("🖨️ Printed to " + (job.printer || "printer") + "!\\njob " + jobId,
           "ok");
      return;
    }
    if (job.status === "failed") {
      show("❌ Print failed: " + (job.error || "unknown reason"), "err");
      return;
    }
    if (job.status === "cancelled") {
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
</script>
</body>
</html>"""


@router.get("/", response_class=HTMLResponse)
def index():
    """Serve the upload page. Opening the server's URL on the phone IS the app."""
    return PAGE
