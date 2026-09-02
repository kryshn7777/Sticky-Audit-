import { useRef } from 'react';
import { gsap } from 'gsap';
import { useGSAP } from '@gsap/react';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { Zap, ShieldCheck, Maximize, Battery, HardDrive, Ghost, Lock, Eye } from 'lucide-react';

gsap.registerPlugin(ScrollTrigger, useGSAP);

const features = [
  {
    title: "Zero Baggage.",
    description: "Built on pure Python 3. No npm installs, no build steps, and no bloated frameworks. Just raw, unadulterated performance.",
    icon: <Zap size={32} strokeWidth={2.5} />,
    color: "bg-neo-yellow",
    span: "md:col-span-2 md:row-span-1",
  },
  {
    title: "Zero CPU.",
    description: "Obsessively optimized. With zero polling loops, the app draws 0.00% CPU when idle.",
    icon: <Battery size={32} strokeWidth={2.5} />,
    color: "bg-neo-green",
    span: "md:col-span-1 md:row-span-1",
  },
  {
    title: "Native Freedom.",
    description: "Break out of the browser tab. Your notes live directly on your desktop as real native windows that persist across reboots.",
    icon: <Maximize size={32} strokeWidth={2.5} />,
    color: "bg-neo-blue",
    span: "md:col-span-1 md:row-span-1",
  },
  {
    title: "Bulletproof Saves.",
    description: "Power cut? Yanked cord? Your ideas are safe. Every keystroke is written atomically. Data corruption is mathematically impossible.",
    icon: <ShieldCheck size={48} strokeWidth={2.5} />,
    color: "bg-neo-pink",
    span: "md:col-span-2 md:row-span-2",
    large: true
  },
  {
    title: "Think. Don't Save.",
    description: "Forget the Save button. We automatically flush your genius to disk exactly 0.7 seconds after you stop typing. Just write.",
    icon: <HardDrive size={32} strokeWidth={2.5} />,
    color: "bg-neo-orange",
    span: "md:col-span-2 md:row-span-1",
  },
  {
    title: "Absolute Privacy.",
    description: "100% offline by design. No sockets opened, no telemetry, no cloud. Your private thoughts stay precisely where they belong: on your machine.",
    icon: <Lock size={32} strokeWidth={2.5} />,
    color: "bg-neo-pink",
    span: "md:col-span-2 md:row-span-1",
  },
  {
    title: "Your Desk Companion.",
    description: "Say hello to Sticky! A procedural stickman that holds up your notes, tracks your cursor, and reacts to your pokes with physics-based charm.",
    icon: <Ghost size={48} strokeWidth={2.5} />,
    color: "bg-neo-yellow",
    span: "md:col-span-2 md:row-span-2",
    large: true
  },
  {
    title: "Unapologetically Bold.",
    description: "Form meets function. Our aggressive high-contrast palette clears strict WCAG AAA contrast standards, paired perfectly with the highly legible Space Grotesk font.",
    icon: <Eye size={48} strokeWidth={2.5} />,
    color: "bg-neo-blue",
    span: "md:col-span-2 md:row-span-2",
    large: true
  }
];

export const Features = () => {
  const containerRef = useRef<HTMLDivElement>(null);

  useGSAP(() => {
    const cards = gsap.utils.toArray('.feature-card');
    
    cards.forEach((card: any, i) => {
      gsap.from(card, {
        scrollTrigger: {
          trigger: card,
          start: "top 90%",
          toggleActions: "play none none reverse"
        },
        y: 60,
        opacity: 0,
        duration: 0.5,
        ease: "steps(3)",
        delay: (i % 3) * 0.1
      });
    });

    // Parallax background text
    gsap.to('.bg-text', {
      scrollTrigger: {
        trigger: containerRef.current,
        start: "top bottom",
        end: "bottom top",
        scrub: 1
      },
      y: -150
    });
  }, { scope: containerRef });

  return (
    <section className="py-32 w-full relative z-10 bg-white text-brand-dark overflow-hidden" ref={containerRef}>
      
      {/* Brutalist Background Typography */}
      <div className="absolute top-0 left-0 w-full h-full pointer-events-none flex flex-col justify-center overflow-hidden opacity-10 bg-text z-0">
        <h2 className="text-[25vw] font-sans font-black leading-[0.8] whitespace-nowrap -ml-10 uppercase stroke-black stroke-2" style={{ WebkitTextStroke: '2px black', color: 'transparent' }}>ENGINEERED</h2>
        <h2 className="text-[25vw] font-sans font-black leading-[0.8] whitespace-nowrap ml-20 uppercase stroke-black stroke-2" style={{ WebkitTextStroke: '2px black', color: 'transparent' }}>FOR FOCUS</h2>
      </div>

      <div className="container mx-auto px-6 max-w-7xl relative z-10">
        <div className="mb-20 max-w-3xl relative">
          <div className="absolute -top-12 -left-8 w-24 h-24 bg-neo-yellow border-4 border-black neo-shadow-sm rotate-12 -z-10"></div>
          <h2 className="text-6xl md:text-8xl font-sans font-black tracking-tighter mb-8 leading-[0.9] uppercase bg-white inline-block">
            Engineered <br/>For Focus.
          </h2>
          <p className="text-xl md:text-3xl text-brand-dark font-sans font-bold border-l-8 border-black pl-6 bg-white py-2 shadow-[10px_10px_0px_#000] max-w-2xl">
            Everything you need to capture your ideas, built with an obsessive dedication to speed, privacy, and charm.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-4 auto-rows-[minmax(220px,auto)] gap-8 grid-flow-dense">
          {features.map((feature, idx) => (
            <div 
              key={idx} 
              className={`feature-card relative text-brand-dark p-6 md:p-8 transition-transform duration-100 flex flex-col group hover:-translate-y-2 hover:-translate-x-2 ${feature.span} border-[4px] border-black ${feature.color} shadow-[6px_6px_0px_#000] hover:shadow-[14px_14px_0px_#000]`}
            >
              <div className={`relative z-10 flex flex-col h-full ${feature.large ? 'justify-center' : ''}`}>
                <div className={`inline-flex items-center justify-center bg-white border-3 border-black neo-shadow-sm ${feature.large ? 'w-20 h-20 mb-8 -rotate-3' : 'w-14 h-14 mb-6 rotate-2'}`}>
                  {feature.icon}
                </div>
                <h3 className={`${feature.large ? 'text-4xl md:text-5xl' : 'text-2xl'} font-black font-sans uppercase mb-4 leading-tight`}>
                  {feature.title}
                </h3>
                <p className={`${feature.large ? 'text-2xl' : 'text-lg'} font-sans font-bold leading-relaxed border-t-2 border-black/20 pt-4`}>
                  {feature.description}
                </p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};
