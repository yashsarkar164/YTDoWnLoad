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

let currentUrl = "";

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

  downloadBtn.disabled = true;
  downloadBtn.textContent = "Downloading...";
  downloadStatus.classList.remove("hidden");
  downloadStatus.textContent = "Downloading and processing — this can take a moment for larger files.";

  try {
    const res = await fetch("/api/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: currentUrl, quality: qualitySelect.value }),
    });

    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      downloadStatus.textContent = data.error || "Download failed.";
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

    downloadStatus.textContent = "Done! Check your browser's downloads.";
  } catch (err) {
    downloadStatus.textContent = "Something went wrong during download.";
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
