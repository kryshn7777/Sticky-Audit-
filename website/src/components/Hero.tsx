import { motion } from 'motion/react';

export const Hero = () => {
  return (
    <section className="relative w-full min-h-screen flex items-center justify-center overflow-hidden pt-20">
      <div className="container mx-auto px-6 relative z-10 flex flex-col items-center text-center">
        
        <motion.div
          initial={{ opacity: 0, y: 50 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, ease: "easeOut" }}
          className="mb-10 relative"
        >
          <div className="inline-block px-6 py-3 bg-neo-yellow rotate-[-4deg] border-3 border-black neo-shadow mb-6">
            <span className="font-handwriting text-3xl text-brand-dark font-bold">Sticky — he lives down there ↓</span>
          </div>
          
          <svg className="absolute -right-12 top-10 w-16 h-16 text-black rotate-[20deg]" viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M10 50 Q 50 10 90 50" stroke="currentColor" strokeWidth="6" strokeLinecap="round" fill="none" />
            <path d="M70 40 L 90 50 L 70 70" stroke="currentColor" strokeWidth="6" strokeLinecap="round" strokeLinejoin="round" fill="none" />
          </svg>
        </motion.div>

        <motion.h1
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 1, ease: [0.16, 1, 0.3, 1], delay: 0.2 }}
          className="text-6xl md:text-8xl font-sans font-black tracking-tight text-brand-dark mb-8 leading-[1.1] uppercase"
        >
          Notes That<br/>
          Stay Put.<br/>
          <span className="inline-block bg-neo-pink text-white px-4 py-2 mt-4 border-4 border-black neo-shadow-sm rotate-[1deg]">A Crew That Doesn't.</span>
        </motion.h1>

        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.8, delay: 0.6 }}
          className="text-xl md:text-3xl font-sans text-brand-dark font-medium max-w-3xl mb-12 border-l-4 border-black pl-6 text-left bg-white p-6 neo-shadow-sm"
        >
          Real paper windows on your desktop — and a small crew who live on them. Drag one off and he walks the taskbar, hangs off your note edges, and goes looking for the others. Offline, no account, and about a fifth of one percent of a core when nobody is out there.
        </motion.p>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.8 }}
          className="flex flex-col items-center gap-6 w-full max-w-lg"
        >
          <div className="flex flex-col sm:flex-row w-full justify-center gap-6">
            <button className="neo-btn bg-neo-green text-xl py-4 w-full sm:w-auto">
              Download for Windows
            </button>
            <button className="neo-btn bg-white text-xl py-4 w-full sm:w-auto">
              View Source
            </button>
          </div>
          
          <div className="flex items-center gap-3 mt-4 border-3 border-black bg-neo-blue px-4 py-2 font-bold neo-shadow-sm rotate-[-1deg]">
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" className="lucide lucide-shield-check"><path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2-1 4-2 7-2s5 1 7 2a1 1 0 0 1 1 1v7z"/><path d="m9 12 2 2 4-4"/></svg>
            <span className="uppercase text-sm tracking-wide">100% Free & Open Source</span>
          </div>
        </motion.div>

      </div>
    </section>
  );
};
