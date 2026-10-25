export type SourceColumnRole = "serial" | "heading" | "specification" | "quantity" | "remark" | "compliance" | "deviation" | "other";
export type ResponseSheetColumn = {
  header: string;
  role: "heading" | "requirement" | "source" | "response" | "page";
  sourceIndex?: number;
};
export type ResponseSheetRow = {
  id: string;
  sourceRequirementId: string;
  sourceRequirementIds: string[];
  continuationOfPrevious?: boolean;
  values: string[];
  section?: boolean;
  mergeScope?: string;
  exportGroupId?: string;
  sectionHeadings?: string[];
  headingId?: string;
  sourceHeaders?: Partial<Record<number, string>>;
  includeParameterColumn?: boolean;
};
export type ResponseSheet = { columns: ResponseSheetColumn[]; rows: ResponseSheetRow[]; layout?: "sectioned" };
export type ResponseRequirement = {
  id: string;
  text: string;
  quote: string;
  page: number;
  continuationOfPrevious?: boolean;
  continuationSourceCellsBlank?: boolean;
  parameter?: string;
  specifications?: string[];
  sourceCells?: string[];
  sourceColumnMap?: Array<{header: string; role: string}>;
  sourceSectionTitle?: string;
  sourceSectionHeadings?: string[];
  sourceSpecificationColumnIndex?: number;
  sourceSpecificationBlank?: boolean;
  exportGroupId?: string;
  rowType?: "section" | "requirement" | "optional_heading";
  headingPrefix?: string;
};
export type ResponseSheetSource = {
  normalizedTables?: boolean;
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
  if (source.normalizedTables) return buildGroupedTableSheet(source);
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
  const sourceHeadingIndex = sourceColumns.findIndex((column) => column.role === "heading");
  const sourceSerialIndex = sourceColumns.findIndex((column) => column.role === "serial");

  const rows: ResponseSheetRow[] = [];
  const addRow = (item: ResponseRequirement, heading: string, requirement: string, rowIndex: number, section = false) => {
    const values = columns.map((column) => {
      if (column.role === "heading") return column.sourceIndex === undefined ? heading : item.sourceCells?.[column.sourceIndex] || heading;
      if (column.role === "requirement") return requirement;
      if (column.role === "response") return "";
      if (column.role === "page") return `Page ${item.page}`;
      return column.sourceIndex === undefined ? "" : item.sourceCells?.[column.sourceIndex] ?? "";
    });
    rows.push({
      id: `${item.id}:${rowIndex}`,
      sourceRequirementId: item.id,
      sourceRequirementIds: [item.id],
      ...(item.continuationOfPrevious && rowIndex === 0
        && item.continuationSourceCellsBlank === true
        ? { continuationOfPrevious: true }
        : {}),
      values,
      ...(section ? { section: true } : {}),
    });
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
  let previousSourceHeading = "";
  for (const originalItem of source.requirements) {
    let item = originalItem;
    const sourceHeading = item.sourceCells?.[sourceHeadingIndex]?.trim() ?? "";
    if (sourceHeading) previousSourceHeading = sourceHeading;
    else if (item.continuationOfPrevious && previousSourceHeading && sourceHeadingIndex >= 0) {
      const sourceCells = [...(item.sourceCells ?? [])];
      const sourceContinuationBlank = sourceHeadingIndex >= 0 && !item.sourceCells?.[sourceHeadingIndex]?.trim()
        && (sourceSerialIndex < 0 || !item.sourceCells?.[sourceSerialIndex]?.trim());
      sourceCells[sourceHeadingIndex] = previousSourceHeading;
      item = { ...item, sourceCells, continuationSourceCellsBlank: sourceContinuationBlank };
    }
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
  if (source.extractionMode === "visual-compliance-sheet") {
    const requirementIndex = columns.findIndex((column) => column.role === "requirement");
    const pageIndex = columns.findIndex((column) => column.role === "page");
    const merged: ResponseSheetRow[] = [];
    for (const row of rows) {
      const previous = merged.at(-1);
      if (row.continuationOfPrevious && previous && requirementIndex >= 0 && pageIndex >= 0) {
        previous.values[requirementIndex] = [previous.values[requirementIndex], row.values[requirementIndex]].filter(Boolean).join(" ");
        const pages = [...new Set([previous.values[pageIndex], row.values[pageIndex]]
          .flatMap((value) => [...value.matchAll(/\bPage\s+(\d+)\b/g)].map((match) => Number(match[1]))))];
        previous.values[pageIndex] = pages.length > 1 ? `Pages ${pages.join(" and ")}` : previous.values[pageIndex];
        previous.sourceRequirementIds = [...previous.sourceRequirementIds, ...row.sourceRequirementIds];
      } else {
        merged.push(row);
      }
    }
    return { columns, rows: merged };
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
    while (firstIndex > 0 && sheet.rows[firstIndex - 1].mergeScope === sheet.rows[targetIndex].mergeScope && sheet.rows[firstIndex - 1].values[columnIndex] === oldHeading) firstIndex -= 1;
    while (lastIndex + 1 < sheet.rows.length && sheet.rows[lastIndex + 1].mergeScope === sheet.rows[targetIndex].mergeScope && sheet.rows[lastIndex + 1].values[columnIndex] === oldHeading) lastIndex += 1;
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

/** Preserve source table wording while normalizing distinct schedules into one review sheet. */
function buildGroupedTableSheet(source: ResponseSheetSource): ResponseSheet {
  const columns: ResponseSheetColumn[] = [
    { header: "Equipment / group", role: "heading" },
    { header: "Annexure / section", role: "source" },
    { header: "Specification", role: "source" },
    { header: "Description", role: "requirement" },
    { header: "Comply (Yes/No)", role: "response" },
    { header: "Any deviation", role: "response" },
    { header: "Remarks / Justifications", role: "response" },
    { header: "Source page", role: "page" },
  ];
  const rows: ResponseSheetRow[] = [];
  let group = "";
  let groupId = "";
  let previousWasTable = false;
  let section = "";
  for (const item of source.requirements) {
    if (item.sourceSectionTitle && item.sourceSectionTitle !== section) {
      section = item.sourceSectionTitle;
      group = "";
      groupId = "";
    }
    if (item.rowType === "section" || item.rowType === "optional_heading") {
      group = item.quote;
      groupId = item.id;
      previousWasTable = Boolean(item.sourceColumnMap?.length);
      continue;
    }
    const mapping = item.sourceColumnMap ?? [];
    if (!mapping.length && previousWasTable) { group = ""; groupId = `general-${item.page}`; }
    previousWasTable = mapping.length > 0;
    const parameterIndex = mapping.findIndex((column) => column.role === "heading");
    const parameter = parameterIndex >= 0 ? item.sourceCells?.[parameterIndex] ?? "" : "";
    const specificationIndex = item.sourceSpecificationColumnIndex ?? mapping.findIndex((column) => column.role === "specification");
    const extras = mapping.flatMap((column, index) => {
      if (index === parameterIndex || index === specificationIndex || ["serial", "compliance", "deviation", "remark"].includes(column.role)) return [];
      const value = item.sourceCells?.[index];
      return value ? [`${column.header}: ${value}`] : [];
    });
    const sourceRemarks = mapping.flatMap((column, index) => ["remark", "deviation", "compliance"].includes(column.role) && item.sourceCells?.[index]
      ? [`${column.header}: ${item.sourceCells[index]}`] : []);
    rows.push({
      id: `${item.id}:0`, sourceRequirementId: item.id, sourceRequirementIds: [item.id],
      includeParameterColumn: mapping.length ? parameterIndex >= 0 : item.sourceCells?.length ? undefined : false,
      sourceHeaders: {
        ...(parameterIndex >= 0 ? {2: mapping[parameterIndex].header} : {}),
        3: mapping[specificationIndex]?.header || "Description",
        4: mapping.find(column => column.role === "compliance")?.header || "Comply (Yes/No)",
        6: mapping.find(column => column.role === "remark")?.header || "Remarks / Justifications",
      },
      mergeScope: section, exportGroupId: item.exportGroupId, sectionHeadings: item.sourceSectionHeadings, headingId: groupId,
      continuationOfPrevious: item.continuationOfPrevious === true
        && parameter === ""
        && mapping.every((column, index) => column.role !== "serial" || !item.sourceCells?.[index]?.trim()),
      values: [group, section, parameter, [item.sourceSpecificationBlank ? "" : item.quote, ...extras, ...sourceRemarks].join("\n"), "", "", "", `Page ${item.page}`],
    });
  }
  const merged: ResponseSheetRow[] = [];
  for (const row of rows) {
    const previous = merged.at(-1);
    if (row.exportGroupId && previous?.exportGroupId === row.exportGroupId && previous.mergeScope === row.mergeScope) {
      previous.values[3] += " " + row.values[3];
      previous.sourceRequirementIds.push(...row.sourceRequirementIds);
    } else merged.push(row);
  }
  const continued: ResponseSheetRow[] = [];
  for (const row of merged) {
    const previous = continued.at(-1);
    const currentPage = Number(row.values[7].match(/\d+/)?.[0]);
    const previousPages = [...(previous?.values[7].matchAll(/\d+/g) ?? [])].map((match) => Number(match[0]));
    if (row.continuationOfPrevious && previous && previous.mergeScope === row.mergeScope
      && previous.values[0] === row.values[0] && previousPages.at(-1) === currentPage - 1) {
      previous.values[3] += " " + row.values[3];
      previous.values[7] = `Pages ${[...previousPages, currentPage].join(" and ")}`;
      previous.sourceRequirementIds.push(...row.sourceRequirementIds);
    } else continued.push(row);
  }
  return {columns, rows: continued, layout: "sectioned"};
}

export function responseHeadingMergeKeys(sheet: ResponseSheet): string[] {
  const headingColumn = sheet.columns.findIndex((column) => column.role === "heading");
  return sheet.rows.map((row) => {
    const value = headingColumn < 0 ? "" : row.values[headingColumn] ?? "";
    return value && row.mergeScope ? `${row.mergeScope}\u0000${value}` : value;
  });
}
