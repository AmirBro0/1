import {CONFIG} from './config.js';
const A = CONFIG.audio;
const clamp = value => Math.max(0, Math.min(1, value));
const readPreference=key=>{try{return localStorage.getItem(key);}catch{return null;}};
const writePreference=(key,value)=>{try{localStorage.setItem(key,value);}catch{/* Sound still works when browser storage is blocked. */}};

export class AudioManager {
  constructor() {
    this.enabled = readPreference('site-sound') === 'on';
    this.unlocked = false; this.context = null; this.world = 'overworld'; this.ducked = false;
    this.music = new Map(); this.buffers = new Map(); this.active = new Set();
    this.abort = new AbortController(); this.frame = 0; this.portal = null; this.soundRevision = 0;
    const saved = readPreference('site-music-volume');
    this.userVolume = saved !== null && Number.isFinite(+saved) ? clamp(+saved) : A.musicVolume;
    this.button = document.getElementById('sound-toggle');
    this.buttons = [this.button, document.getElementById('portal-sound-toggle'), document.getElementById('credits-sound-toggle')].filter(Boolean); this.updateButton();
    const options = {signal: this.abort.signal};
    this.buttons.forEach(button => button.addEventListener('click', () => this.setEnabled(!this.enabled), options));
    const gesture = () => {if(this.enabled)this.unlock();};
    document.addEventListener('pointerdown', gesture, {...options, passive: true});
    document.addEventListener('keydown', gesture, options);
    document.addEventListener('visibilitychange', () => {
      if(document.hidden)this.stopPlaying();
      else if(this.enabled && this.unlocked)this.resumeMusic(A.incomingFadeMs);
    }, options);
    window.addEventListener('pagehide', event => {if(!event.persisted)this.dispose();}, options);
  }
  updateButton() {
    for(const button of this.buttons) {
      button.setAttribute('aria-pressed', String(this.enabled));
      button.setAttribute('aria-label', this.enabled ? 'Выключить звуки сайта' : 'Включить звуки сайта');
      button.title = this.enabled ? 'Звуки сайта: включены' : 'Звуки сайта: выключены';
      button.querySelector('use').setAttribute('href', this.enabled ? '#i-sound' : '#i-muted');
    }
  }
  async unlock() {
    if(this.disposed)return;
    const wasUnlocked = this.unlocked;
    if(!this.context) {
      const Context = window.AudioContext || window.webkitAudioContext;
      if(!Context)return;
      try {this.context = new Context();}catch{return;}
    }
    try {await this.context.resume(); this.unlocked = this.context.state === 'running';}
    catch {return;}
    if(this.enabled && this.unlocked && (!wasUnlocked || this.music.get(this.world)?.element.paused))
      this.resumeMusic(A.firstFadeMs);
    if(this.localSounds?.has('portal'))this.getBuffer('portal').catch(() => {});
  }
  async setEnabled(value) {
    this.enabled = value; writePreference('site-sound', value ? 'on' : 'off'); this.updateButton();
    if(!value) {this.stopPlaying(); return;}
    await this.unlock();
    if(this.enabled)this.resumeMusic(A.firstFadeMs);
  }
  level(world) {
    const track = A.tracks[world];
    // Per-world ceilings preserve a quieter saved preference without multiplying
    // the requested End/credits level by the default music level a second time.
    const base = Math.min(this.userVolume, track?.volume ?? this.userVolume) * (track?.balance ?? 1);
    return this.ducked ? base * A.musicDuckMultiplier : base;
  }
  getTrack(world) {
    if(!A.tracks[world]?.url)return null;
    if(!this.music.has(world)) {
      const element = document.createElement('audio');
      // Music has a single volume stage, the media element; no music GainNode.
      element.volume = 0; element.loop = true; element.preload = 'none'; element.hidden = true;
      element.dataset.world = world; element.setAttribute('aria-hidden', 'true');
      const entry = {element, level: 0, envelope: null, request: 0, unavailable: false, started: false};
      element.addEventListener('error', () => {
        entry.unavailable = true; entry.envelope = null; entry.level = 0;
        element.dataset.unavailable = 'true'; element.volume = 0; element.pause();
      });
      element.src = A.tracks[world].url; document.body.append(element); this.music.set(world, entry);
    }
    return this.music.get(world);
  }
  fade(entry, target, duration, pause = false) {
    entry.envelope = {from: entry.level, to: clamp(target), start: performance.now(), duration, pause};
    this.ensureMixer();
  }
  ensureMixer() {if(!this.frame && !document.hidden && !this.disposed)this.frame = requestAnimationFrame(t => this.mix(t));}
  mix(now) {
    this.frame = 0; let running = false;
    for(const entry of this.music.values()) {
      const {element} = entry, envelope = entry.envelope;
      if(envelope) {
        const progress = Math.min(1, (now-envelope.start)/envelope.duration);
        entry.level = envelope.from+(envelope.to-envelope.from)*progress;
        if(progress === 1) {entry.envelope = null; if(envelope.pause)element.pause();}
      }
      let edge = 1;
      if(Number.isFinite(element.duration) && element.duration > 1) {
        const seconds = A.loopEdgeMs/1000;
        edge = Math.min(1, element.currentTime/seconds, (element.duration-element.currentTime)/seconds);
      }
      element.volume = this.enabled && !document.hidden ? clamp(entry.level*Math.max(0, edge)) : 0;
      running ||= !element.paused || !!entry.envelope;
    }
    if(running)this.ensureMixer();
  }
  async resumeMusic(duration = A.incomingFadeMs) {
    if(!this.enabled || !this.unlocked || document.hidden || this.disposed || (this.world === 'credits' && this.creditsPaused))return;
    if(this.portal && this.world !== this.portal.target)return;
    const entry = this.getTrack(this.world);
    if(!entry || entry.unavailable)return;
    const request = ++entry.request;
    if(entry.element.paused) {entry.level = 0; entry.element.volume = 0;}
    try {
      await entry.element.play();
      if(request !== entry.request)return;
      if(!this.enabled || document.hidden || this.world !== entry.element.dataset.world) {
        entry.element.volume = 0; entry.element.pause(); return;
      }
      this.fade(entry, this.level(this.world), entry.started ? duration : A.firstFadeMs);
      entry.started = true;
    } catch {/* Autoplay can be retried on another gesture using the same element. */}
  }
  setWorld(world) {
    this.world = world;
    if(world !== 'credits')this.creditsPaused = false;
    for(const [name, entry] of this.music)if(name !== world) {
      ++entry.request; this.fade(entry, 0, A.outgoingFadeMs, true);
    }
    this.resumeMusic();
  }
  setCreditsPaused(paused) {
    this.creditsPaused = paused;
    if(this.world !== 'credits')return;
    if(paused)this.stopPlaying();else this.resumeMusic();
  }
  duck(value) {
    this.ducked = value;
    const entry = this.music.get(this.world);
    if(entry && this.enabled && !entry.element.paused && (!this.portal || this.world === this.portal.target))
      this.fade(entry, this.level(this.world), value ? A.duckFadeMs : A.restoreFadeMs);
  }
  stopPlaying() {
    ++this.soundRevision; cancelAnimationFrame(this.frame); this.frame = 0;
    for(const entry of this.music.values()) {
      ++entry.request; entry.envelope = null; entry.level = 0; entry.element.volume = 0; entry.element.pause();
    }
    for(const record of [...this.active])this.stopNode(record, 0);
  }
  async useLocalPack(manifestUrl) {
    if(!manifestUrl || this.packUrl === manifestUrl)return;
    this.packUrl = manifestUrl;
    try {
      const response = await fetch(manifestUrl); if(!response.ok)return;
      const manifest = await response.json(), base = manifestUrl.slice(0, manifestUrl.lastIndexOf('/')+1);
      const mapping = {button_click: 'click', portal_travel: 'portal', soft_block_landing: 'landing', analysis_complete: 'complete'};
      this.localSounds = new Map(manifest.files.filter(f => f.kind === 'sound').map(f => [mapping[f.role], {...f, url: base+f.local_path}]));
      const textures = {oak_planks: '--wood', nether_bricks: '--brick', obsidian: '--obsidian'};
      for(const file of manifest.files)if(textures[file.name])document.documentElement.style.setProperty(textures[file.name], 'url("'+base+file.local_path+'")');
      if(this.context)await this.getBuffer('portal');
    } catch {/* Optional private assets never block the service. */}
  }
  getBuffer(name) {
    if(!this.buffers.has(name))this.buffers.set(name, (async () => {
      const asset = this.localSounds?.get(name);
      if(!asset || !this.context)throw new Error('No local sound');
      const response = await fetch(asset.url); if(!response.ok)throw new Error('No local sound');
      return this.context.decodeAudioData(await response.arrayBuffer());
    })());
    return this.buffers.get(name);
  }
  connect(source, channel) {
    const gain = this.context.createGain(); gain.gain.value = 0;
    source.connect(gain).connect(this.context.destination);
    const record = {source, gain, channel}; this.active.add(record);
    source.onended = () => {this.active.delete(record); source.disconnect(); gain.disconnect();};
    return record;
  }
  stopNode(record, seconds) {
    const now = this.context.currentTime;
    record.gain.gain.cancelScheduledValues(now);
    if(seconds) {
      record.gain.gain.setValueAtTime(record.gain.gain.value, now);
      record.gain.gain.linearRampToValueAtTime(0, now+seconds);
    } else record.gain.gain.setValueAtTime(0, now);
    try {record.source.stop(now+seconds);} catch {}
  }
  async play(name) {
    if(name === 'portal' || !this.enabled || !this.unlocked || document.hidden || !this.context)return;
    const revision = this.soundRevision;
    try {
      if(this.localSounds?.has(name)) {
        const buffer = await this.getBuffer(name);
        if(!this.enabled || document.hidden || revision !== this.soundRevision)return;
        const source = this.context.createBufferSource(); source.buffer = buffer;
        const {gain} = this.connect(source, 'ui'), now = this.context.currentTime;
        const duration = Math.min(buffer.duration, (name === 'complete' ? A.ui.completeDurationMs : A.ui.durationMs)/1000);
        gain.gain.setValueAtTime(0, now); gain.gain.linearRampToValueAtTime(A.uiVolume, now+A.ui.fadeInMs/1000);
        gain.gain.setValueAtTime(A.uiVolume, now+duration-A.ui.fadeOutMs/1000); gain.gain.linearRampToValueAtTime(0, now+duration);
        source.start(now, 0, duration); return;
      }
    } catch {/* Generated quiet fallback remains replaceable. */}
    if(!this.enabled || document.hidden || revision !== this.soundRevision)return;
    const notes = name === 'complete' ? [523,659,784] : name === 'landing' ? [95] : [380];
    notes.forEach((frequency, i) => {
      const source = this.context.createOscillator(); source.type = 'square'; source.frequency.value = frequency;
      const {gain} = this.connect(source, 'ui'), start = this.context.currentTime+i*A.ui.noteSpacingMs/1000;
      gain.gain.setValueAtTime(0, start); gain.gain.linearRampToValueAtTime(A.uiVolume*A.ui.fallbackGain, start+A.ui.fallbackAttackMs/1000);
      gain.gain.exponentialRampToValueAtTime(.0001, start+A.ui.fallbackDurationMs/1000); source.start(start); source.stop(start+(A.ui.fallbackDurationMs+20)/1000);
    });
  }
  beginPortal({start, target, calm}) {
    this.endPortal(); this.portal = {start, target}; ++this.soundRevision;
    for(const entry of this.music.values()) {++entry.request; this.fade(entry, 0, A.outgoingFadeMs, true);}
    if(calm || !this.enabled || !this.unlocked || document.hidden || !this.context)return;
    const timeline = this.portal;
    const origin = this.context.currentTime+(start-performance.now())/1000;
    const hum = this.context.createOscillator(); hum.type = 'triangle'; hum.frequency.value = 83;
    const {gain} = this.connect(hum, 'portal');
    gain.gain.setValueAtTime(0, origin+A.portal.humStartMs/1000); gain.gain.linearRampToValueAtTime(A.portalVolume*A.portal.humApproachGain, origin+A.portal.approachMs/1000);
    gain.gain.linearRampToValueAtTime(A.portalVolume*A.portal.humPeakGain, origin+A.portal.crossingMs/1000); gain.gain.linearRampToValueAtTime(0, origin+A.portal.tailEndMs/1000);
    hum.start(Math.max(this.context.currentTime, origin+A.portal.humStartMs/1000)); hum.stop(origin+(A.portal.tailEndMs+20)/1000);
    if(this.localSounds?.has('portal')) {
      this.getBuffer('portal').then(buffer => {
        if(this.portal !== timeline || !this.enabled || document.hidden)return;
        const when = origin+A.portal.startMs/1000;
        if(this.context.currentTime > when+.06)return;
        const source = this.context.createBufferSource(); source.buffer = buffer;
        const {gain} = this.connect(source, 'portal'), peak = A.portalVolume*A.portal.assetAttenuation;
        gain.gain.setValueAtTime(0, when); gain.gain.linearRampToValueAtTime(peak*A.portal.assetApproachGain, when+A.portal.assetFadeInMs/1000);
        gain.gain.linearRampToValueAtTime(peak, origin+A.portal.crossingMs/1000);
        gain.gain.linearRampToValueAtTime(peak*A.portal.assetTailGain, when+A.portal.assetTailStartMs/1000);
        gain.gain.linearRampToValueAtTime(0, when+A.portal.durationSeconds);
        source.start(when, A.portal.offsetSeconds, A.portal.durationSeconds);
      }).catch(() => {});
    } else {
      const accent = this.context.createOscillator(); accent.type = 'triangle'; accent.frequency.value = 196;
      const {gain} = this.connect(accent, 'portal'), when = origin+A.portal.accentStartMs/1000;
      gain.gain.setValueAtTime(0, when); gain.gain.linearRampToValueAtTime(A.portalVolume*A.portal.fallbackAccentGain, origin+A.portal.crossingMs/1000);
      gain.gain.exponentialRampToValueAtTime(.0001, origin+A.portal.tailEndMs/1000);
      accent.start(when); accent.stop(origin+A.portal.tailEndMs/1000);
    }
  }
  endPortal() {
    this.portal = null;
    for(const record of [...this.active])if(record.channel === 'portal')this.stopNode(record, A.skipTailMs/1000);
  }
  finishPortal() {
    this.endPortal();
    if(!this.music.get(this.world) || this.music.get(this.world).element.paused)this.resumeMusic(A.incomingFadeMs);
  }
  dispose() {
    this.disposed = true; this.stopPlaying(); this.abort.abort();
    for(const entry of this.music.values()) {entry.element.removeAttribute('src'); entry.element.load(); entry.element.remove();}
    this.music.clear(); this.portal=null;if(this.context&&this.context.state!=='closed')this.context.close().catch(()=>{});
  }
}

