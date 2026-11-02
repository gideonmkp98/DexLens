const sharp = require('../apps/web/node_modules/sharp');
const fs = require('fs');
const path = require('path');

function makeSvg(size, isMaskable) {
  const pad = isMaskable ? size * 0.15 : size * 0.08;
  const radius = (size - 2 * pad) / 2;
  const cx = size / 2;
  const cy = size / 2;
  const beltHeight = size * 0.08;
  const innerRadius = size * 0.14;
  const buttonRadius = size * 0.08;

  return `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
    <rect width="${size}" height="${size}" fill="#20251f"/>
    <g transform="translate(${cx}, ${cy})">
      <clipPath id="ballClip_${size}_${isMaskable}">
        <circle r="${radius}" cx="0" cy="0"/>
      </clipPath>
      <circle r="${radius}" cx="0" cy="0" fill="#252923"/>
      <!-- Top hemisphere (DexLens red) -->
      <path d="M ${-radius} 0 A ${radius} ${radius} 0 0 1 ${radius} 0 Z" fill="#c6372e" clip-path="url(#ballClip_${size}_${isMaskable})"/>
      <!-- Bottom hemisphere (DexLens cream) -->
      <path d="M ${-radius} 0 A ${radius} ${radius} 0 0 0 ${radius} 0 Z" fill="#fffcf5" clip-path="url(#ballClip_${size}_${isMaskable})"/>
      <!-- Center belt -->
      <rect x="${-radius}" y="${-beltHeight/2}" width="${radius*2}" height="${beltHeight}" fill="#252923"/>
      <!-- Outer ring of button -->
      <circle r="${innerRadius}" cx="0" cy="0" fill="#252923"/>
      <circle r="${innerRadius - 3}" cx="0" cy="0" fill="#fffcf5"/>
      <!-- Inner lens button -->
      <circle r="${buttonRadius}" cx="0" cy="0" fill="#8e977b"/>
      <circle r="${buttonRadius - 3}" cx="0" cy="0" fill="#c2cbb2"/>
    </g>
  </svg>`;
}

async function run() {
  const publicDir = path.resolve(__dirname, '../apps/web/public');
  const svg192 = Buffer.from(makeSvg(192, false));
  const svg512 = Buffer.from(makeSvg(512, false));
  const svgMaskable192 = Buffer.from(makeSvg(192, true));
  const svgMaskable512 = Buffer.from(makeSvg(512, true));

  await sharp(svg192).png().toFile(path.join(publicDir, 'icon-192.png'));
  await sharp(svg512).png().toFile(path.join(publicDir, 'icon-512.png'));
  await sharp(svgMaskable192).png().toFile(path.join(publicDir, 'icon-maskable-192.png'));
  await sharp(svgMaskable512).png().toFile(path.join(publicDir, 'icon-maskable-512.png'));
  await sharp(svg192).png().toFile(path.join(publicDir, 'apple-touch-icon.png'));
  
  // Also write SVG version
  fs.writeFileSync(path.join(publicDir, 'icon.svg'), makeSvg(512, false));
  console.log('PWA icons created successfully in apps/web/public');
}

run().catch(err => {
  console.error(err);
  process.exit(1);
});
