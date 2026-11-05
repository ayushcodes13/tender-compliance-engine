import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { jsPDF } from 'jspdf';
import autoTable from 'jspdf-autotable';
import { createCanvas } from '@napi-rs/canvas';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const outDir = path.join(__dirname, '../test-fixtures/stress-tenders');

if (!fs.existsSync(outDir)) {
  fs.mkdirSync(outDir, { recursive: true });
}

// ----------------------------------------------------------------------------
// 1. Archetype 1: Multi-Column Specification Sheet (2-column & 3-column)
// ----------------------------------------------------------------------------
export function generateMultiColumnTender() {
  const doc = new jsPDF({ unit: 'pt', format: 'a4' });
  const fontPath = path.join(__dirname, '../public/fonts/DejaVuSans.ttf');
  const fontBase64 = fs.readFileSync(fontPath).toString('base64');
  doc.addFileToVFS('DejaVuSans.ttf', fontBase64);
  doc.addFont('DejaVuSans.ttf', 'DejaVuSans', 'normal');
  doc.setFont('DejaVuSans', 'normal');

  // Page 1: 2-Column Layout
  doc.setFontSize(16);
  doc.text('TENDER SPECIFICATION DOCUMENT: ADVANCED SPECTROSCOPY SYSTEM', 40, 45);
  doc.setFontSize(10);
  doc.text('SECTION A: GENERAL TECHNICAL SPECIFICATIONS (PARALLEL COLUMNS)', 40, 65);
  doc.setLineWidth(1);
  doc.line(40, 72, 555, 72);

  // Left Column (x: 40 to 280)
  const leftX = 40;
  const colWidth = 240;
  let leftY = 95;
  doc.setFontSize(12);
  doc.text('1. Mechanical & Structural Subsystem', leftX, leftY);
  leftY += 20;
  doc.setFontSize(9);
  const leftSpecs = [
    '• Overall system footprint shall not exceed 1200 x 800 x 1600 mm (W x D x H);',
    '• Total instrument weight: maximum 450 kg including vibration dampeners;',
    '• Enclosure protection rating: IP54 compliant for industrial dust resistance;',
    '• Structural frame: anodized aluminum profile with active leveling castors;',
    '• Acoustic noise level: < 55 dBA at 1 meter during normal operation;',
  ];
  for (const spec of leftSpecs) {
    const lines = doc.splitTextToSize(spec, colWidth);
    doc.text(lines, leftX, leftY);
    leftY += lines.length * 12 + 8;
  }

  // Right Column (x: 315 to 555)
  const rightX = 315;
  let rightY = 95;
  doc.setFontSize(12);
  doc.text('2. Electrical & Power Subsystem', rightX, rightY);
  rightY += 20;
  doc.setFontSize(9);
  const rightSpecs = [
    '• Input operating voltage: 230 V AC +/- 10%, 50 Hz single phase utility power;',
    '• Total power consumption: maximum 2.5 kW under full cryogenic load;',
    '• Power conversion efficiency: >= 92% at rated nominal load;',
    '• Emergency power off (EPO): dual circuit break interlock switch provided;',
    '• Integrated online UPS: 3 kVA true online double-conversion backup system;',
  ];
  for (const spec of rightSpecs) {
    const lines = doc.splitTextToSize(spec, colWidth);
    doc.text(lines, rightX, rightY);
    rightY += lines.length * 12 + 8;
  }

  // Page 2: 3-Column Layout
  doc.addPage();
  doc.setFontSize(14);
  doc.text('SECTION B: SUBSYSTEM DETAILED SPECIFICATIONS (3-COLUMN MATRIX)', 40, 45);
  doc.setLineWidth(1);
  doc.line(40, 52, 555, 52);

  const col3Width = 160;
  const col1X = 40;
  const col2X = 215;
  const col3X = 390;

  // Column 1: Optical
  let c1Y = 75;
  doc.setFontSize(11);
  doc.text('Optical Subsystem', col1X, c1Y);
  c1Y += 18;
  doc.setFontSize(8.5);
  const col1Specs = [
    '• Excitation laser: 532 nm +/- 0.5 nm wavelength;',
    '• Output optical power: 100 mW continuous wave;',
    '• Spectral resolution: better than 0.5 cm-1;',
    '• Beam divergence: < 1.0 mrad full angle;',
  ];
  for (const spec of col1Specs) {
    const lines = doc.splitTextToSize(spec, col3Width);
    doc.text(lines, col1X, c1Y);
    c1Y += lines.length * 11 + 6;
  }

  // Column 2: Environmental
  let c2Y = 75;
  doc.setFontSize(11);
  doc.text('Environmental Chamber', col2X, c2Y);
  c2Y += 18;
  doc.setFontSize(8.5);
  const col2Specs = [
    '• Ambient temperature range: 18 °C to 28 °C;',
    '• Relative humidity: 20% to 75% non-condensing;',
    '• Thermal stabilization time: < 30 minutes from cold start;',
    '• Heat dissipation: < 1.2 kW into ambient laboratory air;',
  ];
  for (const spec of col2Specs) {
    const lines = doc.splitTextToSize(spec, col3Width);
    doc.text(lines, col2X, c2Y);
    c2Y += lines.length * 11 + 6;
  }

  // Column 3: Digital & Control
  let c3Y = 75;
  doc.setFontSize(11);
  doc.text('Data & Control System', col3X, c3Y);
  c3Y += 18;
  doc.setFontSize(8.5);
  const col3Specs = [
    '• Communication bus: Gigabit Ethernet (1000Base-T);',
    '• Data acquisition ADC: 16-bit at 100 MSPS sampling rate;',
    '• Controller OS: Linux Ubuntu 22.04 LTS 64-bit;',
    '• Export format support: CSV, JSON, HDF5 and ASCII formats;',
  ];
  for (const spec of col3Specs) {
    const lines = doc.splitTextToSize(spec, col3Width);
    doc.text(lines, col3X, c3Y);
    c3Y += lines.length * 11 + 6;
  }

  const filePath = path.join(outDir, 'stress-multi-column.pdf');
  fs.writeFileSync(filePath, Buffer.from(doc.output('arraybuffer')));
  return filePath;
}

// ----------------------------------------------------------------------------
// 2. Archetype 2: Borderless Multi-Page Continuation Table
// ----------------------------------------------------------------------------
export function generateBorderlessTableTender() {
  const doc = new jsPDF({ unit: 'pt', format: 'a4' });
  const fontPath = path.join(__dirname, '../public/fonts/DejaVuSans.ttf');
  const fontBase64 = fs.readFileSync(fontPath).toString('base64');
  doc.addFileToVFS('DejaVuSans.ttf', fontBase64);
  doc.addFont('DejaVuSans.ttf', 'DejaVuSans', 'normal');
  doc.setFont('DejaVuSans', 'normal');

  doc.setFontSize(15);
  doc.text('ANNEXURE III: VACUUM & CRYOGENIC SPECIFICATION SCHEDULE', 40, 45);
  doc.setFontSize(9);
  doc.text('Technical specifications for high-vacuum cryogenic probe station. Borderless continuation matrix.', 40, 60);

  const headers = ['Sl. No.', 'Subsystem / Parameter', 'Technical Tender Specification', 'Compliance (Yes/No)', 'Remarks / Justifications'];

  const rows = [
    ['1.0', 'Vacuum Chamber', 'Ultimate base pressure: <= 1.0 x 10^-7 mbar within 4 hours of turbo pumping;', '', ''],
    ['2.0', 'Turbo Pump', 'Pumping speed for N2: >= 600 L/s with integrated magnetic levitation bearing;', '', ''],
    ['3.0', 'Roughing Pump', 'Dry scroll vacuum backing pump with pumping speed of >= 15 m3/h;', '', ''],
    ['4.0', 'Vacuum Gauging', 'Wide range combination gauge (Pirani / Cold Cathode) from 1000 mbar to 10^-9 mbar;', '', ''],
    ['5.0', 'Cryocooler Unit', 'Two-stage closed cycle pulse tube cryocooler providing 1.0 W cooling power at 4.2 K;', '', ''],
    ['6.0', 'Vibration Damping', 'Bellows vibration isolation interface with residual vibration amplitude < 50 nm RMS;', '', ''],
    ['7.0', 'Temperature Controller', '3-channel cryogenic temperature controller with 0.001 K sensor reading resolution;', '', ''],
    ['8.0', 'Sample Mount', 'Oxygen-free high conductivity (OFHC) copper sample stage with 50 mm diameter;', '', ''],
    ['9.0', 'Optical Viewport', 'Fused silica optical windows with anti-reflective coating for 400 nm to 1100 nm;', '', ''],
    ['10.0', 'Coaxial Cabling', 'Four semi-rigid coaxial lines rated for DC to 40 GHz with SMA connectors;', '', ''],
    ['11.0', 'Radiation Shield', 'Gold plated copper radiation shield minimizing thermal radiative heat transfer;', '', ''],
    ['12.0', 'System Warranty', 'Comprehensive 3-year on-site warranty covering cryocooler, pumps and controller;', '', ''],
  ];

  autoTable(doc, {
    startY: 80,
    head: [headers],
    body: rows,
    theme: 'plain', // Borderless theme
    showHead: 'everyPage', // Repeats header on Page 2
    rowPageBreak: 'avoid',
    styles: {
      font: 'DejaVuSans',
      fontSize: 8.5,
      cellPadding: 7,
      overflow: 'linebreak',
      valign: 'top',
    },
    headStyles: {
      font: 'DejaVuSans',
      fontStyle: 'normal',
      fillColor: [240, 243, 246],
      textColor: [15, 23, 42],
    },
    columnStyles: {
      0: { cellWidth: 45 },
      1: { cellWidth: 120 },
      2: { cellWidth: 200 },
      3: { cellWidth: 75 },
      4: { cellWidth: 75 },
    },
    margin: { left: 40, right: 40, top: 40, bottom: 40 },
  });

  const filePath = path.join(outDir, 'stress-borderless-table.pdf');
  fs.writeFileSync(filePath, Buffer.from(doc.output('arraybuffer')));
  return filePath;
}

// ----------------------------------------------------------------------------
// 3. Archetype 3: Deep Nested Numbered Clauses
// ----------------------------------------------------------------------------
export function generateNestedClausesTender() {
  const doc = new jsPDF({ unit: 'pt', format: 'a4' });
  const fontPath = path.join(__dirname, '../public/fonts/DejaVuSans.ttf');
  const fontBase64 = fs.readFileSync(fontPath).toString('base64');
  doc.addFileToVFS('DejaVuSans.ttf', fontBase64);
  doc.addFont('DejaVuSans.ttf', 'DejaVuSans', 'normal');
  doc.setFont('DejaVuSans', 'normal');

  doc.setFontSize(16);
  doc.text('SECTION 4: RADAR & RF SUBSYSTEM REQUIREMENTS', 40, 45);
  doc.setFontSize(10);
  doc.text('Hierarchical Technical Specification Clauses & Nested Verification Tree', 40, 62);
  doc.setLineWidth(1);
  doc.line(40, 70, 555, 70);

  let y = 90;
  const writeClause = (text, indent, isHeader = false) => {
    if (y > 770) {
      doc.addPage();
      y = 45;
    }
    doc.setFontSize(isHeader ? 11 : 9);
    const lines = doc.splitTextToSize(text, 515 - indent);
    doc.text(lines, 40 + indent, y);
    y += lines.length * (isHeader ? 14 : 12) + (isHeader ? 6 : 4);
  };

  writeClause('Clause 4.1 Frequency Generation & Synthesizers', 0, true);
  writeClause('4.1.1 The master microwave frequency source shall satisfy the following operational bounds:', 15);
  writeClause('(a) Frequency tuning range: 2.0 GHz to 18.0 GHz continuously tunable in 100 Hz increments;', 30);
  writeClause('(b) Output power level: +15 dBm minimum leveled power across the entire frequency spectrum;', 30);
  writeClause('(c) Spectral purity and phase noise constraints:', 30);
  writeClause('(i) Phase noise at 10 kHz offset: <= -115 dBc/Hz across all operational bands;', 45);
  writeClause('(ii) Phase noise at 100 kHz offset: <= -128 dBc/Hz at 10 GHz carrier frequency;', 45);
  writeClause('(iii) Harmonic spurious suppression: > 45 dBc below carrier at rated maximum output;', 45);

  y += 10;
  writeClause('Clause 4.2 Wideband Digital Receiver & Signal Channel', 0, true);
  writeClause('4.2.1 High-speed analog-to-digital converter (ADC) and signal channel criteria:', 15);
  writeClause('(a) Sampling rate: minimum 2.5 GSPS with 14-bit digitizer resolution;', 30);
  writeClause('(b) Analog instantaneous bandwidth: DC to 4.0 GHz (-3 dB cutoff point);', 30);
  writeClause('(c) Spurious-Free Dynamic Range (SFDR): >= 72 dBc for input tones up to 1 GHz;', 30);
  writeClause('(d) Real-time FPGA processing: Xilinx UltraScale+ FPGA with minimum 8 GB DDR4 buffer memory;', 30);

  y += 10;
  writeClause('Clause 4.3 Digital Signal Processing (DSP) Algorithms', 0, true);
  writeClause('4.3.1 Embedded DSP firmware functions:', 15);
  writeClause('(a) Polyphase filter bank: minimum 1024 channels with >= 60 dB stopband rejection;', 30);
  writeClause('(b) Real-time pulse compression: matched filter implementation for chirp waveforms up to 500 MHz;', 30);
  writeClause('(c) Latency requirement: overall pipeline processing latency shall not exceed 1.5 microseconds;', 30);

  const filePath = path.join(outDir, 'stress-nested-clauses.pdf');
  fs.writeFileSync(filePath, Buffer.from(doc.output('arraybuffer')));
  return filePath;
}

// ----------------------------------------------------------------------------
// 4. Archetype 4: Extreme Degradation & Scientific Notation (Scanned Page)
// ----------------------------------------------------------------------------
export function generateScientificDegradedTender() {
  // Create high-res canvas (1200 x 1600 px) to simulate scanned document page
  const canvas = createCanvas(1200, 1600);
  const ctx = canvas.getContext('2d');

  // Background with subtle scanner grain / off-white tint
  ctx.fillStyle = '#FAF9F6';
  ctx.fillRect(0, 0, 1200, 1600);

  // Slight scanner rotation (0.35 degrees)
  ctx.translate(600, 800);
  ctx.rotate((0.35 * Math.PI) / 180);
  ctx.translate(-600, -800);

  // Document Title
  ctx.fillStyle = '#111827';
  ctx.font = 'bold 32px sans-serif';
  ctx.fillText('SCHEDULE OF TECHNICAL SPECIFICATIONS (EPR/ESR PROBE)', 80, 120);

  ctx.font = 'normal 22px sans-serif';
  ctx.fillText('Ref: R&D-TENDER-2026-PHYSICS-09', 80, 160);

  ctx.strokeStyle = '#374151';
  ctx.lineWidth = 3;
  ctx.beginPath();
  ctx.moveTo(80, 180);
  ctx.lineTo(1120, 180);
  ctx.stroke();

  // Draw specification lines with extreme scientific notations & math symbols
  const specs = [
    { title: '1. Resonator Absolute Sensitivity', val: 'Absolute sensitivity: >= 1.5 x 10^9 spins/G line width (weak pitch sample);' },
    { title: '2. Working Frequency Range', val: 'Operational frequency band: 9.20 GHz to 9.85 GHz with 1 kHz synthesizer resolution;' },
    { title: '3. Microwave Leveled Power', val: 'Output microwave power in leveled mode: 200 mW +/- 10 mW continuous;' },
    { title: '4. Dynamic Attenuation Precision', val: 'Calibrated attenuation range: 0 to 60 dB in steps of 1 dB with precision +/- 0.25 dB;' },
    { title: '5. Sample Tube Volume Capability', val: 'Sample volume compatibility: 5 uL to 100 uL capillary tubes with quartz CFQ grade;' },
    { title: '6. Characteristic RF Impedance', val: 'Nominal microwave impedance: 50 Ohm +/- 0.5 Ohm, water-cooled circulating jacket;' },
    { title: '7. Magnetic Field Stability', val: 'Long term field stability: +/- 10 mG/hour under room temperature variation < +/- 1.0 °C;' },
    { title: '8. Cryogenic Temperature Bounds', val: 'Operating temperature span: 4.2 K to 350 K with temperature stability of +/- 0.05 K;' },
    { title: '9. Modulation Linearity', val: 'Modulation frequency: 100 kHz with harmonic distortion <= -55 dBc;' },
  ];

  let y = 240;
  for (const s of specs) {
    ctx.font = 'bold 24px sans-serif';
    ctx.fillStyle = '#1F2937';
    ctx.fillText(s.title, 80, y);
    y += 35;

    ctx.font = 'normal 22px sans-serif';
    ctx.fillStyle = '#374151';
    ctx.fillText(s.val, 110, y);
    y += 55;
  }

  // Draw subtle horizontal dividing lines
  ctx.strokeStyle = '#D1D5DB';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(80, y);
  ctx.lineTo(1120, y);
  ctx.stroke();

  // Convert canvas to JPEG buffer
  const jpegBuffer = canvas.toBuffer('image/jpeg');

  // Embed image into a 1-page PDF
  const doc = new jsPDF({ unit: 'pt', format: 'a4' });
  const imgBase64 = jpegBuffer.toString('base64');
  doc.addImage(`data:image/jpeg;base64,${imgBase64}`, 'JPEG', 0, 0, 595.28, 841.89);

  const filePath = path.join(outDir, 'stress-ocr-scientific.pdf');
  fs.writeFileSync(filePath, Buffer.from(doc.output('arraybuffer')));
  return filePath;
}

export function generateAllStressTenders() {
  console.log('Generating stress test tender corpus in:', outDir);
  const multiCol = generateMultiColumnTender();
  console.log('✓ Generated multi-column specification sheet:', multiCol);
  const borderless = generateBorderlessTableTender();
  console.log('✓ Generated borderless continuation table:', borderless);
  const nested = generateNestedClausesTender();
  console.log('✓ Generated nested numbered clauses:', nested);
  const degraded = generateScientificDegradedTender();
  console.log('✓ Generated scientific degraded scan tender:', degraded);

  return {
    multiCol,
    borderless,
    nested,
    degraded,
  };
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  generateAllStressTenders();
}
