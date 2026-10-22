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
