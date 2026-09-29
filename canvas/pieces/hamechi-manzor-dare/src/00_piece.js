'use strict';
/* ============================================================
   HAMECHI MANZOR DARE — همه‌چی منظور داره
   a kaleidophone piece — Sep The Concept
   one file. no dependencies. drop the track on it.
   modes:  (live)            click → paranoia drone, or drop a wav
           ?render=1&w=&h=&seed=   deterministic, driven via __frame()
           ?cover=1&size=3000      still cover generator
   ============================================================ */
const Q = new URLSearchParams(location.search);
const RENDER = Q.get('render')==='1';
const COVER  = Q.get('cover')==='1';
const SEED   = parseInt(Q.get('seed')||'137',10);

/* ---------- deterministic RNG + noise ---------- */
function mulberry32(a){return function(){a|=0;a=a+0x6D2B79F5|0;let t=Math.imul(a^a>>>15,1|a);
  t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296;}}
let R = mulberry32(SEED);
function hashN(n){const s=Math.sin(n)*43758.5453123;return s-Math.floor(s);}
function noise1(x){const i=Math.floor(x),f=x-i,u=f*f*(3-2*f);return hashN(i)*(1-u)+hashN(i+1)*u;}
function snz(x){return noise1(x)*2-1;}

/* ---------- palette ---------- */
const BG='#060505', BONE='#e9e4d8', BONE_D='#151312';
const EMBER=[255,74,29], EMBER2=[255,155,61], HOT=[255,243,224];

/* ---------- canvas ---------- */
const cv=document.getElementById('cv');
const ctx=cv.getContext('2d');
let W=0,H=0,DPR=1,S=100,CX=0,CY=0;
function LWF(){return Math.max(0.8,S/200);}
let fb=document.createElement('canvas'), fx=fb.getContext('2d'); // feedback/glow layer (half res)
let FBS=0.5;
function resize(w,h){
  DPR = RENDER||COVER ? 1 : Math.min(2, window.devicePixelRatio||1);
  W=w; H=h;
  cv.width=W*DPR; cv.height=H*DPR;
  cv.style.width=w+'px'; cv.style.height=h+'px';
  fb.width=Math.round(W*DPR*FBS); fb.height=Math.round(H*DPR*FBS);
  S = Math.min(W,H)*0.155;              // head half-height (world unit)
  if(H>W*1.3) S = Math.min(W*0.185, H*0.118);   // portrait
  CX=W/2; CY=H*(H>W?0.40:0.46);
  makeGrain();
}
if(!RENDER && !COVER){
  window.addEventListener('resize',()=>resize(window.innerWidth,window.innerHeight));
}

/* ---------- grain / scanlines / flame sprite ---------- */
let grains=[], scan=null, flameSprite=null, emberSprite=null;
function makeSprites(){
  flameSprite=document.createElement('canvas');flameSprite.width=flameSprite.height=64;
  let g=flameSprite.getContext('2d');
  let gr=g.createRadialGradient(32,32,0,32,32,32);
  gr.addColorStop(0,'rgba(255,246,228,1)');gr.addColorStop(0.28,'rgba(255,168,72,0.85)');
  gr.addColorStop(0.62,'rgba(232,72,28,0.38)');gr.addColorStop(1,'rgba(160,30,10,0)');
  g.fillStyle=gr;g.fillRect(0,0,64,64);
  emberSprite=document.createElement('canvas');emberSprite.width=emberSprite.height=32;
  g=emberSprite.getContext('2d');
  gr=g.createRadialGradient(16,16,0,16,16,16);
  gr.addColorStop(0,'rgba(255,214,160,1)');gr.addColorStop(0.5,'rgba(255,110,40,0.5)');
  gr.addColorStop(1,'rgba(200,50,15,0)');
  g.fillStyle=gr;g.fillRect(0,0,32,32);
}
function makeGrain(){
  grains=[];
  for(let g=0;g<3;g++){
    const c=document.createElement('canvas');c.width=c.height=256;
    const g2=c.getContext('2d'),im=g2.createImageData(256,256);
    for(let i=0;i<im.data.length;i+=4){const v=200+Math.floor(R()*55);
      im.data[i]=im.data[i+1]=im.data[i+2]=v; im.data[i+3]=(R()<0.5)?0:22;}
    g2.putImageData(im,0,0); grains.push(c);
  }
  scan=document.createElement('canvas');scan.width=4;scan.height=3;
  const s2=scan.getContext('2d');s2.fillStyle='rgba(0,0,0,0.16)';s2.fillRect(0,2,4,1);
  makeSprites();
}

/* ---------- state ---------- */
const ST={
  t:0, dt:1/60,
  bass:0,mid:0,high:0,rms:0,          // 0..1 normalized bands
  scream:0,                            // slow-release bass follower → jaw
  beatPulse:0, beatCount:0, phrase:0,
  intensity:0,                         // long rms follower → pressure
  ratchet:0,                           // permanent creep from clicks
  camScale:1, shX:0, shY:0, rot:0,
  maskState:'off',                     // off | on | falling
  maskType:0, maskT:0, maskSeed:1, cracks:[],
  maskBag:[], forcedOff:0,
  eyesOpen:0,                          // 0 closed → 1 open (intro)
  cursor:{x:0,y:0,heat:0},
  slipT:0, slipY:0, slipH:0, slipDX:0, // vhs tracking slip
  titleCard:0, endCard:0,
  started:false, fileLoaded:false,
  screamLines:[], flames:[], swarm:[],
  paused:false,
};

/* ---------- swarm ---------- */
const WORDS=['منظور','نگاه','چشم','حرف','فکر','صدا','سایه','گوش','اسم','نشونه','تقصیر','دروغ'];
function buildSwarm(){
  ST.swarm=[];
  const N = (RENDER||COVER) ? 150 : Math.min(160, Math.round((W*H)/9000));
  for(let i=0;i<N;i++){
    const r=R(), type = r<0.40?'eye': r<0.66?'word': r<0.86?'sliver':'mouth';
    ST.swarm.push({
      type, a:R()*Math.PI*2,
      r0:1.55+1.7*Math.pow(R(),1.6),
      spin:(R()-0.5)*0.05, nz:R()*100, sz:0.5+R()*0.9,
      word:WORDS[Math.floor(R()*WORDS.length)],
      dim:0.28+R()*0.5, blink:R()*8, imp:0, impV:0, glance:R()*10, flare:0,
    });
  }
}

/* ---------- flames ---------- */
function spawnFlames(rate){
  const n=Math.floor(rate)+((R()<rate%1)?1:0);
  for(let i=0;i<n;i++){
    const th=-Math.PI/2+(R()-0.5)*2.0;               // top arc of skull
    const f=0.90+R()*0.12;
    ST.flames.push({x:Math.cos(th)*0.72*S*f, y:Math.sin(th)*1.0*S*f,
      vx:(R()-0.5)*S*0.30, vy:-(0.9+R()*1.7)*S,
      life:0.30+R()*0.55, age:0, sz:S*(0.045+R()*0.085), nz:R()*40, ember:R()<0.18});
  }
  if(ST.flames.length>520) ST.flames.splice(0,ST.flames.length-520);
}

/* ---------- face geometry ---------- */
function facePts(scale,jaw,n=72){
  const pts=[];
  for(let i=0;i<=n;i++){
    const th=-Math.PI/2+i/n*Math.PI*2, c=Math.cos(th), s=Math.sin(th);
    const lower=Math.max(0,s);
    let rx=0.72*(1-0.30*Math.pow(lower,1.7)), ry=1.0;
    let x=c*rx*scale, y=s*ry*scale;
    y+=Math.pow(lower,2.3)*jaw*0.88*scale;           // the stretch
    x*=1-0.11*jaw*Math.pow(lower,1.6);               // cheeks hollow
    pts.push([x,y]);
  }
  return pts;
}
function jPath(pts,amp,so,close){
  ctx.beginPath();
  for(let i=0;i<pts.length;i++){
    const p=pts[i];
    const ox=snz(i*0.43+so+ST.t*1.9)*amp, oy=snz(i*0.43+so+50+ST.t*1.9)*amp;
    if(i===0)ctx.moveTo(p[0]+ox,p[1]+oy); else ctx.lineTo(p[0]+ox,p[1]+oy);
  }
  if(close)ctx.closePath();
}
function strokeJ(pts,amp,w,alpha,so,close){
  ctx.lineWidth=w*LWF();ctx.strokeStyle=BONE;ctx.globalAlpha=alpha;
  jPath(pts,amp,so,close);ctx.stroke();
  ctx.globalAlpha=alpha*0.5;jPath(pts,amp*1.9,so+31,close);ctx.stroke();
  ctx.globalAlpha=1;
}

/* ---------- masks ---------- */
const MASKS=['smile','grin','blank','weep','rage','polite'];
function refillBag(){ST.maskBag=MASKS.map((m,i)=>i);
  for(let i=ST.maskBag.length-1;i>0;i--){const j=Math.floor(R()*(i+1));
    [ST.maskBag[i],ST.maskBag[j]]=[ST.maskBag[j],ST.maskBag[i]];}}
function drawMaskFeatures(type,s){
  ctx.strokeStyle=BONE_D;ctx.fillStyle=BONE_D;ctx.lineWidth=Math.max(1.4,s*0.028);
  ctx.lineCap='round';
  const ey=-0.16*s, ex=0.26*s, my=0.45*s;
  switch(MASKS[type]){
    case 'smile':
      for(const d of[-1,1]){ctx.beginPath();ctx.arc(d*ex,ey+0.02*s,0.09*s,Math.PI*0.15,Math.PI*0.85);ctx.stroke();}
      ctx.beginPath();ctx.arc(0,my-0.16*s,0.22*s,Math.PI*0.2,Math.PI*0.8);ctx.stroke();break;
    case 'grin':
      for(const d of[-1,1]){ctx.beginPath();ctx.ellipse(d*ex,ey,0.075*s,0.095*s,0,0,7);ctx.stroke();}
      ctx.beginPath();ctx.moveTo(-0.30*s,my-0.12*s);
      ctx.quadraticCurveTo(0,my+0.24*s,0.30*s,my-0.12*s);
      ctx.quadraticCurveTo(0,my+0.05*s,-0.30*s,my-0.12*s);ctx.fill();
      ctx.strokeStyle=BONE;ctx.lineWidth=s*0.012;
      for(let i=-2;i<=2;i++){ctx.beginPath();ctx.moveTo(i*0.10*s,my-0.045*s);ctx.lineTo(i*0.10*s,my+0.06*s);ctx.stroke();}
      break;
    case 'blank':
      for(const d of[-1,1]){ctx.beginPath();ctx.ellipse(d*ex,ey,0.065*s,0.105*s,0,0,7);ctx.fill();}break;
    case 'weep':
      for(const d of[-1,1]){ctx.beginPath();ctx.arc(d*ex,ey+0.09*s,0.09*s,Math.PI*1.15,Math.PI*1.85);ctx.stroke();
        ctx.lineWidth=Math.max(1,s*0.016);
        ctx.beginPath();ctx.moveTo(d*ex,ey+0.10*s);ctx.lineTo(d*ex+d*0.03*s,my+0.16*s);ctx.stroke();
        ctx.lineWidth=Math.max(1.4,s*0.028);}
      ctx.beginPath();ctx.arc(0,my+0.13*s,0.16*s,Math.PI*1.2,Math.PI*1.8);ctx.stroke();break;
    case 'rage':
      for(const d of[-1,1]){ctx.beginPath();ctx.moveTo(d*0.12*s,ey-0.10*s);ctx.lineTo(d*0.38*s,ey-0.20*s);ctx.stroke();
        ctx.beginPath();ctx.ellipse(d*ex,ey+0.01*s,0.055*s,0.075*s,0,0,7);ctx.fill();}
      ctx.beginPath();ctx.rect(-0.20*s,my-0.06*s,0.40*s,0.10*s);ctx.stroke();
      for(let i=-1;i<=1;i++){ctx.beginPath();ctx.moveTo(i*0.10*s,my-0.06*s);ctx.lineTo(i*0.10*s,my+0.04*s);ctx.stroke();}
      break;
    case 'polite':
      for(const d of[-1,1]){ctx.beginPath();ctx.arc(d*ex,ey,0.028*s,0,7);ctx.fill();}
      ctx.beginPath();ctx.moveTo(-0.10*s,my-0.05*s);ctx.lineTo(0.10*s,my-0.05*s);ctx.stroke();break;
  }
}
function drawMask(alpha,fallY,fallRot){
  const s=S*1.07;
  ctx.save();ctx.translate(0,fallY);ctx.rotate(fallRot);
  ctx.globalAlpha=alpha;
  const pts=facePts(s,0);
  const grd=ctx.createLinearGradient(0,-s,0,s);
  grd.addColorStop(0,'#efeadb');grd.addColorStop(0.6,'#ded8c6');grd.addColorStop(1,'#c9c2ae');
  ctx.fillStyle=grd;
  jPath(pts,S*0.006,900,true);ctx.fill();
  ctx.lineWidth=Math.max(1,S*0.014);ctx.strokeStyle='rgba(20,17,15,0.55)';ctx.stroke();
  // shading strokes
  ctx.strokeStyle='rgba(20,17,15,0.10)';ctx.lineWidth=1*LWF();
  for(let i=0;i<7;i++){const yy=-s+((i+1)/8)*2*s;
    ctx.beginPath();ctx.moveTo(-0.6*s*(1-Math.abs(yy)/(1.3*s)),yy);
    ctx.lineTo(0.6*s*(1-Math.abs(yy)/(1.3*s)),yy+0.03*s);ctx.stroke();}
  drawMaskFeatures(ST.maskType,s);
  // cracks
  ctx.strokeStyle='rgba(15,12,10,0.85)';
  for(const cr of ST.cracks){
    ctx.lineWidth=cr.w*LWF();ctx.beginPath();
    for(let i=0;i<cr.p.length;i++){const q=cr.p[i];
      if(i===0)ctx.moveTo(q[0]*s,q[1]*s);else ctx.lineTo(q[0]*s,q[1]*s);}
    ctx.stroke();
    if(cr.glow>0){ // ember light inside fresh crack
      ctx.save();ctx.globalAlpha=alpha*cr.glow*0.6;ctx.strokeStyle='rgba(214,74,26,0.85)';
      ctx.lineWidth=cr.w*1.3*LWF();ctx.stroke();ctx.restore();
    }
  }
  ctx.restore();ctx.globalAlpha=1;
}
function addCrack(){
  const a=R()*Math.PI*2, p=[[Math.cos(a)*0.68,Math.sin(a)*0.92]];
  let x=p[0][0],y=p[0][1];
  const tx=(R()-0.5)*0.25, ty=(R()-0.5)*0.25, n=8+Math.floor(R()*6);
  const branches=[];
  for(let i=0;i<n;i++){
    x+=(tx-x)*0.16+(R()-0.5)*0.075;
    y+=(ty-y)*0.16+(R()-0.5)*0.075;
    p.push([x,y]);
    if(R()<0.22&&i>1){ // short offshoot
      const bl=[[x,y]]; let bx=x,by=y;
      const ba=R()*Math.PI*2;
      for(let k2=0;k2<3;k2++){bx+=Math.cos(ba)*0.045+(R()-0.5)*0.03;by+=Math.sin(ba)*0.045+(R()-0.5)*0.03;bl.push([bx,by]);}
      branches.push(bl);
    }
  }
  ST.cracks.push({p,w:0.55+R()*0.6,glow:0.8});
  for(const b of branches)ST.cracks.push({p:b,w:0.4+R()*0.35,glow:0.5});
}

/* ---------- audio ---------- */
let AC=null, analyser=null, srcNode=null, procNodes=[], freqData=null, timeData=null;
let agc={bass:0.3,mid:0.3,high:0.3,rms:0.3};
let fluxBuf=[], lastBeatAt=-9;
function initAudioGraph(){
  AC=new (window.AudioContext||window.webkitAudioContext)();
  analyser=AC.createAnalyser();analyser.fftSize=2048;analyser.smoothingTimeConstant=0.5;
  freqData=new Uint8Array(analyser.frequencyBinCount);
  timeData=new Uint8Array(analyser.fftSize);
  analyser.connect(AC.destination);
}
function stopSource(){
  if(srcNode){try{srcNode.stop();}catch(e){} srcNode=null;}
  for(const n of procNodes){try{n.stop?n.stop():0;}catch(e){} try{n.disconnect();}catch(e){}}
  procNodes=[];
}
/* the paranoia drone — fallback when no track is dropped */
function startDrone(){
  const g=AC.createGain();g.gain.value=0.9;g.connect(analyser);procNodes.push(g);
  const mk=(type,f,det,vol,lpf)=>{
    const o=AC.createOscillator();o.type=type;o.frequency.value=f;o.detune.value=det;
    const lo=AC.createBiquadFilter();lo.type='lowpass';lo.frequency.value=lpf;
    const gg=AC.createGain();gg.gain.value=vol;
    o.connect(lo);lo.connect(gg);gg.connect(g);o.start();
    procNodes.push(o,lo,gg);return {o,lo,gg};
  };
  const d1=mk('sawtooth',55,0,0.075,240), d2=mk('sawtooth',55,9,0.075,240);
  const lfo=AC.createOscillator();lfo.frequency.value=0.055;
  const lg=AC.createGain();lg.gain.value=130;lfo.connect(lg);lg.connect(d1.lo.frequency);lg.connect(d2.lo.frequency);
  lfo.start();procNodes.push(lfo,lg);
  // air
  const nb=AC.createBuffer(1,AC.sampleRate*2,AC.sampleRate);
  const ch=nb.getChannelData(0);for(let i=0;i<ch.length;i++)ch[i]=Math.random()*2-1;
  const ns=AC.createBufferSource();ns.buffer=nb;ns.loop=true;
  const bp=AC.createBiquadFilter();bp.type='bandpass';bp.frequency.value=6200;bp.Q.value=0.8;
  const ng=AC.createGain();ng.gain.value=0.012;
  ns.connect(bp);bp.connect(ng);ng.connect(g);ns.start();procNodes.push(ns,bp,ng);
  // sub kick @ 73.17 bpm + whisper bursts, scheduled
  const BEAT=60/73.17;
  let nextK=AC.currentTime+0.1, nextW=AC.currentTime+2.5, kn=0;
  function sched(){
    if(!procNodes.length)return;
    while(nextK<AC.currentTime+0.4){
      const o=AC.createOscillator(),kg=AC.createGain();
      o.type='sine';o.frequency.setValueAtTime(150,nextK);
      o.frequency.exponentialRampToValueAtTime(43,nextK+0.09);
      kg.gain.setValueAtTime(0.0001,nextK);
      kg.gain.exponentialRampToValueAtTime((kn%8===0)?0.85:0.55,nextK+0.008);
      kg.gain.exponentialRampToValueAtTime(0.0001,nextK+0.30);
      o.connect(kg);kg.connect(g);o.start(nextK);o.stop(nextK+0.35);
      kn++; nextK+= (kn%16===15)? BEAT*0.5 : BEAT;
    }
    while(nextW<AC.currentTime+0.6){
      const ws=AC.createBufferSource();ws.buffer=nb;ws.loop=true;
      const wb=AC.createBiquadFilter();wb.type='bandpass';
      wb.frequency.value=900+Math.random()*2400;wb.Q.value=2.5;
      const wg=AC.createGain(),pan=AC.createStereoPanner?AC.createStereoPanner():null;
      wg.gain.setValueAtTime(0.0001,nextW);
      wg.gain.exponentialRampToValueAtTime(0.05+Math.random()*0.05,nextW+0.15);
      wg.gain.exponentialRampToValueAtTime(0.0001,nextW+0.7+Math.random()*0.8);
      ws.connect(wb);wb.connect(wg);
      if(pan){pan.pan.value=Math.random()*2-1;wg.connect(pan);pan.connect(g);}else wg.connect(g);
      ws.start(nextW);ws.stop(nextW+2);
      nextW+=2.5+Math.random()*6;
    }
    if(procNodes.length)setTimeout(sched,120);
  }
  sched();
}
function playBuffer(buf){
  stopSource();
  srcNode=AC.createBufferSource();srcNode.buffer=buf;srcNode.loop=true; // the loop never ends
  srcNode.connect(analyser);srcNode.start();
  ST.fileLoaded=true;document.getElementById('hint').style.opacity=0;
}
async function loadFile(f){
  if(!AC)begin(true);
  const ab=await f.arrayBuffer();
  AC.decodeAudioData(ab,b=>playBuffer(b),()=>{});
}
/* band extraction from analyser (both modes) */
function readBands(dt){
  analyser.getByteFrequencyData(freqData);
  analyser.getByteTimeDomainData(timeData);
  const binHz=AC.sampleRate/analyser.fftSize;
  const band=(lo,hi)=>{let s=0,c=0;
    for(let i=Math.max(1,Math.floor(lo/binHz));i<Math.min(freqData.length,Math.ceil(hi/binHz));i++){s+=freqData[i];c++;}
    return c?s/c/255:0;};
  let b=band(20,160), m=band(160,2000), h=band(4000,11000);
  let r=0;for(let i=0;i<timeData.length;i+=4){const v=(timeData[i]-128)/128;r+=v*v;}
  r=Math.sqrt(r/(timeData.length/4));
  for(const [k,v] of [['bass',b],['mid',m],['high',h],['rms',r]]){
    agc[k]=Math.max(v,agc[k]*(1-0.04*dt)); }
  ST.bass=b/Math.max(0.22,agc.bass); ST.mid=m/Math.max(0.22,agc.mid);
  ST.high=h/Math.max(0.22,agc.high); ST.rms=r/Math.max(0.18,agc.rms);
  // beat: bass flux
  fluxBuf.push(b);if(fluxBuf.length>72)fluxBuf.shift();
  const mean=fluxBuf.reduce((a,x)=>a+x,0)/fluxBuf.length;
  const sd=Math.sqrt(fluxBuf.reduce((a,x)=>a+(x-mean)*(x-mean),0)/fluxBuf.length);
  if(b>mean+1.9*sd && b>0.12 && ST.t-lastBeatAt>0.28){lastBeatAt=ST.t;onBeat();}
}

/* ---------- beat / phrase / mask logic ---------- */
function onBeat(){
  ST.beatPulse=1;ST.beatCount++;
  for(const e of ST.swarm){ if(R()<0.28){e.impV-=0.10+R()*0.10;}
    if(e.type==='word'&&R()<0.045)e.flare=1; }
  if(ST.maskState==='on' && ST.bass>0.8 && R()<0.45) addCrack();
  if(ST.beatCount%8===0){
    ST.phrase++;
    if(!ST.noAutoMask)phraseFlip();
  }
}
function phraseFlip(){
  if(ST.maskState==='on'){ dropMask(); }
  else if(ST.intensity<0.80){ wearMask(); }
}
function wearMask(){
  if(!ST.maskBag.length)refillBag();
  ST.maskType=ST.maskBag.pop();
  ST.maskState='on';ST.maskT=0;ST.cracks=[];ST.maskSeed=R()*1000;
}
function dropMask(){ if(ST.maskState==='on'){ST.maskState='falling';ST.maskT=0;} }

/* ---------- interaction ---------- */
function scatter(){
  for(const e of ST.swarm){e.impV+=0.55+R()*0.45;}
  ST.ratchet=Math.min(0.22,ST.ratchet+0.018);   // they come back closer
}

/* ---------- update ---------- */
function update(dt){
  ST.t+=dt;ST.dt=dt;
  // followers
  const atk=1-Math.pow(0.0001,dt), rel=1-Math.pow(0.35,dt);
  ST.scream += (ST.bass>ST.scream? atk:rel)*(ST.bass-ST.scream);
  ST.intensity += (1-Math.pow(0.65,dt))*(ST.rms-ST.intensity);
  ST.beatPulse*=Math.exp(-dt*7.5);
  ST.eyesOpen += ((ST.started?1:0)-ST.eyesOpen)*(1-Math.pow(0.02,dt));
  ST.cursor.heat=Math.max(0,ST.cursor.heat-dt*0.8);
  // forced unmasking at peaks — the truth comes out loud
  if(ST.maskState==='on' && ST.intensity>0.86 && ST.maskT>1.2) dropMask();
  if(ST.maskState==='on'){ST.maskT+=dt; for(const c of ST.cracks)c.glow=Math.max(0,c.glow-dt*1.4);}
  if(ST.maskState==='falling'){ST.maskT+=dt; if(ST.maskT>0.55)ST.maskState='off';}
  // swarm
  for(const e of ST.swarm){
    e.a+=e.spin*dt*(1+ST.mid*1.6);
    e.impV+= -e.imp*10*dt - e.impV*4.2*dt;  // spring back
    e.imp+=e.impV*dt*8;
    e.blink-=dt; if(e.blink<0)e.blink=2.5+R()*7;
    e.glance-=dt; if(e.glance<0)e.glance=4+R()*9;
    e.flare=Math.max(0,e.flare-dt*1.8);
  }
  // flames
  spawnFlames((6+ST.high*230+ST.scream*60)*dt);
  for(let i=ST.flames.length-1;i>=0;i--){
    const f=ST.flames[i];f.age+=dt;
    if(f.age>f.life){ST.flames.splice(i,1);continue;}
    const cu=snz(f.nz+f.age*3.2)*S*1.6;
    f.x+=(f.vx+cu)*dt; f.y+=f.vy*dt*(1+ST.high*0.9);
  }
  // scream lines
  if(ST.beatPulse>0.85 && ST.scream>0.55){
    const n=6+Math.floor(R()*8);
    for(let i=0;i<n;i++){const a=R()*Math.PI*2;
      ST.screamLines.push({a,l:(0.5+R()*0.9),age:0,life:0.16+R()*0.12});}
  }
  for(let i=ST.screamLines.length-1;i>=0;i--){const l=ST.screamLines[i];l.age+=dt;
    if(l.age>l.life)ST.screamLines.splice(i,1);}
  // camera
  const sh=ST.beatPulse*ST.scream;
  ST.camScale=1+ST.bass*0.022+ST.beatPulse*0.030;
  ST.shX=snz(ST.t*23)*sh*S*0.06; ST.shY=snz(ST.t*27+9)*sh*S*0.06;
  ST.rot=snz(ST.t*3.1)*0.004*ST.bass;
  // vhs slip
  ST.slipT-=dt;
  if(ST.slipT<=0){ST.slipT=6+R()*8;ST.slipY=R()*0.8;ST.slipH=0.02+R()*0.05;ST.slipDX=(R()<0.5?-1:1)*(3+R()*9);}
}

/* ---------- draw ---------- */
function ringScale(){return Math.max(0.60,1.30-0.52*ST.intensity-ST.ratchet);}
function drawSwarm(){
  const kx=Math.max(0.55,Math.min(1.30,(W*0.47)/(S*3.4)));
  const ky=Math.max(0.55,Math.min(1.40,(H*0.46)/(S*3.4)));
  const rs=ringScale();
  ctx.textAlign='center';ctx.textBaseline='middle';
  for(const e of ST.swarm){
    const wob=1+snz(e.nz+ST.t*0.5)*0.10+ST.mid*snz(e.nz*3+ST.t*4)*0.06;
    const rr=(e.r0*rs*wob+e.imp)*S;
    const x=Math.cos(e.a)*rr*kx, y=Math.sin(e.a)*rr*ky;
    if(Math.abs(x)>W*0.55||Math.abs(y)>H*0.55)continue;
    if(COVER && y+CY>H*0.80 && Math.abs(x)<W*0.36)continue; // keep the title zone clear
    const flick=0.7+0.3*noise1(e.nz*7+ST.t*(2+ST.mid*9));
    let al=e.dim*flick*(0.55+0.45*ST.eyesOpen);
    const sz=e.sz*S*0.16*(1+ST.beatPulse*0.12);
    ctx.save();ctx.translate(x,y);
    if(e.type==='eye'){
      const bl=(e.blink<0.13)?Math.max(0.08,e.blink/0.13):1;
      ctx.scale(1,bl);
      ctx.strokeStyle=BONE;ctx.globalAlpha=al;ctx.lineWidth=1.2*LWF();
      ctx.beginPath();ctx.moveTo(-sz,0);ctx.quadraticCurveTo(0,-sz*0.72,sz,0);
      ctx.quadraticCurveTo(0,sz*0.72,-sz,0);ctx.closePath();ctx.stroke();
      // pupil aims at head (or the cursor, briefly, when it moves)
      let tx=-x,ty=-y;
      if(ST.cursor.heat>0&&e.glance<1.4){tx=ST.cursor.x-CX-x;ty=ST.cursor.y-CY-y;}
      const dl=Math.hypot(tx,ty)||1;
      ctx.fillStyle=BONE;
      ctx.beginPath();ctx.arc(tx/dl*sz*0.28,ty/dl*sz*0.2,sz*0.2,0,7);ctx.fill();
    }else if(e.type==='word'){
      ctx.globalAlpha=Math.min(1,al*0.9+e.flare*0.8);
      ctx.fillStyle=BONE;
      const fs=Math.round((10+e.sz*11)*LWF()*(1+e.flare*0.25));
      ctx.font=`${e.flare>0.4?'700 ':''}${fs}px Vazirmatn`;
      ctx.fillText(e.word,0,0);
    }else if(e.type==='sliver'){
      const ang=Math.atan2(-y,-x);
      ctx.rotate(ang);ctx.globalAlpha=al*0.8;
      const L=sz*(2.2+ST.mid*1.6);
      ctx.strokeStyle=BONE;ctx.lineWidth=1*LWF();
      ctx.beginPath();ctx.moveTo(-L,0);ctx.lineTo(0,0);ctx.stroke();
      ctx.beginPath();ctx.moveTo(-sz*0.5,-sz*0.22);ctx.lineTo(0,0);ctx.lineTo(-sz*0.5,sz*0.22);ctx.stroke();
    }else{ // whispering mouth
      const open=(0.15+0.85*Math.max(0,ST.mid*noise1(e.nz+ST.t*6)))*sz*0.5;
      ctx.strokeStyle=BONE;ctx.globalAlpha=al;ctx.lineWidth=1.2*LWF();
      ctx.beginPath();ctx.moveTo(-sz*0.7,0);ctx.quadraticCurveTo(0,-open,sz*0.7,0);
      ctx.quadraticCurveTo(0,open,-sz*0.7,0);ctx.closePath();ctx.stroke();
    }
    ctx.restore();
  }
  ctx.globalAlpha=1;
}
function drawHead(){
  const jaw=(0.06+ST.scream*0.58)*ST.eyesOpen;
  const jit=S*(0.012+0.05*ST.scream+0.02*ST.beatPulse);
  // neck + shoulders
  ctx.lineCap='round';
  ctx.strokeStyle=BONE;
  for(const d of[-1,1]){
    const jx=snz(ST.t*2+d)*jit;
    // neck side: from under the jaw down
    ctx.globalAlpha=0.75;ctx.lineWidth=2.2*LWF();
    ctx.beginPath();
    ctx.moveTo(d*S*0.26+jx, S*(0.88+jaw*0.35));
    ctx.quadraticCurveTo(d*S*0.30, S*1.12, d*S*0.34+jx*0.6, S*1.30);
    ctx.stroke();
    // trapezius / shoulder
    ctx.globalAlpha=0.85;ctx.lineWidth=2.8*LWF();
    ctx.beginPath();
    ctx.moveTo(d*S*0.32+jx*0.6, S*1.26);
    ctx.quadraticCurveTo(d*S*0.92, S*1.30, d*S*1.55, S*1.66);
    ctx.stroke();
    // collar hint
    ctx.globalAlpha=0.32;ctx.lineWidth=1.6*LWF();
    ctx.beginPath();
    ctx.moveTo(d*S*0.34, S*1.34);
    ctx.quadraticCurveTo(d*S*0.80, S*1.42, d*S*1.38, S*1.74);
    ctx.stroke();
  }
  // sternum notch
  ctx.globalAlpha=0.5;ctx.lineWidth=1.6*LWF();
  ctx.beginPath();ctx.moveTo(-S*0.10,S*1.40);ctx.quadraticCurveTo(0,S*1.48,S*0.10,S*1.40);ctx.stroke();
  // face
  strokeJ(facePts(S,jaw),jit,2.2,0.92,0,true);
  // ears hint
  // eyes
  const ex=S*0.26, ey=-S*0.16;
  if(ST.eyesOpen<0.98){
    ctx.globalAlpha=0.9*(1-ST.eyesOpen);ctx.strokeStyle=BONE;ctx.lineWidth=2*LWF();
    for(const d of[-1,1]){ctx.beginPath();
      ctx.moveTo(d*ex-S*0.09,ey+S*0.02);ctx.quadraticCurveTo(d*ex,ey+S*0.06,d*ex+S*0.09,ey+S*0.02);ctx.stroke();}
  }
  if(ST.eyesOpen>0.05){
    const o=ST.eyesOpen;
    for(const d of[-1,1]){
      // hollow socket — tilted, inner corner pulled up (anguish)
      ctx.globalAlpha=o;ctx.fillStyle='#000';
      ctx.save();
      ctx.translate(d*ex+snz(ST.t*9+d)*jit*0.4,ey);
      ctx.rotate(-d*(0.30+0.14*ST.scream));
      ctx.beginPath();
      ctx.ellipse(0,0,S*0.052,S*(0.075+0.045*o+0.035*ST.scream),0,0,7);ctx.fill();
      ctx.strokeStyle=BONE;ctx.lineWidth=1.4*LWF();ctx.globalAlpha=o*0.8;ctx.stroke();
      ctx.restore();
      // anguished brow — curves down over the socket
      ctx.globalAlpha=o*0.85;ctx.strokeStyle=BONE;ctx.lineWidth=2.2*LWF();
      ctx.beginPath();
      ctx.moveTo(d*(ex-S*0.13),ey-S*(0.10+0.02*ST.scream));
      ctx.quadraticCurveTo(d*ex,ey-S*(0.20+0.05*ST.scream),
        d*(ex+S*0.11),ey-S*(0.075-0.02*ST.scream));
      ctx.stroke();
    }
    // glabella tension creases
    if(ST.scream>0.25){
      ctx.globalAlpha=o*0.55*Math.min(1,(ST.scream-0.25)/0.3);
      ctx.lineWidth=1.3*LWF();
      for(const d of[-1,1]){
        ctx.beginPath();
        ctx.moveTo(d*S*0.035,ey-S*0.16);
        ctx.lineTo(d*S*0.055,ey-S*0.04);ctx.stroke();
      }
    }
  }
  // the mouth void
  const mw=S*(0.27-0.05*ST.scream), mh=S*(0.10+jaw*1.05);
  const my=S*0.46+mh*0.42;
  ctx.save();ctx.translate(snz(ST.t*14)*jit*0.4,0);
  ctx.beginPath();
  const n=26;
  for(let i=0;i<=n;i++){const th=i/n*Math.PI*2;
    const xx=Math.cos(th)*mw*(1+snz(i*0.8+ST.t*3)*0.05);
    const yy=my+Math.sin(th)*mh*(1+snz(i*0.8+40+ST.t*3)*0.05);
    i===0?ctx.moveTo(xx,yy):ctx.lineTo(xx,yy);}
  ctx.closePath();
  ctx.fillStyle='#000';ctx.globalAlpha=1;ctx.fill();
  if(ST.scream>0.35){
    const g=ctx.createRadialGradient(0,my,0,0,my,Math.max(mw,mh));
    const a=(ST.scream-0.35)*0.55;
    g.addColorStop(0,`rgba(${EMBER[0]},${EMBER[1]},${EMBER[2]},${a})`);
    g.addColorStop(1,'rgba(0,0,0,0)');
    ctx.fillStyle=g;ctx.fill();
  }
  ctx.strokeStyle=BONE;ctx.lineWidth=1.8*LWF();ctx.globalAlpha=0.85;ctx.stroke();
  // radial strain creases around the void
  if(jaw>0.18){
    ctx.lineWidth=1.1*LWF();ctx.globalAlpha=0.32*Math.min(1,(jaw-0.18)/0.2);
    for(const d of[-1,1])for(const aa of[-0.45,0,0.45]){
      const bx=d*mw*1.05, by=my+aa*mh*0.5;
      const dl=Math.hypot(bx,by-my)||1, ux=bx/dl, uy=(by-my)/dl;
      ctx.beginPath();
      ctx.moveTo(bx+ux*S*0.02,by+uy*S*0.02);
      ctx.lineTo(bx+ux*S*(0.10+0.05*jaw),by+uy*S*(0.10+0.05*jaw));ctx.stroke();}
  }
  ctx.restore();
  ctx.globalAlpha=1;
}
function drawMaskLayer(){
  if(ST.maskState==='on'){
    const t=Math.min(1,ST.maskT/0.13);
    const sc=1.35-0.35*(1-Math.pow(1-t,3));   // slam in
    ctx.save();ctx.scale(sc,sc);
    drawMask(Math.min(1,t*1.4)*0.985,S*0.02*snz(ST.t*8),snz(ST.maskSeed+ST.t*0.7)*0.02);
    ctx.restore();
  }else if(ST.maskState==='falling'){
    const t=ST.maskT/0.55;
    drawMask((1-t)*0.95, t*t*S*2.6, t*0.5*(ST.maskSeed%2?1:-1));
  }
}
function drawFlamesTo(g,scale){
  g.save();g.globalCompositeOperation='lighter';
  // base glow crowning the skull
  const heat=Math.min(1,ST.high*0.85+ST.scream*0.45);
  if(heat>0.05){
    g.globalAlpha=heat*0.5;
    const gw=S*1.9*scale;
    g.drawImage(flameSprite,-gw/2,(-1.28*S)*scale-gw/2,gw,gw);
  }
  for(const f of ST.flames){
    const k=f.age/f.life, a=(1-k)*Math.min(1,f.age*10+0.25);
    const spr=f.ember?emberSprite:flameSprite;
    const r=f.sz*(1.25-k*0.55)*scale;
    g.globalAlpha=a*(f.ember?0.9:0.75);
    const sx=f.x*scale, sy=f.y*scale;
    g.save();g.translate(sx,sy);g.rotate(snz(f.nz)*0.5);
    g.drawImage(spr,-r,-r*(f.ember?1:1.9),r*2,r*(f.ember?2:3.8));
    g.restore();
  }
  // scream lines
  g.strokeStyle=`rgba(${HOT[0]},${HOT[1]},${HOT[2]},0.8)`;
  for(const l of ST.screamLines){
    const k=l.age/l.life;g.globalAlpha=(1-k)*0.75;g.lineWidth=1.6*LWF()*scale;
    const r0=S*0.35*scale, r1=S*(0.35+l.l*(0.4+k))*scale;
    const my=S*0.55*scale;
    g.beginPath();g.moveTo(Math.cos(l.a)*r0,my+Math.sin(l.a)*r0*0.8);
    g.lineTo(Math.cos(l.a)*r1,my+Math.sin(l.a)*r1);g.stroke();
  }
  g.globalAlpha=1;g.restore();
}
function drawTitle(){
  if(RENDER&&(ST.titleCard>0||ST.endCard>0))return; // cards handle it
  ctx.save();ctx.resetTransform();ctx.scale(DPR,DPR);
  ctx.textAlign='center';
  const base=Math.min(W,H);
  if(COVER){
    ctx.fillStyle=BONE;ctx.globalAlpha=0.92;
    ctx.font=`700 ${Math.round(base*0.056)}px Vazirmatn`;
    ctx.fillText('همه‌چی منظور داره',W/2,H*0.895);
    ctx.globalAlpha=0.42;
    ctx.font=`${Math.round(base*0.0145)}px ui-monospace,Menlo,monospace`;
    ctx.fillText('S E P   T H E   C O N C E P T',W/2,H*0.928);
  }else{
    ctx.fillStyle=BONE;ctx.globalAlpha=0.8;
    ctx.font=`500 ${Math.round(base*0.030)}px Vazirmatn`;
    ctx.fillText('همه‌چی منظور داره',W/2,H-base*0.062);
    ctx.globalAlpha=0.34;
    ctx.font=`${Math.round(base*0.0115)}px ui-monospace,Menlo,monospace`;
    ctx.fillText('S E P   T H E   C O N C E P T',W/2,H-base*0.034);
  }
  ctx.restore();ctx.globalAlpha=1;
}
function drawCards(){
  if(!RENDER)return;
  ctx.save();ctx.resetTransform();
  if(ST.titleCard>0){
    ctx.fillStyle=`rgba(4,3,3,${0.82*ST.titleCard})`;ctx.fillRect(0,0,W,H);
    ctx.textAlign='center';ctx.globalAlpha=ST.titleCard;
    ctx.fillStyle=BONE;
    ctx.font=`700 ${Math.round(W*0.088)}px Vazirmatn`;
    ctx.fillText('همه‌چی',W/2,H*0.44);
    ctx.fillText('منظور داره',W/2,H*0.44+W*0.115);
    ctx.globalAlpha=ST.titleCard*0.5;
    ctx.font=`${Math.round(W*0.020)}px ui-monospace,Menlo,monospace`;
    ctx.fillText('S E P   T H E   C O N C E P T',W/2,H*0.44+W*0.20);
  }
  if(ST.endCard>0){
    ctx.fillStyle=`rgba(4,3,3,${Math.min(1,ST.endCard*1.2)})`;ctx.fillRect(0,0,W,H);
    ctx.textAlign='center';ctx.globalAlpha=Math.min(1,ST.endCard);
    ctx.fillStyle=BONE;
    ctx.font=`500 ${Math.round(W*0.052)}px Vazirmatn`;
    ctx.fillText('همه‌چی منظور داره',W/2,H*0.485);
    ctx.globalAlpha=Math.min(1,ST.endCard)*0.5;
    ctx.font=`${Math.round(W*0.016)}px ui-monospace,Menlo,monospace`;
    ctx.fillText('S E P   T H E   C O N C E P T',W/2,H*0.485+W*0.055);
  }
  ctx.restore();ctx.globalAlpha=1;
}
function draw(){
  ctx.resetTransform();ctx.scale(DPR,DPR);
  ctx.fillStyle=BG;ctx.fillRect(0,0,W,H);
  // world transform
  ctx.save();
  ctx.translate(CX+ST.shX,CY+ST.shY);
  ctx.rotate(ST.rot);ctx.scale(ST.camScale,ST.camScale);
  drawSwarm();
  drawHead();
  drawMaskLayer();
  ctx.restore();
  // feedback/glow layer
  const fw=fb.width,fh=fb.height;
  fx.setTransform(1,0,0,1,0,0);
  fx.globalAlpha=0.93-0.05*(1-ST.intensity);
  const z=1.008+ST.bass*0.005;
  fx.drawImage(fb,fw/2-fw/2*z,fh/2-fh/2*z-1.1,fw*z,fh*z);
  fx.globalAlpha=1;
  // fade the layer slightly toward black so trails die
  fx.fillStyle='rgba(0,0,0,0.11)';fx.fillRect(0,0,fw,fh);
  fx.save();fx.translate(fw/2+ST.shX*FBS*DPR,(CY/H)*fh+ST.shY*FBS*DPR);
  drawFlamesTo(fx,FBS*DPR*(S/ (S))); // scale via coords: flame coords are world px → *FBS*DPR
  fx.restore();
  ctx.save();ctx.resetTransform();
  ctx.globalCompositeOperation='screen';
  ctx.drawImage(fb,0,0,cv.width,cv.height);
  ctx.restore();
  // vignette
  ctx.save();ctx.resetTransform();ctx.scale(DPR,DPR);
  const vr=Math.max(W,H)*(0.78-0.16*ST.intensity);
  const vg=ctx.createRadialGradient(W/2,H*0.44,vr*0.35,W/2,H*0.44,vr);
  vg.addColorStop(0,'rgba(0,0,0,0)');vg.addColorStop(1,`rgba(0,0,0,${0.62+0.2*ST.intensity})`);
  ctx.fillStyle=vg;ctx.fillRect(0,0,W,H);
  // vhs slip
  if(ST.slipT<0.16){
    const sy=Math.floor(H*ST.slipY), sh2=Math.max(2,Math.floor(H*ST.slipH));
    try{ctx.drawImage(cv,0,sy*DPR,cv.width,sh2*DPR,ST.slipDX,sy,W,sh2);}catch(e){}
  }
  // grain + scanlines
  const gi=Math.floor(R()*3);
  ctx.globalAlpha=0.55;
  const pat=ctx.createPattern(grains[gi],'repeat');
  ctx.save();ctx.translate(Math.floor(R()*256),Math.floor(R()*256));
  ctx.fillStyle=pat;ctx.fillRect(-256,-256,W+512,H+512);ctx.restore();
  ctx.globalAlpha=0.5;
  const sp=ctx.createPattern(scan,'repeat');
  ctx.save();ctx.translate(0,Math.floor(ST.t*8)%3);
  ctx.fillStyle=sp;ctx.fillRect(0,-3,W,H+6);ctx.restore();
  ctx.globalAlpha=1;ctx.restore();
  drawTitle();
  drawCards();
}

/* ---------- live loop ---------- */
let lastT=0,fpsAcc=0,fpsN=0;
function loop(ts){
  if(RENDER||COVER)return;
  requestAnimationFrame(loop);
  if(ST.paused){lastT=ts;return;}
  const dt=Math.min(0.05,Math.max(0.001,(ts-lastT)/1000||0.016));lastT=ts;
  if(AC&&analyser)readBands(dt);
  else{ // idle before start: faint drift
    ST.bass*=0.98;ST.mid=0.15+0.1*noise1(ST.t*0.3);ST.high*=0.98;ST.rms=0.12;
  }
  update(dt);draw();
  fpsAcc+=1/dt;fpsN++;
  if(fpsN>=90){const f=fpsAcc/fpsN;fpsAcc=0;fpsN=0;
    if(f<42&&ST.swarm.length>70){ST.swarm.length=Math.floor(ST.swarm.length*0.8);}}
}

/* ---------- boot / modes ---------- */
function begin(silent){
  if(ST.started)return;
  ST.started=true;
  document.getElementById('ui').classList.add('gone');
  initAudioGraph();
  if(!silent)startDrone();
  setTimeout(()=>{if(!ST.fileLoaded)document.getElementById('hint').style.opacity=0.35;},4000);
}
if(!RENDER&&!COVER){
  resize(window.innerWidth,window.innerHeight);
  buildSwarm();refillBag();
  document.getElementById('ui').addEventListener('click',()=>{begin(false);});
  window.addEventListener('pointerdown',e=>{
    if(!ST.started)return;
    ST.cursor.x=e.clientX;ST.cursor.y=e.clientY;ST.cursor.heat=1.4;
    scatter();
  });
  window.addEventListener('pointermove',e=>{ST.cursor.x=e.clientX;ST.cursor.y=e.clientY;ST.cursor.heat=1.4;});
  window.addEventListener('keydown',e=>{if(e.code==='Space'){ST.paused=!ST.paused;if(AC)AC[ST.paused?'suspend':'resume']();}});
  window.addEventListener('dragover',e=>e.preventDefault());
  window.addEventListener('drop',e=>{e.preventDefault();
    if(e.dataTransfer.files&&e.dataTransfer.files[0])loadFile(e.dataTransfer.files[0]);});
  document.fonts.load('16px Vazirmatn','منظور').then(()=>{requestAnimationFrame(loop);});
}

/* ---------- render mode API (driven by headless capture) ---------- */
if(RENDER){
  const w=parseInt(Q.get('w')||'1080'),h=parseInt(Q.get('h')||'1920');
  resize(w,h);buildSwarm();refillBag();
  ST.started=true;ST.eyesOpen=1;
  window.__ready = document.fonts.load('16px Vazirmatn','منظور داره همه‌چی').then(()=>
    document.fonts.load('700 16px Vazirmatn','منظور')).then(()=>'ok');
  window.__frame = function(p){
    ST.bass=p.bass;ST.mid=p.mid;ST.high=p.high;ST.rms=p.rms;
    ST.noAutoMask=!!p.noAutoMask;
    if(p.beat){onBeat();}
    if(p.forceMaskOff&&ST.maskState==='on')dropMask();
    if(p.forceMaskOn&&ST.maskState==='off')wearMask();
    ST.titleCard=p.titleCard||0;ST.endCard=p.endCard||0;
    update(p.dt);draw();
    return 'ok';
  };
}

/* ---------- cover mode ---------- */
if(COVER){
  const size=parseInt(Q.get('size')||'3000');
  resize(size,size);
  S=size*0.17;CX=size/2;CY=size*0.435;
  buildSwarm();
  ST.started=true;ST.eyesOpen=1;ST.intensity=0.62;ST.scream=1.0;
  ST.bass=0.85;ST.high=0.75;ST.mid=0.4;ST.rms=0.62;
  window.__cover=async function(variant){
    await document.fonts.load('16px Vazirmatn','منظور');
    await document.fonts.load('700 16px Vazirmatn','منظور');
    await document.fonts.load('500 16px Vazirmatn','منظور');
    // settle, then accumulate a few drawn frames so the glow layer breathes
    for(let i=0;i<130;i++){update(1/30);}
    if(variant==='mask'){ST.maskState='on';ST.maskType=2;ST.maskT=1;ST.cracks=[];
      addCrack();addCrack();}
    else ST.maskState='off';
    for(let i=0;i<22;i++){update(1/30);draw();}
    if(variant==='mask'){for(const c of ST.cracks)c.glow=0.55;}
    draw();
    return 'ok';
  };
}
