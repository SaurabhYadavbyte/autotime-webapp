const fs = require('node:fs');
const path = require('node:path');
const { instance } = require('@viz-js/viz');
const sharp = require('sharp');

const base = __dirname;
const diagrams = [
  ['level-0-context', 'level-0-context.dot'],
  ['level-1-main-processes', 'level-1-main-processes.dot'],
];

async function main() {
  const viz = await instance();

  for (const [name, sourceFile] of diagrams) {
    const source = fs.readFileSync(path.join(base, sourceFile), 'utf8');
    const result = viz.render(source, { format: 'svg', engine: 'dot' });

    if (result.status !== 'success' || result.errors.some((item) => item.level === 'error')) {
      throw new Error(`${sourceFile}: ${JSON.stringify(result.errors)}`);
    }

    const svgPath = path.join(base, `${name}.svg`);
    const pngPath = path.join(base, `${name}.png`);
    fs.writeFileSync(svgPath, result.output);

    await sharp(Buffer.from(result.output), { density: 200 })
      .resize({ width: name.startsWith('level-1') ? 2400 : 2000, withoutEnlargement: false })
      .flatten({ background: '#ffffff' })
      .png()
      .toFile(pngPath);
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
