// Simurg Studio — vanilla JS front-end.
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const j = (url, opts) => fetch(url, opts).then(async r => {
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || r.statusText);
  return r.json();
});
const postJSON = (url, body) => j(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
const toast = (m, k = "ok") => { const t = $("#toast"); t.textContent = m; t.className = `toast show ${k}`; setTimeout(() => t.className = "toast", 2600); };
const VP_ICON = { ground_to_air: "🛰️", air_to_air: "✈️", air_to_ground: "🔻", mixed: "🎲" };

// ---- tabs ----
$$(".nav").forEach(b => b.onclick = () => {
  $$(".nav").forEach(x => x.classList.remove("active"));
  $$(".tab").forEach(x => x.classList.remove("active"));
  b.classList.add("active"); $(`#tab-${b.dataset.tab}`).classList.add("active");
  ({ models: loadModels, skies: loadSkies, datasets: loadDatasets, advanced: loadAdvanced }[b.dataset.tab] || (() => {}))();
});

// ================= STUDIO =================
const STUDIO = { viewpoint: "ground_to_air", range: "mixed", classes: new Set(), skies: new Set(), allSkies: [] };

async function loadStudio() {
  const o = await j("/api/scene-options");
  const d = o.defaults;
  STUDIO.viewpoint = d.viewpoint; STUDIO.range = d.range || "mixed";
  STUDIO.classes = new Set(d.include_classes);
  STUDIO.allSkies = o.skies; STUDIO.skies = new Set(d.hdri_include);
  $("#tg-min").value = d.n_targets[0]; $("#tg-max").value = d.n_targets[1];
  $("#st-samples").placeholder = d.samples; $("#st-analog").checked = !!d.analog;

  // viewpoint cards
  $("#vp-grid").innerHTML = o.viewpoints.map(v =>
    `<div class="vp ${v.id === STUDIO.viewpoint ? "sel" : ""}" data-id="${v.id}">
       <div class="ico">${VP_ICON[v.id] || "•"}</div>
       <div><div class="t">${v.label}</div><div class="s">${v.elevation_deg[0]}° … ${v.elevation_deg[1]}°</div></div></div>`).join("");
  $$("#vp-grid .vp").forEach(el => el.onclick = () => {
    STUDIO.viewpoint = el.dataset.id;
    $$("#vp-grid .vp").forEach(x => x.classList.toggle("sel", x === el));
    $("#vp-hint").textContent = o.viewpoints.find(v => v.id === el.dataset.id).hint;
  });
  $("#vp-hint").textContent = o.viewpoints.find(v => v.id === STUDIO.viewpoint).hint;

  // range segmented
  $("#range-seg").innerHTML = o.ranges.map(r =>
    `<button class="${r.id === STUDIO.range ? "sel" : ""}" data-id="${r.id}">${r.label}</button>`).join("");
  $$("#range-seg button").forEach(b => b.onclick = () => {
    STUDIO.range = b.dataset.id; $$("#range-seg button").forEach(x => x.classList.toggle("sel", x === b));
  });

  // class chips
  $("#cls-chips").innerHTML = o.classes.map(c =>
    `<div class="chip ${STUDIO.classes.has(c) ? "sel" : ""}" data-c="${c}">${c}</div>`).join("");
  $$("#cls-chips .chip").forEach(ch => ch.onclick = () => {
    const c = ch.dataset.c; STUDIO.classes.has(c) ? STUDIO.classes.delete(c) : STUDIO.classes.add(c);
    ch.classList.toggle("sel"); updateCounts();
  });

  // sky chips
  renderSkyChips(); updateCounts();
}
function renderSkyChips() {
  $("#sky-chips").innerHTML = STUDIO.allSkies.map(s =>
    `<div class="chip ${STUDIO.skies.has(s) ? "sel" : ""}" data-s="${s}" title="${s}">${s.replace(/_\dk\.hdr$/, "").slice(0, 22)}</div>`).join("")
    || `<span class="muted small">No skies — add some in the Skies tab.</span>`;
  $$("#sky-chips .chip").forEach(ch => ch.onclick = () => {
    const s = ch.dataset.s; STUDIO.skies.has(s) ? STUDIO.skies.delete(s) : STUDIO.skies.add(s);
    ch.classList.toggle("sel"); updateCounts();
  });
}
function updateCounts() {
  $("#cls-count").textContent = `${STUDIO.classes.size} selected`;
  $("#sky-count").textContent = `${STUDIO.skies.size}/${STUDIO.allSkies.length}`;
}
$("#sky-all").onclick = () => {
  if (STUDIO.skies.size === STUDIO.allSkies.length) STUDIO.skies.clear();
  else STUDIO.skies = new Set(STUDIO.allSkies);
  renderSkyChips(); updateCounts();
};

function scenario(extra = {}) {
  return {
    viewpoint: STUDIO.viewpoint, range: STUDIO.range,
    n_targets: [+$("#tg-min").value, +$("#tg-max").value],
    include_classes: [...STUDIO.classes],
    hdri_include: STUDIO.skies.size === STUDIO.allSkies.length ? [] : [...STUDIO.skies],
    samples: $("#st-samples").value || null,
    analog: $("#st-analog").checked,
    output: ($("#st-out").value || "studio_run"),
    ...extra,
  };
}
$("#st-render").onclick = async () => {
  if (!STUDIO.classes.size) return toast("Pick at least one class", "err");
  await postJSON("/api/render", { studio: scenario(), n: +$("#st-n").value });
  toast("Render started"); window._previewOf = $("#st-out").value || "studio_run";
};
$("#st-preview").onclick = async () => {
  if (!STUDIO.classes.size) return toast("Pick at least one class", "err");
  await postJSON("/api/render", { studio: scenario({ output: "_preview", samples: 14 }), n: 4 });
  toast("Preview rendering…"); window._previewOf = "_preview";
};
$("#st-stop").onclick = () => window._activeJob && postJSON(`/api/job/${window._activeJob}/stop`).then(() => toast("Stopping…"));

// ================= MODELS =================
async function loadModels() {
  const o = await j("/api/scene-options").catch(() => ({ classes: [] }));
  const classes = o.classes || [];
  $("#m-class").innerHTML = classes.map(c => `<option>${c}</option>`).join("");
  const d = await j("/api/models");
  $("#m-count").textContent = d.models.length;
  const opts = (sel) => classes.map(c => `<option ${c === sel ? "selected" : ""}>${c}</option>`).join("");
  $("#m-grid").innerHTML = d.models.length ? d.models.map(m => {
    const nc = !["by", "cc0", "cc-by"].includes((m.license || "").toLowerCase());
    return `<div class="mcard ${m.enabled ? "" : "off"}" data-f="${m.file}">
      <div class="nm" title="${m.name}">${m.name}</div>
      <div class="meta"><span class="lic ${nc ? "nc" : ""}">${m.license}</span><span class="muted small">${m.mb}MB</span></div>
      <select class="m-cls">${opts(m.class)}</select>
      <div class="foot2">
        <label class="sw"><input type="checkbox" class="m-en" ${m.enabled ? "checked" : ""}><span></span></label>
        <span class="muted small">${m.enabled ? "in use" : "disabled"}</span>
        <span class="grow"></span><span class="x m-del">✕</span>
      </div></div>`;
  }).join("") : `<div class="muted small">No models. Fetch from Objaverse above, or render with proxy drones.</div>`;
  $$("#m-grid .mcard").forEach(card => {
    const f = card.dataset.f;
    $(".m-en", card).onchange = e => postJSON("/api/models/update", { file: f, enabled: e.target.checked }).then(loadModels);
    $(".m-cls", card).onchange = e => postJSON("/api/models/update", { file: f, class: e.target.value }).then(() => toast("Class set"));
    $(".m-del", card).onclick = () => postJSON("/api/models/delete", { file: f }).then(() => { toast("Deleted"); loadModels(); });
  });
}
$("#ob-fetch").onclick = async () => {
  await postJSON("/api/models/fetch", { categories: $("#ob-cats").value, per_class: +$("#ob-per").value, allow_all_licenses: $("#ob-all").checked });
  toast("Fetching models… (watch job panel)");
};
$("#m-upload").onclick = async () => {
  const f = $("#m-file").files[0]; if (!f) return toast("Pick a file", "err");
  const fd = new FormData(); fd.append("file", f); fd.append("class", $("#m-class").value); fd.append("license", $("#m-license").value || "unknown");
  await j("/api/models/upload", { method: "POST", body: fd }); toast("Uploaded"); loadModels();
};

// ================= SKIES =================
async function loadSkies() {
  const list = await j("/api/hdris");
  $("#h-count").textContent = list.length;
  $("#h-list").innerHTML = list.length ? list.map(h =>
    `<div class="chip">☁ ${h.name.replace(/_\dk\.hdr$/, "")} <span class="sz">${h.mb}MB</span> <span class="x" data-n="${h.name}">✕</span></div>`).join("")
    : `<span class="muted small">No skies yet.</span>`;
  $$("#h-list .x").forEach(x => x.onclick = () => postJSON("/api/hdris/delete", { name: x.dataset.n }).then(() => { toast("Deleted"); loadSkies(); }));
}
$("#h-fetch").onclick = async () => { await postJSON("/api/hdris/fetch", { n: +$("#h-n").value, res: $("#h-res").value }); toast("Downloading skies…"); };

// ================= DATASETS =================
async function loadDatasets() {
  const ds = await j("/api/datasets");
  $("#d-list").innerHTML = `<tr><th>dataset</th><th>images</th><th>boxes</th><th>empty</th><th></th></tr>` +
    (ds.length ? ds.map(d => `<tr><td><a class="link" data-n="${d.name}">${d.name}</a></td><td>${d.images}</td><td>${d.annotations}</td><td>${Math.round((d.empty_frac||0)*100)}%</td><td><a class="link" data-n="${d.name}">open ▸</a></td></tr>`).join("")
      : `<tr><td colspan="5" class="muted">No datasets yet.</td></tr>`);
  $$("#d-list .link").forEach(a => a.onclick = () => openDataset(a.dataset.n));
}
let CUR_DS = null;
async function openDataset(name) {
  CUR_DS = name; $("#d-detail").style.display = "block"; $("#d-title").textContent = name;
  const s = await j(`/api/dataset/${name}/stats`); const sz = Object.values(s.size_hist || {});
  $("#d-stats").innerHTML = `<span>images <b>${s.images}</b></span><span>boxes <b>${s.annotations}</b></span><span>empty <b>${Math.round(s.empty_frac*100)}%</b></span><span>tiny+small <b>${Math.round(((sz[0]||0)+(sz[1]||0))/Math.max(1,s.annotations)*100)}%</b></span>`;
  drawGallery("#d-gallery", name, await j(`/api/dataset/${name}/gallery?limit=60`), $("#d-boxes").checked);
  $("#d-detail").scrollIntoView({ behavior: "smooth" });
}
$("#d-boxes").onchange = () => CUR_DS && openDataset(CUR_DS);
$("#d-export").onclick = () => CUR_DS && postJSON(`/api/export/${CUR_DS}`, { val_split: 0.1 }).then(() => toast("Exporting YOLO…"));

function drawGallery(sel, name, g, showBoxes) {
  $(sel).innerHTML = (g.items || []).map(it => {
    const boxes = showBoxes ? it.boxes.map(b => {
      const [x, y, w, h] = b.bbox;
      return `<div class="bx" style="left:${x/it.w*100}%;top:${y/it.h*100}%;width:${w/it.w*100}%;height:${h/it.h*100}%"><span class="bl">${b.label}</span></div>`;
    }).join("") : "";
    return `<div class="thumb"><img loading="lazy" src="/api/dataset/${name}/image/${it.file}">${boxes}</div>`;
  }).join("") || `<div class="muted small">No frames.</div>`;
}

// ================= ADVANCED (raw config) =================
const FIELDS = [["render.width","Width"],["render.height","Height"],["render.samples","Samples"],
  ["camera.fov_deg","FOV° [min,max]","pair"],["camera.elevation_deg","Elevation° [min,max]","pair"],
  ["scene.n_targets","Targets [min,max]","pair"],["scene.distance_m","Distance m [min,max]","pair"],
  ["scene.target_scale_m","Size m [min,max]","pair"],["lighting.sun_energy","Sun energy [min,max]","pair"]];
let CFG = null;
const getp = (o, p) => p.split(".").reduce((a, k) => (a || {})[k], o);
const setp = (o, p, v) => { const ks = p.split("."); let a = o; ks.slice(0, -1).forEach(k => a = a[k] = a[k] || {}); a[ks.at(-1)] = v; };
async function loadAdvanced() {
  const cfgs = await j("/api/configs"); $("#c-name").innerHTML = cfgs.map(c => `<option>${c}</option>`).join("");
  if (cfgs.length) loadOneConfig(cfgs.includes("skywatch") ? "skywatch" : cfgs[0]);
}
$("#c-name").onchange = e => loadOneConfig(e.target.value);
$("#c-reload").onclick = () => loadOneConfig($("#c-name").value);
async function loadOneConfig(name) {
  CFG = await j(`/api/config/${name}`); $("#c-saveas").value = name;
  $("#c-fields").innerHTML = FIELDS.map(([p, label, t]) => {
    const v = getp(CFG, p);
    if (t === "pair") { const [a, b] = Array.isArray(v) ? v : [v, v];
      return `<label>${label}<div class="row"><input data-path="${p}" data-i="0" type="number" value="${a}" style="width:50%"><input data-path="${p}" data-i="1" type="number" value="${b}" style="width:50%"></div></label>`; }
    return `<label>${label}<input data-path="${p}" type="number" value="${v ?? ""}"></label>`;
  }).join("");
  renderClasses(CFG.classes || []);
}
function renderClasses(classes) {
  $("#c-classes").innerHTML = `<tr><th>name</th><th>id</th><th>shape</th><th></th></tr>` + classes.map((c, i) =>
    `<tr><td><input class="cc" data-i="${i}" data-k="name" value="${c.name}"></td><td><input class="cc" data-i="${i}" data-k="id" type="number" value="${c.id}" style="width:70px"></td>
     <td><select class="cc" data-i="${i}" data-k="shape"><option ${c.shape==="quad"?"selected":""}>quad</option><option ${c.shape==="fixedwing"?"selected":""}>fixedwing</option></select></td>
     <td><span class="x" data-i="${i}">✕</span></td></tr>`).join("");
  $$("#c-classes .x").forEach(x => x.onclick = () => { CFG.classes.splice(+x.dataset.i, 1); renderClasses(CFG.classes); });
}
$("#c-addclass").onclick = () => { CFG.classes = CFG.classes || []; CFG.classes.push({ name: "new_class", id: Math.max(0, ...CFG.classes.map(c => c.id)) + 1, shape: "quad" }); renderClasses(CFG.classes); };
$("#c-save").onclick = async () => {
  $$("#c-fields input").forEach(inp => { const p = inp.dataset.path;
    if (inp.dataset.i !== undefined) { const cur = getp(CFG, p); const arr = Array.isArray(cur) ? cur.slice() : [0, 0]; arr[+inp.dataset.i] = +inp.value; setp(CFG, p, arr); }
    else setp(CFG, p, +inp.value); });
  $$("#c-classes .cc").forEach(inp => { CFG.classes[+inp.dataset.i][inp.dataset.k] = inp.dataset.k === "id" ? +inp.value : inp.value; });
  await postJSON(`/api/config/${$("#c-saveas").value || "untitled"}`, CFG); toast("Saved");
};

// ================= JOB POLLING + PREVIEW =================
let lastDone = null;
async function poll() {
  try {
    const { active, jobs } = await j("/api/jobs");
    const mini = $("#jobMini");
    if (active) { window._activeJob = active.id;
      mini.innerHTML = `<div class="jm"><b>${active.kind}</b> · ${active.progress}%<div class="b"><i style="width:${active.progress}%"></i></div></div>`;
    } else { window._activeJob = null; mini.innerHTML = ""; }
    const job = active || jobs[0];
    if (job) {
      $("#st-status").innerHTML = `<span class="badge ${job.status}">${job.status}</span> ${job.kind}${job.output ? " → " + job.output : ""} · ${job.rendered}/${job.total || "?"} · ${job.elapsed}s`;
      $("#st-bar").style.width = job.progress + "%";
      $("#st-log").textContent = (job.log || []).join("\n"); $("#st-log").scrollTop = 1e9;
      $("#st-stop").style.display = job.status === "running" ? "inline-block" : "none";
      // refresh preview when a render job finishes
      if (job.kind === "render" && job.status === "done" && lastDone !== job.id) {
        lastDone = job.id;
        const name = window._previewOf || job.output;
        if (name) j(`/api/dataset/${name}/gallery?limit=8`).then(g => drawGallery("#st-preview-grid", name, g, true)).catch(() => {});
      }
    }
  } catch (e) {}
}
setInterval(poll, 1500);

// ---- init ----
loadStudio().catch(() => toast("Start the server, then refresh", "err"));
poll();
