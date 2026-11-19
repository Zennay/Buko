(() => {
  const origin = new URL(document.currentScript.src).origin;
  if (customElements.get('blendbook-form')) return;
  class Booking extends HTMLElement {
    async connectedCallback() {
      if (this.shadowRoot) return;
      const root = this.attachShadow({mode:'open'});
      root.innerHTML = `<style>
        :host{display:block;color:inherit;font:inherit;--ink:var(--blendbook-color,#253c36)}
        form{max-width:560px;display:grid;gap:16px}label{display:grid;gap:5px}
        button,select,input{border:1px solid #a9b8b0;border-radius:8px;padding:11px;font:inherit}
        button{background:var(--ink);color:white;cursor:pointer}button:disabled{opacity:.5}
        output{line-height:1.5} [hidden]{display:none}
      </style><form><label class="service">Dienst<select name="service"></select></label>
      <label>Datum<input required type="date" name="day"></label>
      <label><span class="mode">Tijd</span><select required name="start"></select></label>
      <label>Naam<input required name="name" autocomplete="name" maxlength="120"></label>
      <label>E-mailadres<input required type="email" name="email" autocomplete="email"></label>
      <button disabled>Afspraak boeken</button></form><output aria-live="polite"></output>`;
      const form=root.querySelector('form'), fields=form.elements, msg=root.querySelector('output');
      const button=form.querySelector('button');
      const shop=this.getAttribute('bedrijf') || new URLSearchParams(location.search).get('bedrijf') || 'studio';
      const api=origin+'/api/'+encodeURIComponent(shop)+'/';
      async function request(path, options) {
        const response=await fetch(api+path, options);
        const body=await response.json();
        if (!response.ok) throw new Error(body.error);
        return body;
      }
      let revision=0;
      async function refresh() {
        const current=++revision;
        fields.start.replaceChildren();
        button.disabled=true;
        try {
          const query=new URLSearchParams({day:fields.day.value,service:fields.service.value||0});
          const slots=await request('slots?'+query);
          if (current!==revision) return;
          slots.forEach(slot=>fields.start.add(new Option(slot.label,slot.start)));
          button.disabled=!slots.length;
          msg.textContent=slots.length?'':'Geen tijden vrij. Kies een andere datum.';
        } catch(e) { if(current===revision) msg.textContent=e.message; }
      }
      try {
        const c=await request('config');
        if(c.theme){
          const t=c.theme;
          Object.assign(form.style,{backgroundColor:t.background,color:t.foreground,fontFamily:t.font,padding:'16px',borderRadius:'8px'});
          Object.assign(button.style,{backgroundColor:t.accent,color:t.buttonText});
        }
        root.querySelector('.service').hidden=!c.showServices;
        root.querySelector('.mode').textContent=c.windows?'Aankomst tussen (Nederlandse tijd)':'Starttijd (Nederlandse tijd)';
        c.services.forEach((s,i)=>fields.service.add(new Option([s.name,s.duration+' min',s.price].filter(Boolean).join(' · '),i)));
        fields.day.min=new Intl.DateTimeFormat('sv-SE',{timeZone:'Europe/Amsterdam'}).format(new Date());
        fields.day.value=fields.day.min;
        fields.day.onchange=fields.service.onchange=refresh;
        await refresh();
        form.onsubmit=async event=>{
          event.preventDefault();
          button.disabled=true;
          const payload=Object.fromEntries(new FormData(form));
          payload.start=Number(payload.start);
          try {
            const b=await request('book',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
            form.hidden=true;
            msg.textContent='Geboekt voor '+b.day+' om '+b.label+'. Je boekingsnummer is '+b.reference+'. ';
            const link=document.createElement('a');
            link.href=origin+'/beheer-afspraak#'+[shop,b.reference,b.manageKey].map(encodeURIComponent).join('/');
            link.textContent='Beheer je afspraak of voeg deze toe aan je agenda';
            msg.append(link);
          } catch(e) { await refresh(); msg.textContent=e.message; }
        };
      } catch(e) {msg.textContent=e.message;}
    }
  }
  customElements.define('blendbook-form',Booking);
})();
