import { motion } from 'motion/react';
import { Download } from 'lucide-react';

export const CtaSection = () => {
  return (
    <section className="py-32 bg-neo-pink text-black text-center relative overflow-hidden border-t-4 border-black">
      {/* Background decorations */}
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-full max-w-5xl h-full pointer-events-none z-0">
        <div className="absolute top-10 left-10 w-32 h-32 bg-neo-yellow border-4 border-black rotate-[-12deg] shadow-[8px_8px_0px_#000]"></div>
        <div className="absolute bottom-10 right-10 w-40 h-40 bg-neo-blue border-4 border-black rotate-[8deg] shadow-[8px_8px_0px_#000]"></div>
        <div className="absolute top-1/2 right-20 w-16 h-16 rounded-full bg-neo-green border-4 border-black shadow-[4px_4px_0px_#000]"></div>
      </div>

      <div className="container mx-auto px-6 relative z-10 max-w-4xl bg-white border-4 border-black p-12 md:p-20 shadow-[16px_16px_0px_#000]">
        <motion.h2 
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.4 }}
          className="text-5xl md:text-7xl font-sans font-black tracking-tighter mb-8 leading-[0.9] uppercase"
        >
          Take One Off The Note.
        </motion.h2>
        
        <motion.p
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.4, delay: 0.1 }}
          className="text-xl md:text-2xl text-black font-sans font-bold mb-12 max-w-2xl mx-auto"
        >
          Free, open source, and about a megabyte. Windows 10 or 11. Your notes stay on your machine - and so does he.
        </motion.p>
        
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          whileInView={{ opacity: 1, scale: 1 }}
          viewport={{ once: true }}
          transition={{ duration: 0.4, delay: 0.2 }}
        >
          <button className="neo-btn bg-neo-yellow text-2xl py-6 px-10 w-full sm:w-auto flex items-center justify-center gap-3 mx-auto">
            <Download size={32} strokeWidth={3} />
            Download for Windows
          </button>
          
          <div className="mt-8 inline-block bg-white px-4 py-2 border-2 border-black border-dashed font-bold uppercase text-sm">
            Requires Windows 10 or 11 &bull; Less than 1MB
          </div>
        </motion.div>
      </div>
    </section>
  );
};
