/* Page Ajout : trois façons de brancher une prise de noms (catalogue de l'État, adresse collée, formulaire). Un test est
   obligatoire avant d'enregistrer ; la prise est enregistrée désactivée. */
"use strict";
(function(){
  var CIBLES=[["nom","Nom"],["ville","Ville"],["genre","Genre de chose"],["id","Identifiant officiel"]];
  var mode=0, echantillon=[], champs={}, testeur=null, parametresUrl=[];
  function el(id){return document.getElementById(id)}
  function erreur(t){var e=el("aj-erreur");e.style.display=t?"block":"none";e.textContent=t||""}
  function empreinte(){return JSON.stringify(spec())}

  /* ---- spécification courante ---- */
  function spec(){
    var manuel=mode===2, url=(manuel?el("m-url"):el("aj-url")).value.trim();
    return {
      nom:el("aj-nom").value.trim(), url:url, format:manuel?el("m-format").value:(spec.format||"json"),
      items:manuel?el("m-items").value.trim():(spec.items||""), parametre_requete:manuel?el("m-param").value.trim():(el("aj-param").value||""),
      delimiteur:manuel?el("m-sep").value:(spec.delimiteur||";"), champs:copie(champs)
    };
  }
  spec.format="json";spec.items="";spec.delimiteur=";";
  function copie(o){var r={};Object.keys(o).forEach(function(k){if(o[k])r[k]=o[k]});return r}

  /* ---- modes ---- */
  function afficherMode(){
    document.querySelectorAll(".mode").forEach(function(b){b.classList.toggle("on",+b.dataset.m===mode)});
    el("ajout-catalogue").style.display=mode===0?"block":"none";
    el("gauche-adresse").style.display=mode===2?"none":"block";
    el("gauche-manuel").style.display=mode===2?"block":"none";
    el("raw").style.display=mode===2||!echantillon.length?"none":"block";
    el("raw-aide").style.display=mode===2?"none":"block";
    el("gauche-titre").textContent=mode===2?"Formulaire":"Réponse de la source";
    rendreMapping();
  }
  document.querySelectorAll(".mode").forEach(function(b){b.onclick=function(){mode=+b.dataset.m;afficherMode()}});

  /* ---- réponse brute et champs à désigner ---- */
  function rendreBrut(){
    var r=el("raw");
    if(!echantillon.length){r.style.display="none";return}
    r.style.display=mode===2?"none":"block";
    r.innerHTML="{\n"+echantillon.map(function(e){
      var used=CIBLES.some(function(c){return champs[c[0]]===e.champ});
      return '  <span class="pick'+(used?" used":"")+'" data-f="'+esc(e.champ)+'">"'+esc(e.champ)+'"</span>: <b>"'+esc(e.valeur)+'"</b>,'}).join("\n")+"\n}";
    r.querySelectorAll(".pick").forEach(function(p){p.onclick=function(){choisirChamp(p.dataset.f)}});
  }
  function choisirChamp(f){
    var deja=CIBLES.find(function(c){return champs[c[0]]===f});
    if(deja){delete champs[deja[0]]}
    else{var libre=CIBLES.find(function(c){return !champs[c[0]]});if(libre)champs[libre[0]]=f}
    testeur=null;rendreBrut();rendreMapping();
  }
  function rendreMapping(){
    var manuel=mode===2;
    el("mapping").innerHTML=CIBLES.map(function(c){
      var v=champs[c[0]]||"";
      return '<div class="maprow"><span class="lbl">'+c[1]+"</span>"+(manuel
        ?'<input class="inp" data-c="'+c[0]+'" value="'+esc(v)+'" placeholder="nom du champ">'
        :'<span class="val'+(v?"":" vide")+'">'+(v?esc(v):"— clique un champ —")+"</span>")+"</div>"}).join("");
    el("mapping").querySelectorAll("input").forEach(function(i){i.oninput=function(){champs[i.dataset.c]=i.value.trim();testeur=null;majBoutons()}});
    majBoutons();
  }
  function majBoutons(){
    var pret=!!champs.nom;
    el("btn-test").disabled=!pret;
    el("btn-save").disabled=!(testeur&&testeur===empreinte());
    el("essai").style.display="block";
    if(!pret&&!testeur)el("essai").textContent="— rien tant qu'un nom n'est pas désigné —";
  }

  /* ---- appeler une fois ---- */
  el("aj-appeler").onclick=function(){
    var url=el("aj-url").value.trim();
    if(!url){erreur("Collez d'abord une adresse.");return}
    el("aj-appeler").disabled=true;erreur("");el("aj-ok").textContent="";
    envoyer("/api/ajout/appeler","POST",{url:url}).then(function(r){
      echantillon=r.echantillon;spec.format=r.format;spec.items=r.items;spec.delimiteur=r.delimiteur||";";champs={};testeur=null;parametresUrl=r.parametres_url;
      el("raw-aide").textContent="Clique un champ pour dire ce qu'il représente. "+r.nb_items+" résultats dans cette réponse.";
      var sel=el("aj-param");
      sel.innerHTML='<option value="">aucun</option>'+r.parametres_url.map(function(p){return '<option value="'+esc(p.nom)+'"'+(p.nom===r.parametre_requete?" selected":"")+">"+esc(p.nom)+" = "+esc(p.valeur)+"</option>"}).join("");
      el("aj-params").style.display=r.parametres_url.length&&r.format==="json"?"block":"none";
      if(r.mot_essai&&!el("aj-mot").value)el("aj-mot").value=r.mot_essai;
      rendreBrut();rendreMapping();
    }).catch(function(e){echantillon=[];rendreBrut();erreur(e.message)}).then(function(){el("aj-appeler").disabled=false});
  };

  /* ---- tester, enregistrer ---- */
  el("btn-test").onclick=function(){
    var s=spec(), mot=el("aj-mot").value.trim();
    if(!s.nom){erreur("Donnez d'abord un nom à la prise.");return}
    erreur("");el("btn-test").disabled=true;el("essai").textContent="Essai en cours…";
    envoyer("/api/ajout/tester","POST",{spec:s,mot:mot}).then(function(r){
      if(!r.ok){testeur=null;el("essai").textContent=r.message;return}
      testeur=JSON.stringify(s);
      el("essai").innerHTML=r.noms.map(function(n){return esc(n.nom)+(n.ville?" · "+esc(n.ville):"")+(n.genre?" · "+esc(n.genre):"")+(n.id?" · "+esc(n.id):"")}).join("<br>")
        +'<div style="color:var(--faint);font-weight:400;margin-top:4px">'+r.total+" nom"+(r.total>1?"s":"")+" rendu"+(r.total>1?"s":"")+" pour « "+esc(r.essai)+" » ("+r.appels+" appel"+(r.appels>1?"s":"")+" réel"+(r.appels>1?"s":"")+")</div>";
    }).catch(function(e){testeur=null;el("essai").textContent="";erreur(e.message)}).then(function(){el("btn-test").disabled=!champs.nom;majBoutons()});
  };
  ["aj-nom","aj-url","aj-mot","m-url","m-format","m-items","m-param","m-sep"].forEach(function(id){var e=el(id);if(e)e.addEventListener("input",function(){if(testeur&&testeur!==empreinte()){testeur=null}majBoutons()})});
  el("aj-param").onchange=function(){testeur=null;majBoutons()};
  el("btn-save").onclick=function(){
    el("btn-save").disabled=true;
    envoyer("/api/ajout/enregistrer","POST",{spec:spec()}).then(function(r){
      el("aj-ok").textContent="La prise « "+spec().nom+" » est enregistrée (fichier "+r.fichier+"), désactivée. Tu l'actives dans Réglages.";
      el("aller-reglages").style.display="inline-block";testeur=null;
    }).catch(function(e){erreur(e.message);majBoutons()});
  };
  el("aller-reglages").onclick=function(){var t=document.querySelector('.tab[data-p="reglages"]');if(t)t.click()};

  /* ---- catalogue de l'État ---- */
  function msgCat(t){el("cat-msg").textContent=t||""}
  el("cat-go").onclick=function(){
    var q=el("cat-q").value.trim();if(!q){msgCat("Tapez quelques mots à chercher.");return}
    msgCat("Recherche dans le catalogue…");el("cat-res").innerHTML="";el("cat-go").disabled=true;
    api("/api/ajout/catalogue?q="+encodeURIComponent(q)).then(function(r){
      msgCat(r.apis.length+r.jeux.length?"":"Rien trouvé : essayez d'autres mots.");
      var h="";
      if(r.apis.length)h+='<h3 style="margin:8px 0">API publiques</h3>'+r.apis.map(function(x){return ligneCat("api",x,x.base)}).join("");
      if(r.jeux.length)h+='<h3 style="margin:10px 0 8px">Jeux de données</h3>'+r.jeux.map(function(x){return ligneCat("jeu",x,x.nb_ressources+" fichier(s)")}).join("");
      el("cat-res").innerHTML=h;
      el("cat-res").querySelectorAll("[data-id]").forEach(function(b){b.onclick=function(){ouvrirCat(b.dataset.genre,b.dataset.id,b.dataset.titre)}});
    }).catch(function(e){msgCat(e.message)}).then(function(){el("cat-go").disabled=false});
  };
  el("cat-q").onkeydown=function(e){if(e.key==="Enter")el("cat-go").onclick()};
  function ligneCat(genre,x,detail){
    return '<button class="srow" style="width:100%;text-align:left;background:none;border:none;border-bottom:1px solid var(--line)" data-genre="'+genre+'" data-id="'+esc(x.id)+'" data-titre="'+esc(x.titre)+'">'
      +'<span class="sgrow"><span class="sname">'+esc(x.titre)+'</span><span class="smeta">'+esc(x.organisation)+(detail?" — "+esc(detail):"")+"</span></span></button>";
  }
  function ouvrirCat(genre,id,titre){
    msgCat("Lecture de « "+titre+" »…");
    if(genre==="api"){
      api("/api/ajout/catalogue/api/"+encodeURIComponent(id)).then(function(a){
        var pts=a.points.filter(function(p){return p.parametre_requete});
        if(!pts.length){msgCat("Cette API n'a pas de recherche par mots simple ; essayez « À la main ».");return}
        msgCat("");
        el("cat-res").innerHTML='<h3 style="margin:8px 0">'+esc(titre)+" — quelle recherche ?</h3>"+pts.map(function(p,i){
          return '<button class="srow" style="width:100%;text-align:left;background:none;border:none;border-bottom:1px solid var(--line)" data-i="'+i+'"><span class="sgrow"><span class="sname">'+esc(p.chemin)+'</span><span class="smeta">'+esc(p.resume||"recherche par mots")+"</span></span></button>"}).join("");
        el("cat-res").querySelectorAll("[data-i]").forEach(function(b){b.onclick=function(){
          var p=pts[+b.dataset.i], mot=el("aj-mot").value.trim()||el("cat-q").value.trim().split(/\s+/)[0]||"";
          el("aj-nom").value=titre;remplirAdresse(a.base+p.chemin+"?"+p.parametre_requete+"="+encodeURIComponent(mot),mot)}});
      }).catch(function(e){msgCat(e.message)});
    }else{
      api("/api/ajout/catalogue/jeu/"+encodeURIComponent(id)).then(function(rs){
        if(!rs.length){msgCat("Ce jeu n'a pas de fichier CSV ou JSON lisible.");return}
        msgCat("");
        el("cat-res").innerHTML='<h3 style="margin:8px 0">'+esc(titre)+" — quel fichier ?</h3>"+rs.map(function(r,i){
          return '<button class="srow" style="width:100%;text-align:left;background:none;border:none;border-bottom:1px solid var(--line)" data-i="'+i+'"><span class="sgrow"><span class="sname">'+esc(r.titre)+'</span><span class="smeta">'+esc(r.format||"?")+(r.taille?" · "+esc(r.taille):"")+"</span></span></button>"}).join("");
        el("cat-res").querySelectorAll("[data-i]").forEach(function(b){b.onclick=function(){el("aj-nom").value=titre;remplirAdresse(rs[+b.dataset.i].url,"")}});
      }).catch(function(e){msgCat(e.message)});
    }
  }
  function remplirAdresse(url,mot){
    mode=1;afficherMode();el("aj-url").value=url;if(mot)el("aj-mot").value=mot;el("aj-appeler").onclick();
  }

  afficherMode();
})();
