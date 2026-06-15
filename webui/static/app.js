// Simurg control panel — vanilla JS, talks to the Flask API.
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const api = async (url, opts) => {
  const r = await fetch(url, opts);
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || r.statusText);
  return r.json();
};
const toast = (msg, kind = "ok") => {
  const t = $("#toast"); t.textContent = msg; t.className = `toast show ${kind}`;
  setTimeout(() => (t.className = "toast"), 2600);
};

// ---- tabs ----
$$(".nav").forEach(b => b.onclick = () => {
  $$(".nav").forEach(x => x.classList.remove("active"));
  $$(".tab").forEach(x => x.classList.remove("active"));
  b.classList.add("active");
  $(`#tab-${b.dataset.tab}`).classList.add("active");
  ({ config: loadConfigTab, hdris: loadHdris, models: loadModels, datasets: loadDatasets }[b.dataset.tab] || (() => {}))();
});

// ================= RENDER =================
async function loadConfigsInto(sel) {
  const cfgs = await api("/api/configs");
  sel.innerHTML = cfgs.map(c => `<option>${c}</option>`).join("");
  return cfgs;
}
$("#r-start").onclick = async () => {
  const body = {
    config: $("#r-config").value, n: +$("#r-n").value,
    output: $("#r-out").value || ($("#r-config").value + "_run"),
    samples: $("#r-samples").value || null, seed: $("#r-seed").value || null,
  };
  try { await api("/api/render", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }); toast("Render started"); }
  catch (e) { toast(e.message, "err"); }
};
$("#r-preview").onclick = async () => {
  const body = { config: $("#r-config").value, n: 1, output: "_preview", samples: 12 };
  await api("/api/render", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  toast("Preview rendering…");
};
$("#r-stop").onclick = async () => {
  if (window._activeJob) { await api(`/api/job/${window._activeJob}/stop`, { method: "POST" }); toast("Stopping…"); }
};

// ================= CONFIG =================
const FIELDS = [
  ["render.width", "Width", "number"], ["render.height", "Height", "number"],
  ["render.samples", "Samples", "number"],
  ["camera.fov_deg", "FOV° [min,max]", "pair"],
  ["scene.n_targets", "Targets/frame [min,max]", "pair"],
  ["scene.distance_m", "Distance m [min,max]", "pair"],
  ["scene.target_scale_m", "Target size m [min,max]", "pair"],
  ["lighting.sun_energy", "Sun energy [min,max]", "pair"],
  ["lighting.sun_elevation_deg", "Sun elev° [min,max]", "pair"],
];
let CURRENT_CFG = null;
const getp = (o, path) => path.split(".").reduce((a, k) => (a || {})[k], o);
const setp = (o, path, v) => { const ks = path.split("."); let a = o; ks.slice(0, -1).forEach(k => (a = a[k] = a[k] || {})); a[ks.at(-1)] = v; };

async function loadConfigTab() {
  const cfgs = await loadConfigsInto($("#c-name"));
  if (cfgs.length) await loadOneConfig(cfgs[0]);
}
$("#c-name").onchange = e => loadOneConfig(e.target.value);
$("#c-reload").onclick = () => loadOneConfig($("#c-name").value);

async function loadOneConfig(name) {
  CURRENT_CFG = await api(`/api/config/${name}`);
  $("#c-saveas").value = name;
  // fields
  $("#c-fields").innerHTML = FIELDS.map(([path, label, type]) => {
    const v = getp(CURRENT_CFG, path);
    if (type === "pair") {
      const [a, b] = Array.isArray(v) ? v : [v, v];
      return `<label>${label}<div class="row"><input data-path="${path}" data-i="0" type="number" value="${a}" style="width:50%"><input data-path="${path}" data-i="1" type="number" value="${b}" style="width:50%"></div></label>`;
    }
    return `<label>${label}<input data-path="${path}" type="number" value="${v ?? ""}"></label>`;
  }).join("");
  // classes
  renderClasses(CURRENT_CFG.classes || []);
  // model class dropdown (used in models tab too)
  window._classes = (CURRENT_CFG.classes || []).map(c => c.name);
}

function renderClasses(classes) {
  const t = $("#c-classes");
  t.innerHTML = `<tr><th>name</th><th>id</th><th>shape</th><th></th></tr>` +
    classes.map((c, i) => `<tr>
      <td><input class="cc" data-i="${i}" data-k="name" value="${c.name}"></td>
      <td><input class="cc" data-i="${i}" data-k="id" type="number" value="${c.id}" style="width:70px"></td>
      <td><select class="cc" data-i="${i}" data-k="shape">
        <option ${c.shape === "quad" ? "selected" : ""}>quad</option>
        <option ${c.shape === "fixedwing" ? "selected" : ""}>fixedwing</option></select></td>
      <td><span class="x" data-i="${i}">✕</span></td></tr>`).join("");
  $$(".x", t).forEach(x => x.onclick = () => { CURRENT_CFG.classes.splice(+x.dataset.i, 1); renderClasses(CURRENT_CFG.classes); });
}
$("#c-addclass").onclick = () => {
  CURRENT_CFG.classes = CURRENT_CFG.classes || [];
  const nextId = Math.max(0, ...CURRENT_CFG.classes.map(c => c.id)) + 1;
  CURRENT_CFG.classes.push({ name: "new_class", id: nextId, shape: "quad" });
  renderClasses(CURRENT_CFG.classes);
};
$("#c-save").onclick = async () => {
  // collect scalar/pair fields
  $$("#c-fields input").forEach(inp => {
    const path = inp.dataset.path;
    if (inp.dataset.i !== undefined) {
      const cur = getp(CURRENT_CFG, path); const arr = Array.isArray(cur) ? cur.slice() : [0, 0];
      arr[+inp.dataset.i] = +inp.value; setp(CURRENT_CFG, path, arr);
    } else setp(CURRENT_CFG, path, +inp.value);
  });
  // collect classes
  $$("#c-classes .cc").forEach(inp => {
    const i = +inp.dataset.i, k = inp.dataset.k;
    CURRENT_CFG.classes[i][k] = k === "id" ? +inp.value : inp.value;
  });
  const name = ($("#c-saveas").value || "untitled").trim();
  try {
    await api(`/api/config/${name}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(CURRENT_CFG) });
    toast(`Saved ${name}.yaml`); loadConfigsInto($("#r-config"));
  } catch (e) { toast(e.message, "err"); }
};

// ================= HDRIS =================
async function loadHdris() {
  const list = await api("/api/hdris");
  $("#h-count").textContent = list.length;
  $("#h-list").innerHTML = list.length ? list.map(h =>
    `<div class="chip">☁ ${h.name} <span class="sz">${h.mb}MB</span> <span class="x" data-n="${h.name}">✕</span></div>`).join("")
    : `<span class="muted">No skies yet — download some, or the renderer falls back to a flat sky.</span>`;
  $$("#h-list .x").forEach(x => x.onclick = async () => {
    await api("/api/hdris/delete", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: x.dataset.n }) });
    toast("Deleted"); loadHdris();
  });
}
$("#h-fetch").onclick = async () => {
  const body = { n: +$("#h-n").value, res: $("#h-res").value };
  await api("/api/hdris/fetch", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  toast("Downloading skies… (watch job panel)"); $("#h-fetchlog").textContent = "Fetching…";
};

// ================= MODELS =================
async function loadModels() {
  const d = await api("/api/models");
  const classes = window._classes || (await api("/api/config/skywatch").catch(() => ({ classes: [] }))).classes?.map(c => c.name) || [];
  $("#m-class").innerHTML = classes.map(c => `<option>${c}</option>`).join("");
  const man = Object.fromEntries((d.manifest || []).map(m => [m.file, m]));
  $("#m-list").innerHTML = `<tr><th>file</th><th>class</th><th>license</th><th>size</th><th></th></tr>` +
    (d.files.length ? d.files.map(f => {
      const m = man[f.file] || {};
      return `<tr><td>✈ ${f.file}</td><td>${m.class || "<span class='muted'>—</span>"}</td><td>${m.license || "—"}</td><td>${f.mb}MB</td><td><span class="x" data-f="${f.file}">✕</span></td></tr>`;
    }).join("") : `<tr><td colspan="5" class="muted">No models uploaded.</td></tr>`);
  $$("#m-list .x").forEach(x => x.onclick = async () => {
    await api("/api/models/delete", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ file: x.dataset.f }) });
    toast("Removed"); loadModels();
  });
}
$("#m-upload").onclick = async () => {
  const f = $("#m-file").files[0];
  if (!f) return toast("Pick a file first", "err");
  const fd = new FormData(); fd.append("file", f); fd.append("class", $("#m-class").value); fd.append("license", $("#m-license").value || "unknown");
  try { await api("/api/models/upload", { method: "POST", body: fd }); toast("Uploaded"); loadModels(); }
  catch (e) { toast(e.message, "err"); }
};

// ================= DATASETS =================
async function loadDatasets() {
  const ds = await api("/api/datasets");
  $("#d-list").innerHTML = `<tr><th>dataset</th><th>images</th><th>annotations</th><th>empty</th><th></th></tr>` +
    (ds.length ? ds.map(d => `<tr>
      <td><a class="link" data-n="${d.name}">${d.name}</a></td>
      <td>${d.images}</td><td>${d.annotations}</td><td>${Math.round((d.empty_frac||0)*100)}%</td>
      <td><a class="link open" data-n="${d.name}">open ▸</a></td></tr>`).join("")
      : `<tr><td colspan="5" class="muted">No datasets yet — render one first.</td></tr>`);
  $$("#d-list .link").forEach(a => a.onclick = () => openDataset(a.dataset.n));
}
let CUR_DS = null;
async function openDataset(name) {
  CUR_DS = name;
  $("#d-detail").style.display = "block";
  $("#d-title").textContent = name;
  const s = await api(`/api/dataset/${name}/stats`);
  const sz = s.size_hist || {};
  $("#d-stats").innerHTML = `
    <span>images <b>${s.images}</b></span><span>boxes <b>${s.annotations}</b></span>
    <span>empty <b>${Math.round(s.empty_frac*100)}%</b></span>
    <span>avg/img <b>${s.avg_targets_per_image}</b></span>
    <span>tiny+small <b>${Math.round(((Object.values(sz)[0]||0)+(Object.values(sz)[1]||0))/Math.max(1,s.annotations)*100)}%</b></span>`;
  const g = await api(`/api/dataset/${name}/gallery?limit=60`);
  drawGallery(name, g);
  $("#d-detail").scrollIntoView({ behavior: "smooth" });
}
function drawGallery(name, g) {
  const showBoxes = $("#d-boxes").checked;
  $("#d-gallery").innerHTML = g.items.map(it => {
    const boxes = showBoxes ? it.boxes.map(b => {
      const [x, y, w, h] = b.bbox;
      const L = x / it.w * 100, T = y / it.h * 100, W = w / it.w * 100, H = h / it.h * 100;
      return `<div class="bx" style="left:${L}%;top:${T}%;width:${W}%;height:${H}%"><span class="bl">${b.label}</span></div>`;
    }).join("") : "";
    return `<div class="thumb"><img loading="lazy" src="/api/dataset/${name}/image/${it.file}">${boxes}</div>`;
  }).join("");
}
$("#d-boxes").onchange = () => CUR_DS && openDataset(CUR_DS);
$("#d-export").onclick = async () => {
  if (!CUR_DS) return;
  await api(`/api/export/${CUR_DS}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ val_split: 0.1 }) });
  toast("Exporting YOLO… (watch job panel)");
};

// ================= JOB POLLING =================
async function poll() {
  try {
    const { active, jobs } = await api("/api/jobs");
    const mini = $("#jobMini");
    if (active) {
      window._activeJob = active.id;
      mini.innerHTML = `<div class="jm"><b>${active.kind}</b> · ${active.progress}%<br><span class="muted small">${active.output || ""}</span></div>`;
    } else { window._activeJob = null; mini.innerHTML = ""; }
    // render tab live view: prefer active, else most recent
    const j = active || jobs[0];
    if (j) {
      $("#r-status").innerHTML = `<span class="badge ${j.status}">${j.status}</span> ${j.kind} ${j.output ? "→ " + j.output : ""} · ${j.rendered}/${j.total || "?"} · ${j.elapsed}s`;
      $("#r-bar").style.width = j.progress + "%";
      $("#r-log").textContent = (j.log || []).join("\n");
      $("#r-log").scrollTop = 1e9;
      $("#r-stop").style.display = j.status === "running" ? "inline-block" : "none";
    }
  } catch (e) { /* server starting */ }
}
setInterval(poll, 1500);

// ---- init ----
(async () => {
  await loadConfigsInto($("#r-config"));
  poll();
})();
