import {CONFIG} from './config.js';
const F = CONFIG.atmosphere, P = CONFIG.portal;
const BACKGROUND_WIDTH=480, BACKGROUND_HEIGHT=270;
const random = ([min,max]) => min+Math.random()*(max-min);
const canvas = (width=F.width,height=F.height) => {
  const node=document.createElement('canvas');node.width=width;node.height=height;return node;
};
const progress = (value,start,end) => Math.max(0,Math.min(1,(value-start)/(end-start)));
const readPreference=key=>{try{return localStorage.getItem(key);}catch{return null;}};
const writePreference=(key,value)=>{try{localStorage.setItem(key,value);}catch{/* Preferences remain available for this page. */}};
const rect = (ctx,color,x,y,w,h) => {ctx.fillStyle=color;ctx.fillRect(Math.round(x),Math.round(y),Math.round(w),Math.round(h));};

export class Worlds {
  constructor({onChange,audio}) {
    this.world='overworld';this.onChange=onChange;this.audio=audio;
    this.background=document.getElementById('landscape').getContext('2d');
    this.fx=document.getElementById('atmosphere').getContext('2d');
    this.portal=document.getElementById('portal-transition');
    this.portalCanvas=document.getElementById('portal-canvas');
    this.portalCanvas.width=P.gridWidth;this.portalCanvas.height=P.gridHeight;
    this.portalCtx=this.portalCanvas.getContext('2d');
    this.surface=canvas(P.gridWidth,P.gridHeight);this.surfaceCtx=this.surface.getContext('2d');
    for(const ctx of [this.background,this.fx,this.portalCtx,this.surfaceCtx])ctx.imageSmoothingEnabled=false;
    this.images={};this.particles=[];this.blocked=[];this.clock=0;this.last=0;
    this.frame=0;this.portalFrame=0;this.timerIds=[];this.abort=new AbortController();
    this.reduced=matchMedia('(prefers-reduced-motion: reduce)');
    this.motion=readPreference('decorative-motion')!=='off';
    const options={signal:this.abort.signal};
    document.getElementById('skip-transition').addEventListener('click',()=>this.finish(),options);
    document.addEventListener('visibilitychange',()=>{
      document.documentElement.classList.toggle('tab-hidden',document.hidden);
      if(document.hidden && this.transitioning)this.finish({assemble:false});
      this.refreshAnimation();
    },options);
    this.reduced.addEventListener('change',()=>this.refreshAnimation(),options);
    document.getElementById('motion-toggle').addEventListener('click',()=>{
      this.motion=!this.motion;writePreference('decorative-motion',this.motion?'on':'off');this.refreshAnimation();
    },options);
    window.addEventListener('resize',()=>{this.measureExclusions();this.fitPortal();},options);
    window.addEventListener('scroll',()=>this.measureExclusions(),{...options,passive:true});
    document.addEventListener('toggle',()=>this.measureExclusions(),{...options,capture:true});
    this.observer=new ResizeObserver(()=>this.measureExclusions());
    document.querySelectorAll(F.exclusions).forEach(el=>this.observer.observe(el));
    this.mutations=new MutationObserver(()=>{
      if(this.maskFrame)return;
      this.maskFrame=requestAnimationFrame(()=>{this.maskFrame=0;this.measureExclusions();});
    });
    this.mutations.observe(document.querySelector('main'),{childList:true,subtree:true,attributes:true,attributeFilter:['hidden','open','class']});
    // Keep the original composition, averaging its fine textures into a calmer pixel grid.
    this.ready=Promise.all(['overworld','nether','end'].map(world=>new Promise(resolve=>{
      const img=new Image();
      img.onload=()=>{this.images[world]=img;if(world==='nether')this.prepareLava(img);if(world===this.world){this.backgroundWorld=null;this.drawBackground();}resolve();};
      img.onerror=()=>resolve();
      img.src=new URL('./assets/worlds/'+world+'.png',import.meta.url).href;
    })));
    this.theme=readPreference('forte-theme')==='light'?'light':'dark';
    const themeButton=document.getElementById('theme-toggle');
    const applyTheme=()=>{document.documentElement.dataset.theme=this.theme;themeButton?.setAttribute('aria-label',this.theme==='light'?'Включить тёмную тему':'Включить светлую тему');themeButton?.setAttribute('aria-pressed',String(this.theme==='light'));};
    applyTheme();themeButton?.addEventListener('click',()=>{this.theme=this.theme==='light'?'dark':'light';writePreference('forte-theme',this.theme);applyTheme();},options);
    this.refreshAnimation();this.fitPortal();this.measureExclusions();
    window.addEventListener('pagehide',event=>{if(!event.persisted)this.dispose();},options);
    window.addEventListener('pageshow',event=>{if(event.persisted){this.refreshAnimation();this.measureExclusions();}},options);
  }
  get animated(){return this.motion && !this.reduced.matches;}
  refreshAnimation(){
    cancelAnimationFrame(this.frame);this.frame=0;this.last=0;
    document.documentElement.classList.toggle('motion-off',!this.animated);
    const button=document.getElementById('motion-toggle');
    button.setAttribute('aria-pressed',String(!this.motion));button.disabled=this.reduced.matches;
    button.setAttribute('aria-label',this.reduced.matches?'Движение отключено настройкой устройства':this.motion?'Отключить декоративное движение':'Включить декоративное движение');
    this.particles=[];this.resetSpawns();this.fx.clearRect(0,0,F.width,F.height);this.drawBackground();
    if(!this.animated && this.transitioning)this.finish({assemble:false});
    if(this.animated && !document.hidden)this.frame=requestAnimationFrame(t=>this.tick(t));
  }
  drawBackground(){
    const ctx=this.background,image=this.images[this.world];
    const key=image?this.world:'pending-'+this.world;
    if(this.backgroundWorld===key)return;
    this.backgroundWorld=key;
    ctx.canvas.width=BACKGROUND_WIDTH;ctx.canvas.height=BACKGROUND_HEIGHT;
    if(image){
      // Downsample once per scene; CSS scales this cached canvas with crisp edges.
      // Only this static image uses smoothing. Particle and portal grids stay independent.
      ctx.imageSmoothingEnabled=true;ctx.imageSmoothingQuality='high';
      ctx.drawImage(image,0,0,BACKGROUND_WIDTH,BACKGROUND_HEIGHT);
      ctx.imageSmoothingEnabled=false;
    }else{
      rect(ctx,this.world==='overworld'?'#91a7a2':this.world==='nether'?'#260e16':'#100d1b',0,0,BACKGROUND_WIDTH,BACKGROUND_HEIGHT);
    }
  }
  prepareLava(img){
    const ctx=canvas().getContext('2d',{willReadFrequently:true});
    ctx.imageSmoothingEnabled=false;ctx.drawImage(img,0,0,F.width,F.height);
    const data=ctx.getImageData(0,0,F.width,F.height).data;this.lava=[];
    for(let y=F.lavaMinimumY;y<F.height;y+=2)for(let x=0;x<F.width;x+=2){
      const i=(y*F.width+x)*4;
      if(data[i]>180 && data[i+1]>85 && data[i+2]<85)this.lava.push({x,y});
    }
  }
  measureExclusions(){
    const scale=Math.max(innerWidth/F.width,innerHeight/F.height);
    const ox=(innerWidth-F.width*scale)/2,oy=(innerHeight-F.height*scale)/2,pad=F.exclusionPadding;
    this.view={scale,ox,oy,left:-ox/scale,right:(innerWidth-ox)/scale,top:-oy/scale,bottom:(innerHeight-oy)/scale};
    this.blocked=[...document.querySelectorAll(F.exclusions)].filter(el=>el.getClientRects().length).map(el=>{
      const r=el.getBoundingClientRect();return {x:(r.left-pad-ox)/scale,y:(r.top-pad-oy)/scale,w:(r.width+pad*2)/scale,h:(r.height+pad*2)/scale};
    });
    this.clipEffects();
  }
  clipEffects(){for(const r of this.blocked)this.fx.clearRect(Math.floor(r.x),Math.floor(r.y),Math.ceil(r.w)+1,Math.ceil(r.h)+1);}
  isBlocked(x,y){return this.blocked.some(r=>x>=r.x&&x<=r.x+r.w&&y>=r.y&&y<=r.y+r.h);}
  resetSpawns(){this.next={};for(const type of ['leaf','ash','spark','end'])this.next[type]=this.clock+random(F[type].intervalMs);}
  spawn(type){
    const config=F[type],mobile=innerWidth<=F.mobileWidth,max=mobile?config.mobileMax:config.max;
    if(this.particles.filter(p=>p.type===type).length>=max)return;
    const v=this.view;if(!v)return;
    let x,y;
    if(type==='leaf'){
      // Visible crown edges only; never emit in the middle of the sky.
      const regions=[{x:[68,132],y:[90,158]},{x:[555,633],y:[100,176]}].filter(r=>r.x[1]>v.left&&r.x[0]<v.right);
      if(!regions.length)return;
      const region=regions[Math.floor(Math.random()*regions.length)];
      x=random([Math.max(v.left+2,region.x[0]),Math.min(v.right-2,region.x[1])]);y=random(region.y);
    }else if(type==='spark'){
      const points=(this.lava||[]).filter(point=>point.x>v.left&&point.x<v.right&&point.y>v.top&&point.y<v.bottom&&!this.isBlocked(point.x,point.y));
      if(!points.length)return;({x,y}=points[Math.floor(Math.random()*points.length)]);
    }
    else{
      for(let attempt=0;attempt<F.spawnAttempts;attempt++){
        x=random([v.left+2,v.right-2]);y=random([Math.max(v.top+4,55),Math.min(v.bottom-5,340)]);
        if(!this.isBlocked(x,y))break;
      }
    }
    if(this.isBlocked(x,y))return;
    this.particles.push({type,x,y,born:this.clock,life:random(config.lifeMs),phase:Math.random()*Math.PI*2,drift:random([-5,5])});
  }
  tick(t){
    if(document.hidden||!this.animated)return;
    if(!this.last)this.last=t;
    const elapsed=t-this.last;
    if(elapsed>=F.frameMs){
      this.clock+=Math.min(elapsed,200);this.last=t;
      this.drawBackground();this.drawEffects();
    }
    this.frame=requestAnimationFrame(next=>this.tick(next));
  }
  drawEffects(){
    const ctx=this.fx;ctx.clearRect(0,0,F.width,F.height);
    if(!this.animated||document.hidden)return;
    for(const type of this.world==='overworld'?['leaf']:this.world==='nether'?['ash','spark']:this.world==='end'?['end']:[])if(this.clock>=this.next[type]){
      this.next[type]=this.clock+random(F[type].intervalMs);this.spawn(type);
    }
    this.particles=this.particles.filter(p=>this.clock-p.born<p.life);
    for(const p of this.particles){
      const age=(this.clock-p.born)/p.life;
      const x=Math.round(p.x+p.drift*age+Math.sin(age*5+p.phase)*(p.type==='leaf'?2:1));
      const y=Math.round(p.y+(p.type==='leaf'?30:p.type==='spark'?-24:-12)*age);
      ctx.globalAlpha=Math.min(1,age*7,(1-age)*5)*(p.type==='leaf'?.8:p.type==='spark'?.55:.45);
      if(p.type==='leaf'){
        const pose=Math.floor(age*9)%4;ctx.fillStyle='#4d7936';
        if(pose%2){ctx.fillRect(x,y,1,3);ctx.fillStyle='#96ad45';ctx.fillRect(x+1,y+1,1,1);}
        else{ctx.fillRect(x,y,3,2);ctx.fillStyle='#96ad45';ctx.fillRect(x+(pose===0?0:2),y,1,1);}
      }else{ctx.fillStyle=p.type==='spark'?'#e9a15c':p.type==='end'?'#a98ccd':'#b4aa9b';ctx.fillRect(x,y,1,p.type==='spark'?2:1);}
    }
    ctx.globalAlpha=1;
    this.clipEffects();
  }
  setWorld(world){
    this.world=world;this.particles=[];this.resetSpawns();
    document.documentElement.dataset.world=world;
    document.getElementById('welcome-scene').hidden=world!=='overworld';
    document.getElementById('workspace-scene').hidden=world!=='nether';
    document.getElementById('archive-scene').hidden=world!=='end';
    document.getElementById('credits-scene').hidden=world!=='credits';
    document.getElementById('workspace-scene').classList.remove('upload-assembling');
    document.getElementById('workspace-scene').toggleAttribute('data-arriving',world==='nether'&&this.transitioning&&!this.uploadAssembled);
    document.getElementById('scene-name').textContent=({nether:'Анализ видео',end:'История',credits:'Команда',overworld:'Приветствие'})[world];
    document.getElementById('world-label').textContent=world.toUpperCase();
    const back=document.getElementById('back-button');
    back.disabled=world==='overworld'||this.transitioning;
    const backLabel=world==='end'?'Назад в Nether':'Назад в Overworld';
    back.setAttribute('aria-label',backLabel);back.title=backLabel;
    document.querySelector('meta[name=theme-color]').content=world==='overworld'?'#91a7a2':world==='nether'?'#160e15':'#100d1b';
    for(const [id,value] of [['nav-home','overworld'],['nav-analysis','nether'],['nav-history','end']])document.getElementById(id)?.setAttribute('aria-current',value===world?'page':'false');
    this.drawBackground();this.measureExclusions();this.drawEffects();this.onChange(world);this.audio.setWorld(world);
  }
  assembleUpload(){
    if(this.world!=='nether'||this.uploadAssembled)return;
    this.uploadAssembled=true;
    if(!this.animated||document.hidden)return;
    const workspace=document.getElementById('workspace-scene');
    workspace.classList.remove('upload-assembling');void workspace.offsetWidth;workspace.classList.add('upload-assembling');
    [600,850,1100].forEach(delay=>this.timerIds.push(setTimeout(()=>{if(!this.transitioning && !document.hidden)this.audio.play('landing');},delay)));
  }
  fitPortal(){
    // An integer pixel scale with a centered crop keeps every grid cell crisp.
    const scale=Math.ceil(Math.max(innerWidth/P.gridWidth,innerHeight/P.gridHeight));
    this.portalCanvas.style.width=P.gridWidth*scale+'px';this.portalCanvas.style.height=P.gridHeight*scale+'px';
  }
  go(world){
    if(!['overworld','nether','end','credits'].includes(world))return Promise.reject(new Error('Неизвестная сцена'));
    if(this.transitioning && this.target===world)return this.transitionPromise;
    if(this.transitioning)this.finish({assemble:false});
    if(this.world===world)return Promise.resolve();
    this.timerIds.forEach(clearTimeout);this.timerIds=[];
    this.target=world;this.endTransition=world==='end'||this.world==='end'||world==='credits'||this.world==='credits';this.transitioning=true;this.portal.hidden=false;this.portal.className='portal-transition to-'+world;
    this.portal.dataset.phase='reveal';this.fitPortal();
    this.calm=!this.animated;this.start=performance.now();
    if(!this.calm && this.world==='overworld')document.getElementById('intro-composition').classList.add('intro-leaving');
    document.documentElement.style.setProperty('--sign-exit-ms',P.signExitMs+'ms');
    document.getElementById('back-button').disabled=true;
    this.audio.beginPortal({start:this.start,target:world,calm:this.calm});
    this.transitionPromise=new Promise(resolve=>{this.resolveTransition=resolve;});
    this.portalFrame=requestAnimationFrame(t=>this.stepPortal(t));
    return this.transitionPromise;
  }
  stepPortal(t){
    if(!this.transitioning)return;
    const elapsed=t-this.start,duration=this.calm?P.calmDurationMs:this.endTransition?P.endDurationMs:P.durationMs;
    this.renderPortal(elapsed);
    const switchAt=this.calm?duration/2:this.endTransition?P.endSwitchMs:P.switchMs;
    if(elapsed>=switchAt && this.world!==this.target)this.setWorld(this.target);
    if(elapsed>=duration){this.finish();return;}
    this.portalFrame=requestAnimationFrame(next=>this.stepPortal(next));
  }
  renderPortal(ms){
    const ctx=this.portalCtx,W=P.gridWidth,H=P.gridHeight;
    ctx.clearRect(0,0,W,H);
    if(this.calm){
      const p=Math.min(1,ms/P.calmDurationMs);ctx.globalAlpha=Math.sin(p*Math.PI)*.85;
      ctx.fillStyle=this.endTransition?'#100d1b':this.target==='nether'?'#532133':'#70bdd3';ctx.fillRect(0,0,W,H);ctx.globalAlpha=1;return;
    }
    if(this.endTransition){
      const p=Math.min(1,ms/P.endDurationMs);ctx.globalAlpha=p<.5?Math.min(1,p*4):Math.max(0,2-p*2);rect(ctx,'#100d1b',0,0,W,H);
      if(p<.5){const scale=1+p*5,x=W/2,y=H/2,w=56*scale,h=17*scale;
        ctx.globalAlpha=1;rect(ctx,'#555c40',x-w/2-5,y-h/2-5,w+10,h+10);rect(ctx,'#d0cf91',x-w/2-3,y-h/2-3,w+6,h+6);rect(ctx,'#090b17',x-w/2,y-h/2,w,h);
        for(let i=0;i<6;i++){const bx=x-w/2+i*w/5;rect(ctx,'#365d50',bx-2,y-h/2-5,5,4);rect(ctx,'#82a579',bx,y-h/2-4,2,2);rect(ctx,'#365d50',bx-2,y+h/2+1,5,4);}
        for(let i=0;i<12;i++)rect(ctx,i%2?'#70618d':'#b7abc6',x-w/2+4+(i*17)%Math.max(1,w-8),y-h/2+2+(i*7)%Math.max(1,h-4),1,1);
      }ctx.globalAlpha=1;return;
    }
    const stage=ms<P.signExitMs?'reveal':ms<P.approachEndMs?'approach':ms<P.crossingEndMs?'crossing':ms<P.revealMs?'destination':'exit';
    this.portal.dataset.phase=stage;
    const blend=progress(ms,P.crossingEndMs,P.revealMs),fade=1-progress(ms,P.revealMs,P.durationMs);
    const purple=[[45,20,76],[66,28,101],[91,38,126],[116,45,151],[142,57,168],[165,76,182],[123,55,154],[76,28,114]];
    const destination=this.target==='nether'?[[43,13,25],[68,21,31],[97,31,35],[125,44,37],[151,63,40],[174,84,49],[126,45,40],[77,24,32]]
      :[[37,101,137],[48,124,158],[66,147,180],[87,168,196],[110,187,208],[141,202,216],[97,173,199],[59,133,169]];
    const palette=purple.map((rgb,i)=>'rgb('+rgb.map((c,j)=>Math.round(c+(destination[i][j]-c)*blend)).join(',')+')');
    const sc=this.surfaceCtx,phase=Math.floor(ms/80)*.12;
    // Coherent stepped waves: neighbouring cells share bands, no random fullscreen noise.
    for(let y=0;y<H;y+=4)for(let x=0;x<W;x+=4){
      const dx=x-W/2,dy=(y-H/2)*1.3,r=Math.hypot(dx,dy);
      const wave=Math.sin(r*.075-phase*2+Math.sin(Math.atan2(dy,dx)*3+phase)*.65)+Math.sin(x*.035+y*.022-phase)*.45;
      const index=Math.max(0,Math.min(7,Math.floor((wave+1.45)/2.9*8)));
      sc.fillStyle=palette[index];sc.fillRect(x,y,4,4);
    }
    ctx.globalAlpha=fade*progress(ms,0,120);
    if(ms<P.approachEndMs){
      const p=progress(ms,P.signExitMs,P.approachEndMs),scale=1+p*p*7;
      const w=Math.round(64*scale),h=Math.round(112*scale),rim=Math.round(10*scale);
      const x=Math.round((W-w)/2),y=Math.round((H-h)/2);
      ctx.fillStyle='#181221';ctx.fillRect(x-rim,y-rim,w+rim*2,h+rim*2);
      for(let by=y-rim;by<y+h+rim;by+=8)for(let bx=x-rim;bx<x+w+rim;bx+=8){
        ctx.fillStyle=(Math.floor(bx/8)+Math.floor(by/8))%3?'#281c36':'#392546';ctx.fillRect(bx,by,7,7);
      }
      ctx.save();ctx.beginPath();ctx.rect(x,y,w,h);ctx.clip();ctx.drawImage(this.surface,0,0);ctx.restore();
      for(let i=0;i<5;i++){const angle=i*1.3+phase;ctx.fillStyle='#af69c9';ctx.fillRect(Math.round(W/2+Math.cos(angle)*(w/2+12)),Math.round(H/2+Math.sin(angle)*(h/2+9)),2,2);}
    }else ctx.drawImage(this.surface,0,0);
    ctx.globalAlpha=1;
  }
  finish({assemble=true}={}){
    if(!this.transitioning)return;
    cancelAnimationFrame(this.portalFrame);this.portalFrame=0;
    if(this.world!==this.target)this.setWorld(this.target);
    this.portal.hidden=true;this.portal.dataset.phase='idle';this.portalCtx.clearRect(0,0,P.gridWidth,P.gridHeight);
    document.getElementById('intro-composition').classList.remove('intro-leaving');
    this.transitioning=false;document.getElementById('back-button').disabled=this.world==='overworld';
    document.getElementById('workspace-scene').removeAttribute('data-arriving');
    this.audio.finishPortal();if(assemble)this.assembleUpload();
    this.resolveTransition?.();this.resolveTransition=null;this.measureExclusions();
  }
  dispose(){
    cancelAnimationFrame(this.frame);cancelAnimationFrame(this.portalFrame);
    cancelAnimationFrame(this.maskFrame);this.timerIds.forEach(clearTimeout);this.abort.abort();this.observer.disconnect();this.mutations.disconnect();this.particles=[];
  }
}

