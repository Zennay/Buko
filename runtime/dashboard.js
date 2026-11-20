'use strict';
const $=id=>document.getElementById(id), pages=[...document.querySelectorAll('[data-page]')];
const make=(tag,text)=>Object.assign(document.createElement(tag),{textContent:text});
const days=['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'];
const today=new Intl.DateTimeFormat('sv-SE',{timeZone:'Europe/Amsterdam'}).format(new Date());
let state,selected=today,month=new Date(today+'T12:00'),moving,revision=0;
const api=()=>'/api/'+encodeURIComponent($('shop').value)+'/';
async function call(action,data){
 const options={headers:{Authorization:'Bearer '+$('key').value}};
 if(data!==undefined){options.method='POST';options.headers['Content-Type']='application/json';options.body=JSON.stringify(data)}
 const r=await fetch(api()+action,options), result=await r.json();
 if(!r.ok)throw Error(result.error);return result;
}
function feedback(message){$('status').textContent=message}
function button(label,fn){const b=make('button',label);b.type='button';b.className='soft';b.onclick=()=>Promise.resolve().then(fn).catch(e=>feedback(e.message));return b}
function nav(name){
 const legacy={Overzicht:'Overview',Boekingen:'Bookings',Kalender:'Calendar',Boekingsformulier:'Booking form',Beschikbaarheid:'Availability',Integraties:'Integrations',Diensten:'Services',Ontwerp:'Design','E-mails':'Emails',Publiceren:'Publish'};
 name=legacy[name]||name;
const groupIndex=['Services','Design','Emails','Publish'].indexOf(name);
 if(groupIndex>=0){name='Booking form';const group=document.querySelectorAll('.editorGroup')[groupIndex];group.open=true;requestAnimationFrame(()=>group.scrollIntoView({block:'nearest'}))}
 if(!pages.some(p=>p.dataset.page===name))name='Overview';
 pages.forEach(p=>p.hidden=p.dataset.page!==name);for(const b of $('nav').children)b.setAttribute('aria-current',b.textContent===name?'page':'false');
 $('pageSelect').value=name;$('title').textContent=name;history.replaceState(null,'','#'+encodeURIComponent(name));feedback('');}
pages.forEach(p=>$('nav').append(button(p.dataset.page,()=>nav(p.dataset.page))));
for(const link of document.querySelectorAll('[data-to]'))link.onclick=()=>nav(link.dataset.to);
for(const page of pages)$('pageSelect').add(new Option(page.dataset.page));
$('pageSelect').onchange=()=>nav($('pageSelect').value);
$('copyPublic').onclick=async()=>{try{await navigator.clipboard.writeText($('public').href);feedback('Booking link copied.')}catch{feedback('Copy the link above the button.')}};
function field(label,type,value){const l=make('label',label),i=document.createElement('input');i.type=type;i.value=value;l.append(i);return l}
function service(s={name:'',duration:30,price:''}){const row=make('div','');row.className='service';
 const name=field('Service','text',s.name),duration=field('Minutes','number',s.duration),price=field('Price (optional)','text',s.price);
 duration.lastChild.min=5;duration.lastChild.max=720;row.append(name,duration,price,button('Remove',()=>{row.remove();updateEditor()}));$('serviceRows').append(row)}
function exception(date='',hours=''){const row=make('div','');row.className='row';row.append(field('Date','date',date),field('Time blocks · leave blank for a day off','text',hours),button('Remove',()=>row.remove()));$('exceptions').append(row)}
function weekDay(day, value){
 const box=make('div',''),label=make('label',day),enabled=document.createElement('input'),blocks=make('div','');
 enabled.type='checkbox';enabled.checked=Boolean(value);label.prepend(enabled);label.className='check';box.className='weekDay';
 function add(interval='09:00-17:00'){
  const row=make('div',''),parts=interval.split('-');row.className='timeBlock';
  const from=field('From','time',parts[0]),to=field('To','time',parts[1]);from.lastChild.required=to.lastChild.required=true;
  row.append(from,to,button('Remove',()=>{row.remove();if(!blocks.children.length){enabled.checked=false;sync()}}));blocks.append(row);
 }
 const append=button('+ Time block',()=>add('13:00-17:00'));
 function sync(){blocks.hidden=append.hidden=!enabled.checked;if(enabled.checked&&!blocks.children.length)add();for(const input of blocks.querySelectorAll('input'))input.disabled=!enabled.checked}
 if(value)value.split(',').forEach(v=>add(v.trim()));enabled.onchange=sync;box.append(label,blocks,append);sync();$('week').append(box);
}
function weekValues(){return [...$('week').children].map(box=>box.querySelector('input').checked?[...box.querySelectorAll('.timeBlock')].map(row=>[...row.querySelectorAll('input')].map(i=>i.value).join('-')).join(', '):'')}
$('addService').onclick=()=>{service();updateEditor()};$('addException').onclick=()=>exception();
function toggle(){ $('serviceEditor').hidden=!$('showServices').checked;$('defaultDuration').hidden=$('showServices').checked;$('windowLabel').hidden=!$('windows').checked}
$('showServices').onchange=$('windows').onchange=toggle;
function renderBookings(box,entries,editable=false){box.replaceChildren();if(!entries.length){box.append(make('p','No appointments match this selection.'));return}
 for(const b of entries){const row=make('div',''),info=make('div','');row.className='row';info.append(make('strong',b.name),make('small',[b.day,b.label,b.service,b.price].filter(Boolean).join(' · ')),make('small',b.email));row.append(info);
 if(editable){const actions=make('div','');actions.className='actions';actions.append(button('Reschedule',()=>openMove(b)),button('Cancel',async()=>{if(confirm('Cancel the appointment for '+b.name+' on '+b.day+'?')){await call('managecancel',{ref:b.ref});await reloadBookings();feedback('Appointment cancelled.')}}));row.append(actions)}box.append(row)}}
function filter(){const q=$('search').value.toLowerCase(),period=$('period').value;
 renderBookings($('reservations'),state.bookings.filter(b=>[b.name,b.email,b.service].join(' ').toLowerCase().includes(q)&&(period==='all'||(period==='past'?b.day<today:b.day>=today))),true)}
$('search').oninput=$('period').onchange=filter;
function calendar(){const y=month.getFullYear(),m=month.getMonth(),start=new Date(y,m,1),grid=$('monthGrid');grid.replaceChildren();$('month').textContent=month.toLocaleDateString('en-GB',{month:'long',year:'numeric'});
 days.forEach(d=>grid.append(make('small',d.slice(0,2))));for(let i=0;i<(start.getDay()+6)%7;i++)grid.append(make('span',''));
 for(let i=1;i<=new Date(y,m+1,0).getDate();i++){const date=[y,String(m+1).padStart(2,'0'),String(i).padStart(2,'0')].join('-'),count=state.bookings.filter(b=>b.day===date).length;const b=button(String(i)+(count?' •':''),()=>{selected=date;calendar()});b.title=count+' appointments';b.classList.toggle('selected',date===selected);grid.append(b)}
 $('selectedDay').textContent=new Date(selected+'T12:00').toLocaleDateString('en-GB',{day:'numeric',month:'long'});renderBookings($('dayBookings'),state.bookings.filter(b=>b.day===selected),true)}
for(const [id,delta] of [['prev',-1],['next',1]])$(id).onclick=()=>{month=new Date(month.getFullYear(),month.getMonth()+delta,1);calendar()};
function overview(){
 const strip=$('weekStrip');strip.replaceChildren();
 for(let offset=0;offset<7;offset++){const date=new Date(today+'T12:00');date.setDate(date.getDate()+offset);
  const key=[date.getFullYear(),String(date.getMonth()+1).padStart(2,'0'),String(date.getDate()).padStart(2,'0')].join('-'),count=state.bookings.filter(b=>b.day===key).length;
  const b=button('',()=>{selected=key;month=new Date(date);calendar();nav('Calendar')});
  b.setAttribute('aria-label',date.toLocaleDateString('en-GB',{weekday:'long',day:'numeric',month:'long'})+', '+count+' appointments');b.className='weekCell';b.classList.toggle('current',offset===0);b.append(make('small',date.toLocaleDateString('en-GB',{weekday:'short'})),make('strong',date.getDate()),make('span',count?String(count):'·'));strip.append(b);
 }
 $('serviceSummary').textContent=state.config.showServices?state.config.services.map(s=>s.name).join(', '):'Single appointment type';$('hoursSummary').textContent=state.config.hours.filter(Boolean).length+' working days per week';const future=state.bookings.filter(b=>b.day>=today);$('stats').replaceChildren();
 for(const [label,count] of [['Today',future.filter(b=>b.day===today).length],['From today',future.length],['Services',state.config.showServices?state.config.services.length:1]]){const card=make('div',label);card.className='metric';card.append(make('strong',count));$('stats').append(card)}
 renderBookings($('upcoming'),future.slice(0,4));filter();calendar()}
async function reloadBookings(){state=await call('admin');overview()}
function draft(){
 const services=[...$('serviceRows').children].map(row=>{const [name,duration,price]=row.querySelectorAll('input');return {name:name.value.trim(),duration:Number(duration.value),price:price.value.trim()}});
 const theme=Object.fromEntries(['background','foreground','accent','font'].map(k=>[k,$(k).value]));
 const channels=theme.accent.match(/\w\w/g).map(s=>parseInt(s,16)/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4);
 theme.buttonText=channels.reduce((sum,v,i)=>sum+v*[.2126,.7152,.0722][i],0)>.179?'#000000':'#ffffff';
 theme.name='Custom design';
 return {theme,services,showServices:$('showServices').checked,duration:+$('duration').value,mailText:$('mailText').value,buttonLabel:$('buttonLabel').value.trim(),successLabel:$('successLabel').value.trim()};
}
let publishedDraft='';
function updateEditor(){
 if(!state)return;
 const data=draft();
 $('visitorWidget').renderPreview({...data,windows:state.config.windows});
 const changed=JSON.stringify(data)!==publishedDraft;
 $('editorState').textContent=changed?'Unpublished changes':'Published';
 $('publishForm').disabled=!changed;
}
$('builder').addEventListener('input',updateEditor);
document.addEventListener('choose-theme',event=>{for(const k of ['accent','background','foreground','font'])$(k).value=event.detail[k];updateEditor()});
$('publishForm').onclick=async()=>{
 const data=draft();$('publishForm').disabled=true;
 try{
  state=await call('admin',{...state.config,...data});
  publishedDraft=JSON.stringify(data);overview();updateEditor();feedback('Booking form published.');
 }catch(e){$('editorState').textContent=e.message;feedback(e.message);$('publishForm').disabled=false}
};
function mailPreview(){$('mailPreview').textContent=$('mailText').value.replace(/\{\{(customer_name|service_name|booking_date|booking_time|booking_price)\}\}/g,(_,k)=>({customer_name:'Robin',service_name:'Introductory call',booking_date:today,booking_time:'10:00',booking_price:'€ 30'})[k])||'Your message will appear here.'}
$('mailText').oninput=mailPreview;
function integrations(){
 const box=$('providers');box.replaceChildren();
 for(const [id,label] of [['google','Google Calendar'],['microsoft','Microsoft Outlook']]){
  const linked=state.calendars.includes(id),subscribed=state.calendarLinks.includes(id);
  const card=make('article','');card.className='providerCard';
  const head=make('div','');head.className='providerHead';
  const mark=make('span',id==='google'?'31':'O');mark.className='providerMark '+id;
  const title=make('div','');title.append(make('strong',label),make('small',linked?'Connected via OAuth':subscribed?'Calendar link active':'Connect availability'));head.append(mark,title);card.append(head);
  if(linked||state.ready[id])card.append(button(linked?'Disconnect OAuth':'Sign in with '+label,async()=>{
   const r=await call(linked?'disconnect':'connect',{provider:id});if(r.url)location.assign(r.url);else{state=await call('admin');integrations()}
  }));
  if(subscribed)card.append(button('Disconnect calendar link',async()=>{await call('unlinkcalendar',{provider:id});state=await call('admin');integrations();feedback('Calendar link removed.')}));
  else{
   const exp=make('details','');exp.append(make('summary','Connect with a calendar link'));
   const hint=id==='google'?'Open your Google calendar settings. Under Integrate calendar, copy the secret address in iCal format.':'In Outlook on the web, open Calendar → Shared calendars. Publish the calendar and copy the ICS link.';
   const form=make('form',''),input=field('ICS link','url',''),status=make('output','');status.setAttribute('role','status');input.lastChild.required=true;input.lastChild.autocomplete='off';input.lastChild.placeholder='https://…';
   const submit=make('button','Connect calendar');form.append(make('p',hint),input,submit,status);
   form.onsubmit=async event=>{event.preventDefault();submit.disabled=true;status.textContent='Checking calendar…';try{await call('linkcalendar',{provider:id,url:input.lastChild.value});state=await call('admin');integrations();feedback(label+' connected. Busy times will be blocked.')}catch(err){status.textContent=err.message;submit.disabled=false}};
   exp.append(form);card.append(exp);
  }
  if(!linked&&!state.ready[id])card.append(make('small','OAuth sign-in is not configured.'));
  box.append(card);
 }
 $('smtp').textContent=state.ready.smtp?'SMTP configured. The mail worker processes queued messages.':'SMTP is not configured yet. Messages are queued for delivery.'}
async function openWorkspace(){state=await call('admin');const c=state.config;
 sessionStorage.setItem('blendbook-login',JSON.stringify({shop:$('shop').value,key:$('key').value}));$('gate').hidden=true;document.querySelector('main').hidden=false;$('logout').hidden=false;$('workspace').textContent=$('shop').value;
 for(const k of ['duration','windowSize','buffer','mailText'])$(k).value=c[k];for(const k of ['windows','showServices'])$(k).checked=c[k];toggle();
 $('serviceRows').replaceChildren();c.services.forEach(service);$('week').replaceChildren();days.forEach((d,i)=>weekDay(d,c.hours[i]));$('exceptions').replaceChildren();Object.entries({...c.overrides,...Object.fromEntries(c.closed.map(d=>[d,'']))}).sort().forEach(([date,h])=>exception(date,h));
 const theme=state.theme||{accent:'#294e39',background:'#ffffff',foreground:'#20362d',font:'inherit'};for(const k of ['accent','background','foreground','font'])$(k).value=theme[k];$('buttonLabel').value=c.buttonLabel||'Book appointment';$('successLabel').value=c.successLabel||'';publishedDraft=JSON.stringify(draft());updateEditor();mailPreview();
 const url=location.origin+'/book?bedrijf='+encodeURIComponent($('shop').value);$('booking').href=$('public').href=url;$('booking').textContent=url;$('public').textContent=url;
 $('embed').textContent='<blendbook-form bedrijf="'+$('shop').value+'"></blendbook-form><script src="'+location.origin+'/widget.js" defer></script>';
 $('dateline').textContent=new Date().toLocaleDateString('en-GB',{weekday:'long',day:'numeric',month:'long'});integrations();overview();nav(decodeURIComponent(location.hash.slice(1)));document.dispatchEvent(new Event('workspace-open'))}
$('login').onsubmit=e=>{e.preventDefault();openWorkspace().catch(err=>$('loginError').textContent=err.message)};
$('logout').onclick=()=>{sessionStorage.removeItem('blendbook-login');location.replace('/admin')};
function onSubmit(id,fn){$(id).onsubmit=async e=>{e.preventDefault();const b=e.submitter;if(b)b.disabled=true;try{await fn();}catch(err){feedback(err.message)}finally{if(b)b.disabled=false}}}
async function save(patch){state=await call('admin',{...state.config,...patch});overview();updateEditor();feedback('Changes saved.')}

onSubmit('hoursForm',()=>{const overrides={},closed=[];for(const row of $('exceptions').children){const [d,h]=row.querySelectorAll('input');if(!d.value||d.value in overrides||closed.includes(d.value))throw Error('Enter each override date only once.');if(h.value.trim())overrides[d.value]=h.value.trim();else closed.push(d.value)}
 return save({hours:weekValues(),overrides,closed,windows:$('windows').checked,windowSize:+$('windowSize').value,buffer:+$('buffer').value})});


for(const [id,enabled] of [['makeFeed',true],['stopFeed',false]])$(id).onclick=async()=>{try{const r=await call('feed',{enabled});$('feedUrl').hidden=!r.path;$('feedUrl').value=r.path?location.origin+r.path:'';feedback(enabled?'Private link created.':'Private link revoked.')}catch(e){feedback(e.message)}};
$('copyEmbed').onclick=async()=>{try{await navigator.clipboard.writeText($('embed').textContent);feedback('Embed code copied.')}catch{feedback('Select and copy the embed code.')}};
function openMove(b){moving=b;$('changeName').textContent=b.name+' · '+b.service;$('changeDay').min=today;$('changeDay').value='';$('changeTime').replaceChildren();$('changeStatus').textContent='';$('changeSubmit').disabled=true;$('edit').showModal()}
$('closeDialog').onclick=()=>$('edit').close();$('edit').onclose=()=>revision++;
$('changeDay').onchange=async()=>{const seq=++revision;$('changeSubmit').disabled=true;$('changeTime').replaceChildren();try{const index=state.config.showServices?state.config.services.findIndex(s=>s.name===moving.service):0;if(index<0)throw Error('The service has changed.');
 const slots=await call('slots?'+new URLSearchParams({day:$('changeDay').value,service:index}));if(seq!==revision)return;slots.forEach(s=>$('changeTime').add(new Option(s.label,s.start)));$('changeSubmit').disabled=!slots.length;$('changeStatus').textContent=slots.length?'':'No times available.'}catch(e){$('changeStatus').textContent=e.message}};
$('changeForm').onsubmit=async e=>{e.preventDefault();$('changeSubmit').disabled=true;try{await call('managemove',{ref:moving.ref,day:$('changeDay').value,start:+$('changeTime').value});$('edit').close();await reloadBookings();feedback('Appointment rescheduled.')}catch(e){$('changeStatus').textContent=e.message}finally{$('changeSubmit').disabled=false}};
const saved=sessionStorage.getItem('blendbook-login');if(saved){try{const login=JSON.parse(saved);$('shop').value=login.shop;$('key').value=login.key;openWorkspace().catch(e=>$('loginError').textContent=e.message)}catch{sessionStorage.removeItem('blendbook-login')}}

onSubmit('verifyForm',async()=>feedback((await call('verify',{email:$('verifyEmail').value})).message));
