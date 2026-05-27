// resonance-tokens.jsx — Resonance design system
// Tokens, primitives, and the 6 scene previews. No deps beyond React.

const R = {
  // Backgrounds — deeper void to suppress code-editor associations
  void:     '#06060C',
  deep:     '#0B0C18',
  surface:  '#11132A',
  raised:   '#181B3A',
  bezel:    '#222652',          // instrument bezel
  hairline: 'rgba(120,130,220,0.10)',
  hairBright:'rgba(190,200,255,0.20)',
  // Brand thread
  indigo:   '#6366F1',
  violet:   '#A855F7',
  pink:     '#EC4899',
  // Live signal — oscilloscope trace colour
  trace:    '#7DF9FF',
  traceDim: '#3DD9E5',
  // Semantic
  amber:    '#FBBF24',
  green:    '#34D399',
  red:      '#F87171',
  // Text
  phosphor: '#E6E8FF',  // primary
  ion:      '#A5A9D6',  // secondary
  dim:      '#6B6F94',  // tertiary
  faint:    '#3A3D62',  // quaternary
};

const GRAD = 'linear-gradient(135deg, #6366F1 0%, #A855F7 50%, #EC4899 100%)';
const GRAD_SOFT = 'linear-gradient(135deg, rgba(99,102,241,.6) 0%, rgba(168,85,247,.55) 50%, rgba(236,72,153,.5) 100%)';

// Fonts — load before this script
const F = {
  display: '"Space Grotesk", system-ui, sans-serif',
  ui:      '"Geist", "Space Grotesk", system-ui, sans-serif',
  mono:    '"Geist Mono", "JetBrains Mono", ui-monospace, monospace',
};

// ─────────────────────────────────────────────────────────────
// PhaseLine — the signature motif. A thin oscilloscope trace
// that breathes across the top of every primary surface.
// ─────────────────────────────────────────────────────────────
function PhaseLine({ width=900, height=44, seed=0, amp=10, freq=0.018, speed=0.6, color=R.trace, glow=true, ticks=true }) {
  const ref = React.useRef(null);
  React.useEffect(() => {
    const c = ref.current; if (!c) return;
    const ctx = c.getContext('2d');
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    c.width = width * dpr; c.height = height * dpr;
    ctx.scale(dpr, dpr);
    let raf, t0 = performance.now();
    const draw = (now) => {
      const t = (now - t0) / 1000 * speed + seed;
      ctx.clearRect(0,0,width,height);
      // tick marks (instrument calibration)
      if (ticks) {
        ctx.strokeStyle = 'rgba(180,190,255,0.08)';
        ctx.lineWidth = 1;
        for (let x = 0; x <= width; x += 16) {
          const major = x % 64 === 0;
          ctx.beginPath();
          ctx.moveTo(x + 0.5, height - 4);
          ctx.lineTo(x + 0.5, height - (major ? 12 : 8));
          ctx.stroke();
        }
      }
      // Phase trace — sum of two sines for organic feel
      ctx.beginPath();
      const mid = height / 2;
      for (let x = 0; x <= width; x++) {
        const y = mid
          + Math.sin(x*freq + t) * amp
          + Math.sin(x*freq*2.3 + t*1.7 + seed) * amp*0.35;
        if (x === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      }
      if (glow) {
        ctx.shadowColor = color; ctx.shadowBlur = 12;
      }
      ctx.strokeStyle = color;
      ctx.lineWidth = 1.4;
      ctx.stroke();
      ctx.shadowBlur = 0;
      // moving cursor
      const cx = (width * 0.78) + Math.sin(t*0.3) * width * 0.1;
      const cy = mid + Math.sin(cx*freq + t) * amp + Math.sin(cx*freq*2.3 + t*1.7 + seed)*amp*0.35;
      ctx.fillStyle = color;
      ctx.beginPath(); ctx.arc(cx, cy, 2.5, 0, Math.PI*2); ctx.fill();
      ctx.strokeStyle = 'rgba(125,249,255,0.25)';
      ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(cx, 4); ctx.lineTo(cx, height-4); ctx.stroke();
      raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [width, height, seed, amp, freq, speed, color, glow, ticks]);
  return <canvas ref={ref} style={{ width, height, display: 'block' }} />;
}

// ─────────────────────────────────────────────────────────────
// Reticle — concentric crosshair used as a corner marker
// ─────────────────────────────────────────────────────────────
function Reticle({ size=18, color=R.trace, opacity=0.5 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" style={{ opacity }}>
      <circle cx="12" cy="12" r="10" stroke={color} strokeWidth="0.7" fill="none"/>
      <circle cx="12" cy="12" r="4"  stroke={color} strokeWidth="0.7" fill="none"/>
      <line x1="12" y1="0" x2="12" y2="6" stroke={color} strokeWidth="0.7"/>
      <line x1="12" y1="18" x2="12" y2="24" stroke={color} strokeWidth="0.7"/>
      <line x1="0" y1="12" x2="6" y2="12" stroke={color} strokeWidth="0.7"/>
      <line x1="18" y1="12" x2="24" y2="12" stroke={color} strokeWidth="0.7"/>
      <circle cx="12" cy="12" r="1.2" fill={color}/>
    </svg>
  );
}

// Corner brackets — instrument viewport framing
function CornerBrackets({ inset=8, len=14, color=R.ion, opacity=0.4 }) {
  const s = { position:'absolute', width:len, height:len, borderColor:color, opacity, pointerEvents:'none' };
  const w = 1;
  return (<>
    <div style={{ ...s, top:inset, left:inset, borderTop:`${w}px solid`, borderLeft:`${w}px solid` }}/>
    <div style={{ ...s, top:inset, right:inset, borderTop:`${w}px solid`, borderRight:`${w}px solid` }}/>
    <div style={{ ...s, bottom:inset, left:inset, borderBottom:`${w}px solid`, borderLeft:`${w}px solid` }}/>
    <div style={{ ...s, bottom:inset, right:inset, borderBottom:`${w}px solid`, borderRight:`${w}px solid` }}/>
  </>);
}

// Tiny tag chip
function Tag({ children, color=R.trace, dot=true }) {
  return (
    <span style={{
      display:'inline-flex', alignItems:'center', gap:6,
      padding:'3px 8px 3px 7px', borderRadius: 999,
      background: 'rgba(125,249,255,0.07)',
      border: `1px solid ${R.hairline}`,
      fontFamily: F.mono, fontSize: 10, letterSpacing: '0.12em',
      color: R.ion, textTransform:'uppercase',
    }}>
      {dot && <span style={{ width:5, height:5, borderRadius:5, background:color, boxShadow:`0 0 6px ${color}` }}/>}
      {children}
    </span>
  );
}

// ─────────────────────────────────────────────────────────────
// Scene previews — the heart of the Gallery. Each is a tiny,
// animated, math-flavoured loop that runs entirely on canvas.
// ─────────────────────────────────────────────────────────────
function useCanvas(draw, deps=[]) {
  const ref = React.useRef(null);
  React.useEffect(() => {
    const c = ref.current; if (!c) return;
    const ctx = c.getContext('2d');
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = c.clientWidth, h = c.clientHeight;
    c.width = w*dpr; c.height = h*dpr; ctx.scale(dpr, dpr);
    let raf, t0 = performance.now();
    const loop = (now) => {
      const t = (now - t0)/1000;
      ctx.clearRect(0,0,w,h);
      draw(ctx, t, w, h);
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
    // eslint-disable-next-line
  }, deps);
  return ref;
}

// 1. Hello Manim — letters drawn by tracing path
function ScenePreview_Hello({ w=300, h=180 }) {
  const ref = useCanvas((ctx, t, w, h) => {
    const cx = w/2, cy = h/2 + 6;
    // baseline + reticles
    ctx.strokeStyle = 'rgba(125,249,255,0.10)'; ctx.lineWidth = 1;
    ctx.setLineDash([2,4]); ctx.beginPath(); ctx.moveTo(20, cy+22); ctx.lineTo(w-20, cy+22); ctx.stroke();
    ctx.setLineDash([]);
    // pen-trace 'M'
    const M = [[0,1],[0,-1],[0.5,0.4],[1,-1],[1,1]];
    const tri = [[1.1,1],[1.6,-1],[2.1,1],[1.85,0.3],[1.35,0.3]];
    const phase = (t % 3) / 3;
    const drawPath = (pts, sx, scale, drawTo) => {
      ctx.beginPath();
      for (let i=0;i<=drawTo;i++) {
        const p = pts[i]; if (!p) continue;
        const x = sx + p[0]*scale, y = cy + p[1]*scale*0.7;
        if (i===0) ctx.moveTo(x,y); else ctx.lineTo(x,y);
      }
      ctx.lineWidth = 2.2; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
      const grad = ctx.createLinearGradient(0,0,w,0);
      grad.addColorStop(0,'#6366F1'); grad.addColorStop(0.5,'#A855F7'); grad.addColorStop(1,'#EC4899');
      ctx.strokeStyle = grad; ctx.shadowColor = '#A855F7'; ctx.shadowBlur = 10; ctx.stroke();
      ctx.shadowBlur = 0;
    };
    const total = M.length + tri.length;
    const drawn = Math.floor(phase * total);
    drawPath(M, cx - 70, 26, Math.min(drawn, M.length-1));
    drawPath(tri, cx - 70, 26, Math.min(drawn - M.length, tri.length-1));
    // label
    ctx.fillStyle = 'rgba(229,232,255,0.55)';
    ctx.font = `10px ${F.mono}`; ctx.textAlign='center';
    ctx.fillText('HELLO  MANIM', cx, h-14);
  });
  return <canvas ref={ref} style={{ width:w, height:h, display:'block' }}/>;
}

// 2. Pythagorean Theorem — triangle with three squares
function ScenePreview_Pythag({ w=300, h=180 }) {
  const ref = useCanvas((ctx, t, w, h) => {
    const cx = w/2 + 6, cy = h/2 + 16;
    const a = 32, b = 44;
    // triangle vertices
    const A = [cx - b/2, cy + a/2];
    const B = [cx + b/2, cy + a/2];
    const C = [cx + b/2, cy - a/2];
    // anim: each square scales in sequence
    const phase = (t % 4) / 4;
    const e1 = Math.max(0, Math.min(1, phase*4));
    const e2 = Math.max(0, Math.min(1, (phase-0.25)*4));
    const e3 = Math.max(0, Math.min(1, (phase-0.5)*4));
    // square on b (bottom)
    ctx.save();
    ctx.fillStyle = 'rgba(99,102,241,0.18)';
    ctx.strokeStyle = '#6366F1'; ctx.lineWidth = 1.3;
    ctx.beginPath(); ctx.rect(A[0], A[1], b*e1, b); ctx.fill(); ctx.stroke();
    // square on a (right)
    ctx.fillStyle = 'rgba(236,72,153,0.18)';
    ctx.strokeStyle = '#EC4899';
    ctx.beginPath(); ctx.rect(B[0], B[1]-a*e2, a, a*e2); ctx.fill(); ctx.stroke();
    // square on c (hypotenuse) — rotated
    const dx = C[0]-A[0], dy = C[1]-A[1]; const len = Math.hypot(dx,dy);
    const ang = Math.atan2(dy, dx);
    ctx.translate(A[0], A[1]); ctx.rotate(ang);
    ctx.fillStyle = 'rgba(168,85,247,0.18)';
    ctx.strokeStyle = '#A855F7';
    ctx.beginPath(); ctx.rect(0, -len*e3, len, len*e3); ctx.fill(); ctx.stroke();
    ctx.restore();
    // triangle on top
    ctx.beginPath(); ctx.moveTo(...A); ctx.lineTo(...B); ctx.lineTo(...C); ctx.closePath();
    ctx.strokeStyle = R.phosphor; ctx.lineWidth = 1.6; ctx.stroke();
    // label
    ctx.fillStyle = 'rgba(229,232,255,0.55)';
    ctx.font = `10px ${F.mono}`; ctx.textAlign='center';
    ctx.fillText('a² + b² = c²', w/2, h-14);
  });
  return <canvas ref={ref} style={{ width:w, height:h, display:'block' }}/>;
}

// 3. Sine wave — animated trace
function ScenePreview_Sine({ w=300, h=180 }) {
  const ref = useCanvas((ctx, t, w, h) => {
    const cy = h/2;
    // grid
    ctx.strokeStyle = 'rgba(125,249,255,0.06)'; ctx.lineWidth = 1;
    for (let x=0;x<w;x+=20) { ctx.beginPath(); ctx.moveTo(x,8); ctx.lineTo(x,h-22); ctx.stroke(); }
    for (let y=8;y<h-22;y+=20){ ctx.beginPath(); ctx.moveTo(8,y); ctx.lineTo(w-8,y); ctx.stroke(); }
    // axes
    ctx.strokeStyle = 'rgba(229,232,255,0.18)';
    ctx.beginPath(); ctx.moveTo(8,cy); ctx.lineTo(w-8,cy); ctx.stroke();
    // sine
    ctx.beginPath();
    for (let x=8;x<w-8;x++) {
      const y = cy + Math.sin((x-8)*0.06 - t*1.8) * 26;
      if (x===8) ctx.moveTo(x,y); else ctx.lineTo(x,y);
    }
    const grad = ctx.createLinearGradient(0,0,w,0);
    grad.addColorStop(0,'#6366F1'); grad.addColorStop(1,'#EC4899');
    ctx.strokeStyle = grad; ctx.lineWidth = 2;
    ctx.shadowColor = '#A855F7'; ctx.shadowBlur = 10; ctx.stroke(); ctx.shadowBlur = 0;
    // dot rider
    const rx = 8 + ((t*40)%(w-16));
    const ry = cy + Math.sin((rx-8)*0.06 - t*1.8)*26;
    ctx.fillStyle = R.trace; ctx.beginPath(); ctx.arc(rx,ry,3,0,Math.PI*2); ctx.fill();
    ctx.fillStyle = 'rgba(229,232,255,0.55)';
    ctx.font = `10px ${F.mono}`; ctx.textAlign='center';
    ctx.fillText('y = sin(x)', w/2, h-8);
  });
  return <canvas ref={ref} style={{ width:w, height:h, display:'block' }}/>;
}

// 4. Fourier squares — rotating epicycles tracing a square
function ScenePreview_Fourier({ w=300, h=180 }) {
  const trail = React.useRef([]);
  const ref = useCanvas((ctx, t, w, h) => {
    const cx = w*0.42, cy = h/2;
    // square via fourier (odd harmonics, sine series for square wave) — used as 2D rotation chain
    const N = 5;
    let x = cx, y = cy;
    const colors = ['#6366F1','#7B5FF1','#A855F7','#D04AB9','#EC4899'];
    for (let k=0;k<N;k++) {
      const n = 2*k+1;
      const r = 26 * (4/(Math.PI*n));
      const ang = t * 1.2 * n;
      const nx = x + Math.cos(ang)*r;
      const ny = y + Math.sin(ang)*r;
      ctx.strokeStyle = 'rgba(190,200,255,0.18)';
      ctx.lineWidth = 1;
      ctx.beginPath(); ctx.arc(x,y,r,0,Math.PI*2); ctx.stroke();
      ctx.strokeStyle = colors[k]; ctx.lineWidth = 1.2;
      ctx.beginPath(); ctx.moveTo(x,y); ctx.lineTo(nx,ny); ctx.stroke();
      x = nx; y = ny;
    }
    // trail
    trail.current.push([x,y]); if (trail.current.length > 200) trail.current.shift();
    ctx.beginPath();
    trail.current.forEach((p,i)=> { if(i===0) ctx.moveTo(p[0],p[1]); else ctx.lineTo(p[0],p[1]); });
    ctx.strokeStyle = R.trace; ctx.lineWidth = 1.6; ctx.shadowColor = R.trace; ctx.shadowBlur = 8; ctx.stroke();
    ctx.shadowBlur = 0;
    // final tip
    ctx.fillStyle = '#EC4899'; ctx.beginPath(); ctx.arc(x,y,2.5,0,Math.PI*2); ctx.fill();
    ctx.fillStyle = 'rgba(229,232,255,0.55)';
    ctx.font = `10px ${F.mono}`; ctx.textAlign='center';
    ctx.fillText('Σ ƒ(n) — FOURIER', w/2, h-8);
  });
  return <canvas ref={ref} style={{ width:w, height:h, display:'block' }}/>;
}

// 5. Circle ↔ Square morph
function ScenePreview_Morph({ w=300, h=180 }) {
  const ref = useCanvas((ctx, t, w, h) => {
    const cx = w/2, cy = h/2 + 4;
    const R0 = 36;
    // morph factor pulses 0..1..0
    const m = (Math.sin(t*1.4) + 1) / 2;
    const pts = 64;
    ctx.beginPath();
    for (let i=0;i<=pts;i++) {
      const a = (i/pts)*Math.PI*2 - Math.PI/4;
      // circle pt
      const cxp = Math.cos(a)*R0, cyp = Math.sin(a)*R0;
      // square pt (inscribed)
      const k = Math.max(Math.abs(Math.cos(a)), Math.abs(Math.sin(a)));
      const sxp = (Math.cos(a)/k)*R0, syp = (Math.sin(a)/k)*R0;
      const x = cx + cxp*(1-m) + sxp*m;
      const y = cy + cyp*(1-m) + syp*m;
      if (i===0) ctx.moveTo(x,y); else ctx.lineTo(x,y);
    }
    ctx.closePath();
    ctx.fillStyle = 'rgba(168,85,247,0.10)';
    const grad = ctx.createLinearGradient(cx-R0,cy-R0,cx+R0,cy+R0);
    grad.addColorStop(0,'#6366F1'); grad.addColorStop(1,'#EC4899');
    ctx.strokeStyle = grad; ctx.lineWidth = 2;
    ctx.shadowColor = '#A855F7'; ctx.shadowBlur = 12; ctx.fill(); ctx.stroke(); ctx.shadowBlur = 0;
    ctx.fillStyle = 'rgba(229,232,255,0.55)';
    ctx.font = `10px ${F.mono}`; ctx.textAlign='center';
    ctx.fillText('◯ → ▢ — INTERPOLATE', w/2, h-12);
  });
  return <canvas ref={ref} style={{ width:w, height:h, display:'block' }}/>;
}

// 6. Graph Traversal — nodes + animated path
function ScenePreview_Graph({ w=300, h=180 }) {
  const nodes = React.useMemo(() => [
    [60, 60], [130, 40], [210, 70], [255, 130], [180, 140], [100, 130], [60, 100]
  ], []);
  const edges = [[0,1],[1,2],[2,3],[3,4],[4,5],[5,6],[6,0],[1,5],[2,4]];
  const path = [0,1,2,4,5,6];
  const ref = useCanvas((ctx, t, w, h) => {
    // edges
    edges.forEach(([a,b])=> {
      const [ax,ay]=nodes[a], [bx,by]=nodes[b];
      ctx.strokeStyle = 'rgba(190,200,255,0.18)'; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(ax,ay); ctx.lineTo(bx,by); ctx.stroke();
    });
    // traversal — highlight path up to floor(t*1.2)%path.length
    const phase = (t*0.9) % path.length;
    for (let i=0;i<Math.floor(phase);i++) {
      const a=nodes[path[i]], b=nodes[path[i+1]]; if(!b) break;
      ctx.strokeStyle = '#A855F7'; ctx.lineWidth = 2; ctx.shadowColor='#A855F7'; ctx.shadowBlur = 8;
      ctx.beginPath(); ctx.moveTo(...a); ctx.lineTo(...b); ctx.stroke(); ctx.shadowBlur = 0;
    }
    // current animating edge
    const idx = Math.floor(phase);
    const frac = phase - idx;
    if (path[idx+1] !== undefined) {
      const a=nodes[path[idx]], b=nodes[path[idx+1]];
      const x = a[0] + (b[0]-a[0])*frac, y = a[1] + (b[1]-a[1])*frac;
      ctx.strokeStyle = '#EC4899'; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.moveTo(...a); ctx.lineTo(x,y); ctx.stroke();
      ctx.fillStyle = R.trace; ctx.shadowColor = R.trace; ctx.shadowBlur = 10;
      ctx.beginPath(); ctx.arc(x,y,4,0,Math.PI*2); ctx.fill(); ctx.shadowBlur = 0;
    }
    // nodes
    nodes.forEach((n,i)=> {
      const visited = path.slice(0, Math.floor(phase)+1).includes(i);
      ctx.fillStyle = R.deep; ctx.strokeStyle = visited ? '#EC4899' : R.ion; ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.arc(n[0],n[1],5,0,Math.PI*2); ctx.fill(); ctx.stroke();
    });
    ctx.fillStyle = 'rgba(229,232,255,0.55)';
    ctx.font = `10px ${F.mono}`; ctx.textAlign='center';
    ctx.fillText('GRAPH · DFS', w/2, h-8);
  });
  return <canvas ref={ref} style={{ width:w, height:h, display:'block' }}/>;
}

// ─────────────────────────────────────────────────────────────
// Particle / starfield used in render state — light & deterministic
// ─────────────────────────────────────────────────────────────
function ParticleField({ w=400, h=240, density=0.6, speed=1 }) {
  const ref = React.useRef(null);
  React.useEffect(() => {
    const c = ref.current; const ctx = c.getContext('2d');
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    c.width=w*dpr; c.height=h*dpr; ctx.scale(dpr,dpr);
    const N = Math.floor(w*h*0.0008*density);
    const ps = Array.from({length:N}, () => ({
      x: Math.random()*w, y: Math.random()*h,
      v: 0.2 + Math.random()*0.8,
      r: Math.random()*1.4 + 0.3,
      hue: Math.random()<0.6 ? '#7DF9FF' : (Math.random()<0.5 ? '#A855F7' : '#EC4899'),
    }));
    let raf;
    const loop = () => {
      ctx.clearRect(0,0,w,h);
      ps.forEach(p => {
        p.y += p.v * speed * 0.6;
        if (p.y > h) { p.y = -2; p.x = Math.random()*w; }
        ctx.fillStyle = p.hue;
        ctx.globalAlpha = 0.6;
        ctx.beginPath(); ctx.arc(p.x,p.y,p.r,0,Math.PI*2); ctx.fill();
      });
      ctx.globalAlpha = 1;
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [w,h,density,speed]);
  return <canvas ref={ref} style={{ width:w, height:h, display:'block' }}/>;
}

Object.assign(window, {
  R, GRAD, GRAD_SOFT, F,
  PhaseLine, Reticle, CornerBrackets, Tag,
  ScenePreview_Hello, ScenePreview_Pythag, ScenePreview_Sine,
  ScenePreview_Fourier, ScenePreview_Morph, ScenePreview_Graph,
  ParticleField,
});
