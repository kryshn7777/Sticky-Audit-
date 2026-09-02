import { useState } from 'react';
import { motion } from 'motion/react';
import { Mascot } from './Mascot';

const COLORS = [
  { name: 'yellow', class: 'bg-sticky-yellow', hex: '#fdf6b1' },
  { name: 'green', class: 'bg-sticky-green', hex: '#dcfce7' },
  { name: 'pink', class: 'bg-sticky-pink', hex: '#fae8ff' },
  { name: 'purple', class: 'bg-sticky-purple', hex: '#f3e8ff' },
  { name: 'blue', class: 'bg-sticky-blue', hex: '#e0f2fe' },
];

export const Playground = () => {
  const [activeColor, setActiveColor] = useState(COLORS[0]);
  const [text, setText] = useState("Try typing your own thoughts here!\n\nYou can also change the color using the dots above.");
  
  // We'll use a simple pose for the mascot in the playground
  const pose = "side";

  return (
    <section className="py-32 w-full relative z-20 bg-neo-bg border-y-4 border-black overflow-hidden"
      style={{ backgroundImage: 'linear-gradient(45deg, #000 25%, transparent 25%, transparent 75%, #000 75%, #000), linear-gradient(45deg, #000 25%, transparent 25%, transparent 75%, #000 75%, #000)', backgroundSize: '20px 20px', backgroundPosition: '0 0, 10px 10px' }}>
      
      <div className="container mx-auto px-6 max-w-5xl bg-white p-12 border-4 border-black neo-shadow-lg relative">
        <div className="absolute -top-6 -right-6 w-16 h-16 bg-neo-blue border-4 border-black rounded-full flex items-center justify-center font-bold rotate-12 z-10">
          NEW!
        </div>

        <div className="text-center mb-16 relative">
          <h2 className="text-4xl md:text-6xl font-sans font-black tracking-tighter uppercase mb-4 text-brand-dark">Try it before you download.</h2>
          <p className="text-xl text-brand-dark font-sans font-bold max-w-xl mx-auto bg-neo-pink px-4 py-2 border-3 border-black neo-shadow-sm rotate-[-1deg] inline-block">
            Experience the tactile feel right here.
          </p>
        </div>

        {/* Desktop Mockup Container */}
        <div className="relative w-full aspect-video bg-[url('https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?q=80&w=2564&auto=format&fit=crop')] bg-cover bg-center rounded-2xl shadow-2xl overflow-hidden flex items-center justify-center border border-slate-200 z-10">
          
          {/* Windows 11 Taskbar Mockup */}
          <div className="absolute bottom-0 w-full h-12 bg-white/70 backdrop-blur-md border-t border-white/20 flex items-center justify-center gap-2">
            <div className="w-8 h-8 bg-blue-500 rounded-sm"></div>
            <div className="w-8 h-8 bg-white rounded-sm shadow-sm flex items-center justify-center">
              <div className="w-4 h-4 bg-sticky-yellow sticky-cut"></div>
            </div>
          </div>

          {/* Interactive Sticky Note */}
          <motion.div 
            drag
            dragConstraints={{ left: -300, right: 300, top: -200, bottom: 200 }}
            whileDrag={{ scale: 1.05, cursor: 'grabbing' }}
            className="relative cursor-grab"
          >
            {/* Drop Shadow Wrapper */}
            <div className="absolute inset-0 drop-shadow-[5px_15px_30px_rgba(0,0,0,0.3)] pointer-events-none">
              {/* Clipped Paper Shape */}
              <div className={`absolute inset-0 ${activeColor.class} sticky-cut transition-colors duration-500`}>
                {/* Vignette effect */}
                <div className="absolute inset-0 bg-gradient-to-br from-white/40 via-transparent to-black/10"></div>
              </div>
              
              {/* Folded Corner */}
              <div className={`absolute bottom-0 right-0 w-8 h-8 ${activeColor.class} sticky-fold brightness-95 border-t border-l border-white/40 shadow-sm transition-colors duration-500`}></div>
            </div>

            {/* Note Content */}
            <div className="relative z-10 w-72 min-h-72 p-2 flex flex-col">
              
              {/* Drag Handle & Color Picker */}
              <div className="h-8 flex items-center justify-end px-2 gap-1.5 transition-opacity">
                {COLORS.map(c => (
                  <button
                    key={c.name}
                    onPointerDown={(e) => e.stopPropagation()}
                    onClick={() => setActiveColor(c)}
                    className={`w-3 h-3 rounded-full ${c.class} border border-black/20 hover:scale-125 transition-transform ${activeColor.name === c.name ? 'ring-2 ring-black/30 ring-offset-1' : ''}`}
                  />
                ))}
              </div>

              {/* Editable Text Area */}
              <textarea
                value={text}
                onChange={(e) => setText(e.target.value)}
                onPointerDown={(e) => e.stopPropagation()}
                className="w-full flex-grow bg-transparent resize-none outline-none font-handwriting text-xl text-brand-dark p-4 leading-relaxed placeholder-brand-dark/30 [&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] [scrollbar-width:none]"
                placeholder="Start typing..."
                spellCheck={false}
              />
            </div>
            
            {/* Mascot attached to playground note */}
            <Mascot pose={pose} paperColor={activeColor.hex} />
          </motion.div>
          
        </div>
      </div>
    </section>
  );
};
