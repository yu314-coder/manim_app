// resonance-screens.jsx — All Resonance screens & components
// Depends on globals from resonance-tokens.jsx

// ─────────────────────────────────────────────────────────────
// SideRail — vertical nav with rotated labels (iPad)
// ─────────────────────────────────────────────────────────────
const NAV = [
  { id:'gallery',   label:'GALLERY',   icon:'gallery' },
  { id:'workspace', label:'WORKSPACE', icon:'scope' },
  { id:'assets',    label:'ASSETS',    icon:'stack' },
  { id:'packages',  label:'PACKAGES',  icon:'cube' },
  { id:'history',   label:'HISTORY',   icon:'clock' },
  { id:'system',    label:'SYSTEM',    icon:'chip' },
];

function NavIcon({ kind, active }) {
  const s = active ? R.trace : R.dim;
  const sw = 1.4;
  switch (kind) {
    case 'gallery': return (<svg width="22" height="22" viewBox="0 0 24 24" fill="none">
      <rect x="3.5" y="3.5" width="7" height="7" rx="1.2" stroke={s} strokeWidth={sw}/>
      <rect x="13.5" y="3.5" width="7" height="7" rx="1.2" stroke={s} strokeWidth={sw}/>
      <rect x="3.5" y="13.5" width="7" height="7" rx="1.2" stroke={s} strokeWidth={sw}/>
      <circle cx="17" cy="17" r="3.5" stroke={s} strokeWidth={sw}/>
    </svg>);
    case 'scope': return (<svg width="22" height="22" viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="8.5" stroke={s} strokeWidth={sw}/>
      <path d="M3.5 12 C 7 8, 9 16, 12 12 S 17 8, 20.5 12" stroke={s} strokeWidth={sw} strokeLinecap="round"/>
      <circle cx="12" cy="12" r="1.3" fill={s}/>
    </svg>);
    case 'stack': return (<svg width="22" height="22" viewBox="0 0 24 24" fill="none">
      <path d="M4 8l8-4 8 4-8 4-8-4z" stroke={s} strokeWidth={sw} strokeLinejoin="round"/>
      <path d="M4 13l8 4 8-4" stroke={s} strokeWidth={sw} strokeLinejoin="round"/>
      <path d="M4 17l8 4 8-4" stroke={s} strokeWidth={sw} strokeLinejoin="round"/>
    </svg>);
    case 'cube': return (<svg width="22" height="22" viewBox="0 0 24 24" fill="none">
      <path d="M12 3l8 4.5v9L12 21l-8-4.5v-9L12 3z" stroke={s} strokeWidth={sw} strokeLinejoin="round"/>
      <path d="M12 3v9m0 0l8-4.5M12 12L4 7.5M12 12v9" stroke={s} strokeWidth={sw}/>
    </svg>);
    case 'clock': return (<svg width="22" height="22" viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="8.5" stroke={s} strokeWidth={sw}/>
      <path d="M12 7v5l3.5 2.5" stroke={s} strokeWidth={sw} strokeLinecap="round"/>
    </svg>);
    case 'chip': return (<svg width="22" height="22" viewBox="0 0 24 24" fill="none">
      <rect x="6.5" y="6.5" width="11" height="11" rx="1.6" stroke={s} strokeWidth={sw}/>
      <rect x="9.5" y="9.5" width="5" height="5" stroke={s} strokeWidth={sw}/>
      {[0,1,2,3].map(i => (<g key={i}>
        <line x1={9 + i*2} y1="3.5" x2={9 + i*2} y2="6.5" stroke={s} strokeWidth={sw}/>
        <line x1={9 + i*2} y1="17.5" x2={9 + i*2} y2="20.5" stroke={s} strokeWidth={sw}/>
        <line x1="3.5" y1={9 + i*2} x2="6.5" y2={9 + i*2} stroke={s} strokeWidth={sw}/>
        <line x1="17.5" y1={9 + i*2} x2="20.5" y2={9 + i*2} stroke={s} strokeWidth={sw}/>
      </g>))}
    </svg>);
    default: return null;
  }
}

function SideRail({ active, onChange, compact }) {
  const W = 88;
  return (
    <div style={{
      width: W, flexShrink: 0, height: '100%',
      background: 'linear-gradient(180deg, #0B0C18 0%, #0A0B1A 100%)',
      borderRight: `1px solid ${R.hairline}`,
      display:'flex', flexDirection:'column', alignItems:'center',
      paddingTop: 24, paddingBottom: 16, position:'relative',
    }}>
      {/* Logo glyph */}
      <div style={{ marginBottom: 28 }}>
        <ResonanceMark size={36} />
      </div>
      {/* nav items */}
      <div style={{ display:'flex', flexDirection:'column', gap: 4, width:'100%' }}>
        {NAV.map(n => {
          const isActive = active === n.id;
          return (
            <div key={n.id} onClick={() => onChange?.(n.id)} style={{
              padding: '14px 0', display:'flex', flexDirection:'column', alignItems:'center', gap:8,
              cursor:'pointer', position:'relative',
              background: isActive ? 'linear-gradient(90deg, rgba(125,249,255,0.06) 0%, rgba(125,249,255,0) 100%)' : 'transparent',
            }}>
              {isActive && <div style={{
                position:'absolute', left:0, top:8, bottom:8, width:2,
                background: GRAD, borderRadius: 2, boxShadow: '0 0 8px rgba(168,85,247,0.6)',
              }}/>}
              <NavIcon kind={n.icon} active={isActive}/>
              <div style={{
                fontFamily: F.mono, fontSize: 9, letterSpacing: '0.18em',
                color: isActive ? R.phosphor : R.dim,
              }}>{n.label}</div>
            </div>
          );
        })}
      </div>
      <div style={{ marginTop:'auto', display:'flex', flexDirection:'column', alignItems:'center', gap:8 }}>
        <div style={{ fontFamily:F.mono, fontSize:8, color:R.faint, letterSpacing:'0.2em' }}>v0.9.1</div>
        <Reticle size={14} color={R.dim} opacity={0.4}/>
      </div>
    </div>
  );
}

// Brand mark — the Resonance glyph: a phase wave inside a circle
function ResonanceMark({ size=40, animated=false }) {
  const id = React.useId();
  return (
    <svg width={size} height={size} viewBox="0 0 40 40">
      <defs>
        <linearGradient id={`g-${id}`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%"  stopColor="#6366F1"/>
          <stop offset="50%" stopColor="#A855F7"/>
          <stop offset="100%" stopColor="#EC4899"/>
        </linearGradient>
        <filter id={`glow-${id}`}><feGaussianBlur stdDeviation="0.8"/></filter>
      </defs>
      <circle cx="20" cy="20" r="18" stroke={`url(#g-${id})`} strokeWidth="1.4" fill="none"/>
      <path d="M5 20 C 9 12, 12 28, 16 20 S 22 12, 26 20 S 31 28, 35 20"
            stroke={`url(#g-${id})`} strokeWidth="2.2" fill="none" strokeLinecap="round"
            filter={`url(#glow-${id})`}/>
      <circle cx="20" cy="20" r="1.6" fill="#EC4899"/>
    </svg>
  );
}

// ─────────────────────────────────────────────────────────────
// HeaderBar — phase-line strip + scene meta + render button
// ─────────────────────────────────────────────────────────────
function HeaderBar({ width, scene, onRender, running }) {
  return (
    <div style={{
      width:'100%', height: 76, flexShrink:0,
      borderBottom: `1px solid ${R.hairline}`,
      background: 'linear-gradient(180deg, rgba(17,19,42,0.6) 0%, rgba(11,12,24,0.6) 100%)',
      backdropFilter:'blur(20px)',
      display:'flex', alignItems:'center', padding: '0 20px', gap: 20,
      position:'relative', overflow:'hidden',
    }}>
      {/* phase line backdrop */}
      <div style={{ position:'absolute', left:0, right:0, top:0, bottom:0, opacity:0.35, pointerEvents:'none' }}>
        <PhaseLine width={width} height={76} amp={6} freq={0.012} speed={0.4} color={R.traceDim} glow={false} ticks={false}/>
      </div>
      {/* left: scene */}
      <div style={{ display:'flex', alignItems:'center', gap: 14, position:'relative', zIndex:1 }}>
        <div style={{
          width:46, height:46, borderRadius: 10,
          border:`1px solid ${R.hairBright}`, background:R.deep,
          display:'flex', alignItems:'center', justifyContent:'center', position:'relative', overflow:'hidden',
        }}>
          <div style={{ transform:'scale(0.45)' }}>
            {scene === 'sine' && <ScenePreview_Sine w={100} h={70}/>}
            {scene === 'pythag' && <ScenePreview_Pythag w={100} h={70}/>}
            {scene === 'fourier' && <ScenePreview_Fourier w={100} h={70}/>}
          </div>
        </div>
        <div>
          <div style={{ display:'flex', alignItems:'center', gap:8 }}>
            <span style={{ fontFamily:F.mono, fontSize:10, color:R.dim, letterSpacing:'0.2em' }}>SCENE · 03</span>
            <span style={{ width:3,height:3, background:R.faint, borderRadius:3 }}/>
            <span style={{ fontFamily:F.mono, fontSize:10, color:R.dim, letterSpacing:'0.15em' }}>1920×1080 · 60fps</span>
          </div>
          <div style={{ fontFamily:F.display, fontSize:20, color:R.phosphor, letterSpacing:'-0.01em', marginTop:2 }}>
            Fourier Squares
          </div>
        </div>
      </div>
      {/* center: phase indicator */}
      <div style={{ flex:1, display:'flex', alignItems:'center', justifyContent:'center', gap:18, position:'relative', zIndex:1 }}>
        <ReadoutChip label="DURATION" value="00:08.32"/>
        <ReadoutChip label="FRAMES" value="499"/>
        <ReadoutChip label="QUALITY" value="HIGH"/>
        <ReadoutChip label="GPU" value="ON" hot/>
      </div>
      {/* right: actions */}
      <div style={{ display:'flex', alignItems:'center', gap:10, position:'relative', zIndex:1 }}>
        <CircleAction label="Preview"/>
        <CircleAction label="Stop"/>
        <RenderTrigger size={56} running={running} onClick={onRender}/>
      </div>
    </div>
  );
}

function ReadoutChip({ label, value, hot }) {
  return (
    <div style={{ display:'flex', flexDirection:'column', alignItems:'flex-start', gap:2 }}>
      <div style={{ fontFamily:F.mono, fontSize:9, color:R.faint, letterSpacing:'0.2em' }}>{label}</div>
      <div style={{
        fontFamily:F.mono, fontSize:13, color: hot ? R.trace : R.phosphor,
        letterSpacing:'0.05em', fontVariantNumeric:'tabular-nums',
        textShadow: hot ? `0 0 8px ${R.trace}` : 'none',
      }}>{value}</div>
    </div>
  );
}

function CircleAction({ label }) {
  return (
    <div style={{
      width: 38, height: 38, borderRadius: 38,
      border:`1px solid ${R.hairline}`, background:'rgba(255,255,255,0.02)',
      display:'flex', alignItems:'center', justifyContent:'center',
      fontFamily:F.mono, fontSize:8, color:R.ion, letterSpacing:'0.16em',
      cursor:'pointer',
    }}>{label.slice(0,4).toUpperCase()}</div>
  );
}

// ─────────────────────────────────────────────────────────────
// RenderTrigger — THE hero button. Concentric reticle + glow.
// ─────────────────────────────────────────────────────────────
function RenderTrigger({ size=120, running=false, onClick, label='RENDER' }) {
  const [hover, setHover] = React.useState(false);
  const ringRef = React.useRef(null);
  React.useEffect(() => {
    const c = ringRef.current; if (!c) return;
    const ctx = c.getContext('2d');
    const dpr = Math.min(window.devicePixelRatio||1, 2);
    c.width = size*dpr; c.height = size*dpr; ctx.scale(dpr,dpr);
    let raf, t0 = performance.now();
    const loop = (now) => {
      const t = (now - t0)/1000;
      ctx.clearRect(0,0,size,size);
      const cx = size/2, cy = size/2;
      // pulsing outer ring
      const pulse = (Math.sin(t*1.6) + 1) / 2;
      ctx.strokeStyle = `rgba(168,85,247,${0.2 + pulse*0.3})`;
      ctx.lineWidth = 1; ctx.beginPath();
      ctx.arc(cx, cy, size/2 - 2 - pulse*2, 0, Math.PI*2); ctx.stroke();
      // tick marks
      const ticks = 60;
      for (let i=0;i<ticks;i++) {
        const a = (i/ticks)*Math.PI*2 - Math.PI/2;
        const r0 = size/2 - 10, r1 = size/2 - (i%5===0 ? 14 : 12);
        ctx.strokeStyle = i%5===0 ? 'rgba(190,200,255,0.4)' : 'rgba(190,200,255,0.15)';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(cx + Math.cos(a)*r0, cy + Math.sin(a)*r0);
        ctx.lineTo(cx + Math.cos(a)*r1, cy + Math.sin(a)*r1);
        ctx.stroke();
      }
      // running: animated sweep
      if (running) {
        const sw = (t*0.8) % 1;
        ctx.strokeStyle = '#7DF9FF'; ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(cx, cy, size/2 - 4, -Math.PI/2, -Math.PI/2 + sw*Math.PI*2);
        ctx.shadowColor = '#7DF9FF'; ctx.shadowBlur = 10; ctx.stroke(); ctx.shadowBlur = 0;
      }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [size, running]);

  const inner = size - 28;
  return (
    <div onClick={onClick} onMouseEnter={()=>setHover(true)} onMouseLeave={()=>setHover(false)} style={{
      width: size, height: size, position:'relative', cursor:'pointer',
      transform: hover ? 'scale(1.03)' : 'scale(1)', transition:'transform 200ms cubic-bezier(.2,.7,.2,1.1)',
    }}>
      <canvas ref={ringRef} style={{ position:'absolute', inset:0, width:size, height:size }}/>
      <div style={{
        position:'absolute', left:(size-inner)/2, top:(size-inner)/2, width:inner, height:inner,
        borderRadius:inner, background: GRAD,
        display:'flex', alignItems:'center', justifyContent:'center', flexDirection:'column',
        boxShadow:`0 0 ${hover?48:32}px rgba(168,85,247,0.55), inset 0 0 ${size/3}px rgba(255,255,255,0.18), inset 0 -${size/8}px ${size/4}px rgba(0,0,0,0.4)`,
      }}>
        {running ? (
          <>
            <div style={{ fontFamily:F.mono, fontSize: size*0.085, letterSpacing:'0.18em', color:'#fff', opacity:0.95 }}>STOP</div>
            <div style={{ width: size*0.18, height:2, background:'#fff', marginTop:4, borderRadius:2 }}/>
          </>
        ) : (
          <>
            <div style={{ fontFamily:F.display, fontSize: size*0.18, fontWeight:600, letterSpacing:'-0.02em', color:'#fff' }}>▶</div>
            <div style={{ fontFamily:F.mono, fontSize: size*0.085, letterSpacing:'0.22em', color:'#fff', opacity:0.95, marginTop:2 }}>{label}</div>
          </>
        )}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// SceneCard — Gallery card
// ─────────────────────────────────────────────────────────────
function SceneCard({ idx, title, subtitle, formula, Preview, accent, onPick }) {
  const [hover, setHover] = React.useState(false);
  return (
    <div onMouseEnter={()=>setHover(true)} onMouseLeave={()=>setHover(false)} onClick={onPick} style={{
      width: '100%', borderRadius: 16, cursor:'pointer',
      background: 'linear-gradient(180deg, rgba(24,27,58,0.6) 0%, rgba(11,12,24,0.8) 100%)',
      border: `1px solid ${hover ? R.hairBright : R.hairline}`,
      position:'relative', overflow:'hidden',
      transition:'border-color 200ms, transform 200ms',
      transform: hover ? 'translateY(-2px)' : 'none',
    }}>
      <CornerBrackets inset={10} len={12} color={accent || R.ion} opacity={hover ? 0.7 : 0.3}/>
      {/* preview area */}
      <div style={{
        height: 188, position:'relative',
        background: `radial-gradient(circle at 50% 60%, rgba(99,102,241,0.08) 0%, transparent 60%), ${R.void}`,
        borderBottom: `1px solid ${R.hairline}`,
      }}>
        <Preview w={260} h={188}/>
        {/* index */}
        <div style={{
          position:'absolute', top:10, left:14,
          fontFamily:F.mono, fontSize:10, letterSpacing:'0.2em', color:R.dim,
        }}>{String(idx).padStart(2,'0')} / 06</div>
        {/* status */}
        <div style={{ position:'absolute', top:10, right:14, display:'flex', gap:6, alignItems:'center' }}>
          <span style={{ width:5,height:5, background:R.green, borderRadius:5, boxShadow:`0 0 6px ${R.green}` }}/>
          <span style={{ fontFamily:F.mono, fontSize:9, color:R.ion, letterSpacing:'0.18em' }}>READY</span>
        </div>
      </div>
      {/* meta */}
      <div style={{ padding: '14px 16px 16px' }}>
        <div style={{ fontFamily:F.display, fontSize: 17, color:R.phosphor, letterSpacing:'-0.005em' }}>{title}</div>
        <div style={{ fontFamily:F.ui, fontSize: 12, color:R.ion, marginTop:4, lineHeight:1.45 }}>{subtitle}</div>
        <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginTop: 12 }}>
          <span style={{ fontFamily:F.mono, fontSize: 10.5, color:R.trace, letterSpacing:'0.05em' }}>{formula}</span>
          <span style={{ fontFamily:F.mono, fontSize: 9, color:R.dim, letterSpacing:'0.18em' }}>LOAD →</span>
        </div>
      </div>
    </div>
  );
}

const SCENES = [
  { id:'hello',   title:'Hello Manim',          subtitle:'A traced-pen wordmark — the first scene every Manim project earns.',  formula:'manim.Write(text)',         Preview: ScenePreview_Hello,   accent:'#A855F7' },
  { id:'pythag',  title:'Pythagorean Theorem',  subtitle:'Three squares stage themselves on the legs and hypotenuse.',          formula:'a² + b² = c²',              Preview: ScenePreview_Pythag,  accent:'#6366F1' },
  { id:'sine',    title:'Sine Wave',            subtitle:'A unit-circle trace projected onto its phase axis.',                  formula:'y = sin(x)',                Preview: ScenePreview_Sine,    accent:'#7DF9FF' },
  { id:'fourier', title:'Fourier Squares',      subtitle:'Five rotating epicycles approximate a square wave.',                  formula:'Σ (4/πn)·sin(nωt)',         Preview: ScenePreview_Fourier, accent:'#EC4899' },
  { id:'morph',   title:'Circle ↔ Square',      subtitle:'A 64-point polygon interpolates between two parents.',                 formula:'lerp(◯, ▢, t)',             Preview: ScenePreview_Morph,   accent:'#A855F7' },
  { id:'graph',   title:'Graph Traversal',      subtitle:'Depth-first walk over a planar graph, highlighting each visited edge.', formula:'DFS(G, v₀)',              Preview: ScenePreview_Graph,   accent:'#EC4899' },
];

// ─────────────────────────────────────────────────────────────
// Gallery — iPad
// ─────────────────────────────────────────────────────────────
function Gallery({ width=1112, height=834, onPick }) {
  return (
    <div style={{ width, height, background: R.void, color: R.phosphor, display:'flex', overflow:'hidden', fontFamily:F.ui }}>
      <SideRail active="gallery"/>
      <div style={{ flex:1, display:'flex', flexDirection:'column', overflow:'hidden' }}>
        {/* phase-line strip (signature) */}
        <div style={{ height: 48, borderBottom:`1px solid ${R.hairline}`, position:'relative',
          background: 'linear-gradient(180deg, rgba(17,19,42,0.4), rgba(11,12,24,0.4))',
          display:'flex', alignItems:'center', padding:'0 24px', gap: 16,
        }}>
          <div style={{ position:'absolute', inset:0, opacity:0.5 }}>
            <PhaseLine width={width-88} height={48} amp={7} freq={0.018} speed={0.5} color={R.traceDim} glow={false}/>
          </div>
          <div style={{ position:'relative', zIndex:1, fontFamily:F.mono, fontSize:10, letterSpacing:'0.3em', color:R.phosphor }}>
            RESONANCE · MATHEMATICAL ANIMATION STUDIO
          </div>
          <div style={{ position:'relative', zIndex:1, marginLeft:'auto', display:'flex', gap:14, alignItems:'center' }}>
            <Tag color={R.green}>GPU READY</Tag>
            <Tag color={R.amber}>PYTHON 3.14</Tag>
            <Tag>MANIM 0.18</Tag>
          </div>
        </div>
        {/* hero band */}
        <div style={{ padding:'36px 48px 22px', display:'flex', alignItems:'flex-end', gap: 28 }}>
          <div style={{ flex:1 }}>
            <div style={{ fontFamily:F.mono, fontSize:11, letterSpacing:'0.28em', color:R.trace, marginBottom:14 }}>
              ◍  GALLERY · 06 SCENES
            </div>
            <div style={{ fontFamily:F.display, fontSize: 52, lineHeight:1.0, letterSpacing:'-0.02em', color:R.phosphor, textWrap:'pretty' }}>
              Pick a scene. <span style={{
                background: GRAD, WebkitBackgroundClip:'text', backgroundClip:'text', color:'transparent',
              }}>Render in seconds.</span>
            </div>
            <div style={{ fontFamily:F.ui, fontSize: 15, color: R.ion, marginTop: 14, maxWidth: 620, lineHeight:1.5 }}>
              Each template ships as a fully-formed Manim scene — drop it onto the workbench, tweak its parameters, and fire the encoder.
            </div>
          </div>
          <div style={{ display:'flex', flexDirection:'column', alignItems:'flex-end', gap: 10 }}>
            <RenderTrigger size={104} label="NEW SCENE"/>
            <div style={{ fontFamily:F.mono, fontSize:10, color:R.dim, letterSpacing:'0.18em' }}>BLANK · py</div>
          </div>
        </div>
        {/* grid */}
        <div style={{ padding:'8px 48px 48px', overflowY:'auto', flex:1 }}>
          <div style={{ display:'grid', gridTemplateColumns:'repeat(3, 1fr)', gap: 20 }}>
            {SCENES.map((s, i) => (
              <SceneCard key={s.id} idx={i+1} {...s} onPick={() => onPick?.(s.id)}/>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// Workspace — preview-hero. Editor + log are drawer panels.
// ─────────────────────────────────────────────────────────────
function Workspace({ width=1112, height=834, openDrawer='preview', onRender, running }) {
  const drawerOpen = openDrawer === 'editor' || openDrawer === 'log';
  return (
    <div style={{ width, height, background: R.void, color: R.phosphor, display:'flex', overflow:'hidden', fontFamily:F.ui }}>
      <SideRail active="workspace"/>
      <div style={{ flex:1, display:'flex', flexDirection:'column', overflow:'hidden' }}>
        <HeaderBar width={width-88} scene="fourier" running={running} onRender={onRender}/>
        {/* preview hero */}
        <div style={{ flex:1, position:'relative', display:'flex', overflow:'hidden' }}>
          {/* scene strip (left) */}
          <div style={{ width: 72, borderRight:`1px solid ${R.hairline}`, padding:'12px 0', display:'flex', flexDirection:'column', alignItems:'center', gap:10, background:R.deep }}>
            {SCENES.map((s,i) => (
              <div key={s.id} style={{
                width: 50, height: 36, borderRadius: 6, overflow:'hidden', position:'relative',
                border: `1px solid ${i===3 ? R.trace : R.hairline}`,
                boxShadow: i===3 ? `0 0 12px rgba(125,249,255,0.4)` : 'none',
              }}>
                <div style={{ transform:'scale(0.2)', transformOrigin:'top left', width:'500%', height:'500%' }}>
                  <s.Preview w={250} h={180}/>
                </div>
              </div>
            ))}
            <div style={{ marginTop:'auto', fontFamily:F.mono, fontSize:9, color:R.dim, letterSpacing:'0.15em' }}>+ ADD</div>
          </div>
          {/* center stage */}
          <div style={{ flex:1, display:'flex', flexDirection:'column', overflow:'hidden', background: R.void, position:'relative' }}>
            <PreviewStage width={width-88-72-260} height={drawerOpen ? height-76-48-260 : height-76-48-90} running={running}/>
            <Transport drawerOpen={drawerOpen} openDrawer={openDrawer}/>
            {drawerOpen && (
              openDrawer === 'editor'
                ? <EditorDrawer height={260}/>
                : <RenderLogDrawer height={260} running={running}/>
            )}
          </div>
          {/* right rail — render controls */}
          <ControlsRail/>
        </div>
      </div>
    </div>
  );
}

function PreviewStage({ width, height, running }) {
  // 16:9 letterboxed
  const stageH = Math.min(height - 40, (width - 80) * 9/16);
  const stageW = stageH * 16/9;
  return (
    <div style={{ flex:1, display:'flex', alignItems:'center', justifyContent:'center', position:'relative', padding: 24 }}>
      {/* grid backdrop */}
      <div style={{
        position:'absolute', inset:0,
        backgroundImage:
          'linear-gradient(rgba(125,249,255,0.04) 1px, transparent 1px), linear-gradient(90deg, rgba(125,249,255,0.04) 1px, transparent 1px)',
        backgroundSize: '32px 32px',
        maskImage:'radial-gradient(ellipse at center, black 30%, transparent 75%)',
      }}/>
      {/* coord readouts */}
      <CoordReadouts/>
      <div style={{ width: stageW, height: stageH, position:'relative',
        background: '#0A0B16', borderRadius: 6,
        border:`1px solid ${R.hairBright}`,
        boxShadow:'0 30px 80px rgba(0,0,0,0.6), 0 0 0 1px rgba(125,249,255,0.05), inset 0 0 80px rgba(99,102,241,0.05)',
        overflow:'hidden',
      }}>
        <CornerBrackets inset={6} len={14} color={R.trace} opacity={0.6}/>
        <div style={{ transform:'scale(2.2)', transformOrigin:'center', width:'100%', height:'100%', display:'flex', alignItems:'center', justifyContent:'center' }}>
          <ScenePreview_Fourier w={stageW*0.5} h={stageH*0.5}/>
        </div>
        {/* viewport meta */}
        <div style={{ position:'absolute', top:10, left:14, fontFamily:F.mono, fontSize:10, color:R.ion, letterSpacing:'0.16em' }}>
          ▢ 1920 × 1080 · 60 FPS
        </div>
        <div style={{ position:'absolute', top:10, right:14, fontFamily:F.mono, fontSize:10, color:R.trace, letterSpacing:'0.16em' }}>
          ◉ LIVE PREVIEW
        </div>
        <div style={{ position:'absolute', bottom:10, left:14, fontFamily:F.mono, fontSize:10, color:R.dim, letterSpacing:'0.12em' }}>
          FRAME 247 / 499
        </div>
        <div style={{ position:'absolute', bottom:10, right:14, fontFamily:F.mono, fontSize:10, color:R.dim, letterSpacing:'0.12em' }}>
          t = 4.12 s
        </div>
      </div>
    </div>
  );
}

function CoordReadouts() {
  return (
    <>
      {/* top axis ticks */}
      <div style={{ position:'absolute', top:8, left:80, right:80, height:14, display:'flex', justifyContent:'space-between', pointerEvents:'none' }}>
        {Array.from({length:9}).map((_,i)=>(
          <div key={i} style={{ width:1, height: i%2===0 ? 8:4, background:R.faint }}/>
        ))}
      </div>
      <div style={{ position:'absolute', top:24, left:80, fontFamily:F.mono, fontSize:9, color:R.faint, letterSpacing:'0.12em' }}>−8</div>
      <div style={{ position:'absolute', top:24, right:80, fontFamily:F.mono, fontSize:9, color:R.faint, letterSpacing:'0.12em' }}>+8</div>
    </>
  );
}

function Transport({ drawerOpen, openDrawer }) {
  const tabStyle = (active) => ({
    padding:'10px 18px', fontFamily:F.mono, fontSize:11, letterSpacing:'0.18em',
    color: active ? R.phosphor : R.dim, cursor:'pointer',
    borderTop: active ? `1px solid ${R.trace}` : `1px solid transparent`,
    background: active ? 'linear-gradient(180deg, rgba(125,249,255,0.06), transparent)' : 'transparent',
  });
  return (
    <div style={{
      height: drawerOpen ? 42 : 90, flexShrink:0,
      borderTop:`1px solid ${R.hairline}`, background: R.deep,
      display:'flex', flexDirection:'column',
    }}>
      {/* tab bar */}
      <div style={{ display:'flex', height:36, borderBottom:`1px solid ${R.hairline}`, alignItems:'flex-end' }}>
        <div style={tabStyle(openDrawer==='preview')}>◉ PREVIEW</div>
        <div style={tabStyle(openDrawer==='editor')}>▤ SCENE.PY</div>
        <div style={tabStyle(openDrawer==='log')}>≋ RENDER LOG</div>
        <div style={{ marginLeft:'auto', display:'flex', gap:14, alignItems:'center', padding:'0 18px' }}>
          <span style={{ fontFamily:F.mono, fontSize:10, color:R.dim, letterSpacing:'0.18em' }}>00:04.12 / 00:08.32</span>
          <Reticle size={12} color={R.dim}/>
        </div>
      </div>
      {!drawerOpen && (
        <div style={{ flex:1, display:'flex', alignItems:'center', padding:'0 24px', gap:14 }}>
          <button style={iconBtn}>⏮</button>
          <button style={iconBtn}>⏵</button>
          <button style={iconBtn}>⏭</button>
          <div style={{ flex:1, height: 6, borderRadius: 6, background: 'rgba(125,249,255,0.08)', position:'relative', overflow:'hidden' }}>
            <div style={{ position:'absolute', left:0, top:0, bottom:0, width:'48%', background: GRAD, borderRadius:6 }}/>
            <div style={{ position:'absolute', left:'48%', top:-6, width:2, height:18, background:R.trace, boxShadow:`0 0 8px ${R.trace}` }}/>
            {/* keyframes */}
            {[0.12,0.28,0.4,0.6,0.78,0.92].map((p,i)=>(
              <div key={i} style={{ position:'absolute', left:`${p*100}%`, top:-2, width:1, height:10, background:R.dim }}/>
            ))}
          </div>
          <div style={{ fontFamily:F.mono, fontSize:11, color:R.phosphor, letterSpacing:'0.05em', minWidth:90, textAlign:'right' }}>FRAME 247</div>
        </div>
      )}
    </div>
  );
}
const iconBtn = {
  width:34, height:34, borderRadius:34, border:`1px solid ${R.hairline}`,
  background:'transparent', color:R.phosphor, fontFamily:F.ui, fontSize:14, cursor:'pointer',
  display:'flex', alignItems:'center', justifyContent:'center',
};

function EditorDrawer({ height }) {
  const lines = [
    ['from manim import *', 'kw'],
    ['', null],
    ['class FourierSquare(Scene):', 'def'],
    ['    def construct(self):', 'def'],
    ['        N = 5', 'num'],
    ['        circles = VGroup()', 'var'],
    ['        for k in range(N):', 'kw'],
    ['            n = 2*k + 1', 'num'],
    ['            r = 4/(PI*n)', 'num'],
    ['            c = Circle(radius=r, stroke_color=BLUE)', 'var'],
    ['            circles.add(c)', null],
    ['        self.play(Create(circles), run_time=2)', null],
    ['        self.wait()', null],
  ];
  return (
    <div style={{ height, flexShrink:0, background:'#08091A', borderTop:`1px solid ${R.hairline}`, display:'flex', overflow:'hidden' }}>
      {/* gutter */}
      <div style={{ width: 42, background: R.deep, borderRight:`1px solid ${R.hairline}`, padding:'10px 0',
        fontFamily:F.mono, fontSize:10.5, color:R.faint, lineHeight: '18px', textAlign:'right', paddingRight:8 }}>
        {lines.map((_,i)=> <div key={i}>{i+1}</div>)}
      </div>
      <div style={{ flex:1, padding:'10px 14px', fontFamily:F.mono, fontSize:11.5, lineHeight: '18px', color:R.phosphor }}>
        {lines.map((l,i)=> (
          <div key={i} style={{ whiteSpace:'pre' }}>
            <SyntaxLine text={l[0]}/>
          </div>
        ))}
      </div>
      <div style={{ width: 180, borderLeft:`1px solid ${R.hairline}`, padding:'12px 14px',
        background:R.deep, fontFamily:F.mono, fontSize:10, color:R.dim, letterSpacing:'0.12em' }}>
        <div style={{ color:R.trace, marginBottom:10 }}>◍ OUTLINE</div>
        <div style={{ color:R.phosphor, marginBottom:6 }}>▾ FourierSquare</div>
        <div style={{ paddingLeft: 12, marginBottom: 4 }}>· construct()</div>
        <div style={{ paddingLeft: 24, marginBottom: 4 }}>circles</div>
        <div style={{ paddingLeft: 24, marginBottom: 12 }}>play()</div>
        <div style={{ color:R.trace, marginBottom:10 }}>◍ IMPORTS</div>
        <div style={{ paddingLeft: 12 }}>manim</div>
      </div>
    </div>
  );
}
function SyntaxLine({ text }) {
  // simple python-ish highlighter
  const KW = ['from','import','class','def','for','in','range','return','self'];
  const tokens = text.split(/(\s+|[(),:=])/);
  return tokens.map((tok, i) => {
    let color = R.phosphor;
    if (KW.includes(tok)) color = '#A855F7';
    else if (/^[A-Z][A-Za-z]+$/.test(tok)) color = R.trace;
    else if (/^\d+(\.\d+)?$/.test(tok)) color = R.amber;
    else if (/^[a-z_]+\(/.test(tok)) color = '#EC4899';
    else if (tok === '#') color = R.dim;
    return <span key={i} style={{ color }}>{tok}</span>;
  });
}

function RenderLogDrawer({ height, running }) {
  const lines = [
    ['12:04:18.302', 'INFO', 'Loaded scene  FourierSquare  from /scenes/fourier.py'],
    ['12:04:18.418', 'INFO', 'Resolution    1920 × 1080  @  60 fps'],
    ['12:04:18.480', 'INFO', 'Codec         h.264 (VideoToolbox)'],
    ['12:04:18.520', 'INFO', 'GPU pipeline  Metal  (M3, 10-core)'],
    ['12:04:18.560', 'OK',   'Cairo backend ready'],
    ['12:04:18.624', 'OK',   'TeX kernel    busytex / xelatex'],
    ['12:04:19.012', 'INFO', 'Vector pass   ▸  begin'],
    ['12:04:21.481', 'OK',   'Vector pass   ▸  done  (2.47s · 499 frames)'],
    ['12:04:21.610', 'INFO', 'Raster pass   ▸  begin'],
    ['12:04:25.802', 'INFO', 'Raster pass   ▸  247 / 499 frames'],
  ];
  return (
    <div style={{ height, flexShrink:0, background:'#06070F', borderTop:`1px solid ${R.hairline}`, padding:'14px 18px',
      fontFamily:F.mono, fontSize:11.5, color:R.phosphor, lineHeight:'20px', overflow:'hidden' }}>
      {lines.map(([t,lv,msg],i)=>(
        <div key={i} style={{ display:'flex', gap:14 }}>
          <span style={{ color:R.faint }}>{t}</span>
          <span style={{ color: lv==='OK'?R.green : lv==='ERR'?R.red : R.trace, width:36 }}>{lv}</span>
          <span style={{ color:R.ion }}>{msg}</span>
        </div>
      ))}
      {running && <div style={{ marginTop:6, color: R.trace, display:'flex', gap:6, alignItems:'center' }}>
        <span style={{ width:6,height:6, borderRadius:6, background:R.trace, boxShadow:`0 0 6px ${R.trace}`}}/>
        rendering…
      </div>}
    </div>
  );
}

function ControlsRail() {
  return (
    <div style={{ width: 260, flexShrink:0, borderLeft:`1px solid ${R.hairline}`, background:R.deep,
      display:'flex', flexDirection:'column' }}>
      <div style={{ padding:'16px 18px 12px', borderBottom:`1px solid ${R.hairline}` }}>
        <div style={{ fontFamily:F.mono, fontSize:10, letterSpacing:'0.24em', color:R.trace }}>◍ INSTRUMENT</div>
        <div style={{ fontFamily:F.display, fontSize:17, color:R.phosphor, marginTop:6 }}>Render settings</div>
      </div>
      {/* Quality dial */}
      <div style={{ padding:'18px 18px 8px' }}>
        <DialControl label="QUALITY" value="HIGH" pct={0.72} options={['LOW','MED','HIGH','4K']} selected={2}/>
      </div>
      <div style={{ padding:'6px 18px 14px', display:'flex', flexDirection:'column', gap: 12 }}>
        <Slider label="FRAME RATE" value="60 fps" pct={1.0}/>
        <Slider label="RESOLUTION" value="1920 × 1080" pct={0.65}/>
        <Slider label="MOTION BLUR" value="2 samples" pct={0.25}/>
      </div>
      <div style={{ padding:'12px 18px', borderTop:`1px solid ${R.hairline}` }}>
        <Toggle label="GPU ACCELERATION" sublabel="Metal · M3" on/>
        <Toggle label="TRANSPARENCY"     sublabel="rgba export"      on={false}/>
        <Toggle label="LATEX PIPELINE"   sublabel="busytex · xelatex" on/>
      </div>
      <div style={{ padding:'14px 18px', borderTop:`1px solid ${R.hairline}`, marginTop:'auto' }}>
        <div style={{ fontFamily:F.mono, fontSize:9.5, color:R.faint, letterSpacing:'0.18em', marginBottom:10 }}>OUTPUT</div>
        <div style={{ fontFamily:F.mono, fontSize:11, color:R.phosphor }}>FourierSquare_v07.mp4</div>
        <div style={{ fontFamily:F.mono, fontSize:10, color:R.dim, marginTop:4 }}>≈ 18 MB · h.264 · 60 fps</div>
      </div>
    </div>
  );
}

function DialControl({ label, value, pct, options, selected }) {
  // half-circle dial
  const r = 64; const a0 = Math.PI*1.15, a1 = Math.PI*1.85;
  const a = a0 + (a1-a0)*pct;
  const cx = r+10, cy = r+10;
  return (
    <div>
      <div style={{ fontFamily:F.mono, fontSize:9.5, color:R.faint, letterSpacing:'0.18em', marginBottom:8 }}>{label}</div>
      <div style={{ display:'flex', alignItems:'center', gap:14 }}>
        <svg width={r*2+20} height={r+30} viewBox={`0 0 ${r*2+20} ${r+30}`}>
          <defs>
            <linearGradient id="dgrad" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor="#6366F1"/><stop offset="50%" stopColor="#A855F7"/><stop offset="100%" stopColor="#EC4899"/>
            </linearGradient>
          </defs>
          {/* track */}
          <path d={`M ${cx + r*Math.cos(a0)} ${cy + r*Math.sin(a0)} A ${r} ${r} 0 0 1 ${cx + r*Math.cos(a1)} ${cy + r*Math.sin(a1)}`}
            stroke="rgba(190,200,255,0.12)" strokeWidth="6" fill="none" strokeLinecap="round"/>
          <path d={`M ${cx + r*Math.cos(a0)} ${cy + r*Math.sin(a0)} A ${r} ${r} 0 0 1 ${cx + r*Math.cos(a)} ${cy + r*Math.sin(a)}`}
            stroke="url(#dgrad)" strokeWidth="6" fill="none" strokeLinecap="round"/>
          {/* tick labels */}
          {options.map((o,i)=>{
            const ta = a0 + (a1-a0)*(i/(options.length-1));
            const tx = cx + (r+12)*Math.cos(ta), ty = cy + (r+12)*Math.sin(ta);
            return <text key={o} x={tx} y={ty} textAnchor="middle" dominantBaseline="middle"
              fontFamily={F.mono} fontSize="8" fill={i===selected ? R.trace : R.dim} letterSpacing="0.15em">{o}</text>;
          })}
          {/* indicator */}
          <line x1={cx} y1={cy} x2={cx + (r-10)*Math.cos(a)} y2={cy + (r-10)*Math.sin(a)} stroke={R.trace} strokeWidth="2" strokeLinecap="round"/>
          <circle cx={cx} cy={cy} r="4" fill={R.trace} style={{ filter:'drop-shadow(0 0 4px #7DF9FF)' }}/>
        </svg>
      </div>
      <div style={{ fontFamily:F.display, fontSize:18, color:R.phosphor, marginTop:-6 }}>{value}</div>
    </div>
  );
}
function Slider({ label, value, pct }) {
  return (
    <div>
      <div style={{ display:'flex', justifyContent:'space-between', marginBottom:6 }}>
        <span style={{ fontFamily:F.mono, fontSize:9.5, color:R.faint, letterSpacing:'0.18em' }}>{label}</span>
        <span style={{ fontFamily:F.mono, fontSize:10, color:R.phosphor }}>{value}</span>
      </div>
      <div style={{ height: 3, background: 'rgba(190,200,255,0.10)', borderRadius:3, position:'relative' }}>
        <div style={{ position:'absolute', left:0, top:0, bottom:0, width:`${pct*100}%`, background: GRAD, borderRadius:3 }}/>
        <div style={{ position:'absolute', left:`${pct*100}%`, top:-3, width:9, height:9, marginLeft:-4, borderRadius:9, background:R.phosphor, boxShadow:`0 0 6px ${R.trace}` }}/>
      </div>
    </div>
  );
}
function Toggle({ label, sublabel, on }) {
  return (
    <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', padding:'8px 0' }}>
      <div>
        <div style={{ fontFamily:F.ui, fontSize:12, color:R.phosphor }}>{label}</div>
        <div style={{ fontFamily:F.mono, fontSize:9.5, color:R.dim, letterSpacing:'0.14em', marginTop:2 }}>{sublabel}</div>
      </div>
      <div style={{
        width: 36, height: 20, borderRadius: 20, position:'relative',
        background: on ? GRAD : 'rgba(190,200,255,0.10)', border:`1px solid ${on ? 'transparent' : R.hairline}`,
      }}>
        <div style={{
          position:'absolute', top:1, left: on ? 17 : 1, width:16, height:16, borderRadius:16,
          background: '#fff', boxShadow:'0 1px 4px rgba(0,0,0,0.4)',
        }}/>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// Render-in-progress takeover
// ─────────────────────────────────────────────────────────────
function RenderState({ width=1112, height=834, pct=0.49 }) {
  const total = 499; const cur = Math.floor(total*pct);
  return (
    <div style={{ width, height, background: R.void, color: R.phosphor, fontFamily:F.ui, position:'relative', overflow:'hidden' }}>
      {/* particle bg */}
      <div style={{ position:'absolute', inset:0 }}><ParticleField w={width} h={height} density={0.7}/></div>
      {/* huge phase line */}
      <div style={{ position:'absolute', left:0, right:0, top: height/2 - 110, opacity:0.4 }}>
        <PhaseLine width={width} height={120} amp={36} freq={0.008} speed={1.4} color={R.trace} glow ticks={false}/>
      </div>
      {/* header */}
      <div style={{ position:'absolute', top:24, left:32, right:32, display:'flex', alignItems:'center', justifyContent:'space-between' }}>
        <div style={{ display:'flex', alignItems:'center', gap:12 }}>
          <ResonanceMark size={28}/>
          <div style={{ fontFamily:F.mono, fontSize:11, letterSpacing:'0.24em', color:R.ion }}>RENDERING · FOURIER SQUARES</div>
        </div>
        <div style={{ display:'flex', gap:12 }}>
          <Tag color={R.amber}>RASTER PASS</Tag>
          <Tag color={R.trace}>GPU · METAL M3</Tag>
        </div>
      </div>
      {/* center scope */}
      <div style={{ position:'absolute', left:'50%', top:'50%', transform:'translate(-50%, -50%)',
        display:'flex', flexDirection:'column', alignItems:'center', gap: 30 }}>
        <RenderTrigger size={200} running label="STOP"/>
        <div style={{ display:'flex', alignItems:'baseline', gap:14 }}>
          <span style={{ fontFamily:F.display, fontSize:64, letterSpacing:'-0.03em', color:R.phosphor, fontVariantNumeric:'tabular-nums' }}>
            {String(cur).padStart(3,'0')}
          </span>
          <span style={{ fontFamily:F.mono, fontSize:18, color:R.dim, letterSpacing:'0.1em' }}>/ {total} FRAMES</span>
        </div>
        <div style={{ width: 480, height: 4, background:'rgba(190,200,255,0.10)', borderRadius:4, position:'relative', overflow:'hidden' }}>
          <div style={{ position:'absolute', inset:0, width:`${pct*100}%`, background: GRAD, boxShadow:`0 0 16px rgba(168,85,247,0.8)`, borderRadius:4 }}/>
          {/* tick marks */}
          {Array.from({length:11}).map((_,i)=>(
            <div key={i} style={{ position:'absolute', left:`${i*10}%`, top:-3, width:1, height:10, background:R.faint }}/>
          ))}
        </div>
        <div style={{ display:'flex', gap:42 }}>
          <Readout label="ELAPSED"   value="00:21" big/>
          <Readout label="ESTIMATED" value="00:22" big/>
          <Readout label="FPS PASS"  value="22.4"  big/>
          <Readout label="MEMORY"    value="312MB" big/>
        </div>
      </div>
      {/* bottom strip — recent frames */}
      <div style={{ position:'absolute', bottom: 24, left:32, right:32 }}>
        <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:10 }}>
          <span style={{ fontFamily:F.mono, fontSize:10, color:R.dim, letterSpacing:'0.2em' }}>◍ FRAME BUFFER</span>
          <span style={{ fontFamily:F.mono, fontSize:10, color:R.dim, letterSpacing:'0.2em' }}>LATEST  ◣  OLDEST</span>
        </div>
        <div style={{ display:'flex', gap:8, overflow:'hidden' }}>
          {Array.from({length:14}).map((_,i)=>(
            <div key={i} style={{
              flex:1, height: 56, borderRadius:4, position:'relative', overflow:'hidden',
              border:`1px solid ${i===0 ? R.trace : R.hairline}`,
              background: R.deep, opacity: 1 - i*0.05,
              boxShadow: i===0 ? '0 0 16px rgba(125,249,255,0.5)' : 'none',
            }}>
              <div style={{ transform:`scale(0.35) rotate(${i*8}deg)`, transformOrigin:'center', width:'100%', height:'100%', display:'flex', alignItems:'center', justifyContent:'center' }}>
                <ScenePreview_Fourier w={200} h={130}/>
              </div>
              <div style={{ position:'absolute', bottom:2, right:4, fontFamily:F.mono, fontSize:8, color:R.dim }}>{cur-i}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
function Readout({ label, value, big }) {
  return (
    <div style={{ textAlign:'center' }}>
      <div style={{ fontFamily:F.mono, fontSize:10, color:R.faint, letterSpacing:'0.2em', marginBottom:4 }}>{label}</div>
      <div style={{ fontFamily:F.mono, fontSize: big?22:14, color:R.phosphor, letterSpacing:'0.04em', fontVariantNumeric:'tabular-nums' }}>{value}</div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// iPhone variants
// ─────────────────────────────────────────────────────────────
function PhoneGallery() {
  return (
    <div style={{ width: 402, height: 874-94, background:R.void, color:R.phosphor, fontFamily:F.ui, display:'flex', flexDirection:'column', overflow:'hidden' }}>
      {/* compact header */}
      <div style={{ padding:'12px 18px 8px', borderBottom:`1px solid ${R.hairline}`, position:'relative' }}>
        <div style={{ position:'absolute', inset:0, opacity:0.5 }}>
          <PhaseLine width={402} height={62} amp={5} freq={0.025} speed={0.5} color={R.traceDim} glow={false}/>
        </div>
        <div style={{ position:'relative', zIndex:1, display:'flex', alignItems:'center', justifyContent:'space-between' }}>
          <div style={{ display:'flex', alignItems:'center', gap:10 }}>
            <ResonanceMark size={28}/>
            <div>
              <div style={{ fontFamily:F.mono, fontSize:8.5, color:R.dim, letterSpacing:'0.22em' }}>RESONANCE · v0.9</div>
              <div style={{ fontFamily:F.display, fontSize:16, marginTop:1 }}>Gallery</div>
            </div>
          </div>
          <Tag color={R.green}>GPU</Tag>
        </div>
      </div>
      <div style={{ flex:1, overflow:'auto', padding:'14px 14px 80px' }}>
        <div style={{ fontFamily:F.mono, fontSize:9.5, color:R.trace, letterSpacing:'0.26em', marginBottom:10 }}>◍ 06 SCENES</div>
        <div style={{ display:'flex', flexDirection:'column', gap:14 }}>
          {SCENES.map((s,i)=> (
            <div key={s.id} style={{
              display:'flex', gap:12, background:'rgba(24,27,58,0.5)',
              border:`1px solid ${R.hairline}`, borderRadius:14, padding:10, position:'relative',
            }}>
              <div style={{
                width:96, height:72, borderRadius:8, overflow:'hidden',
                border:`1px solid ${R.hairline}`, background:R.deep,
              }}>
                <div style={{ transform:'scale(0.35)', transformOrigin:'top left', width:'285%', height:'285%' }}>
                  <s.Preview w={270} h={205}/>
                </div>
              </div>
              <div style={{ flex:1, minWidth:0 }}>
                <div style={{ fontFamily:F.mono, fontSize:8.5, color:R.dim, letterSpacing:'0.2em' }}>{String(i+1).padStart(2,'0')} · READY</div>
                <div style={{ fontFamily:F.display, fontSize:15, marginTop:2 }}>{s.title}</div>
                <div style={{ fontFamily:F.mono, fontSize:9.5, color:R.trace, marginTop:4 }}>{s.formula}</div>
              </div>
            </div>
          ))}
        </div>
      </div>
      <PhoneDock active="gallery"/>
    </div>
  );
}

function PhoneWorkspace() {
  return (
    <div style={{ width: 402, height: 874-94, background:R.void, color:R.phosphor, fontFamily:F.ui, display:'flex', flexDirection:'column', overflow:'hidden' }}>
      <div style={{ padding:'12px 18px', borderBottom:`1px solid ${R.hairline}`, position:'relative' }}>
        <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between' }}>
          <div>
            <div style={{ fontFamily:F.mono, fontSize:8.5, color:R.dim, letterSpacing:'0.22em' }}>SCENE · 04</div>
            <div style={{ fontFamily:F.display, fontSize:18 }}>Fourier Squares</div>
          </div>
          <Tag color={R.trace}>LIVE</Tag>
        </div>
      </div>
      {/* segmented picker */}
      <div style={{ padding:'10px 14px 6px', display:'flex', gap:6 }}>
        {['PREVIEW','SCENE.PY','LOG'].map((t,i)=>(
          <div key={t} style={{
            flex:1, padding:'8px 0', textAlign:'center',
            fontFamily:F.mono, fontSize:10, letterSpacing:'0.18em',
            color: i===0 ? R.phosphor : R.dim,
            background: i===0 ? 'rgba(125,249,255,0.06)' : 'transparent',
            border:`1px solid ${i===0 ? R.hairBright : R.hairline}`,
            borderRadius:8,
          }}>{t}</div>
        ))}
      </div>
      {/* preview stage */}
      <div style={{ padding:'10px 14px', flex:1, display:'flex', flexDirection:'column', overflow:'hidden' }}>
        <div style={{
          aspectRatio:'16/9', borderRadius:8, border:`1px solid ${R.hairBright}`,
          background:'#0A0B16', position:'relative', overflow:'hidden',
          boxShadow:'0 0 30px rgba(99,102,241,0.15)',
        }}>
          <CornerBrackets inset={4} len={10} color={R.trace} opacity={0.6}/>
          <div style={{ transform:'scale(1.6)', transformOrigin:'center', width:'100%', height:'100%' }}>
            <ScenePreview_Fourier w={372} h={209}/>
          </div>
          <div style={{ position:'absolute', top:6, left:8, fontFamily:F.mono, fontSize:8, color:R.ion, letterSpacing:'0.16em' }}>◉ LIVE</div>
          <div style={{ position:'absolute', bottom:6, right:8, fontFamily:F.mono, fontSize:8, color:R.dim }}>247/499</div>
        </div>
        {/* transport */}
        <div style={{ display:'flex', alignItems:'center', gap:10, marginTop:14 }}>
          <button style={{...iconBtn, width:30, height:30}}>⏮</button>
          <button style={{...iconBtn, width:30, height:30}}>⏵</button>
          <div style={{ flex:1, height:4, borderRadius:4, background:'rgba(190,200,255,0.10)', position:'relative' }}>
            <div style={{ position:'absolute', inset:0, width:'48%', background: GRAD, borderRadius:4 }}/>
            <div style={{ position:'absolute', left:'48%', top:-4, width:2, height:12, background:R.trace }}/>
          </div>
        </div>
        {/* readouts grid */}
        <div style={{ display:'grid', gridTemplateColumns:'repeat(3,1fr)', gap:8, marginTop:14 }}>
          <MiniReadout label="DURATION" value="08.32s"/>
          <MiniReadout label="FRAMES" value="499"/>
          <MiniReadout label="QUALITY" value="HIGH"/>
        </div>
        {/* render */}
        <div style={{ marginTop:'auto', display:'flex', justifyContent:'center', padding:'12px 0 6px' }}>
          <RenderTrigger size={88}/>
        </div>
      </div>
      <PhoneDock active="workspace"/>
    </div>
  );
}
function MiniReadout({ label, value }) {
  return (
    <div style={{ background:'rgba(24,27,58,0.5)', border:`1px solid ${R.hairline}`, borderRadius:8, padding:'8px 10px' }}>
      <div style={{ fontFamily:F.mono, fontSize:8.5, color:R.faint, letterSpacing:'0.18em' }}>{label}</div>
      <div style={{ fontFamily:F.mono, fontSize:13, color:R.phosphor, marginTop:2 }}>{value}</div>
    </div>
  );
}

function PhoneDock({ active }) {
  return (
    <div style={{
      borderTop:`1px solid ${R.hairline}`, background:R.deep,
      padding:'10px 14px 14px',
      display:'flex', justifyContent:'space-around', alignItems:'center',
    }}>
      {NAV.slice(0,5).map(n => {
        const isA = active === n.id;
        return (
          <div key={n.id} style={{ display:'flex', flexDirection:'column', alignItems:'center', gap:4 }}>
            <NavIcon kind={n.icon} active={isA}/>
            <div style={{ fontFamily:F.mono, fontSize:7.5, letterSpacing:'0.18em', color: isA ? R.phosphor : R.faint }}>{n.label}</div>
            {isA && <div style={{ width:18, height:2, background: GRAD, borderRadius:2 }}/>}
          </div>
        );
      })}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// App icon directions
// ─────────────────────────────────────────────────────────────
function AppIcon({ size=180, kind='phase', label }) {
  const id = React.useId();
  const base = (children) => (
    <div style={{ width:size, height:size, borderRadius: size*0.225, overflow:'hidden', position:'relative',
      background: GRAD, boxShadow:'0 20px 40px rgba(99,102,241,0.35), inset 0 1px 0 rgba(255,255,255,0.25)' }}>
      {children}
    </div>
  );
  let inner = null;
  if (kind === 'phase') {
    // Phase trace
    inner = (
      <svg width={size} height={size} viewBox="0 0 180 180">
        <defs>
          <filter id={`g${id}`}><feGaussianBlur stdDeviation="1.4"/></filter>
        </defs>
        <path d="M14 90 C 30 38, 50 142, 76 90 S 110 38, 132 90 S 162 142, 174 70"
          stroke="#fff" strokeWidth="6" fill="none" strokeLinecap="round" opacity="0.95" filter={`url(#g${id})`}/>
        <path d="M14 90 C 30 38, 50 142, 76 90 S 110 38, 132 90 S 162 142, 174 70"
          stroke="#fff" strokeWidth="3" fill="none" strokeLinecap="round"/>
        <circle cx="174" cy="70" r="5" fill="#fff"/>
      </svg>
    );
  } else if (kind === 'reticle') {
    inner = (
      <svg width={size} height={size} viewBox="0 0 180 180">
        <circle cx="90" cy="90" r="70" stroke="#fff" strokeWidth="2.5" fill="none" opacity="0.9"/>
        <circle cx="90" cy="90" r="44" stroke="#fff" strokeWidth="2.5" fill="none" opacity="0.7"/>
        <circle cx="90" cy="90" r="18" stroke="#fff" strokeWidth="2.5" fill="none"/>
        <line x1="90" y1="14" x2="90" y2="34" stroke="#fff" strokeWidth="2.5"/>
        <line x1="90" y1="146" x2="90" y2="166" stroke="#fff" strokeWidth="2.5"/>
        <line x1="14" y1="90" x2="34" y2="90" stroke="#fff" strokeWidth="2.5"/>
        <line x1="146" y1="90" x2="166" y2="90" stroke="#fff" strokeWidth="2.5"/>
        <circle cx="90" cy="90" r="4" fill="#fff"/>
      </svg>
    );
  } else if (kind === 'orbit') {
    inner = (
      <svg width={size} height={size} viewBox="0 0 180 180">
        <ellipse cx="90" cy="90" rx="64" ry="20" stroke="#fff" strokeWidth="2.2" fill="none" opacity="0.7" transform="rotate(-30 90 90)"/>
        <ellipse cx="90" cy="90" rx="64" ry="20" stroke="#fff" strokeWidth="2.2" fill="none" opacity="0.6" transform="rotate(30 90 90)"/>
        <ellipse cx="90" cy="90" rx="64" ry="20" stroke="#fff" strokeWidth="2.2" fill="none" opacity="0.55" transform="rotate(90 90 90)"/>
        <circle cx="90" cy="90" r="10" fill="#fff"/>
        <circle cx="34" cy="90" r="4" fill="#fff"/>
        <circle cx="146" cy="90" r="4" fill="#fff"/>
        <circle cx="118" cy="40" r="3.5" fill="#fff" opacity="0.7"/>
      </svg>
    );
  } else if (kind === 'integral') {
    inner = (
      <svg width={size} height={size} viewBox="0 0 180 180">
        <path d="M70 30 C 110 30, 110 60, 95 90 S 70 150, 110 150" stroke="#fff" strokeWidth="11" fill="none" strokeLinecap="round"/>
        <circle cx="70" cy="30" r="6" fill="#fff"/>
        <circle cx="110" cy="150" r="6" fill="#fff"/>
        <line x1="40" y1="120" x2="62" y2="120" stroke="#fff" strokeWidth="4" opacity="0.7" strokeLinecap="round"/>
        <line x1="120" y1="60" x2="142" y2="60" stroke="#fff" strokeWidth="4" opacity="0.7" strokeLinecap="round"/>
      </svg>
    );
  }
  return (
    <div style={{ display:'flex', flexDirection:'column', alignItems:'center', gap: 10 }}>
      {base(inner)}
      <div style={{ fontFamily:F.mono, fontSize:11, color:R.ion, letterSpacing:'0.2em' }}>{label}</div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// Identity / Palette / Type / Motif cards
// ─────────────────────────────────────────────────────────────
function IdentityStatement() {
  return (
    <div style={{ width: 720, height: 420, background: R.deep, border:`1px solid ${R.hairline}`, borderRadius:18, padding: 40, color:R.phosphor, fontFamily:F.ui, position:'relative', overflow:'hidden' }}>
      <div style={{ position:'absolute', top:0, left:0, right:0, opacity:0.6 }}>
        <PhaseLine width={720} height={48} amp={8} freq={0.02} speed={0.5} color={R.traceDim} glow={false}/>
      </div>
      <CornerBrackets inset={14} len={16} color={R.trace} opacity={0.5}/>
      <div style={{ fontFamily:F.mono, fontSize:11, color:R.trace, letterSpacing:'0.3em', marginBottom:14 }}>
        ◍  VISUAL IDENTITY · RESONANCE
      </div>
      <div style={{ fontFamily:F.display, fontSize: 40, lineHeight:1.05, letterSpacing:'-0.02em', marginBottom: 22 }}>
        An <span style={{ background: GRAD, WebkitBackgroundClip:'text', backgroundClip:'text', color:'transparent', fontStyle:'italic' }}>instrument</span> for mathematical animation.
      </div>
      <div style={{ fontFamily:F.ui, fontSize: 15, lineHeight:1.55, color: R.ion, maxWidth: 640 }}>
        Resonance is built like a piece of scientific hardware, not a developer tool. A live phase-line breathes across every primary surface; concentric reticles frame every viewport; rendered frames materialise as glowing particles rather than progress bars. The signature indigo→violet→pink thread persists, but it now flows along an oscilloscope trace rather than washing over flat dark surfaces. Code is present where it earns its keep — never in front of the camera.
      </div>
      <div style={{ position:'absolute', bottom: 22, left: 40, right: 40, display:'flex', justifyContent:'space-between', alignItems:'flex-end' }}>
        <div style={{ fontFamily:F.mono, fontSize:9, color:R.dim, letterSpacing:'0.24em' }}>METAPHOR  ◣  OSCILLOSCOPE · OBSERVATORY · LABORATORY</div>
        <ResonanceMark size={36}/>
      </div>
    </div>
  );
}

function PaletteCard() {
  const sw = (c, name, code) => (
    <div key={code} style={{ flex:1, display:'flex', flexDirection:'column', gap:6 }}>
      <div style={{ height: 70, borderRadius:8, background: c, border:`1px solid ${R.hairline}` }}/>
      <div style={{ fontFamily:F.mono, fontSize:9.5, color:R.phosphor, letterSpacing:'0.14em' }}>{name}</div>
      <div style={{ fontFamily:F.mono, fontSize:9, color:R.dim }}>{code}</div>
    </div>
  );
  return (
    <div style={{ width: 720, height: 560, background:R.deep, border:`1px solid ${R.hairline}`, borderRadius:18, padding:32, color:R.phosphor, fontFamily:F.ui }}>
      <div style={{ fontFamily:F.mono, fontSize:11, color:R.trace, letterSpacing:'0.3em', marginBottom:8 }}>◍ PALETTE</div>
      <div style={{ fontFamily:F.display, fontSize:24, marginBottom: 18 }}>Signal & surface</div>
      <div style={{ fontFamily:F.mono, fontSize:10, color:R.faint, letterSpacing:'0.18em', marginBottom:8 }}>SURFACES</div>
      <div style={{ display:'flex', gap:12, marginBottom:22 }}>
        {sw(R.void, 'VOID', '#06060C')}
        {sw(R.deep, 'DEEP', '#0B0C18')}
        {sw(R.surface, 'SURFACE', '#11132A')}
        {sw(R.raised, 'RAISED', '#181B3A')}
        {sw(R.bezel, 'BEZEL', '#222652')}
      </div>
      <div style={{ fontFamily:F.mono, fontSize:10, color:R.faint, letterSpacing:'0.18em', marginBottom:8 }}>BRAND THREAD</div>
      <div style={{ display:'flex', gap:12, marginBottom:22 }}>
        {sw(R.indigo, 'INDIGO', '#6366F1')}
        {sw(R.violet, 'VIOLET', '#A855F7')}
        {sw(R.pink, 'PINK', '#EC4899')}
        <div style={{ flex:2, display:'flex', flexDirection:'column', gap:6 }}>
          <div style={{ height: 70, borderRadius:8, background: GRAD, border:`1px solid ${R.hairline}` }}/>
          <div style={{ fontFamily:F.mono, fontSize:9.5, color:R.phosphor, letterSpacing:'0.14em' }}>SIGNATURE</div>
          <div style={{ fontFamily:F.mono, fontSize:9, color:R.dim }}>135° · indigo → violet → pink</div>
        </div>
      </div>
      <div style={{ fontFamily:F.mono, fontSize:10, color:R.faint, letterSpacing:'0.18em', marginBottom:8 }}>LIVE SIGNAL</div>
      <div style={{ display:'flex', gap:12 }}>
        {sw(R.trace, 'TRACE', '#7DF9FF')}
        {sw(R.amber, 'AMBER', '#FBBF24')}
        {sw(R.green, 'GREEN', '#34D399')}
        {sw(R.red,   'STOP',  '#F87171')}
      </div>
    </div>
  );
}

function TypeCard() {
  return (
    <div style={{ width: 720, height: 560, background:R.deep, border:`1px solid ${R.hairline}`, borderRadius:18, padding:32, color:R.phosphor, fontFamily:F.ui }}>
      <div style={{ fontFamily:F.mono, fontSize:11, color:R.trace, letterSpacing:'0.3em', marginBottom:8 }}>◍ TYPOGRAPHY</div>
      <div style={{ fontFamily:F.display, fontSize:24, marginBottom: 22 }}>Three voices</div>
      <div style={{ marginBottom:24 }}>
        <div style={{ display:'flex', alignItems:'baseline', justifyContent:'space-between', borderBottom:`1px solid ${R.hairline}`, paddingBottom:6, marginBottom:10 }}>
          <span style={{ fontFamily:F.mono, fontSize:10, color:R.dim, letterSpacing:'0.2em' }}>DISPLAY · SPACE GROTESK</span>
          <span style={{ fontFamily:F.mono, fontSize:10, color:R.faint }}>Headings · Hero · Scene titles</span>
        </div>
        <div style={{ fontFamily:F.display, fontSize:46, letterSpacing:'-0.02em', lineHeight:1 }}>Resonance · 42 fps</div>
      </div>
      <div style={{ marginBottom:24 }}>
        <div style={{ display:'flex', alignItems:'baseline', justifyContent:'space-between', borderBottom:`1px solid ${R.hairline}`, paddingBottom:6, marginBottom:10 }}>
          <span style={{ fontFamily:F.mono, fontSize:10, color:R.dim, letterSpacing:'0.2em' }}>UI · GEIST SANS</span>
          <span style={{ fontFamily:F.mono, fontSize:10, color:R.faint }}>Body · Controls · Settings</span>
        </div>
        <div style={{ fontFamily:F.ui, fontSize:20, lineHeight:1.4, color:R.ion }}>
          Pick a scene from the gallery, tweak its parameters, and fire the render.
        </div>
      </div>
      <div>
        <div style={{ display:'flex', alignItems:'baseline', justifyContent:'space-between', borderBottom:`1px solid ${R.hairline}`, paddingBottom:6, marginBottom:10 }}>
          <span style={{ fontFamily:F.mono, fontSize:10, color:R.dim, letterSpacing:'0.2em' }}>MONO · GEIST MONO</span>
          <span style={{ fontFamily:F.mono, fontSize:10, color:R.faint }}>Readouts · Tags · Code · Frame numbers</span>
        </div>
        <div style={{ fontFamily:F.mono, fontSize:16, color:R.trace, letterSpacing:'0.02em' }}>
          FRAME  247 / 499   t = 4.12 s   y = sin(2πft)
        </div>
      </div>
    </div>
  );
}

function MotifCard() {
  return (
    <div style={{ width: 720, height: 380, background:R.deep, border:`1px solid ${R.hairline}`, borderRadius:18, padding:32, color:R.phosphor, fontFamily:F.ui, position:'relative', overflow:'hidden' }}>
      <div style={{ fontFamily:F.mono, fontSize:11, color:R.trace, letterSpacing:'0.3em', marginBottom:8 }}>◍ SIGNATURE MOTIF</div>
      <div style={{ fontFamily:F.display, fontSize:24 }}>The Phase Line</div>
      <div style={{ fontFamily:F.ui, fontSize:13, color:R.ion, marginTop:8, maxWidth:540, lineHeight:1.5 }}>
        A thin, breathing oscilloscope trace that runs across the top of every primary surface. Each scene contributes its own waveform signature; during render, the line pulses in sync with frame completion. It carries the brand thread in motion.
      </div>
      <div style={{ marginTop: 22, padding:14, borderRadius: 10, background: R.void, border:`1px solid ${R.hairline}` }}>
        <PhaseLine width={656} height={80} amp={20} freq={0.014} speed={0.7}/>
      </div>
      <div style={{ marginTop: 16, display:'flex', gap: 16 }}>
        <Tag color={R.trace}>BREATHING IDLE</Tag>
        <Tag color={R.amber}>PULSE ON RENDER</Tag>
        <Tag color={R.pink}>SCENE-SPECIFIC SEED</Tag>
      </div>
    </div>
  );
}

Object.assign(window, {
  Gallery, Workspace, RenderState,
  PhoneGallery, PhoneWorkspace,
  RenderTrigger, ResonanceMark, AppIcon,
  IdentityStatement, PaletteCard, TypeCard, MotifCard,
  SideRail, HeaderBar, PhoneDock,
});
