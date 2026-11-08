import type { ProductDocument, ProductDocumentPage, BoundingBox } from "./oem-compliance-engine";
import { jsPDF } from "jspdf";

export async function parseProductPdfFile(
  file: File,
  documentId?: string
): Promise<ProductDocument> {
  const pdfjs = await import("pdfjs-dist");
  pdfjs.GlobalWorkerOptions.workerSrc = "/pdf.worker.min.mjs";

  const bytes = new Uint8Array(await file.arrayBuffer());
  const loading = pdfjs.getDocument({ data: bytes, isEvalSupported: false });
  const doc = await loading.promise;

  const pages: ProductDocumentPage[] = [];

  for (let pageNumber = 1; pageNumber <= doc.numPages; pageNumber++) {
    const page = await doc.getPage(pageNumber);
    const viewport = page.getViewport({ scale: 1 });
    const textContent = await page.getTextContent();

    const lines: Array<{ text: string; bbox?: BoundingBox }> = [];
    let fullPageText = "";

    for (const item of textContent.items as Array<any>) {
      if (!item.str || !item.str.trim()) continue;
      const text = item.str.trim();
      fullPageText += `${text} `;

      // Compute normalized 0-100% bounding box
      if (item.transform && viewport.width > 0 && viewport.height > 0) {
        const x = (item.transform[4] / viewport.width) * 100;
        // PDF coordinates are bottom-up, invert y to top-down
        const y = Math.max(0, (1 - (item.transform[5] + item.height) / viewport.height) * 100);
        const width = (item.width / viewport.width) * 100;
        const height = (item.height / viewport.height) * 100;

        lines.push({
          text,
          bbox: {
            x: Math.round(x * 10) / 10,
            y: Math.round(y * 10) / 10,
            width: Math.max(1, Math.round(width * 10) / 10),
            height: Math.max(1, Math.round(height * 10) / 10),
          },
        });
      } else {
        lines.push({ text });
      }
    }

    pages.push({
      pageNumber,
      text: fullPageText.trim(),
      lines,
    });
  }

  return {
    id: documentId || `prod-${Date.now()}`,
    name: file.name,
    type: "datasheet",
    pageCount: doc.numPages,
    pages,
    uploadedAt: new Date().toISOString(),
  };
}

/**
 * Built-in OEM reference document for technical salinometer tenders,
 * allowing instant demonstration and offline testing before user uploads custom PDFs.
 */
export function getSampleProductDocument(): ProductDocument {
  return {
    id: "sample-salinometer-oem",
    name: "Auto-Salinometer-Model-8400C-Datasheet.pdf",
    type: "datasheet",
    pageCount: 3,
    uploadedAt: new Date().toISOString(),
    pages: [
      {
        pageNumber: 1,
        text: "Auto Salinometer Model 8400C High Precision Laboratory Salinometer. Measurement range: Conductivity 0 to 70 mS/cm. Salinity measurement range 2 to 42 PSU. Salinity accuracy: ±0.002 PSU at 25°C. Digital readout unit with 24-character 2-line vacuum fluorescent display standard. Dual temperature controlled oil bath.",
        lines: [
          { text: "Auto Salinometer Model 8400C High Precision Laboratory Salinometer", bbox: { x: 10, y: 12, width: 80, height: 4 } },
          { text: "Measurement range: Conductivity 0 to 70 mS/cm", bbox: { x: 10, y: 22, width: 60, height: 3 } },
          { text: "Salinity accuracy: ±0.002 PSU at 25°C", bbox: { x: 10, y: 32, width: 55, height: 3 } },
          { text: "Digital readout unit with 24-character 2-line display standard", bbox: { x: 10, y: 44, width: 68, height: 3 } },
        ],
      },
      {
        pageNumber: 2,
        text: "Operating temperature range: +15°C to +30°C. Power supply: 230 V AC ±10%, 50/60 Hz single phase. Standard computer interface RS-232 and USB port provided. Flow-through measurement cell volume 15 ml. Sample bath volume 1.5 liters.",
        lines: [
          { text: "Power supply: 230 V AC ±10%, 50/60 Hz single phase", bbox: { x: 10, y: 20, width: 65, height: 3 } },
          { text: "Standard computer interface RS-232 and USB port provided", bbox: { x: 10, y: 32, width: 70, height: 3 } },
          { text: "Operating temperature range: +15°C to +30°C", bbox: { x: 10, y: 45, width: 60, height: 3 } },
        ],
      },
      {
        pageNumber: 3,
        text: "Physical Dimensions and Weight: 550 mm x 450 mm x 350 mm. Total instrument weight: 14.5 kg. Heavy-duty transportation wooden crate with custom shock-absorbing foam inserts included. 3-year standard manufacturer warranty with annual calibration certification included.",
        lines: [
          { text: "Total instrument weight: 14.5 kg", bbox: { x: 10, y: 24, width: 45, height: 3 } },
          { text: "Heavy-duty transportation wooden crate with foam inserts included", bbox: { x: 10, y: 38, width: 75, height: 3 } },
          { text: "3-year standard manufacturer warranty with calibration certification", bbox: { x: 10, y: 52, width: 78, height: 3 } },
        ],
      },
    ],
  };
}

export function getSampleProductFile(): File {
  const doc = new jsPDF();

  // Page 1
  doc.setFontSize(16);
  doc.text("Auto Salinometer Model 8400C", 14, 22);
  doc.setFontSize(12);
  doc.text("High Precision Laboratory Salinometer Datasheet", 14, 30);
  doc.setFontSize(10);
  doc.text("Measurement range: Conductivity 0 to 70 mS/cm", 14, 45);
  doc.text("Salinity measurement range 2 to 42 PSU", 14, 55);
  doc.text("Salinity accuracy: ±0.002 PSU at 25°C", 14, 65);
  doc.text("Digital readout unit with 24-character 2-line display standard", 14, 75);
  doc.text("Dual temperature controlled oil bath", 14, 85);

  // Page 2
  doc.addPage();
  doc.setFontSize(14);
  doc.text("Electrical & Environmental Specifications", 14, 22);
  doc.setFontSize(10);
  doc.text("Power supply: 230 V AC ±10%, 50/60 Hz single phase", 14, 40);
  doc.text("Standard computer interface RS-232 and USB port provided", 14, 52);
  doc.text("Operating temperature range: +15°C to +30°C", 14, 64);
  doc.text("Sample bath volume 1.5 liters", 14, 76);

  // Page 3
  doc.addPage();
  doc.setFontSize(14);
  doc.text("Physical Dimensions & Warranty", 14, 22);
  doc.setFontSize(10);
  doc.text("Total instrument weight: 14.5 kg", 14, 40);
  doc.text("Heavy-duty transportation wooden crate with foam inserts included", 14, 52);
  doc.text("3-year standard manufacturer warranty with calibration certification", 14, 64);

  const arrayBuffer = doc.output("arraybuffer");
  return new File([arrayBuffer], "Auto-Salinometer-Model-8400C-Datasheet.pdf", { type: "application/pdf" });
}
