// Outils de dessin minimaux : un élément DOM par appel, jamais de HTML construit par chaîne (un nom de source ne peut donc pas
// injecter de balise). Les pictogrammes viennent de la seule table `pictogrammes.js`.
import { PICTOGRAMMES } from "./pictogrammes.js";

const NS = "http://www.w3.org/2000/svg";

export function h(tag, attrs, ...enfants) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === false || v === null || v === undefined) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "dataset") Object.assign(el.dataset, v);
    else if (k === "style") Object.assign(el.style, v);
    else if (k in el && k !== "list" && k !== "form") el[k] = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  ajouter(el, enfants);
  return el;
}

export function ajouter(el, enfants) {
  for (const e of enfants.flat(Infinity)) {
    if (e === null || e === undefined || e === false) continue;
    el.append(e.nodeType ? e : document.createTextNode(String(e)));
  }
  return el;
}

/** Un pictogramme de la table unique. `taille` : 20 (lignes, boutons, panneaux) ou 28 (tuiles) ; 12 est réservé au × de la tuile. */
export function icone(nom, taille = 20, extra = {}) {
  const d = PICTOGRAMMES[nom];
  if (!d) throw new Error(`pictogramme inconnu : ${nom}`);
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("width", String(taille));
  svg.setAttribute("height", String(taille));
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", String(extra.trait || 1.6));
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("stroke-linejoin", "round");
  svg.setAttribute("aria-hidden", "true");
  svg.classList.add("picto");
  const p = document.createElementNS(NS, "path");
  p.setAttribute("d", d);
  svg.append(p);
  return svg;
}

export function svg(tag, attrs) {
  const el = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs || {})) el.setAttribute(k, String(v));
  return el;
}

export function vider(el) {
  while (el.firstChild) el.removeChild(el.firstChild);
  return el;
}
