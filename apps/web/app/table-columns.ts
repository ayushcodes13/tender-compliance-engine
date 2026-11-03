export type TableColumn = {
  header: string;
  role: "serial" | "heading" | "specification" | "quantity" | "remark" | "compliance" | "deviation" | "other";
};

/** Uses the model's per-document column map, with a conservative semantic fallback for incomplete maps. */
export function chooseRequirementColumn(columns: TableColumn[], rows: string[][]): number {
  const specification = columns.findIndex((column) => column.role === "specification");
  if (specification >= 0) return specification;

  const textColumn = columns.findIndex((column) => column.role !== "serial"
    && column.role !== "heading"
    && column.role !== "quantity"
    && column.role !== "compliance"
    && column.role !== "remark"
    && column.role !== "deviation"
    && /description|requirement|technical detail|specification|parameter/i.test(column.header));
  if (textColumn >= 0) return textColumn;

  const eligible = columns.map((column, index) => ({ column, index }))
    .filter(({ column }) => !["serial", "quantity", "compliance", "remark", "deviation", "heading"].includes(column.role));
  const candidates = eligible.length ? eligible : columns.map((column, index) => ({ column, index }))
    .filter(({ column }) => !["serial", "quantity", "compliance", "remark", "deviation"].includes(column.role));
  if (!candidates.length) return 0;
  return candidates[0].index;
}

/** A lettered group spanning the label cells with no specification value is source structure. */
export function sourceTableGroupHeading(cells: string[], columns: TableColumn[]): string | null {
  const specification = columns.findIndex((column) => column.role === "specification");
  if (specification < 0 || cells[specification]?.trim()) return null;
  const serial = columns.findIndex((column) => column.role === "serial");
  if (serial >= 0 && /^\d+(?:\.\d+)*[.)]?$/.test(cells[serial]?.trim() ?? "")) return null;
  const text = cells.filter((_, index) => !["compliance", "deviation", "remark"].includes(columns[index]?.role ?? "other"))
    .join(" ").replace(/\s+/g, " ").trim();
  return /^[A-Z][.)]\s*\S/.test(text) ? text : null;
}

/** Blank specification cells cite their label; a serial or response is never a specification. */
export function sourceRequirementCell(cells: string[], columns: TableColumn[], specificationIndex: number): {quote:string;columnIndex:number;specificationBlank:boolean} | null {
  const value = cells[specificationIndex]?.trim();
  if (value) return {quote:value,columnIndex:specificationIndex,specificationBlank:false};
  const headingIndex = columns.findIndex((column,index) => column.role === "heading" && Boolean(cells[index]?.trim()));
  if (headingIndex >= 0) return {quote:cells[headingIndex].trim(),columnIndex:headingIndex,specificationBlank:true};
  return null;
}
