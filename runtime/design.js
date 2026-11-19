(() => {
  const box = document.querySelector('#design');
  let revision = 0;
  function invalidate() {
    revision++;
    box.querySelector('.choices').replaceChildren();
    box.querySelector('output').textContent='';
  }
  ['key','shop'].forEach(id=>document.getElementById(id).addEventListener('input',invalidate));
  const button=box.querySelector('#generate');
  async function send(action,data) {
    const options={headers:{Authorization:'Bearer '+document.getElementById('key').value}};
    if (data) {
      options.method='POST';
      options.headers['Content-Type']='application/json';
      options.body=JSON.stringify(data);
    }
    const shop=encodeURIComponent(document.getElementById('shop').value);
    const response=await fetch('/api/'+shop+'/'+action,options);
    const body=await response.json();
    if (!response.ok) throw Error(body.error);
    return body;
  }
  async function run(action,data) {
    const current=++revision,output=box.querySelector('output');
    const choices=box.querySelector('.choices');
    button.disabled=true;
    output.textContent=action==='generate'?'Je websitekleuren en lettertypen worden gelezen…':'';
    try {
      const result=await send(action,data);
      if(current!==revision)return;
      choices.replaceChildren();
      box.querySelector('input').value=result.site;
      button.disabled=result.pending || result.variants.length>0;
      result.variants.forEach((theme,index)=>{
        const card=document.createElement('article'), sample=document.createElement('div');
        const name=document.createElement('strong'),hint=document.createElement('p'),apply=document.createElement('button');
        Object.assign(card.style,{backgroundColor:theme.background,color:theme.foreground,fontFamily:theme.font,padding:'16px',borderRadius:'10px',margin:'8px 0'});
        name.textContent=theme.name;hint.textContent='Kennismaking · 30 minuten';
        sample.textContent='09:00　 10:30　 14:00';
        apply.textContent=JSON.stringify(result.active)===JSON.stringify(theme)?'Gepubliceerd':'Deze variant publiceren';
        apply.disabled=apply.textContent==='Gepubliceerd';
        Object.assign(apply.style,{backgroundColor:theme.accent,color:theme.buttonText});
        apply.onclick=()=>run('publish',{batch:result.batch,index});
        card.append(name,hint,sample,apply);choices.append(card);
      });
      output.textContent=result.pending?'Een generatie loopt. Vernieuw de ontwerpen over een moment.':
        result.variants.length?'Je drie varianten voor '+result.month+'. Je kunt wisselen zonder opnieuw te genereren.':'Je kunt deze maand drie varianten genereren.';
    } catch(e) {
      if(current===revision){output.textContent=e.message;button.disabled=false;}
    }
  }
  button.onclick=()=>run('generate',{site:box.querySelector('input').value.trim()});
  box.querySelector('#reloadDesign').onclick=()=>run('design');
  document.addEventListener('workspace-open',()=>run('design'));
})();
