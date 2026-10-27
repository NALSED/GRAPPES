/* Page Ajout, nouvelle source (fiche 11) : API avec clé, serveur MCP, flux RSS/OPML, fichier local, base SQLite, programme local,
   et « autre » (OAuth, curseur, GraphQL : enregistrée quand même, elle demande un adaptateur).
   La source est enregistrée ÉTEINTE, puis testée sans rien appeler. La clé collée est rangée par le programme, jamais relue. */
"use strict";
(function(){
  function el(id){return document.getElementById(id)}
  var PANNEAUX={api:"t-api",mcp:"t-mcp",fichier:"t-fichier",base:"t-base",base_exterieure:"t-baseext",programme:"t-prog",adaptateur:"t-autre"};
  function afficher(){
    var t=el("t-type").value;
    el("t-rss").style.display=t==="rss"?"block":"none";
    el("t-generique").style.display=t==="rss"?"none":"block";
    Object.keys(PANNEAUX).forEach(function(k){el(PANNEAUX[k]).style.display=k===t?"grid":"none"});
    el("t-champs").style.display=(t==="api"||t==="mcp"||t==="fichier")?"grid":"none";
    el("t-exemple").style.display=(t==="api"||t==="mcp")?"block":"none";
    el("t-cle-zone").style.display=(t==="fichier"||t==="base"||t==="base_exterieure"||t==="programme")?"none":"block";
  }
  function genres(){
    api("/api/reglages").then(function(d){el("t-genre").innerHTML=d.genres.map(function(g){return '<option value="'+esc(g)+'">'+esc(g)+"</option>"}).join("")}).catch(function(){});
  }
  function liste(t){return t.split(",").map(function(x){return x.trim()}).filter(Boolean)}
  function corps(){
    var t=el("t-type").value,champs={nom:el("t-cnom").value.trim()};
    if(el("t-cville").value.trim())champs.ville=el("t-cville").value.trim();
    if(el("t-cnum").value.trim())champs.numero=el("t-cnum").value.trim();
    var commun={nom:el("t-nom").value.trim(),trouve:el("t-trouve").value.trim(),pays:liste(el("t-pays").value||"monde"),genres:[el("t-genre").value],genre:el("t-genre").value,
      main:el("t-main").value,origine:el("t-main").value==="premiere"?"registre":"web",confiance:parseFloat(el("t-confiance").value),
      roles:el("t-verifier").checked?["chercher","verifier"]:["chercher"],
      /* la clé ne part que pour les types qui en ont une : collée puis type changé pour « fichier », elle ne doit pas être rangée quand même */
      cle_valeur:(t==="api"||t==="mcp"||t==="adaptateur")?el("t-cle-val").value.trim():"",
      cout:{unite:el("t-unite").value,vers_dollar:parseFloat(el("t-dollar").value)||0,par_appel:parseFloat(el("t-par").value)||1}};
    var ex=el("t-ex").value.trim(),exemple;
    if(ex){try{exemple=JSON.parse(ex)}catch(e){exemple=ex}}
    if(t==="api"){
      var spec=Object.assign(commun,{url:el("t-url").value.trim(),parametre_requete:el("t-param").value.trim(),liste:el("t-liste").value.trim(),champs:champs,exemple:exemple});
      if(el("t-auth").value)spec.auth={type:el("t-auth").value,nom:el("t-authnom").value.trim()};
      return {type:"api",spec:spec};
    }
    if(t==="mcp"){
      var args;try{args=JSON.parse(el("t-args").value)}catch(e){throw new Error("Les arguments doivent être du JSON valide.")}
      var avert=el("t-avert").value.trim();
      return {type:"mcp",spec:Object.assign(commun,{mcp:el("t-mcpurl").value.trim(),outil:el("t-outil").value.trim(),arguments:args,champs:champs,exemple:exemple,
        prestataire:!!avert,avertissement:avert,liste:el("t-liste").value.trim()})};
    }
    if(t==="adaptateur")return {type:"adaptateur",spec:Object.assign(commun,{url:el("t-aurl").value.trim(),protocole:el("t-proto").value})};
    if(t==="fichier")return {type:"fichier",spec:Object.assign(commun,{chemin:el("t-chemin").value.trim(),format:el("t-format").value,delimiteur:el("t-sep").value,champs:champs,liste:el("t-liste").value.trim()})};
    if(t==="base")return {type:"base",spec:Object.assign(commun,{base:el("t-basef").value.trim(),requete:el("t-sql").value,mot_essai:el("t-essai").value.trim()})};
    if(t==="base_exterieure")return {type:"base_exterieure",spec:Object.assign(commun,{systeme:el("t-bx-sys").value,hote:el("t-bx-hote").value.trim(),port:parseInt(el("t-bx-port").value,10)||"",base_nom:el("t-bx-base").value.trim(),
      utilisateur:el("t-bx-user").value.trim(),mot_de_passe:el("t-bx-mdp").value,requete:el("t-bx-sql").value,mot_essai:el("t-bx-essai").value.trim()})};
    return {type:"programme",spec:Object.assign(commun,{commande:el("t-cmd").value.split("\n").map(function(x){return x.trim()}).filter(Boolean),delai_s:parseFloat(el("t-delai").value)||10,exemple:exemple})};
  }
  el("t-type").onchange=afficher;
  el("t-go").onclick=function(){
    var c;try{c=corps()}catch(e){el("t-msg").textContent=e.message;return}
    el("t-msg").textContent="Enregistrement et test en cours…";
    var chemin=c.type==="programme"?"/api/programmes-locaux":"/api/ajout/source",corpsEnvoye=c.type==="programme"?Object.assign({nom:c.spec.nom},c.spec):c;
    envoyer(chemin,"POST",corpsEnvoye).then(function(r){
      el("t-cle-val").value="";el("t-bx-mdp").value="";  /* la clé et le mot de passe sont rangés côté serveur : on ne les garde pas dans la page */
      if(c.type==="adaptateur"){el("t-msg").textContent="Enregistrée, éteinte : cette source demande un adaptateur (un petit programme à écrire). Elle apparaît dans Réglages avec ce message et ne s’allume pas avant.";return}
      el("t-msg").textContent="Enregistrée, éteinte. "+(r.test.statut==="ok"?"Test local réussi : ":"Test local échoué : ")+(r.test.statut==="ok"?(r.test.noms_exemple||[]).map(function(n){return n.nom}).join(", "):r.test.raison)
        +(r.test.statut==="ok"?" — à activer dans Réglages.":" — elle reste éteinte tant que le test ne passe pas.");
    }).catch(function(e){el("t-msg").textContent="Refusé : "+e.message});
  };
  /* « Ajouter une nouvelle source » depuis Réglages : on arrive ici, type à choisir, rôle « vérifier » coché si on venait de Vérification */
  document.addEventListener("ajout-nouvelle",function(e){
    el("t-verifier").checked=!!(e.detail&&e.detail.verifier);
    var box=el("ajout-types");if(box&&box.scrollIntoView)box.scrollIntoView();
  });
  afficher();genres();
})();
