const day=document.querySelector('#day'), times=document.querySelector('#times'), preview=document.querySelector('#preview');
for(let i=1;i<=5;i++){const d=new Date();d.setDate(d.getDate()+i);day.add(new Option(d.toLocaleDateString('nl-NL',{weekday:'long',day:'numeric',month:'long'})))}
function display(){times.replaceChildren();preview.textContent='Kies een tijd voor het voorbeeld.';
for(const time of (day.selectedIndex%2?['10:00','11:30','15:00']:['09:00','10:30','14:00'])){const b=document.createElement('button');b.className='soft';b.textContent=time;b.onclick=()=>{for(const t of times.children)t.setAttribute('aria-pressed',String(t===b));preview.textContent='Voorbeeldafspraak · '+day.value+' om '+time};times.append(b)}}
day.onchange=display;display();document.querySelector('#paint').oninput=e=>document.querySelector('#demo').style.setProperty('--green',e.target.value);
