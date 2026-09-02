import { useEffect } from 'react';
import { ReactLenis, useLenis } from 'lenis/react';
import { gsap } from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { ThreeScene } from './components/ThreeScene';
import { Hero } from './components/Hero';
import { ScrollRevealNote } from './components/ScrollRevealNote';
import { Features } from './components/Features';
import { Playground } from './components/Playground';
import { CtaSection } from './components/CtaSection';
import { Footer } from './components/Footer';

gsap.registerPlugin(ScrollTrigger);

function App() {
  const lenis = useLenis(() => {
    // Scroll event if needed
  });

  useEffect(() => {
    if (!lenis) return;
    
    // Sync Lenis with GSAP ScrollTrigger
    lenis.on('scroll', ScrollTrigger.update);
    
    const ticker = (time: number) => {
      lenis.raf(time * 1000);
    };
    
    gsap.ticker.add(ticker);
    gsap.ticker.lagSmoothing(0);

    return () => {
      gsap.ticker.remove(ticker);
    };
  }, [lenis]);

  return (
    <ReactLenis root>
      <div className="relative w-full h-full min-h-screen">
        <div className="fixed inset-0 z-0 pointer-events-none">
          <ThreeScene />
        </div>
        
        <div className="relative z-10">
          <Hero />
          <Playground />
          <Features />
          <CtaSection />
          <ScrollRevealNote />
          <Footer />
        </div>
      </div>
    </ReactLenis>
  );
}

export default App;
