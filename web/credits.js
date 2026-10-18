import {CONFIG} from './config.js';

export class Credits {
  constructor({audio,onFinish=()=>{}}) {
    this.audio=audio;this.onFinish=onFinish;this.active=false;this.paused=false;this.frame=0;this.revision=0;
    this.scroller=document.getElementById('credits-scroll');this.content=document.getElementById('credits-content');
    this.pauseButton=document.getElementById('credits-pause');this.error=document.getElementById('credits-error');
    this.reduced=matchMedia('(prefers-reduced-motion: reduce)');this.abort=new AbortController();
    const options={signal:this.abort.signal};
    this.pauseButton.addEventListener('click',()=>this.togglePause(),options);
    document.getElementById('credits-skip').addEventListener('click',()=>this.finish(),options);
    document.addEventListener('keydown',event=>{
      if(!this.active)return;
      if(event.key==='Escape'){event.preventDefault();event.stopPropagation();this.finish();return;}
      if(event.code==='Space'&&!event.target.closest('input,textarea,select,button,dialog,[contenteditable]')){
        event.preventDefault();event.stopPropagation();this.togglePause();
      }
    },options);
    document.addEventListener('visibilitychange',()=>{
      if(!this.active)return;
      if(document.hidden){this.wasPaused=this.paused;this.pause();}
      else if(this.wasPaused===false){this.wasPaused=undefined;this.resume();}
    },options);
    this.reduced.addEventListener('change',()=>{if(this.active){this.last=0;this.refreshMode();}},options);
    window.addEventListener('pagehide',event=>{if(!event.persisted)this.dispose();},options);
  }
  async start(){
    const revision=++this.revision;this.active=true;this.paused=false;this.finished=false;this.wasPaused=undefined;
    cancelAnimationFrame(this.frame);this.frame=0;this.last=0;this.error.hidden=true;
    try{
      if(!this.data){const response=await fetch(CONFIG.credits.url);if(!response.ok)throw new Error('Не удалось открыть титры.');this.data=await response.json();}
      if(!this.active||revision!==this.revision)return;
      const nodes=[];
      for(const block of this.data.blocks||[]){
        const node=document.createElement(block.type==='title'?'h1':block.type==='heading'?'h2':'p');
        node.className=`credits-block credits-${String(block.type).replace(/[^a-z]/g,'')}`;
        if(block.tone==='cyan'||block.tone==='green')node.dataset.tone=block.tone;
        if(block.speaker){const speaker=document.createElement('span');speaker.className='credits-speaker';speaker.textContent=block.speaker;node.append(speaker,document.createTextNode(String(block.text||'')));}
        else node.textContent=String(block.text||'');
        nodes.push(node);
      }
      this.content.replaceChildren(...nodes);this.scroller.scrollTop=0;this.audio.setWorld('credits');this.audio.setCreditsPaused(this.paused||document.hidden);
      await document.fonts?.ready;
      if(!this.active||revision!==this.revision)return;
      this.refreshMode();this.scroller.focus({preventScroll:true});
    }catch(error){if(this.active&&revision===this.revision){this.error.textContent='Текст титров недоступен. Нажмите «Пропустить», чтобы вернуться.';this.error.hidden=false;this.pause();}}
  }
  refreshMode(){
    this.scroller.classList.toggle('static-credits',this.reduced.matches);
    this.pauseButton.hidden=this.reduced.matches;this.updateButton();
    document.querySelector('.credits-hint').textContent=this.reduced.matches?'Прокрутите, чтобы прочитать · Escape — пропустить':'Пробел — пауза · Escape — пропустить';
    this.speed=Math.max(CONFIG.credits.minPixelsPerSecond,(this.scroller.scrollHeight-this.scroller.clientHeight)/(CONFIG.credits.targetDurationMs/1000));
    cancelAnimationFrame(this.frame);this.frame=0;
    if(this.active&&!this.paused&&!this.reduced.matches&&!document.hidden)this.frame=requestAnimationFrame(t=>this.tick(t));
  }
  updateButton(){this.pauseButton.textContent=this.paused?'Продолжить':'Пауза';this.pauseButton.setAttribute('aria-pressed',String(this.paused));}
  tick(now){
    if(!this.active||this.paused||this.reduced.matches||document.hidden){this.frame=0;return;}
    if(!this.last)this.last=now;
    const elapsed=Math.min(100,now-this.last);this.last=now;
    this.scroller.scrollTop+=this.speed*elapsed/1000;
    if(this.scroller.scrollTop+this.scroller.clientHeight>=this.scroller.scrollHeight-2){this.finish();return;}
    this.frame=requestAnimationFrame(t=>this.tick(t));
  }
  pause(){if(!this.active)return;this.paused=true;this.last=0;cancelAnimationFrame(this.frame);this.frame=0;this.audio.setCreditsPaused(true);this.updateButton();}
  resume(){if(!this.active)return;this.paused=false;this.last=0;this.audio.setCreditsPaused(false);this.refreshMode();}
  togglePause(){if(this.paused)this.resume();else this.pause();}
  stop({notify=false}={}){
    const wasActive=this.active;this.active=false;this.revision++;cancelAnimationFrame(this.frame);this.frame=0;this.last=0;
    this.audio.setCreditsPaused(true);if(notify&&wasActive)this.onFinish();
  }
  finish(){if(!this.active||this.finished)return;this.finished=true;this.stop({notify:true});}
  dispose(){this.stop();this.abort.abort();}
}
