// ManaForge front-end — talks to /api/build and renders the deck.

const COLOR_INFO = {
  W: { name: "White", cls: "pip-w" },
  U: { name: "Blue", cls: "pip-u" },
  B: { name: "Black", cls: "pip-b" },
  R: { name: "Red", cls: "pip-r" },
  G: { name: "Green", cls: "pip-g" },
};
const CAT_TITLES = {
  commander: "Commander",
  theme: "On-theme creatures & payoffs",
  ramp: "Ramp",
  draw: "Card draw",
  removal: "Removal",
  wipe: "Board wipes",
  lands: "Lands",
};

const $ = (id) => document.getElementById(id);

document.addEventListener("DOMContentLoaded", () => {
  fetch("/api/health").then(r => r.json()).then(h => {
    $("llm-badge").textContent = h.llm_enabled ? "LLM enrichment: on" : "Logic engine: heuristic";
  }).catch(() => {});

  document.querySelectorAll(".chip").forEach(btn => {
    btn.addEventListener("click", () => { $("desc").value = btn.dataset.fill; });
  });
  $("build").addEventListener("click", buildDeck);
});

async function buildDeck() {
  const description = $("desc").value.trim();
  if (!description) { showStatus("Enter a theme first.", true); return; }

  const btn = $("build");
  btn.disabled = true;
  $("results").hidden = true;
  showStatus('<span class="spinner"></span> Interpreting the theme and querying Scryfall…', false);

  try {
    const resp = await fetch("/api/build", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        description,
        format: $("fmt").value === "auto" ? "commander" : $("fmt").value,
        deck_type_hint: $("fmt").value === "auto" ? "" : $("fmt").value,
        offline: $("offline").checked,
        references: $("references").value.trim(),
      }),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || "Build failed.");
    render(data);
    $("status").hidden = true;
  } catch (e) {
    showStatus("⚠ " + e.message, true);
  } finally {
    btn.disabled = false;
  }
}

function showStatus(html, isError) {
  const el = $("status");
  el.hidden = false;
  el.className = "status" + (isError ? " error" : "");
  el.innerHTML = html;
}

function render(data) {
  const p = data.params;
  const s = data.stats;

  // Identity panel
  const colorDots = p.colors.map(c => {
    const info = COLOR_INFO[c] || { name: c, cls: "" };
    return `<span class="color-dot"><span class="pip ${info.cls}"></span>${info.name}</span>`;
  }).join("");
  $("identity-panel").innerHTML = `
    <h3>Deck identity</h3>
    <div class="identity-colors">${colorDots}</div>
    <div class="meta-row"><span>Archetype</span><b>${p.archetype}</b></div>
    <div class="meta-row"><span>Format</span><b>${data.format === "commander" ? "Commander" : "60-card"}</b></div>
    ${p.set_names && p.set_names.length ? `<div class="meta-row"><span>Set focus</span><b>${escapeHtml(p.set_names.join(", "))}</b></div>` : ""}
    ${p.reference_cards && p.reference_cards.length ? `<div class="meta-row"><span>References</span><b>${escapeHtml(p.reference_cards.slice(0, 4).join(", "))}</b></div>` : ""}
    <div class="meta-row"><span>Total cards</span><b>${s.total_cards}</b></div>
    <div class="meta-row"><span>Lands</span><b>${s.lands}</b></div>
    <div class="meta-row"><span>Avg mana value</span><b>${s.avg_cmc}</b></div>
    ${p.oracle_terms && p.oracle_terms.length ? `<div class="meta-row"><span>Theme terms</span><b style="text-transform:none">${p.oracle_terms.join(", ")}</b></div>` : ""}
  `;

  // Reasoning panel
  $("reasoning-panel").innerHTML = `
    <h3>How this deck was built</h3>
    <div class="reasoning">${mdBold(data.reasoning)}</div>
    <span class="src-pill">card data: ${data.source === "offline" ? "offline sample" : "live Scryfall"} · logic: ${p.source}</span>
  `;

  renderCurve(s.curve);
  renderComposition(data.categories);
  renderExpansion(p.expansion);
  renderDecklist(data.categories);

  $("results").hidden = false;
  $("results").scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderCurve(curve) {
  const max = Math.max(1, ...Object.values(curve));
  const labels = { "1": "0-1", "2": "2", "3": "3", "4": "4", "5": "5", "6": "6+" };
  $("curve").innerHTML = Object.keys(labels).map(k => {
    const v = curve[k] || 0;
    const h = Math.round((v / max) * 120);
    return `<div class="bar-wrap">
      <span class="bar-count">${v}</span>
      <div class="bar" style="height:${h}px"></div>
      <span class="bar-label">${labels[k]}</span>
    </div>`;
  }).join("");
}

function renderComposition(categories) {
  const order = ["theme", "ramp", "draw", "removal", "wipe", "lands"];
  const counts = {};
  order.forEach(c => {
    if (!categories[c]) return;
    counts[c] = categories[c].reduce((n, x) => n + (x.count || 1), 0);
  });
  const max = Math.max(1, ...Object.values(counts));
  $("composition").innerHTML = Object.keys(counts).map(c => {
    const w = Math.round((counts[c] / max) * 100);
    return `<div class="comp-row">
      <span class="comp-name">${CAT_TITLES[c] === "On-theme creatures & payoffs" ? "theme" : c}</span>
      <span class="comp-bar" style="width:${Math.max(6, w)}%"></span>
      <span class="comp-count">${counts[c]}</span>
    </div>`;
  }).join("");
}

function renderExpansion(expansion) {
  const panel = $("expansion-panel");
  if (!expansion || !expansion.concepts || !expansion.concepts.length) {
    panel.innerHTML = "";
    panel.hidden = true;
    return;
  }
  panel.hidden = false;
  panel.innerHTML = `
    <h3>Semantic expansion</h3>
    <div class="expansion-tags">
      <div><strong>Expanded concepts</strong><br>${escapeHtml(expansion.concepts.slice(0, 10).join(", "))}</div>
      <div><strong>MTG themes</strong><br>${escapeHtml(expansion.mtg_themes.join(", "))}</div>
    </div>
  `;
}

function renderDecklist(categories) {
  const order = ["commander", "theme", "ramp", "draw", "removal", "wipe", "lands"];
  let html = "";
  order.forEach(cat => {
    const cards = categories[cat];
    if (!cards || !cards.length) return;
    const total = cards.reduce((n, x) => n + (x.count || 1), 0);
    html += `<div class="cat-block"><div class="cat-head">
      <h3>${CAT_TITLES[cat] || cat}</h3><span class="n">${total} card${total !== 1 ? "s" : ""}</span></div>`;

    if (cat === "lands") {
      html += `<div class="grid">` + cards.map(landCard).join("") + `</div>`;
    } else {
      html += `<div class="grid">` + cards.map(cardTile).join("") + `</div>`;
    }
    html += `</div>`;
  });
  $("decklist").innerHTML = html;
}

function cardTile(c) {
  const img = c.image
    ? `<img loading="lazy" src="${c.image}" alt="${escapeHtml(c.name)}" onerror="this.replaceWith(Object.assign(document.createElement('div'),{className:'noimg',textContent:'${escapeAttr(c.name)}'}))" />`
    : `<div class="noimg">${escapeHtml(c.name)}<br><small>${escapeHtml(c.type_line || "")}</small></div>`;
  const qty = (c.count && c.count > 1) ? `${c.count}× ` : "";
  const link = c.uri
    ? `<a href="${c.uri}" target="_blank" rel="noopener">${qty}${escapeHtml(c.name)}</a>`
    : `${qty}${escapeHtml(c.name)}`;
  return `<div class="mcard">${img}<div class="cname">${link}<span class="cmc">${manaText(c.mana_cost)}</span></div></div>`;
}

function landCard(c) {
  return `<div class="mcard land-line"><span>${escapeHtml(c.name)}</span><span class="cmc">×${c.count || 1}</span></div>`;
}

function manaText(cost) { return (cost || "").replace(/[{}]/g, ""); }
function mdBold(t) { return escapeHtml(t).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>"); }
function escapeHtml(s) { return (s || "").replace(/[&<>"]/g, m => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[m])); }
function escapeAttr(s) { return escapeHtml(s).replace(/'/g, "&#39;"); }
