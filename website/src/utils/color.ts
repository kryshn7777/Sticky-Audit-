export function shade(hexColor: string, factor: number): string {
  // Ensure we have a proper hex with 6 characters
  let hex = hexColor.replace(/^#/, '');
  if (hex.length === 3) {
    hex = hex.split('').map(c => c + c).join('');
  }
  
  const r = parseInt(hex.substring(0, 2), 16);
  const g = parseInt(hex.substring(2, 4), 16);
  const b = parseInt(hex.substring(4, 6), 16);
  
  const clamp = (v: number) => Math.max(0, Math.min(255, Math.floor(v * factor)));
  
  const rc = clamp(r).toString(16).padStart(2, '0');
  const gc = clamp(g).toString(16).padStart(2, '0');
  const bc = clamp(b).toString(16).padStart(2, '0');
  
  return `#${rc}${gc}${bc}`;
}
