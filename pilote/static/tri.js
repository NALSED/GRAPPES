/* Page Tri : des PAQUETS d'abord (jamais des milliers de lignes), cinq vues sur les mêmes noms, décisions annulables.
   Seules les lignes visibles sont dessinées (liste virtuelle). La couleur d'un nom dit D'OÙ IL VIENT ; le vert et le rouge ne
   servent qu'aux décisions de l'utilisateur. */
"use strict";
(function(){
  var COULEUR={registre:"var(--o1)",presse:"var(--o2)",encyclo:"var(--o3)",web:"var(--o4)",texte:"var(--o5)"};
  var ORIGINE_PHRASE={registre:"dans un registre officiel",presse:"cité par la presse",encyclo:"dans une encyclopédie",web:"trouvé sur le web",texte:"lu dans un texte"};
  var DEC_PHRASE={garder:"gardés",rejeter:"rejetés",plus_tard:"mis de côté"};
  var MOT_ORIGINE={registre:"REGISTRE",presse:"PRESSE",encyclo:"ENCYCLO",web:"WEB",texte:"TEXTE"};  /* la couleur ne porte jamais seule l'information */
  var HAUTEUR=64, HAUTEUR_CARTE=56, HAUTEUR_LIGNE_TABLEAU=34;
  var filtres=[], texte="", nouveaux=false, tabulateur=null, fileDecisions=Promise.resolve(), delaiFiche=null, abandonFiche=null, enAttente={}, seqCharger=0, touchees={}, selTableau=null, jeuTableau=null;
  var T=null, rid=lire("g_tri_recherche"), clActif=lire("g_tri_classement")||"solides", vue="liste", sel=null;
  var ouverts={}, parPaquet={}, parId={}, handles=[], dernierMessage="", dernierAnnulable=false, tri_tableau={cle:"nom",sens:1};

  function lire(k){try{return localStorage.getItem(k)}catch(e){return null}}
  function ecrire(k,v){try{localStorage.setItem(k,v)}catch(e){}}
  function el(id){return document.getElementById(id)}
  function plur(n,s,p){return n+" "+(n>1?(p||s+"s"):s)}

  /* ------------------------------------------------ liste virtuelle ------------------------------------------------ */
  function vlist(host,n,h,rendre){
    var etat={n:n,h:h};
    function dessiner(){
      var haut=host.scrollTop||0, vue_h=host.clientHeight||330;
      var a=Math.max(0,Math.floor(haut/h)-4), b=Math.min(n,Math.ceil((haut+vue_h)/h)+4), html="";
      for(var i=a;i<b;i++)html+=rendre(i);
      host.innerHTML='<div style="height:'+(a*h)+'px"></div>'+html+'<div style="height:'+((n-b)*h)+'px"></div>';
      etat.rendues=b-a;
    }
    var attente=false;
    host.onscroll=function(){if(attente)return;attente=true;(typeof requestAnimationFrame==="function"?requestAnimationFrame:function(f){setTimeout(f,16)})(function(){attente=false;dessiner()})};
    etat.redessiner=dessiner;
    etat.montrer=function(i){var haut=host.scrollTop||0,vh=host.clientHeight||330;
      if(i*h<haut)host.scrollTop=i*h;else if((i+1)*h>haut+vh)host.scrollTop=(i+1)*h-vh;dessiner()};
    dessiner();handles.push(etat);return etat;
  }

  /* ------------------------------------------------ chargement ------------------------------------------------ */
  function indexer(){
    parPaquet={};parId={};
    T.lignes.forEach(function(l){(parPaquet[l.p]=parPaquet[l.p]||[]).push(l);parId[l.id]=l});
  }
  function requete(){
    return ["classement="+encodeURIComponent(clActif)].concat(filtres.map(function(f){return "filtre="+encodeURIComponent(f)}),
      texte?["q="+encodeURIComponent(texte)]:[],nouveaux?["nouveaux=true"]:[]).join("&");
  }
  function charger(garder){
    if(!rid)return Promise.resolve();
    var mon=++seqCharger;  /* une réponse plus ancienne que la dernière demande est ignorée */
    return api("/api/recherches/"+rid+"/tri?"+requete()).then(function(t){
      if(mon!==seqCharger)return;
      T=t;clActif=t.classement.id;ecrire("g_tri_classement",clActif);indexer();
      /* les décisions prises ici et pas encore confirmées par le serveur restent ce qu'on a décidé : un rechargement ne les efface jamais */
      Object.keys(enAttente).forEach(function(id){var l=parId[id];if(l){l.d=enAttente[id].d;l.mo=enAttente[id].mo}});
      recompter();
      if(!garder||!parId[sel])sel=premierADecider();
      tout();
    }).catch(function(e){el("tri-body").innerHTML='<div class="empty">'+esc(e.message)+"</div>"});
  }
  function listeRecherches(){
    return api("/api/recherches").then(function(rs){
      var avec=rs.filter(function(r){return r.noms>0});
      var sl=el("tri-recherche");
      sl.innerHTML=avec.length?avec.map(function(r){
        var d=r.cree_le?new Date(r.cree_le).toLocaleDateString("fr-FR",{day:"2-digit",month:"2-digit"}):"";
        return '<option value="'+esc(r.id)+'">'+esc((r.sujet&&r.sujet.quoi)||"(sans titre)")+" — "+d+" · "+r.noms+" noms</option>"}).join(""):'<option value="">Aucune recherche avec des noms</option>';
      if(!avec.some(function(r){return r.id===rid}))rid=avec.length?avec[0].id:null;
      if(rid)sl.value=rid;
      sl.onchange=function(){rid=sl.value;ecrire("g_tri_recherche",rid);sel=null;ouverts={};charger()};
      if(!rid){el("tri-body").innerHTML='<div class="empty">Aucun nom à trier pour l\'instant. Lancez une recherche dans Recherches.</div>';el("ov-n").textContent=0;el("ov-rest").textContent="";el("detail").innerHTML='<div class="empty">Sélectionne un nom.</div>'}
    });
  }

  /* ------------------------------------------------ vue d'ensemble, classements ------------------------------------------------ */
  function ensemble(){
    var avecPoints=T.recherche.verification;
    el("tri-titre").textContent="Tri — "+(T.recherche.quoi||"");
    el("tri-sans-verif").style.display=avecPoints?"none":"block";
    /* Une vérification coupée au milieu est dite : sinon les noms non examinés ressemblent à des noms vérifiés sans trouvaille. */
    var vfs=(T.recherche.verifications||[]), zone=el("tri-verifs");
    zone.innerHTML=vfs.map(function(v){
      var fin=v.complete?"":' — <b>incomplète</b>'+(v.raison?" ("+esc(v.raison)+")":"");
      return esc(v.nom||v.source)+" : "+v.examines+" nom"+(v.examines>1?"s":"")+" examiné"+(v.examines>1?"s":"")+" sur "+v.a_verifier+", "+v.trouves+" vérifié"+(v.trouves>1?"s":"")+fin}).join(" · ");
    zone.style.display=vfs.length?"block":"none";
    el("ov-n").textContent=T.total.toLocaleString("fr-FR");
    el("ov-rest").textContent="reste "+T.a_decider.toLocaleString("fr-FR")+" à décider";
    el("ovbar").innerHTML=T.origines.map(function(o){return '<div style="width:'+(T.total?o.n/T.total*100:0)+'%;background:'+COULEUR[o.id]+'"></div>'}).join("");
    el("ovkey").innerHTML=T.origines.map(function(o){return '<span><i style="background:'+COULEUR[o.id]+'"></i>'+esc(o.libelle)+" "+o.n+"</span>"}).join("");
    el("undo").disabled=!T.peut_annuler;
  }
  function classements(){
    el("cl-list").innerHTML=T.classements.map(function(c){
      return '<button class="cl'+(c.id===clActif?" on":"")+(c.livre?"":" perso")+'" data-id="'+esc(c.id)+'">'+esc(c.nom)+"</button>"}).join("");
    el("cl-list").querySelectorAll(".cl").forEach(function(b){b.onclick=function(){clActif=b.dataset.id;ouverts={};charger(true)}});
    el("cl-exp").href="/api/classements/"+encodeURIComponent(clActif)+"/fichier";
  }
  el("cl-add").onclick=function(){
    var f=el("cl-form");f.style.display=f.style.display==="none"?"block":"none";
    el("cl-fait").innerHTML=Object.keys(T.faits).map(function(k){return '<option value="'+esc(k)+'">'+esc(T.faits[k])+"</option>"}).join("");
    el("cl-ordre").innerHTML=Object.keys(T.ordres_paquets).map(function(k){return '<option value="'+esc(k)+'">'+esc(T.ordres_paquets[k])+"</option>"}).join("");
  };
  el("cl-non").onclick=function(){el("cl-form").style.display="none"};
  el("cl-ok").onclick=function(){
    envoyer("/api/classements","POST",{nom:el("cl-nom").value,grouper_par:[el("cl-fait").value],ordre_paquets:el("cl-ordre").value}).then(function(c){
      el("cl-erreur").style.display="none";el("cl-form").style.display="none";el("cl-nom").value="";clActif=c.id;ouverts={};charger(true);
    }).catch(function(e){var x=el("cl-erreur");x.style.display="block";x.textContent=e.message});
  };
  el("cl-dup").onclick=function(){
    envoyer("/api/classements/"+encodeURIComponent(clActif)+"/dupliquer","POST",{}).then(function(c){clActif=c.id;ouverts={};charger(true)}).catch(function(e){message(e.message)});
  };

  /* ------------------------------------------------ lignes ------------------------------------------------ */
  /* Trois niveaux de typographie, deux graisses, pas plus : 1 = le nom (16 px, demi-gras) ; 2 = ce qui aide à décider (13 px, gris moyen) ;
     3 = le détail (11 px, gris clair), visible seulement sur la ligne sélectionnée. */
  function plat(c){var d=c.normalize?c.normalize("NFD"):c;return (d.charAt(0)||c).toLowerCase()}
  /* Les mots cherchés sont surlignés dans les noms : même longueur après mise à plat (une lettre -> une lettre), donc mêmes positions. */
  function surligner(nom){
    var mots=((T&&T.recherche&&T.recherche.mots)||[]).filter(function(m){return m.length>=2});
    if(!mots.length)return esc(nom);
    var p="";for(var i=0;i<nom.length;i++)p+=plat(nom.charAt(i));
    var cache=new Array(nom.length).fill(false);
    mots.forEach(function(m){var k=0;while((k=p.indexOf(m,k))>=0){for(var j=k;j<k+m.length;j++)cache[j]=true;k+=m.length}});
    var out="",ouvert=false;
    for(var q=0;q<nom.length;q++){
      if(cache[q]&&!ouvert){out+="<mark>";ouvert=true}
      if(!cache[q]&&ouvert){out+="</mark>";ouvert=false}
      out+=esc(nom.charAt(q));
    }
    return out+(ouvert?"</mark>":"");
  }
  /* DEUX signaux séparés, jamais recombinés en une note : (1) d'où vient le nom — la couleur et le mot ; (2) combien d'endroits
     distincts l'ont donné — un nombre. Un nom vu sur trois sites web banals affiche « 3 endroits » et reste marqué WEB ; un nom
     d'un registre officiel affiche « 1 endroit » et reste marqué REGISTRE. Le second ne compense pas le premier. */
  function endroits(l){return T.recherche.verification?plur(l.e,"endroit"):""}
  var TITRE_ENDROITS="Nombre d’endroits distincts qui ont donné ce nom (de première main, ou indépendants entre eux). Ce n’est PAS une note : la qualité de la source est dite à part, par la couleur et le mot.";
  function ligne2(l){
    var p=[];
    p.push('<span class="mot">'+MOT_ORIGINE[l.o]+"</span>");
    if(T.recherche.verification)p.push('<span class="pts" title="'+esc(TITRE_ENDROITS)+'">'+endroits(l)+"</span>");
    if(l.v)p.push(esc(l.v));
    if(l.f)p.push(esc(l.f));
    if(l.m)p.push(esc(l.m));
    if(l.r)p.push("≈ "+esc(l.r));
    if(l.d==="rejeter"&&l.mo)p.push("rejeté : "+esc(libelleMotif(l.mo)));
    return p.join(" · ");
  }
  function libelleMotif(id){var m=(T.motifs||[]).find(function(x){return x.id===id});return m?m.libelle:id}
  function ligne3(l){
    var noms=(l.t||[]).map(function(t){return esc((T.sources_noms||{})[t]||t)});
    var d=T.date?new Date(T.date).toLocaleDateString("fr-FR"):"";
    return (noms.length?"Trouvé par "+noms.join(", "):"")+(l.u?" · "+esc(l.u):"")+(l.nu?" · n° "+esc(l.nu):"")+(d?" · recherche du "+d:"");
  }
  function marque(l){return l.d==="garder"?"✓":l.d==="rejeter"?"✕":l.d==="plus_tard"?"·":""}
  function ligne(l){
    return '<div class="row'+(l.d?" d-"+l.d:"")+(l.id===sel?" sel":"")+'" data-id="'+l.id+'" style="border-left-color:'+COULEUR[l.o]+';height:'+HAUTEUR+'px">'
      +'<div class="rcol"><div class="r1">'+surligner(l.nom)+'</div><div class="r2">'+ligne2(l)+'</div><div class="r3">'+(l.id===sel?ligne3(l):"")+"</div></div>"
      +'<span class="rd" aria-label="'+(l.d?DEC_PHRASE[l.d]:"")+'">'+marque(l)+"</span></div>";
  }
  function miniBarre(p){
    var tot=p.n||1;
    return '<span class="grp-mini">'+T.origines.map(function(o){var n=p.composition[o.id]||0;return n?'<div style="width:'+(n/tot*100)+'%;background:'+COULEUR[o.id]+'"></div>':""}).join("")+"</span>";
  }

  /* ------------------------------------------------ vue Liste ------------------------------------------------ */
  function vueListe(){
    el("tri-body").innerHTML=T.paquets.map(function(p,i){
      var ouv=!!ouverts[p.cle];
      return '<div class="grp"><div style="display:flex;align-items:center;gap:9px;padding:0 11px 0 0">'
        +'<button class="grp-h" data-k="'+esc(p.cle)+'"><span class="car">'+(ouv?"▾":"▸")+'</span><span class="gn">'+p.n.toLocaleString("fr-FR")+'</span><span class="gl">'+esc(p.phrase)+"</span>"+miniBarre(p)+"</button>"
        +(p.a_decider?'<button class="bulk k" data-b="garder" data-k="'+esc(p.cle)+'" title="Garder les '+p.a_decider+' noms pas encore décidés de ce paquet">tout garder</button>'
                      +'<button class="bulk r" data-b="rejeter" data-k="'+esc(p.cle)+'" title="Rejeter les '+p.a_decider+' noms pas encore décidés de ce paquet">tout rejeter</button>'
                    :'<span style="font:400 11px var(--mono);color:var(--faint);white-space:nowrap">traité</span>')
        +"</div>"+(ouv?'<div class="grp-body" id="corps-'+i+'" data-i="'+i+'"></div>':"")+"</div>";
    }).join("");
    handles=[];
    T.paquets.forEach(function(p,i){
      var h=el("corps-"+i);
      if(!h||!ouverts[p.cle])return;
      var items=parPaquet[p.cle]||[];
      var vl=vlist(h,items.length,HAUTEUR,function(k){return ligne(items[k])});
      vl.paquet=p.cle;vl.items=items;
      h.onclick=function(e){var r=e.target.closest&&e.target.closest(".row");if(r){choisir(+r.dataset.id)}};
    });
    el("tri-body").querySelectorAll(".grp-h").forEach(function(b){b.onclick=function(){ouverts[b.dataset.k]=!ouverts[b.dataset.k];vueListe()}});
    el("tri-body").querySelectorAll(".bulk").forEach(function(b){b.onclick=function(e){e.stopPropagation();groupe(b.dataset.k,b.dataset.b)}});
  }

  /* ------------------------------------------------ vue Colonnes ------------------------------------------------ */
  function vueColonnes(){
    var cols=[{k:null,t:"à décider"},{k:"garder",t:"gardés"},{k:"plus_tard",t:"de côté"},{k:"rejeter",t:"rejetés"}];
    el("tri-body").innerHTML='<div class="kan">'+cols.map(function(c,i){
      var n=T.lignes.filter(function(l){return (l.d||null)===c.k}).length;
      return '<div class="kcol"><h3>'+c.t+'<span class="num">'+n+'</span></h3><div class="kbody" id="kcol-'+i+'" style="max-height:440px;overflow-y:auto"></div></div>'}).join("")+"</div>";
    handles=[];
    cols.forEach(function(c,i){
      var items=T.lignes.filter(function(l){return (l.d||null)===c.k});
      var h=el("kcol-"+i);
      if(!items.length){h.innerHTML='<div class="empty">vide</div>';return}
      vlist(h,items.length,HAUTEUR_CARTE,function(k){var l=items[k];
        return '<div class="kcard" data-id="'+l.id+'" style="border-left-color:'+COULEUR[l.o]+';height:'+(HAUTEUR_CARTE-4)+'px"><div class="kn">'+surligner(l.nom)+'</div><div class="km">'+MOT_ORIGINE[l.o]+" · "+endroits(l)+" "+esc(l.v)+"</div></div>"});
      h.onclick=function(e){var r=e.target.closest&&e.target.closest(".kcard");if(r)choisir(+r.dataset.id)};
    });
  }

  /* ------------------------------------------------ vue Tableau (Tabulator) ------------------------------------------------ */
  /* Tabulator (MIT, sans dépendance, servi par pilote) fait le tableau : lignes virtuelles, tri par colonne, groupes repliables par paquet.
     Les décisions, le surlignage et le clavier restent ceux de la page. */
  function vueTableau(){
    el("tri-body").innerHTML='<div id="tbl"></div>';
    handles=[];
    if(tabulateur){try{tabulateur.destroy()}catch(e){}tabulateur=null;jeuTableau=null}
    if(typeof Tabulator==="undefined"){el("tbl").innerHTML='<div class="empty">Le composant de tableau n\'est pas chargé.</div>';return}
    var donnees=T.lignes.map(function(l){return {id:l.id,nom:l.nom,o:l.o,e:l.e,v:l.v,g:l.g,f:l.f,s:l.s,d:l.d||"",mo:l.mo,p:l.p}});
    var phrases={};T.paquets.forEach(function(p){phrases[p.cle]=p.phrase});
    tabulateur=new Tabulator("#tbl",{
      data:donnees,index:"id",height:"520px",layout:"fitColumns",rowHeight:HAUTEUR_LIGNE_TABLEAU,selectableRows:1,
      groupBy:"p",groupStartOpen:true,groupToggleElement:"header",groupHeader:function(valeur,n){return esc(phrases[valeur]||valeur)+' <span class="gcompte">'+n+"</span>"},
      initialSort:[{column:"nom",dir:"asc"}],
      columns:[
        {title:"Nom",field:"nom",minWidth:240,widthGrow:5,formatter:function(c){var l=c.getData();c.getElement().style.borderLeft="4px solid "+COULEUR[l.o];return '<span class="r1">'+surligner(l.nom)+"</span>"}},
        {title:"Origine",field:"o",width:96,formatter:function(c){return '<span class="mot">'+MOT_ORIGINE[c.getValue()]+"</span>"}},
        {title:"Endroits",field:"e",width:88,hozAlign:"right",headerTooltip:TITRE_ENDROITS,formatter:function(c){return T.recherche.verification?'<span class="pts">'+c.getValue()+"</span>":""}},
        {title:"Ville",field:"v",minWidth:80},{title:"Fonction",field:"f",minWidth:70},{title:"Genre",field:"g",minWidth:70},
        {title:"Décision",field:"d",width:150,formatter:function(c){var l=c.getData();return l.d==="garder"?"✓ gardé":l.d==="rejeter"?"✕ rejeté"+(l.mo?" · "+esc(libelleMotif(l.mo)):""):l.d==="plus_tard"?"· de côté":""}},
      ],
      rowFormatter:function(row){var d=row.getData();var e=row.getElement();e.classList.toggle("d-garder",d.d==="garder");e.classList.toggle("d-rejeter",d.d==="rejeter");e.classList.toggle("d-plus_tard",d.d==="plus_tard");e.classList.toggle("sel",d.id===sel)},
    });
    tabulateur.on("rowClick",function(e,row){choisir(row.getData().id)});
    tabulateur.on("tableBuilt",function(){selTableau=sel;scrollerTableau()});
    jeuTableau=T;
  }
  /* Une décision ne reconstruit pas le tableau (on perdrait le tri choisi et la position) : seules les lignes touchées sont mises à jour. */
  function majTableau(){
    var ids={};Object.keys(touchees).forEach(function(i){ids[i]=true});
    if(selTableau)ids[selTableau]=true;if(sel)ids[sel]=true;
    Object.keys(ids).forEach(function(i){
      var l=parId[i],r=tabulateur.getRow(+i);if(!l||!r)return;
      r.update({d:l.d||"",mo:l.mo});r.reformat();
    });
    touchees={};selTableau=sel;scrollerTableau();
  }

  /* ------------------------------------------------ vue Fiches ------------------------------------------------ */
  function vueFiches(){
    var ad=ordreNavigation().filter(function(l){return !l.d});
    if(!ad.length){el("tri-body").innerHTML='<div class="box"><div class="empty">Tout est trié.</div></div>';return}
    var c=ad[0];sel=c.id;
    el("tri-body").innerHTML='<div class="box" style="border-left:4px solid '+COULEUR[c.o]+'"><div style="font:600 17px var(--sans);margin-bottom:9px">'+esc(c.nom)+"</div>"
      +'<div class="dkv"><span class="k">D’où il vient</span><span class="v">'+esc(ORIGINE_PHRASE[c.o])+"</span></div>"
      +'<div class="dkv"><span class="k">Trouvé à</span><span class="v">'+plur(c.e,"endroit")+"</span></div>"
      +'<div class="dkv"><span class="k">Ville</span><span class="v">'+(esc(c.v)||"—")+"</span></div>"
      +'<div class="dkv"><span class="k">Site web</span><span class="v">'+(c.s?"oui":"non trouvé")+"</span></div>"
      +(c.r?'<div class="dnote">Nom très proche de « '+esc(c.r)+" ».</div>":"")
      +'<div class="dec"><button class="k" data-d="garder">✓ Garder <kbd>G</kbd></button><button class="l" data-d="plus_tard">Plus tard <kbd>P</kbd></button><button class="r" data-d="rejeter">✕ Rejeter <kbd>R</kbd></button></div>'
      +'<p class="hint">'+plur(ad.length,"restant")+"</p></div>";
    el("tri-body").querySelectorAll(".dec button").forEach(function(b){b.onclick=function(){decider(c.id,b.dataset.d)}});
  }

  /* ------------------------------------------------ vue Carte de liens (fiche 15, chap. 4) ------------------------------------------------ */
  /* Jamais tout d'un coup : les noms GARDÉS, ou le voisinage d'UN nom (60 points au plus, plafond posé par le serveur). Chaque point est aussi
     dans le texte du panneau (voisins, relations) : la carte ne porte jamais seule une information. */
  var carteMode="gardes", carteCy=null;
  var STYLE_LIEN={siege:["solid",2,false],maison_mere:["solid",4,true],trouve_via:["dashed",2,false],meme_adresse:["dotted",3,false],autre:["solid",1,false]};
  function couleurOrigine(o){
    var v=COULEUR[o];if(!v)return "#8a8f98";
    var m=/var\((--[a-z0-9]+)\)/.exec(v);
    return m?(getComputedStyle(document.documentElement).getPropertyValue(m[1]).trim()||"#8a8f98"):v;
  }
  function vueCarte(){
    var h=el("tri-body");
    if(!window.cytoscape){h.innerHTML='<div class="box"><div class="empty">La bibliothèque de la carte n\'est pas chargée.</div></div>';return}
    var centre=carteMode==="voisinage"?sel:null;
    h.innerHTML='<div class="box"><div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:8px">'
      +'<button class="btn'+(carteMode==="gardes"?" on":"")+'" id="carte-gardes">Mes noms gardés</button>'
      +'<button class="btn'+(carteMode==="voisinage"?" on":"")+'" id="carte-voisins"'+(sel?"":" disabled")+'>Voisinage du nom sélectionné</button>'
      +'<span class="smeta" id="carte-etat"></span></div>'
      +'<div id="carte-zone" style="height:380px;border:1px solid var(--line2);border-radius:6px"></div>'
      +'<div class="smeta" id="carte-legende" style="margin-top:6px;white-space:normal"></div>'
      +'<div id="carte-info" style="margin-top:8px"></div></div>';
    el("carte-gardes").onclick=function(){carteMode="gardes";vueCarte()};
    el("carte-voisins").onclick=function(){carteMode="voisinage";vueCarte()};
    if(carteMode==="voisinage"&&!sel){carteMode="gardes";return vueCarte()}
    api("/api/recherches/"+rid+"/carte"+(centre?"?centre="+centre:"")).then(function(c){
      if(vue!=="carte")return;
      var zone=el("carte-zone");
      el("carte-etat").textContent=c.message||(c.noeuds.length+" noms, "+c.aretes.length+" liens"+(c.tronque?" — carte limitée à "+c.plafond+" noms":""));
      zone.dataset.noeuds=c.noeuds.length;zone.dataset.aretes=c.aretes.length;
      el("carte-legende").innerHTML="Taille = nombre d’endroits qui l’ont trouvé. Couleur = origine (comme la liste). Liens : "
        +Object.keys(c.familles).map(function(k){var st=STYLE_LIEN[k]||STYLE_LIEN.autre;return esc(c.familles[k])+" ("+(k==="maison_mere"?"trait épais avec flèche":st[0]==="dashed"?"tirets":st[0]==="dotted"?"pointillés":"trait plein")+")"}).join(" ; ")+".";
      if(carteCy){carteCy.destroy();carteCy=null}
      if(!c.noeuds.length){zone.innerHTML='<div class="empty" style="padding:14px">'+esc(c.message)+"</div>";return}
      var elements=c.noeuds.map(function(n){return {data:{id:String(n.id),nom:n.nom,o:n.o,e:n.e,d:n.d||"",externe:n.externe?1:0,centre:n.centre?1:0}}})
        .concat(c.aretes.map(function(a,i){return {data:{id:"a"+i,source:String(a.de),target:String(a.vers),f:a.famille}}}));
      var styles=[
        {selector:"node",style:{label:"data(nom)","font-size":10,"text-wrap":"ellipsis","text-max-width":110,"text-valign":"bottom","text-margin-y":3,
          width:function(n){return 14+5*Math.min(n.data("e"),8)},height:function(n){return 14+5*Math.min(n.data("e"),8)},
          "background-color":function(n){return couleurOrigine(n.data("o"))},"border-width":1,"border-color":"#444"}},
        {selector:"node[externe = 1]",style:{"background-color":"#ddd","border-style":"dashed"}},
        {selector:"node[centre = 1]",style:{"border-width":4}},
        {selector:'node[d = "rejeter"]',style:{opacity:0.45}},
        {selector:"node:selected",style:{"border-width":4,"border-color":"#000"}},
        {selector:"edge",style:{width:1,"line-color":"#888","curve-style":"bezier"}}
      ];
      Object.keys(STYLE_LIEN).forEach(function(k){var st=STYLE_LIEN[k];
        styles.push({selector:'edge[f = "'+k+'"]',style:{"line-style":st[0],width:st[1],"target-arrow-shape":st[2]?"triangle":"none","target-arrow-color":"#888"}})});
      carteCy=window.cytoscape({container:zone,elements:elements,style:styles,layout:{name:"cose",animate:false,padding:24,nodeRepulsion:function(){return 9000}},minZoom:0.3,maxZoom:3});
      carteCy.on("tap","node",function(ev){noeudCarte(ev.target.data(),c)});
      if(centre){var n0=carteCy.getElementById(String(centre));if(n0&&n0.length){n0.select();noeudCarte(n0.data(),c)}}
    }).catch(function(e){var z=el("carte-etat");if(z&&vue==="carte")z.textContent=e.message});  /* la vue a pu changer entre-temps */
  }
  function noeudCarte(n,c){
    var id=n.id, interne=!n.externe, lignes=[];
    c.aretes.forEach(function(a){
      var autre=String(a.de)===id?String(a.vers):String(a.vers)===id?String(a.de):null;if(autre===null)return;
      var o=c.noeuds.find(function(x){return String(x.id)===autre});
      lignes.push("<li>"+esc(c.familles[a.famille]||a.famille)+" : "+esc(o?o.nom:autre)+"</li>")});
    var h='<div style="font:600 14px var(--sans)">'+esc(n.nom)+"</div>"
      +'<div class="smeta">'+(interne?"trouvé à "+plur(n.e,"endroit"):"hors des résultats (cité par une source)")+"</div>"
      +'<ul style="margin:6px 0 6px 18px;padding:0;font-size:12.5px">'+(lignes.join("")||"<li>aucun lien dessiné</li>")+"</ul>";
    if(interne){h+='<div class="dec"><button class="k" data-cd="garder">✓ Garder</button><button class="r" data-cd="rejeter">✕ Rejeter</button>'
      +'<button class="l" data-cd="liens">Voir ses liens</button><button class="l" data-cd="etendre">Étendre autour de ce nom…</button></div>'}
    el("carte-info").innerHTML=h;
    el("carte-info").querySelectorAll("button[data-cd]").forEach(function(b){b.onclick=function(){
      var k=b.dataset.cd, cid=parseInt(id,10);
      if(k==="garder"||k==="rejeter"){sel=cid;decider(cid,k)}
      else if(k==="liens"){sel=cid;carteMode="voisinage";vueCarte()}
      else{ /* relance une petite recherche ciblée : l'utilisateur choisit où dépenser le budget, rien ne part tout seul */
        var tab=document.querySelector('.tab[data-p="lancement"]');if(tab)tab.click();
        var q=document.getElementById("f-quoi");if(q){q.value=n.nom;q.dispatchEvent(new Event("input",{bubbles:true}));q.focus()}}}});
  }

  /* ------------------------------------------------ détail ------------------------------------------------ */
  /* Le panneau de détail a une partie FIXE (le nom sur une ligne, les boutons de décision, les motifs) et une partie variable dessous : les
     boutons sont toujours exactement au même endroit, quel que soit le nom, pour que le geste devienne automatique. */
  function detail(){
    var d=el("detail");
    if(!sel||!parId[sel]){d.innerHTML='<div class="empty">Sélectionne un nom.</div>';return}
    var l=parId[sel], mon=sel;
    d.innerHTML='<div class="dname" title="'+esc(l.nom)+'">'+surligner(l.nom)+"</div>"+decisionBoutons(l)+'<div id="dtail"></div>';
    brancherDecisions(d,mon);
    /* La fiche complète se charge quand on s'arrête sur un nom (pas à chaque touche) : en trions vite, on n'interroge pas le serveur 400 fois. */
    if(delaiFiche)clearTimeout(delaiFiche);
    if(abandonFiche&&abandonFiche.abort){try{abandonFiche.abort()}catch(e){}}
    delaiFiche=setTimeout(function(){chargerFiche(mon,d)},180);
  }
  function chargerFiche(mon,d){
    if(sel!==mon)return;
    abandonFiche=typeof AbortController==="function"?new AbortController():null;
    api("/api/recherches/"+rid+"/noms/"+mon,abandonFiche?{signal:abandonFiche.signal}:undefined).then(function(f){
      var zone=el("dtail");
      if(sel!==mon||!zone)return;
      zone.innerHTML=
        '<div class="dkv"><span class="k">D’où il vient</span><span class="v" style="color:'+COULEUR[f.origine]+'">'+esc(f.origine_phrase)+"</span></div>"
        +'<div class="dkv"><span class="k">Trouvé à</span><span class="v">'+plur(f.endroits,"endroit")+"</span></div>"
        +(f.genre_de_chose?'<div class="dkv"><span class="k">Genre</span><span class="v">'+esc(f.genre_de_chose)+"</span></div>":"")
        +(f.regle8_ecartee&&!f.regle8_leve?'<div class="dnote">Écartée du rapprochement par la règle n° 8 (compte au nom d’une personne physique). Si c’est en réalité une organisation, <button class="btn" id="personne-morale" style="padding:2px 8px;font-size:11.5px">marquez-la comme personne morale</button>.</div>':"")
        +(f.regle8_leve?'<div class="dnote">Règle n° 8 levée sur cette fiche par '+esc(f.regle8_leve.qui||"")+" le "+esc((f.regle8_leve.quand||"").replace("T"," ").slice(0,16))+' : elle entre dans le rapprochement. <button class="btn" id="personne-morale-annuler" style="padding:2px 8px;font-size:11.5px">annuler cette levée</button>.</div>':"")
        +(f.alias&&f.alias.length?'<div class="dkv"><span class="k">Autres noms déclarés</span><span class="v">'+f.alias.map(esc).join(" · ")+"</span></div>":"")
        +'<div class="dkv"><span class="k">Ville</span><span class="v">'+(esc(f.ville)||"—")+"</span></div>"
        +'<div class="dkv"><span class="k">Site web</span><span class="v">'+(f.site?esc(f.site):"non trouvé")+"</span></div>"
        +(f.numero_officiel?'<div class="dkv"><span class="k">Numéro officiel</span><span class="v">'+esc(f.numero_officiel)+"</span></div>":"")
        +f.sources.map(function(s){return '<div class="dsrc"><b>'+esc(s.nom)+"</b>"+(s.detail?'<div class="q">'+esc(s.detail)+"</div>":"")
          +(s.id?'<div class="conf">Niveau de confiance de cette source <input type="number" min="0" max="1" step="0.05" value="'+s.confiance+'" data-src="'+esc(s.id)+'"> <button class="btn" data-conf="'+esc(s.id)+'" style="padding:1px 7px;font-size:11px">Enregistrer</button></div>':"")+"</div>"}).join("")
        +(f.verifications||[]).map(function(v){var lien=/^https?:\/\//.test(v.preuve)?' · <a href="'+esc(v.preuve)+'" target="_blank" rel="noopener noreferrer">voir la preuve</a>':"";return '<div class="dnote">'+(v.signal==="alerte"?"⚠ Alerte · ":v.signal==="information"?"Information · ":"Vérifié par ")+esc(v.nom)+(v.origine?" : "+esc(v.origine):"")+lien+"</div>"}).join("")
        +(f.enrichissements||[]).map(function(v){var ch=v.champs||{},bouts=[];if(ch.coordonnees)bouts.push("coordonnées "+ch.coordonnees.lat+", "+ch.coordonnees.lon);["ville","site","numero","pays","detail"].forEach(function(k){if(ch[k])bouts.push(k+" "+ch[k])});return '<div class="dnote">Enrichie par '+esc(v.nom)+" : "+esc(bouts.join(" · "))+(v.origine?" ("+esc(v.origine)+")":"")+"</div>"}).join("")
        +(f.fonction?'<div class="dkv"><span class="k">Fonction</span><span class="v">'+esc(f.fonction)+(f.bloc?" · groupe de "+esc(f.bloc):"")+"</span></div>":"")
        +(f.rapprochement?'<div class="dnote">'+esc(f.rapprochement)+"</div>":"")
        +(f.relations&&f.relations.length?'<div class="dnote">'+f.relations.map(function(r){return esc(r.type.replace(/_/g," "))+" : "+esc(r.vers)}).join("<br>")+"</div>":"")
        +(f.ressemble_a?'<div class="dnote">Nom très proche de « '+esc(f.ressemble_a)+' ». Si ce n’est pas le même, <button class="btn" id="separer" style="padding:2px 8px;font-size:11.5px">dites-le</button>.</div>':"");
      zone.querySelectorAll("button[data-conf]").forEach(function(b){b.onclick=function(){
        var champ=zone.querySelector('input[data-src="'+b.dataset.conf+'"]');
        envoyer("/api/reglages/source/"+encodeURIComponent(b.dataset.conf),"PUT",{confiance:parseFloat(champ.value)}).then(function(){message("Confiance de la source enregistrée (elle vaut aussi dans Réglages).")}).catch(function(e){message(e.message)})}});
      var sp=el("separer");if(sp)sp.onclick=function(){envoyer("/api/recherches/"+rid+"/noms/"+mon+"/separer","POST",{}).then(function(){charger(true)})};
      /* Levée de la règle n° 8 sur cette fiche, puis relance du moteur de rapprochement par la route qui existe pour ça :
         elle peut mettre du temps ou être indisponible, et elle le dit — on ne le cache pas derrière le clic. */
      var pm=el("personne-morale");if(pm)pm.onclick=function(){
        pm.disabled=true;pm.textContent="levée en cours…";
        envoyer("/api/recherches/"+rid+"/noms/"+mon+"/personne_morale","POST",{}).then(function(){
          message("Règle n° 8 levée sur cette fiche. Recherche des rapprochements…");
          return envoyer("/api/suite/tri/proposer/"+rid,"POST",{}).then(function(r){
            message(r&&r.proposes?r.proposes+" rapprochement(s) proposé(s) dans l’onglet Tri.":"Aucun rapprochement trouvé pour cette fiche.");
          }).catch(function(e){message("Levée faite, mais le moteur de rapprochement n’a pas tourné : "+e.message)});
        }).catch(function(e){message(e.message)}).then(function(){charger(true);chargerFiche(mon,d)})};
      var pa=el("personne-morale-annuler");if(pa)pa.onclick=function(){
        pa.disabled=true;
        envoyer("/api/recherches/"+rid+"/noms/"+mon+"/personne_morale","DELETE",{}).then(function(r){
          message(r&&r.rapprochements_retires?"Levée annulée ; "+r.rapprochements_retires+" rapprochement(s) en attente retiré(s).":"Levée annulée.");
        }).catch(function(e){message(e.message)}).then(function(){charger(true);chargerFiche(mon,d)})};
    }).catch(function(e){  /* une fiche qui ne se charge pas doit le dire : un panneau vide ressemblait à un nom sans détail */
      var zone=el("dtail");
      if(zone&&sel===mon&&e&&e.name!=="AbortError")zone.innerHTML='<div class="dnote">Le détail de ce nom n’a pas pu être chargé : '+esc(e.message)+"</div>";
    });
  }
  function decisionBoutons(l){
    return '<div class="dec"><button class="k'+(l.d==="garder"?" on":"")+'" data-d="garder">✓ Garder <kbd>G</kbd></button><button class="l'+(l.d==="plus_tard"?" on":"")+'" data-d="plus_tard">Plus tard <kbd>P</kbd></button><button class="r'+(l.d==="rejeter"&&!l.mo?" on":"")+'" data-d="rejeter">✕ Rejeter <kbd>R</kbd></button></div>'
      +'<div class="motifs">'+(T.motifs||[]).map(function(m){return '<button class="mo'+(l.d==="rejeter"&&l.mo===m.id?" on":"")+'" data-motif="'+esc(m.id)+'" title="Rejeter : '+esc(m.libelle)+'"><kbd>'+esc(m.touche)+"</kbd> "+esc(m.libelle)+"</button>"}).join("")
      +'<button class="mo" id="motifs-regler" title="Changer les motifs et leurs touches">⚙</button></div>';
  }
  function brancherDecisions(d,id){
    d.querySelectorAll(".dec button").forEach(function(b){b.onclick=function(){decider(id,b.dataset.d)}});
    d.querySelectorAll("button[data-motif]").forEach(function(b){b.onclick=function(){decider(id,"rejeter",b.dataset.motif)}});
    var r=d.querySelector("#motifs-regler");if(r)r.onclick=reglerMotifs;
  }
  function reglerMotifs(){
    var courant=(T.motifs||[]).map(function(m){return m.touche+" = "+m.libelle}).join("\n");
    var t=window.prompt("Motifs de rejet : une ligne par motif, « touche = libellé ». Les touches G, R, P, Z et / sont prises.\n\n",courant);
    if(t===null)return;
    var motifs=t.split("\n").map(function(x){return x.trim()}).filter(Boolean).map(function(x){
      var i=x.indexOf("=");var touche=x.slice(0,i).trim(),libelle=x.slice(i+1).trim();
      var ancien=(T.motifs||[]).find(function(m){return m.libelle===libelle});
      return {id:ancien?ancien.id:libelle.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g,"").replace(/[^a-z0-9]+/g,"_").replace(/^_|_$/g,""),libelle:libelle,touche:touche}});
    envoyer("/api/motifs-rejet","PUT",{motifs:motifs}).then(function(){charger(true)}).catch(function(e){message(e.message)});
  }

  /* ------------------------------------------------ décisions ------------------------------------------------ */
  function message(t,avecAnnuler){
    dernierMessage=t;dernierAnnulable=!!avecAnnuler;
    var m=el("tri-msg");
    if(m)m.innerHTML=esc(t)+(avecAnnuler?' <button class="btn" id="msg-undo" style="padding:2px 8px;font-size:11.5px">Annuler</button>':"");
    var u=el("msg-undo");if(u)u.onclick=annulerDernier;
  }
  function recompter(){
    T.a_decider=T.lignes.filter(function(l){return !l.d}).length;
    T.paquets.forEach(function(p){p.a_decider=(parPaquet[p.cle]||[]).filter(function(l){return !l.d}).length});
  }
  function decider(id,valeur,motif){
    var l=parId[id];if(!l)return;
    var avant=l.d, avantMotif=l.mo;if(avant===valeur&&(avantMotif||"")===(motif||""))return;
    l.d=valeur;l.mo=valeur==="rejeter"?(motif||""):"";touchees[id]=true;T.peut_annuler=true;recompter();suivant(id);tout();
    var r=rid, moi={d:valeur,mo:l.mo};enAttente[id]=moi;
    /* les décisions partent UNE À LA FOIS, dans l'ordre où elles ont été prises (jamais des centaines de requêtes en même temps) */
    fileDecisions=fileDecisions.then(function(){
      return envoyer("/api/recherches/"+r+"/decisions","POST",{valeur:valeur,ids:[id],motif:motif||null}).then(function(){if(enAttente[id]===moi)delete enAttente[id]})
        .catch(function(e){if(enAttente[id]===moi)delete enAttente[id];l.d=avant;l.mo=avantMotif;recompter();tout();message("La décision n'a pas pu être enregistrée : "+e.message)});
    });
  }
  function groupe(cle,valeur){
    var p=T.paquets.find(function(x){return x.cle===cle});if(!p)return;
    fileDecisions.then(function(){return envoyer("/api/recherches/"+rid+"/decisions","POST",{valeur:valeur,classement:clActif,cle:cle,filtres:filtres,q:texte,nouveaux:nouveaux})}).then(function(r){
      message(plur(r.touches.length,"nom")+" "+(valeur==="garder"?"gardés":"rejetés")+" dans « "+p.phrase+" ».",true);
      return charger(true);
    }).catch(function(e){message("L'action n'a pas pu être faite : "+e.message)});
  }
  function annulerDernier(){
    if(!T||!T.peut_annuler)return;
    fileDecisions.then(function(){return envoyer("/api/recherches/"+rid+"/annuler","POST",{})}).then(function(r){
      message(r.touches.length?"Annulé : "+plur(r.touches.length,"décision")+" retirée"+(r.touches.length>1?"s":"")+".":"Rien à annuler.");
      return charger(true);
    }).catch(function(e){message(e.message)});
  }
  el("undo").onclick=annulerDernier;

  /* ------------------------------------------------ navigation ------------------------------------------------ */
  /* Au clavier on parcourt TOUS les noms, paquet après paquet, dans l'ordre de l'écran : à la fin d'un paquet on passe au suivant (qui s'ouvre). */
  function ordreNavigation(){
    return T.paquets.reduce(function(a,p){return a.concat(parPaquet[p.cle]||[])},[]);
  }
  function premierADecider(){var o=T?T.lignes.filter(function(l){return !l.d}):[];return o.length?o[0].id:(T&&T.lignes.length?T.lignes[0].id:null)}
  function suivant(apres){
    var nav=ordreNavigation(), i=nav.findIndex(function(l){return l.id===apres});
    var s=nav.slice(i+1).concat(nav.slice(0,i)).find(function(l){return !l.d});
    if(s){sel=s.id;ouvrirPaquetDe(sel)}
  }
  /* Au clavier, le nom suivant peut être dans un paquet replié : on l'ouvre, pour que la ligne active soit toujours visible. */
  function ouvrirPaquetDe(id){var l=parId[id];if(vue==="liste"&&l&&!ouverts[l.p])ouverts[l.p]=true}
  function choisir(id){sel=id;redessinerVisibles();detail()}
  function redessinerVisibles(){handles.forEach(function(h){if(h.redessiner)h.redessiner()});if(tabulateur&&vue==='tableau'){try{tabulateur.getRows().forEach(function(r){r.reformat()})}catch(e){}}}
  function deplacer(delta){
    var nav=ordreNavigation(), i=nav.findIndex(function(l){return l.id===sel});
    var n=nav[Math.max(0,Math.min(nav.length-1,(i<0?0:i+delta)))];
    if(!n)return;sel=n.id;
    if(vue==="liste"&&!ouverts[parId[sel].p]){ouverts[parId[sel].p]=true;vueListe()}
    handles.forEach(function(h){if(h.paquet!==undefined){var k=h.items.indexOf(n);if(k>=0)h.montrer(k)}});
    redessinerVisibles();
    if(tabulateur&&vue==="tableau"){scrollerTableau()}
    detail();
  }

  /* ------------------------------------------------ filtres : facettes, texte, nouveaux ------------------------------------------------ */
  function dessinerFacettes(){
    el("facettes").innerHTML=(T.facettes||[]).map(function(f){
      return '<div class="facette"><span class="fl">'+esc(f.libelle)+"</span>"+f.valeurs.map(function(v){
        return '<button class="fv'+(v.actif?" on":"")+(v.n?"":" vide")+'" data-f="'+esc(f.id+":"+v.valeur)+'" aria-pressed="'+(v.actif?"true":"false")+'">'+esc(v.libelle)+' <span class="n">'+v.n+"</span></button>"}).join("")+"</div>"}).join("");
    el("facettes").querySelectorAll(".fv").forEach(function(b){b.onclick=function(){
      var k=b.dataset.f, i=filtres.indexOf(k);if(i>=0)filtres.splice(i,1);else filtres.push(k);ouverts={};charger(true)}});
    var actif=filtres.length||texte||nouveaux;
    el("tri-effacer").style.display=actif?"inline-block":"none";
    el("tri-filtre-etat").textContent=actif?T.total+" nom"+(T.total>1?"s":"")+" sur "+T.total_tout:"";
    el("tri-q").value=texte;el("tri-nouveaux").checked=nouveaux;
  }
  var delaiQ=null;
  el("tri-q").oninput=function(){var v=el("tri-q").value;if(delaiQ)clearTimeout(delaiQ);delaiQ=setTimeout(function(){texte=v.trim();ouverts={};charger(true)},250)};
  el("tri-nouveaux").onchange=function(){nouveaux=el("tri-nouveaux").checked;ouverts={};charger(true)};
  el("tri-effacer").onclick=function(){filtres=[];texte="";nouveaux=false;ouverts={};charger(true)};
  el("tri-rejets").onclick=function(){
    var p=el("rejets-panneau");
    if(p.style.display==="block"){p.style.display="none";return}
    if(!rid)return;
    api("/api/recherches/"+rid+"/rejets").then(function(r){
      var motifs=Object.keys(r.motifs).filter(function(m){return r.sources.some(function(s){return s.motifs[m]})});
      p.innerHTML=r.total_rejetes?'<table class="rejets"><thead><tr><th>Source</th><th>Rejetés</th><th>sur</th><th>Part</th>'+motifs.map(function(m){return "<th>"+esc(r.motifs[m])+"</th>"}).join("")+"</tr></thead><tbody>"
        +r.sources.map(function(s){return "<tr><td>"+esc(s.nom)+'</td><td class="num">'+s.rejetes+'</td><td class="num">'+s.total+'</td><td class="num">'+Math.round(s.part*100)+" %</td>"+motifs.map(function(m){return '<td class="num">'+(s.motifs[m]||0)+"</td>"}).join("")+"</tr>"}).join("")+"</tbody></table>"
        :'<div class="empty">Aucun nom rejeté pour l\'instant.</div>';
      p.style.display="block";
    }).catch(function(e){message(e.message)});
  };

  /* ------------------------------------------------ ensemble ------------------------------------------------ */
  function tout(){
    if(!T)return;
    ensemble();classements();dessinerFacettes();
    if(vue==="liste")vueListe();else if(vue==="colonnes")vueColonnes();else if(vue==="tableau"){if(tabulateur&&jeuTableau===T)majTableau();else vueTableau()}else if(vue==="carte")vueCarte();else vueFiches();
    detail();
    montrerSelection();
    if(dernierMessage)message(dernierMessage,dernierAnnulable&&T.peut_annuler);
  }
  /* Après chaque redessin (une décision, un filtre), la ligne active reste dans la partie visible : on ne perd jamais sa place. */
  function scrollerTableau(){
    try{var p=tabulateur.scrollToRow(sel,"nearest",false);if(p&&p.catch)p.catch(function(){})}catch(e){}  /* une ligne pas encore dessinée n'est pas une erreur */
  }
  function montrerSelection(){
    if(!sel)return;
    handles.forEach(function(h){if(h.paquet!==undefined&&h.items){var k=h.items.findIndex(function(l){return l.id===sel});if(k>=0)h.montrer(k)}});
    if(tabulateur&&vue==="tableau"){scrollerTableau()}
  }
  document.querySelectorAll(".views button[data-v]").forEach(function(b){
    b.onclick=function(){vue=b.dataset.v;document.querySelectorAll(".views button[data-v]").forEach(function(x){x.classList.remove("on")});b.classList.add("on");tout()}});

  document.addEventListener("keydown",function(e){
    var page=el("pg-tri");
    if(!page||!page.classList||!page.classList.contains("on"))return;
    if(e.target&&(e.target.tagName==="INPUT"||e.target.tagName==="SELECT"||e.target.tagName==="TEXTAREA"))return;
    var k=(e.key||"").toLowerCase();
    if(k==="arrowdown"){deplacer(1);e.preventDefault()}
    else if(k==="arrowup"){deplacer(-1);e.preventDefault()}
    else if(k==="g"&&sel)decider(sel,"garder");
    else if(k==="r"&&sel)decider(sel,"rejeter");
    else if(k==="p"&&sel)decider(sel,"plus_tard");
    else if(k==="z")annulerDernier();
    else if(sel&&!e.ctrlKey&&!e.metaKey&&!e.altKey){
      var m=(T&&T.motifs||[]).find(function(x){return x.touche.toLowerCase()===k});
      if(m)decider(sel,"rejeter",m.id);  /* une touche = un rejet motivé */
    }
  });

  /* ------------------------------------------------ export ------------------------------------------------ */
  var FORMATS=[], REGLAGES_SORTIE=null, derniereSignature="";
  var CONTENU_PHRASE={nom:"les noms",tsites:"nom;ville;pays (trouver-sites)",detail:"le détail"};
  function chargerFormats(){
    Promise.all([api("/api/formats"),api("/api/reglages")]).then(function(r){
      FORMATS=r[0];REGLAGES_SORTIE=r[1];
      var signature=JSON.stringify([r[0].map(function(f){return f.id}),(r[1].parties.sortie||[]).map(function(f){return [f.actif,f.contenus_choisis]})]);
      if(signature===derniereSignature)return;  /* rien n'a changé dans Réglages : on ne touche pas aux cases que vous êtes en train de cocher */
      derniereSignature=signature;
      var actifs=(r[1].parties.sortie||[]).filter(function(f){return f.actif}).map(function(f){return f.id});
      var choisis={};(r[1].parties.sortie||[]).forEach(function(f){choisis[f.id]=f.contenus_choisis});
      el("export-formats").innerHTML=FORMATS.map(function(f){
        var cs=f.contenus.length>1?f.contenus.map(function(c){return '<label style="margin-left:10px"><input type="checkbox" data-fc="'+esc(f.id)+'" data-c="'+esc(c)+'"'+((choisis[f.id]||f.contenus_defaut).indexOf(c)>=0?" checked":"")+"> "+esc(CONTENU_PHRASE[c]||c)+"</label>"}).join(""):"";
        return '<div style="margin:4px 0"><label><input type="checkbox" data-f="'+esc(f.id)+'"'+(actifs.indexOf(f.id)>=0?" checked":"")+"> <b>"+esc(f.nom)+"</b></label>"+cs+' <span style="color:var(--dim)">— '+esc(f.description)+"</span></div>"}).join("");
      el("export-formats").querySelectorAll("input[data-f]").forEach(function(i){i.onchange=majWebhook});
      el("export-webhook").value=(r[1].sortie||{}).webhook_url||"";
      majWebhook();
    }).catch(function(){});
  }
  function majWebhook(){var w=el("export-formats").querySelector('input[data-f="webhook"]');el("export-webhook-w").style.display=w&&w.checked?"block":"none"}
  el("exporter").onclick=function(){
    if(!rid)return;
    var demandes=[].slice.call(el("export-formats").querySelectorAll("input[data-f]")).filter(function(i){return i.checked}).map(function(i){
      var f=FORMATS.find(function(x){return x.id===i.dataset.f});
      var cs=[].slice.call(el("export-formats").querySelectorAll('input[data-fc="'+f.id+'"]')).filter(function(c){return c.checked}).map(function(c){return c.dataset.c});
      var d={format:f.id};if(cs.length)d.contenus=cs;
      if(f.id==="webhook")d.options={url:el("export-webhook").value.trim()};
      return d});
    if(!demandes.length){el("export-msg").textContent="Cochez au moins un format.";return}
    var filtre=el("export-filtre").value;
    el("exporter").disabled=true;el("export-msg").textContent="Écriture…";
    envoyer("/api/recherches/"+rid+"/export","POST",{formats:demandes,filtre:filtre.indexOf(",")>=0?filtre.split(","):filtre,dossier:el("export-dossier").value.trim()}).then(function(r){
      el("export-msg").textContent=r.exportes+" nom"+(r.exportes>1?"s":"")+" exporté"+(r.exportes>1?"s":"")+" ("+r.trace.filtre+") — fichiers : "+r.fichiers.join(", ")
        +(r.envois.length?" — envoyé à "+r.envois.map(function(e){return e.adresse+" (réponse "+e.statut+")"}).join(", "):"")+(r.erreurs.length?" — PROBLÈME : "+r.erreurs.map(function(e){return e.format+" : "+e.raison}).join(" ; "):"")+". Dossier : "+r.dossier;
    }).catch(function(e){el("export-msg").textContent="L'export n'a pas pu se faire : "+e.message}).then(function(){el("exporter").disabled=false});
  };

  document.addEventListener("onglet",function(e){if(e.detail==="tri"){chargerFormats();listeRecherches().then(function(){charger(true)})}});
  listeRecherches().then(function(){charger()});chargerFormats();
})();
