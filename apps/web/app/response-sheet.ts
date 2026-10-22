export type SourceColumnRole = "serial" | "heading" | "specification" | "quantity" | "remark" | "compliance" | "deviation" | "other";
export type ResponseSheetColumn = {
  header: string;
  role: "heading" | "requirement" | "source" | "response" | "page";
  sourceIndex?: number;
};
export type ResponseSheetRow = {
  id: string;
  sourceRequirementId: string;
  values: string[];
  section?: boolean;
};
export type ResponseSheet = { columns: ResponseSheetColumn[]; rows: ResponseSheetRow[] };
export type ResponseRequirement = {
  id: string;
  text: string;
  quote: string;
  page: number;
  parameter?: string;
  specifications?: string[];
  sourceCells?: string[];
  rowType?: "section" | "requirement" | "optional_heading";
  headingPrefix?: string;
};
export type ResponseSheetSource = {
  requirements: ResponseRequirement[];
  sourceColumns?: Array<{ header: string; role: SourceColumnRole }>;
  extractionMode?: "rule-based-preview" | "structured-table" | "visual-compliance-sheet";
  sheetProductTitle?: string;
  sectionTitle?: string;
  sheetHeading?: string;
};

function splitRequirementSubpoints(text: string): string[] {
  return text
    .split(/(?=[\uF0B7\u2022\u25CF\u25AA]\s*|(?<=\s)o\s+(?!C\b)(?=[A-Z0-9])|(?<=\s)[1-9]\.\s+(?=[A-Z]))/)
    .map((part) => part.trim())
    .filter(Boolean);
}

function splitHeadingPrefix(text: string, headingPrefix?: string): { heading: string; remainder: string } | null {
  const prefix = headingPrefix?.trim();
  if (!prefix || !text.trim()) return null;
  const escapedWords = prefix.split(/\s+/).map((word) => word.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const match = new RegExp(`^\\s*${escapedWords.join("\\s+")}(?=\\s|$)`).exec(text);
  return match ? { heading: match[0].trim(), remainder: text.slice(match[0].length) } : null;
}

export function buildResponseSheet(source: ResponseSheetSource): ResponseSheet {
  const structured = source.extractionMode === "structured-table";
  const sourceColumns = structured
    ? [
      { header: "Parameter", role: "heading" as const },
      { header: "Required Specification", role: "specification" as const },
      { header: "Compliance (Yes / No)", role: "compliance" as const },
      { header: "Any remarks", role: "remark" as const },
    ]
    : source.sourceColumns?.length
      ? source.sourceColumns
      : [{ header: "Tender specification", role: "specification" as const }];
  const hasHeadingColumn = sourceColumns.some((column) => column.role === "heading");
  const columns: ResponseSheetColumn[] = sourceColumns.flatMap((column, index): ResponseSheetColumn[] => {
    if (column.role === "heading") return [{ header: column.header || "Heading", role: "heading", sourceIndex: index }];
    if (column.role === "specification") return hasHeadingColumn
      ? [{ header: column.header || "Tender requirement", role: "requirement", sourceIndex: index }]
      : [{ header: "Heading", role: "heading" }, { header: column.header || "Tender requirement", role: "requirement", sourceIndex: index }];
    return [{ header: column.header || `Source column ${index + 1}`, role: "source", sourceIndex: index }];
  });
  if (!sourceColumns.some((column) => ["compliance", "deviation", "remark"].includes(column.role))) {
    columns.push({ header: "OEM response", role: "response" });
  }
  columns.push({ header: "Source page", role: "page" });

  const rows: ResponseSheetRow[] = [];
  const addRow = (item: ResponseRequirement, heading: string, requirement: string, rowIndex: number, section = false) => {
    const values = columns.map((column) => {
      if (column.role === "heading") return column.sourceIndex === undefined ? heading : item.sourceCells?.[column.sourceIndex] || heading;
      if (column.role === "requirement") return requirement;
      if (column.role === "response") return "";
      if (column.role === "page") return `Page ${item.page}`;
      return column.sourceIndex === undefined ? "" : item.sourceCells?.[column.sourceIndex] ?? "";
    });
    rows.push({ id: `${item.id}:${rowIndex}`, sourceRequirementId: item.id, values, ...(section ? { section: true } : {}) });
  };

  let activeHeading = source.sheetProductTitle || source.sectionTitle || "";
  const structuralLabel = /^(?:section|part|chapter|annex(?:ure)?|schedule)\s*(?:[-:.)]?\s*)?(?:[ivxlcdm]+|\d+|[a-z])\s*[.:)-]?$/i;
  if (structured) {
    for (const item of source.requirements) {
      const heading = item.parameter ?? item.text;
      let rowIndex = 0;
      for (const specification of item.specifications?.length ? item.specifications : [item.quote]) {
        for (const subpoint of splitRequirementSubpoints(specification)) {
          addRow(item, heading, subpoint.replace(/^\s*[•●]\s*/, ""), rowIndex++);
        }
      }
    }
    return { columns, rows };
  }

  let productHeading = "";
  for (const item of source.requirements) {
    const label = item.text.trim();
    if (structuralLabel.test(label)) continue;
    if (item.rowType === "optional_heading") {
      if (productHeading) addRow(item, productHeading, label, 0, true);
      else {
        activeHeading = label;
        addRow(item, label, "", 0, true);
      }
      continue;
    }
    if (item.rowType === "section") {
      if (productHeading) addRow(item, productHeading, label, 0, true);
      else if (!/^\d+(?:\.\d+)*\s/.test(label)) {
        productHeading = label;
        activeHeading = label;
        addRow(item, label, "", 0, true);
      } else {
        activeHeading = label;
        addRow(item, label, "", 0, true);
      }
      continue;
    }
    const split = splitHeadingPrefix(label, item.headingPrefix);
    const requirement = split?.remainder.trim() || label;
    if (split?.heading.trim()) {
      productHeading ||= split.heading.trim();
      activeHeading = productHeading;
    }
    const heading = productHeading || activeHeading || source.sheetHeading || "Tender requirement";
    splitRequirementSubpoints(requirement).forEach((subpoint, rowIndex) => addRow(item, heading, subpoint, rowIndex));
  }
  return { columns, rows };
}

export function updateResponseSheetCell(sheet: ResponseSheet, rowId: string, columnIndex: number, value: string): ResponseSheet {
  const column = sheet.columns[columnIndex];
  if (column?.role === "page") return sheet;
  const targetIndex = sheet.rows.findIndex((row) => row.id === rowId);
  if (targetIndex < 0) return sheet;
  let firstIndex = targetIndex;
  let lastIndex = targetIndex;
  if (column?.role === "heading" && sheet.rows[targetIndex].values[columnIndex]) {
    const oldHeading = sheet.rows[targetIndex].values[columnIndex];
    while (firstIndex > 0 && sheet.rows[firstIndex - 1].values[columnIndex] === oldHeading) firstIndex -= 1;
    while (lastIndex + 1 < sheet.rows.length && sheet.rows[lastIndex + 1].values[columnIndex] === oldHeading) lastIndex += 1;
  }
  return {
    ...sheet,
    rows: sheet.rows.map((row, rowIndex) => rowIndex >= firstIndex && rowIndex <= lastIndex
      ? { ...row, values: row.values.map((cell, index) => index === columnIndex ? value : cell) }
      : row),
  };
}

export function removeResponseSheetRow(sheet: ResponseSheet, rowId: string): ResponseSheet {
  return { ...sheet, rows: sheet.rows.filter((row) => row.id !== rowId) };
}
