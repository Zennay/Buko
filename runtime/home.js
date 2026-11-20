const examples=[
 {name:'Studio session',duration:45,price:'',accent:'#6c51b4',surface:'#ffffff',host:'Studio Lumen'},
 {name:'Discovery call',duration:30,price:'',accent:'#176e63',surface:'#fcfefc',host:'North Consulting'},
 {name:'Home consultation',duration:60,price:'',accent:'#955735',surface:'#fffdfa',host:'Fieldwork'}
];
const widget=document.querySelector('#demoWidget'),tabs=[...document.querySelectorAll('#demoThemes button')];
function showExample(index){
 const sample=examples[index];tabs.forEach((tab,i)=>tab.setAttribute('aria-pressed',String(i===index)));
 widget.renderPreview({previewHost:sample.host,services:[sample],duration:sample.duration,showServices:true,windows:index===2,theme:{accent:sample.accent,background:sample.surface,foreground:'#262728',buttonText:'#ffffff'},buttonLabel:'Confirm appointment',successLabel:'Preview complete. No appointment was booked.'});
}
tabs.forEach((tab,i)=>tab.onclick=()=>showExample(i));showExample(0);
