(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const FIELDS = ["city", "district", "area_m2", "age_years", "rooms", "bathrooms", "floor", "finishing", "asking_price"];
  const NUMERIC = ["area_m2", "age_years", "rooms", "bathrooms", "floor", "asking_price"];
  const FINISHING = { none: "بدون تشطيب", semi: "نص تشطيب", full: "تشطيب كامل", luxury: "سوبر لوكس" };
  const CONF = { low: "منخفضة", medium: "متوسطة", high: "عالية" };
  const VERDICT = {
    overpriced: { badge: "▼ مبالغ فيه", cls: "overpriced", color: "#9F1D1D" },
    fair: { badge: "● سعر عادل", cls: "fair", color: "#854D0E" },
    opportunity: { badge: "▲ فرصة", cls: "opportunity", color: "#166534" },
  };
  const nf = new Intl.NumberFormat("en-US");
  const fmt = (n) => nf.format(Math.round(n));
  const fmtM = (n) => (n / 1e6).toFixed(2);

  let meta = null;
  let chart = null;

  /* ---------- helpers ---------- */
  const toLatin = (s) =>
    String(s)
      .replace(/[\u0660-\u0669]/g, (d) => d.charCodeAt(0) - 0x0660)
      .replace(/[\u06F0-\u06F9]/g, (d) => d.charCodeAt(0) - 0x06f0)
      .replace(/[\u066B]/g, ".")
      .replace(/[\u066C\u060C,\s]/g, "");

  const parseNum = (s) => {
    const v = toLatin(s);
    return v === "" || isNaN(Number(v)) ? null : Number(v);
  };

  const monthLabel = (ym, withYear = true) => {
    const [y, m] = ym.split("-").map(Number);
    return new Date(y, m - 1, 1).toLocaleDateString("ar-EG-u-nu-latn", withYear ? { month: "short", year: "numeric" } : { month: "short" });
  };

  const el = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  };

  async function api(url, options) {
    const res = await fetch(url, options);
    let body = null;
    try { body = await res.json(); } catch (_) { /* ignore */ }
    if (!res.ok) {
      const err = new Error((body && body.error) || "حصل خطأ غير متوقع. حاول مرة تانية.");
      err.fields = (body && body.fields) || {};
      throw err;
    }
    return body;
  }

  /* ---------- form setup ---------- */
  function fillDistricts() {
    const city = meta.cities.find((c) => c.name === $("city").value);
    const sel = $("district");
    sel.replaceChildren(new Option("اختر الحي", ""));
    (city ? city.districts : []).forEach((d) => sel.add(new Option(d.name, d.name)));
  }

  function clearErrors() {
    FIELDS.forEach((f) => {
      const input = $(f), err = $("err-" + f);
      input.removeAttribute("aria-invalid");
      input.removeAttribute("aria-describedby");
      err.hidden = true; err.textContent = "";
    });
    $("form-error").hidden = true;
  }

  function showErrors(fields, message) {
    let first = null;
    FIELDS.filter((f) => fields && fields[f]).forEach((f) => {
      const msg = fields[f];
      $(f).setAttribute("aria-invalid", "true");
      $(f).setAttribute("aria-describedby", "err-" + f);
      $("err-" + f).textContent = msg; $("err-" + f).hidden = false;
      first = first || $(f);
    });
    if (message) { $("form-error").textContent = message; $("form-error").hidden = false; }
    if (first) first.focus();
  }

  async function init() {
    try {
      meta = await api("/api/meta");
    } catch (e) {
      showErrors({}, "مقدرناش نحمّل بيانات الأحياء. اتأكد إن السيرفر شغال وحدّث الصفحة.");
      return;
    }
    $("city").replaceChildren(...meta.cities.map((c) => new Option(c.name, c.name)));
    fillDistricts();
    $("finishing").replaceChildren(new Option("اختر التشطيب", ""),
      ...meta.finishing.map((k) => new Option(FINISHING[k] || k, k)));
    if (meta.data_source === "synthetic") $("notice").hidden = false;
    $("city").addEventListener("change", () => { fillDistricts(); syncMap(); });
    $("district").addEventListener("change", syncMap);
    initMap();

    const price = $("asking_price");
    price.addEventListener("blur", () => { const v = parseNum(price.value); if (v !== null) price.value = fmt(v); });
    applyQuery();
  }

  /* ---------- map ---------- */
  let map = null;
  const markers = {};

  function priceColor(v, min, max) {
    const t = v == null || max === min ? 0.5 : (v - min) / (max - min);
    const a = [191, 230, 224], b = [11, 95, 89];
    return "rgb(" + a.map((c, i) => Math.round(c + (b[i] - c) * t)).join(",") + ")";
  }

  function initMap() {
    const card = $("map-card");
    if (!window.L || !meta.map) { card.hidden = true; return; }
    const all = meta.cities.flatMap((c) => c.districts.map((d) => ({ ...d, city: c.name }))).filter((d) => d.lat != null && d.lng != null);
    if (!all.length) { card.hidden = true; return; }
    map = L.map("map", { scrollWheelZoom: false, dragging: !L.Browser.mobile, attributionControl: true })
      .setView(meta.map.center, meta.map.zoom);
    L.tileLayer(meta.map.tiles, { attribution: meta.map.attribution, maxZoom: 18 }).addTo(map);
    const prices = all.map((d) => d.avg_ppm).filter((v) => v != null);
    const min = Math.min(...prices), max = Math.max(...prices);
    all.forEach((d) => {
      const m = L.circleMarker([d.lat, d.lng], { radius: 11, weight: 2, color: "#fff", fillColor: priceColor(d.avg_ppm, min, max), fillOpacity: 0.92 }).addTo(map);
      const tip = el("div", "map-tip");
      tip.append(el("strong", "", d.name), el("br"),
        document.createTextNode(d.avg_ppm ? `${fmt(d.avg_ppm)} ج.م/م² · ${fmt(d.sales)} صفقة` : `${fmt(d.sales)} صفقة`));
      m.bindTooltip(tip, { direction: "top", offset: [0, -8] });
      m.on("click", () => {
        $("city").value = d.city; fillDistricts(); $("district").value = d.name;
        $("district").dispatchEvent(new Event("change"));
      });
      markers[d.city + "|" + d.name] = m;
    });
    if (all.length > 1) map.fitBounds(L.latLngBounds(all.map((d) => [d.lat, d.lng])), { padding: [36, 36], maxZoom: 15 });
  }

  function syncMap() {
    if (!map) return;
    const key = $("city").value + "|" + $("district").value;
    Object.entries(markers).forEach(([k, m]) => {
      const on = k === key;
      m.setStyle({ weight: on ? 4 : 2, color: on ? "#0B1F33" : "#fff" });
      if (on) { m.bringToFront(); map.panTo(m.getLatLng()); }
    });
  }

  /* ---------- prefill from URL (used by the history page) ---------- */
  function applyQuery() {
    const q = new URLSearchParams(window.location.search);
    if (!q.has("district")) return;
    if (q.get("city") && meta.cities.some((c) => c.name === q.get("city"))) { $("city").value = q.get("city"); fillDistricts(); }
    if ([...$("district").options].some((o) => o.value === q.get("district"))) $("district").value = q.get("district");
    FIELDS.slice(2).forEach((f) => {
      if (!q.has(f) || q.get(f) === "") return;
      const v = q.get(f);
      $(f).value = f === "asking_price" && parseNum(v) !== null ? fmt(parseNum(v)) : v;
    });
    syncMap();
    if (q.get("run") === "1") $("form").requestSubmit();
  }

  /* ---------- rendering ---------- */
  function rangeBarSVG(low, pred, high, asking, color) {
    const lo = Math.min(low, asking), hi = Math.max(high, asking);
    const pad = (hi - lo) * 0.3 || pred * 0.1;
    const raw = (hi - lo + 2 * pad) / 4;
    const step = [10e3, 25e3, 50e3, 100e3, 250e3, 500e3, 1e6, 2.5e6, 5e6, 1e7].find((s) => s >= raw) || 1e7;
    const min = Math.floor((lo - pad) / step) * step, max = Math.ceil((hi + pad) / step) * step;
    const compact = window.innerWidth < 700;
    const W = compact ? 360 : 720, X = (v) => 20 + ((v - min) / (max - min)) * W;
    const near = Math.abs(X(asking) - X(pred)) < (compact ? 90 : 100);
    let ticks = "";
    for (let v = min; v <= max + 1; v += step) {
      ticks += `<text x="${X(v).toFixed(1)}" y="90">${fmtM(v)}</text>`;
    }
    return `<svg viewBox="0 0 ${W + 40} 100" role="img" aria-label="النطاق المتوقع من ${fmtM(low)} إلى ${fmtM(high)} مليون، والسعر المعروض ${fmtM(asking)} مليون">
      <rect x="20" y="48" width="${W}" height="8" rx="4" fill="#E1E6EC"/>
      <rect x="${X(low).toFixed(1)}" y="48" width="${(X(high) - X(low)).toFixed(1)}" height="8" rx="4" fill="#99D5CE"/>
      <rect x="${(X(pred) - 2).toFixed(1)}" y="38" width="4" height="28" rx="2" fill="#0F766E"/>
      <path d="M${X(asking).toFixed(1)} 40l9 12-9 12-9-12z" fill="${color}"/>
      <g font-size="12" text-anchor="middle" font-family="IBM Plex Sans Arabic, sans-serif">
        <text x="${X(pred).toFixed(1)}" y="30" font-weight="600" fill="#0F766E">المتوقع ${fmtM(pred)}</text>
        <text x="${X(asking).toFixed(1)}" y="${near ? 14 : 30}" font-weight="600" fill="${color}">المعروض ${fmtM(asking)}</text>
        <g fill="#33475B">${ticks}</g>
      </g></svg>`;
  }

  function renderResult(input, r) {
    const v = VERDICT[r.verdict];
    $("chips").replaceChildren(
      ...[`${input.city} · ${input.district}`, `${fmt(input.area_m2)} م²`, `عمر ${input.age_years} سنة`,
          `الدور ${input.floor}`, FINISHING[input.finishing]].map((t) => el("span", "chip", t)));
    $("r-price").textContent = fmt(r.predicted);
    $("r-range").textContent = `النطاق المتوقع: من ${fmt(r.range[0])} إلى ${fmt(r.range[1])} ج.م`;
    $("range-bar").innerHTML = rangeBarSVG(r.range[0], r.predicted, r.range[1], r.asking_price, v.color);

    const badge = $("r-badge");
    badge.textContent = v.badge; badge.className = "badge " + v.cls;
    $("r-diff").textContent = (r.diff_pct > 0 ? "+" : "") + r.diff_pct.toFixed(1) + "%";
    const amount = fmt(Math.abs(r.diff_amount));
    $("r-diff-text").textContent =
      r.verdict === "overpriced" ? `السعر المعروض أعلى من المتوقع بمقدار ${amount} ج.م.`
      : r.verdict === "opportunity" ? `السعر المعروض أقل من المتوقع بمقدار ${amount} ج.م.`
      : `السعر المعروض قريب من المتوقع (فرق ${amount} ج.م).`;

    $("k-pred").textContent = fmt(r.per_m2.predicted);
    $("k-ask").textContent = fmt(r.per_m2.asking);
    $("k-diff").textContent = (r.diff_amount > 0 ? "+" : r.diff_amount < 0 ? "-" : "") + fmt(Math.abs(r.diff_amount));
    $("k-conf").textContent = CONF[r.confidence];
    $("k-conf-note").textContent = `بناءً على ${fmt(r.district_sales)} صفقة في الحي`;
  }

  function renderTrend(t) {
    const labels = [...t.months, ...t.forecast_months].map((m) => monthLabel(m));
    const hist = [...t.avg_price_m2, ...t.forecast_months.map(() => null)];
    const lastIdx = t.avg_price_m2.map((v) => v !== null).lastIndexOf(true);
    const fc = labels.map(() => null);
    if (lastIdx >= 0 && t.forecast_avg_price_m2.length) {
      fc[lastIdx] = t.avg_price_m2[lastIdx];
      t.forecast_avg_price_m2.forEach((v, i) => { fc[t.months.length + i] = v; });
    }
    if (chart) chart.destroy();
    Chart.defaults.font.family = '"IBM Plex Sans Arabic", sans-serif';
    chart = new Chart($("trend-chart"), {
      type: "line",
      data: { labels, datasets: [
        { label: "متوسط سعر المتر", data: hist, borderColor: "#0F766E", backgroundColor: "rgba(15,118,110,.1)", fill: true, tension: 0.25, borderWidth: 2.5, pointRadius: 0, pointHoverRadius: 4, spanGaps: true },
        { label: "توقع", data: fc, borderColor: "#0F766E", borderDash: [6, 5], borderWidth: 2.5, pointRadius: 0, pointHoverRadius: 4, spanGaps: true, fill: false },
      ] },
      options: {
        responsive: true, maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: { legend: { display: false }, tooltip: { rtl: true, callbacks: { label: (c) => `${c.dataset.label}: ${fmt(c.parsed.y)} ج.م/م²` } } },
        scales: {
          x: { grid: { display: false }, ticks: { maxTicksLimit: window.innerWidth < 700 ? 4 : 6, maxRotation: 0, autoSkip: true, color: "#5B6B7B" } },
          y: { grid: { color: "#E1E6EC" }, ticks: { color: "#5B6B7B", callback: (v) => fmt(v) } },
        },
      },
    });
  }

  function renderComps(items) {
    const ul = $("comps");
    if (!items.length) { ul.replaceChildren(el("li", "empty", "مفيش صفقات مشابهة في آخر 12 شهر.")); return; }
    ul.replaceChildren(...items.map((c) => {
      const li = el("li");
      const left = el("div");
      left.append(el("div", "t", `${fmt(c.area_m2)} م² · ${c.rooms} غرف`),
                  el("div", "s", `${monthLabel(c.sale_date.slice(0, 7))} · الدور ${c.floor} · ${FINISHING[c.finishing] || c.finishing}`));
      const right = el("div", "p", fmt(c.price));
      right.append(el("small", "", `${fmt(c.price_per_m2)} ج.م/م²`));
      li.append(left, right);
      return li;
    }));
  }

  /* ---------- submit ---------- */
  async function onSubmit(ev) {
    ev.preventDefault();
    clearErrors();
    const payload = {};
    FIELDS.forEach((f) => { payload[f] = NUMERIC.includes(f) ? parseNum($(f).value) : $(f).value; });
    const btn = $("submit");
    btn.disabled = true; btn.textContent = "جاري الحساب...";
    try {
      const r = await api("/api/predict", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      const q = new URLSearchParams({ city: payload.city });
      const [trend, comps] = await Promise.all([
        api(`/api/trend/${encodeURIComponent(payload.district)}?${q}`),
        api(`/api/comparables?${new URLSearchParams({ city: payload.city, district: payload.district, area: payload.area_m2 })}`),
      ]);
      renderResult(payload, r);
      $("result").hidden = false;
      renderTrend(trend);
      renderComps(comps.items);
      const title = $("result-title");
      title.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
      title.focus({ preventScroll: true });
    } catch (e) {
      showErrors(e.fields, e.message);
    } finally {
      btn.disabled = false; btn.textContent = "احسب السعر";
    }
  }

  $("form").addEventListener("submit", onSubmit);
  $("form").addEventListener("reset", () => { clearErrors(); $("result").hidden = true; setTimeout(() => { fillDistricts(); syncMap(); }, 0); });
  $("again").addEventListener("click", () => { window.scrollTo({ top: 0 }); $("district").focus(); });
  $("print").addEventListener("click", () => window.print());
  init();
})();
