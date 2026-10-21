/* Presse (fiche 09) : la liste des flux RSS de l'utilisateur (Réglages) et l'encadré « Contexte » (page de lancement). */
"use strict";
(function(){
  function el(id){return document.getElementById(id)}
  var CONTEXTE_CHARGE={};

  /* ---- Mes flux RSS ---- */
  function messageFlux(t,mauvais){var m=el("flux-msg");if(m){m.textContent=t||"";m.style.color=mauvais?"var(--non-txt, inherit)":"inherit"}}
  function dessinerFlux(liste){
    var h='<div class="sname">Mes flux RSS <span class="smeta">'+liste.length+' flux</span></div>'
      +'<span class="smeta" style="display:block">Les journaux et sites que vous suivez. Chaque flux est lu une fois par recherche ; les noms cités dans les articles sont extraits (extraction bruyante).</span>';
    h+=liste.length?'<ul style="margin:6px 0;padding-left:18px">'+liste.map(function(f){
      return '<li style="font-size:12px">'+esc(f.nom)+' <span class="smeta">'+esc(f.url)+(f.pays?" · "+esc(f.pays):"")+'</span> <button class="btn" data-suppr="'+esc(f.id)+'" style="padding:1px 7px">Retirer</button></li>'}).join("")+"</ul>"
      :'<span class="smeta" style="display:block;margin:6px 0">Aucun flux pour l’instant : ajoutez l’adresse d’un flux, ou importez un fichier OPML exporté de votre lecteur de flux.</span>';
    h+='<div class="form" style="margin-top:6px"><div><label class="fl" for="flux-url">Adresse du flux</label><input class="inp" id="flux-url" placeholder="https://…"></div>'
      +'<div><label class="fl" for="flux-nom">Nom (facultatif)</label><input class="inp" id="flux-nom"></div></div>'
      +'<div style="display:flex;gap:7px;margin-top:7px;flex-wrap:wrap;align-items:center"><button class="btn" id="flux-ajout">Ajouter et lire le flux</button>'
      +'<label class="btn" for="flux-opml" style="cursor:pointer">Importer un fichier OPML…</label><input type="file" id="flux-opml" accept=".opml,.xml,text/xml" style="display:none">'
      +'<span id="flux-msg" class="smeta"></span></div>';
    el("flux-rss").innerHTML=h;
    var a=el("flux-ajout"),f=el("flux-opml");
    if(a)a.onclick=function(){
      var url=el("flux-url").value.trim();if(!url){messageFlux("Donnez l’adresse du flux.",true);return}
      messageFlux("Lecture du flux…");
      envoyer("/api/flux-rss","POST",{url:url,nom:el("flux-nom").value.trim()}).then(function(r){chargerFlux().then(function(){messageFlux("Flux ajouté : "+r.articles+" articles lus.")})})
        .catch(function(e){messageFlux("Ce flux est refusé : "+e.message,true)});
    };
    if(f)f.onchange=function(){
      var fichier=f.files&&f.files[0];if(!fichier)return;
      messageFlux("Import en cours…");
      fichier.text().then(function(t){return api("/api/flux-rss/opml",{method:"POST",headers:{"content-type":"text/x-opml"},body:t})}).then(function(r){
        chargerFlux().then(function(){messageFlux(r.ajoutes+" flux ajoutés"+(r.doublons?", "+r.doublons+" déjà présents":"")+(r.ignores&&r.ignores.length?", "+r.ignores.length+" ignorés (adresse invalide)":"")+".")})})
        .catch(function(e){messageFlux("Cet import est refusé : "+e.message,true)});
    };
    el("flux-rss").querySelectorAll("[data-suppr]").forEach(function(b){
      b.onclick=function(){api("/api/flux-rss/"+encodeURIComponent(b.dataset.suppr),{method:"DELETE"}).then(chargerFlux).catch(function(e){messageFlux(e.message,true)})};
    });
  }
  function chargerFlux(){
    return api("/api/flux-rss").then(function(r){dessinerFlux(r.flux)}).catch(function(e){el("flux-rss").innerHTML='<span class="smeta">'+esc("La liste des flux est illisible : "+e.message)+"</span>"});
  }

  /* ---- Contexte : titres déjà collectés (aucune nouvelle collecte) ---- */
  function dessinerContexte(c){
    if(!c.articles.length){el("contexte").innerHTML="";return}
    el("contexte").innerHTML='<h3 style="margin:0 0 4px">Contexte</h3><span class="smeta" style="display:block">'+esc(c.note)+" "+c.nombre+" article"+(c.nombre>1?"s":"")+".</span>"
      +'<ul style="margin:6px 0;padding-left:18px">'+c.articles.slice(0,8).map(function(a){
        var t=a.url&&/^https?:\/\//.test(a.url)?'<a href="'+esc(a.url)+'" target="_blank" rel="noopener noreferrer">'+esc(a.titre)+"</a>":esc(a.titre);
        return '<li style="font-size:12px">'+t+' <span class="smeta">'+esc(a.source)+(a.date?" · "+esc(a.date):"")+"</span></li>"}).join("")+"</ul>";
  }
  window.chargerContexte=function(rid,etat){
    var cle=rid+"/"+etat;if(CONTEXTE_CHARGE[rid]===cle)return;CONTEXTE_CHARGE[rid]=cle;
    api("/api/recherches/"+encodeURIComponent(rid)+"/contexte").then(dessinerContexte).catch(function(){});
  };

  if(el("flux-rss"))chargerFlux();
})();
