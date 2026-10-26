// Appels au serveur de pilote. Une erreur rend la phrase en français du serveur, telle quelle.
export class Refus extends Error {
  constructor(message, statut = 0, corps = null) {
    super(message);
    this.statut = statut;
    this.corps = corps; // la réponse du serveur, pour un 409 (avertissement à lire avant d'allumer)
  }
}

async function appel(methode, chemin, corps) {
  let rep;
  try {
    rep = await fetch(`/api/suite${chemin}`, {
      method: methode,
      headers: corps === undefined ? {} : { "Content-Type": "application/json" },
      body: corps === undefined ? undefined : JSON.stringify(corps),
    });
  } catch {
    throw new Refus("Le serveur de pilote ne répond pas.");
  }
  let json = null;
  try {
    json = await rep.json();
  } catch {
    /* corps vide */
  }
  if (!rep.ok) {
    const d = json && json.detail;
    throw new Refus(typeof d === "string" ? d : "La demande a été refusée.", rep.status, d);
  }
  return json;
}

export const api = {
  etat: () => appel("GET", "/etat"),
  tri: () => appel("GET", "/tri"),
  post: (chemin, corps = {}) => appel("POST", chemin, corps),
  put: (chemin, corps = {}) => appel("PUT", chemin, corps),
  supprimer: (chemin) => appel("DELETE", chemin),
  aide: (fonction, corps = {}) => appel("POST", `/aide/${fonction}`, corps),
  aideGet: (chemin) => appel("GET", `/aide/${chemin}`),
};
