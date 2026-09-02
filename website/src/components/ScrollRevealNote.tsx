import { useRef, useMemo } from 'react';
import { gsap } from 'gsap';
import { useGSAP } from '@gsap/react';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { Mascot } from './Mascot';

gsap.registerPlugin(ScrollTrigger);

export const ScrollRevealNote = () => {
  const containerRef = useRef<HTMLDivElement>(null);
  const noteRef = useRef<HTMLDivElement>(null);
  const lettersRef = useRef<HTMLDivElement>(null);
  const text = "STICKY";
  
  // Shuffle pose on refresh
  const initialPose = useMemo(() => {
    const poses = ["stand", "side", "top", "hang"];
    return poses[Math.floor(Math.random() * poses.length)];
  }, []);

  useGSAP(() => {
    const letters = gsap.utils.toArray('.reveal-letter');
    
    // Pin the note in the center while scrolling
    ScrollTrigger.create({
      trigger: containerRef.current,
      start: "top top",
      end: "+=120%", // Reduced to make scrolling much faster
      pin: noteRef.current,
      scrub: true,
    });

    // Reveal letters sequentially based on scroll progress within the pinned container
    const tl = gsap.timeline({
      scrollTrigger: {
        trigger: containerRef.current,
        start: "top top",
        end: "+=120%",
        scrub: 0.5,
      }
    });

    letters.forEach((letter: any, i) => {
      tl.fromTo(letter, 
        { opacity: 0, y: 20, rotation: Math.random() * 20 - 10, scale: 0.8 },
        { opacity: 1, y: 0, rotation: Math.random() * 6 - 3, scale: 1, ease: "back.out(1.5)", duration: 1 },
        i * 0.3 // Faster stagger
      );
    });
    
  }, { scope: containerRef });

  return (
    <section ref={containerRef} className="relative w-full bg-neo-bg border-t-4 border-black">
      <div 
        ref={noteRef} 
        className="w-full h-screen flex items-center justify-center pointer-events-none p-4"
      >
        {/* Giant Sticky Note */}
        <div className="relative w-[85vw] md:w-[45vw] max-w-2xl aspect-[4/3] rotate-[-1deg] pointer-events-auto group">
          
          {/* Drop Shadow Wrapper for Clipped Shape */}
          <div className="absolute inset-0 drop-shadow-[10px_25px_60px_rgba(0,0,0,0.5)] pointer-events-none">
            
            {/* Clipped Paper Shape */}
            <div className="absolute inset-0 bg-neo-yellow sticky-cut">
              {/* Edge shadow simulating paper */}
              <div className="absolute inset-0 bg-gradient-to-br from-white/20 via-transparent to-black/5"></div>
              {/* Glue strip at the top */}
              <div className="absolute top-0 left-0 right-0 h-12 bg-black/5"></div>
            </div>
            
            {/* Real Folded Corner */}
            <div className="absolute bottom-0 right-0 w-16 h-16 bg-neo-yellow sticky-fold brightness-95 border-t border-l border-white/40 shadow-[-2px_-2px_10px_rgba(0,0,0,0.1)]"></div>
          </div>
          
          {/* Mascot Attached to the Note */}
          <Mascot pose={initialPose} scale={2.5} />

          {/* Letters Container */}
          <div 
            ref={lettersRef}
            className="relative z-10 w-full h-full flex items-center justify-center flex-wrap gap-2 md:gap-4 p-8 pointer-events-none"
          >
            {text.split('').map((char, index) => (
              <span 
                key={index} 
                className="reveal-letter text-4xl md:text-[5rem] font-handwriting font-bold text-black opacity-0"
              >
                {char}
              </span>
            ))}
          </div>

        </div>
      </div>
    </section>
  );
};
