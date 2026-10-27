(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const nf = new Intl.NumberFormat("en-US");
  const fmt = (n) => nf.format(Math.round(n));
  const FINISHING = { none: "بدون تشطيب", semi: "نص تشطيب", full: "تشطيب كامل", luxury: "سوبر لوكس" };
  const VERDICT = {
    overpriced: { text: "▼ مبالغ فيه", cls: "overpriced" },
    fair: { text: "● سعر عادل", cls: "fair" },
    opportunity: { text: "▲ فرصة", cls: "opportunity" },
  };
  let page = 1, pages = 1;

  const el = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  };
  const when = (s) => new Date(s.replace(" ", "T") + "Z")
    .toLocaleString("ar-EG-u-nu-latn", { day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit" });

  async function call(url, options) {
    const res = await fetch(url, options);
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(body.error || "حصل خطأ غير متوقع. حاول مرة تانية.");
    return body;
  }

  function cell(label, ...children) {
    const td = el("td");
    td.dataset.label = label;
    td.append(...children);
    return td;
  }

  function rerunUrl(i) {
    const q = new URLSearchParams({
      city: i.city, district: i.district, area_m2: i.area_m2, age_years: i.age_years, rooms: i.rooms,
      bathrooms: i.bathrooms, floor: i.floor, finishing: i.finishing, asking_price: "", run: "1",
    });
    return q;
  }

  function row(it) {
    const i = it.input, v = VERDICT[it.verdict];
    const tr = el("tr");
    const prop = el("div"); prop.append(el("div", "t", `${i.city} · ${i.district}`),
      el("div", "s", `${fmt(i.area_m2)} م² · عمر ${i.age_years} سنة · الدور ${i.floor} · ${FINISHING[i.finishing] || i.finishing}`));
    const diff = el("span", "num", (it.diff_pct > 0 ? "+" : "") + it.diff_pct.toFixed(1) + "%"); diff.dir = "ltr";
    const badge = el("span", "badge " + v.cls, v.text);

    const q = rerunUrl(i); q.set("asking_price", String(it.asking_price));
    const again = el("a", "btn sm", "إعادة التقدير"); again.href = "/?" + q.toString();
    const del = el("button", "btn sm ghost", "حذف"); del.type = "button";
    del.setAttribute("aria-label", `حذف تقدير ${i.district}`);
    del.addEventListener("click", async () => {
      del.disabled = true;
      try { await call(`/api/history/${it.id}`, { method: "DELETE" }); await load(); }
      catch (e) { showError(e.message); del.disabled = false; }
    });
    const actions = el("div", "row-actions"); actions.append(again, del);

    tr.append(cell("التاريخ", el("span", "when", when(it.created_at))), cell("العقار", prop),
      cell("السعر المتوقع", el("span", "num", fmt(it.predicted))), cell("السعر المعروض", el("span", "num", fmt(it.asking_price))),
      cell("الفرق", diff), cell("الحكم", badge), cell("", actions));
    return tr;
  }

  function showError(msg) { const e = $("hist-error"); e.textContent = msg; e.hidden = !msg; }

  async function load() {
    showError("");
    const flt = $("filter").value;
    const q = new URLSearchParams({ page: String(page) });
    if (flt) q.set("verdict", flt);
    let d;
    try { d = await call("/api/history?" + q); }
    catch (e) { showError(e.message); return; }
    page = d.page; pages = d.pages;
    $("s-total").textContent = d.summary.total;
    ["overpriced", "fair", "opportunity"].forEach((k) => { $("s-" + k).textContent = d.summary[k]; });
    $("rows").replaceChildren(...d.items.map(row));
    const empty = d.items.length === 0;
    $("hist").hidden = empty; $("empty").hidden = !empty;
    $("empty-title").textContent = flt ? "مفيش تقديرات بالحكم ده" : "لسه معملتش أي تقدير";
    $("clear").disabled = d.summary.total === 0;
    $("pager").hidden = pages <= 1;
    $("page-info").textContent = `صفحة ${page} من ${pages}`;
    $("prev").disabled = page <= 1; $("next").disabled = page >= pages;
  }

  $("filter").addEventListener("change", () => { page = 1; load(); });
  $("prev").addEventListener("click", () => { page -= 1; load(); window.scrollTo({ top: 0 }); });
  $("next").addEventListener("click", () => { page += 1; load(); window.scrollTo({ top: 0 }); });
  $("clear").addEventListener("click", async () => {
    if (!window.confirm("هتمسح كل تقديراتك السابقة؟ الإجراء ده مش بيترجع.")) return;
    try { await call("/api/history", { method: "DELETE" }); page = 1; await load(); }
    catch (e) { showError(e.message); }
  });
  load();
})();
