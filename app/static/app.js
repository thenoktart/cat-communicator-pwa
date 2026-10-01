const $ = (id) => document.getElementById(id);

let recorder = null;
let stream = null;
let chunks = [];
let blob = null;
let startedAt = null;
let timerInterval = null;
let durationMs = 0;

const labelsTr = {
  food: "Mama",
  attention: "İlgi",
  play: "Oyun",
  door: "Kapı",
  greeting: "Selamlama",
  stress: "Stres",
  unknown: "Bilinmiyor",
};

function preferredMimeType() {
  const candidates = [
    "audio/mp4",
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/ogg;codecs=opus",
  ];
  return candidates.find((t) => MediaRecorder.isTypeSupported(t)) || "";
}

function fmt(ms) {
  const sec = ms / 1000;
  const min = Math.floor(sec / 60).toString().padStart(2, "0");
  const rest = (sec % 60).toFixed(1).padStart(4, "0");
  return `${min}:${rest}`;
}

async function startRecording() {
  $("message").textContent = "";
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
    $("message").textContent = "Bu tarayıcı ses kaydını desteklemiyor.";
    return;
  }

  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: false,
        noiseSuppression: false,
        autoGainControl: false
      }
    });

    const mimeType = preferredMimeType();
    recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
    chunks = [];
    blob = null;

    recorder.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) chunks.push(e.data);
    };

    recorder.onstop = () => {
      durationMs = Date.now() - startedAt;
      blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
      $("preview").src = URL.createObjectURL(blob);
      $("preview").classList.remove("hidden");
      $("formFields").classList.remove("hidden");
      $("recordBtn").classList.remove("hidden");
      $("stopBtn").classList.add("hidden");
      $("pulse").classList.remove("live");
      stream?.getTracks().forEach((track) => track.stop());
      clearInterval(timerInterval);
      $("timer").textContent = fmt(durationMs);
    };

    recorder.start();
    startedAt = Date.now();
    $("recordBtn").classList.add("hidden");
    $("stopBtn").classList.remove("hidden");
    $("formFields").classList.add("hidden");
    $("preview").classList.add("hidden");
    $("pulse").classList.add("live");

    timerInterval = setInterval(() => {
      $("timer").textContent = fmt(Date.now() - startedAt);
    }, 100);
  } catch (err) {
    $("message").textContent = `Mikrofon açılamadı: ${err.message}`;
  }
}

function stopRecording() {
  if (recorder && recorder.state !== "inactive") recorder.stop();
}

function discardRecording() {
  blob = null;
  chunks = [];
  durationMs = 0;
  $("preview").src = "";
  $("preview").classList.add("hidden");
  $("formFields").classList.add("hidden");
  $("timer").textContent = "00:00.0";
  $("message").textContent = "Kayıt silindi.";
}

async function saveRecording() {
  if (!blob) return;
  const catName = $("catName").value.trim();
  if (!catName) {
    $("message").textContent = "Önce kedinin adını yaz.";
    $("catName").focus();
    return;
  }

  localStorage.setItem("catName", catName);
  const fd = new FormData();
  const ext = blob.type.includes("mp4") ? "m4a" : blob.type.includes("ogg") ? "ogg" : "webm";
  fd.append("audio", blob, `vocalization.${ext}`);
  fd.append("cat_name", catName);
  fd.append("label", $("label").value);
  fd.append("context", $("context").value);
  fd.append("outcome", $("outcome").value);
  fd.append("notes", $("notes").value);
  fd.append("duration_ms", String(durationMs));

  $("saveBtn").disabled = true;
  $("message").textContent = "Kaydediliyor…";

  try {
    const res = await fetch("/api/records", { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Kayıt başarısız.");

    $("context").value = "";
    $("notes").value = "";
    $("outcome").value = "unknown";
    $("label").value = "unknown";
    discardRecording();
    $("message").textContent = "Kayıt veri setine eklendi.";
    await refresh();
  } catch (err) {
    $("message").textContent = err.message;
  } finally {
    $("saveBtn").disabled = false;
  }
}

async function refresh() {
  try {
    const [statsRes, recRes] = await Promise.all([
      fetch("/api/stats"),
      fetch("/api/records?limit=8"),
    ]);
    const stats = await statsRes.json();
    const records = await recRes.json();

    $("totalCount").textContent = stats.total;
    $("progressBar").style.width = `${Math.min(100, (stats.total / stats.target_for_first_model) * 100)}%`;

    $("recent").innerHTML = records.length
      ? records.map((r) => `
        <div class="row">
          <div>
            <strong>${labelsTr[r.label] || r.label}</strong>
            <div class="muted">${escapeHtml(r.cat_name)}</div>
          </div>
          <small>${new Date(r.created_at).toLocaleString("tr-TR")}<br>${r.duration_ms ? (r.duration_ms/1000).toFixed(1) + " sn" : ""}</small>
        </div>
      `).join("")
      : '<div class="muted">Henüz kayıt yok.</div>';
  } catch {
    $("message").textContent = "Sunucuya bağlanılamadı.";
  }
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (m) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
  }[m]));
}

$("recordBtn").addEventListener("click", startRecording);
$("stopBtn").addEventListener("click", stopRecording);
$("saveBtn").addEventListener("click", saveRecording);
$("discardBtn").addEventListener("click", discardRecording);

$("catName").value = localStorage.getItem("catName") || "";
refresh();

let deferredPrompt = null;
const installBtn = $("installBtn");
const installHint = $("installHint");

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/static/sw.js").catch((err) => {
      console.warn("Service worker kaydı başarısız:", err);
    });
  });
}

window.addEventListener("beforeinstallprompt", (event) => {
  event.preventDefault();
  deferredPrompt = event;
  installBtn?.classList.remove("hidden");
  if (installHint) installHint.textContent = "Tek dokunuşla ana ekrana yükleyebilirsin.";
});

installBtn?.addEventListener("click", async () => {
  if (!deferredPrompt) return;
  deferredPrompt.prompt();
  await deferredPrompt.userChoice;
  deferredPrompt = null;
  installBtn.classList.add("hidden");
});

const isIOS = /iphone|ipad|ipod/i.test(navigator.userAgent);
const isStandalone = window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone === true;

if (isIOS && !isStandalone && installHint) {
  installHint.textContent = "iPhone: Safari → Paylaş → Ana Ekrana Ekle.";
}

if (isStandalone && document.getElementById("installCard")) {
  document.getElementById("installCard").classList.add("hidden");
}
