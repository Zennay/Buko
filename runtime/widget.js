(() => {
  const origin = new URL(document.currentScript.src).origin;
  if (customElements.get('blendbook-form')) return;
  const today = () => new Intl.DateTimeFormat('sv-SE',{timeZone:'Europe/Amsterdam'}).format(new Date());
  const key = date => [date.getFullYear(),String(date.getMonth()+1).padStart(2,'0'),String(date.getDate()).padStart(2,'0')].join('-');
  const local = day => new Date(day+'T12:00:00');
  const label = (day,options) => local(day).toLocaleDateString('en-GB',options);
  class Booking extends HTMLElement {
    connectedCallback() {
      if (this.shadowRoot) return;
      const root=this.attachShadow({mode:'open'});
      root.innerHTML=`<style>
      :host{display:block;container-type:inline-size;--accent:var(--blendbook-color,#2759cb);--on:#fff;color:#192b41;font:inherit}
      *{box-sizing:border-box}[hidden]{display:none!important}h2,h3,p{margin:0}h2{font-size:1.35rem;letter-spacing:-.035em}h3{font-size:1rem}small{font-size:.82em}button,input,select{font:inherit;color:inherit}button{cursor:pointer;border:1px solid #ccd4e0;background:transparent;border-radius:7px;padding:.52em .8em}button:disabled{opacity:.35;cursor:default}button:focus-visible,input:focus-visible,select:focus-visible{outline:3px solid var(--accent);outline-offset:2px}
      .layout{border:1px solid #dbe1e9;border-radius:14px;overflow:hidden;background:var(--surface,#fff);color:var(--text,inherit)}aside,section{padding:clamp(14px,3cqw,26px)}aside{border-bottom:1px solid #dbe1e9;display:grid;align-content:start;gap:10px}.host{font-weight:650;font-size:.84rem;overflow-wrap:anywhere}.meta{font-size:.87rem;line-height:1.55}.meta span{display:block}section{display:grid;gap:14px;align-content:start}.month,.actions{display:flex;align-items:center;justify-content:space-between;gap:6px}.month button{width:36px;height:36px;padding:0;font-size:18px}.grid{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:2px;text-align:center}.grid small{padding:6px 0}.grid button{border:0;min-height:35px;padding:3px 0;font-size:.9rem}.grid button:hover:enabled,.slots button:hover{background:color-mix(in srgb,var(--accent) 10%,transparent)}.grid [aria-pressed=true],.grid [aria-pressed=true]:hover,.primary{background:var(--accent)!important;color:var(--on);font-weight:650}.grid [aria-current=date]{box-shadow:inset 0 0 0 1px var(--accent)}.slots{display:grid;grid-template-columns:repeat(auto-fit,minmax(84px,1fr));gap:6px;max-height:220px;overflow:auto}.slots button{font-weight:600;border-color:var(--accent);font-size:.9em}.slots:empty{display:none}
      label{display:grid;gap:4px;font-size:.88rem;font-weight:600}input,select{background:var(--surface,#fff);border:1px solid #bac6d4;padding:9px;border-radius:7px;width:100%;min-width:0}.details{display:grid;gap:14px}.primary{padding:11px;border:0}.message{display:block;font-size:.9rem;line-height:1.5}.message:empty{display:none}a{color:inherit}.back{justify-self:start}.timebox{display:grid;gap:8px;align-content:start}.picker{display:grid;gap:12px}.datebox{display:grid;gap:6px}
      @container(min-width:590px){.layout{display:grid;grid-template-columns:minmax(165px,.75fr) minmax(0,1.5fr)}aside{border:0;border-right:1px solid #dbe1e9}}
      @container(min-width:850px){.picker{grid-template-columns:minmax(230px,1.7fr) minmax(115px,1fr)}.slots{grid-template-columns:1fr;max-height:265px}}
      </style><div class="layout"><aside><span class="host"></span><h2></h2><div class="meta"><span class="duration"></span><span>Europe/Amsterdam</span></div><label class="service">Event type<select></select></label></aside>
      <section><div class="schedule"><h3>Select a date &amp; time</h3><div class="picker"><div class="datebox"><div class="month"><button type="button" aria-label="Previous month">‹</button><strong></strong><button type="button" aria-label="Next month">›</button></div><div class="grid"></div></div><div class="timebox"><strong class="chosenDay"></strong><div class="slots"></div></div></div></div>
      <form class="details" hidden><button type="button" class="back">← Change time</button><h3>Your details</h3><strong class="summary"></strong><label>Name<input required name="name" maxlength="120" autocomplete="name"></label><label>Email address<input required type="email" name="email" autocomplete="email"></label><button class="primary">Book appointment</button></form><output class="message" role="status"></output></section></div>`;
      const get=q=>root.querySelector(q), form=get('form'), select=get('select'), msg=get('output'), grid=get('.grid'), times=get('.slots');
      const shop=this.getAttribute('bedrijf') || new URLSearchParams(location.search).get('bedrijf') || 'studio';
      const preview=this.hasAttribute('preview'), api=origin+'/api/'+encodeURIComponent(shop)+'/';
      let config,day=today(),month=local(day),slot,seq=0;
      const limit=local(day);limit.setDate(limit.getDate()+365);
      get('.host').textContent=preview?'Your booking page':shop.replaceAll('-',' ');
      async function request(path,opts){const r=await fetch(api+path,opts);const body=await r.json();if(!r.ok)throw Error(body.error);return body}
      function calendar(){
        const y=month.getFullYear(),m=month.getMonth();
        get('.month strong').textContent=month.toLocaleDateString('en-GB',{month:'long',year:'numeric'});
        get('[aria-label="Previous month"]').disabled=key(new Date(y,m,1)).slice(0,7)<=today().slice(0,7);
        get('[aria-label="Next month"]').disabled=key(new Date(y,m,1)).slice(0,7)>=key(limit).slice(0,7);
        grid.replaceChildren();
        for(const text of ['Mo','Tu','We','Th','Fr','Sa','Su']){const el=document.createElement('small');el.textContent=text;grid.append(el)}
        for(let n=0;n<(new Date(y,m,1).getDay()+6)%7;n++)grid.append(document.createElement('span'));
        for(let n=1;n<=new Date(y,m+1,0).getDate();n++){
          const value=key(new Date(y,m,n)),b=document.createElement('button');b.type='button';b.textContent=n;b.disabled=value<today()||value>key(limit);
          b.setAttribute('aria-label',label(value,{dateStyle:'full'}));b.setAttribute('aria-pressed',String(day===value));if(value===today())b.setAttribute('aria-current','date');
          b.onclick=()=>{day=value;calendar();refresh()};grid.append(b);
        }
      }
      for(const [direction,step] of [['Previous',-1],['Next',1]])get('[aria-label="'+direction+' month"]').onclick=()=>{month=new Date(month.getFullYear(),month.getMonth()+step,1);calendar()};
      function info(){const s=config.showServices?config.services[Number(select.value)||0]:null;get('h2').textContent=s?.name||'Appointment';get('.duration').textContent=[(s?.duration||config.duration)+' min',s?.price].filter(Boolean).join(' · ')}
      async function refresh(){
        const ticket=++seq;times.replaceChildren();slot=null;info();
        get('.chosenDay').textContent=label(day,{weekday:'short',day:'numeric',month:'short'});msg.textContent='Loading times…';
        try{
          const options=preview?[{start:540,label:config.windows?'09:00–11:00':'09:00'},{start:780,label:config.windows?'13:00–15:00':'13:00'}]:await request('slots?'+new URLSearchParams({day,service:select.value||0}));
          if(ticket!==seq)return;msg.textContent=options.length?'':'No times available. Choose another date.';
          for(const option of options){const b=document.createElement('button');b.type='button';b.textContent=option.label;b.onclick=()=>{slot=option;get('.summary').textContent=label(day,{dateStyle:'medium'})+' · '+slot.label;get('.schedule').hidden=true;form.hidden=false;select.disabled=true;form.elements.name.focus()};times.append(b)}
        }catch(e){if(ticket===seq)msg.textContent=e.message}
      }
      function apply(c){config=c;if(preview&&c.previewHost)get('.host').textContent=c.previewHost;form.hidden=true;get('.schedule').hidden=false;select.disabled=false;const t=c.theme||{},layout=get('.layout');
        for(const [property,value] of Object.entries({'--accent':t.accent,'--on':t.buttonText,'--surface':t.background,'--text':t.foreground}))if(value)layout.style.setProperty(property,value);
        layout.style.fontFamily=t.font||'inherit';select.replaceChildren();c.services.forEach((s,i)=>select.add(new Option(s.name,i)));
        get('.service').hidden=!c.showServices||c.services.length<=1;get('.primary').textContent=c.buttonLabel||'Book appointment';calendar();refresh()}
      select.onchange=refresh;get('.back').onclick=()=>{form.hidden=true;get('.schedule').hidden=false;select.disabled=false;refresh()};
      form.onsubmit=async e=>{e.preventDefault();if(!slot)return;if(preview){msg.textContent=config.successLabel||'Appointment confirmed.';return;}get('.primary').disabled=true;get('.back').disabled=true;
        try{const b=await request('book',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({day,service:select.value||0,start:slot.start,name:form.elements.name.value,email:form.elements.email.value})});form.hidden=true;get('.service').hidden=true;
          msg.textContent=(config.successLabel||'Appointment confirmed.')+' '+label(b.day,{dateStyle:'long'})+' · '+b.label+'. ';const a=document.createElement('a');a.href=origin+'/manage#'+[shop,b.reference,b.manageKey].map(encodeURIComponent).join('/');a.textContent='Manage appointment';msg.append(a);
        }catch(err){form.hidden=true;get('.schedule').hidden=false;select.disabled=false;await refresh();msg.textContent=err.message}finally{get('.primary').disabled=false;get('.back').disabled=false}};
      if(preview)this.renderPreview=apply;else request('config').then(apply).catch(e=>msg.textContent=e.message)
    }
  }
  customElements.define('blendbook-form',Booking);
})();
