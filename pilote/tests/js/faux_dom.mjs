// Un très petit « navigateur » pour tester les pages sous Node : des éléments à la demande, un innerHTML qu'on peut fouiller avec
// des sélecteurs simples (tag[attr], tag[attr="valeur"], .classe) et des gestionnaires (onclick, onchange...) qu'on peut déclencher.
import vm from "node:vm";
import fs from "node:fs";

export function creer({ reponses = {}, stockage = {}, prompt = () => null } = {}) {
  const els = {};
  const appels = [];
  const classes = new Set();
  const racineDoc = { handlers: {} };
  function fabriquer(id, parent) {
    const o = {
      id, innerHTML: "", textContent: "", value: "", checked: false, disabled: false, style: {}, dataset: {}, parent,
      classList: { add: (c) => { classes.add(id + ":" + c); }, remove: (c) => { classes.delete(id + ":" + c); }, contains: (c) => classes.has(id + ":" + c), toggle() {} },
      querySelector: (sel) => o.querySelectorAll(sel)[0] ?? null,
      querySelectorAll: (sel) => {
        const k = sel + "||" + o.innerHTML;
        o._cache ??= {};
        return (o._cache[k] ??= cherche(o.innerHTML, sel));
      },
      addEventListener() {}, appendChild() {}, insertBefore() {}, remove() {},
    };
    return o;
  }
  function cherche(html, sel) {
    const out = [];
    const m = sel.match(/^(\w*)(?:\[([\w-]+)(?:=["']?([^"'\]]*)["']?)?\])?$/);
    if (!m) return out;
    const [, tag, attr, val] = m;
    const re = new RegExp(`<${tag || "\\w+"}\\b([^>]*)>`, "g");
    for (const t of html.matchAll(re)) {
      const attrs = Object.fromEntries([...t[1].matchAll(/([\w-]+)="([^"]*)"/g)].map((x) => [x[1], x[2].replace(/&quot;/g, '"').replace(/&amp;/g, "&").replace(/&#39;/g, "'")]));
      if (attr && !(attr in attrs) && !new RegExp(`\\b${attr}\\b`).test(t[1])) continue;
      if (val !== undefined && attrs[attr] !== val) continue;
      const e = fabriquer("n", null);
      e.dataset = Object.fromEntries(Object.entries(attrs).filter(([k]) => k.startsWith("data-")).map(([k, v]) => [k.slice(5).replace(/-(\w)/g, (_, c) => c.toUpperCase()), v]));
      e.value = attrs.value ?? "";
      e.checked = /\bchecked\b/.test(t[1]);
      e.name = attrs.name;
      e.attrs = attrs;
      out.push(e);
    }
    return out;
  }
  const el = (id) => (els[id] ??= fabriquer(id));
  const doc = {
    getElementById: el, querySelector: (s) => doc.querySelectorAll(s)[0] ?? null,
    querySelectorAll: (sel) => (cacheDoc[sel] ??= []),
    addEventListener(ev, f) { (racineDoc.handlers[ev] ??= []).push(f); }, dispatchEvent() {}, createElement: (t) => fabriquer(t),
    createTextNode: () => ({}), body: fabriquer("body"),
  };
  const cacheDoc = {};
  const ctx = {
    document: doc, console, location: { origin: "https://x", reload() { ctx.__recharge = true; } }, localStorage: { getItem: (k) => stockage[k] ?? null, setItem(k, v) { stockage[k] = v; } },
    window: { prompt }, CustomEvent: class { constructor(n, o) { this.type = n; this.detail = o?.detail; } },
    setTimeout, setInterval: () => 0, clearInterval() {}, requestAnimationFrame: (f) => f(),
    fetch: async (u, o) => {
      const methode = o?.method || "GET";
      appels.push({ cle: methode + " " + u, corps: o?.body ? JSON.parse(o.body) : null });
      const r = reponses[methode + " " + u] ?? reponses[u];
      const val = typeof r === "function" ? r(o?.body ? JSON.parse(o.body) : null) : r;
      return { ok: val !== undefined && !(val && val.__erreur), status: val?.__erreur ?? 200, json: async () => (val?.__erreur ? { detail: val.detail } : val) };
    },
  };
  vm.createContext(ctx);
  return {
    ctx, doc, el, appels, classes, handlers: racineDoc.handlers,
    charge(...fichiers) { for (const f of fichiers) vm.runInContext(fs.readFileSync(f, "utf8"), ctx); },
    declarer(sel, liste) { cacheDoc[sel] = liste; },
    attendre: (ms = 60) => new Promise((r) => setTimeout(r, ms)),
  };
}
