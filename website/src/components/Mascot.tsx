import { useEffect, useRef, useState } from 'react';
import { motion, useMotionValue } from 'motion/react';
import { shade } from '../utils/color';

const REACTIONS = ["hop", "wave", "wink", "wobble", "dizzy", "spin", "nod", "shake", "squish", "float"];

// Exact constants from mascot.py
const HEAD = 30;
const LEG_H = 18;
const SHOE_H = 7;
const GROUND_DROP = 8;
const EYE_DX = 6.5;
const EYE_R = 2.8;
const EYE_R_WIDE = 5.0;
const GLINT_R = 1.8;
const PUPIL_TRAVEL = 4.0;
const LOOK_RANGE = 150.0;
const NEAR = 110;
const NEAR_OUT = 160;

export const Mascot = ({ pose = "stand", paperColor = "#FFF200", inkColor = "#000000", className = "", scale = 1 }: any) => {
  const [reaction, setReaction] = useState<string | null>(null);
  const [happy, setHappy] = useState(false);
  const [blink, setBlink] = useState(false);
  const [reactionStep, setReactionStep] = useState(-1);
  
  const skin = shade(paperColor, 1.06);
  const limb = shade(inkColor, 1.35);

  const pupilX = useMotionValue(0);
  const pupilY = useMotionValue(0);

  // Reaction state
  const offset = useRef({ x: 0, y: 0 });
  const faceScale = useRef({ x: 1, y: 1 });
  const wink = useRef(false);
  const hideEyes = useRef(false);
  const armRot = useRef(0);
  const dizzyMarks = useRef(0);
  const dizzySpin = useRef(0);
  const popText = useRef("");

  const [bounds, setBounds] = useState({ w: 500, h: 500 });
  const containerRef = useRef<SVGSVGElement>(null);
  
  useEffect(() => {
    if (!containerRef.current) return;
    const observer = new ResizeObserver((entries) => {
      if (entries[0]) {
        setBounds({ w: entries[0].contentRect.width, h: entries[0].contentRect.height });
      }
    });
    observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, []);

  // Base layout based on pose
  // We draw relative to the top-left of the paper
  // Scale the container bounds down into the mascot's drawing coordinate space
  const OX = 0;
  const OY = 0;
  const PW = bounds.w / scale;
  const PH = bounds.h / scale;

  let cx = OX, cy = OY;
  const half = HEAD / 2;
  let leftArm = [] as number[];
  let rightArm = [] as number[];
  let legs = [] as any[];

  if (pose === "stand") {
    const ground = OY + PH + GROUND_DROP;
    cx = OX - HEAD * 0.95;
    cy = ground - LEG_H - half;
    const armY = cy + HEAD * 0.16;
    rightArm = [cx + half - 2, armY, OX - 2, armY - 5, OX + 10, armY - 9];
    leftArm = [cx - half + 2, armY, cx - half - 6, armY + 6, cx - half - 10, armY + 13];
    
    for (const side of [-1, 1]) {
      const legX = cx + side * 7;
      legs.push({
        bone: [legX, cy + half - 1, legX, ground - SHOE_H + 2],
        shoe: { heel: legX, toe: legX + side * 4, sole: ground }
      });
    }
  } else if (pose === "side") {
    cx = OX - HEAD * 0.55;
    cy = OY + PH * 0.40;
    const armY = cy + HEAD * 0.18;
    rightArm = [cx + half - 4, armY, OX + 6, armY + 3, OX + 16, armY - 2];
    leftArm = [cx - half + 2, armY, cx - half - 7, armY + 7, cx - half - 11, armY + 15];
    
    for (const side of [-1, 1]) {
      const legX = cx + side * 7;
      legs.push({
        bone: [legX, cy + half - 1, legX + side * 2, cy + half + 12],
        shoe: { heel: legX + side * 2, toe: legX + side * 5, sole: cy + half + 19 }
      });
    }
  } else if (pose === "top") {
    cx = OX + PW * 0.32;
    cy = OY + 6 - half;
    const armY = cy + HEAD * 0.06;
    rightArm = [cx + half - 2, armY, cx + half + 10, armY + 4, cx + half + 20, armY + 1];
    leftArm = [cx - half + 2, armY, cx - half - 10, armY + 4, cx - half - 20, armY + 1];
  } else if (pose === "hang") {
    cx = OX + PW * 0.65;
    const gripY = OY + PH - 4;
    cy = gripY + 14 + half;
    for (const side of [-1, 1]) {
      rightArm = side === 1 ? [cx + 9, cy - half + 4, cx + 13, gripY] : rightArm;
      leftArm = side === -1 ? [cx - 9, cy - half + 4, cx - 13, gripY] : leftArm;
      const legX = cx + side * 7;
      legs.push({
        bone: [legX, cy + half - 1, legX + side * 4, cy + half + 13],
        shoe: { heel: legX + side * 4, toe: legX + side * 8, sole: cy + half + 20 }
      });
    }
  }

  const faceBox = { x0: cx - half, y0: cy - half, x1: cx + half, y1: cy + half };
  const hx = cx;
  const hy = cy - HEAD * 0.06;
  const eyeHome = [{ x: hx - EYE_DX, y: hy }, { x: hx + EYE_DX, y: hy }];

  // Mouse tracking logic
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      // Mouse pos relative to container, scaled down to drawing coordinates
      const px = (e.clientX - rect.left) / scale;
      const py = (e.clientY - rect.top) / scale;
      
      const dx = px - hx;
      const dy = py - hy;
      const dist = Math.sqrt(dx * dx + dy * dy) || 1.0;
      
      const reach = (Math.min(dist, LOOK_RANGE) / LOOK_RANGE) * PUPIL_TRAVEL;
      const targetX = Math.round((dx / dist) * reach * 2) / 2.0;
      const targetY = Math.round((dy / dist) * reach * 2) / 2.0;
      
      pupilX.set(targetX);
      pupilY.set(targetY);

      if (dist <= NEAR) {
        setHappy(true);
      } else if (dist > NEAR_OUT) {
        setHappy(false);
      }
    };
    window.addEventListener('mousemove', handleMouseMove);
    return () => window.removeEventListener('mousemove', handleMouseMove);
  }, [hx, hy, pupilX, pupilY]);

  // Reaction Loop
  useEffect(() => {
    if (reactionStep < 0) return;
    
    const REACT_FRAMES = 12;
    const t = reactionStep / REACT_FRAMES;
    
    offset.current = { x: 0, y: 0 };
    faceScale.current = { x: 1, y: 1 };
    wink.current = false;
    hideEyes.current = false;
    armRot.current = 0;
    dizzyMarks.current = 0;
    popText.current = "";

    const kind = reaction;
    
    if (kind === "hop") {
      const air = Math.sin(Math.PI * t);
      offset.current.y = -11 * air;
      const land = Math.max(0, (t - 0.86) / 0.14);
      faceScale.current = { x: 1 - 0.16 * air + 0.22 * land, y: 1 + 0.18 * air - 0.20 * land };
      if (reactionStep === 3) dizzyMarks.current = 3;
    } else if (kind === "wave") {
      armRot.current = 0.85 * Math.sin(t * Math.PI * 3.0);
      offset.current.y = -1.5 * Math.abs(Math.sin(t * Math.PI * 3.0));
    } else if (kind === "wink") {
      wink.current = reactionStep >= 2 && reactionStep <= 7;
      offset.current.y = wink.current ? 1.5 : 0;
      if (wink.current) dizzyMarks.current = 2;
    } else if (kind === "wobble") {
      offset.current.x = 4 * Math.sin(t * Math.PI * 6.0) * (1 - t);
      popText.current = "!";
    } else if (kind === "dizzy") {
      offset.current.x = 2.5 * Math.sin(t * Math.PI * 10.0);
      dizzyMarks.current = 3;
      dizzySpin.current = t * Math.PI * 3.0;
    } else if (kind === "nod") {
      offset.current.y = 3.0 * Math.sin(t * Math.PI * 4.0);
    } else if (kind === "shake") {
      offset.current.x = 4.0 * Math.sin(t * Math.PI * 8.0);
    } else if (kind === "squish") {
      const sq = Math.sin(t * Math.PI);
      faceScale.current = { x: 1 + 0.3 * sq, y: 1 - 0.4 * sq };
    } else if (kind === "float") {
      offset.current.y = -12.0 * Math.sin(t * Math.PI);
    } else if (kind === "spin") {
      const turn = Math.abs(Math.cos(t * Math.PI * 2.0));
      faceScale.current = { x: Math.max(0.12, turn), y: 1 };
      hideEyes.current = turn < 0.45;
      offset.current.y = -4.0 * Math.sin(Math.PI * t);
    }

    if (reactionStep < REACT_FRAMES) {
      const timer = setTimeout(() => setReactionStep(s => s + 1), 26);
      return () => clearTimeout(timer);
    } else {
      setReaction(null);
      setReactionStep(-1);
      offset.current = { x: 0, y: 0 };
      faceScale.current = { x: 1, y: 1 };
      armRot.current = 0;
    }
  }, [reactionStep, reaction]);

  // Idle Blink Loop
  useEffect(() => {
    if (reaction) return;
    const blinkTimeout = setTimeout(() => {
      setBlink(true);
      setTimeout(() => setBlink(false), 90);
    }, 3500 + Math.random() * 5500);
    return () => clearTimeout(blinkTimeout);
  }, [blink, reaction]);

  const handleInteract = () => {
    if (reactionStep >= 0) return;
    const nextReaction = REACTIONS[Math.floor(Math.random() * REACTIONS.length)];
    setReaction(nextReaction);
    setHappy(true);
    setReactionStep(0);
  };

  // SVG Helpers
  const Bone = ({ pts, w = 2 }: any) => {
    if (!pts || pts.length === 0) return null;
    const d = `M ${pts[0]} ${pts[1]} ` + (pts.length > 2 ? `L ${pts[2]} ${pts[3]} ` : "") + (pts.length > 4 ? `L ${pts[4]} ${pts[5]}` : "");
    return (
      <g>
        <path d={d} stroke={skin} strokeWidth={w + 3} strokeLinecap="round" strokeLinejoin="round" fill="none" />
        <path d={d} stroke={limb} strokeWidth={w} strokeLinecap="round" strokeLinejoin="round" fill="none" />
      </g>
    );
  };

  const Shoe = ({ shoe }: any) => {
    if (!shoe) return null;
    const { heel, toe, sole } = shoe;
    const minX = Math.min(heel, toe) - 5;
    const maxX = Math.max(heel, toe) + 5;
    const cx = (minX + maxX) / 2;
    const r = (maxX - minX) / 2;
    return (
      <path d={`M ${cx - r} ${sole} A ${r} ${SHOE_H} 0 0 1 ${cx + r} ${sole} Z`} fill={limb} />
    );
  };

  // Transform left arm if waving
  let leftArmPts = [...leftArm];
  if (armRot.current !== 0 && leftArmPts.length >= 6) {
    const ex = leftArmPts[2], ey = leftArmPts[3], tx = leftArmPts[4], ty = leftArmPts[5];
    const dx = tx - ex, dy = ty - ey;
    const ca = Math.cos(armRot.current), sa = Math.sin(armRot.current);
    leftArmPts[4] = ex + dx * ca - dy * sa;
    leftArmPts[5] = ey + dx * sa + dy * ca;
  }

  const ox = offset.current.x;
  const oy = offset.current.y;
  const fsx = faceScale.current.x;
  const fsy = faceScale.current.y;
  
  const faceH = HEAD * fsy;
  const base = faceBox.y1;
  const currCx = cx + ox;
  const currCy = base - faceH/2 + oy;

  return (
    <div 
      className={`absolute inset-0 select-none overflow-visible pointer-events-none ${className}`}
      ref={() => {
        // We could measure size here if we want to be exact, but we'll just use a generic large coordinate system for now, 
        // or actually let's just make the SVG cover the note bounds exactly.
      }}
    >
      <svg 
        ref={containerRef}
        className="absolute inset-0 w-full h-full overflow-visible pointer-events-auto"
        onMouseEnter={handleInteract}
        onClick={handleInteract}
      >
        <g transform={`scale(${scale})`}>
          <g transform={`translate(${ox}, ${oy})`}>
            <Bone pts={rightArm} />
            <Bone pts={leftArmPts} />
            
            {legs.map((l, i) => <Bone key={'lb'+i} pts={l.bone} />)}
            {legs.map((l, i) => <Shoe key={'ls'+i} shoe={l.shoe} />)}
          </g>
          
          {/* Face bounds - affected by scale */}
          <g transform={`translate(${currCx}, ${currCy}) scale(${fsx}, ${fsy})`}>
            <rect 
              x={-HEAD/2} y={-HEAD/2} width={HEAD} height={HEAD} 
              fill={skin} stroke={limb} strokeWidth={2/Math.max(fsx, fsy)} 
              rx={1}
            />
          </g>

          {!hideEyes.current && (
            <motion.g transform={`translate(${ox}, ${oy})`}>
              {eyeHome.map((eh, i) => {
                const dx = pupilX.get();
                const dy = pupilY.get();
                const ex = cx + (eh.x - cx + dx) * fsx;
                const ey = base - (base - eh.y - dy) * fsy;
                
                const isWinking = wink.current && i === 0;
                const isShut = blink || isWinking;
                const r = happy ? EYE_R_WIDE : EYE_R;
                const ry = isShut ? 1.0 : r;
                
                return (
                  <g key={'e'+i}>
                    <ellipse cx={ex} cy={ey} rx={r} ry={ry} fill={inkColor} />
                    {happy && !isShut && (
                      <circle cx={ex - r * 0.34} cy={ey - r * 0.38} r={GLINT_R} fill="#FFFFFF" />
                    )}
                  </g>
                );
              })}
              
              {happy && !hideEyes.current && (
                <path d={`M ${cx - 7 + (pupilX.get()*0.2)} ${currCy + 6 + (pupilY.get()*0.2)} Q ${cx} ${currCy + 14} ${cx + 7 + (pupilX.get()*0.2)} ${currCy + 6 + (pupilY.get()*0.2)}`} fill="none" stroke={inkColor} strokeWidth={1.6} />
              )}
            </motion.g>
          )}
        </g>
      </svg>
    </div>
  );
};
