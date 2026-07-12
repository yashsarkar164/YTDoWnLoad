const urlInput = document.getElementById("url");
const fetchBtn = document.getElementById("fetchBtn");
const errorMsg = document.getElementById("errorMsg");
const result = document.getElementById("result");
const thumb = document.getElementById("thumb");
const titleEl = document.getElementById("title");
const uploaderEl = document.getElementById("uploader");
const durationEl = document.getElementById("duration");
const qualitySelect = document.getElementById("quality");
const downloadBtn = document.getElementById("downloadBtn");
const downloadStatus = document.getElementById("downloadStatus");
const progressBlock = document.getElementById("progressBlock");
const progressFill = document.getElementById("progressFill");
const progressPercent = document.getElementById("progressPercent");
const progressStatus = document.getElementById("progressStatus");
const progressSpeed = document.getElementById("progressSpeed");
const progressEta = document.getElementById("progressEta");

let currentUrl = "";
let pollTimer = null;

function formatBytesPerSec(bytesPerSec) {
  if (!bytesPerSec && bytesPerSec !== 0) return "";
  const units = ["B/s", "KB/s", "MB/s", "GB/s"];
  let val = bytesPerSec;
  let i = 0;
  while (val >= 1024 && i < units.length - 1) {
    val /= 1024;
    i += 1;
  }
  return `${val.toFixed(1)} ${units[i]}`;
}

function formatEta(seconds) {
  if (seconds === null || seconds === undefined) return "";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `ETA ${m}:${s.toString().padStart(2, "0")}`;
}

function resetProgressUI() {
  progressBlock.classList.remove("hidden");
  progressFill.style.width = "0%";
  progressFill.classList.remove("postprocessing");
  progressPercent.textContent = "0%";
  progressStatus.textContent = "Starting...";
  progressSpeed.textContent = "";
  progressEta.textContent = "";
  downloadStatus.classList.add("hidden");
  downloadStatus.classList.remove("error-text");
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

function showError(msg) {
  errorMsg.textContent = msg;
  errorMsg.classList.remove("hidden");
}

function clearError() {
  errorMsg.textContent = "";
  errorMsg.classList.add("hidden");
}

async function fetchInfo() {
  const url = urlInput.value.trim();
  clearError();
  result.classList.add("hidden");
  downloadStatus.classList.add("hidden");

  if (!url) {
    showError("Please paste a video URL first.");
    return;
  }

  fetchBtn.disabled = true;
  fetchBtn.textContent = "Fetching...";

  try {
    const res = await fetch("/api/info", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    const data = await res.json();

    if (!res.ok) {
      showError(data.error || "Something went wrong.");
      return;
    }

    currentUrl = url;
    thumb.src = data.thumbnail || "";
    titleEl.textContent = data.title || "Untitled";
    uploaderEl.textContent = data.uploader ? `By ${data.uploader}` : "";
    durationEl.textContent = data.duration ? `Duration: ${data.duration}` : "";
    result.classList.remove("hidden");
  } catch (err) {
    showError("Could not reach the server. Is app.py running?");
  } finally {
    fetchBtn.disabled = false;
    fetchBtn.textContent = "Fetch Info";
  }
}

async function startDownload() {
  if (!currentUrl) return;

  stopPolling();
  resetProgressUI();
  downloadBtn.disabled = true;
  downloadBtn.textContent = "Downloading...";

  let jobId;
  try {
    const res = await fetch("/api/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: currentUrl, quality: qualitySelect.value }),
    });
    const data = await res.json();

    if (!res.ok) {
      showDownloadError(data.error || "Download failed to start.");
      return;
    }
    jobId = data.job_id;
  } catch (err) {
    showDownloadError("Could not reach the server. Is app.py running?");
    return;
  }

  pollTimer = setInterval(() => pollProgress(jobId), 1000);
  // Kick off an immediate poll so the UI updates without waiting a full second.
  pollProgress(jobId);
}

async function pollProgress(jobId) {
  try {
    const res = await fetch(`/api/progress/${jobId}`);
    const data = await res.json();

    if (!res.ok) {
      stopPolling();
      showDownloadError(data.error || "Lost track of this download.");
      return;
    }

    updateProgressUI(data);

    if (data.status === "finished") {
      stopPolling();
      await triggerBrowserDownload(jobId);
    } else if (data.status === "error") {
      stopPolling();
      showDownloadError(data.error || "Download failed.");
    }
  } catch (err) {
    stopPolling();
    showDownloadError("Lost connection to the server while downloading.");
  }
}

function updateProgressUI(data) {
  const percent = Math.max(0, Math.min(100, data.percent || 0));
  progressFill.style.width = `${percent}%`;
  progressPercent.textContent = `${percent.toFixed(1)}%`;

  if (data.status === "postprocessing") {
    progressFill.classList.add("postprocessing");
    progressStatus.textContent = "Processing (merging/converting)...";
    progressSpeed.textContent = "";
    progressEta.textContent = "";
  } else {
    progressFill.classList.remove("postprocessing");
    progressStatus.textContent = data.status === "downloading" ? "Downloading..." : "Starting...";
    progressSpeed.textContent = formatBytesPerSec(data.speed);
    progressEta.textContent = formatEta(data.eta);
  }
}

function showDownloadError(message) {
  progressBlock.classList.add("hidden");
  downloadStatus.classList.remove("hidden");
  downloadStatus.classList.add("error-text");
  downloadStatus.textContent = message;
  downloadBtn.disabled = false;
  downloadBtn.textContent = "Download";
}

async function triggerBrowserDownload(jobId) {
  progressStatus.textContent = "Finalizing...";
  try {
    const res = await fetch(`/api/file/${jobId}`);
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      showDownloadError(data.error || "Could not retrieve the finished file.");
      return;
    }

    const blob = await res.blob();
    const disposition = res.headers.get("Content-Disposition") || "";
    const match = disposition.match(/filename="?([^"]+)"?/);
    const filename = match ? match[1] : "download";

    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();

    progressStatus.textContent = "Done!";
    downloadStatus.classList.remove("hidden", "error-text");
    downloadStatus.textContent = "Done! Check your browser's downloads.";
  } catch (err) {
    showDownloadError("Something went wrong while fetching the finished file.");
  } finally {
    downloadBtn.disabled = false;
    downloadBtn.textContent = "Download";
  }
}

fetchBtn.addEventListener("click", fetchInfo);
urlInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") fetchInfo();
});
downloadBtn.addEventListener("click", startDownload);
