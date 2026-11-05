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
  nativeHeadingPrefix?: string;
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

function isListMarkerLine(line: string): boolean {
  return /^[\uF0B7\u2022\u25CF\u25AA•●▪■◆«¢\-\*]\s+/i.test(line)
    || /^(?:[0-9]+|[a-z]|[ivxlcdm]+)[\.\)]\s+/i.test(line)
    || /^\([0-9a-zivxlcdm]+\)\s+/i.test(line);
}

export function recombinePhysicalWrappedLines(lines: string[]): string[] {
  if (lines.length <= 1) return lines;
  const combined: string[] = [];
  let current = lines[0];

  for (let i = 1; i < lines.length; i += 1) {
    const nextLine = lines[i];
    const nextIsMarker = isListMarkerLine(nextLine);
    const prevTerminatedWithDelim = /[;:]$/.test(current.trim());
    const prevEndedSentence = /\.\s*$/.test(current.trim()) && /^[A-Z0-9]/.test(nextLine);

    if (nextIsMarker || prevTerminatedWithDelim || prevEndedSentence) {
      combined.push(current);
      current = nextLine;
    } else {
      // It is a physical line wrap continuation of the same sentence
      current = `${current} ${nextLine}`;
    }
  }
  combined.push(current);
  return combined;
}

function splitInlineSubpoints(text: string): string[] {
  return text
    .split(/(?=[\uF0B7\u2022\u25CF\u25AA•●▪■◆«¢]\s*|(?<=[;.]\s+)(?:[•●▪■◆«¢]|o\s+(?=[A-Z0-9])|[1-9]\.\s+(?=[A-Z])|\([a-z0-9]+\)\s+))/)
    .map((part) => part.trim())
    .filter(Boolean);
}

export function splitRequirementSubpoints(text: string): string[] {
  const rawLines = text
    .split(/\r?\n+/)
    .map((line) => line.trim())
    .filter(Boolean);

  if (rawLines.length > 1) {
    const recombined = recombinePhysicalWrappedLines(rawLines);
    return recombined.flatMap((line) => splitInlineSubpoints(line));
  }

  return splitInlineSubpoints(text);
}

function splitHeadingPrefix(text: string, headingPrefix?: string): { heading: string; remainder: string } | null {
  const prefix = headingPrefix?.trim();
  if (!prefix || !text.trim()) return null;
  const escapedWords = prefix.split(/\s+/).map((word) => word.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const match = new RegExp(`^\\s*${escapedWords.join("\\s+")}(?=\\s|$)`).exec(text);
  return match ? { heading: match[0].trim(), remainder: text.slice(match[0].length) } : null;
}

export function isMajorUnitHeading(title: string): boolean {
  const clean = title.replace(/^[\d\.\s\-\:\(]+|[ivxlcdm]+[\.\)]\s*/i, "").trim().toLowerCase();
  if (/^(?:microwave\s+unit|console|epr\s+software|magnet\s+unit|digital\s+variable\s+temperature|warranty|experience|optional|general|technical\s+specification)/i.test(clean)) return true;
  if (/\b(?:unit|console|system|software|mainframe|package)\b/i.test(clean) && !/\b(?:magnetic\s+field\s+controller|temperature\s+controller|acquisition\s+controller)\b/i.test(clean)) return true;
  if (/^\d+\.\s+[A-Z]/.test(title.trim())) return true;
  return false;
}

function detectMultiLevelHeadings(requirements: ResponseRequirement[]): boolean {
  let activeMain = "";
  let activeSub = "";

  for (let i = 0; i < requirements.length; i++) {
    const item = requirements[i];
    const sectionCount = item.sourceSectionHeadings?.length ?? 0;
    if (sectionCount >= 2) return true;
    if (item.sourceSectionTitle) {
      if (item.parameter && item.parameter !== item.sourceSectionTitle) return true;
      if (sectionCount >= 2) return true;
    }
    if ((item.headingPrefix || item.parameter) && sectionCount >= 1) return true;

    if (item.rowType === "section" || item.rowType === "optional_heading") {
      const label = item.text.trim();
      const nextItem = requirements[i + 1];
      const isNextAlsoSection = nextItem && (nextItem.rowType === "section" || nextItem.rowType === "optional_heading");
      if (isMajorUnitHeading(label) || (isNextAlsoSection && activeMain !== label && !activeSub)) {
        activeMain = label.replace(/^[\d\.\s\-]+/, "").replace(/[\:\-]+$/, "").trim();
        activeSub = "";
      } else {
        activeSub = label.replace(/^[\d\.\s\-a-z\(\)]+[\.\:]\s*/i, "").replace(/[\:\-]+$/, "").trim();
      }
    } else {
      const split = splitHeadingPrefix(item.text.trim(), item.headingPrefix);
      if (split?.heading.trim()) {
        activeSub = split.heading.trim();
      } else if (item.parameter?.trim()) {
        activeSub = item.parameter.trim();
      }
    }

    if (activeMain && activeSub && activeMain !== activeSub) {
      return true;
    }
  }
  return false;
}

export function buildResponseSheet(source: ResponseSheetSource): ResponseSheet {
  if (source.normalizedTables) return buildGroupedTableSheet(source);
  const structured = source.extractionMode === "structured-table";
  const hasMultiLevel = !structured && detectMultiLevelHeadings(source.requirements);

  let columns: ResponseSheetColumn[];
  if (structured) {
    columns = [
      { header: "Parameter", role: "heading" },
      { header: "Required Specification", role: "requirement" },
      { header: "Compliance (Yes / No)", role: "response" },
      { header: "Any remarks", role: "response" },
    ];
  } else if (hasMultiLevel) {
    const serialCol = source.sourceColumns?.find((c) => c.role === "serial");
    const serialIndex = source.sourceColumns?.findIndex((c) => c.role === "serial") ?? -1;
    const specCol = source.sourceColumns?.find((c) => c.role === "specification");
    const specIndex = source.sourceColumns?.findIndex((c) => c.role === "specification") ?? -1;

    columns = [];
    if (serialCol && serialIndex >= 0) {
      columns.push({ header: serialCol.header || "Sl. No.", role: "source", sourceIndex: serialIndex });
    }
    columns.push(
      { header: "Section / Unit", role: "heading" },
      { header: "Subsystem / Parameter", role: "heading" },
      { header: specCol?.header || "Tender requirement", role: "requirement", ...(specIndex >= 0 ? { sourceIndex: specIndex } : {}) },
      { header: "Compliance (Yes / No)", role: "response" },
      { header: "Remarks / Justifications", role: "response" },
    );
  } else if (source.sourceColumns?.length) {
    const hasHeadingColumn = source.sourceColumns.some((column) => column.role === "heading");
    columns = source.sourceColumns.flatMap((column, index): ResponseSheetColumn[] => {
      if (column.role === "heading") return [{ header: column.header || "Heading", role: "heading", sourceIndex: index }];
      if (column.role === "specification") return hasHeadingColumn
        ? [{ header: column.header || "Tender requirement", role: "requirement", sourceIndex: index }]
        : [{ header: "Heading", role: "heading" }, { header: column.header || "Tender requirement", role: "requirement", sourceIndex: index }];
      if (column.role === "compliance") {
        return [{ header: column.header || "Compliance (Yes / No)", role: "response" }];
      }
      if (column.role === "remark" || column.role === "deviation") {
        return [{ header: column.header || "Remarks / Justifications", role: "response" }];
      }
      return [{ header: column.header || `Source column ${index + 1}`, role: "source", sourceIndex: index }];
    });
  } else {
    columns = [
      { header: "Heading", role: "heading" },
      { header: "Tender requirement", role: "requirement" },
    ];
  }

  // Ensure deterministic compliance and remarks response columns are always present when missing
  if (!structured && !hasMultiLevel) {
    const hasCompliance = columns.some((column) => /comply|compliance/i.test(column.header));
    const hasRemark = columns.some((column) => /remark|comment|deviation|justification/i.test(column.header));
    if (!hasCompliance) {
      columns.push({ header: "Compliance (Yes / No)", role: "response" });
    }
    if (!hasRemark) {
      columns.push({ header: "Remarks / Justifications", role: "response" });
    }
  }
  columns.push({ header: "Source page", role: "page" });

  const headingColumns = columns.filter((col) => col.role === "heading");
  const isMultiHeading = headingColumns.length >= 2;
  const sourceHeadingIndex = source.sourceColumns?.findIndex((column) => column.role === "heading") ?? -1;
  const sourceSerialIndex = source.sourceColumns?.findIndex((column) => column.role === "serial") ?? -1;

  const rows: ResponseSheetRow[] = [];
  const addRow = (item: ResponseRequirement, mainHeading: string, subHeading: string, requirement: string, rowIndex: number, section = false) => {
    let headingSeen = 0;
    const values = columns.map((column) => {
      if (column.role === "heading") {
        if (column.sourceIndex !== undefined) return item.sourceCells?.[column.sourceIndex] || subHeading || mainHeading;
        headingSeen++;
        if (isMultiHeading) {
          return headingSeen === 1 ? mainHeading : (subHeading || "General");
        }
        return subHeading || mainHeading;
      }
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

  let activeMainSection = source.sheetProductTitle || source.sectionTitle || "";
  let activeSubSection = "";
  const structuralLabel = /^(?:section|part|chapter|annex(?:ure)?|schedule)\s*(?:[-:.)]?\s*)?(?:[ivxlcdm]+|\d+|[a-z])\s*[.:)-]?$/i;

  if (structured) {
    for (const item of source.requirements) {
      const heading = item.parameter ?? item.text;
      let rowIndex = 0;
      for (const specification of item.specifications?.length ? item.specifications : [item.quote]) {
        for (const subpoint of splitRequirementSubpoints(specification)) {
          addRow(item, heading, heading, subpoint.replace(/^\s*[•●]\s*/, ""), rowIndex++);
        }
      }
    }
    return { columns, rows };
  }

  let previousSourceHeading = "";
  for (let itemIdx = 0; itemIdx < source.requirements.length; itemIdx++) {
    let item = source.requirements[itemIdx];
    const nextItem = source.requirements[itemIdx + 1];
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

    if (item.rowType === "optional_heading" || item.rowType === "section") {
      const isNextAlsoSection = nextItem && (nextItem.rowType === "section" || nextItem.rowType === "optional_heading");
      if (isMajorUnitHeading(label) || (isNextAlsoSection && activeMainSection !== label && !activeSubSection)) {
        activeMainSection = label.replace(/^[\d\.\s\-]+/, "").replace(/[\:\-]+$/, "").trim();
        activeSubSection = "";
      } else {
        activeSubSection = label.replace(/^[\d\.\s\-a-z\(\)]+[\.\:]\s*/i, "").replace(/[\:\-]+$/, "").trim();
      }
      continue;
    }

    const split = splitHeadingPrefix(label, item.headingPrefix);
    const requirement = split?.remainder.trim() || label;
    if (split?.heading.trim()) {
      activeSubSection = split.heading.trim();
    } else if (item.parameter?.trim()) {
      activeSubSection = item.parameter.trim();
    }

    const mainHeading = activeMainSection || source.sheetHeading || "Tender requirement";
    const subHeading = activeSubSection || mainHeading;

    const specs = item.specifications?.length ? item.specifications : [requirement];
    let rowIndex = 0;
    for (const spec of specs) {
      for (const subpoint of splitRequirementSubpoints(spec)) {
        addRow(item, mainHeading, subHeading, subpoint, rowIndex++);
      }
    }
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
    const split = splitHeadingPrefix(item.quote, item.nativeHeadingPrefix);
    if (split?.remainder.trim()) { group = split.heading; groupId = item.id; }
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
        ...(parameterIndex >= 0 ? { 2: mapping[parameterIndex].header } : {}),
        3: mapping[specificationIndex]?.header || "Description",
        4: mapping.find(column => column.role === "compliance")?.header || "Comply (Yes/No)",
        6: mapping.find(column => column.role === "remark")?.header || "Remarks / Justifications",
      },
      mergeScope: section, exportGroupId: item.exportGroupId, sectionHeadings: item.sourceSectionHeadings, headingId: groupId,
      continuationOfPrevious: item.continuationOfPrevious === true
        && parameter === ""
        && mapping.every((column, index) => column.role !== "serial" || !item.sourceCells?.[index]?.trim()),
      values: [group, section, parameter, [item.sourceSpecificationBlank ? "" : split?.remainder.trim() || item.quote, ...extras, ...sourceRemarks].join("\n"), "", "", "", `Page ${item.page}`],
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
  return { columns, rows: continued, layout: "sectioned" };
}

export function responseHeadingMergeKeys(sheet: ResponseSheet): string[] {
  const headingColumn = sheet.columns.findIndex((column) => column.role === "heading");
  return sheet.rows.map((row) => {
    const value = headingColumn < 0 ? "" : row.values[headingColumn] ?? "";
    return value && row.mergeScope ? `${row.mergeScope}\u0000${value}` : value;
  });
}
