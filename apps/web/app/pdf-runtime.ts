import { existsSync } from 'node:fs';
import { join } from 'node:path';

// The supported launch locations are the app root and repository root.
// Explicit paths also avoid bundler rewriting of require.resolve into module IDs.
const pdfjsDirectory = [process.cwd(), join(process.cwd(), 'apps/web')]
  .map(root => join(root, 'node_modules', 'pdfjs-dist'))
  .find(root => existsSync(join(root, 'standard_fonts', 'FoxitSerif.pfb')));
if (!pdfjsDirectory) throw new Error('Bundled PDF.js fonts are missing from this deployment.');
export const PDF_FONT_OPTIONS = {
  useSystemFonts: false,
  standardFontDataUrl: join(pdfjsDirectory, 'standard_fonts') + '/',
  cMapUrl: join(pdfjsDirectory, 'cmaps') + '/',
  cMapPacked: true,
};
